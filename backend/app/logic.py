"""議題の結果と価値観マップの計算。"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Event, Statement, Story, Topic, User, Vote
from .values import AXES, MAP_COMPLETE_TOPICS

# 賛成率を「参考値」でなく表示するのに必要な、賛成＋反対の人数
MIN_N = 5
# 合意・分かれ目の判定（賛成率）
CONSENSUS_HIGH = 0.7
CONSENSUS_LOW = 0.3
DIVIDED_LOW, DIVIDED_HIGH = 0.4, 0.6
SHOW_REASONS = 3
SHOW_STORIES = 3
HIST_BINS = 5


def visible_statements(db: Session, topic_id: int) -> list[Statement]:
    return list(db.scalars(
        select(Statement).where(Statement.topic_id == topic_id, Statement.hidden.is_(False)).order_by(Statement.id)
    ))


def completed_topic_ids(db: Session, user_id: int) -> set[int]:
    return set(db.scalars(
        select(Event.topic_id).where(Event.user_id == user_id, Event.name == "topic_complete")
    ))


def _label(agree_rate: float | None, n: int) -> str:
    if agree_rate is None or n < MIN_N:
        return "few"
    if agree_rate >= CONSENSUS_HIGH:
        return "consensus_agree"
    if agree_rate <= CONSENSUS_LOW:
        return "consensus_disagree"
    if DIVIDED_LOW <= agree_rate <= DIVIDED_HIGH:
        return "divided"
    return "leaning"


def topic_results(db: Session, topic: Topic, user: User | None) -> dict:
    stmts = visible_statements(db, topic.id)
    sids = [s.id for s in stmts]
    votes = list(db.scalars(select(Vote).where(Vote.statement_id.in_(sids)))) if sids else []
    students = set(db.scalars(select(User.id).where(User.is_student.is_(True))))
    stories = list(db.scalars(
        select(Story).where(Story.statement_id.in_(sids), Story.hidden.is_(False)).order_by(Story.id.desc())
    )) if sids else []

    by_stmt: dict[int, list[Vote]] = defaultdict(list)
    for v in votes:
        by_stmt[v.statement_id].append(v)
    stories_by_stmt: dict[int, list[Story]] = defaultdict(list)
    for st in stories:
        stories_by_stmt[st.statement_id].append(st)

    items = []
    n_majority = n_rated = 0
    for s in stmts:
        vs = by_stmt[s.id]
        agree = sum(1 for v in vs if v.value == 1)
        disagree = sum(1 for v in vs if v.value == -1)
        n = agree + disagree
        rate = agree / n if n else None
        st_vs = [v for v in vs if v.user_id in students and v.value != 0]
        st_n = len(st_vs)
        st_rate = (sum(1 for v in st_vs if v.value == 1) / st_n) if st_n >= MIN_N else None
        mine = next((v for v in vs if user and v.user_id == user.id), None)
        my_vote = mine.value if mine else None
        same_rate = None
        if my_vote in (1, -1) and n:
            same_rate = (agree if my_vote == 1 else disagree) / n
            if n >= MIN_N:
                n_rated += 1
                if same_rate >= 0.5:
                    n_majority += 1

        reasons = {"agree": [], "disagree": []}
        for v in sorted(vs, key=lambda v: v.id, reverse=True):
            if not v.reason or v.reason_hidden or (user and v.user_id == user.id) or v.value == 0:
                continue
            side = "agree" if v.value == 1 else "disagree"
            if len(reasons[side]) < SHOW_REASONS:
                reasons[side].append({"id": v.id, "text": v.reason})
        story_groups = {"agree": [], "disagree": [], "other": []}
        for st in stories_by_stmt[s.id]:
            side = {1: "agree", -1: "disagree"}.get(st.stance, "other")
            if len(story_groups[side]) < SHOW_STORIES:
                story_groups[side].append({"id": st.id, "body": st.body, "mine": bool(user and st.user_id == user.id)})

        items.append({
            "id": s.id,
            "body": s.body,
            "axis_key": s.axis_key,
            "agree": agree,
            "disagree": disagree,
            "pass": sum(1 for v in vs if v.value == 0),
            "n": n,
            "agree_rate": rate,
            "student_agree_rate": st_rate,
            "label": _label(rate, n),
            "my_vote": my_vote,
            "my_reason": mine.reason if mine else None,
            "same_rate": same_rate,
            "reasons": reasons,
            "stories": story_groups,
            "n_stories": len(stories_by_stmt[s.id]),
        })

    minority = [i for i in items if i["same_rate"] is not None and i["n"] >= MIN_N and i["same_rate"] < 0.5]
    minority.sort(key=lambda i: i["same_rate"])
    return {
        "n_participants": len({v.user_id for v in votes}),
        "min_n": MIN_N,
        "statements": items,
        "summary": {
            "n_answered": sum(1 for i in items if i["my_vote"] is not None),
            "n_rated": n_rated,
            "n_majority": n_majority,
            "most_minority": (
                {"id": minority[0]["id"], "body": minority[0]["body"], "same_rate": minority[0]["same_rate"]}
                if minority else None
            ),
        },
    }


def _axis_scores(db: Session) -> dict[int, dict[str, list[tuple[int, int, int]]]]:
    """利用者ごと・軸ごとの (statement_id, vote, direction) の一覧。わからない（0）は除く。"""
    rows = db.execute(
        select(Vote.user_id, Vote.statement_id, Vote.value, Statement.axis_key, Statement.direction)
        .join(Statement, Statement.id == Vote.statement_id)
        .where(Statement.axis_key.is_not(None), Statement.hidden.is_(False), Vote.value != 0)
    ).all()
    out: dict[int, dict[str, list[tuple[int, int, int]]]] = defaultdict(lambda: defaultdict(list))
    for uid, sid, value, axis, direction in rows:
        out[uid][axis].append((sid, value, direction or 1))
    return out


def _score(entries: list[tuple[int, int, int]]) -> float | None:
    if not entries:
        return None
    return sum(v * d for _, v, d in entries) / len(entries)


def _bin(score: float) -> int:
    return min(HIST_BINS - 1, int((score + 1) / 2 * HIST_BINS))


def value_map(db: Session, user: User) -> dict:
    done = completed_topic_ids(db, user.id)
    all_scores = _axis_scores(db)
    mine = all_scores.get(user.id, {})
    sids = {sid for entries in mine.values() for sid, _, _ in entries}
    stmt_info = {}
    if sids:
        for s, t_title in db.execute(
            select(Statement, Topic.title).join(Topic, Topic.id == Statement.topic_id).where(Statement.id.in_(sids))
        ).all():
            stmt_info[s.id] = (s.body, t_title)

    axes = []
    for ax in AXES:
        hist = [0] * HIST_BINS
        for per_user in all_scores.values():
            sc = _score(per_user.get(ax["key"], []))
            if sc is not None:
                hist[_bin(sc)] += 1
        entries = mine.get(ax["key"], [])
        score = _score(entries)
        axes.append({
            **ax,
            "score": score,
            "n_used": len(entries),
            "my_bin": _bin(score) if score is not None else None,
            "histogram": hist,
            "basis": [
                {
                    "statement_id": sid,
                    "body": stmt_info.get(sid, ("", ""))[0],
                    "topic_title": stmt_info.get(sid, ("", ""))[1],
                    "my_vote": v,
                    "toward": ax["right"] if v * d > 0 else ax["left"],
                }
                for sid, v, d in entries
            ],
        })

    scored = [a for a in axes if a["score"] is not None and abs(a["score"]) > 0]
    scored.sort(key=lambda a: abs(a["score"]), reverse=True)
    type_name = None
    if scored:
        words = [a["right_word"] if a["score"] > 0 else a["left_word"] for a in scored[:2]]
        type_name = "×".join(words) + "タイプ"
    code = "".join(
        (a["right_word"][0] if a["score"] > 0 else a["left_word"][0]) if a["score"] else "・"
        for a in axes
    ) if any(a["score"] is not None for a in axes) else None

    return {
        "completed_topics": len(done),
        "required": MAP_COMPLETE_TOPICS,
        "complete": len(done) >= MAP_COMPLETE_TOPICS,
        "type_name": type_name,
        "code": code,
        "axes": axes,
    }

"""管理者向けの集計（漏斗・離脱位置・再訪・理解度）。すべて events などの生データから毎回数える。"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .logic import visible_statements
from .models import Event, Flag, Statement, Story, Topic, Understanding, Vote
from .values import MAP_COMPLETE_TOPICS

JST = timezone(timedelta(hours=9))
RETURN_WINDOW_DAYS = 7

# 利用者が画面から送ってよいイベント。ほかはサーバーが自分で記録する
CLIENT_EVENTS = {"visit", "topic_view", "result_view", "story_read", "map_view", "share", "profile_skip"}


def _jst_date(dt):
    if dt.tzinfo is None:  # SQLite は tz を落とすので UTC として扱う
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(JST).date()


def compute_metrics(db: Session) -> dict:
    events = db.execute(select(Event.user_id, Event.name, Event.topic_id, Event.created_at)).all()

    users_by: dict[str, set[int]] = defaultdict(set)
    topics_started: dict[int, set[int]] = defaultdict(set)
    topics_done: dict[int, set[int]] = defaultdict(set)
    visit_days: dict[int, set] = defaultdict(set)
    viewers: dict[int, set[int]] = defaultdict(set)
    daily = Counter()
    for uid, name, topic_id, created in events:
        if uid is None:
            continue
        users_by[name].add(uid)
        if name == "topic_first_vote" and topic_id:
            topics_started[uid].add(topic_id)
        if name == "topic_complete" and topic_id:
            topics_done[uid].add(topic_id)
        if name == "topic_view" and topic_id:
            viewers[topic_id].add(uid)
        if name == "visit":
            visit_days[uid].add(_jst_date(created))
        if name in ("visit", "vote"):
            daily[(_jst_date(created).isoformat(), name)] += 1

    def with_at_least(d: dict[int, set[int]], k: int) -> set[int]:
        return {uid for uid, s in d.items() if len(s) >= k}

    steps = [
        ("visit", "サイトを開いた", users_by["visit"]),
        ("topic_view", "議題を開いた", users_by["topic_view"]),
        ("first_vote", "1票目を入れた", users_by["first_vote"]),
        ("complete1", "1議題を完答", with_at_least(topics_done, 1)),
        ("result_view", "結果を見た", users_by["result_view"]),
        ("start2", "2議題目を始めた", with_at_least(topics_started, 2)),
        ("complete2", "2議題を完答", with_at_least(topics_done, 2)),
        ("map_complete", f"マップ完成（{MAP_COMPLETE_TOPICS}議題）", with_at_least(topics_done, MAP_COMPLETE_TOPICS)),
        ("share", "共有した", users_by["share"]),
    ]
    # 漏斗は「前の段階をすべて通った人」だけを数える。raw は段階を飛ばした人も含む人数
    funnel = []
    passed: set[int] | None = None
    for key, label, users in steps:
        passed = set(users) if passed is None else passed & users
        funnel.append({"key": key, "label": label, "users": len(passed), "raw": len(users)})

    # 再訪：初回訪問日から7日以内に、別の日にも訪問した人
    returned = 0
    for days in visit_days.values():
        first = min(days)
        if any(0 < (d - first).days <= RETURN_WINDOW_DAYS for d in days):
            returned += 1

    # 議題別：開いた・始めた・完答・離脱位置（完答しなかった人が何問目で止まったか）
    votes_per = Counter(
        (uid, tid) for uid, tid in db.execute(
            select(Vote.user_id, Vote.topic_id).join(Statement, Statement.id == Vote.statement_id)
            .where(Statement.hidden.is_(False))
        ).all()
    )
    und = defaultdict(list)
    for tid, score in db.execute(select(Understanding.topic_id, Understanding.score)).all():
        und[tid].append(score)
    per_topic = []
    for t in db.scalars(select(Topic).order_by(Topic.id)):
        n_stmts = len(visible_statements(db, t.id))
        voters = {uid for (uid, tid) in votes_per if tid == t.id}
        done = {uid for uid, s in topics_done.items() if t.id in s}
        stops = Counter(votes_per[(uid, t.id)] for uid in voters - done)
        scores = und.get(t.id, [])
        per_topic.append({
            "id": t.id,
            "title": t.title,
            "origin": t.origin,
            "hidden": t.hidden,
            "n_statements": n_stmts,
            "viewers": len(viewers[t.id]),
            "voters": len(voters),
            "completers": len(done),
            "dropoff": [{"answered": k, "users": stops[k]} for k in sorted(stops)],
            "understanding_avg": (sum(scores) / len(scores)) if scores else None,
            "understanding_n": len(scores),
        })

    all_scores = [s for v in und.values() for s in v]
    today = _jst_date(datetime.now(timezone.utc))
    days = [(today - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]

    return {
        "funnel": funnel,
        "return_7d": {"visitors": len(visit_days), "returned": returned},
        "understanding": {
            "avg": (sum(all_scores) / len(all_scores)) if all_scores else None,
            "n": len(all_scores),
            "dist": [all_scores.count(i) for i in range(1, 6)],
        },
        "content": {
            "reasons": db.scalar(select(func.count()).select_from(Vote).where(Vote.reason.is_not(None))) or 0,
            "stories": db.scalar(select(func.count()).select_from(Story)) or 0,
            "story_readers": len(users_by["story_read"]),
            "user_statements": db.scalar(select(func.count()).select_from(Statement).where(Statement.origin == "user")) or 0,
            "user_topics": db.scalar(select(func.count()).select_from(Topic).where(Topic.origin == "user")) or 0,
            "flags": db.scalar(select(func.count()).select_from(Flag)) or 0,
        },
        "daily": [{"date": d, "visits": daily[(d, "visit")], "votes": daily[(d, "vote")]} for d in days],
        "topics": per_topic,
    }

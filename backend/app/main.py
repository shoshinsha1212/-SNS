"""FastAPI エンドポイント実装（docs/06_API仕様.md 準拠）。"""

from __future__ import annotations

import csv
import io
import secrets
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db import SessionLocal, get_db, init_db
from .models import (
    AnalysisSnapshot,
    Contribution,
    PositionAxis,
    PositionOption,
    ReportVersion,
    Statement,
    StatementStats,
    Story,
    StoryReaction,
    StoryStatementLink,
    Topic,
    User,
    UserAttribute,
    UserTopicPosition,
    VoteEvent,
    utcnow,
)
from .seed import ensure_seeded
from .services.ai_service import (
    anonymize_story,
    check_duplicate,
    check_moderation,
    convert_complaint,
    generate_bridges,
    suggest_axes,
    suggest_initial_statements,
)
from .services.analysis_service import (
    META_ATTRIBUTES,
    build_story_cards,
    compute_by_position,
    get_diagnosis_data,
    get_dimensions_for_topic,
    get_latest_votes,
    get_map_data,
    get_user_position_snapshot,
    run_analysis,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        ensure_seeded(db)
    yield


app = FastAPI(title="成果型SNS API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 認証ヘルパー ----------
def get_optional_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    return db.scalars(select(User).where(User.token == token)).first()


def get_current_user(user: User | None = Depends(get_optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    return user


def _serialize_user(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "handle": u.handle,
        "attributes": {a.key: a.value for a in u.attributes},
    }


def _topic_summary(db: Session, topic: Topic) -> dict[str, Any]:
    n_statements = db.scalar(
        select(func.count(Statement.id)).where(
            Statement.topic_id == topic.id, Statement.status == "active"
        )
    ) or 0
    n_participants = db.scalar(
        select(func.count(func.distinct(VoteEvent.user_id))).where(VoteEvent.topic_id == topic.id)
    ) or 0
    latest_rep = db.scalars(
        select(ReportVersion)
        .where(ReportVersion.topic_id == topic.id)
        .order_by(ReportVersion.id.desc())
    ).first()
    return {
        "id": topic.id,
        "title": topic.title,
        "description": topic.description,
        "status": topic.status,
        "n_participants": int(n_participants),
        "n_statements": int(n_statements),
        "report_version": latest_rep.version if latest_rep else None,
    }


def _topic_detail(db: Session, topic: Topic, user: User | None) -> dict[str, Any]:
    base = _topic_summary(db, topic)
    axes_out = [
        {
            "id": ax.id,
            "name": ax.name,
            "options": [{"id": opt.id, "label": opt.label} for opt in ax.options],
        }
        for ax in topic.axes
    ]
    my_positions: dict[str, int] = {}
    voted_count = 0
    if user:
        pos_rows = db.scalars(
            select(UserTopicPosition).where(
                UserTopicPosition.user_id == user.id,
                UserTopicPosition.topic_id == topic.id,
                UserTopicPosition.valid_to.is_(None),
            )
        ).all()
        for r in pos_rows:
            my_positions[str(r.axis_id)] = r.option_id
        voted_count = db.scalar(
            select(func.count(func.distinct(VoteEvent.statement_id))).where(
                VoteEvent.topic_id == topic.id, VoteEvent.user_id == user.id
            )
        ) or 0

    latest_snap = db.scalars(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.topic_id == topic.id)
        .order_by(AnalysisSnapshot.id.desc())
    ).first()
    votes_since = 0
    if latest_snap:
        votes_since = db.scalar(
            select(func.count(VoteEvent.id)).where(
                VoteEvent.topic_id == topic.id, VoteEvent.id > latest_snap.last_vote_event_id
            )
        ) or 0
    else:
        votes_since = db.scalar(
            select(func.count(VoteEvent.id)).where(VoteEvent.topic_id == topic.id)
        ) or 0

    return {
        **base,
        "axes": axes_out,
        "my_positions": my_positions,
        "my_progress": {"voted": int(voted_count), "total": base["n_statements"]},
        "analysis": {
            "last_computed_at": latest_snap.computed_at.isoformat() if latest_snap else None,
            "votes_since": int(votes_since),
        },
    }


def _statement_brief(db: Session, st: Statement, user: User | None) -> dict[str, Any]:
    n_stories = db.scalar(
        select(func.count(StoryStatementLink.id)).where(StoryStatementLink.statement_id == st.id)
    ) or 0
    return {
        "id": st.id,
        "text": st.body,
        "origin": st.origin,
        "author_is_me": bool(user and st.author_id == user.id),
        "n_stories": int(n_stories),
    }


# ---------- リクエストスキーマ ----------
class CreateUserReq(BaseModel):
    handle: str = Field(min_length=1, max_length=50)
    attributes: dict[str, str] = Field(default_factory=dict)


class SuggestAxesReq(BaseModel):
    title: str
    description: str = ""


class AxisCreateIn(BaseModel):
    name: str
    options: list[str]


class CreateTopicReq(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = ""
    axes: list[AxisCreateIn] = Field(default_factory=list)
    initial_statements: list[str] = Field(default_factory=list)


class PutPositionsReq(BaseModel):
    positions: dict[str, int]


class ConvertReq(BaseModel):
    text: str


class StoryIn(BaseModel):
    kind: str = "present"
    body: str


class CreateStatementReq(BaseModel):
    text: str = Field(min_length=4, max_length=200)
    origin: str = "user"
    story: StoryIn | None = None


class VoteReq(BaseModel):
    value: int


class AnonymizeReq(BaseModel):
    body: str


class PostStoryReq(BaseModel):
    kind: str = "past"
    body: str = Field(min_length=4)
    summary: str | None = None
    stance: str = "supports"


class ReactionReq(BaseModel):
    kind: str


# ---------- ユーザー・メタ情報 ----------
@app.get("/api/meta")
def api_meta():
    return {"attributes": META_ATTRIBUTES}


@app.post("/api/users")
def api_create_user(req: CreateUserReq, db: Session = Depends(get_db)):
    token = secrets.token_hex(24)
    u = User(handle=req.handle.strip(), token=token, trust_level=1, is_synthetic=False)
    db.add(u)
    db.flush()
    valid_keys = {a["key"] for a in META_ATTRIBUTES}
    for k, v in req.attributes.items():
        if k in valid_keys and v:
            db.add(UserAttribute(user_id=u.id, key=k, value=v))
    db.commit()
    db.refresh(u)
    return {"user": _serialize_user(u), "token": token}


@app.get("/api/me")
def api_get_me(user: User = Depends(get_current_user)):
    return _serialize_user(user)


@app.get("/api/me/contributions")
def api_get_contributions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Contribution)
        .where(Contribution.user_id == user.id)
        .order_by(Contribution.created_at.desc(), Contribution.id.desc())
    ).all()
    out = []
    for c in rows:
        rep = db.get(ReportVersion, c.report_version_id)
        topic = db.get(Topic, rep.topic_id) if rep else None
        ref_text = ""
        if c.ref_type == "statement":
            st = db.get(Statement, c.ref_id)
            ref_text = st.body if st else ""
        elif c.ref_type == "story":
            so = db.get(Story, c.ref_id)
            ref_text = (so.summary or so.body[:60]) if so else ""
        out.append(
            {
                "topic_id": topic.id if topic else 0,
                "topic_title": topic.title if topic else "",
                "report_version": rep.version if rep else None,
                "kind": c.kind,
                "ref_type": c.ref_type,
                "ref_id": c.ref_id,
                "ref_text": ref_text,
                "weight": c.weight,
                "created_at": c.created_at.isoformat(),
            }
        )
    return out


# ---------- トピック ----------
@app.get("/api/topics")
def api_list_topics(db: Session = Depends(get_db)):
    topics = db.scalars(select(Topic).order_by(Topic.id.asc())).all()
    return [_topic_summary(db, t) for t in topics]


@app.post("/api/topics/suggest-axes")
def api_suggest_axes(req: SuggestAxesReq):
    return suggest_axes(req.title, req.description)


@app.post("/api/topics/suggest-statements")
def api_suggest_statements(req: SuggestAxesReq):
    return suggest_initial_statements(req.title, req.description)


@app.post("/api/topics")
def api_create_topic(
    req: CreateTopicReq,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    axes_in = req.axes[:3]
    if not axes_in:
        suggested = suggest_axes(req.title, req.description)["axes"]
        axes_in = [AxisCreateIn(name=a["name"], options=a["options"]) for a in suggested[:2]]

    topic = Topic(
        title=req.title.strip(),
        description=req.description.strip(),
        status="open",
        created_by=user.id,
    )
    db.add(topic)
    db.flush()

    for idx, ax_in in enumerate(axes_in):
        opts_clean = [o.strip() for o in ax_in.options if o.strip()][:6]
        if "当てはまらない" not in opts_clean:
            opts_clean.append("当てはまらない")
        if len(opts_clean) < 2:
            continue
        ax = PositionAxis(
            topic_id=topic.id,
            name=ax_in.name.strip(),
            source="admin",
            order=idx,
        )
        db.add(ax)
        db.flush()
        for lbl in opts_clean:
            db.add(PositionOption(axis_id=ax.id, label=lbl))

    # 初期論点（投票項目）の登録
    stmts_to_add = [s.strip() for s in req.initial_statements if s.strip() and len(s.strip()) >= 4]
    if not stmts_to_add:
        # 入力がない場合はAIが初期論点候補を自動生成して初期セット
        auto_stmts = suggest_initial_statements(req.title, req.description)["statements"]
        stmts_to_add = auto_stmts[:4]

    for s_body in stmts_to_add:
        st = Statement(
            topic_id=topic.id,
            author_id=user.id,
            body=s_body[:200],
            origin="seed",
            status="active",
        )
        db.add(st)

    db.commit()
    db.refresh(topic)
    return _topic_detail(db, topic, user)


@app.get("/api/topics/{topic_id}")
def api_get_topic(
    topic_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")
    return _topic_detail(db, topic, user)


@app.put("/api/topics/{topic_id}/positions")
def api_put_positions(
    topic_id: int,
    req: PutPositionsReq,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")

    valid_axes = {ax.id: {o.id for o in ax.options} for ax in topic.axes}
    now = utcnow()
    for axis_key, opt_id in req.positions.items():
        ax_id = int(axis_key)
        if ax_id not in valid_axes or opt_id not in valid_axes[ax_id]:
            raise HTTPException(status_code=422, detail="無効な立場の選択肢です")
        current = db.scalars(
            select(UserTopicPosition).where(
                UserTopicPosition.user_id == user.id,
                UserTopicPosition.topic_id == topic.id,
                UserTopicPosition.axis_id == ax_id,
                UserTopicPosition.valid_to.is_(None),
            )
        ).all()
        for row in current:
            row.valid_to = now
        db.add(
            UserTopicPosition(
                user_id=user.id,
                topic_id=topic.id,
                axis_id=ax_id,
                option_id=opt_id,
                valid_from=now,
            )
        )
    db.commit()
    db.refresh(topic)
    return _topic_detail(db, topic, user)


@app.post("/api/topics/{topic_id}/analyze")
def api_analyze_topic(topic_id: int, db: Session = Depends(get_db)):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")
    return run_analysis(db, topic.id)


# ---------- 原則と投票 ----------
@app.get("/api/topics/{topic_id}/next-statement")
def api_next_statement(
    topic_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")
    statements = db.scalars(
        select(Statement)
        .where(Statement.topic_id == topic_id, Statement.status == "active")
        .order_by(Statement.id.asc())
    ).all()
    voted_ids: set[int] = set()
    if user:
        voted_ids = set(
            db.scalars(
                select(func.distinct(VoteEvent.statement_id)).where(
                    VoteEvent.topic_id == topic_id, VoteEvent.user_id == user.id
                )
            ).all()
        )
    unvoted = [s for s in statements if s.id not in voted_ids]
    next_st = unvoted[0] if unvoted else None
    return {
        "statement": _statement_brief(db, next_st, user) if next_st else None,
        "progress": {"voted": len(voted_ids), "total": len(statements)},
    }


@app.get("/api/topics/{topic_id}/statements")
def api_list_statements(
    topic_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")
    statements = db.scalars(
        select(Statement)
        .where(Statement.topic_id == topic_id, Statement.status == "active")
        .order_by(Statement.id.asc())
    ).all()
    latest_votes = get_latest_votes(db, topic_id)
    latest_snap = db.scalars(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.topic_id == topic_id)
        .order_by(AnalysisSnapshot.id.desc())
    ).first()
    stats_by_sid: dict[int, StatementStats] = {}
    if latest_snap:
        stats_by_sid = {
            s.statement_id: s
            for s in db.scalars(
                select(StatementStats).where(StatementStats.snapshot_id == latest_snap.id)
            ).all()
        }

    out = []
    for st in statements:
        sid = st.id
        ag = sum(1 for (_, s), ev in latest_votes.items() if s == sid and ev.value == 1)
        dis = sum(1 for (_, s), ev in latest_votes.items() if s == sid and ev.value == -1)
        pas = sum(1 for (_, s), ev in latest_votes.items() if s == sid and ev.value == 0)
        my_v = latest_votes[(user.id, sid)].value if (user and (user.id, sid) in latest_votes) else None
        st_stat = stats_by_sid.get(sid)
        out.append(
            {
                **_statement_brief(db, st, user),
                "my_vote": my_v,
                "counts": {"agree": ag, "disagree": dis, "pass": pas},
                "section": st_stat.section if st_stat else None,
                "gap": st_stat.gap if st_stat else None,
            }
        )
    return out


@app.post("/api/topics/{topic_id}/convert")
def api_convert_complaint(topic_id: int, req: ConvertReq, db: Session = Depends(get_db)):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")
    return convert_complaint(topic.title, topic.description, req.text)


@app.post("/api/topics/{topic_id}/statements")
def api_post_statement(
    topic_id: int,
    req: CreateStatementReq,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")

    body = req.text.strip()
    mod_err = check_moderation(body)
    if mod_err:
        return {"statement": None, "merged_into": None, "rejected_reason": mod_err}

    existing = [
        (s.id, s.body)
        for s in db.scalars(
            select(Statement).where(Statement.topic_id == topic_id, Statement.status == "active")
        ).all()
    ]
    dup = check_duplicate(body, existing)
    if dup is not None:
        dup_id, dup_text = dup
        merged_st = Statement(
            topic_id=topic_id,
            author_id=user.id,
            body=body[:200],
            origin=req.origin if req.origin in ("user", "ai_from_complaint") else "user",
            status="merged",
            merged_into=dup_id,
        )
        db.add(merged_st)
        if req.story and req.story.body.strip():
            snap = get_user_position_snapshot(db, user.id, topic_id)
            anon = anonymize_story(req.story.body)
            st_obj = Story(
                author_id=user.id,
                topic_id=topic_id,
                kind=req.story.kind if req.story.kind in ("past", "present", "future") else "present",
                body=anon["masked_body"],
                summary=anon["summary"],
                anonymization="ai_masked_user_approved",
                position_snapshot=snap,
            )
            db.add(st_obj)
            db.flush()
            db.add(StoryStatementLink(story_id=st_obj.id, statement_id=dup_id, stance="supports"))
        db.commit()
        return {"statement": None, "merged_into": {"id": dup_id, "text": dup_text}, "rejected_reason": None}

    st = Statement(
        topic_id=topic_id,
        author_id=user.id,
        body=body[:200],
        origin=req.origin if req.origin in ("user", "ai_from_complaint") else "user",
        status="active",
    )
    db.add(st)
    db.flush()

    snap = get_user_position_snapshot(db, user.id, topic_id)
    # 投稿者自身の賛成票を記録
    db.add(
        VoteEvent(
            user_id=user.id,
            statement_id=st.id,
            topic_id=topic_id,
            value=1,
            position_snapshot=snap,
        )
    )

    if req.story and req.story.body.strip():
        anon = anonymize_story(req.story.body)
        st_obj = Story(
            author_id=user.id,
            topic_id=topic_id,
            kind=req.story.kind if req.story.kind in ("past", "present", "future") else "present",
            body=anon["masked_body"],
            summary=anon["summary"],
            anonymization="ai_masked_user_approved",
            position_snapshot=snap,
        )
        db.add(st_obj)
        db.flush()
        db.add(StoryStatementLink(story_id=st_obj.id, statement_id=st.id, stance="supports"))

    db.commit()
    db.refresh(st)
    return {
        "statement": _statement_brief(db, st, user),
        "merged_into": None,
        "rejected_reason": None,
    }


@app.get("/api/statements/{statement_id}")
def api_get_statement(
    statement_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    st = db.get(Statement, statement_id)
    if not st:
        raise HTTPException(status_code=404, detail="原則が見つかりません")
    topic = db.get(Topic, st.topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")

    latest_votes = get_latest_votes(db, topic.id)
    ag = sum(1 for (_, s), ev in latest_votes.items() if s == st.id and ev.value == 1)
    dis = sum(1 for (_, s), ev in latest_votes.items() if s == st.id and ev.value == -1)
    pas = sum(1 for (_, s), ev in latest_votes.items() if s == st.id and ev.value == 0)
    my_v = latest_votes[(user.id, st.id)].value if (user and (user.id, st.id) in latest_votes) else None

    latest_snap = db.scalars(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.topic_id == topic.id)
        .order_by(AnalysisSnapshot.id.desc())
    ).first()
    stats_out = None
    if latest_snap:
        s_row = db.scalars(
            select(StatementStats).where(
                StatementStats.snapshot_id == latest_snap.id,
                StatementStats.statement_id == st.id,
            )
        ).first()
        if s_row:
            dim_labels = {d[0]: d[1] for d in get_dimensions_for_topic(topic)}
            stats_out = {
                "section": s_row.section,
                "pd": s_row.pd,
                "pd_by_dimension": s_row.pd_by_dimension or {},
                "gap": s_row.gap,
                "gap_dimension": s_row.gap_dimension,
                "gap_dimension_label": dim_labels.get(s_row.gap_dimension or "", None),
                "q_value": s_row.q_value,
                "gic": s_row.gic,
            }

    by_pos = compute_by_position(topic, st.id, latest_votes)
    stories = build_story_cards(db, topic, st.id, user.id if user else None, latest_votes)

    return {
        **_statement_brief(db, st, user),
        "status": st.status,
        "my_vote": my_v,
        "counts": {"agree": ag, "disagree": dis, "pass": pas},
        "stats": stats_out,
        "by_position": by_pos,
        "stories": stories,
    }


@app.post("/api/statements/{statement_id}/vote")
def api_vote_statement(
    statement_id: int,
    req: VoteReq,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if req.value not in (1, -1, 0):
        raise HTTPException(status_code=422, detail="value は 1, -1, 0 のいずれかである必要があります")
    st = db.get(Statement, statement_id)
    if not st or st.status != "active":
        raise HTTPException(status_code=404, detail="投票対象の原則が見つかりません")
    topic = db.get(Topic, st.topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")

    snap = get_user_position_snapshot(db, user.id, topic.id)
    ev = VoteEvent(
        user_id=user.id,
        statement_id=st.id,
        topic_id=topic.id,
        value=req.value,
        position_snapshot=snap,
    )
    db.add(ev)
    db.commit()

    latest_votes = get_latest_votes(db, topic.id)
    ag = sum(1 for (_, s), v in latest_votes.items() if s == st.id and v.value == 1)
    dis = sum(1 for (_, s), v in latest_votes.items() if s == st.id and v.value == -1)
    pas = sum(1 for (_, s), v in latest_votes.items() if s == st.id and v.value == 0)
    by_pos = compute_by_position(topic, st.id, latest_votes)

    return {
        "my_vote": req.value,
        "counts": {"agree": ag, "disagree": dis, "pass": pas},
        "by_position": by_pos,
    }


@app.post("/api/statements/{statement_id}/bridges")
def api_generate_bridges(
    statement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    st = db.get(Statement, statement_id)
    if not st:
        raise HTTPException(status_code=404, detail="原則が見つかりません")
    topic = db.get(Topic, st.topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")

    latest_votes = get_latest_votes(db, topic.id)
    cards = build_story_cards(db, topic, st.id, user.id, latest_votes)
    sup = [(c["id"], c["summary"]) for c in cards["supports"]]
    opp = [(c["id"], c["summary"]) for c in cards["opposes"]]
    bnd = [(c["id"], c["summary"]) for c in (cards["supports"] + cards["opposes"]) if c["is_boundary"]]

    res = generate_bridges(st.body, sup, opp, bnd)
    existing_bodies = {
        s.body
        for s in db.scalars(select(Statement).where(Statement.topic_id == topic.id)).all()
    }
    created_out = []
    for bp in res["bridge_principles"]:
        txt = bp["text"].strip()
        if txt in existing_bodies:
            continue
        new_st = Statement(
            topic_id=topic.id,
            author_id=user.id,
            body=txt[:200],
            origin="ai_bridge",
            status="active",
        )
        db.add(new_st)
        db.flush()
        created_out.append(_statement_brief(db, new_st, user))
        existing_bodies.add(txt)

    db.commit()
    msg = (
        f"{len(created_out)}件の条件付き合意案を投票リストに追加しました。成果物に載るかどうかは今後の投票で決まります。"
        if created_out
        else "すでに同内容の条件付き合意案が作成されています。"
    )
    return {
        "concerns": res["concerns"],
        "created": created_out,
        "ai": res["ai"],
        "message": msg,
    }


# ---------- 原体験 ----------
@app.post("/api/stories/anonymize")
def api_anonymize_story(req: AnonymizeReq):
    return anonymize_story(req.body)


@app.post("/api/statements/{statement_id}/stories")
def api_post_story(
    statement_id: int,
    req: PostStoryReq,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    st = db.get(Statement, statement_id)
    if not st:
        raise HTTPException(status_code=404, detail="原則が見つかりません")
    topic = db.get(Topic, st.topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")

    mod_err = check_moderation(req.body)
    if mod_err:
        raise HTTPException(status_code=422, detail=mod_err)

    anon = anonymize_story(req.body)
    summary = (req.summary or anon["summary"])[:200]
    snap = get_user_position_snapshot(db, user.id, topic.id)

    story_obj = Story(
        author_id=user.id,
        topic_id=topic.id,
        kind=req.kind if req.kind in ("past", "present", "future") else "past",
        body=req.body.strip(),
        summary=summary,
        anonymization="ai_masked_user_approved",
        position_snapshot=snap,
    )
    db.add(story_obj)
    db.flush()
    stance = req.stance if req.stance in ("supports", "opposes", "context") else "supports"
    db.add(StoryStatementLink(story_id=story_obj.id, statement_id=st.id, stance=stance))
    db.commit()

    cards = build_story_cards(db, topic, st.id, user.id)
    for c in cards.get(stance, []):
        if c["id"] == story_obj.id:
            return c
    raise HTTPException(status_code=500, detail="体験談の取得に失敗しました")


@app.post("/api/stories/{story_id}/reactions")
def api_react_story(
    story_id: int,
    req: ReactionReq,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if req.kind not in ("resonate", "understand"):
        raise HTTPException(status_code=422, detail="kind は resonate または understand です")
    st_obj = db.get(Story, story_id)
    if not st_obj:
        raise HTTPException(status_code=404, detail="体験談が見つかりません")

    existing = db.scalars(
        select(StoryReaction).where(
            StoryReaction.user_id == user.id,
            StoryReaction.story_id == story_id,
            StoryReaction.kind == req.kind,
        )
    ).first()
    if existing:
        db.delete(existing)
    else:
        snap = get_user_position_snapshot(db, user.id, st_obj.topic_id)
        db.add(
            StoryReaction(
                user_id=user.id,
                story_id=story_id,
                kind=req.kind,
                position_snapshot=snap,
            )
        )
    db.commit()

    r_list = db.scalars(select(StoryReaction).where(StoryReaction.story_id == story_id)).all()
    n_resonate = sum(1 for r in r_list if r.kind == "resonate")
    n_understand = sum(1 for r in r_list if r.kind == "understand")
    my_reacs = [r.kind for r in r_list if r.user_id == user.id]
    return {
        "reactions": {"resonate": n_resonate, "understand": n_understand},
        "my_reactions": my_reacs,
    }


# ---------- 分析結果 ----------
@app.get("/api/topics/{topic_id}/map")
def api_get_map(
    topic_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")
    return get_map_data(db, topic, user.id if user else None)


@app.get("/api/topics/{topic_id}/diagnosis")
def api_get_diagnosis(
    topic_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")
    return get_diagnosis_data(db, topic, user.id if user else None)


def _serialize_report(db: Session, rep: ReportVersion) -> dict[str, Any]:
    snap = db.get(AnalysisSnapshot, rep.snapshot_id)
    n_participants = db.scalar(
        select(func.count(func.distinct(VoteEvent.user_id))).where(VoteEvent.topic_id == rep.topic_id)
    ) or 0
    return {
        "version": rep.version,
        "created_at": rep.created_at.isoformat(),
        "generator": rep.generator,
        "body_md": rep.body_md,
        "sections": rep.sections,
        "params": snap.params if snap else {},
        "n_participants": int(n_participants),
    }


@app.get("/api/topics/{topic_id}/reports")
def api_list_reports(topic_id: int, db: Session = Depends(get_db)):
    reps = db.scalars(
        select(ReportVersion)
        .where(ReportVersion.topic_id == topic_id)
        .order_by(ReportVersion.id.desc())
    ).all()
    return [
        {"version": r.version, "created_at": r.created_at.isoformat(), "generator": r.generator}
        for r in reps
    ]


@app.get("/api/topics/{topic_id}/report")
def api_get_latest_report(topic_id: int, db: Session = Depends(get_db)):
    rep = db.scalars(
        select(ReportVersion)
        .where(ReportVersion.topic_id == topic_id)
        .order_by(ReportVersion.id.desc())
    ).first()
    if not rep:
        raise HTTPException(status_code=404, detail="まだ成果物が生成されていません")
    return _serialize_report(db, rep)


@app.get("/api/topics/{topic_id}/reports/{version}")
def api_get_report_version(topic_id: int, version: str, db: Session = Depends(get_db)):
    rep = db.scalars(
        select(ReportVersion).where(
            ReportVersion.topic_id == topic_id, ReportVersion.version == version
        )
    ).first()
    if not rep:
        raise HTTPException(status_code=404, detail="指定されたバージョンの成果物が見つかりません")
    return _serialize_report(db, rep)


# ---------- データエクスポート（投票結果・集計・原体験 CSV） ----------
SECTION_JA_MAP = {
    "consensus": "立場を越えた共通原則",
    "divergence": "立場によって見え方が違う論点",
    "bridge": "条件付き合意案（架け橋）",
    "value_split": "価値観による分岐",
    "undecided": "集計中",
}


@app.get("/api/topics/{topic_id}/export/votes.csv")
def api_export_votes_csv(topic_id: int, db: Session = Depends(get_db)):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")

    statements = db.scalars(
        select(Statement)
        .where(Statement.topic_id == topic_id, Statement.status == "active")
        .order_by(Statement.id.asc())
    ).all()

    latest_votes = get_latest_votes(db, topic_id)
    latest_snap = db.scalars(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.topic_id == topic_id)
        .order_by(AnalysisSnapshot.id.desc())
    ).first()

    stats_by_sid: dict[int, StatementStats] = {}
    if latest_snap:
        stats_by_sid = {
            s.statement_id: s
            for s in db.scalars(
                select(StatementStats).where(StatementStats.snapshot_id == latest_snap.id)
            ).all()
        }

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "論点ID",
        "論点本文",
        "賛成数",
        "反対数",
        "パス数",
        "有効投票数(賛否計)",
        "全体賛成率(%)",
        "合意分類",
        "立場間ギャップ",
        "原体験数",
        "立場別の賛成率内訳",
    ])

    for st in statements:
        sid = st.id
        ag = sum(1 for (_, s), ev in latest_votes.items() if s == sid and ev.value == 1)
        dis = sum(1 for (_, s), ev in latest_votes.items() if s == sid and ev.value == -1)
        pas = sum(1 for (_, s), ev in latest_votes.items() if s == sid and ev.value == 0)
        valid_n = ag + dis
        agree_pct = round((ag / valid_n) * 100, 1) if valid_n > 0 else 0.0

        st_stat = stats_by_sid.get(sid)
        sec = SECTION_JA_MAP.get(st_stat.section if st_stat else "", "未集計")
        gap_val = f"{st_stat.gap:.2f}" if (st_stat and st_stat.gap is not None) else "-"

        n_stories = db.scalar(
            select(func.count(StoryStatementLink.id)).where(StoryStatementLink.statement_id == sid)
        ) or 0

        pos_rates = compute_by_position(topic, sid, latest_votes)
        pos_summary = " / ".join(
            f"{pr['group_label']}: {int(pr['agree_rate']*100)}%(n={pr['n']})"
            for pr in pos_rates
            if not pr.get("hidden") and pr.get("agree_rate") is not None
        )

        writer.writerow([
            sid,
            st.body,
            ag,
            dis,
            pas,
            valid_n,
            agree_pct,
            sec,
            gap_val,
            n_stories,
            pos_summary,
        ])

    csv_data = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="topic_{topic_id}_votes_summary.csv"',
        },
    )


@app.get("/api/topics/{topic_id}/export/stories.csv")
def api_export_stories_csv(topic_id: int, db: Session = Depends(get_db)):
    topic = db.get(Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="トピックが見つかりません")

    stories = db.scalars(
        select(Story).where(Story.topic_id == topic_id).order_by(Story.id.asc())
    ).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "原体験ID",
        "関連論点ID",
        "関連論点本文",
        "投稿者の立場",
        "時間軸",
        "スタンス",
        "要約",
        "原体験本文",
        "共感数",
        "理解数",
        "投稿日時",
    ])

    KIND_JA = {"past": "過去の経験", "present": "現在の現状", "future": "未来の懸念・希望"}
    STANCE_JA = {"supports": "賛成理由", "opposes": "反対理由", "context": "背景・文脈"}

    for st in stories:
        link = db.scalars(select(StoryStatementLink).where(StoryStatementLink.story_id == st.id)).first()
        stmt_body = ""
        sid = ""
        stance = ""
        if link:
            sid = link.statement_id
            stmt = db.get(Statement, link.statement_id)
            if stmt:
                stmt_body = stmt.body
            stance = STANCE_JA.get(link.stance, link.stance)

        pos_label = st.position_snapshot.get("main_position") or ""
        if not pos_label:
            for k, v in st.position_snapshot.items():
                if k.startswith("axis:"):
                    pos_label = str(v)
                    break
        if not pos_label:
            pos_label = "未設定"

        res_cnt = db.scalar(
            select(func.count(StoryReaction.id)).where(StoryReaction.story_id == st.id, StoryReaction.kind == "resonate")
        ) or 0
        und_cnt = db.scalar(
            select(func.count(StoryReaction.id)).where(StoryReaction.story_id == st.id, StoryReaction.kind == "understand")
        ) or 0

        writer.writerow([
            st.id,
            sid,
            stmt_body,
            pos_label,
            KIND_JA.get(st.kind, st.kind),
            stance,
            st.summary,
            st.body,
            res_cnt,
            und_cnt,
            st.created_at.strftime("%Y-%m-%d %H:%M:%S") if st.created_at else "",
        ])

    csv_data = output.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="topic_{topic_id}_stories.csv"',
        },
    )


# ---------- 静的ファイル配信（フロントエンドSPA対応） ----------
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if not _frontend_dist.exists():
    # Dockerコンテナ環境等での相対パス対応
    _alt_dist = Path("/app/frontend/dist")
    if _alt_dist.exists():
        _frontend_dist = _alt_dist

if _frontend_dist.exists():
    _assets_dir = _frontend_dist / "assets"
    if _assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # APIルートは除外
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        file_path = _frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        index_file = _frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend build not found")


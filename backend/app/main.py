"""成果型SNS の API。

参加者の流れ：議題に答える → 議題の結果（自分の位置・反対側の理由と体験談）→ 複数議題で価値観マップ。
行動はすべて events に記録し、管理画面で漏斗として見る。
"""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from datetime import timezone
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .db import SessionLocal, get_db, init_db
from .logic import completed_topic_ids, topic_results, value_map, visible_statements
from .metrics import CLIENT_EVENTS, compute_metrics
from .models import Event, Flag, Statement, Story, Topic, Understanding, User, Vote, now
from .seed import ensure_seeded
from .values import AXES, AXIS_KEYS, MAP_COMPLETE_TOPICS

# 通報がこの数に達したら自動で非表示にする
FLAG_HIDE_THRESHOLD = 3
AGE_BANDS = ("〜18歳", "19〜22歳", "23〜29歳", "30代", "40代以上")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        ensure_seeded(db)
    yield


app = FastAPI(title="成果型SNS", lifespan=lifespan)


# ---------- 認証（端末に保存したトークン） ----------

def _token(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:].strip() or None
    return None


def optional_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> User | None:
    tok = _token(authorization)
    return db.scalars(select(User).where(User.token == tok)).first() if tok else None


def require_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(401, "参加者として登録されていません")
    return user


def require_admin(x_admin_key: str | None = Header(None)) -> None:
    key = os.environ.get("ADMIN_KEY")
    if not key:
        raise HTTPException(503, "管理画面は無効です（ADMIN_KEY が未設定）")
    if not x_admin_key or not secrets.compare_digest(x_admin_key, key):
        raise HTTPException(403, "合言葉が違います")


def log(db: Session, user: User | None, name: str, topic_id: int | None = None,
        statement_id: int | None = None, value: int | None = None) -> None:
    db.add(Event(user_id=user.id if user else None, name=name, topic_id=topic_id,
                 statement_id=statement_id, value=value))


# ---------- 入力 ----------

def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = " ".join(v.split())
    return v or None


class AxisRef(BaseModel):
    axis_key: str | None = None
    direction: Literal[1, -1] | None = None

    @field_validator("axis_key")
    @classmethod
    def _axis(cls, v):
        if v is not None and v not in AXIS_KEYS:
            raise ValueError("不明な価値観の軸です")
        return v


class NewStatement(AxisRef):
    body: str = Field(min_length=5, max_length=100)

    @field_validator("body")
    @classmethod
    def _body(cls, v):
        v = _clean(v)
        if not v or len(v) < 5:
            raise ValueError("論点は5文字以上で書いてください")
        return v


class CreateTopicReq(BaseModel):
    title: str = Field(min_length=3, max_length=60)
    description: str = Field("", max_length=300)
    statements: list[NewStatement] = Field(min_length=3, max_length=10)

    @field_validator("title")
    @classmethod
    def _title(cls, v):
        v = _clean(v)
        if not v or len(v) < 3:
            raise ValueError("タイトルは3文字以上で書いてください")
        return v


class VoteReq(BaseModel):
    value: Literal[1, 0, -1]
    reason: str | None = Field(None, max_length=80)


class StoryReq(BaseModel):
    body: str = Field(min_length=10, max_length=400)


class ProfileReq(BaseModel):
    age_band: str | None = None
    is_student: bool | None = None

    @field_validator("age_band")
    @classmethod
    def _age(cls, v):
        if v is not None and v not in AGE_BANDS:
            raise ValueError("不明な年齢層です")
        return v


class UnderstandingReq(BaseModel):
    score: int = Field(ge=1, le=5)


class EventReq(BaseModel):
    name: str
    topic_id: int | None = None
    statement_id: int | None = None


class FlagReq(BaseModel):
    target_type: Literal["topic", "statement", "reason", "story"]
    target_id: int


class ModerateReq(FlagReq):
    action: Literal["hide", "show", "delete"]


class AxisPatchReq(AxisRef):
    pass


# ---------- 参加者 ----------

def _me(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "age_band": user.age_band,
        "is_student": user.is_student,
        "profile_asked": user.profile_asked,
        "completed_topics": len(completed_topic_ids(db, user.id)),
        "map_required": MAP_COMPLETE_TOPICS,
    }


@app.get("/api/meta")
def api_meta():
    return {"axes": AXES, "age_bands": AGE_BANDS, "map_required": MAP_COMPLETE_TOPICS,
            "flag_hide_threshold": FLAG_HIDE_THRESHOLD}


@app.post("/api/users")
def api_create_user(db: Session = Depends(get_db)):
    user = User(token=secrets.token_urlsafe(32))
    db.add(user)
    db.commit()
    return {"token": user.token, "me": _me(db, user)}


@app.get("/api/me")
def api_get_me(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return _me(db, user)


@app.patch("/api/me")
def api_patch_me(req: ProfileReq, user: User = Depends(require_user), db: Session = Depends(get_db)):
    user.age_band = req.age_band
    user.is_student = req.is_student
    user.profile_asked = True
    db.commit()
    return _me(db, user)


@app.post("/api/events")
def api_event(req: EventReq, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    if req.name not in CLIENT_EVENTS:
        raise HTTPException(400, "記録できないイベントです")
    log(db, user, req.name, req.topic_id, req.statement_id)
    db.commit()
    return {"ok": True}


# ---------- 議題 ----------

def _get_topic(db: Session, topic_id: int) -> Topic:
    t = db.get(Topic, topic_id)
    if t is None or t.hidden:
        raise HTTPException(404, "議題が見つかりません")
    return t


@app.get("/api/topics")
def api_list_topics(user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    topics = list(db.scalars(select(Topic).where(Topic.hidden.is_(False)).order_by(Topic.origin.desc(), Topic.id)))
    counts = dict(db.execute(
        select(Statement.topic_id, func.count()).where(Statement.hidden.is_(False)).group_by(Statement.topic_id)
    ).all())
    participants = dict(db.execute(
        select(Vote.topic_id, func.count(func.distinct(Vote.user_id))).group_by(Vote.topic_id)
    ).all())
    mine: dict[int, int] = {}
    done: set[int] = set()
    if user:
        mine = dict(db.execute(
            select(Vote.topic_id, func.count()).join(Statement, Statement.id == Vote.statement_id)
            .where(Vote.user_id == user.id, Statement.hidden.is_(False)).group_by(Vote.topic_id)
        ).all())
        done = completed_topic_ids(db, user.id)
    return [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "origin": t.origin,
            "n_statements": counts.get(t.id, 0),
            "n_participants": participants.get(t.id, 0),
            "my_answered": mine.get(t.id, 0),
            "completed": t.id in done,
        }
        for t in topics
    ]


@app.post("/api/topics")
def api_create_topic(req: CreateTopicReq, user: User = Depends(require_user), db: Session = Depends(get_db)):
    topic = Topic(title=req.title, description=_clean(req.description) or "", author_id=user.id, origin="user")
    db.add(topic)
    db.flush()
    for s in req.statements:
        db.add(Statement(topic_id=topic.id, body=s.body, author_id=user.id, origin="user",
                         axis_key=s.axis_key, direction=s.direction if s.axis_key else None))
    log(db, user, "topic_created", topic.id)
    db.commit()
    return {"id": topic.id}


@app.get("/api/topics/{topic_id}")
def api_get_topic(topic_id: int, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    t = _get_topic(db, topic_id)
    stmts = visible_statements(db, t.id)
    my_votes = {}
    if user:
        for v in db.scalars(select(Vote).where(Vote.user_id == user.id, Vote.topic_id == t.id)):
            my_votes[v.statement_id] = {"value": v.value, "reason": v.reason}
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "origin": t.origin,
        "statements": [
            {"id": s.id, "body": s.body, "origin": s.origin, "axis_key": s.axis_key} for s in stmts
        ],
        "my_votes": my_votes,
        "completed": bool(user and t.id in completed_topic_ids(db, user.id)),
    }


@app.post("/api/topics/{topic_id}/statements")
def api_add_statement(topic_id: int, req: NewStatement, user: User = Depends(require_user),
                      db: Session = Depends(get_db)):
    t = _get_topic(db, topic_id)
    if db.scalars(select(Statement.id).where(Statement.topic_id == t.id, Statement.body == req.body)).first():
        raise HTTPException(409, "同じ論点がすでにあります")
    s = Statement(topic_id=t.id, body=req.body, author_id=user.id, origin="user",
                  axis_key=req.axis_key, direction=req.direction if req.axis_key else None)
    db.add(s)
    db.flush()
    log(db, user, "statement_added", t.id, s.id)
    db.commit()
    return {"id": s.id, "body": s.body, "origin": s.origin, "axis_key": s.axis_key}


@app.get("/api/topics/{topic_id}/results")
def api_results(topic_id: int, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    t = _get_topic(db, topic_id)
    res = topic_results(db, t, user)
    my_score = None
    if user:
        u = db.scalars(select(Understanding).where(Understanding.user_id == user.id,
                                                   Understanding.topic_id == t.id)).first()
        my_score = u.score if u else None
    return {"topic": {"id": t.id, "title": t.title, "description": t.description},
            **res, "my_understanding": my_score}


@app.post("/api/topics/{topic_id}/understanding")
def api_understanding(topic_id: int, req: UnderstandingReq, user: User = Depends(require_user),
                      db: Session = Depends(get_db)):
    t = _get_topic(db, topic_id)
    u = db.scalars(select(Understanding).where(Understanding.user_id == user.id,
                                               Understanding.topic_id == t.id)).first()
    if u:
        u.score = req.score
    else:
        db.add(Understanding(user_id=user.id, topic_id=t.id, score=req.score))
    log(db, user, "understanding", t.id, value=req.score)
    db.commit()
    return {"score": req.score}


# ---------- 投票・体験談 ----------

def _get_statement(db: Session, statement_id: int) -> Statement:
    s = db.get(Statement, statement_id)
    if s is None or s.hidden:
        raise HTTPException(404, "論点が見つかりません")
    _get_topic(db, s.topic_id)
    return s


@app.post("/api/statements/{statement_id}/vote")
def api_vote(statement_id: int, req: VoteReq, user: User = Depends(require_user), db: Session = Depends(get_db)):
    s = _get_statement(db, statement_id)
    reason = _clean(req.reason) if req.value != 0 else None
    is_first_ever = db.scalars(select(Vote.id).where(Vote.user_id == user.id)).first() is None
    is_first_in_topic = db.scalars(
        select(Vote.id).where(Vote.user_id == user.id, Vote.topic_id == s.topic_id)
    ).first() is None

    v = db.scalars(select(Vote).where(Vote.user_id == user.id, Vote.statement_id == s.id)).first()
    if v:
        v.value = req.value
        v.reason = reason
        v.updated_at = now()
    else:
        db.add(Vote(user_id=user.id, statement_id=s.id, topic_id=s.topic_id, value=req.value, reason=reason))
    log(db, user, "vote", s.topic_id, s.id, req.value)
    if is_first_ever:
        log(db, user, "first_vote", s.topic_id, s.id)
    if is_first_in_topic:
        log(db, user, "topic_first_vote", s.topic_id, s.id)
    if reason:
        log(db, user, "reason_written", s.topic_id, s.id)
    db.flush()

    done_before = completed_topic_ids(db, user.id)
    completed_now = False
    if s.topic_id not in done_before:
        visible_ids = {x.id for x in visible_statements(db, s.topic_id)}
        voted_ids = set(db.scalars(select(Vote.statement_id).where(Vote.user_id == user.id,
                                                                   Vote.topic_id == s.topic_id)))
        if visible_ids <= voted_ids:
            completed_now = True
            log(db, user, "topic_complete", s.topic_id)
            if len(done_before) + 1 == MAP_COMPLETE_TOPICS:
                log(db, user, "map_complete")
    db.commit()
    n_done = len(done_before) + (1 if completed_now else 0)
    return {
        "value": req.value,
        "reason": reason,
        "topic_completed_now": completed_now,
        "completed_topics": n_done,
        "map_completed_now": completed_now and n_done == MAP_COMPLETE_TOPICS,
    }


@app.post("/api/statements/{statement_id}/stories")
def api_post_story(statement_id: int, req: StoryReq, user: User = Depends(require_user),
                   db: Session = Depends(get_db)):
    s = _get_statement(db, statement_id)
    body = _clean(req.body)
    if not body or len(body) < 10:
        raise HTTPException(422, "体験談は10文字以上で書いてください")
    v = db.scalars(select(Vote).where(Vote.user_id == user.id, Vote.statement_id == s.id)).first()
    st = Story(statement_id=s.id, user_id=user.id, body=body, stance=v.value if v else 0)
    db.add(st)
    db.flush()
    log(db, user, "story_written", s.topic_id, s.id)
    db.commit()
    return {"id": st.id, "body": st.body, "stance": st.stance}


# ---------- 通報 ----------

def _flag_target(db: Session, target_type: str, target_id: int):
    model = {"topic": Topic, "statement": Statement, "reason": Vote, "story": Story}[target_type]
    obj = db.get(model, target_id)
    if obj is None:
        raise HTTPException(404, "対象が見つかりません")
    return obj


def _set_hidden(obj, target_type: str, hidden: bool) -> None:
    if target_type == "reason":
        obj.reason_hidden = hidden
    else:
        obj.hidden = hidden


@app.post("/api/flags")
def api_flag(req: FlagReq, user: User = Depends(require_user), db: Session = Depends(get_db)):
    obj = _flag_target(db, req.target_type, req.target_id)
    exists = db.scalars(select(Flag).where(Flag.user_id == user.id, Flag.target_type == req.target_type,
                                           Flag.target_id == req.target_id)).first()
    if not exists:
        db.add(Flag(user_id=user.id, target_type=req.target_type, target_id=req.target_id))
        db.add(Event(user_id=user.id, name="flag"))
        db.flush()
    n = db.scalar(select(func.count()).select_from(Flag).where(
        Flag.target_type == req.target_type, Flag.target_id == req.target_id)) or 0
    hidden = n >= FLAG_HIDE_THRESHOLD
    if hidden:
        _set_hidden(obj, req.target_type, True)
    db.commit()
    return {"flagged": True, "hidden": hidden}


# ---------- 価値観マップ ----------

@app.get("/api/me/map")
def api_map(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return value_map(db, user)


# ---------- 管理 ----------

def _target_text(db: Session, target_type: str, obj) -> tuple[str, bool]:
    if target_type == "topic":
        return obj.title, obj.hidden
    if target_type == "statement":
        return obj.body, obj.hidden
    if target_type == "reason":
        return obj.reason or "（削除済み）", obj.reason_hidden
    return obj.body, obj.hidden


@app.get("/api/admin/metrics", dependencies=[Depends(require_admin)])
def api_admin_metrics(db: Session = Depends(get_db)):
    return compute_metrics(db)


@app.get("/api/admin/flags", dependencies=[Depends(require_admin)])
def api_admin_flags(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Flag.target_type, Flag.target_id, func.count(), func.max(Flag.created_at))
        .group_by(Flag.target_type, Flag.target_id).order_by(func.max(Flag.created_at).desc())
    ).all()
    out = []
    for target_type, target_id, n, last in rows:
        model = {"topic": Topic, "statement": Statement, "reason": Vote, "story": Story}[target_type]
        obj = db.get(model, target_id)
        if obj is None:
            continue
        text, hidden = _target_text(db, target_type, obj)
        out.append({"target_type": target_type, "target_id": target_id, "count": n, "text": text,
                    "hidden": hidden, "last_at": last.replace(tzinfo=last.tzinfo or timezone.utc).isoformat()})
    return out


@app.post("/api/admin/moderate", dependencies=[Depends(require_admin)])
def api_admin_moderate(req: ModerateReq, db: Session = Depends(get_db)):
    obj = _flag_target(db, req.target_type, req.target_id)
    if req.action == "delete":
        if req.target_type == "story":
            db.delete(obj)
        elif req.target_type == "reason":
            obj.reason = None
        else:
            raise HTTPException(400, "議題と論点は非表示にだけできます（票が消えるため）")
        db.execute(delete(Flag).where(Flag.target_type == req.target_type, Flag.target_id == req.target_id))
    else:
        _set_hidden(obj, req.target_type, req.action == "hide")
        if req.action == "show":
            db.execute(delete(Flag).where(Flag.target_type == req.target_type, Flag.target_id == req.target_id))
    db.commit()
    return {"ok": True}


@app.get("/api/admin/statements", dependencies=[Depends(require_admin)])
def api_admin_statements(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Statement, Topic.title).join(Topic, Topic.id == Statement.topic_id).order_by(Topic.id, Statement.id)
    ).all()
    return [
        {"id": s.id, "topic_id": s.topic_id, "topic_title": title, "body": s.body, "origin": s.origin,
         "axis_key": s.axis_key, "direction": s.direction, "hidden": s.hidden}
        for s, title in rows
    ]


@app.patch("/api/admin/statements/{statement_id}", dependencies=[Depends(require_admin)])
def api_admin_patch_statement(statement_id: int, req: AxisPatchReq, db: Session = Depends(get_db)):
    s = db.get(Statement, statement_id)
    if s is None:
        raise HTTPException(404, "論点が見つかりません")
    if req.axis_key and req.direction is None:
        raise HTTPException(422, "軸を付けるときは向きも選んでください")
    s.axis_key = req.axis_key
    s.direction = req.direction if req.axis_key else None
    db.commit()
    return {"id": s.id, "axis_key": s.axis_key, "direction": s.direction}


# ---------- 画面（ビルド済みのフロントエンド） ----------

_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if _frontend_dist.exists():

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not Found")
        # ".." で dist の外（DB や設定ファイル）を読ませない
        file_path = (_frontend_dist / full_path).resolve()
        if full_path and file_path.is_relative_to(_frontend_dist.resolve()) and file_path.is_file():
            return FileResponse(file_path)
        # デプロイ後に古い index.html（古い JS を指す）が残らないよう毎回確認させる
        return FileResponse(_frontend_dist / "index.html", headers={"Cache-Control": "no-cache"})

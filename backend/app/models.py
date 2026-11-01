"""テーブル定義。

参加者は端末に保存したトークンだけで識別する（ログインなし）。
価値観の軸そのものはコード（values.py）に置き、論点には軸のキーと向きだけを持たせる。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # 任意の属性。未回答は None
    age_band: Mapped[str | None] = mapped_column(String(16))
    is_student: Mapped[bool | None] = mapped_column()
    profile_asked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    origin: Mapped[str] = mapped_column(String(8), default="user")  # seed | user
    hidden: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Statement(Base):
    __tablename__ = "statements"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    body: Mapped[str] = mapped_column(String(140))
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    origin: Mapped[str] = mapped_column(String(8), default="user")
    # 賛成したときに軸のどちら側へ寄るか：+1 なら右側、-1 なら左側。軸が無ければマップに使わない
    axis_key: Mapped[str | None] = mapped_column(String(16))
    direction: Mapped[int | None] = mapped_column(Integer)
    hidden: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("user_id", "statement_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("statements.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    value: Mapped[int] = mapped_column(Integer)  # 1 賛成 / -1 反対 / 0 わからない
    reason: Mapped[str | None] = mapped_column(String(80))
    reason_hidden: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Story(Base):
    __tablename__ = "stories"
    id: Mapped[int] = mapped_column(primary_key=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("statements.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(String(400))
    stance: Mapped[int] = mapped_column(Integer)  # 投稿時点の本人の答え
    hidden: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Flag(Base):
    """通報。target_type は topic / statement / reason（=Vote）/ story。"""

    __tablename__ = "flags"
    __table_args__ = (UniqueConstraint("user_id", "target_type", "target_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    target_type: Mapped[str] = mapped_column(String(12))
    target_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Understanding(Base):
    """議題の最後の1問「反対側の考えが前より理解できた」（1〜5）。"""

    __tablename__ = "understandings"
    __table_args__ = (UniqueConstraint("user_id", "topic_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    score: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Event(Base):
    """行動計測。漏斗・離脱・再訪はすべてここから集計する。"""

    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(32), index=True)
    topic_id: Mapped[int | None] = mapped_column(Integer)
    statement_id: Mapped[int | None] = mapped_column(Integer)
    value: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

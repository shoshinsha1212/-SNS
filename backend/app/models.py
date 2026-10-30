"""ORMモデル。docs/01_データモデル.md に対応（MVPのため ID は整数）。"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    handle: Mapped[str] = mapped_column(String(50))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    trust_level: Mapped[int] = mapped_column(Integer, default=1)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    attributes: Mapped[list["UserAttribute"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserAttribute(Base):
    __tablename__ = "user_attributes"
    __table_args__ = (UniqueConstraint("user_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    key: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(String(100))
    verification: Mapped[str] = mapped_column(String(20), default="self")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user: Mapped[User] = relationship(back_populates="attributes")


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    axes: Mapped[list["PositionAxis"]] = relationship(
        back_populates="topic", order_by="PositionAxis.order", cascade="all, delete-orphan"
    )


class PositionAxis(Base):
    __tablename__ = "position_axes"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(20), default="admin")
    order: Mapped[int] = mapped_column(Integer, default=0)
    topic: Mapped[Topic] = relationship(back_populates="axes")
    options: Mapped[list["PositionOption"]] = relationship(
        back_populates="axis", order_by="PositionOption.id", cascade="all, delete-orphan"
    )


class PositionOption(Base):
    __tablename__ = "position_options"
    id: Mapped[int] = mapped_column(primary_key=True)
    axis_id: Mapped[int] = mapped_column(ForeignKey("position_axes.id"), index=True)
    label: Mapped[str] = mapped_column(String(100))
    axis: Mapped[PositionAxis] = relationship(back_populates="options")


class UserTopicPosition(Base):
    """立場の履歴。valid_to が NULL のものが現在の立場。"""

    __tablename__ = "user_topic_positions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    axis_id: Mapped[int] = mapped_column(ForeignKey("position_axes.id"))
    option_id: Mapped[int] = mapped_column(ForeignKey("position_options.id"))
    valid_from: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Statement(Base):
    __tablename__ = "statements"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    body: Mapped[str] = mapped_column(String(200))
    origin: Mapped[str] = mapped_column(String(30), default="user")
    status: Mapped[str] = mapped_column(String(20), default="active")
    merged_into: Mapped[int | None] = mapped_column(ForeignKey("statements.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VoteEvent(Base):
    """投票は上書きせずイベントとして保存。ユーザー×原則の最新が現在の票。"""

    __tablename__ = "vote_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("statements.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    value: Mapped[int] = mapped_column(Integer)
    position_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Story(Base):
    __tablename__ = "stories"
    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="past")
    body: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(String(200), default="")
    anonymization: Mapped[str] = mapped_column(String(30), default="none")
    position_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StoryStatementLink(Base):
    __tablename__ = "story_statement_links"
    __table_args__ = (UniqueConstraint("story_id", "statement_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("statements.id"), index=True)
    stance: Mapped[str] = mapped_column(String(10), default="supports")


class StoryReaction(Base):
    __tablename__ = "story_reactions"
    __table_args__ = (UniqueConstraint("user_id", "story_id", "kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    position_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AnalysisSnapshot(Base):
    __tablename__ = "analysis_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_vote_event_id: Mapped[int] = mapped_column(Integer, default=0)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    # クラスターの中心・代表原則・トピック全体の立場依存度などの付随情報
    meta: Mapped[dict] = mapped_column(JSON, default=dict)


class StatementStats(Base):
    __tablename__ = "statement_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("analysis_snapshots.id"), index=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("statements.id"), index=True)
    n_seen: Mapped[int] = mapped_column(Integer, default=0)
    n_agree: Mapped[int] = mapped_column(Integer, default=0)
    n_disagree: Mapped[int] = mapped_column(Integer, default=0)
    n_pass: Mapped[int] = mapped_column(Integer, default=0)
    gic: Mapped[float | None] = mapped_column(Float, nullable=True)
    pd: Mapped[float | None] = mapped_column(Float, nullable=True)
    pd_by_dimension: Mapped[dict] = mapped_column(JSON, default=dict)
    gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    gap_dimension: Mapped[str | None] = mapped_column(String(50), nullable=True)
    p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    q_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    section: Mapped[str] = mapped_column(String(20), default="undecided")


class GroupStats(Base):
    __tablename__ = "group_stats"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("analysis_snapshots.id"), index=True)
    statement_id: Mapped[int] = mapped_column(ForeignKey("statements.id"), index=True)
    group_type: Mapped[str] = mapped_column(String(10))  # cluster / position
    dimension: Mapped[str] = mapped_column(String(50))  # cluster の場合は "cluster"
    group_key: Mapped[str] = mapped_column(String(100))
    n_seen: Mapped[int] = mapped_column(Integer, default=0)
    n_agree: Mapped[int] = mapped_column(Integer, default=0)
    n_disagree: Mapped[int] = mapped_column(Integer, default=0)


class UserProjection(Base):
    __tablename__ = "user_projections"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("analysis_snapshots.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    cluster_id: Mapped[int] = mapped_column(Integer)


class ReportVersion(Base):
    __tablename__ = "report_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    version: Mapped[str] = mapped_column(String(20))
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("analysis_snapshots.id"))
    body_md: Mapped[str] = mapped_column(Text)
    generator: Mapped[str] = mapped_column(String(10), default="template")
    sections: Mapped[dict] = mapped_column(JSON, default=dict)
    diff: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReportCitation(Base):
    __tablename__ = "report_citations"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_version_id: Mapped[int] = mapped_column(ForeignKey("report_versions.id"), index=True)
    section_key: Mapped[str] = mapped_column(String(20))
    ref_type: Mapped[str] = mapped_column(String(10))
    ref_id: Mapped[int] = mapped_column(Integer)


class Contribution(Base):
    __tablename__ = "contributions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    report_version_id: Mapped[int] = mapped_column(ForeignKey("report_versions.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    ref_type: Mapped[str] = mapped_column(String(10))
    ref_id: Mapped[int] = mapped_column(Integer)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

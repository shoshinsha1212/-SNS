"""起動時の初期データ。運営が用意する議題と論点だけを入れる。参加者・票は作らない。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Statement, Topic
from .values import SEED_TOPICS


def ensure_seeded(db: Session) -> None:
    existing = set(db.scalars(select(Topic.title).where(Topic.origin == "seed")))
    for spec in SEED_TOPICS:
        if spec["title"] in existing:
            continue
        topic = Topic(title=spec["title"], description=spec["description"], origin="seed")
        db.add(topic)
        db.flush()
        for body, axis_key, direction in spec["statements"]:
            db.add(Statement(
                topic_id=topic.id, body=body, origin="seed", axis_key=axis_key, direction=direction,
            ))
    db.commit()

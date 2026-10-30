"""データベース接続。既定は SQLite（DATABASE_URL で PostgreSQL などに切り替え可能）。"""

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "seika.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{_DEFAULT_DB.as_posix()}")

_is_sqlite = DATABASE_URL.startswith("sqlite")
_is_memory = ":memory:" in DATABASE_URL
if _is_sqlite and not _is_memory:
    _DEFAULT_DB.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    poolclass=StaticPool if (_is_sqlite and _is_memory) else None,
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - 接続設定のみ
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from sqlalchemy import text
    from . import models  # noqa: F401  モデルを登録するため

    Base.metadata.create_all(engine)
    if _is_sqlite and not _is_memory:
        with engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN device_id VARCHAR(64)"))
                conn.commit()
            except Exception:
                pass

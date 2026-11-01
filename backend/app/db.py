"""データベース接続。手元は SQLite、本番は DATABASE_URL で Postgres（Neon など）に切り替える。"""

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "seika.db"


def _normalize(url: str) -> str:
    # Neon などが渡す postgres:// / postgresql:// を psycopg 3 のドライバ指定に揃える
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _normalize(os.environ.get("DATABASE_URL") or f"sqlite:///{_DEFAULT_DB.as_posix()}")

_is_sqlite = DATABASE_URL.startswith("sqlite")
_is_memory = ":memory:" in DATABASE_URL
if _is_sqlite and not _is_memory:
    _DEFAULT_DB.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    poolclass=StaticPool if (_is_sqlite and _is_memory) else None,
    pool_pre_ping=not _is_sqlite,
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # pragma: no cover - 接続設定のみ
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
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
    from . import models  # noqa: F401  モデルを登録するため

    Base.metadata.create_all(engine)


def reset_db() -> None:
    """テスト用：全テーブルを作り直す。"""
    from . import models  # noqa: F401

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

def _engine_url(url: str) -> str:
    """Accept the plain postgres:// URLs that hosts hand out and use the psycopg 3 driver for them."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _engine_url(settings.database_url)
IS_SQLITE = DATABASE_URL.startswith("sqlite")
# Behind a connection pooler (e.g. Supabase) prepared statements break; pre-ping drops dead connections.
connect_args = {"check_same_thread": False, "timeout": 30} if IS_SQLITE else {"prepare_threshold": None}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True, pool_pre_ping=not IS_SQLITE)

if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        # WAL lets parallel experts read while one writes; busy_timeout queues writers instead of failing
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.close()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

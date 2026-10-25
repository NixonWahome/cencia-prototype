"""SQLite engine, sessions and the single-writer lock."""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

engine: Engine | None = None
SessionLocal: sessionmaker[Session] | None = None

# SQLite allows one writer at a time. Every write in the process (simulator,
# verifier, API, demo injectors) goes through this lock so none of them ever
# sees "database is locked". Reads run concurrently thanks to WAL mode.
write_lock = threading.RLock()


def init_db(db_path: str, reset: bool = False) -> None:
    global engine, SessionLocal
    if engine is not None:
        engine.dispose()

    path = Path(db_path)
    if reset:
        for suffix in ("", "-wal", "-shm"):
            Path(f"{path}{suffix}").unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(engine, expire_on_commit=False)


def dispose() -> None:
    global engine
    if engine is not None:
        engine.dispose()
        engine = None


@contextmanager
def read_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def write_session() -> Iterator[Session]:
    with write_lock:
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency for read-only request handlers."""
    with read_session() as session:
        yield session

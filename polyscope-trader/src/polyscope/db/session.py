"""Database engine and session helpers."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from polyscope.config import Settings
from polyscope.db.migrate import run_migrations
from polyscope.db.models import Base, LedgerAccount, SystemState


def make_engine(db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"
    return create_engine(url, connect_args={"check_same_thread": False})


def init_db(settings: Settings) -> sessionmaker[Session]:
    engine = make_engine(settings.db_path)
    Base.metadata.create_all(engine)
    run_migrations(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with SessionLocal() as session:
        state = session.get(SystemState, 1)
        if state is None:
            state = SystemState(id=1)
            session.add(state)
        state.live_session_armed = False
        for name, balance in (
            ("available", settings.risk.starting_balance),
            ("reserved", Decimal("0")),
            ("fees", Decimal("0")),
            ("realized_pnl", Decimal("0")),
        ):
            acct = session.scalar(select(LedgerAccount).where(LedgerAccount.name == name))
            if acct is None:
                session.add(LedgerAccount(name=name, balance=balance))
            elif name == "available" and acct.balance == 0:
                acct.balance = settings.risk.starting_balance
        session.commit()
    return SessionLocal


@contextmanager
def session_scope(session_factory: sessionmaker[Session]):
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_system_state(session: Session) -> SystemState:
    state = session.get(SystemState, 1)
    if state is None:
        state = SystemState(id=1)
        session.add(state)
        session.flush()
    return state

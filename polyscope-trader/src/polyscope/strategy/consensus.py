"""Flow consensus — count cohort wallets on same outcome."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from polyscope.db.models import Signal, utcnow


def consensus_count(
    session: Session,
    condition_id: str,
    outcome: str | None,
    side: str,
    within_minutes: int = 60,
) -> int:
    since = utcnow() - timedelta(minutes=within_minutes)
    q = (
        select(func.count(func.distinct(Signal.wallet)))
        .where(Signal.condition_id == condition_id)
        .where(Signal.side == side)
        .where(Signal.observed_at >= since)
    )
    if outcome:
        q = q.where(Signal.outcome == outcome)
    return session.scalar(q) or 0

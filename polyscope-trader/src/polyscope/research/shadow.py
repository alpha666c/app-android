"""Shadow ledger for rejected signals."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from polyscope.db.models import ShadowSignal, Signal


def record_shadow_rejection(
    session: Session, signal: Signal, entry_price: Decimal
) -> None:
    existing = session.scalar(
        select(ShadowSignal).where(ShadowSignal.signal_id == signal.id)
    )
    if existing:
        return
    session.add(
        ShadowSignal(
            signal_id=signal.id,
            reject_reason=signal.reject_reason or "unknown",
            hypothetical_entry=entry_price,
        )
    )

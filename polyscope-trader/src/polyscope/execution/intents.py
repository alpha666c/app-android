"""Idempotent order intent creation."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from polyscope.config import Settings, TradingMode
from polyscope.db.models import OrderIntent, Signal


def intent_key(signal_id: int, side: str, token_id: str) -> str:
    return f"{signal_id}:{side.upper()}:{token_id}"


def get_or_create_intent(
    session: Session,
    settings: Settings,
    signal: Signal,
    *,
    limit_price: Decimal,
    size: Decimal,
    reserved_usdc: Decimal,
) -> OrderIntent:
    key = intent_key(signal.id, signal.side, signal.token_id)
    existing = session.scalar(select(OrderIntent).where(OrderIntent.intent_key == key))
    if existing:
        return existing
    mode = settings.trading_mode.value
    intent = OrderIntent(
        intent_key=key,
        signal_id=signal.id,
        mode=mode,
        side=signal.side,
        token_id=signal.token_id,
        condition_id=signal.condition_id,
        limit_price=limit_price,
        size=size,
        reserved_usdc=reserved_usdc,
        status="created",
    )
    session.add(intent)
    session.flush()
    return intent


def paper_mode_blocks_live(settings: Settings) -> bool:
    return settings.trading_mode != TradingMode.LIVE

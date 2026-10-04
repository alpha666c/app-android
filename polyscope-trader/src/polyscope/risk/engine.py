"""Deterministic pre-trade risk checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from polyscope.config import RiskLimits, Settings
from polyscope.db.models import LedgerAccount, OrderIntent, Position, SystemState, utcnow


@dataclass
class RiskDecision:
    allowed: bool
    reason: str | None = None
    daily_loss: Decimal | None = None
    total_exposure: Decimal | None = None


def _sum_positions(session: Session) -> Decimal:
    total = session.scalar(
        select(func.coalesce(func.sum(Position.cost_basis), 0))
    )
    return Decimal(str(total or 0))


def _event_exposure(session: Session, event_slug: str | None) -> Decimal:
    if not event_slug:
        return Decimal("0")
    total = session.scalar(
        select(func.coalesce(func.sum(Position.cost_basis), 0)).where(
            Position.event_slug == event_slug
        )
    )
    return Decimal(str(total or 0))


def _open_positions_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Position).where(Position.size > 0)) or 0


def _outstanding_orders(session: Session) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(OrderIntent)
            .where(OrderIntent.status.in_(("created", "submitted", "partial")))
        )
        or 0
    )


def _daily_loss(session: Session, state: SystemState, limits: RiskLimits) -> Decimal | None:
    if state.day_baseline_realized is None or state.day_baseline_unrealized is None:
        return None
    realized = session.scalar(
        select(LedgerAccount.balance).where(LedgerAccount.name == "realized_pnl")
    )
    unrealized = session.scalar(
        select(func.coalesce(func.sum(Position.unrealized_pnl), 0))
    )
    if realized is None:
        return None
    cur_r = Decimal(str(realized))
    cur_u = Decimal(str(unrealized or 0))
    loss = (state.day_baseline_realized - cur_r) + (state.day_baseline_unrealized - cur_u)
    return max(Decimal("0"), loss)


def ensure_day_boundary(session: Session, state: SystemState) -> None:
    today = utcnow().date().isoformat()
    if state.day_boundary != today:
        realized = session.scalar(
            select(LedgerAccount.balance).where(LedgerAccount.name == "realized_pnl")
        )
        unrealized = session.scalar(
            select(func.coalesce(func.sum(Position.unrealized_pnl), 0))
        )
        state.day_boundary = today
        state.day_baseline_realized = Decimal(str(realized or 0))
        state.day_baseline_unrealized = Decimal(str(unrealized or 0))


def evaluate_order(
    session: Session,
    settings: Settings,
    *,
    order_cost: Decimal,
    event_slug: str | None,
    data_age_seconds: float | None,
    spread: Decimal | None,
    signal_age_seconds: float | None,
) -> RiskDecision:
    limits = settings.risk
    state = session.get(SystemState, 1)
    if state is None:
        return RiskDecision(False, "missing_system_state")
    if state.kill_switch:
        return RiskDecision(False, "kill_switch")
    if state.data_stale:
        return RiskDecision(False, "stale_feed")
    ensure_day_boundary(session, state)

    if order_cost > limits.max_order_cost:
        return RiskDecision(False, "max_order_cost")
    total_exp = _sum_positions(session)
    if total_exp + order_cost > limits.max_total_exposure:
        return RiskDecision(False, "max_total_exposure", total_exposure=total_exp)
    event_exp = _event_exposure(session, event_slug)
    if event_exp + order_cost > limits.max_event_exposure:
        return RiskDecision(False, "max_event_exposure")
    if _open_positions_count(session) >= limits.max_open_positions:
        return RiskDecision(False, "max_open_positions")
    if _outstanding_orders(session) >= limits.max_outstanding_orders:
        return RiskDecision(False, "max_outstanding_orders")

    daily = _daily_loss(session, state, limits)
    if daily is not None and daily >= limits.daily_loss_circuit_breaker:
        return RiskDecision(False, "daily_loss_circuit_breaker", daily_loss=daily)

    if data_age_seconds is not None and data_age_seconds > limits.max_data_age_seconds:
        return RiskDecision(False, "data_too_old")
    if signal_age_seconds is not None and signal_age_seconds > limits.max_signal_age_seconds:
        return RiskDecision(False, "stale_signal")
    if spread is not None and spread > limits.max_spread:
        return RiskDecision(False, "wide_spread")

    available = session.scalar(
        select(LedgerAccount.balance).where(LedgerAccount.name == "available")
    )
    if available is None or Decimal(str(available)) < order_cost:
        return RiskDecision(False, "insufficient_balance")

    return RiskDecision(True, total_exposure=total_exp, daily_loss=daily)

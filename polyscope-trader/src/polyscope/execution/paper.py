"""Realistic paper execution against order book depth."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from polyscope.config import Settings
from polyscope.db.models import Fill, LedgerAccount, OrderIntent, Position, Signal
from polyscope.execution.fees import taker_fee_usdc
from polyscope.execution.intents import get_or_create_intent
from polyscope.platform.public_client import OrderBookSnapshot, PlatformClient
from polyscope.risk.engine import evaluate_order
from polyscope.risk.reservations import commit_spend, release_reservation, reserve_funds

logger = logging.getLogger(__name__)


def _best_prices(book: OrderBookSnapshot) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    best_bid = book.bids[0][0] if book.bids else None
    best_ask = book.asks[0][0] if book.asks else None
    if best_bid is not None and best_ask is not None:
        spread = best_ask - best_bid
    else:
        spread = None
    return best_bid, best_ask, spread


def _walk_book(
    side: str, limit_price: Decimal, size: Decimal, book: OrderBookSnapshot
) -> tuple[Decimal, Decimal, Decimal]:
    """Returns filled size, avg price, cost."""
    remaining = size
    filled = Decimal("0")
    cost = Decimal("0")
    levels = book.asks if side.upper() == "BUY" else book.bids
    for price, level_size in levels:
        if side.upper() == "BUY" and price > limit_price:
            break
        if side.upper() == "SELL" and price < limit_price:
            break
        take = min(remaining, level_size)
        if take <= 0:
            continue
        filled += take
        cost += take * price
        remaining -= take
        if remaining <= 0:
            break
    if filled == 0:
        return Decimal("0"), Decimal("0"), Decimal("0")
    avg = cost / filled
    return filled, avg, cost


async def process_approved_signals(
    session: Session, settings: Settings, platform: PlatformClient
) -> int:
    signals = session.scalars(
        select(Signal).where(Signal.status == "approved")
    ).all()
    processed = 0
    now = datetime.now(timezone.utc)
    for signal in signals:
        book = await platform.fetch_order_book(signal.token_id)
        data_age = (now - book.fetched_at).total_seconds()
        best_bid, best_ask, spread = _best_prices(book)
        if signal.side.upper() == "BUY":
            executable = best_ask
        else:
            executable = best_bid
        if executable is None:
            signal.status = "rejected"
            signal.reject_reason = "insufficient_depth"
            continue
        if abs(executable - signal.reference_price) > settings.signal_price_tolerance:
            signal.status = "rejected"
            signal.reject_reason = "price_moved"
            continue
        signal_age = (now - signal.observed_at).total_seconds()
        fee = taker_fee_usdc(signal.size, executable, category="politics")
        if fee is None:
            signal.status = "rejected"
            signal.reject_reason = "missing_fees"
            continue
        est_cost = signal.size * executable + fee
        decision = evaluate_order(
            session,
            settings,
            order_cost=est_cost,
            event_slug=signal.event_slug,
            data_age_seconds=data_age,
            spread=spread,
            signal_age_seconds=signal_age,
        )
        if not decision.allowed:
            signal.status = "rejected"
            signal.reject_reason = decision.reason
            continue

        intent = get_or_create_intent(
            session,
            settings,
            signal,
            limit_price=executable,
            size=signal.size,
            reserved_usdc=est_cost,
        )
        if intent.status not in ("created",):
            signal.status = "executed"
            continue
        try:
            reserve_funds(session, intent.id, est_cost)
        except Exception:
            signal.status = "rejected"
            signal.reject_reason = "insufficient_balance"
            continue

        filled, avg_price, cost = _walk_book(signal.side, executable, signal.size, book)
        if filled <= 0:
            release_reservation(session, intent.id, est_cost)
            signal.status = "rejected"
            signal.reject_reason = "insufficient_depth"
            intent.status = "rejected"
            continue

        actual_fee = taker_fee_usdc(filled, avg_price, category="politics") or Decimal("0")
        spent = cost + actual_fee
        commit_spend(session, intent.id, spent)
        session.add(
            Fill(
                intent_id=intent.id,
                price=avg_price,
                size=filled,
                fee_usdc=actual_fee,
            )
        )
        intent.status = "filled" if filled >= signal.size else "partial"
        intent.simulation_limited = book.limited
        pos = session.scalar(
            select(Position).where(Position.token_id == signal.token_id)
        )
        if pos is None:
            pos = Position(
                token_id=signal.token_id,
                condition_id=signal.condition_id,
                event_slug=signal.event_slug,
                outcome=signal.outcome,
                size=Decimal("0"),
                avg_entry_price=Decimal("0"),
                cost_basis=Decimal("0"),
            )
            session.add(pos)
        new_size = pos.size + filled
        pos.cost_basis = pos.cost_basis + cost
        pos.avg_entry_price = pos.cost_basis / new_size if new_size else Decimal("0")
        pos.size = new_size
        pos.mark_price = executable
        pos.unrealized_pnl = (pos.mark_price - pos.avg_entry_price) * pos.size
        pos.fees_paid = pos.fees_paid + actual_fee
        fees_acct = session.scalar(
            select(LedgerAccount).where(LedgerAccount.name == "fees")
        )
        if fees_acct:
            fees_acct.balance += actual_fee
        signal.status = "executed"
        processed += 1
    session.flush()
    return processed

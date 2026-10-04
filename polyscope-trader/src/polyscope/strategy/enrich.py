"""Enrich signals with book snapshots and market metadata."""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from polyscope.config import Settings
from polyscope.db.models import CohortWallet, Signal
from polyscope.platform.market_cache import resolve_market_meta
from polyscope.platform.public_client import PlatformClient
from polyscope.platform.stream_ingest import BookCache
from polyscope.strategy.consensus import consensus_count
from polyscope.strategy.devils_advocate import build_devils_advocate

logger = logging.getLogger(__name__)


async def enrich_open_signals(
    session: Session,
    settings: Settings,
    platform: PlatformClient,
    book_cache: BookCache,
) -> int:
    signals = session.scalars(
        select(Signal).where(Signal.status.in_(("approved", "pending")))
    ).all()
    updated = 0
    for sig in signals:
        if sig.best_bid_at_signal is not None:
            continue
        try:
            book = await book_cache.get_book(platform, sig.token_id)
        except Exception as exc:
            logger.warning("book fetch failed: %s", exc)
            continue
        best_bid = book.bids[0][0] if book.bids else None
        best_ask = book.asks[0][0] if book.asks else None
        spread = (best_ask - best_bid) if best_bid and best_ask else None
        sig.best_bid_at_signal = best_bid
        sig.best_ask_at_signal = best_ask
        sig.spread_at_signal = spread
        if condition_id := sig.condition_id:
            meta = await resolve_market_meta(session, platform, condition_id, sig.token_id)
            if meta:
                sig.market_category = meta.category
                if meta.event_slug and not sig.event_slug:
                    sig.event_slug = meta.event_slug
                if meta.closed or meta.accepting_orders is False:
                    sig.status = "rejected"
                    sig.reject_reason = "market_closed"
        count = consensus_count(session, sig.condition_id, sig.outcome, sig.side)
        sig.consensus_wallet_count = count
        member = session.scalar(
            select(CohortWallet).where(CohortWallet.wallet == sig.wallet)
        )
        sig.devils_advocate = build_devils_advocate(
            consensus_wallet_count=count,
            min_consensus=settings.flow_consensus_min_wallets,
            spread=spread,
            max_spread=settings.risk.max_spread,
            history_incomplete=bool(member and member.history_incomplete),
            single_wallet=count < 2,
        )
        if count < settings.flow_consensus_min_wallets and sig.status == "approved":
            sig.status = "rejected"
            sig.reject_reason = "insufficient_consensus"
        updated += 1
    session.flush()
    return updated

"""Gamma/CLOB market metadata cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from polyscope.db.models import MarketCache, utcnow
from polyscope.platform.public_client import PlatformClient


@dataclass
class MarketMeta:
    condition_id: str
    token_id: str
    category: str | None
    accepting_orders: bool | None
    min_order_size: Decimal | None
    tick_size: Decimal | None
    event_slug: str | None
    closed: bool | None


async def resolve_market_meta(
    session: Session,
    platform: PlatformClient,
    condition_id: str,
    token_id: str,
) -> MarketMeta | None:
    cached = session.scalar(
        select(MarketCache).where(
            MarketCache.condition_id == condition_id,
            MarketCache.token_id == token_id,
        )
    )
    if cached and (utcnow() - cached.fetched_at).total_seconds() < 3600:
        return MarketMeta(
            condition_id=cached.condition_id,
            token_id=cached.token_id,
            category=cached.category,
            accepting_orders=cached.accepting_orders,
            min_order_size=cached.min_order_size,
            tick_size=cached.tick_size,
            event_slug=cached.event_slug,
            closed=cached.closed,
        )

    market = None
    try:
        pages = platform.client.list_markets(closed=False, page_size=100)
        page = await pages.first_page()
        for m in page.items:
            if str(getattr(m, "condition_id", "")) == condition_id:
                market = m
                break
    except Exception:
        return None
    if market is None:
        return None

    category = getattr(market, "category", None) or getattr(market, "group", None)
    if category is not None:
        category = str(category).lower()
    accepting = getattr(market, "accepting_orders", None)
    if accepting is None:
        accepting = not bool(getattr(market, "closed", False))
    min_size = getattr(market, "minimum_order_size", None) or getattr(market, "min_order_size", None)
    tick = getattr(market, "minimum_tick_size", None) or getattr(market, "tick_size", None)
    event_slug = None
    events = getattr(market, "events", None) or []
    if events:
        event_slug = getattr(events[0], "slug", None) or getattr(events[0], "ticker", None)

    row = cached or MarketCache(condition_id=condition_id, token_id=token_id)
    row.category = category
    row.accepting_orders = bool(accepting) if accepting is not None else None
    row.min_order_size = Decimal(str(min_size)) if min_size is not None else None
    row.tick_size = Decimal(str(tick)) if tick is not None else None
    row.event_slug = str(event_slug) if event_slug else None
    row.closed = bool(getattr(market, "closed", False))
    row.fetched_at = utcnow()
    session.add(row)
    session.flush()

    return MarketMeta(
        condition_id=condition_id,
        token_id=token_id,
        category=row.category,
        accepting_orders=row.accepting_orders,
        min_order_size=row.min_order_size,
        tick_size=row.tick_size,
        event_slug=row.event_slug,
        closed=row.closed,
    )

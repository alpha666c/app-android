"""Resolve Polymarket outcomes in code for paper scoring."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from polyscope.platform.public_client import PlatformClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketResolution:
    resolved: bool
    yes_wins: bool | None
    yes_price: Decimal | None
    no_price: Decimal | None
    closed: bool


def _dec(raw) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except Exception:
        return None


async def fetch_market_outcome_prices(
    platform: PlatformClient, condition_id: str | None
) -> MarketResolution | None:
    if not condition_id:
        return None
    try:
        for closed_flag in (False, True):
            pages = platform.client.list_markets(closed=closed_flag, page_size=100)
            page = await pages.first_page()
            for m in page.items:
                if str(getattr(m, "condition_id", "")) != condition_id:
                    continue
                oc = getattr(m, "outcomes", None)
                yes_p = _dec(getattr(oc.yes, "price", None)) if oc and oc.yes else None
                no_p = _dec(getattr(oc.no, "price", None)) if oc and oc.no else None
                closed = bool(getattr(m, "closed", False)) or closed_flag
                accepting = getattr(m, "accepting_orders", None)
                if accepting is False:
                    closed = True
                resolved = False
                yes_wins: bool | None = None
                if yes_p is not None and no_p is not None:
                    if yes_p >= Decimal("0.95"):
                        resolved = True
                        yes_wins = True
                    elif yes_p <= Decimal("0.05"):
                        resolved = True
                        yes_wins = False
                    elif no_p >= Decimal("0.95"):
                        resolved = True
                        yes_wins = False
                    elif no_p <= Decimal("0.05"):
                        resolved = True
                        yes_wins = True
                return MarketResolution(
                    resolved=resolved,
                    yes_wins=yes_wins,
                    yes_price=yes_p,
                    no_price=no_p,
                    closed=closed,
                )
    except Exception as exc:
        logger.warning("resolution fetch failed: %s", exc)
    return None


def score_paper_position(
    side: str,
    entry_price: Decimal,
    stake_usdc: Decimal,
    yes_wins: bool | None,
    fee_usdc: Decimal | None = None,
) -> tuple[str, Decimal]:
    """Return resolution label win|loss|push and realized pnl in paper USDC."""
    fee = fee_usdc if fee_usdc is not None else Decimal("0")
    side = side.upper()
    if yes_wins is None:
        return ("push", Decimal("0"))
    if entry_price <= 0 or stake_usdc <= 0:
        return ("push", Decimal("0"))
    if side == "YES":
        won = yes_wins is True
    else:
        won = yes_wins is False
    shares = stake_usdc / entry_price
    if won:
        payout = shares * Decimal("1")
        pnl = payout - stake_usdc - fee
        return ("win", pnl)
    pnl = -stake_usdc - fee
    return ("loss", pnl)

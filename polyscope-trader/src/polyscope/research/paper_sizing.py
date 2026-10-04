"""Code-computed paper stake, shares, and taker fee."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

from polyscope.config import Settings
from polyscope.execution.fees import taker_fee_usdc


@dataclass(frozen=True)
class PaperBetSizing:
    stake_usdc: Decimal
    size_shares: Decimal
    entry_price: Decimal
    fee_usdc: Decimal


def _normalize_category(raw: str | None) -> str:
    if raw and str(raw).strip():
        return str(raw).strip().lower()
    return "politics"


def compute_paper_bet(
    settings: Settings,
    entry_price: Decimal,
    category: str | None,
) -> PaperBetSizing | None:
    if entry_price <= 0:
        return None
    stake = settings.risk.max_order_cost
    if stake <= 0:
        stake = Decimal("0.25")
    stake = min(stake, settings.risk.starting_balance)
    shares = (stake / entry_price).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
    if shares <= 0:
        return None
    cat = _normalize_category(category)
    fee = taker_fee_usdc(shares, entry_price, cat)
    if fee is None:
        fee = Decimal("0")
    return PaperBetSizing(
        stake_usdc=stake,
        size_shares=shares,
        entry_price=entry_price,
        fee_usdc=fee,
    )

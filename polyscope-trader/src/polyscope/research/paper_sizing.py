"""Code-computed paper stake and share size (no model arithmetic)."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from polyscope.config import Settings


def compute_paper_stake_and_shares(settings: Settings, entry_price: Decimal) -> tuple[Decimal, Decimal]:
    if entry_price <= 0:
        return Decimal("0"), Decimal("0")
    stake = min(settings.risk.max_order_cost, settings.risk.max_order_cost)
    stake = min(stake, settings.risk.starting_balance)
    if stake <= 0:
        stake = Decimal("0.25")
    shares = (stake / entry_price).quantize(Decimal("0.0001"), rounding=ROUND_DOWN)
    if shares <= 0:
        return stake, Decimal("0")
    return stake, shares

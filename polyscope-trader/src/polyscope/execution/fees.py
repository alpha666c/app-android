"""Taker fee calculation per Polymarket docs."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

FEE_RATES: dict[str, Decimal] = {
    "crypto": Decimal("0.07"),
    "sports": Decimal("0.05"),
    "finance": Decimal("0.04"),
    "politics": Decimal("0.04"),
    "economics": Decimal("0.05"),
    "culture": Decimal("0.05"),
    "weather": Decimal("0.05"),
    "other": Decimal("0.05"),
    "mentions": Decimal("0.04"),
    "tech": Decimal("0.04"),
    "geopolitics": Decimal("0"),
}


def taker_fee_usdc(shares: Decimal, price: Decimal, category: str | None) -> Decimal | None:
    if category is None:
        return None
    rate = FEE_RATES.get(category.lower().strip())
    if rate is None:
        return None
    if rate == 0:
        return Decimal("0")
    fee = shares * rate * price * (Decimal("1") - price)
    return fee.quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)

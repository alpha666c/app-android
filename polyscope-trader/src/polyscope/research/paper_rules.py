"""Deterministic paper rule when no model key (not a live trade)."""

from __future__ import annotations

from decimal import Decimal

from polyscope.research.evidence import MarketEvidence

PROVIDER = "deterministic_rule"


def deterministic_paper_action(evidence: MarketEvidence) -> tuple[str, str]:
    if not evidence.price_available or evidence.yes_buy_price is None:
        return "WAIT", "Deterministic rule: public price missing. Not a model call."
    price = evidence.yes_buy_price
    if price >= Decimal("0.58"):
        return (
            "BUY",
            "Deterministic paper rule: YES price above band. Stake sized in code. Not a model call.",
        )
    if price <= Decimal("0.42"):
        return (
            "SELL",
            "Deterministic paper rule: YES price below band. Stake sized in code. Not a model call.",
        )
    return "WAIT", "Deterministic paper rule: mid band abstain. Not a model call."

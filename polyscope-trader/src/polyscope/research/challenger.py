"""Deterministic challenge layer: can downgrade proposals to WAIT or REJECT."""

from __future__ import annotations

from decimal import Decimal

from polyscope.config import Settings
from polyscope.research.evidence import MarketEvidence

VALID_ACTIONS = frozenset({"BUY", "SELL", "WAIT", "REJECT"})


def normalize_action(raw: str) -> str:
    upper = (raw or "WAIT").upper()
    if upper in ("BUY_YES", "YES"):
        return "BUY"
    if upper in ("BUY_NO", "NO"):
        return "SELL"
    if upper in VALID_ACTIONS:
        return upper
    return "WAIT"


def challenge_proposal(
    action: str,
    reason: str,
    evidence: MarketEvidence,
    contradiction_ids: list[str],
    settings: Settings,
) -> tuple[str, str, list[str]]:
    """Return final action, reason, extra contradiction ids."""
    action = normalize_action(action)
    extra_contra: list[str] = []
    max_spread = settings.risk.max_spread

    if not evidence.price_available:
        return (
            "WAIT",
            "Challenger: required price data missing. " + reason,
            extra_contra,
        )

    if evidence.spread_flag == "extreme_implied_odds":
        extra_contra.append(evidence.evidence_id)
        if action in ("BUY", "SELL"):
            return (
                "WAIT",
                "Challenger: implied odds near 0 or 1; wait for clearer liquidity. " + reason,
                extra_contra,
            )

    if evidence.yes_buy_price is not None:
        # Proxy spread check: distance from 0.5 as rough uncertainty (code-only heuristic)
        distance = abs(evidence.yes_buy_price - Decimal("0.5"))
        if distance < max_spread and action in ("BUY", "SELL"):
            extra_contra.append(evidence.evidence_id)
            return (
                "REJECT",
                "Challenger: price sits in a tight band; no clear edge without more evidence. "
                + reason,
                extra_contra,
            )

    if contradiction_ids:
        if action in ("BUY", "SELL"):
            return (
                "WAIT",
                "Challenger: contradictory evidence on file. " + reason,
                extra_contra,
            )

    return action, reason, extra_contra

"""Rule-based reasons not to trade (no LLM required)."""

from __future__ import annotations

from decimal import Decimal


def build_devils_advocate(
    *,
    consensus_wallet_count: int,
    min_consensus: int,
    spread: Decimal | None,
    max_spread: Decimal,
    history_incomplete: bool,
    single_wallet: bool,
) -> str:
    reasons: list[str] = []
    if consensus_wallet_count < min_consensus:
        reasons.append(f"Only {consensus_wallet_count} wallet(s) in flow consensus (need {min_consensus})")
    if spread is not None and spread > max_spread:
        reasons.append(f"Spread {spread} exceeds limit {max_spread}")
    if history_incomplete:
        reasons.append("Wallet or market history pagination incomplete")
    if single_wallet:
        reasons.append("Single-wallet flow is not proof of unhedged conviction")
    if not reasons:
        reasons.append("Residual model risk: hypothesis only, not established EV")
    return "; ".join(reasons)

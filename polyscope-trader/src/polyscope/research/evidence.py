"""Code-computed market evidence snapshots (no model arithmetic)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class MarketEvidence:
    evidence_id: str
    market_slug: str
    market_title: str
    condition_id: str | None
    observed_at: str
    yes_buy_price: Decimal | None
    price_available: bool
    spread_flag: str
    category: str
    snapshot_lines: list[str]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.evidence_id,
            "market_slug": self.market_slug,
            "title": self.market_title,
            "yes_buy_price": str(self.yes_buy_price) if self.yes_buy_price is not None else None,
            "price_available": self.price_available,
            "spread_flag": self.spread_flag,
            "observed_at": self.observed_at,
        }


def _parse_price(raw: str | None) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def _evidence_id(slug: str, when: datetime) -> str:
    digest = hashlib.sha256(f"{slug}:{when.isoformat()}".encode()).hexdigest()[:10]
    return f"market-snapshot-{when.strftime('%Y%m%d%H%M')}-{digest}"


def build_market_evidence(market: dict, observed_at: datetime | None = None) -> MarketEvidence:
    when = observed_at or datetime.now(timezone.utc)
    slug = market.get("slug") or "unknown"
    title = market.get("title") or slug
    condition_id = market.get("condition_id")
    yes_price = _parse_price(market.get("yes_buy_price"))
    price_available = yes_price is not None
    spread_flag = "unknown"
    if yes_price is not None:
        if yes_price <= Decimal("0.02") or yes_price >= Decimal("0.98"):
            spread_flag = "extreme_implied_odds"
        else:
            spread_flag = "mid_range"
    eid = _evidence_id(slug, when)
    lines = [
        f"# Market snapshot: {title}",
        "",
        "Computed in code from public Polymarket API responses.",
        "",
        f"- Slug: `{slug}`",
        f"- Condition: `{condition_id or 'n/a'}`",
        f"- YES buy price (venue): {yes_price if yes_price is not None else 'unavailable'}",
        f"- Price available: {price_available}",
        f"- Spread / liquidity flag: {spread_flag}",
        f"- Category: {market.get('category') or 'n/a'}",
    ]
    return MarketEvidence(
        evidence_id=eid,
        market_slug=slug,
        market_title=title,
        condition_id=condition_id,
        observed_at=when.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        yes_buy_price=yes_price,
        price_available=price_available,
        spread_flag=spread_flag,
        category=str(market.get("category") or ""),
        snapshot_lines=lines,
    )


def evidence_is_thin(evidence: MarketEvidence, peer_count: int) -> tuple[bool, str]:
    if not evidence.price_available:
        return True, "Public YES price missing for featured market."
    if peer_count < 1:
        return True, "Too few open markets to cross-check context."
    return False, ""

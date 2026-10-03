"""Generate and persist paper model calls from open markets."""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from polyscope.config import Settings, assert_paper_only_for_research
from polyscope.db.models import PaperModelCall, utcnow
from polyscope.platform.public_client import PlatformClient
from polyscope.research.ai.client import ResearchAIClient

logger = logging.getLogger(__name__)


async def fetch_open_markets(platform: PlatformClient, limit: int = 8) -> list[dict]:
    pages = platform.client.list_markets(closed=False, page_size=limit)
    page = await pages.first_page()
    rows: list[dict] = []
    for m in page.items:
        slug = getattr(m, "slug", None) or ""
        title = getattr(m, "question", None) or getattr(m, "title", None) or slug
        condition_id = str(getattr(m, "condition_id", "") or "")
        yes_price = None
        try:
            outcomes = getattr(m, "outcomes", None)
            if outcomes and getattr(outcomes, "yes", None):
                tid = outcomes.yes.token_id
                if tid:
                    price = await platform.client.get_price(token_id=tid, side="BUY")
                    yes_price = str(price)
        except Exception:
            pass
        rows.append(
            {
                "slug": slug,
                "title": str(title),
                "condition_id": condition_id,
                "yes_buy_price": yes_price,
                "category": str(getattr(m, "category", "") or ""),
            }
        )
    return rows


async def generate_paper_model_call(
    session: Session,
    settings: Settings,
    platform: PlatformClient,
) -> PaperModelCall:
    assert_paper_only_for_research(settings)
    markets = await fetch_open_markets(platform, limit=8)
    if not markets:
        row = PaperModelCall(
            market_slug="none",
            market_title="No open markets",
            condition_id=None,
            call="SKIP",
            reason="Could not load open markets from public API.",
            provider="rules_fallback",
            mode="paper",
            outcome=None,
            created_at=utcnow(),
        )
        session.add(row)
        session.flush()
        return row

    featured = markets[0]
    client = ResearchAIClient(settings)
    suggestion = await client.suggest_paper_call(
        {"featured_market": featured, "other_markets": markets[1:4]}
    )
    row = PaperModelCall(
        market_slug=featured["slug"] or "unknown",
        market_title=featured["title"],
        condition_id=featured.get("condition_id"),
        call=suggestion.call,
        reason=suggestion.reason,
        provider=suggestion.provider,
        mode="paper",
        outcome=None,
        created_at=utcnow(),
    )
    session.add(row)
    session.flush()
    return row

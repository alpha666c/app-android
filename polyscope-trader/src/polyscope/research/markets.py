"""Public Polymarket market fetch helpers."""

from __future__ import annotations

from polyscope.platform.public_client import PlatformClient


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

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
                "no_buy_price": None,
                "yes_token_id": None,
                "no_token_id": None,
                "category": str(getattr(m, "category", "") or ""),
            }
        )
        oc = getattr(m, "outcomes", None)
        if oc:
            if oc.yes:
                rows[-1]["yes_token_id"] = str(oc.yes.token_id)
            if oc.no:
                rows[-1]["no_token_id"] = str(oc.no.token_id)
                try:
                    np = await platform.client.get_price(token_id=oc.no.token_id, side="BUY")
                    rows[-1]["no_buy_price"] = str(np)
                except Exception:
                    pass
    return rows


async def enrich_market_tokens(
    platform: PlatformClient, featured: dict, condition_id: str | None
) -> None:
    if featured.get("yes_token_id"):
        return
    if not condition_id:
        return
    pages = platform.client.list_markets(closed=False, page_size=50)
    page = await pages.first_page()
    for m in page.items:
        if str(getattr(m, "condition_id", "")) != condition_id:
            continue
        oc = getattr(m, "outcomes", None)
        if oc and oc.yes:
            featured["yes_token_id"] = str(oc.yes.token_id)
            try:
                featured["yes_buy_price"] = str(
                    await platform.client.get_price(token_id=oc.yes.token_id, side="BUY")
                )
            except Exception:
                pass
        if oc and oc.no:
            featured["no_token_id"] = str(oc.no.token_id)
            try:
                featured["no_buy_price"] = str(
                    await platform.client.get_price(token_id=oc.no.token_id, side="BUY")
                )
            except Exception:
                pass
        break

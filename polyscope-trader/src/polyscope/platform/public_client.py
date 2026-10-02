"""Public Polymarket data access and geoblock checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import httpx
from polymarket import AsyncPublicClient

logger = logging.getLogger(__name__)

GEOBLOCK_URL = "https://polymarket.com/api/geoblock"


@dataclass
class GeoblockResult:
    blocked: bool
    ip: str | None
    country: str | None
    region: str | None
    checked_at: datetime


@dataclass
class OrderBookSnapshot:
    token_id: str
    bids: list[tuple[Decimal, Decimal]]
    asks: list[tuple[Decimal, Decimal]]
    fetched_at: datetime
    limited: bool = False


class PlatformClient:
    def __init__(self) -> None:
        self._client: AsyncPublicClient | None = None

    async def __aenter__(self) -> PlatformClient:
        self._client = AsyncPublicClient()
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client is not None:
            await self._client.__aexit__(*args)

    @property
    def client(self) -> AsyncPublicClient:
        if self._client is None:
            raise RuntimeError("PlatformClient not started")
        return self._client

    async def check_geoblock(self) -> GeoblockResult:
        async with httpx.AsyncClient(timeout=15.0) as http:
            response = await http.get(GEOBLOCK_URL)
            response.raise_for_status()
            data = response.json()
        return GeoblockResult(
            blocked=bool(data.get("blocked")),
            ip=data.get("ip"),
            country=data.get("country"),
            region=data.get("region"),
            checked_at=datetime.now(timezone.utc),
        )

    async def fetch_leaderboard_page(
        self, window: str, page_size: int = 50
    ) -> list[Any]:
        pages = self.client.list_trader_leaderboard(window=window, page_size=page_size)
        page = await pages.first_page()
        return list(page.items)

    async def fetch_wallet_activity(self, wallet: str, page_size: int = 20) -> list[Any]:
        pages = self.client.list_activity(user=wallet, page_size=page_size)
        page = await pages.first_page()
        return list(page.items)

    async def fetch_order_book(self, token_id: str) -> OrderBookSnapshot:
        book = await self.client.get_order_book(token_id=token_id)
        bids: list[tuple[Decimal, Decimal]] = []
        asks: list[tuple[Decimal, Decimal]] = []
        limited = False
        for level in getattr(book, "bids", []) or []:
            bids.append((Decimal(str(level.price)), Decimal(str(level.size))))
        for level in getattr(book, "asks", []) or []:
            asks.append((Decimal(str(level.price)), Decimal(str(level.size))))
        if not bids and not asks:
            limited = True
        return OrderBookSnapshot(
            token_id=token_id,
            bids=sorted(bids, key=lambda x: x[0], reverse=True),
            asks=sorted(asks, key=lambda x: x[0]),
            fetched_at=datetime.now(timezone.utc),
            limited=limited,
        )

    async def smoke_markets(self, limit: int = 3) -> list[str]:
        pages = self.client.list_markets(closed=False, page_size=limit)
        page = await pages.first_page()
        return [m.slug or str(m.condition_id) for m in page.items]

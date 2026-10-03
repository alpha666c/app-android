"""Optional realtime book cache with poll fallback."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from polyscope.platform.public_client import OrderBookSnapshot, PlatformClient

logger = logging.getLogger(__name__)


@dataclass
class BookCache:
    books: dict[str, OrderBookSnapshot] = field(default_factory=dict)
    use_stream: bool = False
    _task: asyncio.Task | None = None

    async def get_book(self, platform: PlatformClient, token_id: str) -> OrderBookSnapshot:
        cached = self.books.get(token_id)
        if cached and (datetime.now(timezone.utc) - cached.fetched_at).total_seconds() < 30:
            return cached
        book = await platform.fetch_order_book(token_id)
        self.books[token_id] = book
        return book

    async def start_stream(self, platform: PlatformClient, token_ids: list[str]) -> None:
        if not token_ids or self._task is not None:
            return
        self.use_stream = True

        async def _run() -> None:
            try:
                from polymarket.streams import MarketSpec

                async with await platform.client.subscribe(
                    [MarketSpec(token_ids=token_ids[:20])]
                ) as stream:
                    async for event in stream:
                        tid = getattr(event, "token_id", None) or getattr(
                            getattr(event, "payload", None), "token_id", None
                        )
                        if tid:
                            book = await platform.fetch_order_book(str(tid))
                            self.books[str(tid)] = book
            except Exception as exc:
                logger.info("stream ingest unavailable, using poll: %s", exc)
                self.use_stream = False

        self._task = asyncio.create_task(_run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

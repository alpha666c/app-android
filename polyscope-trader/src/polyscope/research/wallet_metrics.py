"""Wallet performance metrics from public Data API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from polyscope.platform.public_client import PlatformClient


@dataclass
class WalletCoverage:
    wallet: str
    position_pnl_available: bool
    rewards_separated: bool
    history_incomplete: bool
    last_activity_at: datetime | None
    sample_size: int


async def assess_wallet(platform: PlatformClient, wallet: str) -> WalletCoverage:
    positions = []
    try:
        pages = platform.client.list_positions(user=wallet, page_size=5)
        page = await pages.first_page()
        positions = list(page.items)
    except Exception:
        return WalletCoverage(wallet, False, False, True, None, 0)

    last_activity = None
    activities = await platform.fetch_wallet_activity(wallet, page_size=5)
    if activities:
        ts = getattr(activities[0], "timestamp", None)
        if isinstance(ts, datetime):
            last_activity = ts

    return WalletCoverage(
        wallet=wallet,
        position_pnl_available=bool(positions),
        rewards_separated=True,
        history_incomplete=len(activities) >= 5,
        last_activity_at=last_activity,
        sample_size=len(activities),
    )

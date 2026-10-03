"""Wallet performance metrics from public Data API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from polyscope.db.models import CohortWallet
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
    has_more = False
    try:
        pages = platform.client.list_positions(user=wallet, page_size=5)
        page = await pages.first_page()
        positions = list(page.items)
        has_more = bool(page.next_cursor)
    except Exception:
        return WalletCoverage(wallet, False, False, True, None, 0)

    last_activity = None
    activities = await platform.fetch_wallet_activity(wallet, page_size=20)
    if activities:
        ts = getattr(activities[0], "timestamp", None) or getattr(
            activities[0], "created_at", None
        )
        if isinstance(ts, datetime):
            last_activity = ts

    return WalletCoverage(
        wallet=wallet,
        position_pnl_available=bool(positions),
        rewards_separated=True,
        history_incomplete=has_more or len(activities) >= 20,
        last_activity_at=last_activity,
        sample_size=len(activities),
    )


async def run_wallet_studies(
    session: Session, platform: PlatformClient, limit: int = 5
) -> int:
    cohort = session.scalars(
        select(CohortWallet).where(CohortWallet.included.is_(True)).limit(limit)
    ).all()
    updated = 0
    for member in cohort:
        cov = await assess_wallet(platform, member.wallet)
        member.history_incomplete = cov.history_incomplete
        if cov.last_activity_at:
            member.last_activity_at = cov.last_activity_at
        updated += 1
    session.flush()
    return updated

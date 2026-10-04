"""Leaderboard-driven wallet cohort discovery."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from polyscope.config import Settings
from polyscope.db.models import CohortWallet, utcnow
from polyscope.platform.public_client import PlatformClient

logger = logging.getLogger(__name__)


async def refresh_cohort(session: Session, settings: Settings, platform: PlatformClient) -> int:
    session.execute(delete(CohortWallet))
    entries = await platform.fetch_leaderboard_page(
        window=settings.cohort_leaderboard_window,
        page_size=settings.cohort_max_rank,
    )
    included = 0
    now = utcnow()
    for entry in entries:
        wallet = str(getattr(entry, "wallet", "") or "").lower()
        rank = int(getattr(entry, "rank", 0) or 0)
        pnl = Decimal(str(getattr(entry, "pnl", 0) or 0))
        volume = Decimal(str(getattr(entry, "volume", 0) or 0))
        exclusion: str | None = None
        is_included = True
        if rank > settings.cohort_max_rank:
            exclusion = "rank_above_max"
            is_included = False
        elif volume < settings.cohort_min_volume:
            exclusion = "volume_below_min"
            is_included = False

        last_activity: datetime | None = None
        history_incomplete = False
        if is_included:
            try:
                activities = await platform.fetch_wallet_activity(wallet, page_size=5)
                if activities:
                    ts = getattr(activities[0], "timestamp", None) or getattr(
                        activities[0], "created_at", None
                    )
                    if ts is not None:
                        last_activity = ts if isinstance(ts, datetime) else ts
                    if len(activities) < 1:
                        history_incomplete = True
                else:
                    exclusion = "no_recent_activity"
                    is_included = False
            except Exception as exc:
                logger.warning("activity fetch failed for %s: %s", wallet[:10], exc)
                history_incomplete = True

            if is_included and last_activity:
                if isinstance(last_activity, datetime):
                    if last_activity.tzinfo is None:
                        last_activity = last_activity.replace(tzinfo=timezone.utc)
                    if last_activity < now - timedelta(days=14):
                        exclusion = "inactive"
                        is_included = False

        row = CohortWallet(
            wallet=wallet,
            rank=rank,
            window=settings.cohort_leaderboard_window,
            pnl=pnl,
            volume=volume,
            included=is_included,
            exclusion_reason=exclusion,
            last_activity_at=last_activity if isinstance(last_activity, datetime) else None,
            observed_at=now,
            history_incomplete=history_incomplete,
        )
        session.add(row)
        if is_included:
            included += 1
    session.flush()
    return included

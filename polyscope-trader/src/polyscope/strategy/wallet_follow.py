"""Wallet-following signal pipeline."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from polyscope.config import Settings
from polyscope.db.models import CohortWallet, Signal, WalletActivityCursor, utcnow
from polyscope.platform.public_client import PlatformClient

logger = logging.getLogger(__name__)


def _activity_id(item: object) -> str:
    for attr in ("id", "transaction_hash", "trade_id", "activity_id"):
        val = getattr(item, attr, None)
        if val:
            return str(val)
    return f"{getattr(item, 'timestamp', '')}:{getattr(item, 'token_id', '')}"


def _parse_side(item: object) -> str | None:
    side = getattr(item, "side", None) or getattr(item, "type", None)
    if side is None:
        return None
    text = str(side).upper()
    if "BUY" in text:
        return "BUY"
    if "SELL" in text:
        return "SELL"
    return None


async def ingest_cohort_activity(
    session: Session, settings: Settings, platform: PlatformClient
) -> tuple[int, int]:
    cohort = session.scalars(select(CohortWallet).where(CohortWallet.included.is_(True))).all()
    new_signals = 0
    rejected = 0
    now = utcnow()
    for member in cohort:
        try:
            activities = await platform.fetch_wallet_activity(member.wallet, page_size=10)
        except Exception as exc:
            logger.warning("activity poll failed: %s", exc)
            continue
        cursor = session.get(WalletActivityCursor, member.wallet)
        if cursor is None:
            cursor = WalletActivityCursor(wallet=member.wallet)
            session.add(cursor)
        for item in activities:
            act_id = _activity_id(item)
            if cursor.last_seen_tx_id == act_id:
                break
            side = _parse_side(item)
            token_id = str(getattr(item, "token_id", "") or getattr(item, "asset_id", "") or "")
            condition_id = str(getattr(item, "condition_id", "") or "")
            if not side or not token_id:
                continue
            price_raw = getattr(item, "price", None) or getattr(item, "avg_price", None)
            size_raw = getattr(item, "size", None) or getattr(item, "amount", None)
            if price_raw is None or size_raw is None:
                continue
            price = Decimal(str(price_raw))
            size = Decimal(str(size_raw))
            exchange_ts = getattr(item, "timestamp", None) or getattr(item, "created_at", None)
            if isinstance(exchange_ts, datetime) and exchange_ts.tzinfo is None:
                exchange_ts = exchange_ts.replace(tzinfo=timezone.utc)
            dedupe_key = f"{member.wallet}:{act_id}:{side}:{token_id}"
            existing = session.scalar(select(Signal).where(Signal.dedupe_key == dedupe_key))
            if existing:
                continue
            signal_age = (now - exchange_ts).total_seconds() if exchange_ts else None
            reject_reason = None
            status = "approved"
            if signal_age is not None and signal_age > settings.risk.max_signal_age_seconds:
                reject_reason = "stale_signal"
                status = "rejected"
                rejected += 1
            sig = Signal(
                dedupe_key=dedupe_key,
                wallet=member.wallet,
                condition_id=condition_id,
                token_id=token_id,
                event_slug=getattr(item, "event_slug", None),
                outcome=getattr(item, "outcome", None),
                side=side,
                reference_price=price,
                size=size,
                exchange_timestamp=exchange_ts if isinstance(exchange_ts, datetime) else None,
                observed_at=now,
                status=status,
                reject_reason=reject_reason,
            )
            session.add(sig)
            if status == "approved":
                new_signals += 1
        if activities:
            cursor.last_seen_tx_id = _activity_id(activities[0])
            cursor.updated_at = now
    session.flush()
    return new_signals, rejected

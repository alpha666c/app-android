"""Readiness score and automation tiers (deterministic)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from polyscope.config import AutomationTier, Settings
from polyscope.db.models import ReadinessSnapshot, Signal, SystemState, utcnow
from polyscope.db.session import get_system_state


@dataclass
class ReadinessResult:
    score: int
    tier: AutomationTier
    breakdown: dict[str, int | str | bool]
    insufficient_data: bool


def compute_readiness(session: Session, settings: Settings) -> ReadinessResult:
    state = get_system_state(session)
    breakdown: dict[str, int | str | bool] = {}
    score = 0

    if state.data_stale:
        breakdown["data_stale"] = True
    else:
        score += 20
        breakdown["data_fresh"] = True

    if state.geoblock_blocked is False:
        score += 10
        breakdown["geoblock_clear"] = True
    elif state.geoblock_blocked is True:
        breakdown["geoblock_blocked"] = True

    if state.last_reconciliation_at:
        age = (utcnow() - state.last_reconciliation_at).total_seconds()
        if age < settings.risk.max_data_age_seconds * 2:
            score += 15
            breakdown["reconciliation_recent"] = True

    recent_signals = session.scalar(
        select(func.count())
        .select_from(Signal)
        .where(Signal.created_at >= utcnow().replace(hour=0, minute=0, second=0))
    ) or 0
    breakdown["signals_today"] = recent_signals
    if recent_signals >= 1:
        score += 10
    else:
        breakdown["insufficient_signal_sample"] = True

    rejected = session.scalar(
        select(func.count()).select_from(Signal).where(Signal.status == "rejected")
    ) or 0
    total = session.scalar(select(func.count()).select_from(Signal)) or 0
    if total >= 10:
        score += min(15, int(15 * (1 - rejected / max(total, 1))))
        breakdown["filter_ratio"] = f"{rejected}/{total}"

    if settings.trading_mode.value == "paper":
        score += 20
        breakdown["paper_mode"] = True

    if state.live_stream_ok:
        score += 10
        breakdown["live_stream"] = True

    tier = AutomationTier(settings.automation_tier)
    insufficient = total < 5 and recent_signals == 0

    return ReadinessResult(
        score=min(100, score),
        tier=tier,
        breakdown=breakdown,
        insufficient_data=insufficient,
    )


def persist_readiness(session: Session, result: ReadinessResult) -> None:
    state = get_system_state(session)
    state.readiness_score = result.score
    session.add(
        ReadinessSnapshot(
            score=result.score,
            tier=result.tier.value,
            breakdown_json=json.dumps(result.breakdown),
        )
    )


def tier_allows_auto_execute(settings: Settings, tier: AutomationTier) -> bool:
    if tier == AutomationTier.OBSERVE:
        return False
    if tier == AutomationTier.PAPER_AUTO:
        return settings.trading_mode.value == "paper"
    if tier == AutomationTier.LIVE_MICRO:
        return settings.trading_mode.value == "live"
    if tier == AutomationTier.LIVE_SCALED:
        return settings.trading_mode.value == "live" and settings.live_scaled_unlocked
    return False

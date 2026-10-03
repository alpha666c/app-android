"""AI research jobs — advisory briefs stored in DB."""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from polyscope.config import Settings
from polyscope.db.models import CohortWallet, ResearchBrief, Signal
from polyscope.research.ai.client import ResearchAIClient


async def run_daily_brief(session: Session, settings: Settings) -> ResearchBrief | None:
    client = ResearchAIClient(settings)
    if not client.available():
        return None
    facts = {
        "cohort_included": session.scalar(
            select(func.count()).select_from(CohortWallet).where(CohortWallet.included.is_(True))
        ),
        "signals_total": session.scalar(select(func.count()).select_from(Signal)),
        "signals_rejected": session.scalar(
            select(func.count()).select_from(Signal).where(Signal.status == "rejected")
        ),
        "mode": settings.trading_mode.value,
        "tier": settings.automation_tier.value,
    }
    out = await client.synthesize("daily_sitrep", facts)
    if out is None:
        return None
    brief = ResearchBrief(
        topic="daily_sitrep",
        provider=settings.ai_provider,
        content_json=json.dumps(
            {
                "thesis": out.thesis,
                "uncertainties": out.uncertainties,
                "data_gaps": out.data_gaps,
                "cautions": out.cautions,
            }
        ),
    )
    session.add(brief)
    session.flush()
    return brief

"""Generate and persist paper model calls from open markets."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from polyscope.config import Settings
from polyscope.db.models import PaperModelCall
from polyscope.platform.public_client import PlatformClient
from polyscope.research.markets import fetch_open_markets
from polyscope.research.paper_pass import run_paper_research_pass

logger = logging.getLogger(__name__)

__all__ = ["fetch_open_markets", "generate_paper_model_call"]


async def generate_paper_model_call(
    session: Session,
    settings: Settings,
    platform: PlatformClient,
) -> PaperModelCall:
    return await run_paper_research_pass(session, settings, platform)

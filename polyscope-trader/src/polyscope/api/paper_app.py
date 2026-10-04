"""JSON API helpers for the Viktor paper app shell."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from polyscope.config import Settings, assert_paper_only_for_research
from polyscope.db.models import PaperLesson, PaperModelCall, PaperPosition
from polyscope.db.session import get_system_state
from polyscope.platform.public_client import PlatformClient
from polyscope.research.markets import fetch_open_markets
from polyscope.research.paper_bot import compute_paper_score, lesson_to_api, position_to_api
from polyscope.research.paper_labels import parse_tags_payload, paper_call_to_api


def _call_matches_tag(call: PaperModelCall, tag: str) -> bool:
    tags, _ = parse_tags_payload(call.tags_json)
    return tag.lower() in [t.lower() for t in tags]


def collect_all_tags(session: Session, limit: int = 200) -> list[str]:
    rows = session.scalars(select(PaperModelCall.tags_json).limit(limit)).all()
    found: list[str] = []
    for raw in rows:
        tags, _ = parse_tags_payload(raw)
        for t in tags:
            if t not in found:
                found.append(t)
    return sorted(found)


async def build_paper_app_state(
    session: Session,
    cfg: Settings,
    tag: str | None = None,
) -> dict[str, Any]:
    assert_paper_only_for_research(cfg)
    state = get_system_state(session)
    calls = session.scalars(
        select(PaperModelCall).order_by(PaperModelCall.id.desc()).limit(50)
    ).all()
    if tag:
        calls = [c for c in calls if _call_matches_tag(c, tag)]
    decisions = [paper_call_to_api(c) for c in calls]
    positions = session.scalars(
        select(PaperPosition).order_by(PaperPosition.id.desc()).limit(40)
    ).all()
    lessons = session.scalars(
        select(PaperLesson).order_by(PaperLesson.id.desc()).limit(30)
    ).all()
    markets: list[dict] = []
    async with PlatformClient() as platform:
        try:
            raw = await fetch_open_markets(platform, limit=6)
            markets = [{"title": m.get("title"), "slug": m.get("slug")} for m in raw]
        except Exception:
            markets = []
    loop_pass_count = session.scalar(select(func.count()).select_from(PaperModelCall)) or 0
    return {
        "paper_only": True,
        "live_locked": True,
        "bot": {
            "paused": bool(state.paper_bot_paused),
            "last_run_at": state.paper_bot_last_at.isoformat() if state.paper_bot_last_at else None,
            "run_count": state.paper_bot_runs or 0,
            "interval_seconds": cfg.paper_bot_interval_seconds,
        },
        "score": compute_paper_score(session),
        "loop_pass_count": loop_pass_count,
        "decisions": decisions,
        "positions": [position_to_api(p) for p in positions if p],
        "lessons": [lesson_to_api(l) for l in lessons],
        "all_tags": collect_all_tags(session),
        "markets": markets,
        "active_tag": tag,
    }


def get_decision_detail(session: Session, decision_id: int) -> dict | None:
    row = session.get(PaperModelCall, decision_id)
    if row is None:
        return None
    out = paper_call_to_api(row)
    pos = session.scalar(select(PaperPosition).where(PaperPosition.call_id == row.id))
    out["position"] = position_to_api(pos)
    return out


def get_position_detail(session: Session, position_id: int) -> dict | None:
    row = session.get(PaperPosition, position_id)
    if row is None:
        return None
    out = position_to_api(row)
    call = session.get(PaperModelCall, row.call_id)
    out["call"] = paper_call_to_api(call) if call else None
    return out


def get_lesson_detail(session: Session, lesson_id: int) -> dict | None:
    row = session.get(PaperLesson, lesson_id)
    if row is None:
        return None
    return lesson_to_api(row)

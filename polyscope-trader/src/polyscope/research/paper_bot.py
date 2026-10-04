"""Automatic paper bot tick: resolve, research, open paper positions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from polyscope.config import Settings
from polyscope.db.models import PaperLesson, PaperModelCall, PaperPosition, utcnow
from polyscope.db.session import get_system_state
from polyscope.platform.public_client import PlatformClient
from polyscope.research.paper_labels import paper_call_to_api
from polyscope.research.paper_lessons import market_topic_key, record_loss_lesson
from polyscope.research.markets import enrich_market_tokens
from polyscope.research.paper_pass import run_paper_research_pass
from polyscope.research.paper_resolution import fetch_market_outcome_prices, score_paper_position
from polyscope.research.paper_sizing import compute_paper_stake_and_shares

logger = logging.getLogger(__name__)


def position_to_api(row: PaperPosition | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "call_id": row.call_id,
        "status": row.status,
        "side": row.side,
        "market_slug": row.market_slug,
        "market_title": row.market_title,
        "market_topic": row.market_topic,
        "stake_usdc": str(row.stake_usdc),
        "entry_price": str(row.entry_price),
        "size_shares": str(row.size_shares),
        "opened_at": row.opened_at.isoformat() if row.opened_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "resolution": row.resolution,
        "realized_pnl": str(row.realized_pnl) if row.realized_pnl is not None else None,
    }


def lesson_to_api(row: PaperLesson) -> dict:
    return {
        "id": row.id,
        "lesson_id": row.lesson_id,
        "market_topic": row.market_topic,
        "market_slug": row.market_slug,
        "summary": row.summary,
        "validation_status": row.validation_status,
        "loss_pnl": str(row.loss_pnl) if row.loss_pnl is not None else None,
        "vault_path": row.vault_path,
        "position_id": row.position_id,
        "call_id": row.call_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def compute_paper_score(session: Session) -> dict:
    from sqlalchemy import func

    open_n = session.scalar(
        select(func.count()).select_from(PaperPosition).where(PaperPosition.status == "open")
    ) or 0
    wins = session.scalar(
        select(func.count()).select_from(PaperPosition).where(PaperPosition.resolution == "win")
    ) or 0
    losses = session.scalar(
        select(func.count()).select_from(PaperPosition).where(PaperPosition.resolution == "loss")
    ) or 0
    pnl_rows = session.scalars(
        select(PaperPosition.realized_pnl).where(PaperPosition.realized_pnl.is_not(None))
    ).all()
    total_pnl = sum((p or Decimal("0")) for p in pnl_rows)
    return {
        "open_positions": open_n,
        "wins": wins,
        "losses": losses,
        "total_realized_pnl": str(total_pnl),
    }


async def resolve_open_paper_positions(
    session: Session,
    settings: Settings,
    platform: PlatformClient,
) -> int:
    from pathlib import Path

    open_rows = session.scalars(
        select(PaperPosition).where(PaperPosition.status == "open")
    ).all()
    resolved = 0
    vault_root = Path(settings.vault_dir)
    for pos in open_rows:
        snap = await fetch_market_outcome_prices(platform, pos.condition_id)
        if snap is None or not snap.resolved or snap.yes_wins is None:
            continue
        label, pnl = score_paper_position(
            pos.side,
            pos.entry_price,
            pos.stake_usdc,
            snap.yes_wins,
        )
        pos.status = "resolved"
        pos.resolved_at = utcnow()
        pos.resolution = label
        pos.realized_pnl = pnl
        pos.resolved_yes_price = snap.yes_price
        call = session.get(PaperModelCall, pos.call_id)
        if call:
            call.outcome = label
        if label == "loss":
            record_loss_lesson(session, vault_root, pos, call, pnl)
        resolved += 1
    return resolved


def open_paper_position_from_call(
    session: Session,
    settings: Settings,
    call: PaperModelCall,
    featured: dict,
) -> PaperPosition | None:
    action = (call.call or "").upper()
    if action not in ("BUY", "SELL"):
        return None
    yes_price_raw = featured.get("yes_buy_price")
    no_price_raw = featured.get("no_buy_price")
    try:
        yes_p = Decimal(str(yes_price_raw)) if yes_price_raw else Decimal("0")
    except Exception:
        yes_p = Decimal("0")
    if action == "BUY":
        side = "YES"
        entry = yes_p
        token_id = featured.get("yes_token_id")
    else:
        side = "NO"
        try:
            entry = Decimal(str(no_price_raw)) if no_price_raw else (Decimal("1") - yes_p)
        except Exception:
            entry = Decimal("1") - yes_p if yes_p else Decimal("0")
        token_id = featured.get("no_token_id")
    if entry <= 0:
        return None
    stake, shares = compute_paper_stake_and_shares(settings, entry)
    if shares <= 0:
        return None
    topic = market_topic_key(featured.get("category"), featured.get("slug") or call.market_slug)
    pos = PaperPosition(
        call_id=call.id,
        status="open",
        side=side,
        market_slug=call.market_slug,
        market_title=call.market_title,
        market_topic=topic,
        condition_id=call.condition_id,
        token_id=str(token_id) if token_id else None,
        stake_usdc=stake,
        entry_price=entry,
        size_shares=shares,
        opened_at=utcnow(),
    )
    call.stake_usdc = stake
    call.size_shares = shares
    call.side = side
    session.add(pos)
    session.flush()
    return pos


async def run_paper_bot_tick(
    session: Session,
    settings: Settings,
    platform: PlatformClient,
) -> dict:
    resolved_n = await resolve_open_paper_positions(session, settings, platform)
    call = await run_paper_research_pass(session, settings, platform)
    featured: dict = {
        "slug": call.market_slug,
        "title": call.market_title,
        "category": "",
        "yes_buy_price": None,
        "no_buy_price": None,
    }
    if call.evidence_json:
        import json

        try:
            payload = json.loads(call.evidence_json)
            items = payload.get("items") or []
            if items:
                featured["yes_buy_price"] = items[0].get("yes_buy_price")
        except json.JSONDecodeError:
            pass
    await enrich_market_tokens(platform, featured, call.condition_id)
    position = open_paper_position_from_call(session, settings, call, featured)
    state = get_system_state(session)
    state.paper_bot_last_at = datetime.now(timezone.utc)
    state.paper_bot_runs = (state.paper_bot_runs or 0) + 1
    return {
        "resolved_count": resolved_n,
        "call": paper_call_to_api(call),
        "position": position_to_api(position),
        "score": compute_paper_score(session),
    }

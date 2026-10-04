"""Training lessons from resolved paper bets for future calls."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from polyscope.config import Settings
from polyscope.db.models import PaperLesson, PaperModelCall, PaperPosition, utcnow
from polyscope.research.vault import ensure_vault_layout


def market_topic_key(category: str | None, market_slug: str) -> str:
    if category and category.strip():
        return category.strip().lower()
    parts = (market_slug or "").split("-")
    if len(parts) >= 2:
        return "-".join(parts[:2]).lower()
    return (market_slug or "unknown")[:48].lower()


def load_lessons_for_topic(
    session: Session,
    topic: str,
    limit: int = 5,
    as_of: datetime | None = None,
) -> list[PaperLesson]:
    stmt = select(PaperLesson).where(PaperLesson.market_topic == topic)
    if as_of is not None:
        stmt = stmt.where(PaperLesson.created_at < as_of)
    return session.scalars(stmt.order_by(PaperLesson.id.desc()).limit(limit)).all()


def lessons_to_facts(lessons: list[PaperLesson]) -> list[dict]:
    out: list[dict] = []
    for les in lessons:
        item = {
            "lesson_id": les.lesson_id,
            "market_topic": les.market_topic,
            "summary": les.summary,
            "validation_status": les.validation_status,
        }
        if les.resolution_outcome:
            item["resolution_outcome"] = les.resolution_outcome
        if les.training_json:
            try:
                training = json.loads(les.training_json)
                item["instruction"] = training.get("instruction")
                item["lesson"] = training.get("lesson")
            except json.JSONDecodeError:
                pass
        out.append(item)
    return out


def _parse_call_evidence(call: PaperModelCall | None) -> dict:
    if call is None or not call.evidence_json:
        return {}
    try:
        payload = json.loads(call.evidence_json)
    except json.JSONDecodeError:
        return {}
    items = payload.get("items") or []
    evidence_ids = payload.get("evidence_ids") or []
    compact_items = []
    for it in items[:4]:
        compact_items.append(
            {
                "evidence_id": it.get("id"),
                "yes_buy_price": it.get("yes_buy_price"),
                "price_available": it.get("price_available"),
                "spread_flag": it.get("spread_flag"),
            }
        )
    return {
        "evidence_ids": evidence_ids,
        "items": compact_items,
        "hypothesis_id": payload.get("hypothesis_id"),
        "decision_id": payload.get("decision_id"),
    }


def _why_outcome(resolution: str, side: str, yes_wins: bool | None) -> str:
    side = (side or "").upper()
    if resolution == "win":
        if side == "YES":
            return "YES won on the resolved market. The paper side matched the outcome recorded from public prices."
        return "NO won on the resolved market. The paper side matched the outcome recorded from public prices."
    if resolution == "loss":
        if yes_wins is True:
            return "YES won on the resolved market. The paper NO side did not match that outcome."
        if yes_wins is False:
            return "NO won on the resolved market. The paper YES side did not match that outcome."
        return "The paper side did not match the resolved market outcome recorded in code."
    return "Outcome recorded in code."


def _default_next_step(resolution: str) -> str:
    if resolution == "win":
        return (
            "Before a similar paper entry on this topic, require the same evidence checks "
            "and confirm public prices still support the side."
        )
    return (
        "Before repeating this side on the topic, wait for stronger public price confirmation "
        "and review whether the prior reason still holds."
    )


def build_training_record(
    position: PaperPosition,
    call: PaperModelCall | None,
    resolution: str,
    realized_pnl: Decimal,
    resolved_yes_price: Decimal | None,
    yes_wins: bool | None,
    next_step: str,
) -> dict:
    evidence = _parse_call_evidence(call)
    call_action = (call.call if call else "UNKNOWN").upper()
    call_reason = call.reason if call else "No linked call."
    provider = call.provider if call else "unknown"
    context_lines = [
        f"Market: {position.market_title} ({position.market_slug}).",
        f"Topic key: {position.market_topic}.",
        f"Paper call at entry: {call_action} (paper side {position.side}).",
        f"Provider: {provider}.",
        f"What the call believed: {call_reason}",
        f"Stake (paper USDC): {position.stake_usdc}. Entry price: {position.entry_price}. "
        f"Size (shares): {position.size_shares}. Fee (paper USDC): {position.fee_usdc}.",
    ]
    if evidence.get("evidence_ids"):
        context_lines.append(f"Evidence ids at entry: {', '.join(evidence['evidence_ids'][:6])}.")
    for it in evidence.get("items") or []:
        if it.get("yes_buy_price") is not None:
            context_lines.append(
                f"Snapshot {it.get('evidence_id')}: YES buy price {it.get('yes_buy_price')}."
            )

    outcome_lines = [
        f"Resolution label: {resolution}.",
        f"Realized paper PnL (after fee in code): {realized_pnl}.",
    ]
    if resolved_yes_price is not None:
        outcome_lines.append(f"Resolved YES price from public API: {resolved_yes_price}.")
    outcome_lines.append(_why_outcome(resolution, position.side, yes_wins))

    return {
        "instruction": "Use this resolved paper bet when researching the same topic. Paper only, not a live trade.",
        "context": "\n".join(context_lines),
        "outcome": "\n".join(outcome_lines),
        "lesson": next_step.strip(),
        "resolution": resolution,
        "position_id": position.id,
        "call_id": position.call_id,
    }


def _training_summary(record: dict) -> str:
    resolution = record.get("resolution", "unknown")
    lesson = str(record.get("lesson", ""))[:160]
    return f"Paper training ({resolution}): {lesson}"


def _write_training_vault(path: Path, lesson_id: str, record: dict, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    front = {**meta, "training_record": True}
    body = [
        "# Paper training record",
        "",
        "## Instruction",
        record["instruction"],
        "",
        "## Context",
        record["context"],
        "",
        "## Outcome",
        record["outcome"],
        "",
        "## Lesson",
        record["lesson"],
        "",
        "Paper only. Facts above were filled in code from stored calls and public resolution data.",
    ]
    path.write_text(
        "---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n\n" + "\n".join(body) + "\n",
        encoding="utf-8",
    )


async def record_training_lesson(
    session: Session,
    settings: Settings,
    vault_root: Path,
    position: PaperPosition,
    call: PaperModelCall | None,
    resolution: str,
    realized_pnl: Decimal,
    resolved_yes_price: Decimal | None,
    yes_wins: bool | None,
    *,
    use_ai: bool = True,
) -> PaperLesson | None:
    if resolution not in ("win", "loss"):
        return None
    existing = session.scalar(
        select(PaperLesson).where(PaperLesson.position_id == position.id)
    )
    if existing is not None:
        return existing

    next_step = _default_next_step(resolution)
    from polyscope.research.ai.client import ResearchAIClient

    client = ResearchAIClient(settings)
    if use_ai and client.available():
        facts = {
            "resolution": resolution,
            "market_title": position.market_title,
            "market_slug": position.market_slug,
            "market_topic": position.market_topic,
            "paper_side": position.side,
            "call_action": call.call if call else None,
            "call_reason": call.reason if call else None,
            "call_provider": call.provider if call else None,
            "entry_price": str(position.entry_price),
            "stake_usdc": str(position.stake_usdc),
            "realized_pnl": str(realized_pnl),
            "resolved_yes_price": str(resolved_yes_price) if resolved_yes_price is not None else None,
            "why_outcome": _why_outcome(resolution, position.side, yes_wins),
            "evidence": _parse_call_evidence(call),
        }
        suggested = await client.suggest_training_next_step(facts)
        if suggested:
            next_step = suggested

    record = build_training_record(
        position,
        call,
        resolution,
        realized_pnl,
        resolved_yes_price,
        yes_wins,
        next_step,
    )
    ensure_vault_layout(vault_root)
    lesson_id = f"lesson-{position.id:05d}"
    path = vault_root / "lessons" / f"{lesson_id}.md"
    meta = {
        "id": lesson_id,
        "type": "lesson",
        "market_topic": position.market_topic,
        "market_slug": position.market_slug,
        "validation_status": "unverified",
        "resolution_outcome": resolution,
        "position_id": position.id,
        "call_id": position.call_id,
        "created_at": utcnow().isoformat(),
    }
    _write_training_vault(path, lesson_id, record, meta)
    summary = _training_summary(record)
    row = PaperLesson(
        lesson_id=lesson_id,
        market_topic=position.market_topic,
        market_slug=position.market_slug,
        position_id=position.id,
        call_id=position.call_id,
        summary=summary,
        validation_status="unverified",
        loss_pnl=realized_pnl,
        resolution_outcome=resolution,
        training_json=json.dumps(record),
        vault_path=str(path),
    )
    session.add(row)
    session.flush()
    return row


def infer_yes_wins_from_position(position: PaperPosition) -> bool | None:
    """Derive market YES outcome from stored resolution fields only."""
    if position.resolved_yes_price is not None:
        if position.resolved_yes_price >= Decimal("0.95"):
            return True
        if position.resolved_yes_price <= Decimal("0.05"):
            return False
    resolution = (position.resolution or "").lower()
    side = (position.side or "").upper()
    if resolution == "win":
        return side == "YES"
    if resolution == "loss":
        return side == "NO"
    return None


async def backfill_training_lessons(
    session: Session,
    settings: Settings,
    *,
    use_ai: bool = False,
) -> int:
    """Create training lessons for resolved wins/losses that have none yet."""
    vault_root = Path(settings.vault_dir)
    lesson_position_ids = set(
        session.scalars(select(PaperLesson.position_id).where(PaperLesson.position_id.is_not(None))).all()
    )
    rows = session.scalars(
        select(PaperPosition).where(
            PaperPosition.status == "resolved",
            PaperPosition.resolution.in_(("win", "loss")),
        )
    ).all()
    created = 0
    for pos in rows:
        if pos.id in lesson_position_ids:
            continue
        call = session.get(PaperModelCall, pos.call_id)
        resolution = str(pos.resolution)
        pnl = pos.realized_pnl if pos.realized_pnl is not None else Decimal("0")
        yes_wins = infer_yes_wins_from_position(pos)
        row = await record_training_lesson(
            session,
            settings,
            vault_root,
            pos,
            call,
            resolution,
            pnl,
            pos.resolved_yes_price,
            yes_wins,
            use_ai=use_ai,
        )
        if row is not None:
            created += 1
            lesson_position_ids.add(pos.id)
    return created
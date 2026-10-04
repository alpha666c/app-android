"""Lessons from paper losses for future calls."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

import yaml

from polyscope.db.models import PaperLesson, PaperPosition, PaperModelCall, utcnow
from polyscope.research.vault import write_decision_note, ensure_vault_layout
from pathlib import Path


def market_topic_key(category: str | None, market_slug: str) -> str:
    if category and category.strip():
        return category.strip().lower()
    parts = (market_slug or "").split("-")
    if len(parts) >= 2:
        return "-".join(parts[:2]).lower()
    return (market_slug or "unknown")[:48].lower()


def load_lessons_for_topic(session: Session, topic: str, limit: int = 5) -> list[PaperLesson]:
    return session.scalars(
        select(PaperLesson)
        .where(PaperLesson.market_topic == topic)
        .order_by(PaperLesson.id.desc())
        .limit(limit)
    ).all()


def lessons_to_facts(lessons: list[PaperLesson]) -> list[dict]:
    return [
        {
            "lesson_id": les.lesson_id,
            "market_topic": les.market_topic,
            "summary": les.summary,
            "validation_status": les.validation_status,
        }
        for les in lessons
    ]


def record_loss_lesson(
    session: Session,
    vault_root: Path,
    position: PaperPosition,
    call: PaperModelCall | None,
    realized_pnl: Decimal,
) -> PaperLesson:
    ensure_vault_layout(vault_root)
    lesson_id = f"lesson-{position.id:05d}"
    reason = call.reason if call else "No linked call."
    summary = (
        f"Paper {position.side} on topic {position.market_topic} lost. "
        f"Entry price {position.entry_price}. Stake {position.stake_usdc} paper USDC. "
        f"Prior reason: {reason[:240]}"
    )
    path = vault_root / "lessons" / f"{lesson_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    front = {
        "id": lesson_id,
        "type": "lesson",
        "market_topic": position.market_topic,
        "market_slug": position.market_slug,
        "validation_status": "unverified",
        "position_id": position.id,
        "call_id": position.call_id,
        "created_at": utcnow().isoformat(),
    }
    body = [
        f"# Lesson from paper loss",
        "",
        summary,
        "",
        "This note feeds the next related paper call. Not a live trade.",
    ]
    path.write_text(
        "---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n\n" + "\n".join(body) + "\n",
        encoding="utf-8",
    )
    row = PaperLesson(
        lesson_id=lesson_id,
        market_topic=position.market_topic,
        market_slug=position.market_slug,
        position_id=position.id,
        call_id=position.call_id,
        summary=summary,
        validation_status="unverified",
        loss_pnl=realized_pnl,
        vault_path=str(path),
    )
    session.add(row)
    session.flush()
    return row

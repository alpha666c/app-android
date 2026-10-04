"""One research pass: evidence vault notes plus a structured paper decision."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from polyscope.config import Settings, assert_paper_only_for_research, research_ai_skip_reason
from polyscope.db.models import PaperModelCall, utcnow
from polyscope.platform.public_client import PlatformClient
from polyscope.research.ai.client import ResearchAIClient
from polyscope.research.challenger import challenge_proposal, normalize_action
from polyscope.research.evidence import build_market_evidence, evidence_is_thin
from polyscope.research.markets import fetch_open_markets
from polyscope.research.paper_lessons import lessons_to_facts, load_lessons_for_topic, market_topic_key
from polyscope.research.paper_labels import compute_paper_tags_and_labels, tags_payload_json
from polyscope.research.vault import (
    _utc_iso,
    write_decision_note,
    write_event_snapshot,
    write_hypothesis_note,
)

logger = logging.getLogger(__name__)

PAPER_ACTIONS = frozenset({"BUY", "SELL", "WAIT", "REJECT"})


def _next_ids(session: Session, when: datetime) -> tuple[str, str]:
    count = session.scalar(select(func.count()).select_from(PaperModelCall)) or 0
    seq = count + 1
    stamp = when.strftime("%Y%m%d")
    return f"hypothesis-{stamp}-{seq:04d}", f"decision-{stamp}-{seq:04d}"


def _pick_featured_market(markets: list[dict], session: Session) -> dict:
    if not markets:
        return {}
    prior = session.scalar(select(func.count()).select_from(PaperModelCall)) or 0
    return markets[prior % len(markets)]


def _attach_tags(row: PaperModelCall, action: str, provider: str, reason: str, has_evidence: bool) -> None:
    tags, labels = compute_paper_tags_and_labels(action, provider, reason, has_evidence)
    row.tags_json = tags_payload_json(tags, labels)


async def run_paper_research_pass(
    session: Session,
    settings: Settings,
    platform: PlatformClient,
) -> PaperModelCall:
    assert_paper_only_for_research(settings)
    when = datetime.now(timezone.utc)
    vault_root = Path(settings.vault_dir)
    hypothesis_id, decision_id = _next_ids(session, when)

    markets = await fetch_open_markets(platform, limit=8)
    if not markets:
        return _persist_wait(
            session,
            settings,
            vault_root,
            hypothesis_id,
            decision_id,
            when,
            market_slug="none",
            market_title="No open markets",
            reason="Could not load open markets from public API.",
            evidence_ids=[],
            contradiction_ids=[],
            provider="rules_fallback",
        )

    featured = _pick_featured_market(markets, session)
    topic = market_topic_key(featured.get("category"), featured.get("slug", ""))
    prior_lessons = load_lessons_for_topic(session, topic, limit=5)
    evidence = build_market_evidence(featured, when)
    write_event_snapshot(
        vault_root,
        evidence.evidence_id,
        {
            "type": "market_snapshot",
            "asset": evidence.market_slug,
            "market_title": evidence.market_title,
            "observed_at": evidence.observed_at,
            "yes_buy_price": str(evidence.yes_buy_price) if evidence.yes_buy_price else None,
            "price_available": evidence.price_available,
            "spread_flag": evidence.spread_flag,
            "status": "recorded",
        },
        evidence.snapshot_lines,
    )

    thin, thin_reason = evidence_is_thin(evidence, peer_count=len(markets) - 1)
    peer_ids = []
    for m in markets[1:3]:
        peer = build_market_evidence(m, when)
        peer_ids.append(peer.evidence_id)
        write_event_snapshot(
            vault_root,
            peer.evidence_id,
            {
                "type": "market_snapshot",
                "asset": peer.market_slug,
                "observed_at": peer.observed_at,
                "status": "recorded",
            },
            peer.snapshot_lines,
        )

    evidence_ids = [evidence.evidence_id] + peer_ids
    contradiction_ids: list[str] = []

    write_hypothesis_note(
        vault_root,
        hypothesis_id,
        {
            "type": "hypothesis",
            "asset": evidence.market_slug,
            "market_title": evidence.market_title,
            "status": "monitoring",
            "created_at": _utc_iso(when),
            "horizon": "paper_slice",
            "strategy_version": "polymarket-observe-v1",
            "evidence_ids": evidence_ids,
            "contradiction_ids": contradiction_ids,
            "mode": "paper",
        },
        [
            f"# Hypothesis for {evidence.market_title}",
            "",
            "Research slice only. No live execution.",
            "",
            "## Claim",
            "Observe whether public market data supports a paper BUY or SELL on YES.",
            "",
            "## Supporting evidence",
            *[f"- [[{eid}]]" for eid in evidence_ids],
            "",
            "## Invalidation",
            "Missing or stale public price data blocks entry.",
        ],
    )

    client = ResearchAIClient(settings)
    if thin:
        action = "WAIT"
        reason = f"Evidence thin: {thin_reason}"
        provider = "rules_fallback"
    elif not client.available():
        action = "WAIT"
        reason = research_ai_skip_reason(settings)
        provider = "rules_fallback"
    else:
        suggestion = await client.suggest_paper_decision(
            {
                "featured_evidence_id": evidence.evidence_id,
                "market_title": evidence.market_title,
                "yes_buy_price": str(evidence.yes_buy_price) if evidence.yes_buy_price else None,
                "spread_flag": evidence.spread_flag,
                "peer_market_titles": [m.get("title") for m in markets[1:4]],
                "prior_lessons": lessons_to_facts(prior_lessons),
            }
        )
        action = normalize_action(suggestion.action)
        reason = suggestion.reason
        provider = suggestion.provider

    action, reason, extra_contra = challenge_proposal(
        action, reason, evidence, contradiction_ids, settings
    )
    contradiction_ids = list(dict.fromkeys(contradiction_ids + extra_contra))
    if action not in PAPER_ACTIONS:
        action = "WAIT"

    tag_list, label_list = compute_paper_tags_and_labels(
        action, provider, reason, has_evidence=bool(evidence_ids)
    )

    decision_path = write_decision_note(
        vault_root,
        decision_id,
        {
            "type": "decision",
            "action": action,
            "asset": evidence.market_slug,
            "market_title": evidence.market_title,
            "created_at": _utc_iso(when),
            "hypothesis_id": hypothesis_id,
            "evidence_ids": evidence_ids,
            "contradiction_ids": contradiction_ids,
            "provider": provider,
            "mode": "paper",
            "status": "recorded",
            "expires_at": _utc_iso(when),
            "tags": tag_list,
            "labels": label_list,
        },
        [
            f"# Paper decision: {action}",
            "",
            f"**Reason:** {reason}",
            "",
            "## Evidence",
            *[f"- [[{eid}]]" for eid in evidence_ids],
            "",
            "## Contradictions",
            *([f"- [[{c}]]" for c in contradiction_ids] or ["- none"]),
            "",
            f"Linked hypothesis: [[{hypothesis_id}]]",
        ],
    )

    rel_path = str(decision_path.relative_to(vault_root.parent) if vault_root.is_absolute() else decision_path)
    try:
        rel_path = str(decision_path.relative_to(Path.cwd()))
    except ValueError:
        rel_path = str(decision_path)

    item_dicts = [evidence.to_public_dict()]
    for m in markets[1:3]:
        item_dicts.append(build_market_evidence(m, when).to_public_dict())
    evidence_payload = {
        "evidence_ids": evidence_ids,
        "contradiction_ids": contradiction_ids,
        "hypothesis_id": hypothesis_id,
        "decision_id": decision_id,
        "items": item_dicts,
    }

    row = PaperModelCall(
        market_slug=evidence.market_slug,
        market_title=evidence.market_title,
        condition_id=evidence.condition_id,
        call=action,
        reason=reason,
        provider=provider,
        mode="paper",
        outcome=None,
        hypothesis_id=hypothesis_id,
        decision_id=decision_id,
        evidence_json=json.dumps(evidence_payload),
        vault_decision_path=rel_path,
        created_at=utcnow(),
    )
    _attach_tags(row, action, provider, reason, has_evidence=bool(evidence_ids))
    session.add(row)
    session.flush()
    return row


def _persist_wait(
    session: Session,
    settings: Settings,
    vault_root: Path,
    hypothesis_id: str,
    decision_id: str,
    when: datetime,
    market_slug: str,
    market_title: str,
    reason: str,
    evidence_ids: list[str],
    contradiction_ids: list[str],
    provider: str,
) -> PaperModelCall:
    write_decision_note(
        vault_root,
        decision_id,
        {
            "type": "decision",
            "action": "WAIT",
            "asset": market_slug,
            "created_at": _utc_iso(when),
            "hypothesis_id": hypothesis_id,
            "evidence_ids": evidence_ids,
            "mode": "paper",
            "status": "recorded",
        },
        [f"# Paper decision: WAIT", "", reason],
    )
    row = PaperModelCall(
        market_slug=market_slug,
        market_title=market_title,
        condition_id=None,
        call="WAIT",
        reason=reason,
        provider=provider,
        mode="paper",
        outcome=None,
        hypothesis_id=hypothesis_id,
        decision_id=decision_id,
        evidence_json=json.dumps({"evidence_ids": evidence_ids, "contradiction_ids": contradiction_ids}),
        vault_decision_path=str(vault_root / "decisions" / f"{decision_id}.md"),
        created_at=utcnow(),
    )
    _attach_tags(row, "WAIT", provider, reason, has_evidence=bool(evidence_ids))
    session.add(row)
    session.flush()
    return row

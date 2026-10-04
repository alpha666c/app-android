"""Tags and labels for paper calls (code-defined, not model-invented)."""

from __future__ import annotations

import json
from typing import Any

PAPER_CALL_ACTIONS = frozenset({"BUY", "SELL", "WAIT", "REJECT"})


def compute_paper_tags_and_labels(
    action: str,
    provider: str,
    reason: str,
    has_evidence: bool,
) -> tuple[list[str], list[str]]:
    action = (action or "WAIT").upper()
    tags = ["paper", "polymarket", action.lower()]
    labels = ["Paper only"]

    if action == "WAIT":
        tags.append("abstain")
        labels.append("Abstain")
        if "Missing server env" in reason or "AI_GATEWAY_API_KEY" in reason:
            tags.append("needs-model-key")
            labels.append("Model key not set")
        elif reason.startswith("Evidence thin"):
            tags.append("thin-evidence")
            labels.append("Thin evidence")
        elif provider == "rules_fallback":
            tags.append("rules-fallback")
            labels.append("Rules fallback")
    else:
        tags.append("actionable")
        labels.append("Review this call")
        if action == "BUY":
            labels.append("Paper BUY")
        elif action == "SELL":
            labels.append("Paper SELL")
        elif action == "REJECT":
            labels.append("Paper REJECT")

    if has_evidence:
        tags.append("has-evidence")
        labels.append("Evidence on file")

    if provider == "deterministic_rule":
        tags.append("not-a-model")
        labels.append("Not a model call")
    elif provider == "openrouter":
        tags.append("openrouter")
        labels.append("OpenRouter model")
    elif provider and provider != "rules_fallback":
        tags.append(f"provider-{provider}")
        labels.append(f"Provider {provider}")

    # dedupe preserving order
    tags = list(dict.fromkeys(tags))
    labels = list(dict.fromkeys(labels))
    return tags, labels


def tags_payload_json(tags: list[str], labels: list[str]) -> str:
    return json.dumps({"tags": tags, "labels": labels})


def parse_tags_payload(raw: str | None) -> tuple[list[str], list[str]]:
    if not raw:
        return [], []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            tags = list(data.get("tags") or [])
            labels = list(data.get("labels") or [])
            return tags, labels
    except json.JSONDecodeError:
        pass
    return [], []


def call_is_alert(action: str) -> bool:
    return (action or "WAIT").upper() != "WAIT"


def paper_call_to_api(row: Any) -> dict[str, Any]:
    tags, labels = parse_tags_payload(getattr(row, "tags_json", None))
    action = row.call
    return {
        "paper": True,
        "id": row.id,
        "market": row.market_slug,
        "market_title": row.market_title,
        "call": action,
        "reason": row.reason,
        "provider": row.provider,
        "outcome": row.outcome,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "tags": tags,
        "labels": labels,
        "alert": call_is_alert(action),
        "decision_id": row.decision_id,
        "vault_decision_path": row.vault_decision_path,
        "hypothesis_id": row.hypothesis_id,
        "evidence": json.loads(row.evidence_json) if row.evidence_json else None,
    }

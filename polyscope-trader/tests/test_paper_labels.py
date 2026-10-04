"""Paper tags and loop behavior."""

from __future__ import annotations

from polyscope.research.paper_labels import (
    call_is_alert,
    compute_paper_tags_and_labels,
    tags_payload_json,
)


def test_wait_abstain_tags():
    tags, labels = compute_paper_tags_and_labels(
        "WAIT",
        "rules_fallback",
        "Paper only. Research model skipped. Missing server env: AI_GATEWAY_API_KEY.",
        True,
    )
    assert "abstain" in tags
    assert "needs-model-key" in tags
    assert call_is_alert("WAIT") is False
    assert call_is_alert("BUY") is True


def test_actionable_alert_tags():
    tags, labels = compute_paper_tags_and_labels("BUY", "openai_compatible", "Setup ok.", True)
    assert "actionable" in tags
    assert "Paper BUY" in labels

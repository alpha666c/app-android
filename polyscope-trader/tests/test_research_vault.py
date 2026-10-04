"""Research vault and paper pass tests."""

from __future__ import annotations

from pathlib import Path

from polyscope.config import load_settings, research_ai_skip_reason
from polyscope.research.challenger import normalize_action
from polyscope.research.evidence import build_market_evidence, evidence_is_thin
from polyscope.research.vault import write_decision_note


def test_normalize_actions():
    assert normalize_action("BUY_YES") == "BUY"
    assert normalize_action("REJECT") == "REJECT"


def test_thin_evidence_without_price():
    ev = build_market_evidence({"slug": "x", "title": "Test?", "yes_buy_price": None})
    thin, _ = evidence_is_thin(ev, peer_count=3)
    assert thin is True


def test_vault_decision_note_yaml(tmp_path):
    path = write_decision_note(
        tmp_path,
        "decision-0001",
        {"action": "WAIT", "asset": "test-market", "status": "recorded"},
        ["# Paper decision: WAIT", "", "Abstained."],
    )
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "decision-0001" in text
    assert "action: WAIT" in text


def test_refresh_writes_wait_without_model_key(monkeypatch, tmp_path):
    from polyscope.api import main as api_main
    from fastapi.testclient import TestClient

    vault = tmp_path / "vault"
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("POLYSCOPE_DB_PATH", str(tmp_path / "r.db"))
    monkeypatch.setenv("VAULT_DIR", str(vault))
    monkeypatch.setenv("VIKTOR_PUBLIC_SLUG", "slug-test")
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    api_main.settings = None
    api_main.SessionLocal = None
    app = api_main.create_app()
    client = TestClient(app)
    resp = client.post("/p/slug-test/refresh")
    assert resp.status_code == 200
    body = resp.json()
    assert body["call"] in ("WAIT", "REJECT", "BUY", "SELL")
    assert "tags" in body
    assert body["alert"] is (body["call"] != "WAIT")
    decisions = list((vault / "decisions").glob("*.md"))
    assert len(decisions) >= 1

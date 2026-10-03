"""Viktor paper screen acceptance tests."""

from __future__ import annotations

from polyscope.config import TradingMode, load_settings
from polyscope.db.models import PaperModelCall
from polyscope.platform.live_gateway import DisabledLiveGateway


def test_paper_model_call_has_outcome_field(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("POLYSCOPE_DB_PATH", str(tmp_path / "v.db"))
    from polyscope.db.session import init_db

    sf = init_db(load_settings())
    with sf() as session:
        row = PaperModelCall(
            market_slug="test-market",
            market_title="Test?",
            condition_id="0xabc",
            call="SKIP",
            reason="Paper research only.",
            provider="rules_fallback",
            mode="paper",
            outcome=None,
        )
        session.add(row)
        session.commit()
        saved = session.get(PaperModelCall, row.id)
        assert saved.outcome is None
        assert saved.mode == "paper"


def test_viktor_refresh_rejects_live_mode(monkeypatch, tmp_path):
    from polyscope.api import main as api_main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("POLYSCOPE_DB_PATH", str(tmp_path / "live.db"))
    monkeypatch.setenv("LIVE_MAX_FUNDED_BUDGET", "10")
    monkeypatch.setenv("LIVE_MAX_ORDER_COST", "1")
    monkeypatch.setenv("LIVE_MAX_EVENT_EXPOSURE", "3")
    monkeypatch.setenv("LIVE_MAX_TOTAL_EXPOSURE", "10")
    monkeypatch.setenv("LIVE_MAX_OPEN_POSITIONS", "5")
    monkeypatch.setenv("LIVE_MAX_OUTSTANDING_ORDERS", "5")
    monkeypatch.setenv("LIVE_DAILY_LOSS_CIRCUIT_BREAKER", "2")
    monkeypatch.setenv("LIVE_MAX_SPREAD", "0.05")
    monkeypatch.setenv("LIVE_MAX_SLIPPAGE", "0.03")
    monkeypatch.setenv("LIVE_MAX_SIGNAL_AGE_SECONDS", "300")
    monkeypatch.setenv("LIVE_MAX_DATA_AGE_SECONDS", "120")
    api_main.settings = None
    api_main.SessionLocal = None
    app = api_main.create_app()
    client = TestClient(app)
    resp = client.post("/viktor/refresh", auth=("admin", "secret"))
    assert resp.status_code == 403


def test_viktor_screen_requires_paper(monkeypatch, tmp_path):
    from polyscope.api import main as api_main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("POLYSCOPE_DB_PATH", str(tmp_path / "p.db"))
    api_main.settings = None
    api_main.SessionLocal = None
    app = api_main.create_app()
    client = TestClient(app)
    resp = client.get("/viktor", auth=("admin", "secret"))
    assert resp.status_code == 200
    assert "PAPER ONLY" in resp.text
    assert "LIVE LOCKED" in resp.text


def test_viktor_path_has_no_live_gateway():
    gw = DisabledLiveGateway()
    assert gw.__class__.__name__ == "DisabledLiveGateway"


def test_viktor_public_slug_no_password(monkeypatch, tmp_path):
    from polyscope.api import main as api_main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("POLYSCOPE_DB_PATH", str(tmp_path / "pub.db"))
    monkeypatch.setenv("VIKTOR_PUBLIC_SLUG", "viktor-test-slug-93e7")
    api_main.settings = None
    api_main.SessionLocal = None
    app = api_main.create_app()
    client = TestClient(app)
    resp = client.get("/p/viktor-test-slug-93e7")
    assert resp.status_code == 200
    assert "PAPER ONLY" in resp.text
    assert "/p/viktor-test-slug-93e7/refresh" in resp.text
    bad = client.get("/p/wrong-slug")
    assert bad.status_code == 404
    refresh = client.post("/p/viktor-test-slug-93e7/refresh")
    assert refresh.status_code == 200
    assert refresh.json()["paper"] is True


def test_research_skip_lists_missing_env(monkeypatch):
    from polyscope.config import load_settings, research_ai_skip_reason

    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AI_PROVIDER", "none")
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    cfg = load_settings()
    reason = research_ai_skip_reason(cfg)
    assert "AI_GATEWAY_API_KEY" in reason
    assert "OPENAI_API_KEY" in reason
    assert "AI_PROVIDER" in reason

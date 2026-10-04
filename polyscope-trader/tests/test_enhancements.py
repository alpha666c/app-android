"""Tests for roadmap enhancements."""

from __future__ import annotations

from decimal import Decimal

import pytest

from polyscope.config import AutomationTier, load_settings
from polyscope.risk.confidence import compute_readiness, tier_allows_auto_execute
from polyscope.strategy.devils_advocate import build_devils_advocate


def test_metadata_missing_rejects_fee(monkeypatch, tmp_path):
    from polyscope.execution.fees import taker_fee_usdc

    assert taker_fee_usdc(Decimal("1"), Decimal("0.5"), category=None) is None


def test_readiness_score_bounded(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "x")
    monkeypatch.setenv("POLYSCOPE_DB_PATH", str(tmp_path / "r.db"))
    settings = load_settings()
    from polyscope.db.session import init_db

    sf = init_db(settings)
    with sf() as session:
        from polyscope.db.session import get_system_state

        state = get_system_state(session)
        state.data_stale = False
        state.geoblock_blocked = False
        session.commit()
        result = compute_readiness(session, settings)
        assert 0 <= result.score <= 100


def test_tier_observe_blocks_auto():
    from polyscope.config import Settings, TradingMode, RiskLimits
    from decimal import Decimal

    settings = Settings(
        trading_mode=TradingMode.PAPER,
        db_path="x",
        host="127.0.0.1",
        port=8080,
        dashboard_user="a",
        dashboard_password="b",
        live_arm_token=None,
        live_armed=False,
        polymarket_private_key=None,
        risk=RiskLimits(
            Decimal(100),
            Decimal(1),
            Decimal(3),
            Decimal(10),
            5,
            10,
            Decimal(2),
            Decimal("0.05"),
            Decimal("0.03"),
            300,
            120,
        ),
        cohort_max_rank=50,
        cohort_min_volume=Decimal(1000),
        cohort_leaderboard_window="day",
        signal_price_tolerance=Decimal("0.02"),
        execution_latency_ms=500,
        poll_interval_seconds=30,
        automation_tier=AutomationTier.OBSERVE,
        flow_consensus_min_wallets=1,
        use_stream_ingest=False,
        ai_provider="none",
        ai_gateway_api_key=None,
        ai_api_base="https://api.openai.com/v1",
        ai_model="gpt-4o-mini",
        live_scaled_unlocked=False,
        micro_max_order_cost=None,
        report_dir="evidence/reports",
        viktor_view_token=None,
        viktor_public_slug=None,
        vault_dir="vault",
        paper_bot_interval_seconds=120,
    )
    assert tier_allows_auto_execute(settings, AutomationTier.OBSERVE) is False


def test_devils_advocate_lists_reasons():
    text = build_devils_advocate(
        consensus_wallet_count=1,
        min_consensus=2,
        spread=Decimal("0.1"),
        max_spread=Decimal("0.05"),
        history_incomplete=True,
        single_wallet=True,
    )
    assert "consensus" in text.lower() or "wallet" in text.lower()

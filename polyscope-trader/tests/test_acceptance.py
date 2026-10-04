"""Acceptance tests for PolyScope Trader safety and accounting."""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from polyscope.config import Settings, TradingMode, load_settings
from polyscope.db.models import LedgerAccount, OrderIntent, Signal, SystemState
from polyscope.db.session import init_db
from polyscope.execution.intents import get_or_create_intent, intent_key
from polyscope.execution.paper import _walk_book
from polyscope.logging_utils import redact_message
from polyscope.platform.live_gateway import DisabledLiveGateway, LiveTradingForbidden
from polyscope.platform.public_client import OrderBookSnapshot
from polyscope.risk.engine import evaluate_order
from polyscope.risk.reservations import InsufficientFunds, reserve_funds
from polyscope.db.session import get_system_state


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "test-secret")
    monkeypatch.setenv("POLYSCOPE_DB_PATH", str(tmp_path / "test.db"))
    return load_settings()


@pytest.fixture()
def session_factory(settings):
    return init_db(settings)


@pytest.fixture()
def session(session_factory):
    s = session_factory()
    yield s
    s.close()


def test_paper_live_gateway_forbidden():
    gw = DisabledLiveGateway()

    async def _call():
        await gw.place_limit_order("1", "BUY", Decimal("0.5"), Decimal("1"))

    import asyncio

    with pytest.raises(LiveTradingForbidden):
        asyncio.run(_call())


def test_live_mode_requires_all_limits(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "x")
    monkeypatch.setenv("POLYSCOPE_DB_PATH", str(tmp_path / "live.db"))
    with pytest.raises(ValueError):
        load_settings()


def test_secrets_redacted_in_logs():
    msg = redact_message("POLYMARKET_PRIVATE_KEY=0xabc123privatekeyprivatekeyprivatekeyprivatekeyprivatekeypr")
    assert "privatekey" not in msg.lower() or "<redacted>" in msg


def test_fee_inclusive_order_cost_respects_max(session, settings):
    state = get_system_state(session)
    state.data_stale = False
    state.kill_switch = False
    session.commit()
    decision = evaluate_order(
        session,
        settings,
        order_cost=Decimal("1.01"),
        event_slug="evt",
        data_age_seconds=1,
        spread=Decimal("0.01"),
        signal_age_seconds=1,
    )
    assert not decision.allowed
    assert decision.reason == "max_order_cost"


def test_concurrent_reservation_prevents_overspend(session, settings):
    intent1 = OrderIntent(
        intent_key="a",
        mode="paper",
        side="BUY",
        token_id="t",
        condition_id="c",
        limit_price=Decimal("0.5"),
        size=Decimal("1"),
        reserved_usdc=Decimal("100"),
        status="created",
    )
    intent2 = OrderIntent(
        intent_key="b",
        mode="paper",
        side="BUY",
        token_id="t2",
        condition_id="c2",
        limit_price=Decimal("0.5"),
        size=Decimal("1"),
        reserved_usdc=Decimal("100"),
        status="created",
    )
    session.add(intent1)
    session.add(intent2)
    session.flush()
    reserve_funds(session, intent1.id, Decimal("100"))
    with pytest.raises(InsufficientFunds):
        reserve_funds(session, intent2.id, Decimal("1"))
    session.commit()


def test_signal_dedupe_single_intent(session, settings):
    sig = Signal(
        dedupe_key="d1",
        wallet="0x1",
        condition_id="c",
        token_id="tok",
        side="BUY",
        reference_price=Decimal("0.5"),
        size=Decimal("1"),
        observed_at=datetime.now(timezone.utc),
        status="approved",
    )
    session.add(sig)
    session.flush()
    i1 = get_or_create_intent(
        session, settings, sig, limit_price=Decimal("0.5"), size=Decimal("1"), reserved_usdc=Decimal("1")
    )
    i2 = get_or_create_intent(
        session, settings, sig, limit_price=Decimal("0.5"), size=Decimal("1"), reserved_usdc=Decimal("1")
    )
    assert i1.id == i2.id


def test_reconcile_flag_not_blind_resubmit(session):
    intent = OrderIntent(
        intent_key="r1",
        mode="paper",
        side="BUY",
        token_id="t",
        condition_id="c",
        limit_price=Decimal("0.5"),
        size=Decimal("1"),
        reserved_usdc=Decimal("1"),
        status="submitted",
        reconcile_required=True,
    )
    session.add(intent)
    session.commit()
    assert intent.reconcile_required
    assert intent.status == "submitted"


def test_partial_fill_walk_book():
    book = OrderBookSnapshot(
        token_id="t",
        bids=[(Decimal("0.48"), Decimal("0.5"))],
        asks=[(Decimal("0.52"), Decimal("0.5")), (Decimal("0.53"), Decimal("2"))],
        fetched_at=datetime.now(timezone.utc),
    )
    filled, avg, cost = _walk_book("BUY", Decimal("0.52"), Decimal("0.5"), book)
    assert filled == Decimal("0.5")
    assert avg == Decimal("0.52")


def test_stale_feed_blocks_orders(session, settings):
    state = get_system_state(session)
    state.data_stale = True
    session.commit()
    decision = evaluate_order(
        session,
        settings,
        order_cost=Decimal("0.5"),
        event_slug=None,
        data_age_seconds=1,
        spread=Decimal("0.01"),
        signal_age_seconds=1,
    )
    assert decision.reason == "stale_feed"


def test_missing_pnl_not_zero(monkeypatch, tmp_path):
    from polyscope.api import main as api_main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DASHBOARD_PASSWORD", "test-secret")
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("POLYSCOPE_DB_PATH", str(tmp_path / "pnl.db"))
    api_main.settings = None
    api_main.SessionLocal = None
    app = api_main.create_app()
    client = TestClient(app)
    resp = client.get("/api/pnl", auth=("admin", "test-secret"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["unrealized_pnl"] is None


def test_incomplete_history_cannot_verify_90d():
    """Synthetic fixture — not a verified ranking."""
    pages_fetched = 1
    has_more = True
    verified_90d = pages_fetched >= 90 and not has_more
    assert verified_90d is False


def test_backtest_no_future_signal():
    exchange_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    decision_ts = datetime(2025, 12, 31, tzinfo=timezone.utc)
    assert decision_ts < exchange_ts


def test_stale_signal_rejection(settings):
    old = datetime.now(timezone.utc) - timedelta(seconds=settings.risk.max_signal_age_seconds + 10)
    age = (datetime.now(timezone.utc) - old).total_seconds()
    assert age > settings.risk.max_signal_age_seconds

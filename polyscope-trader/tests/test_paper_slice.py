"""Paper bet slice: sizing, one bet per call, lessons as_of, scoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from polyscope.config import load_settings
from polyscope.db.models import PaperLesson, PaperModelCall, PaperPosition
from polyscope.research.paper_bot import open_paper_position_from_call
from polyscope.research.paper_labels import compute_paper_tags_and_labels
from polyscope.research.paper_lessons import load_lessons_for_topic, record_loss_lesson
from polyscope.research.paper_resolution import score_paper_position
from polyscope.research.paper_rules import deterministic_paper_action
from polyscope.research.paper_sizing import compute_paper_bet
from polyscope.research.evidence import build_market_evidence


@pytest.fixture
def paper_db(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("POLYSCOPE_DB_PATH", str(tmp_path / "slice.db"))
    monkeypatch.setenv("VAULT_DIR", str(tmp_path / "vault"))
    from polyscope.db.session import init_db

    return init_db(load_settings())


def test_compute_paper_bet_includes_fee(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    cfg = load_settings()
    bet = compute_paper_bet(cfg, Decimal("0.55"), "politics")
    assert bet is not None
    assert bet.stake_usdc > 0
    assert bet.size_shares > 0
    assert bet.fee_usdc >= 0


def test_one_bet_per_call(paper_db):
    from polyscope.config import load_settings

    cfg = load_settings()
    with paper_db() as session:
        call = PaperModelCall(
            market_slug="m-one",
            market_title="One bet?",
            condition_id="0x1",
            call="BUY",
            reason="test",
            provider="deterministic_rule",
            mode="paper",
        )
        session.add(call)
        session.flush()
        featured = {"slug": "m-one", "yes_buy_price": "0.60", "category": "politics"}
        p1 = open_paper_position_from_call(session, cfg, call, featured)
        p2 = open_paper_position_from_call(session, cfg, call, featured)
        assert p1 is not None
        assert p2 is not None
        assert p1.id == p2.id
        from sqlalchemy import func, select

        count = session.scalar(
            select(func.count()).select_from(PaperPosition).where(PaperPosition.call_id == call.id)
        )
        assert count == 1


def test_wait_call_does_not_open_bet(paper_db):
    cfg = load_settings()
    with paper_db() as session:
        call = PaperModelCall(
            market_slug="m-wait",
            market_title="Wait?",
            condition_id="0x2",
            call="WAIT",
            reason="abstain",
            provider="rules_fallback",
            mode="paper",
        )
        session.add(call)
        session.flush()
        pos = open_paper_position_from_call(
            session, cfg, call, {"slug": "m-wait", "yes_buy_price": "0.50"}
        )
        assert pos is None


def test_lessons_as_of_excludes_future(paper_db, tmp_path):
    cfg = load_settings()
    vault = tmp_path / "vault"
    vault.mkdir()
    with paper_db() as session:
        call = PaperModelCall(
            market_slug="m-lesson",
            market_title="Lesson?",
            call="BUY",
            reason="r",
            provider="x",
            mode="paper",
        )
        session.add(call)
        session.flush()
        pos = PaperPosition(
            call_id=call.id,
            status="resolved",
            side="YES",
            market_slug="m-lesson",
            market_title="Lesson?",
            market_topic="politics",
            stake_usdc=Decimal("1"),
            entry_price=Decimal("0.5"),
            size_shares=Decimal("2"),
            fee_usdc=Decimal("0"),
            resolution="loss",
        )
        session.add(pos)
        session.flush()
        old = PaperLesson(
            lesson_id="lesson-old",
            market_topic="politics",
            market_slug="m-lesson",
            position_id=pos.id,
            call_id=call.id,
            summary="old lesson",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        new = PaperLesson(
            lesson_id="lesson-new",
            market_topic="politics",
            market_slug="m-lesson",
            position_id=pos.id,
            call_id=call.id,
            summary="new lesson",
            created_at=datetime.now(timezone.utc),
        )
        session.add_all([old, new])
        session.commit()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        loaded = load_lessons_for_topic(session, "politics", limit=10, as_of=cutoff)
        ids = {les.lesson_id for les in loaded}
        assert "lesson-old" in ids
        assert "lesson-new" not in ids


def test_loss_lesson_idempotent(paper_db, tmp_path):
    vault = tmp_path / "vault2"
    vault.mkdir()
    with paper_db() as session:
        call = PaperModelCall(
            market_slug="m-loss",
            market_title="Loss?",
            call="BUY",
            reason="r",
            provider="x",
            mode="paper",
        )
        session.add(call)
        session.flush()
        pos = PaperPosition(
            call_id=call.id,
            status="resolved",
            side="YES",
            market_slug="m-loss",
            market_title="Loss?",
            market_topic="politics",
            stake_usdc=Decimal("1"),
            entry_price=Decimal("0.5"),
            size_shares=Decimal("2"),
            fee_usdc=Decimal("0.01"),
        )
        session.add(pos)
        session.flush()
        l1 = record_loss_lesson(session, vault, pos, call, Decimal("-1"))
        l2 = record_loss_lesson(session, vault, pos, call, Decimal("-1"))
        assert l1 is not None
        assert l2 is not None
        assert l1.id == l2.id


def test_score_applies_fee():
    win_pnl = score_paper_position("YES", Decimal("0.5"), Decimal("1"), True, Decimal("0.02"))
    assert win_pnl[0] == "win"
    loss_pnl = score_paper_position("YES", Decimal("0.5"), Decimal("1"), False, Decimal("0.02"))
    assert loss_pnl[0] == "loss"
    assert loss_pnl[1] == Decimal("-1.02")


def test_deterministic_rule_not_model_label():
    ev = build_market_evidence(
        {"slug": "x", "title": "T", "yes_buy_price": "0.60", "category": "politics"}
    )
    action, reason = deterministic_paper_action(ev)
    assert action == "BUY"
    tags, labels = compute_paper_tags_and_labels(action, "deterministic_rule", reason, True)
    assert "not-a-model" in tags
    assert "Not a model call" in labels


def test_app_payload_has_scoreboard_and_open_bets(monkeypatch, tmp_path):
    from polyscope.api import main as api_main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("TRADING_MODE", "paper")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("POLYSCOPE_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("VIKTOR_PUBLIC_SLUG", "viktor-slice-93e7")
    api_main.settings = None
    api_main.SessionLocal = None
    app = api_main.create_app()
    client = TestClient(app)
    body = client.get("/p/viktor-slice-93e7/api/app").json()
    assert "scoreboard" in body
    assert "open_bets" in body
    assert "lessons" in body
    assert body["scoreboard"]["open_bets"] == body["scoreboard"]["open_positions"]

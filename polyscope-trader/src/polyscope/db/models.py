"""SQLAlchemy models for durable local state."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class SystemState(Base):
    __tablename__ = "system_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    live_session_armed: Mapped[bool] = mapped_column(Boolean, default=False)
    last_reconciliation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_public_data_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    geoblock_blocked: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    geoblock_country: Mapped[str | None] = mapped_column(String(8))
    data_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    executor_holder: Mapped[str | None] = mapped_column(String(64))
    executor_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    day_baseline_realized: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    day_baseline_unrealized: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    day_boundary: Mapped[str | None] = mapped_column(String(16))
    automation_tier: Mapped[int] = mapped_column(Integer, default=1)
    last_order_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    live_stream_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    readiness_score: Mapped[int | None] = mapped_column(Integer)


class LedgerAccount(Base):
    __tablename__ = "ledger_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))


class CohortWallet(Base):
    __tablename__ = "cohort_wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wallet: Mapped[str] = mapped_column(String(66), index=True)
    rank: Mapped[int | None] = mapped_column(Integer)
    window: Mapped[str] = mapped_column(String(32))
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    included: Mapped[bool] = mapped_column(Boolean, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(128))
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    history_incomplete: Mapped[bool] = mapped_column(Boolean, default=False)


class WalletActivityCursor(Base):
    __tablename__ = "wallet_activity_cursors"

    wallet: Mapped[str] = mapped_column(String(66), primary_key=True)
    last_seen_tx_id: Mapped[str | None] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    wallet: Mapped[str] = mapped_column(String(66))
    condition_id: Mapped[str] = mapped_column(String(128))
    token_id: Mapped[str] = mapped_column(String(128))
    event_slug: Mapped[str | None] = mapped_column(String(256))
    outcome: Mapped[str | None] = mapped_column(String(64))
    side: Mapped[str] = mapped_column(String(8))
    reference_price: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    size: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    exchange_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    reject_reason: Mapped[str | None] = mapped_column(String(64))
    opposing_flow: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    round_trip_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    best_bid_at_signal: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    best_ask_at_signal: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    spread_at_signal: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    market_category: Mapped[str | None] = mapped_column(String(64))
    consensus_wallet_count: Mapped[int] = mapped_column(Integer, default=1)
    devils_advocate: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    intents: Mapped[list[OrderIntent]] = relationship(back_populates="signal")


class OrderIntent(Base):
    __tablename__ = "order_intents"
    __table_args__ = (UniqueConstraint("intent_key", name="uq_intent_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intent_key: Mapped[str] = mapped_column(String(256))
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"))
    mode: Mapped[str] = mapped_column(String(16))
    side: Mapped[str] = mapped_column(String(8))
    token_id: Mapped[str] = mapped_column(String(128))
    condition_id: Mapped[str] = mapped_column(String(128))
    limit_price: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    size: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    reserved_usdc: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    status: Mapped[str] = mapped_column(String(32), default="created")
    external_order_id: Mapped[str | None] = mapped_column(String(128))
    reconcile_required: Mapped[bool] = mapped_column(Boolean, default=False)
    simulation_limited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    signal: Mapped[Signal | None] = relationship(back_populates="intents")
    fills: Mapped[list[Fill]] = relationship(back_populates="intent")


class Fill(Base):
    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intent_id: Mapped[int] = mapped_column(ForeignKey("order_intents.id"))
    price: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    size: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    fee_usdc: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    intent: Mapped[OrderIntent] = relationship(back_populates="fills")


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("token_id", name="uq_position_token"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_id: Mapped[str] = mapped_column(String(128))
    condition_id: Mapped[str] = mapped_column(String(128))
    event_slug: Mapped[str | None] = mapped_column(String(256))
    outcome: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    fees_paid: Mapped[Decimal] = mapped_column(Numeric(24, 8), default=Decimal("0"))
    mark_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    intent_id: Mapped[int] = mapped_column(ForeignKey("order_intents.id"), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    released: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KillSwitchEvent(Base):
    __tablename__ = "kill_switch_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    cancel_requested: Mapped[int] = mapped_column(Integer, default=0)
    cancel_confirmed: Mapped[int] = mapped_column(Integer, default=0)
    cancel_unconfirmed: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)


class HealthCheck(Base):
    __tablename__ = "health_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    service: Mapped[str] = mapped_column(String(64))
    ok: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[str | None] = mapped_column(Text)


class MarketCache(Base):
    __tablename__ = "market_cache"
    __table_args__ = (UniqueConstraint("condition_id", "token_id", name="uq_market_cache"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    condition_id: Mapped[str] = mapped_column(String(128))
    token_id: Mapped[str] = mapped_column(String(128))
    category: Mapped[str | None] = mapped_column(String(64))
    accepting_orders: Mapped[bool | None] = mapped_column(Boolean)
    min_order_size: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    event_slug: Mapped[str | None] = mapped_column(String(256))
    closed: Mapped[bool | None] = mapped_column(Boolean)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    hypothesis: Mapped[str] = mapped_column(Text)
    parameters_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_path: Mapped[str | None] = mapped_column(String(512))


class ShadowSignal(Base):
    __tablename__ = "shadow_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"))
    reject_reason: Mapped[str] = mapped_column(String(64))
    hypothetical_entry: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    resolved_outcome_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    hypothetical_pnl: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    market_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResearchBrief(Base):
    __tablename__ = "research_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(32))
    content_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReadinessSnapshot(Base):
    __tablename__ = "readiness_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    score: Mapped[int] = mapped_column(Integer)
    tier: Mapped[int] = mapped_column(Integer)
    breakdown_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaperModelCall(Base):
    """Research model paper suggestion only. Never triggers live execution."""

    __tablename__ = "paper_model_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_slug: Mapped[str] = mapped_column(String(256), index=True)
    market_title: Mapped[str] = mapped_column(String(512))
    condition_id: Mapped[str | None] = mapped_column(String(128))
    call: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(16), default="paper")
    outcome: Mapped[str | None] = mapped_column(String(256))
    hypothesis_id: Mapped[str | None] = mapped_column(String(64))
    decision_id: Mapped[str | None] = mapped_column(String(64))
    evidence_json: Mapped[str | None] = mapped_column(Text)
    vault_decision_path: Mapped[str | None] = mapped_column(String(512))
    tags_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

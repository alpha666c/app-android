"""Lightweight SQLite migrations for new columns."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def _has_column(engine: Engine, table: str, column: str) -> bool:
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns(table)}
    return column in cols


def run_migrations(engine: Engine) -> None:
    with engine.connect() as conn:
        if _has_column(engine, "system_state", "id"):
            for col, ddl in (
                ("automation_tier", "INTEGER DEFAULT 1"),
                ("last_order_heartbeat_at", "TIMESTAMP"),
                ("live_stream_ok", "BOOLEAN DEFAULT 0"),
                ("readiness_score", "INTEGER"),
            ):
                if not _has_column(engine, "system_state", col):
                    conn.execute(text(f"ALTER TABLE system_state ADD COLUMN {col} {ddl}"))
        if _has_column(engine, "signals", "id"):
            for col, ddl in (
                ("best_bid_at_signal", "NUMERIC(24,8)"),
                ("best_ask_at_signal", "NUMERIC(24,8)"),
                ("spread_at_signal", "NUMERIC(24,8)"),
                ("market_category", "VARCHAR(64)"),
                ("consensus_wallet_count", "INTEGER DEFAULT 1"),
                ("devils_advocate", "TEXT"),
            ):
                if not _has_column(engine, "signals", col):
                    conn.execute(text(f"ALTER TABLE signals ADD COLUMN {col} {ddl}"))
        conn.commit()

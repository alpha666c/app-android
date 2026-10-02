"""Application configuration — fail-closed mode and risk limits."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum


class TradingMode(str, Enum):
    RESEARCH = "research"
    PAPER = "paper"
    LIVE = "live"


def _parse_decimal(name: str, raw: str | None, required: bool = False) -> Decimal | None:
    if raw is None or raw.strip() == "":
        if required:
            raise ValueError(f"Missing required config: {name}")
        return None
    try:
        return Decimal(raw.strip())
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal for {name}: {raw!r}") from exc


def _parse_int(name: str, raw: str | None, default: int | None = None, required: bool = False) -> int:
    if raw is None or raw.strip() == "":
        if required:
            raise ValueError(f"Missing required config: {name}")
        if default is None:
            raise ValueError(f"Missing config: {name}")
        return default
    return int(raw.strip())


@dataclass(frozen=True)
class RiskLimits:
    starting_balance: Decimal
    max_order_cost: Decimal
    max_event_exposure: Decimal
    max_total_exposure: Decimal
    max_open_positions: int
    max_outstanding_orders: int
    daily_loss_circuit_breaker: Decimal
    max_spread: Decimal
    max_slippage: Decimal
    max_signal_age_seconds: int
    max_data_age_seconds: int


@dataclass(frozen=True)
class Settings:
    trading_mode: TradingMode
    db_path: str
    host: str
    port: int
    dashboard_user: str
    dashboard_password: str
    live_arm_token: str | None
    live_armed: bool
    polymarket_private_key: str | None
    risk: RiskLimits
    cohort_max_rank: int
    cohort_min_volume: Decimal
    cohort_leaderboard_window: str
    signal_price_tolerance: Decimal
    execution_latency_ms: int
    poll_interval_seconds: int
    collateral_label: str = "pUSD"


def load_settings() -> Settings:
    mode_raw = os.environ.get("TRADING_MODE", "paper").strip().lower()
    try:
        trading_mode = TradingMode(mode_raw)
    except ValueError as exc:
        raise ValueError(
            f"Invalid TRADING_MODE={mode_raw!r}; use research, paper, or live"
        ) from exc

    db_path = os.environ.get("POLYSCOPE_DB_PATH", "/data/polyscope.db")
    host = os.environ.get("POLYSCOPE_HOST", "127.0.0.1")
    port = _parse_int("POLYSCOPE_PORT", os.environ.get("POLYSCOPE_PORT"), default=8080)
    dashboard_user = os.environ.get("DASHBOARD_USER", "admin")
    dashboard_password = os.environ.get("DASHBOARD_PASSWORD", "")
    if not dashboard_password:
        raise ValueError("DASHBOARD_PASSWORD must be set (use .env locally)")

    live_arm_token = os.environ.get("LIVE_ARM_TOKEN") or None
    live_armed_env = os.environ.get("LIVE_ARMED", "false").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    live_armed = live_armed_env and trading_mode == TradingMode.LIVE

    polymarket_private_key = os.environ.get("POLYMARKET_PRIVATE_KEY") or None

    if trading_mode == TradingMode.LIVE:
        risk = RiskLimits(
            starting_balance=_parse_decimal("LIVE_MAX_FUNDED_BUDGET", os.environ.get("LIVE_MAX_FUNDED_BUDGET"), required=True),  # type: ignore[arg-type]
            max_order_cost=_parse_decimal("LIVE_MAX_ORDER_COST", os.environ.get("LIVE_MAX_ORDER_COST"), required=True),  # type: ignore[arg-type]
            max_event_exposure=_parse_decimal(
                "LIVE_MAX_EVENT_EXPOSURE", os.environ.get("LIVE_MAX_EVENT_EXPOSURE"), required=True
            ),  # type: ignore[arg-type]
            max_total_exposure=_parse_decimal(
                "LIVE_MAX_TOTAL_EXPOSURE", os.environ.get("LIVE_MAX_TOTAL_EXPOSURE"), required=True
            ),  # type: ignore[arg-type]
            max_open_positions=_parse_int(
                "LIVE_MAX_OPEN_POSITIONS", os.environ.get("LIVE_MAX_OPEN_POSITIONS"), required=True
            ),
            max_outstanding_orders=_parse_int(
                "LIVE_MAX_OUTSTANDING_ORDERS", os.environ.get("LIVE_MAX_OUTSTANDING_ORDERS"), required=True
            ),
            daily_loss_circuit_breaker=_parse_decimal(
                "LIVE_DAILY_LOSS_CIRCUIT_BREAKER",
                os.environ.get("LIVE_DAILY_LOSS_CIRCUIT_BREAKER"),
                required=True,
            ),  # type: ignore[arg-type]
            max_spread=_parse_decimal("LIVE_MAX_SPREAD", os.environ.get("LIVE_MAX_SPREAD"), required=True),  # type: ignore[arg-type]
            max_slippage=_parse_decimal("LIVE_MAX_SLIPPAGE", os.environ.get("LIVE_MAX_SLIPPAGE"), required=True),  # type: ignore[arg-type]
            max_signal_age_seconds=_parse_int(
                "LIVE_MAX_SIGNAL_AGE_SECONDS", os.environ.get("LIVE_MAX_SIGNAL_AGE_SECONDS"), required=True
            ),
            max_data_age_seconds=_parse_int(
                "LIVE_MAX_DATA_AGE_SECONDS", os.environ.get("LIVE_MAX_DATA_AGE_SECONDS"), required=True
            ),
        )
    else:
        risk = RiskLimits(
            starting_balance=Decimal("100"),
            max_order_cost=Decimal("1"),
            max_event_exposure=Decimal("3"),
            max_total_exposure=Decimal("10"),
            max_open_positions=_parse_int(
                "PAPER_MAX_OPEN_POSITIONS", os.environ.get("PAPER_MAX_OPEN_POSITIONS"), default=5
            ),
            max_outstanding_orders=_parse_int(
                "PAPER_MAX_OUTSTANDING_ORDERS", os.environ.get("PAPER_MAX_OUTSTANDING_ORDERS"), default=10
            ),
            daily_loss_circuit_breaker=Decimal("2"),
            max_spread=Decimal(os.environ.get("PAPER_MAX_SPREAD", "0.05")),
            max_slippage=Decimal(os.environ.get("PAPER_MAX_SLIPPAGE", "0.03")),
            max_signal_age_seconds=_parse_int(
                "PAPER_MAX_SIGNAL_AGE_SECONDS", os.environ.get("PAPER_MAX_SIGNAL_AGE_SECONDS"), default=300
            ),
            max_data_age_seconds=_parse_int(
                "PAPER_MAX_DATA_AGE_SECONDS", os.environ.get("PAPER_MAX_DATA_AGE_SECONDS"), default=120
            ),
        )

    return Settings(
        trading_mode=trading_mode,
        db_path=db_path,
        host=host,
        port=port,
        dashboard_user=dashboard_user,
        dashboard_password=dashboard_password,
        live_arm_token=live_arm_token,
        live_armed=live_armed,
        polymarket_private_key=polymarket_private_key,
        risk=risk,
        cohort_max_rank=_parse_int("COHORT_MAX_RANK", os.environ.get("COHORT_MAX_RANK"), default=50),
        cohort_min_volume=Decimal(os.environ.get("COHORT_MIN_VOLUME", "1000")),
        cohort_leaderboard_window=os.environ.get("COHORT_LEADERBOARD_WINDOW", "day"),
        signal_price_tolerance=Decimal(os.environ.get("SIGNAL_PRICE_TOLERANCE", "0.02")),
        execution_latency_ms=_parse_int(
            "EXECUTION_LATENCY_MS", os.environ.get("EXECUTION_LATENCY_MS"), default=500
        ),
        poll_interval_seconds=_parse_int(
            "POLL_INTERVAL_SECONDS", os.environ.get("POLL_INTERVAL_SECONDS"), default=30
        ),
    )


def live_may_execute(settings: Settings, session_armed: bool, geoblock_blocked: bool | None) -> bool:
    if settings.trading_mode != TradingMode.LIVE:
        return False
    if not settings.live_armed or not session_armed:
        return False
    if not settings.polymarket_private_key:
        return False
    if geoblock_blocked is True:
        return False
    return True

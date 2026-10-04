"""FastAPI application and dashboard."""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import secrets
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from polyscope.config import (
    Settings,
    TradingMode,
    assert_paper_only_for_research,
    live_may_execute,
    load_settings,
)
from polyscope.db.models import (
    CohortWallet,
    KillSwitchEvent,
    LedgerAccount,
    OrderIntent,
    PaperModelCall,
    Position,
    ReadinessSnapshot,
    ResearchBrief,
    ShadowSignal,
    Signal,
    SystemState,
)
from polyscope.db.session import get_system_state, init_db
from polyscope.logging_utils import configure_logging
from polyscope.platform.public_client import PlatformClient
from polyscope.research.ai.paper_signal import fetch_open_markets, generate_paper_model_call
from polyscope.research.paper_labels import paper_call_to_api

logger = logging.getLogger(__name__)
security = HTTPBasic()
BASE_DIR = Path(__file__).resolve().parents[3]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

settings: Settings | None = None
SessionLocal: sessionmaker[Session] | None = None


def get_settings() -> Settings:
    if settings is None:
        raise RuntimeError("App not initialized")
    return settings


def get_db() -> Session:
    if SessionLocal is None:
        raise RuntimeError("App not initialized")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_auth(
    creds: Annotated[HTTPBasicCredentials, Depends(security)],
    cfg: Annotated[Settings, Depends(get_settings)],
) -> str:
    user_ok = secrets.compare_digest(creds.username, cfg.dashboard_user)
    pass_ok = secrets.compare_digest(creds.password, cfg.dashboard_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username


def verify_viktor_access(
    creds: Annotated[HTTPBasicCredentials, Depends(HTTPBasic(auto_error=False))],
    cfg: Annotated[Settings, Depends(get_settings)],
    token: Annotated[str | None, Query()] = None,
) -> bool:
    if cfg.viktor_view_token and token and secrets.compare_digest(token, cfg.viktor_view_token):
        return True
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    user_ok = secrets.compare_digest(creds.username, cfg.dashboard_user)
    pass_ok = secrets.compare_digest(creds.password, cfg.dashboard_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


def assert_viktor_public_slug(slug: str, cfg: Settings) -> None:
    if not cfg.viktor_public_slug or not secrets.compare_digest(slug, cfg.viktor_public_slug):
        raise HTTPException(status_code=404, detail="Not found")


async def viktor_paper_state(db: Session, cfg: Settings) -> dict:
    """JSON state for the Viktor paper app (database-backed)."""
    assert_paper_only_for_research(cfg)
    rows = db.scalars(select(PaperModelCall).order_by(PaperModelCall.id.desc()).limit(30)).all()
    loop_pass_count = db.scalar(select(func.count()).select_from(PaperModelCall)) or 0
    markets: list[dict] = []
    async with PlatformClient() as platform:
        try:
            raw = await fetch_open_markets(platform, limit=6)
            markets = [{"title": m.get("title"), "slug": m.get("slug")} for m in raw]
        except Exception:
            markets = []
    decisions = [paper_call_to_api(r) for r in rows]
    latest = decisions[0] if decisions else None
    return {
        "paper_only": True,
        "live_locked": True,
        "trading_mode": cfg.trading_mode.value,
        "loop_pass_count": loop_pass_count,
        "latest": latest,
        "decisions": decisions,
        "markets": markets,
    }


async def build_viktor_page(
    request: Request,
    db: Session,
    cfg: Settings,
    api_state_path: str,
    api_refresh_path: str,
) -> HTMLResponse:
    try:
        assert_paper_only_for_research(cfg)
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "viktor.html",
        {
            "api_state_path": api_state_path,
            "api_refresh_path": api_refresh_path,
        },
    )


async def run_viktor_refresh(db: Session, cfg: Settings) -> dict:
    if cfg.trading_mode != TradingMode.PAPER:
        raise HTTPException(403, "Live trading is locked. Use TRADING_MODE=paper.")
    async with PlatformClient() as platform:
        row = await generate_paper_model_call(db, cfg, platform)
    db.commit()
    return paper_call_to_api(row)


def create_app() -> FastAPI:
    global settings, SessionLocal
    configure_logging()
    settings = load_settings()
    SessionLocal = init_db(settings)
    app = FastAPI(title="PolyScope Trader", version="0.1.0")
    static_dir = BASE_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/viktor", response_class=HTMLResponse)
    async def viktor_screen(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        cfg: Annotated[Settings, Depends(get_settings)],
        _: Annotated[bool, Depends(verify_viktor_access)],
    ) -> HTMLResponse:
        return await build_viktor_page(
            request, db, cfg, "/viktor/api/state", "/viktor/refresh"
        )

    @app.get("/viktor/api/state")
    async def viktor_api_state(
        db: Annotated[Session, Depends(get_db)],
        cfg: Annotated[Settings, Depends(get_settings)],
        _: Annotated[bool, Depends(verify_viktor_access)],
    ) -> dict:
        return await viktor_paper_state(db, cfg)

    @app.post("/viktor/refresh")
    async def viktor_refresh(
        db: Annotated[Session, Depends(get_db)],
        cfg: Annotated[Settings, Depends(get_settings)],
        _: Annotated[bool, Depends(verify_viktor_access)],
    ) -> dict:
        return await run_viktor_refresh(db, cfg)

    @app.get("/p/{slug}", response_class=HTMLResponse)
    async def viktor_public_screen(
        request: Request,
        slug: str,
        db: Annotated[Session, Depends(get_db)],
        cfg: Annotated[Settings, Depends(get_settings)],
    ) -> HTMLResponse:
        assert_viktor_public_slug(slug, cfg)
        return await build_viktor_page(
            request, db, cfg, f"/p/{slug}/api/state", f"/p/{slug}/refresh"
        )

    @app.get("/p/{slug}/api/state")
    async def viktor_public_api_state(
        slug: str,
        db: Annotated[Session, Depends(get_db)],
        cfg: Annotated[Settings, Depends(get_settings)],
    ) -> dict:
        assert_viktor_public_slug(slug, cfg)
        return await viktor_paper_state(db, cfg)

    @app.post("/p/{slug}/refresh")
    async def viktor_public_refresh(
        slug: str,
        db: Annotated[Session, Depends(get_db)],
        cfg: Annotated[Settings, Depends(get_settings)],
    ) -> dict:
        assert_viktor_public_slug(slug, cfg)
        return await run_viktor_refresh(db, cfg)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        cfg: Annotated[Settings, Depends(get_settings)],
        _: Annotated[str, Depends(verify_auth)],
    ) -> HTMLResponse:
        state = get_system_state(db)
        accounts = {
            a.name: a.balance for a in db.scalars(select(LedgerAccount)).all()
        }
        signals = db.scalars(select(Signal).order_by(Signal.id.desc()).limit(20)).all()
        cohort = db.scalars(select(CohortWallet).order_by(CohortWallet.rank).limit(30)).all()
        positions = db.scalars(select(Position).where(Position.size > 0)).all()
        intents = db.scalars(select(OrderIntent).order_by(OrderIntent.id.desc()).limit(20)).all()
        readiness = db.scalar(
            select(ReadinessSnapshot).order_by(ReadinessSnapshot.id.desc()).limit(1)
        )
        briefs = db.scalars(
            select(ResearchBrief).order_by(ResearchBrief.id.desc()).limit(3)
        ).all()
        shadow_count = db.scalar(select(func.count()).select_from(ShadowSignal)) or 0
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "mode": cfg.trading_mode.value,
                "automation_tier": cfg.automation_tier.value,
                "readiness_score": state.readiness_score,
                "readiness": readiness,
                "briefs": briefs,
                "shadow_count": shadow_count,
                "live_armed_env": cfg.live_armed,
                "live_session_armed": state.live_session_armed,
                "kill_switch": state.kill_switch,
                "geoblock_blocked": state.geoblock_blocked,
                "geoblock_country": state.geoblock_country,
                "last_reconciliation": state.last_reconciliation_at,
                "last_public_data": state.last_public_data_at,
                "accounts": accounts,
                "collateral_label": cfg.collateral_label,
                "micro_max_order": cfg.micro_max_order_cost,
                "signals": signals,
                "cohort": cohort,
                "positions": positions,
                "intents": intents,
                "risk": cfg.risk,
            },
        )

    @app.get("/api/health")
    def health(
        db: Annotated[Session, Depends(get_db)],
        cfg: Annotated[Settings, Depends(get_settings)],
        _: Annotated[str, Depends(verify_auth)],
    ) -> dict:
        state = get_system_state(db)
        return {
            "mode": cfg.trading_mode.value,
            "live_may_execute": live_may_execute(
                cfg, state.live_session_armed, state.geoblock_blocked
            ),
            "kill_switch": state.kill_switch,
            "geoblock_blocked": state.geoblock_blocked,
            "last_reconciliation_at": state.last_reconciliation_at,
            "data_stale": state.data_stale,
        }

    @app.post("/api/kill-switch")
    def kill_switch(
        db: Annotated[Session, Depends(get_db)],
        _: Annotated[str, Depends(verify_auth)],
    ) -> dict:
        state = get_system_state(db)
        state.kill_switch = True
        open_intents = db.scalars(
            select(OrderIntent).where(OrderIntent.status.in_(("submitted", "partial")))
        ).all()
        event = KillSwitchEvent(
            cancel_requested=len(open_intents),
            cancel_confirmed=0,
            cancel_unconfirmed=len(open_intents),
            notes="Paper/LIVE cancel requests recorded; unconfirmed until gateway ack",
        )
        db.add(event)
        db.commit()
        return {
            "kill_switch": True,
            "cancel_requested": event.cancel_requested,
            "cancel_unconfirmed": event.cancel_unconfirmed,
        }

    @app.post("/api/live/arm")
    async def arm_live(
        request: Request,
        db: Annotated[Session, Depends(get_db)],
        cfg: Annotated[Settings, Depends(get_settings)],
        _: Annotated[str, Depends(verify_auth)],
    ) -> dict:
        if cfg.trading_mode != TradingMode.LIVE:
            raise HTTPException(400, "TRADING_MODE must be live")
        try:
            body = await request.json()
        except Exception:
            body = {}
        token = body.get("token") if isinstance(body, dict) else None
        if not cfg.live_arm_token or token != cfg.live_arm_token:
            raise HTTPException(403, "Invalid LIVE arm token")
        if not cfg.polymarket_private_key:
            raise HTTPException(400, "POLYMARKET_PRIVATE_KEY missing")
        state = get_system_state(db)
        if state.geoblock_blocked:
            raise HTTPException(403, "Geoblock active for this environment")
        state.live_session_armed = True
        db.commit()
        return {"live_session_armed": True}

    @app.post("/api/live/disarm")
    def disarm_live(
        db: Annotated[Session, Depends(get_db)],
        _: Annotated[str, Depends(verify_auth)],
    ) -> dict:
        state = get_system_state(db)
        state.live_session_armed = False
        db.commit()
        return {"live_session_armed": False}

    @app.get("/api/export/evidence.json")
    def export_json(
        db: Annotated[Session, Depends(get_db)],
        cfg: Annotated[Settings, Depends(get_settings)],
        _: Annotated[str, Depends(verify_auth)],
    ) -> JSONResponse:
        state = get_system_state(db)
        payload = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "mode": cfg.trading_mode.value,
            "signals": [
                {
                    "id": s.id,
                    "wallet": s.wallet,
                    "status": s.status,
                    "reject_reason": s.reject_reason,
                    "observed_at": s.observed_at.isoformat() if s.observed_at else None,
                }
                for s in db.scalars(select(Signal)).all()
            ],
            "cohort_included": db.scalar(
                select(func.count()).select_from(CohortWallet).where(CohortWallet.included.is_(True))
            ),
            "kill_switch": state.kill_switch,
        }
        return JSONResponse(payload)

    @app.get("/api/export/evidence.csv")
    def export_csv(
        db: Annotated[Session, Depends(get_db)],
        _: Annotated[str, Depends(verify_auth)],
    ) -> StreamingResponse:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["signal_id", "wallet", "status", "reject_reason"])
        for s in db.scalars(select(Signal)).all():
            writer.writerow([s.id, s.wallet, s.status, s.reject_reason or ""])
        buf.seek(0)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv")

    @app.get("/api/pnl")
    def pnl_summary(
        db: Annotated[Session, Depends(get_db)],
        _: Annotated[str, Depends(verify_auth)],
    ) -> dict:
        realized = db.scalar(select(LedgerAccount.balance).where(LedgerAccount.name == "realized_pnl"))
        unrealized = db.scalar(select(func.coalesce(func.sum(Position.unrealized_pnl), None)))
        fees = db.scalar(select(LedgerAccount.balance).where(LedgerAccount.name == "fees"))
        return {
            "realized_pnl": str(realized) if realized is not None else None,
            "unrealized_pnl": str(unrealized) if unrealized is not None else None,
            "fees": str(fees) if fees is not None else None,
        }

    return app


def run() -> None:
    import uvicorn

    cfg = load_settings()
    app = create_app()
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    run()

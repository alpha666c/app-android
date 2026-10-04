"""Background trading worker orchestration."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from polyscope.config import Settings, TradingMode, load_settings
from polyscope.db.session import get_system_state, init_db
from polyscope.execution.paper import process_approved_signals
from polyscope.logging_utils import configure_logging
from polyscope.platform.live_gateway import DisabledLiveGateway, build_live_gateway, create_live_gateway
from polyscope.platform.public_client import PlatformClient
from polyscope.platform.stream_ingest import BookCache
from polyscope.research.ai.tasks import run_daily_brief
from polyscope.research.experiments import ensure_default_experiment
from polyscope.research.reports import write_research_report
from polyscope.research.wallet_cohort import refresh_cohort
from polyscope.research.wallet_metrics import run_wallet_studies
from polyscope.risk.confidence import compute_readiness, persist_readiness, tier_allows_auto_execute as tier_exec
from polyscope.strategy.enrich import enrich_open_signals
from polyscope.strategy.wallet_follow import ingest_cohort_activity
from polyscope.worker.heartbeat import OrderHeartbeatLoop
from polyscope.worker.reconcile import reconcile_account
from polyscope.worker.user_stream import UserStreamSupervisor

logger = logging.getLogger(__name__)


class WorkerRunner:
    def __init__(self, settings: Settings, session_factory: sessionmaker[Session]) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.worker_id = os.environ.get("WORKER_ID", str(uuid.uuid4())[:8])
        self._stop = asyncio.Event()
        self.book_cache = BookCache()
        self.gateway = build_live_gateway(False, None)
        self._secure_client = None
        self._heartbeat: OrderHeartbeatLoop | None = None
        self._user_stream: UserStreamSupervisor | None = None
        self._tick_count = 0

    def stop(self) -> None:
        self._stop.set()

    async def start_live_loops(self) -> None:
        if self.settings.trading_mode != TradingMode.LIVE:
            return
        self.gateway = await create_live_gateway(
            self.settings.live_armed, self.settings.polymarket_private_key
        )
        if self.settings.polymarket_private_key:
            try:
                from polymarket import AsyncSecureClient

                self._secure_client = await AsyncSecureClient.create(
                    private_key=self.settings.polymarket_private_key
                )
            except Exception as exc:
                logger.error("secure client init failed: %s", exc)
        self._heartbeat = OrderHeartbeatLoop(
            self.settings, self.session_factory, self.gateway
        )
        self._heartbeat.start()
        self._user_stream = UserStreamSupervisor(
            self.settings, self.session_factory, self._secure_client
        )
        self._user_stream.start()

    async def run_forever(self) -> None:
        await self.start_live_loops()
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception:
                logger.exception("worker tick failed")
            try:
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self.settings.poll_interval_seconds
                )
            except TimeoutError:
                pass
        if self._heartbeat:
            await self._heartbeat.stop()
        if self._user_stream:
            await self._user_stream.stop()
        await self.book_cache.stop()

    async def tick(self) -> None:
        async with PlatformClient() as platform:
            geo = await platform.check_geoblock()
            with self.session_factory() as session:
                state = get_system_state(session)
                state.geoblock_blocked = geo.blocked
                state.geoblock_country = geo.country
                state.automation_tier = self.settings.automation_tier.value
                state.last_public_data_at = datetime.now(timezone.utc)
                ensure_default_experiment(session)
                ok = await reconcile_account(session, self.settings, self.gateway)
                if not ok:
                    session.commit()
                    return
                if not self._try_acquire_executor(session):
                    session.commit()
                    return
                readiness = compute_readiness(session, self.settings)
                persist_readiness(session, readiness)
                if self.settings.trading_mode != TradingMode.RESEARCH:
                    included = await refresh_cohort(session, self.settings, platform)
                    logger.info("cohort refreshed: %s included wallets", included)
                    await run_wallet_studies(session, platform, limit=5)
                    new_s, rej = await ingest_cohort_activity(session, self.settings, platform)
                    logger.info("signals new=%s rejected=%s", new_s, rej)
                    await enrich_open_signals(session, self.settings, platform, self.book_cache)
                if tier_exec(self.settings, self.settings.automation_tier):
                    if self.settings.trading_mode == TradingMode.PAPER:
                        filled = await process_approved_signals(
                            session, self.settings, platform, self.book_cache
                        )
                        logger.info("paper processed signals: %s", filled)
                self._tick_count += 1
                if self._tick_count % 20 == 0:
                    report_path = write_research_report(
                        session, Path(self.settings.report_dir)
                    )
                    logger.info("wrote report %s", report_path)
                    await run_daily_brief(session, self.settings)
                state.last_reconciliation_at = datetime.now(timezone.utc)
                state.executor_heartbeat_at = datetime.now(timezone.utc)
                session.commit()
            if self.settings.use_stream_ingest and self._tick_count == 1:
                from sqlalchemy import select

                from polyscope.db.models import Signal

                with self.session_factory() as session:
                    tokens = [
                        s.token_id
                        for s in session.scalars(
                            select(Signal).order_by(Signal.id.desc()).limit(10)
                        ).all()
                    ]
                if tokens:
                    await self.book_cache.start_stream(platform, tokens)

    def _try_acquire_executor(self, session: Session) -> bool:
        state = get_system_state(session)
        now = datetime.now(timezone.utc)
        if state.executor_holder and state.executor_holder != self.worker_id:
            if state.executor_heartbeat_at:
                age = (now - state.executor_heartbeat_at).total_seconds()
                if age < self.settings.poll_interval_seconds * 3:
                    return False
        state.executor_holder = self.worker_id
        return True


async def run_async() -> None:
    configure_logging()
    settings = load_settings()
    session_factory = init_db(settings)
    runner = WorkerRunner(settings, session_factory)
    await runner.run_forever()


def run() -> None:
    asyncio.run(run_async())


if __name__ == "__main__":
    run()

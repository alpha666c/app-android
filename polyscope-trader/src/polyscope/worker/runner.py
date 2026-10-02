"""Background trading worker orchestration."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from polyscope.config import Settings, TradingMode, load_settings
from polyscope.db.session import get_system_state, init_db
from polyscope.execution.paper import process_approved_signals
from polyscope.logging_utils import configure_logging
from polyscope.platform.public_client import PlatformClient
from polyscope.research.wallet_cohort import refresh_cohort
from polyscope.strategy.wallet_follow import ingest_cohort_activity

logger = logging.getLogger(__name__)


class WorkerRunner:
    def __init__(self, settings: Settings, session_factory: sessionmaker[Session]) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.worker_id = os.environ.get("WORKER_ID", str(uuid.uuid4())[:8])
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
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

    async def tick(self) -> None:
        async with PlatformClient() as platform:
            geo = await platform.check_geoblock()
            with self.session_factory() as session:
                state = get_system_state(session)
                state.geoblock_blocked = geo.blocked
                state.geoblock_country = geo.country
                state.last_public_data_at = datetime.now(timezone.utc)
                state.data_stale = False
                if not self._try_acquire_executor(session):
                    session.commit()
                    return
                if self.settings.trading_mode != TradingMode.RESEARCH:
                    included = await refresh_cohort(session, self.settings, platform)
                    logger.info("cohort refreshed: %s included wallets", included)
                    new_s, rej = await ingest_cohort_activity(session, self.settings, platform)
                    logger.info("signals new=%s rejected=%s", new_s, rej)
                if self.settings.trading_mode == TradingMode.PAPER:
                    filled = await process_approved_signals(session, self.settings, platform)
                    logger.info("paper processed signals: %s", filled)
                state.last_reconciliation_at = datetime.now(timezone.utc)
                state.executor_heartbeat_at = datetime.now(timezone.utc)
                session.commit()

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

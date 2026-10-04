"""CLOB order heartbeat loop (5s) for LIVE."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from polyscope.config import Settings, live_may_execute
from polyscope.db.session import get_system_state
from polyscope.platform.live_gateway import LiveGateway, LiveTradingForbidden

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 5.0


class OrderHeartbeatLoop:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        gateway: LiveGateway,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.gateway = gateway
        self._heartbeat_id = ""
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def run(self) -> None:
        while not self._stop.is_set():
            with self.session_factory() as session:
                state = get_system_state(session)
                if not live_may_execute(
                    self.settings, state.live_session_armed, state.geoblock_blocked
                ):
                    session.commit()
                    await asyncio.sleep(HEARTBEAT_INTERVAL)
                    continue
            try:
                self._heartbeat_id = await self.gateway.send_order_heartbeat(
                    self._heartbeat_id
                )
                with self.session_factory() as session:
                    state = get_system_state(session)
                    state.last_order_heartbeat_at = datetime.now(timezone.utc)
                    session.commit()
            except LiveTradingForbidden:
                pass
            except Exception as exc:
                logger.error("order heartbeat failed: %s", exc)
                with self.session_factory() as session:
                    state = get_system_state(session)
                    state.data_stale = True
                    session.commit()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=HEARTBEAT_INTERVAL)
            except TimeoutError:
                pass

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
            self._task = None

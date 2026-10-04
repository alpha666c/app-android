"""User WebSocket keepalive for LIVE (PING every 10s)."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session, sessionmaker

from polyscope.config import Settings, live_may_execute
from polyscope.db.session import get_system_state

logger = logging.getLogger(__name__)

PING_INTERVAL = 10.0


class UserStreamSupervisor:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        secure_client: object | None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.secure_client = secure_client
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def run(self) -> None:
        while not self._stop.is_set():
            with self.session_factory() as session:
                state = get_system_state(session)
                armed = live_may_execute(
                    self.settings, state.live_session_armed, state.geoblock_blocked
                )
                if not armed or self.secure_client is None:
                    state.live_stream_ok = False
                    session.commit()
                    await asyncio.sleep(PING_INTERVAL)
                    continue
            try:
                from polymarket.streams import UserSpec

                async with await self.secure_client.subscribe(UserSpec()) as stream:
                    with self.session_factory() as session:
                        state = get_system_state(session)
                        state.live_stream_ok = True
                        session.commit()
                    async for _event in stream:
                        if self._stop.is_set():
                            break
            except Exception as exc:
                logger.warning("user stream error: %s", exc)
                with self.session_factory() as session:
                    state = get_system_state(session)
                    state.live_stream_ok = False
                    session.commit()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=PING_INTERVAL)
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

"""Reconcile local state before trading."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from polyscope.config import Settings, live_may_execute
from polyscope.db.models import OrderIntent, SystemState
from polyscope.db.session import get_system_state
from polyscope.platform.live_gateway import LiveGateway

logger = logging.getLogger(__name__)


async def reconcile_account(
    session: Session,
    settings: Settings,
    gateway: LiveGateway,
) -> bool:
    state = get_system_state(session)
    state.last_reconciliation_at = datetime.now(timezone.utc)

    ambiguous = session.scalars(
        select(OrderIntent).where(
            OrderIntent.reconcile_required.is_(True),
            OrderIntent.status.in_(("submitted", "partial")),
        )
    ).all()
    for intent in ambiguous:
        logger.info("reconcile required for intent %s", intent.id)

    if live_may_execute(settings, state.live_session_armed, state.geoblock_blocked):
        try:
            open_orders = await gateway.reconcile_open_orders()
            logger.info("live open orders count: %s", len(open_orders))
        except Exception as exc:
            logger.error("reconciliation failed: %s", exc)
            state.data_stale = True
            session.flush()
            return False

    state.data_stale = False
    session.flush()
    return True

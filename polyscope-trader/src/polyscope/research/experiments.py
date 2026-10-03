"""Experiment tracking."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from polyscope.db.models import Experiment, utcnow


def ensure_default_experiment(session: Session) -> Experiment:
    from sqlalchemy import select

    exp = session.scalar(
        select(Experiment).where(Experiment.name == "wallet_follow_v1")
    )
    if exp:
        return exp
    exp = Experiment(
        name="wallet_follow_v1",
        hypothesis="Leaderboard cohort wallet buys may predict short-term price pressure (test only)",
        parameters_json=json.dumps({"strategy": "wallet_follow", "mode": "paper"}),
        status="active",
        started_at=utcnow(),
    )
    session.add(exp)
    session.flush()
    return exp

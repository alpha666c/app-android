"""Scheduled markdown research reports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from polyscope.db.models import CohortWallet, Experiment, ReadinessSnapshot, Signal


def write_research_report(session: Session, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"report_{stamp}.md"
    included = session.scalar(
        select(func.count()).select_from(CohortWallet).where(CohortWallet.included.is_(True))
    )
    signals = session.scalar(select(func.count()).select_from(Signal)) or 0
    rejected = (
        session.scalar(
            select(func.count()).select_from(Signal).where(Signal.status == "rejected")
        )
        or 0
    )
    readiness = session.scalar(
        select(ReadinessSnapshot).order_by(ReadinessSnapshot.id.desc()).limit(1)
    )
    experiments = session.scalars(select(Experiment).limit(5)).all()
    lines = [
        f"# PolyScope research report {stamp}",
        "",
        f"- Cohort wallets included: {included}",
        f"- Signals total: {signals} (rejected: {rejected})",
        "",
    ]
    if readiness:
        lines.append(f"- Readiness score: {readiness.score} (tier {readiness.tier})")
        lines.append(f"- Breakdown: `{readiness.breakdown_json}`")
    lines.append("")
    lines.append("## Active experiments")
    for exp in experiments:
        lines.append(f"- **{exp.name}** ({exp.status}): {exp.hypothesis[:120]}...")
    lines.append("")
    lines.append("_Signals are hypotheses, not established positive EV._")
    path.write_text("\n".join(lines))
    return path

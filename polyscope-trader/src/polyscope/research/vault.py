"""Obsidian-compatible markdown vault for hypotheses and decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _utc_iso(dt: datetime | None = None) -> str:
    when = dt or datetime.now(timezone.utc)
    return when.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ensure_vault_layout(vault_root: Path) -> None:
    for sub in ("events", "hypotheses", "decisions"):
        (vault_root / sub).mkdir(parents=True, exist_ok=True)


def write_event_snapshot(
    vault_root: Path,
    evidence_id: str,
    frontmatter: dict[str, Any],
    body_lines: list[str],
) -> Path:
    ensure_vault_layout(vault_root)
    path = vault_root / "events" / f"{evidence_id}.md"
    fm = {"id": evidence_id, **frontmatter}
    content = "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + "\n".join(body_lines) + "\n"
    path.write_text(content, encoding="utf-8")
    return path


def write_hypothesis_note(
    vault_root: Path,
    hypothesis_id: str,
    frontmatter: dict[str, Any],
    body_lines: list[str],
) -> Path:
    ensure_vault_layout(vault_root)
    path = vault_root / "hypotheses" / f"{hypothesis_id}.md"
    fm = {"id": hypothesis_id, **frontmatter}
    content = "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + "\n".join(body_lines) + "\n"
    path.write_text(content, encoding="utf-8")
    return path


def write_decision_note(
    vault_root: Path,
    decision_id: str,
    frontmatter: dict[str, Any],
    body_lines: list[str],
) -> Path:
    ensure_vault_layout(vault_root)
    path = vault_root / "decisions" / f"{decision_id}.md"
    fm = {"id": decision_id, **frontmatter}
    content = "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n\n" + "\n".join(body_lines) + "\n"
    path.write_text(content, encoding="utf-8")
    return path

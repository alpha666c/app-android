#!/usr/bin/env python3
"""Public-data connectivity smoke test — writes evidence JSON."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from polyscope.platform.public_client import PlatformClient  # noqa: E402


async def main() -> int:
    evidence_dir = ROOT / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = evidence_dir / f"smoke_{stamp}.json"
    result: dict = {"started_at": datetime.now(timezone.utc).isoformat(), "checks": {}}
    try:
        async with PlatformClient() as platform:
            geo = await platform.check_geoblock()
            result["checks"]["geoblock"] = {
                "ok": True,
                "blocked": geo.blocked,
                "country": geo.country,
            }
            markets = await platform.smoke_markets(3)
            result["checks"]["gamma_markets"] = {"ok": True, "sample": markets}
            board = await platform.fetch_leaderboard_page("day", page_size=3)
            result["checks"]["leaderboard"] = {
                "ok": True,
                "count": len(board),
                "wallets": [str(getattr(e, "wallet", "")) for e in board[:3]],
            }
            if board:
                wallet = str(getattr(board[0], "wallet", ""))
                acts = await platform.fetch_wallet_activity(wallet, page_size=2)
                result["checks"]["activity"] = {"ok": True, "wallet": wallet, "count": len(acts)}
    except Exception as exc:
        result["error"] = str(exc)
        result["ok"] = False
    else:
        result["ok"] = all(c.get("ok") for c in result["checks"].values())
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    out_path.write_text(json.dumps(result, indent=2))
    print(f"Wrote {out_path}")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

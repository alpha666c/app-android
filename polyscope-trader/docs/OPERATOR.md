# Operator playbook

## Daily operation (PAPER)

1. Start worker + API with `TRADING_MODE=paper`.
2. Check dashboard tier and readiness score (not win probability).
3. Export `/api/export/evidence.json` if you need an audit trail.

## No opportunities for days

Normal. Review shadow signal count and reject reasons on the dashboard. Run `python scripts/smoke_public_data.py` to confirm APIs.

## Geoblock blocked

Trading from this IP is restricted. Do not use VPN/proxy bypass. Run PAPER/RESEARCH only, or move LIVE execution to an eligible network you control.

## Kill switch

`POST /api/kill-switch` (authenticated). Verify unconfirmed cancellations on dashboard events.

## Enable AI research

Set `AI_PROVIDER=openai_compatible` and `AI_GATEWAY_API_KEY`. Briefs are advisory only.

## LIVE micro

1. Complete [live-readiness-checklist.md](live-readiness-checklist.md).
2. `TRADING_MODE=live`, all `LIVE_*` limits, `AUTOMATION_TIER=2`, `MICRO_MAX_ORDER_COST`.
3. `LIVE_ARMED=true` + `LIVE_ARM_TOKEN` + `POST /api/live/arm`.
4. Confirm geoblock clear on operator host.

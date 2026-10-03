# Viktor paper screen

## URL

Local default (basic auth):

Local operator URL (basic auth): `http://127.0.0.1:8080/viktor`

Viktor mobile (no password): set `VIKTOR_PUBLIC_SLUG` and share only:

`https://<your-host>/p/<VIKTOR_PUBLIC_SLUG>`

Run locally plus a TLS tunnel (for example `cloudflared tunnel --url http://127.0.0.1:8080`) or deploy `scripts/run-viktor-public.sh` behind your HTTPS load balancer.

Optional query token when `VIKTOR_VIEW_TOKEN` is set:

`http://127.0.0.1:8080/viktor?token=<your-token>`

## Model provider

Research uses `AI_PROVIDER` (default `openai_compatible`) with `AI_GATEWAY_API_KEY` in server env only.

If no key is set, provider label is `rules_fallback` (SKIP with setup instructions).

## Screenshot

Captured at `/opt/cursor/artifacts/screenshots/viktor-paper-screen.png` (mobile viewport).

## Paper proof

- UI badges: **PAPER ONLY** and **LIVE LOCKED**
- `TRADING_MODE` must be `paper` or `/viktor` returns 503
- `/viktor/refresh` returns 403 if mode is not paper
- Rows stored in `paper_model_calls` with `mode=paper` and `outcome` null until filled later
- No import of live order placement on this path

# Platform verification (Polymarket predictions)

Verified against official documentation on **2026-10-02** and a live smoke run (`evidence/smoke_20261002T195252Z.json`).

## Scope

**Prediction markets only** (Gamma, CLOB, Data API v2). **Perps APIs are out of scope.**

## Endpoints confirmed

| Surface | URL | Used for |
|---------|-----|----------|
| Gamma | `https://gamma-api.polymarket.com` | Active markets discovery |
| CLOB | `https://clob.polymarket.com` | Order books, LIVE orders/heartbeats |
| Data API v2 | `https://data-api.polymarket.com` | Leaderboard, positions, activity |
| Geoblock | `https://polymarket.com/api/geoblock` | Execution eligibility (IP-based) |

## SDK

- Package: **`polymarket-client`** (installed **0.12.0** in dev)
- Public reads: `AsyncPublicClient`
- Signed trading: `AsyncSecureClient.create(private_key=...)` (backend only)

## Authentication (LIVE)

- L1: EIP-712 `ClobAuth` on Polygon **chainId 137**
- L2: HMAC-SHA256 headers (`POLY_ADDRESS`, `POLY_SIGNATURE`, `POLY_TIMESTAMP`, `POLY_API_KEY`, `POLY_PASSPHRASE`)
- Order placement uses L2 + wallet signature on order payload

## Fees

Taker fee (when applicable): `fee = C × feeRate × p × (1 - p)` in USDC; makers pay zero. Geopolitics category fee rate **0**. Paper sim uses category rates from [trading/fees](https://docs.polymarket.com/trading/fees.md); missing fee metadata blocks execution.

## Heartbeats

1. **CLOB order heartbeat**: `POST https://clob.polymarket.com/v1/heartbeats` every **5 seconds** (L2 authenticated). Missing heartbeats cancel resting orders.
2. **User WebSocket**: `PING` text frame every **10 seconds** on `wss://ws-subscriptions-clob.polymarket.com/ws/user` (separate from order heartbeats).

## Leaderboard / wallets

- SDK: `list_trader_leaderboard(window=...)` → Data API `GET /v2/leaderboard?time_period=...`
- Smoke test used `window=day`; entries expose **`wallet`** addresses (proxy wallets in API responses).
- **Not verified**: any **90-day** ranking study; pagination `has_more` must be exhausted before long-window claims.

## Smoke test results (this environment)

| Check | Result |
|-------|--------|
| Geoblock | `blocked: true`, `country: US` — **LIVE order placement would be rejected here** |
| Gamma markets | OK (3 slugs returned) |
| Leaderboard | OK (3 wallets) |
| Wallet activity | OK (2 events for sample wallet) |

## Unresolved / LIVE blockers

- User **personal** geographic eligibility is not established by server IP alone.
- LIVE requires explicit env limits, credentials, geoblock pass, reconciliation, and session arming.
- Rate-limit header semantics not captured in smoke (monitor in production).
- `SecureLiveGateway` uses SDK when armed; SDK heartbeat method availability must be verified before production LIVE.

## Sources

- https://docs.polymarket.com/llms.txt
- https://docs.polymarket.com/getting-started/api.md
- https://docs.polymarket.com/getting-started/python.md
- https://docs.polymarket.com/trading/fees.md
- https://docs.polymarket.com/trading/manage-orders.md (order heartbeats)
- https://docs.polymarket.com/trading/realtime-order-updates.md
- https://docs.polymarket.com/api-reference/geoblock

# Live readiness checklist

Use before arming LIVE. All items must be **Yes** unless marked N/A.

## Configuration

- [ ] `TRADING_MODE=live`
- [ ] All `LIVE_*` limits set explicitly (budget, order cost, event/total exposure, positions/orders caps, daily breaker, spread/slippage/signal/data age)
- [ ] `POLYMARKET_PRIVATE_KEY` in backend env only (never chat/logs)
- [ ] `LIVE_ARM_TOKEN` set; session arm via authenticated API after restart
- [ ] Dedicated minimally funded wallet (operational choice)

## Eligibility & data

- [ ] Geoblock check passes for **user** context (not only server IP)
- [ ] Platform verification doc reviewed; no unresolved LIVE blockers
- [ ] Fee/tick/min-size verified per target markets

## Runtime safety

- [ ] Reconciliation passes on startup (balances, open orders, recent fills)
- [ ] CLOB order heartbeat loop active (5s)
- [ ] User WebSocket connected with PING (10s)
- [ ] Kill switch tested (halts new orders; surfaces unconfirmed cancels)
- [ ] Single authoritative executor confirmed
- [ ] Dashboard bound to localhost or authenticated remote access

## Strategy & expectations

- [ ] Wallet-following understood as **hypothesis**, not validated edge
- [ ] No expectation of guaranteed returns
- [ ] Paper profits do not auto-enable LIVE

## Explicit non-actions (default)

- [ ] No auto-liquidation
- [ ] No unlimited token approvals
- [ ] No VPN/proxy bypass for geoblock

# Vertix Portfolio Baseline Rules

This repository follows the Vertix portfolio operating contract. Existing local instructions may add detail or require stricter controls; use the stricter safety, privacy, review, and verification rule on conflict.

- Read local instructions and inspect files before editing; check `git status` before discarding or switching work.
- Keep changes small, reuse existing code and dependencies, and do not mix unrelated cleanup with a feature or fix.
- Use one topic per branch and commit. Preserve independent repository histories; do not turn the portfolio into a monorepo.
- Run the narrowest real verification available and report it as pass, fail, blocked, or not run.
- Never print, commit, log, or copy secrets, tokens, private keys, `.env` contents, customer data, or raw production payloads.
- Production, deploy, secret, DNS, billing, schema/data, external-side-effect, and public-exposure changes need explicit approval for the exact action.
- Never force-push, rewrite history, delete branches, or delete/move files because they merely look stale. Record evidence and obtain explicit approval.
- Keep archived, experimental, and quarantined projects contained until approved security review and activation.
- For cross-repository work, keep separate branches and commits, document affected interfaces, and record the handoff, verification, risks, and next safe action.


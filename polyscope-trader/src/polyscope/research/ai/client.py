"""Pluggable LLM client for research only — no trading tools."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx

from polyscope.config import Settings, research_ai_skip_reason

logger = logging.getLogger(__name__)

PAPER_DECISION_PROVIDERS = frozenset({"openai_compatible", "openrouter"})


@dataclass
class BriefOutput:
    thesis: str
    uncertainties: list[str]
    data_gaps: list[str]
    cautions: list[str]


@dataclass
class PaperCallOutput:
    call: str
    reason: str
    provider: str


@dataclass
class PaperDecisionOutput:
    action: str
    reason: str
    provider: str


class ResearchAIClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> bool:
        return (
            self.settings.ai_provider not in ("none", "")
            and self.settings.ai_gateway_api_key is not None
        )

    def _chat_completions_url(self) -> str:
        return f"{self.settings.ai_api_base.rstrip('/')}/chat/completions"

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.ai_gateway_api_key}",
            "Content-Type": "application/json",
        }

    def _provider_label(self) -> str:
        if self.settings.ai_provider == "openrouter":
            return "openrouter"
        if self.settings.ai_provider == "openai_compatible":
            return "openai_compatible"
        return self.settings.ai_provider

    async def synthesize(self, topic: str, facts: dict) -> BriefOutput | None:
        if not self.available():
            return None
        prompt = (
            "You are a research analyst for prediction markets. "
            "Output ONLY valid JSON with keys: thesis, uncertainties, data_gaps, cautions. "
            "Do NOT recommend trades or sizes. Facts:\n"
            + json.dumps(facts, default=str)
        )
        if self.settings.ai_provider in PAPER_DECISION_PROVIDERS:
            parsed = await self._chat_json(prompt)
            if parsed:
                return BriefOutput(
                    thesis=str(parsed.get("thesis", topic)),
                    uncertainties=list(parsed.get("uncertainties", [])),
                    data_gaps=list(parsed.get("data_gaps", [])),
                    cautions=list(parsed.get("cautions", [])),
                )
        if self.settings.ai_provider == "anthropic":
            return await self._anthropic(topic, prompt)
        return None

    async def _anthropic(self, topic: str, prompt: str) -> BriefOutput | None:
        logger.info("anthropic provider not fully configured; skip")
        return None

    def provider_display_name(self) -> str:
        if self.settings.ai_provider == "none" or not self.settings.ai_gateway_api_key:
            return "rules_fallback"
        return self._provider_label()

    async def suggest_paper_call(self, market_facts: dict) -> PaperCallOutput:
        """Legacy wrapper; prefer suggest_paper_decision."""
        out = await self.suggest_paper_decision(market_facts)
        return PaperCallOutput(call=out.action, reason=out.reason, provider=out.provider)

    async def suggest_paper_decision(self, market_facts: dict) -> PaperDecisionOutput:
        """Research-only structured decision. Never places orders or invents prices."""
        if not self.available():
            return PaperDecisionOutput(
                action="WAIT",
                reason=research_ai_skip_reason(self.settings),
                provider="rules_fallback",
            )
        prompt = (
            "You advise on Polymarket prediction markets for PAPER research only. "
            "Output ONLY JSON with keys: action, reason. "
            "action must be one of: BUY, SELL, WAIT, REJECT. "
            "BUY means favor YES, SELL means favor NO, WAIT means abstain, REJECT means veto the setup. "
            "reason is one or two short sentences, no hype. "
            "Do NOT invent prices, probabilities, or outcomes. "
            "Use only the facts provided. Market facts:\n"
            + json.dumps(market_facts, default=str)
        )
        if self.settings.ai_provider in PAPER_DECISION_PROVIDERS:
            parsed = await self._chat_json(prompt)
            if parsed:
                action = str(parsed.get("action", parsed.get("call", "WAIT"))).upper()
                allowed = ("BUY", "SELL", "WAIT", "REJECT", "BUY_YES", "BUY_NO", "SKIP")
                if action not in allowed:
                    action = "WAIT"
                return PaperDecisionOutput(
                    action=action,
                    reason=str(parsed.get("reason", "No reason returned.")),
                    provider=self._provider_label(),
                )
            return PaperDecisionOutput(
                action="WAIT",
                reason="Model returned invalid output. Paper mode only.",
                provider=self.provider_display_name(),
            )
        return PaperDecisionOutput(
            action="WAIT",
            reason="Model provider unavailable. Paper mode only.",
            provider=self.provider_display_name(),
        )

    async def suggest_training_next_step(self, facts: dict) -> str | None:
        """One line: what to do differently next time. Facts only, no invented prices."""
        if not self.available():
            return None
        prompt = (
            "You write training notes for a paper-only prediction market bot. "
            "Output ONLY JSON with key: next_step. "
            "next_step is one or two short sentences on what to do differently next time. "
            "Use ONLY the facts provided. Do NOT invent prices, outcomes, or PnL. "
            "Facts:\n"
            + json.dumps(facts, default=str)
        )
        parsed = await self._chat_json(prompt)
        if not parsed:
            return None
        raw = parsed.get("next_step") or parsed.get("lesson")
        if raw is None:
            return None
        return str(raw).strip()[:500]

    async def _chat_json(self, prompt: str) -> dict | None:
        body = {
            "model": self.settings.ai_model,
            "messages": [
                {"role": "system", "content": "Respond with JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as http:
                resp = await http.post(
                    self._chat_completions_url(),
                    headers=self._request_headers(),
                    json=body,
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception as exc:
            logger.warning("AI research call failed: %s", type(exc).__name__)
            return None

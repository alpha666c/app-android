"""Pluggable LLM client for research only — no trading tools."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx

from polyscope.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class BriefOutput:
    thesis: str
    uncertainties: list[str]
    data_gaps: list[str]
    cautions: list[str]


class ResearchAIClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> bool:
        return (
            self.settings.ai_provider != "none"
            and self.settings.ai_gateway_api_key is not None
        )

    async def synthesize(self, topic: str, facts: dict) -> BriefOutput | None:
        if not self.available():
            return None
        prompt = (
            "You are a research analyst for prediction markets. "
            "Output ONLY valid JSON with keys: thesis, uncertainties, data_gaps, cautions. "
            "Do NOT recommend trades or sizes. Facts:\n"
            + json.dumps(facts, default=str)
        )
        if self.settings.ai_provider == "openai_compatible":
            return await self._openai_chat(topic, prompt)
        if self.settings.ai_provider == "anthropic":
            return await self._anthropic(topic, prompt)
        return None

    async def _openai_chat(self, topic: str, prompt: str) -> BriefOutput | None:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.ai_gateway_api_key}",
            "Content-Type": "application/json",
        }
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
                resp = await http.post(url, headers=headers, json=body)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                data = json.loads(content)
                return BriefOutput(
                    thesis=str(data.get("thesis", topic)),
                    uncertainties=list(data.get("uncertainties", [])),
                    data_gaps=list(data.get("data_gaps", [])),
                    cautions=list(data.get("cautions", [])),
                )
        except Exception as exc:
            logger.warning("AI research call failed: %s", exc)
            return None

    async def _anthropic(self, topic: str, prompt: str) -> BriefOutput | None:
        logger.info("anthropic provider not fully configured; skip")
        return None

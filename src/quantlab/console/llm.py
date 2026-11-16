"""Optional OpenAI-compatible research model gateway.

Kimi, DeepSeek, OpenAI-compatible hosted models, and local gateways can use the
same contract. This gateway is explanation-only: it has no tools, credentials,
order methods, or risk-control authority.
"""
from __future__ import annotations

import json
import os
from typing import Callable
from urllib.request import Request, urlopen


SYSTEM_PROMPT = """You are QuantLab's read-only market research assistant.
Use only the supplied evidence JSON. You may discuss observed momentum, highs,
lows, utility metadata, news context, and scenario-based entry/exit/hold risks.
Never invent prices, dates, sources, news, fundamentals, liquidity, or returns.
Do not claim certainty. Do not place, approve, or format a brokerage order.
Clearly label opinions as research, include a heavy disclaimer that this is not
personalized financial advice, and cite the supplied source names and times.
If evidence is missing, say so plainly."""


class OpenAICompatibleModel:
    def __init__(self, base_url: str, api_key: str, model: str, opener: Callable | None = None):
        if not base_url.startswith("https://"):
            raise ValueError("LLM base URL must use HTTPS")
        if not api_key or not model:
            raise ValueError("LLM API key and model are required")
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.opener = opener or urlopen

    def __call__(self, system_prompt: str, evidence_json: str) -> str:
        body = json.dumps({
            "model": self.model,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": evidence_json},
            ],
        }).encode("utf-8")
        request = Request(self.endpoint, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with self.opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
        except Exception as exc:
            raise RuntimeError(f"research model request failed: {type(exc).__name__}") from None
        if not isinstance(content, str) or not content.strip() or len(content) > 8000:
            raise RuntimeError("research model returned invalid content")
        return content.strip()


def build_research_model() -> OpenAICompatibleModel | None:
    base_url = os.getenv("QUANTLAB_LLM_BASE_URL", "")
    api_key = os.getenv("QUANTLAB_LLM_API_KEY", "")
    model = os.getenv("QUANTLAB_LLM_MODEL", "")
    if not (base_url and api_key and model):
        return None
    return OpenAICompatibleModel(base_url, api_key, model)

"""
TrustOS — LLM-assisted risk signals (optional OpenAI).

When OPENAI_API_KEY is set, calls the Chat Completions API with JSON output.
Otherwise returns a deterministic heuristic from review text and counts.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, List, Tuple

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


@dataclass
class LlmRiskAssessment:
    signals: List[str]
    risk_modifier: int
    confidence: float


SYSTEM_PROMPT = """You are TrustOS, a fraud and trust analyst for e-commerce.
Given product and party context, output ONLY valid JSON with this exact shape:
{"signals": ["short_snake_case_label", ...], "risk_modifier": <integer -20 to 20>, "confidence": <float 0.0-1.0>}

Rules:
- signals: 0-8 concise risk or trust hints from reviews/disputes (e.g. "mixed_sentiment", "repeat_complaint_theme").
- risk_modifier: add/subtract from aggregate risk (-20 safer, +20 riskier). Use 0 if neutral.
- confidence: your confidence in this qualitative assessment (0-1).
Do not include markdown or text outside the JSON object."""


def _parse_llm_json(raw: str) -> LlmRiskAssessment:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    signals = [str(s).strip() for s in (data.get("signals") or []) if str(s).strip()]
    modifier = int(data.get("risk_modifier", 0))
    modifier = max(-20, min(20, modifier))
    conf = float(data.get("confidence", 0.5))
    conf = max(0.0, min(1.0, conf))
    return LlmRiskAssessment(signals=signals[:12], risk_modifier=modifier, confidence=conf)


def _heuristic_assessment(
    product_name: str,
    review_summary: str,
    seller_complaints: int,
    buyer_disputes: int,
) -> LlmRiskAssessment:
    text = f"{product_name} {review_summary}".lower()
    signals: List[str] = []

    negative = ("refund", "scam", "fake", "poor", "broken", "never arrived", "worst", "dispute", "fraud")
    positive = ("great", "excellent", "recommend", "perfect", "fast delivery", "genuine")
    for w in negative:
        if w in text:
            signals.append(f"review_keyword_{w.replace(' ', '_')}")
    for w in positive:
        if w in text:
            signals.append(f"review_positive_{w.replace(' ', '_')}")

    if seller_complaints >= 3:
        signals.append("elevated_seller_complaint_count")
    if buyer_disputes >= 2:
        signals.append("elevated_buyer_dispute_count")
    if not review_summary.strip():
        signals.append("missing_review_text")
    if not signals:
        signals.append("no_heuristic_flags")

    modifier = 0
    if any(s.startswith("review_keyword_") for s in signals):
        modifier += 5
    if "elevated_seller_complaint_count" in signals:
        modifier += 4
    if "elevated_buyer_dispute_count" in signals:
        modifier += 3
    if any(s.startswith("review_positive_") for s in signals):
        modifier -= 3
    modifier = max(-20, min(20, modifier))

    conf = 0.35 if not review_summary.strip() else 0.55
    return LlmRiskAssessment(signals=signals[:8], risk_modifier=modifier, confidence=conf)


def assess_with_llm(
    product_name: str,
    review_summary: str,
    seller_complaints: int,
    buyer_disputes: int,
    timeout_sec: float = 25.0,
) -> Tuple[LlmRiskAssessment, str]:
    """
    Returns (assessment, source) where source is 'openai' or 'heuristic'.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("TRUSTOS_LLM_MODEL", "gpt-4o-mini").strip()

    user_payload = {
        "product_name": product_name,
        "review_summary": review_summary or "(none)",
        "seller_complaints": seller_complaints,
        "buyer_disputes": buyer_disputes,
    }

    if not api_key or httpx is None:
        return _heuristic_assessment(
            product_name, review_summary, seller_complaints, buyer_disputes
        ), "heuristic"

    url = "https://api.openai.com/v1/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(user_payload, ensure_ascii=False),
            },
        ],
    }

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            r = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            r.raise_for_status()
            data = r.json()
        content = data["choices"][0]["message"]["content"]
        return _parse_llm_json(content), "openai"
    except Exception:
        return _heuristic_assessment(
            product_name, review_summary, seller_complaints, buyer_disputes
        ), "heuristic_fallback"

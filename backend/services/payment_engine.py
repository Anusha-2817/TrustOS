import json
import os
from typing import Any

from openai import OpenAI


class PaymentEngine:

    @staticmethod
    def process_payment(order, decision):

        if decision == "LOW":
            return {
                "type": "CAPTURE",
                "message": "Immediate payment to seller"
            }

        elif decision == "MEDIUM":
            return {
                "type": "AUTHORIZE",
                "message": "Hold payment, capture later"
            }

        elif decision == "HIGH":
            return {
                "type": "WALLET_HOLD",
                "message": "Route to wallet, no seller access"
            }


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _llm_fallback(message: str) -> dict[str, Any]:
    print("LLM ERROR:", message)
    return {
        "signals": [],
        "risk_modifier": 0,
        "confidence": 0.5,
    }


def call_llm(data: dict[str, Any]) -> dict[str, Any]:
    """OpenAI JSON completion; on any failure returns signals=[], confidence=0.5."""
    product_name = str(data.get("product_name", "") or "")
    review_summary = str(data.get("review_summary", "") or "")
    try:
        seller_complaints = int(data.get("seller_complaints", 0) or 0)
    except (TypeError, ValueError):
        seller_complaints = 0
    try:
        buyer_disputes = int(data.get("buyer_disputes", 0) or 0)
    except (TypeError, ValueError):
        buyer_disputes = 0

    user_prompt = f"""You are a fraud detection expert.

Analyze:
Product: {product_name}
Reviews: {review_summary}
Seller complaints: {seller_complaints}
Buyer disputes: {buyer_disputes}

Return STRICT JSON:
{{
  "signals": ["..."],
  "risk_modifier": number,
  "confidence": number
}}"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = (resp.choices[0].message.content or "").strip()
        print("LLM RESPONSE:", raw)
        first = raw.find("{")
        last = raw.rfind("}")
        if first == -1 or last == -1 or last < first:
            return _llm_fallback("no JSON object found in LLM response")
        json_str = raw[first : last + 1]
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            return _llm_fallback(f"JSON decode error: {e}")
        if not isinstance(parsed, dict):
            return _llm_fallback("parsed JSON is not an object")

        raw_signals = parsed.get("signals", [])
        if not isinstance(raw_signals, list):
            raw_signals = []
        signals = [
            str(s).strip()
            for s in raw_signals
            if str(s).strip()
        ]

        rm = parsed.get("risk_modifier", 0)
        try:
            risk_modifier = float(rm) if rm is not None else 0.0
        except (TypeError, ValueError):
            return _llm_fallback("risk_modifier must be a number")

        cf = parsed.get("confidence", 0.5)
        try:
            confidence = float(cf) if cf is not None else 0.5
        except (TypeError, ValueError):
            return _llm_fallback("confidence must be a number")
        confidence = max(0.0, min(1.0, confidence))

        return {
            "signals": signals,
            "risk_modifier": risk_modifier,
            "confidence": confidence,
        }
    except Exception as e:
        return _llm_fallback(str(e))
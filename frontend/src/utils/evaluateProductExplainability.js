/**
 * Human-readable explainability for POST /evaluate-product responses.
 */

const SIGNAL_MESSAGES = {
  fake_product_risk:
    "Review and listing signals suggest elevated fake or misrepresented product risk.",
  scam_pattern: "Patterns resemble common scam or high-pressure seller tactics.",
  delayed_shipping_risk: "Signals point to shipping, delays, or fulfillment friction.",
  trust_concern: "Narrative signals indicate trust or authenticity concerns in reviews.",
  chargeback_risk: "Signals suggest a higher likelihood of disputes or chargebacks.",
  counterfeit_risk: "Indicators align with counterfeit or non-genuine goods risk.",
  seller_reliability: "Seller reliability shows up as a concern in the review layer.",
  buyer_risk: "Buyer-side behavior or history contributes additional caution.",
};

function humanizeToken(raw) {
  return String(raw || "")
    .trim()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function explainSignal(signal) {
  const raw = String(signal).trim();
  if (!raw) return null;
  const key = raw.toLowerCase().replace(/\s+/g, "_");
  if (SIGNAL_MESSAGES[key]) return SIGNAL_MESSAGES[key];
  return `TrustOS flagged "${humanizeToken(raw)}" from product and review context.`;
}

export function formatSignalTag(signal) {
  const s = String(signal).trim();
  if (!s) return "";
  return `[ ${s} ]`;
}

/**
 * @param {Record<string, unknown>} data - EvaluateProductResponse
 * @returns {{ reasons: string[]; signalTags: string[] }}
 */
export function buildEvaluateProductExplainability(data) {
  const reasons = [];
  const keys = new Set();

  const push = (key, sentence) => {
    if (!sentence || keys.has(key)) return;
    keys.add(key);
    reasons.push(sentence);
  };

  const bt = Number(data.buyer_trust);
  const st = Number(data.seller_trust);
  const bd = Number(data.buyer_disputes) || 0;
  const sc = Number(data.seller_complaints) || 0;
  const bo = Number(data.buyer_orders) || 0;
  const so = Number(data.seller_orders) || 0;
  const price = Number(data.product_price) || 0;
  const rb = data.risk_breakdown || {};
  const valueRisk = Number(rb.value_risk);

  const signals = Array.isArray(data.signals)
    ? data.signals.map((s) => String(s).trim()).filter(Boolean)
    : [];

  signals.forEach((sig, i) => {
    const line = explainSignal(sig);
    if (line) push(`signal-${i}-${sig}`, line);
  });

  if (!Number.isNaN(bt) && bt < 48) {
    if (bd >= 2) {
      push("low-bt-disputes", "Low buyer trust — multiple disputes on this profile reduce confidence.");
    } else if (bo < 6) {
      push("low-bt-orders", "Low buyer trust — relatively few completed orders to establish a strong track record.");
    } else {
      push("low-bt", "Buyer trust is on the low side for this checkout.");
    }
  }

  if (!Number.isNaN(st) && st < 48) {
    if (sc >= 3) {
      push("low-st-complaints", "Low seller trust — several complaints suggest buyers have had issues.");
    } else if (so < 8) {
      push("low-st-orders", "Low seller trust — the seller has limited completed order volume.");
    } else {
      push("low-st", "Seller trust is on the low side, so TrustOS weights this transaction more carefully.");
    }
  }

  if (sc >= 4 && !keys.has("low-st-complaints")) {
    push("seller-complaints-high", "Seller has multiple complaints, which lifts perceived risk.");
  } else if (sc >= 2 && sc < 4 && st >= 48) {
    push("seller-complaints", "Seller has a non-trivial complaint count worth noting.");
  }

  if (bd >= 3 && bt >= 48) {
    push("buyer-disputes", "Buyer has a noticeable dispute history even if trust is moderate.");
  }

  if (price >= 25000 || valueRisk >= 20) {
    push("price-high", "High order value increases risk — larger amounts warrant stronger safeguards.");
  } else if (price >= 8000 || valueRisk >= 10) {
    push("price-elevated", "Order value sits in a higher band, adding measurable value risk.");
  }

  if (data.is_new_interaction) {
    push("new-pair", "First-time buyer–seller pairing — there is no shared history to lean on.");
  }

  if (data.new_device) {
    push("new-device", "A new or unfamiliar device or session adds context risk.");
  }

  const behavior = Number(data.behavior_risk);
  if (!Number.isNaN(behavior) && behavior >= 14 && signals.length === 0) {
    push("behavior-only", "Review-driven behavior risk added a meaningful bump on top of trust and context.");
  }

  if (reasons.length === 0) {
    push(
      "balanced",
      "Risk is mainly explained by the numeric mix of trust, value, and context — see the breakdown above.",
    );
  }

  return {
    reasons,
    signalTags: signals,
  };
}

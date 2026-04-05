const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function detailToMessage(detail) {
  if (detail == null) return "Request failed";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => e.msg || JSON.stringify(e)).join("; ");
  }
  if (typeof detail === "object" && detail.msg) return detail.msg;
  return JSON.stringify(detail);
}

/**
 * @param {string} path
 * @param {RequestInit} [options]
 */
export async function apiFetch(path, options = {}) {
  const url = `${BASE_URL}${path}`;
  const headers = {
    Accept: "application/json",
    ...options.headers,
  };
  if (options.body != null && typeof options.body === "string") {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(url, { ...options, headers });
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    const msg = detailToMessage(data?.detail) || res.statusText || `HTTP ${res.status}`;
    throw new ApiError(msg, res.status, data);
  }
  return data;
}

/** Map UI buyer to BuyerProfile (counts, not percentages). */
export function productToBuyerProfile(buyer) {
  const s = buyer.successfulOrders;
  let disputes = Math.round(s * (buyer.disputeRate / 100));
  if (buyer.disputeRate > 0 && disputes < 1 && s > 0) disputes = 1;
  const total_orders = Math.max(s + disputes, s, 1);
  return {
    successful_orders: s,
    total_orders,
    disputes,
    fraud_flags: buyer.fraudFlags ?? 0,
  };
}

/** Map UI seller to SellerProfile. */
export function productToSellerProfile(seller) {
  const s = seller.successfulOrders;
  let complaints = Math.round(s * (seller.complaintRate / 100));
  if (seller.complaintRate > 0 && complaints < 1 && s > 0) complaints = 1;
  const total_orders = Math.max(s + complaints, s, 1);
  return {
    successful_orders: s,
    total_orders,
    complaints,
    fraud_flags: seller.fraudFlags ?? 0,
  };
}

/** INR order value so backend value-risk tiers match product valueCategory. */
const VALUE_CATEGORY_INR = { low: 2500, mid: 5500, high: 15000 };

export function productToTransactionRequest(product) {
  return {
    buyer: productToBuyerProfile(product.buyer),
    seller: productToSellerProfile(product.seller),
    order_value: VALUE_CATEGORY_INR[product.valueCategory] ?? 5500,
    is_new_pair: Boolean(product.isNewPair),
    is_new_device: Boolean(product.isNewContext),
  };
}

/** Normalize decision engine classification to RISK_CONFIG keys. */
export function riskClassificationToLevel(classification) {
  const c = String(classification || "").toUpperCase();
  if (c === "LOW") return "low";
  if (c === "MEDIUM") return "medium";
  if (c === "HIGH") return "high";
  return "medium";
}

/**
 * @param {object} full - FullEvaluationResponse from backend
 */
export function mapFullEvaluationToRiskData(full) {
  const level = riskClassificationToLevel(full.decision?.risk_classification);
  const rc = full.risk_components;
  return {
    score: full.risk_score,
    level,
    bt: full.buyer_trust,
    st: full.seller_trust,
    tr: rc.transaction_risk_total,
    valueRisk: rc.value_risk,
    interactionRisk: rc.interaction_risk,
    contextRisk: rc.context_risk,
    decision: full.decision,
    buyer_breakdown: full.buyer_breakdown,
    seller_breakdown: full.seller_breakdown,
    buyer_trust_level: full.buyer_trust_level,
    seller_trust_level: full.seller_trust_level,
    raw: full,
  };
}

/** Demo panel: fixed origin as requested (POST /evaluate-product). */
const EVALUATE_PRODUCT_DEMO_URL = "http://127.0.0.1:8000/evaluate-product";

/**
 * @param {object} body - EvaluateProductRequest JSON
 * @returns {Promise<object>}
 */
export async function postEvaluateProduct(body) {
  const res = await fetch(EVALUATE_PRODUCT_DEMO_URL, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  if (!res.ok) {
    const msg = detailToMessage(data?.detail) || res.statusText || `HTTP ${res.status}`;
    throw new ApiError(msg, res.status, data);
  }
  return data;
}

export async function checkHealth() {
  return apiFetch("/health");
}

export async function computeBuyerTrust(profile) {
  return apiFetch("/trust/buyer", {
    method: "POST",
    body: JSON.stringify(profile),
  });
}

export async function computeSellerTrust(profile) {
  return apiFetch("/trust/seller", {
    method: "POST",
    body: JSON.stringify(profile),
  });
}

/** Parallel trust scores for the order detail view. */
export async function fetchTrustPreviewForProduct(product) {
  const body = productToTransactionRequest(product);
  const [buyerRes, sellerRes] = await Promise.all([
    computeBuyerTrust(body.buyer),
    computeSellerTrust(body.seller),
  ]);
  return { buyer: buyerRes, seller: sellerRes };
}

export async function evaluateFullTransaction(product) {
  const body = productToTransactionRequest(product);
  return apiFetch("/decision/evaluate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * Slider / what-if risk simulator (same response as full evaluation).
 * @param {object} params
 */
export async function evaluateSimulator({
  buyerSuccessfulOrders = 12,
  buyerDisputeRatePercent = 5,
  buyerFraudFlags = 0,
  sellerSuccessfulOrders = 40,
  sellerComplaintRatePercent = 5,
  sellerFraudFlags = 0,
  orderValueInr = 5500,
  isNewPair = false,
  isNewDevice = false,
} = {}) {
  return apiFetch("/simulator/evaluate", {
    method: "POST",
    body: JSON.stringify({
      buyer_successful_orders: buyerSuccessfulOrders,
      buyer_dispute_rate_percent: buyerDisputeRatePercent,
      buyer_fraud_flags: buyerFraudFlags,
      seller_successful_orders: sellerSuccessfulOrders,
      seller_complaint_rate_percent: sellerComplaintRatePercent,
      seller_fraud_flags: sellerFraudFlags,
      order_value_inr: orderValueInr,
      is_new_pair: isNewPair,
      is_new_device: isNewDevice,
    }),
  });
}

export async function evaluateRiskQuery(scenario) {
  const q = new URLSearchParams({ scenario: scenario || "medium_risk" });
  return apiFetch(`/evaluate-risk?${q.toString()}`);
}

/**
 * Demo contract: scenario must be low_risk | medium_risk | high_risk.
 * Align with evaluated UI level: `${level}_risk`.
 */
export async function initiatePayment({ scenario = "medium_risk" } = {}) {
  return apiFetch("/initiate-payment", {
    method: "POST",
    body: JSON.stringify({ scenario }),
  });
}

export async function verifyDelivery({ passed = true, inconsistent = false } = {}) {
  return apiFetch("/verify", {
    method: "POST",
    body: JSON.stringify({ passed, inconsistent }),
  });
}

/** action: capture | release | cancel */
export async function settlePayment({ action = "capture" } = {}) {
  return apiFetch("/settle", {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export function scenarioFromRiskLevel(level) {
  const l = String(level || "medium").toLowerCase();
  if (l === "low") return "low_risk";
  if (l === "high") return "high_risk";
  return "medium_risk";
}

/**
 * Hardcoded payloads for POST /evaluate-product (backend EvaluateProductRequest).
 */

export const demoTransactionLowRisk = {
  product_name: "Ergonomic desk lamp",
  product_price: 2800,
  seller_orders: 92,
  seller_complaints: 2,
  buyer_orders: 48,
  buyer_disputes: 1,
  review_summary: "Consistently positive reviews; quick delivery.",
  is_new_interaction: false,
  new_device: false,
};

export const demoTransactionMediumRisk = {
  product_name: "Wireless mechanical keyboard",
  product_price: 6200,
  seller_orders: 22,
  seller_complaints: 5,
  buyer_orders: 14,
  buyer_disputes: 4,
  review_summary: "Some buyers report packaging issues; seller responds to tickets.",
  is_new_interaction: true,
  new_device: false,
};

export const demoTransactionHighRisk = {
  product_name: "Imported camera lens kit",
  product_price: 16500,
  seller_orders: 3,
  seller_complaints: 6,
  buyer_orders: 2,
  buyer_disputes: 5,
  review_summary: "Sparse reviews; several mention non-delivery or wrong item.",
  is_new_interaction: true,
  new_device: true,
};

export const demoTransactionLowValueHighRisk = {
  product_name: "Phone case bundle",
  product_price: 750,
  seller_orders: 2,
  seller_complaints: 4,
  buyer_orders: 1,
  buyer_disputes: 3,
  review_summary: "New listing; no verified purchase reviews yet.",
  is_new_interaction: true,
  new_device: true,
};

export const demoTransactionHighValueTrusted = {
  product_name: "Professional workstation laptop",
  product_price: 48500,
  seller_orders: 240,
  seller_complaints: 5,
  buyer_orders: 112,
  buyer_disputes: 2,
  review_summary: "Top seller badge; long history of successful high-value orders.",
  is_new_interaction: false,
  new_device: false,
};

/** @type {{ id: string; label: string; description: string; payload: typeof demoTransactionLowRisk }[]} */
export const TRUSTOS_DEMO_TRANSACTION_CASES = [
  { id: "low-risk", label: "Low Risk", description: "Established pair, healthy history", payload: demoTransactionLowRisk },
  { id: "medium-risk", label: "Medium Risk", description: "New pair, moderate signals", payload: demoTransactionMediumRisk },
  { id: "high-risk", label: "High Risk", description: "Sparse history, risky context", payload: demoTransactionHighRisk },
  { id: "low-value-high-risk", label: "Low Value High Risk", description: "Small ticket, risky context", payload: demoTransactionLowValueHighRisk },
  { id: "high-value-trusted", label: "High Value Trusted", description: "Large ticket, strong counterparties", payload: demoTransactionHighValueTrusted },
];

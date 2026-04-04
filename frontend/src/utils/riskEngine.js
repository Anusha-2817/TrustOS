// TrustOS Risk Engine - based on rules.txt
// Buyer Trust: 40 + (2 × orders) - (15 × disputeRate%) - (20 × fraudFlags), clamped 0–100
// Seller Trust: 50 + (1.5 × orders) - (20 × complaintRate%) - (30 × fraudFlags), clamped 0–100
// Risk Score: 100 - (0.4 × BT) - (0.4 × ST) + TransactionRisk
// Decision: ≤30 LOW | 31–60 MEDIUM | 61+ HIGH

export const PRODUCTS = [
  {
    id: "prod_low",
    name: "Cloud API Subscription",
    priceLabel: "$49.00/mo",
    priceValue: 49,
    category: "Digital Goods",
    image:
      "https://images.unsplash.com/photo-1551288049-bebda4e38f71?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
    description: "Monthly developer plan — 10M API req/mo, 99.9% SLA, global CDN.",
    expectedRisk: "low",
    buyer: {
      name: "Priya Sharma",
      avatar:
        "https://images.pexels.com/photos/14585727/pexels-photo-14585727.jpeg?auto=compress&cs=tinysrgb&h=120&w=120",
      role: "Developer",
      successfulOrders: 32,
      disputeRate: 0,
      fraudFlags: 0,
    },
    seller: {
      name: "DigitalCloud Inc.",
      avatar:
        "https://images.unsplash.com/photo-1560250097-0b93528c311a?crop=entropy&cs=srgb&fm=jpg&q=85&w=120&h=120",
      role: "API Provider",
      successfulOrders: 67,
      complaintRate: 1,
      fraudFlags: 0,
    },
    isNewPair: false,
    isNewContext: false,
    valueCategory: "low",
  },
  {
    id: "prod_med",
    name: "Limited Edition Sneakers",
    priceLabel: "$299.00",
    priceValue: 299,
    category: "Fashion & Lifestyle",
    image:
      "https://images.unsplash.com/photo-1544441893-aa0f3f67b48a?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
    description: "Exclusive limited drop — Air Force collab, size 10, mint condition sealed.",
    expectedRisk: "medium",
    buyer: {
      name: "Alex Johnson",
      avatar:
        "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?crop=entropy&cs=srgb&fm=jpg&q=85&w=120&h=120",
      role: "Buyer",
      successfulOrders: 10,
      disputeRate: 8,
      fraudFlags: 0,
    },
    seller: {
      name: "UrbanKicks Store",
      avatar:
        "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?crop=entropy&cs=srgb&fm=jpg&q=85&w=120&h=120",
      role: "Seller",
      successfulOrders: 45,
      complaintRate: 5,
      fraudFlags: 0,
    },
    isNewPair: false,
    isNewContext: false,
    valueCategory: "mid",
  },
  {
    id: "prod_high_mid",
    name: "Collectible Sneakers (Resale)",
    priceLabel: "$195.00",
    priceValue: 195,
    category: "Marketplace Resale",
    image:
      "https://images.unsplash.com/photo-1542291026-7eec264c27ff?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
    description:
      "Limited Jordan resale — unverified marketplace seller. New buyer-seller pair, flagged location.",
    expectedRisk: "high",
    buyer: {
      name: "Jordan Lee",
      avatar:
        "https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?crop=entropy&cs=srgb&fm=jpg&q=85&w=120&h=120",
      role: "New Buyer",
      successfulOrders: 2,
      disputeRate: 15,
      fraudFlags: 0,
    },
    seller: {
      name: "Sole Collector Co.",
      avatar:
        "https://images.unsplash.com/photo-1463453091185-61582044d556?crop=entropy&cs=srgb&fm=jpg&q=85&w=120&h=120",
      role: "Unverified Seller",
      successfulOrders: 4,
      complaintRate: 30,
      fraudFlags: 1,
    },
    isNewPair: true,
    isNewContext: true,
    valueCategory: "mid",
  },
  {
    id: "prod_med_high",
    name: "Swiss Luxury Watch",
    priceLabel: "$850.00",
    priceValue: 850,
    category: "Luxury Goods",
    image:
      "https://images.unsplash.com/photo-1523275335684-37898b6baf30?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
    description:
      "Authentic Swiss automatic — certified seller, trusted buyer with proven order history.",
    expectedRisk: "medium",
    buyer: {
      name: "Emma Wilson",
      avatar:
        "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?crop=entropy&cs=srgb&fm=jpg&q=85&w=120&h=120",
      role: "Trusted Buyer",
      successfulOrders: 12,
      disputeRate: 4,
      fraudFlags: 0,
    },
    seller: {
      name: "LuxeTime Boutique",
      avatar:
        "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?crop=entropy&cs=srgb&fm=jpg&q=85&w=120&h=120",
      role: "Certified Seller",
      successfulOrders: 55,
      complaintRate: 4,
      fraudFlags: 0,
    },
    isNewPair: false,
    isNewContext: false,
    valueCategory: "high",
  },
  {
    id: "prod_high",
    name: "MacBook Pro M3 Max",
    priceLabel: "$3,499.00",
    priceValue: 3499,
    category: "Electronics",
    image:
      "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?crop=entropy&cs=srgb&fm=jpg&q=85&w=800",
    description: "Space Black, M3 Max chip, 36GB RAM, 1TB SSD — factory sealed box.",
    expectedRisk: "high",
    buyer: {
      name: "Marcus Chen",
      avatar:
        "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?crop=entropy&cs=srgb&fm=jpg&q=85&w=120&h=120",
      role: "First-time Buyer",
      successfulOrders: 2,
      disputeRate: 10,
      fraudFlags: 0,
    },
    seller: {
      name: "TechMart Official",
      avatar:
        "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?crop=entropy&cs=srgb&fm=jpg&q=85&w=120&h=120",
      role: "New Seller",
      successfulOrders: 8,
      complaintRate: 15,
      fraudFlags: 0,
    },
    isNewPair: true,
    isNewContext: true,
    valueCategory: "high",
  },
];

export function calculateBuyerTrust(buyer) {
  const bt =
    40 + 2 * buyer.successfulOrders - 15 * (buyer.disputeRate / 100) - 20 * buyer.fraudFlags;
  return Math.min(100, Math.max(0, bt));
}

export function calculateSellerTrust(seller) {
  const st =
    50 +
    1.5 * seller.successfulOrders -
    20 * (seller.complaintRate / 100) -
    30 * seller.fraudFlags;
  return Math.min(100, Math.max(0, st));
}

export function calculateTransactionRisk(product) {
  const valueRisk = { low: 5, mid: 15, high: 25 }[product.valueCategory];
  const interactionRisk = product.isNewPair ? 20 : 0;
  const contextRisk = product.isNewContext ? 10 : 0;
  return { valueRisk, interactionRisk, contextRisk, total: valueRisk + interactionRisk + contextRisk };
}

export function calculateRisk(product) {
  const bt = calculateBuyerTrust(product.buyer);
  const st = calculateSellerTrust(product.seller);
  const { valueRisk, interactionRisk, contextRisk, total: tr } = calculateTransactionRisk(product);
  const score = 100 - 0.4 * bt - 0.4 * st + tr;
  const level = score <= 30 ? "low" : score <= 60 ? "medium" : "high";
  return { score, level, bt, st, tr, valueRisk, interactionRisk, contextRisk };
}

export function getBuyerTrustLevel(orders) {
  if (orders >= 15) return { level: 3, label: "Level 3", desc: "Verified" };
  if (orders >= 6) return { level: 2, label: "Level 2", desc: "Trusted" };
  if (orders >= 3) return { level: 1, label: "Level 1", desc: "New" };
  return { level: 0, label: "Level 0", desc: "Unknown" };
}

export function getSellerTrustLevel(orders) {
  if (orders >= 100) return { level: 3, label: "Level 3", desc: "Verified" };
  if (orders >= 30) return { level: 2, label: "Level 2", desc: "Trusted" };
  if (orders >= 10) return { level: 1, label: "Level 1", desc: "New" };
  return { level: 0, label: "Level 0", desc: "Unknown" };
}

export const RISK_CONFIG = {
  low: {
    label: "LOW RISK",
    color: "#10B981",
    bgSoft: "#ECFDF5",
    textDark: "#047857",
    border: "#A7F3D0",
    paymentStatus: "Captured",
    paymentIcon: "✅",
    paymentNote: "Funds captured immediately. Released to seller post-delivery.",
  },
  medium: {
    label: "MEDIUM RISK",
    color: "#F59E0B",
    bgSoft: "#FFFBEB",
    textDark: "#B45309",
    border: "#FDE68A",
    paymentStatus: "Authorized",
    paymentIcon: "⏳",
    paymentNote: "Payment authorized. Funds held pending buyer confirmation.",
  },
  high: {
    label: "HIGH RISK",
    color: "#E11D48",
    bgSoft: "#FFF1F2",
    textDark: "#BE123C",
    border: "#FECDD3",
    paymentStatus: "Held",
    paymentIcon: "🔒",
    paymentNote: "Payment held. Multi-factor verification required for release.",
  },
};

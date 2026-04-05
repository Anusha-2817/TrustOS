import React, { useState, useEffect } from "react";
import {
  ArrowLeft,
  Zap,
  Shield,
  Package,
} from "lucide-react";
import {
  PRODUCTS,
  calculateBuyerTrust,
  calculateSellerTrust,
  getBuyerTrustLevel,
  getSellerTrustLevel,
  RISK_CONFIG,
} from "@/utils/riskEngine";
import {
  fetchTrustPreviewForProduct,
  evaluateFullTransaction,
  mapFullEvaluationToRiskData,
  scenarioFromRiskLevel,
  ApiError,
} from "@/services/api";
import RiskSimulatorPanel from "@/components/RiskSimulatorPanel";
import DemoTransactionCases from "@/components/DemoTransactionCases";

const riskBadgeStyle = (level) =>
  ({
    low: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    medium: "bg-amber-50 text-amber-700 border border-amber-200",
    high: "bg-rose-50 text-rose-700 border border-rose-200",
  })[level];

/** Product grid cards: border + glow keyed by expected risk (LOW green, MEDIUM yellow, HIGH red). */
const PRODUCT_CARD_RISK = {
  low: {
    border: "border-emerald-300/70 dark:border-emerald-500/40",
    borderHover: "hover:border-emerald-400 dark:hover:border-emerald-400/55",
    shadow:
      "shadow-[0_0_0_1px_rgba(16,185,129,0.18),0_4px_6px_-1px_rgb(15_23_42/0.05),0_14px_36px_-14px_rgba(16,185,129,0.18)]",
    darkShadow:
      "dark:shadow-[0_0_0_1px_rgba(52,211,153,0.14),0_8px_28px_-10px_rgb(0_0_0/0.18),0_0_44px_-14px_rgba(16,185,129,0.14)]",
    shadowHover:
      "hover:shadow-[0_0_0_1px_rgba(16,185,129,0.28),0_18px_44px_-12px_rgba(16,185,129,0.24)]",
    darkShadowHover:
      "dark:hover:shadow-[0_0_0_1px_rgba(52,211,153,0.22),0_0_52px_-12px_rgba(16,185,129,0.16),0_12px_36px_-10px_rgb(0_0_0/0.2)]",
    ring: "ring-emerald-500/60 dark:ring-emerald-400/50",
    selectedShadow: "shadow-[0_0_36px_-8px_rgba(16,185,129,0.4)]",
    imgRing: "ring-emerald-400/22 dark:ring-emerald-500/28",
    imgTint: "to-emerald-400/8 dark:to-emerald-400/12",
    footerTint: "to-emerald-50/35 dark:to-emerald-950/28",
    cardBg: "to-emerald-50/45 dark:to-emerald-950/22",
  },
  medium: {
    border: "border-amber-300/75 dark:border-amber-500/42",
    borderHover: "hover:border-amber-400 dark:hover:border-amber-400/55",
    shadow:
      "shadow-[0_0_0_1px_rgba(245,158,11,0.2),0_4px_6px_-1px_rgb(15_23_42/0.05),0_14px_36px_-14px_rgba(245,158,11,0.18)]",
    darkShadow:
      "dark:shadow-[0_0_0_1px_rgba(251,191,36,0.16),0_8px_28px_-10px_rgb(0_0_0/0.18),0_0_44px_-14px_rgba(245,158,11,0.14)]",
    shadowHover:
      "hover:shadow-[0_0_0_1px_rgba(245,158,11,0.32),0_18px_44px_-12px_rgba(245,158,11,0.22)]",
    darkShadowHover:
      "dark:hover:shadow-[0_0_0_1px_rgba(251,191,36,0.24),0_0_52px_-12px_rgba(245,158,11,0.18),0_12px_36px_-10px_rgb(0_0_0/0.2)]",
    ring: "ring-amber-500/60 dark:ring-amber-400/50",
    selectedShadow: "shadow-[0_0_36px_-8px_rgba(245,158,11,0.38)]",
    imgRing: "ring-amber-400/22 dark:ring-amber-500/28",
    imgTint: "to-amber-400/8 dark:to-amber-400/12",
    footerTint: "to-amber-50/40 dark:to-amber-950/26",
    cardBg: "to-amber-50/50 dark:to-amber-950/24",
  },
  high: {
    border: "border-rose-300/75 dark:border-rose-500/42",
    borderHover: "hover:border-rose-400 dark:hover:border-rose-400/55",
    shadow:
      "shadow-[0_0_0_1px_rgba(225,29,72,0.18),0_4px_6px_-1px_rgb(15_23_42/0.05),0_14px_36px_-14px_rgba(225,29,72,0.16)]",
    darkShadow:
      "dark:shadow-[0_0_0_1px_rgba(251,113,133,0.14),0_8px_28px_-10px_rgb(0_0_0/0.18),0_0_44px_-14px_rgba(225,29,72,0.14)]",
    shadowHover:
      "hover:shadow-[0_0_0_1px_rgba(225,29,72,0.28),0_18px_44px_-12px_rgba(225,29,72,0.22)]",
    darkShadowHover:
      "dark:hover:shadow-[0_0_0_1px_rgba(251,113,133,0.22),0_0_52px_-12px_rgba(225,29,72,0.16),0_12px_36px_-10px_rgb(0_0_0/0.2)]",
    ring: "ring-rose-500/60 dark:ring-rose-400/50",
    selectedShadow: "shadow-[0_0_36px_-8px_rgba(225,29,72,0.38)]",
    imgRing: "ring-rose-400/22 dark:ring-rose-500/28",
    imgTint: "to-rose-400/8 dark:to-rose-400/12",
    footerTint: "to-rose-50/40 dark:to-rose-950/28",
    cardBg: "to-rose-50/45 dark:to-rose-950/24",
  },
};

function RiskGauge({ score, level, animated }) {
  const cfg = RISK_CONFIG[level];
  const pct = Math.min(100, Math.max(0, score));
  const r = 40,
    cx = 50,
    cy = 50;
  const circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - pct / 100);

  return (
    <div className="flex flex-col items-center gap-3 animate-scale-in">
      <div className="relative w-28 h-28">
        <svg
          viewBox="0 0 100 100"
          className="w-full h-full -rotate-90 drop-shadow-[0_0_10px_rgba(45,212,191,0.2)] dark:drop-shadow-[0_0_14px_rgba(94,234,212,0.15)]"
        >
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke="currentColor"
            strokeWidth="8"
            className="text-slate-200 dark:text-slate-600"
          />
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={cfg.color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={animated ? offset : circumference}
            className={animated ? "risk-stroke" : ""}
            style={{
              transition: "stroke-dashoffset 1.2s ease-out",
              filter: `drop-shadow(0 0 8px ${cfg.color}55)`,
            }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold font-mono text-slate-900 dark:text-slate-100 animate-count-up">
            {score.toFixed(0)}
          </span>
          <span className="text-[10px] text-slate-500 dark:text-slate-400 font-medium">/ 100</span>
        </div>
      </div>
      <span
        className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wide ${riskBadgeStyle(level)}`}
      >
        <span
          className="inline-block w-1.5 h-1.5 rounded-full mr-1.5"
          style={{ backgroundColor: cfg.color }}
        />
        {cfg.label}
      </span>
    </div>
  );
}

function apiTrustBadgeClass(levelLabel) {
  const L = String(levelLabel || "").toLowerCase();
  if (L === "high") return "bg-emerald-100 text-emerald-700";
  if (L === "medium") return "bg-amber-100 text-amber-700";
  return "bg-rose-100 text-rose-700";
}

function TrustBadge({ person, type, score, orders, apiLevelLabel, loading }) {
  const tierFallback =
    type === "buyer" ? getBuyerTrustLevel(orders) : getSellerTrustLevel(orders);
  const levelColors = [
    "bg-rose-100 text-rose-700",
    "bg-amber-100 text-amber-700",
    "bg-blue-100 text-blue-700",
    "bg-emerald-100 text-emerald-700",
  ];
  const badgeLabel = apiLevelLabel || tierFallback.label;
  const badgeClass = apiLevelLabel
    ? apiTrustBadgeClass(apiLevelLabel)
    : levelColors[tierFallback.level];
  const scoreNum = typeof score === "number" && !Number.isNaN(score) ? score : null;

  return (
    <div
      className="trust-card rounded-xl p-4"
      data-testid={`${type}-trust-badge`}
    >
      <div className="flex items-start gap-3">
        <img
          src={person.avatar}
          alt={person.name}
          className="w-10 h-10 rounded-full object-cover border-2 border-slate-100 dark:border-slate-600"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">
              {person.name}
            </span>
            <span
              className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full flex-shrink-0 ${badgeClass}`}
            >
              {loading ? "…" : badgeLabel}
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-2">{person.role}</p>
          <div className="flex items-center gap-2">
            <div className="flex-1 bg-slate-100 dark:bg-slate-700/80 rounded-full h-1.5 overflow-hidden">
              <div
                className={`h-1.5 rounded-full transition-all duration-700 ${loading ? "animate-pulse bg-slate-300 dark:bg-slate-500 w-1/3" : ""}`}
                style={
                  loading
                    ? undefined
                    : {
                        width: `${Math.min(100, Math.max(0, scoreNum ?? 0))}%`,
                        backgroundColor:
                          (scoreNum ?? 0) > 70
                            ? "#10B981"
                            : (scoreNum ?? 0) > 40
                              ? "#F59E0B"
                              : "#E11D48",
                      }
                }
              />
            </div>
            <span className="text-xs font-mono font-semibold text-slate-700 dark:text-slate-300 flex-shrink-0 w-8 text-right">
              {loading ? "—" : scoreNum != null ? scoreNum.toFixed(0) : "—"}
            </span>
          </div>
          <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">
            {orders} orders ·{" "}
            {type === "buyer"
              ? `${person.disputeRate}% dispute`
              : `${person.complaintRate}% complaint`}{" "}
            rate
          </p>
        </div>
      </div>
    </div>
  );
}

function ProductCard({ product, onSelect, selected }) {
  const cfg = RISK_CONFIG[product.expectedRisk];
  const pc = PRODUCT_CARD_RISK[product.expectedRisk] || PRODUCT_CARD_RISK.medium;
  return (
    <button
      onClick={() => onSelect(product)}
      data-testid={`product-card-${product.id}`}
      className={`group w-full text-left rounded-2xl overflow-hidden border transition-all duration-300 ease-out
        bg-gradient-to-br from-white via-slate-50/90 ${pc.cardBg}
        dark:from-slate-600/35 dark:via-slate-700/65
        ${pc.border} ${pc.borderHover}
        ${pc.shadow} ${pc.darkShadow}
        ${pc.shadowHover} ${pc.darkShadowHover}
        hover:-translate-y-1
        ${
          selected
            ? `ring-2 ${pc.ring} ring-offset-2 ring-offset-[hsl(210_42%_97%)] dark:ring-offset-[hsl(220_18%_19%)] ${pc.selectedShadow}`
            : ""
        }`}
    >
      <div className={`h-36 overflow-hidden relative ring-1 ring-inset ${pc.imgRing}`}>
        <div
          className={`absolute inset-0 z-[1] pointer-events-none bg-gradient-to-t from-slate-900/10 via-transparent ${pc.imgTint} dark:from-slate-950/50`}
          aria-hidden
        />
        <img
          src={product.image}
          alt={product.name}
          className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
        />
      </div>
      <div
        className={`p-4 bg-gradient-to-b from-white/90 via-white/70 ${pc.footerTint} dark:from-slate-800/40 dark:via-slate-800/25 backdrop-blur-[1px]`}
      >
        <div className="flex items-start justify-between gap-2 mb-1">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 leading-tight">
            {product.name}
          </h3>
          <span
            className={`flex-shrink-0 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase`}
            style={{
              backgroundColor: cfg.bgSoft,
              color: cfg.textDark,
              border: `1px solid ${cfg.border}`,
            }}
          >
            {product.expectedRisk}
          </span>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">{product.category}</p>
        <div className="flex items-center justify-between">
          <span className="text-lg font-bold text-slate-900 dark:text-slate-100 font-mono">
            {product.priceLabel}
          </span>
          <span className="text-xs text-slate-400 dark:text-slate-500">
            {product.buyer.name.split(" ")[0]} →{" "}
            {product.seller.name.split(" ")[0]}
          </span>
        </div>
      </div>
    </button>
  );
}

export default function OrderScreen({ onOrderPlaced, addLog }) {
  const [selected, setSelected] = useState(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [riskResult, setRiskResult] = useState(null);
  const [trustPreview, setTrustPreview] = useState(null);
  const [trustLoading, setTrustLoading] = useState(false);
  const [trustError, setTrustError] = useState(null);
  const [evaluateError, setEvaluateError] = useState(null);

  useEffect(() => {
    if (!selected) {
      setTrustPreview(null);
      setTrustError(null);
      return;
    }
    let cancelled = false;
    setTrustLoading(true);
    setTrustError(null);
    setTrustPreview(null);
    fetchTrustPreviewForProduct(selected)
      .then((preview) => {
        if (!cancelled) setTrustPreview(preview);
      })
      .catch((err) => {
        if (!cancelled) {
          setTrustError(err instanceof ApiError ? err.message : String(err.message || err));
          addLog("Trust API unavailable — showing local estimates.", "high");
        }
      })
      .finally(() => {
        if (!cancelled) setTrustLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, addLog]);

  const handleSelectProduct = (product) => {
    setSelected(product);
    setRiskResult(null);
    setEvaluateError(null);
  };

  const handleEvaluateRisk = async () => {
    if (!selected) return;
    setIsEvaluating(true);
    setRiskResult(null);
    setEvaluateError(null);
    addLog(`Analyzing transaction: ${selected.name}`, "system");
    addLog("Calling TrustOS API: trust → risk → decision...", "info");
    try {
      const full = await evaluateFullTransaction(selected);
      const risk = mapFullEvaluationToRiskData(full);
      risk.apiScenario = scenarioFromRiskLevel(risk.level);
      setRiskResult(risk);
      addLog(
        `BT=${risk.bt.toFixed(1)}, ST=${risk.st.toFixed(1)}, TR=+${risk.tr}`,
        "info",
      );
      addLog(
        `Score: ${risk.score.toFixed(1)} → ${risk.level.toUpperCase()} RISK`,
        risk.level,
      );
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err.message || err);
      setEvaluateError(msg);
      addLog(`Evaluation failed: ${msg}`, "high");
    } finally {
      setIsEvaluating(false);
    }
  };

  const risk = riskResult;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="animate-fade-in rounded-2xl border border-teal-100/50 bg-gradient-trust-hero px-5 py-6 shadow-trust-soft sm:px-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">
          Step 1 of 5
        </p>
        <h1 className="font-display text-3xl font-semibold text-slate-900 dark:text-slate-100 tracking-tight">
          Place an Order
        </h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1">
          Select a product to simulate a TrustOS-controlled payment flow.
        </p>
      </div>

      <DemoTransactionCases />

      {!selected ? (
        /* Product Selection Grid */
        <div className="animate-fade-in-delay-1">
          <div className="flex items-center gap-2 mb-4">
            <Package className="w-4 h-4 text-teal-600 dark:text-teal-400 icon-glow-teal-sm shrink-0" />
            <p className="text-sm font-medium text-slate-600 dark:text-slate-300">
              Each product represents a different risk profile
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {PRODUCTS.map((p) => (
              <ProductCard
                key={p.id}
                product={p}
                onSelect={handleSelectProduct}
                selected={false}
              />
            ))}
          </div>
          <div className="mt-8 max-w-3xl">
            <RiskSimulatorPanel addLog={addLog} />
          </div>
        </div>
      ) : (
        /* Risk Evaluation Panel */
        <div className="animate-fade-in">
          <button
            onClick={() => {
              setSelected(null);
              setRiskResult(null);
              setEvaluateError(null);
            }}
            className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 mb-5 transition-colors"
            data-testid="back-to-products-btn"
          >
            <ArrowLeft className="w-4 h-4" /> Change product
          </button>

          <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
            {/* Product Card */}
            <div className="lg:col-span-2 trust-card rounded-2xl overflow-hidden animate-fade-in-delay-1">
              <div className="h-48 overflow-hidden">
                <img
                  src={selected.image}
                  alt={selected.name}
                  className="w-full h-full object-cover"
                />
              </div>
              <div className="p-5">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                  {selected.category}
                </span>
                <h2 className="font-display text-xl font-semibold text-slate-900 dark:text-slate-100 mt-1 mb-2 tracking-tight">
                  {selected.name}
                </h2>
                <p className="text-sm text-slate-500 dark:text-slate-400 mb-4 leading-relaxed">
                  {selected.description}
                </p>
                <div className="flex items-center justify-between">
                  <span className="text-2xl font-bold font-mono text-slate-900 dark:text-slate-100">
                    {selected.priceLabel}
                  </span>
                  <span
                    className={`px-2.5 py-1 rounded-full text-xs font-semibold`}
                    style={{
                      backgroundColor:
                        RISK_CONFIG[selected.expectedRisk].bgSoft,
                      color: RISK_CONFIG[selected.expectedRisk].textDark,
                    }}
                  >
                    Expected: {selected.expectedRisk.toUpperCase()}
                  </span>
                </div>
              </div>
            </div>

            {/* Trust + Risk Panel */}
            <div className="lg:col-span-3 space-y-4 animate-fade-in-delay-2">
              {/* Trust Badges */}
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-2 flex items-center gap-1.5">
                  <Shield className="w-3 h-3 text-teal-600 dark:text-teal-400 icon-glow-teal-sm" strokeWidth={2.5} /> Trust Profiles
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <TrustBadge
                    person={selected.buyer}
                    type="buyer"
                    score={
                      trustPreview?.buyer?.score ??
                      (!trustLoading && trustError != null
                        ? calculateBuyerTrust(selected.buyer)
                        : null)
                    }
                    apiLevelLabel={trustPreview?.buyer?.level}
                    loading={trustLoading}
                    orders={selected.buyer.successfulOrders}
                  />
                  <TrustBadge
                    person={selected.seller}
                    type="seller"
                    score={
                      trustPreview?.seller?.score ??
                      (!trustLoading && trustError != null
                        ? calculateSellerTrust(selected.seller)
                        : null)
                    }
                    apiLevelLabel={trustPreview?.seller?.level}
                    loading={trustLoading}
                    orders={selected.seller.successfulOrders}
                  />
                </div>
                {trustError && (
                  <p className="text-[11px] text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/50 rounded-lg px-3 py-2">
                    Could not load live trust scores ({trustError}). Estimates shown if available after load finishes.
                  </p>
                )}
              </div>

              {/* Evaluate Button */}
              {!riskResult && (
                <>
                {evaluateError && (
                  <div className="rounded-xl border border-rose-200 dark:border-rose-900/50 bg-rose-50 dark:bg-rose-950/35 text-rose-800 dark:text-rose-200 text-sm px-4 py-3">
                    {evaluateError}
                  </div>
                )}
                <button
                  onClick={handleEvaluateRisk}
                  disabled={isEvaluating}
                  data-testid="evaluate-risk-btn"
                  className="w-full flex items-center justify-center gap-2.5 py-3.5 bg-teal-950 text-white rounded-xl font-semibold text-sm hover:bg-teal-900 shadow-trust disabled:opacity-60 disabled:cursor-not-allowed transition-all duration-200"
                >
                  {isEvaluating ? (
                    <>
                      <svg
                        className="animate-spin-slow w-4 h-4"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                        />
                      </svg>
                      Evaluating risk...
                    </>
                  ) : (
                    <>
                      <Zap className="w-4 h-4 icon-glow-teal-sm text-white drop-shadow-[0_0_8px_rgba(255,255,255,0.35)]" />
                      Evaluate Risk Score
                    </>
                  )}
                </button>
                </>
              )}

              {/* Risk Result */}
              {riskResult && (
                <div className="animate-scale-in space-y-4">
                  <div className="trust-card rounded-2xl p-5">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">
                          Risk Assessment
                        </p>
                        <h3 className="font-display text-lg font-semibold text-slate-900 dark:text-slate-100 tracking-tight">
                          Score Breakdown
                        </h3>
                      </div>
                      <RiskGauge
                        score={riskResult.score}
                        level={riskResult.level}
                        animated
                      />
                    </div>
                    <div className="space-y-2 text-sm">
                      {[
                        {
                          label: "Buyer Trust (BT)",
                          value: `${riskResult.bt.toFixed(1)} / 100`,
                          note:
                            "→ −" +
                            (riskResult.raw?.risk_components?.buyer_trust_reduction ??
                              0.4 * riskResult.bt
                            ).toFixed(1) +
                            " pts",
                        },
                        {
                          label: "Seller Trust (ST)",
                          value: `${riskResult.st.toFixed(1)} / 100`,
                          note:
                            "→ −" +
                            (riskResult.raw?.risk_components?.seller_trust_reduction ??
                              0.4 * riskResult.st
                            ).toFixed(1) +
                            " pts",
                        },
                        {
                          label: "Value Risk",
                          value: `+${riskResult.valueRisk} pts`,
                          note:
                            selected.valueCategory === "low"
                              ? "< ₹3K"
                              : selected.valueCategory === "mid"
                                ? "₹3K–₹10K"
                                : "> ₹10K",
                        },
                        {
                          label: "Interaction Risk",
                          value: `+${riskResult.interactionRisk} pts`,
                          note: selected.isNewPair ? "New pair" : "Known pair",
                        },
                        {
                          label: "Context Risk",
                          value: `+${riskResult.contextRisk} pts`,
                          note: selected.isNewContext ? "New device" : "Normal",
                        },
                      ].map((row) => (
                        <div
                          key={row.label}
                          className="flex items-center justify-between py-1.5 border-b border-slate-50 dark:border-slate-700/60"
                        >
                          <span className="text-slate-600 dark:text-slate-300">{row.label}</span>
                          <div className="text-right">
                            <span className="font-mono font-semibold text-slate-900 dark:text-slate-100">
                              {row.value}
                            </span>
                            <span className="text-slate-400 dark:text-slate-500 text-xs ml-2">
                              {row.note}
                            </span>
                          </div>
                        </div>
                      ))}
                      <div className="flex items-center justify-between pt-2">
                        <span className="font-semibold text-slate-900 dark:text-slate-100">
                          Final Risk Score
                        </span>
                        <span className="font-mono font-bold text-lg text-slate-900 dark:text-slate-100">
                          {riskResult.score.toFixed(1)}
                        </span>
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => onOrderPlaced(selected, riskResult)}
                    data-testid="place-order-btn"
                    className="w-full py-3.5 rounded-xl font-bold text-white text-sm transition-all duration-200 hover:opacity-90 active:scale-[0.99]"
                    style={{
                      backgroundColor: RISK_CONFIG[riskResult.level].color,
                    }}
                  >
                    Place Order — {selected.priceLabel}
                  </button>
                  <p className="text-center text-xs text-slate-400 dark:text-slate-500 flex items-center justify-center gap-1.5">
                    <Shield className="w-3 h-3 text-teal-600 dark:text-teal-400 icon-glow-teal-sm shrink-0" strokeWidth={2.5} />
                    Settlement controlled by TrustOS
                  </p>
                </div>
              )}
            </div>
          </div>
          <div className="mt-6">
            <RiskSimulatorPanel addLog={addLog} />
          </div>
        </div>
      )}
    </div>
  );
}

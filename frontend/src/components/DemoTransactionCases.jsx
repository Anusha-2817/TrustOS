import React, { useState } from "react";
import { Layers, Sparkles } from "lucide-react";
import { TRUSTOS_DEMO_TRANSACTION_CASES } from "@/data/trustosDemoTransactions";
import { postEvaluateProduct, ApiError } from "@/services/api";
import { RISK_CONFIG } from "@/utils/riskEngine";
import {
  buildEvaluateProductExplainability,
  formatSignalTag,
} from "@/utils/evaluateProductExplainability";

/** 0.25s ease for hovers / interactive feedback */
const T =
  "transition-[transform,box-shadow,border-color,background-color,color,opacity] duration-[250ms] [transition-timing-function:ease]";

const RISK_CARD = {
  low: {
    border: "border-l-[3px] border-l-emerald-500/90 dark:border-l-emerald-400/75",
    hover:
      "hover:shadow-[0_10px_28px_-8px_rgba(16,185,129,0.22)] hover:border-emerald-200/70 dark:hover:border-emerald-800/50",
    value: "text-emerald-700 dark:text-emerald-300",
    dot: "bg-emerald-500/85 dark:bg-emerald-400/75",
    iconBg: "bg-emerald-600/10 dark:bg-emerald-400/15 text-emerald-700 dark:text-emerald-300 ring-emerald-500/20 dark:ring-emerald-400/25",
    tileHover:
      "hover:shadow-[0_6px_18px_-6px_rgba(16,185,129,0.18)] hover:border-emerald-200/60 dark:hover:border-emerald-800/40",
  },
  medium: {
    border: "border-l-[3px] border-l-amber-500/95 dark:border-l-amber-400/80",
    hover:
      "hover:shadow-[0_10px_28px_-8px_rgba(245,158,11,0.26)] hover:border-amber-200/80 dark:hover:border-amber-800/45",
    value: "text-amber-700 dark:text-amber-300",
    dot: "bg-amber-500/90 dark:bg-amber-400/80",
    iconBg: "bg-amber-500/12 dark:bg-amber-400/15 text-amber-800 dark:text-amber-300 ring-amber-500/25 dark:ring-amber-400/25",
    tileHover:
      "hover:shadow-[0_6px_18px_-6px_rgba(245,158,11,0.22)] hover:border-amber-200/65 dark:hover:border-amber-800/40",
  },
  high: {
    border: "border-l-[3px] border-l-rose-500/95 dark:border-l-rose-400/80",
    hover:
      "hover:shadow-[0_10px_28px_-8px_rgba(225,29,72,0.24)] hover:border-rose-200/80 dark:hover:border-rose-900/45",
    value: "text-rose-700 dark:text-rose-300",
    dot: "bg-rose-500/90 dark:bg-rose-400/80",
    iconBg: "bg-rose-600/10 dark:bg-rose-400/15 text-rose-700 dark:text-rose-300 ring-rose-500/20 dark:ring-rose-400/25",
    tileHover:
      "hover:shadow-[0_6px_18px_-6px_rgba(225,29,72,0.2)] hover:border-rose-200/65 dark:hover:border-rose-900/40",
  },
};

/** Demo scenario button chrome: LOW green, MEDIUM yellow, HIGH red (by scenario intent). */
const DEMO_BTN = {
  low: {
    idle:
      "border-emerald-300/70 dark:border-emerald-500/38 bg-slate-50/90 dark:bg-slate-800/60 text-slate-800 dark:text-slate-200 enabled:hover:bg-emerald-50/70 dark:enabled:hover:bg-emerald-950/35 enabled:hover:border-emerald-400/85 dark:enabled:hover:border-emerald-500/45",
    active:
      "bg-emerald-50 dark:bg-emerald-950/45 border-emerald-400 dark:border-emerald-600 text-emerald-950 dark:text-emerald-100 ring-1 ring-emerald-400/45 dark:ring-emerald-500/35",
  },
  medium: {
    idle:
      "border-amber-300/75 dark:border-amber-500/40 bg-slate-50/90 dark:bg-slate-800/60 text-slate-800 dark:text-slate-200 enabled:hover:bg-amber-50/75 dark:enabled:hover:bg-amber-950/30 enabled:hover:border-amber-400/90 dark:enabled:hover:border-amber-500/48",
    active:
      "bg-amber-50 dark:bg-amber-950/40 border-amber-400 dark:border-amber-600 text-amber-950 dark:text-amber-100 ring-1 ring-amber-400/50 dark:ring-amber-500/38",
  },
  high: {
    idle:
      "border-rose-300/75 dark:border-rose-500/40 bg-slate-50/90 dark:bg-slate-800/60 text-slate-800 dark:text-slate-200 enabled:hover:bg-rose-50/75 dark:enabled:hover:bg-rose-950/32 enabled:hover:border-rose-400/90 dark:enabled:hover:border-rose-500/48",
    active:
      "bg-rose-50 dark:bg-rose-950/40 border-rose-400 dark:border-rose-600 text-rose-950 dark:text-rose-100 ring-1 ring-rose-400/45 dark:ring-rose-500/38",
  },
};

function demoScenarioRiskTier(id) {
  if (id === "low-risk" || id === "high-value-trusted") return "low";
  if (id === "medium-risk") return "medium";
  return "high";
}

function decisionToLevel(decision) {
  const d = String(decision || "").toLowerCase();
  if (d === "low") return "low";
  if (d === "high") return "high";
  return "medium";
}

function fmtRisk(n) {
  if (typeof n !== "number" || Number.isNaN(n)) return "—";
  return n.toFixed(2);
}

function ExplainabilityPanel({ data, level }) {
  const { reasons, signalTags } = buildEvaluateProductExplainability(data);
  const rk = RISK_CARD[level] || RISK_CARD.medium;

  return (
    <div
      className={[
        "trust-card rounded-xl p-4 border border-slate-200/80 dark:border-slate-600/60 bg-gradient-to-br from-white/80 via-slate-50/40 to-white/60 dark:from-slate-900/30 dark:via-slate-900/20 dark:to-slate-950/40",
        rk.border,
        T,
        "shadow-sm hover:scale-[1.01] hover:z-[1]",
        rk.hover,
      ].join(" ")}
      data-testid="evaluate-product-explainability"
    >
      <div className="flex items-start gap-2.5 mb-2">
        <div
          className={[
            "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ring-1",
            T,
            rk.iconBg,
          ].join(" ")}
        >
          <Sparkles className="h-4 w-4" strokeWidth={2} aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 tracking-tight">
            Why is this risky?
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 leading-relaxed">
            TrustOS synthesized these factors from scores, order context, and review signals.
          </p>
        </div>
      </div>

      <ul className="mt-4 space-y-2.5 text-sm text-slate-700 dark:text-slate-200 leading-relaxed">
        {reasons.map((line, i) => (
          <li key={i} className="flex gap-2.5">
            <span
              className={["mt-2 h-1 w-1 shrink-0 rounded-full", rk.dot].join(" ")}
              aria-hidden
            />
            <span>{line}</span>
          </li>
        ))}
      </ul>

      {signalTags.length > 0 && (
        <div className="mt-5 pt-4 border-t border-slate-200/80 dark:border-slate-600/50">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-2.5">
            Detected signals
          </p>
          <div className="flex flex-wrap gap-2">
            {signalTags.map((s, i) => (
              <span
                key={`${s}-${i}`}
                className={[
                  "inline-block font-mono text-[11px] leading-none px-2.5 py-1.5 rounded-md bg-slate-100/95 dark:bg-slate-800/90 text-slate-800 dark:text-slate-200 border border-slate-200/90 dark:border-slate-600/70 shadow-sm",
                  T,
                  "hover:scale-[1.03] hover:shadow-md",
                ].join(" ")}
              >
                {formatSignalTag(s)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function EvaluateProductResult({ data }) {
  const level = decisionToLevel(data.decision);
  const cfg = RISK_CONFIG[level];
  const rk = RISK_CARD[level] || RISK_CARD.medium;
  const rb = data.risk_breakdown || {};

  const cardShell = [
    "trust-card rounded-xl p-4 border border-slate-200/80 dark:border-slate-600/60 shadow-sm",
    rk.border,
    T,
    "hover:scale-[1.01] hover:z-[1]",
    rk.hover,
  ].join(" ");

  return (
    <div className="mt-5 space-y-4" data-testid="evaluate-product-result">
      <div className={cardShell}>
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-3">
          Risk summary
        </h3>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-1.5">
              Final risk
            </p>
            <span
              className={["inline-flex items-center px-3 py-1 rounded-full text-xs font-bold tracking-wide", T].join(
                " ",
              )}
              style={{
                backgroundColor: cfg.bgSoft,
                color: cfg.textDark,
                border: `1px solid ${cfg.border}`,
              }}
            >
              {String(data.decision || "—").toUpperCase()}
            </span>
          </div>
          <div className="text-right">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-0.5">
              final_risk
            </p>
            <p
              className={["text-2xl font-mono font-bold tabular-nums", T, rk.value].join(" ")}
            >
              {fmtRisk(data.final_risk)}
            </p>
          </div>
        </div>
      </div>

      <div className={cardShell}>
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-3">
          Trust scores
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div
            className={[
              "rounded-lg bg-slate-50/90 dark:bg-slate-800/50 px-3 py-2.5 border border-slate-100 dark:border-slate-700/80",
              T,
              "hover:scale-[1.02] hover:z-[1] shadow-sm",
              rk.tileHover,
            ].join(" ")}
          >
            <p className="text-[10px] font-medium text-slate-500 dark:text-slate-400 mb-1">buyer_trust</p>
            <p className="text-lg font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              {fmtRisk(data.buyer_trust)}
            </p>
          </div>
          <div
            className={[
              "rounded-lg bg-slate-50/90 dark:bg-slate-800/50 px-3 py-2.5 border border-slate-100 dark:border-slate-700/80",
              T,
              "hover:scale-[1.02] hover:z-[1] shadow-sm",
              rk.tileHover,
            ].join(" ")}
          >
            <p className="text-[10px] font-medium text-slate-500 dark:text-slate-400 mb-1">seller_trust</p>
            <p className="text-lg font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              {fmtRisk(data.seller_trust)}
            </p>
          </div>
        </div>
      </div>

      <div className={cardShell}>
        <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-3">
          Risk breakdown
        </h3>
        <ul className="space-y-0 divide-y divide-slate-100 dark:divide-slate-700/80 text-sm">
          {[
            { key: "trust_risk", label: "trust_risk", value: rb.trust_risk },
            { key: "value_risk", label: "value_risk", value: rb.value_risk },
            { key: "context_risk", label: "context_risk", value: rb.context_risk },
            { key: "behavior_risk", label: "behavior_risk", value: data.behavior_risk },
          ].map((row) => (
            <li key={row.key} className="flex items-center justify-between py-2.5 first:pt-0 gap-4">
              <span className="text-slate-600 dark:text-slate-300 font-mono text-xs">{row.label}</span>
              <span className="font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                {fmtRisk(row.value)}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <ExplainabilityPanel data={data} level={level} />
    </div>
  );
}

/**
 * Demo buttons: predefined JSON per case; POST to /evaluate-product; response in state.
 */
export default function DemoTransactionCases() {
  const [activeId, setActiveId] = useState(null);
  const [storedDemoPayload, setStoredDemoPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [evaluateResponse, setEvaluateResponse] = useState(null);
  const [evaluateError, setEvaluateError] = useState(null);

  const handlePick = async (c) => {
    if (loading) return;
    setActiveId(c.id);
    setStoredDemoPayload(c.payload);
    setLoading(true);
    setEvaluateResponse(null);
    setEvaluateError(null);
    try {
      const data = await postEvaluateProduct(c.payload);
      setEvaluateResponse(data);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e?.message || e);
      setEvaluateError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section
      className={[
        "rounded-2xl border border-teal-100/70 dark:border-teal-900/40 bg-white/80 dark:bg-slate-900/40 px-4 py-4 sm:px-5 shadow-sm",
        T,
        "hover:shadow-md hover:shadow-slate-900/[0.06] dark:hover:shadow-black/25",
      ].join(" ")}
      aria-label="TrustOS demo transaction cases"
    >
      <div className="flex items-start gap-2 mb-3">
        <Layers className="w-4 h-4 text-teal-600 dark:text-teal-400 mt-0.5 shrink-0" strokeWidth={2} />
        <div>
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Demo scenarios</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            Each button sends its payload to TrustOS <span className="font-mono">/evaluate-product</span>.
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {TRUSTOS_DEMO_TRANSACTION_CASES.map((c) => {
          const active = activeId === c.id;
          const tier = demoScenarioRiskTier(c.id);
          const db = DEMO_BTN[tier];
          return (
            <button
              key={c.id}
              type="button"
              disabled={loading}
              onClick={() => handlePick(c)}
              title={c.description}
              className={[
                "px-3 py-2 rounded-xl text-left text-xs font-medium border min-w-[8.5rem] flex-1 sm:flex-none sm:min-w-0 will-change-transform",
                T,
                "shadow-sm enabled:hover:scale-[1.03] enabled:hover:shadow-md enabled:hover:shadow-slate-900/10 dark:enabled:hover:shadow-black/30",
                "disabled:opacity-50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:hover:scale-100 disabled:hover:shadow-sm",
                active ? db.active : db.idle,
              ].join(" ")}
            >
              <span className="block truncate">{c.label}</span>
            </button>
          );
        })}
      </div>
      {loading && (
        <p className="text-xs text-slate-600 dark:text-slate-300 mt-3" aria-live="polite">
          Analyzing transaction...
        </p>
      )}
      {evaluateError && !loading && (
        <p
          className="mt-3 text-xs text-rose-800 dark:text-rose-200 bg-rose-50/90 dark:bg-rose-950/35 border border-rose-200/90 dark:border-rose-900/50 rounded-lg px-3 py-2"
          role="alert"
        >
          {evaluateError}
        </p>
      )}
      {storedDemoPayload && !loading && (
        <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-3">
          <span className="font-mono text-teal-800 dark:text-teal-300">{activeId}</span>
          <span className="mx-1.5 text-slate-300 dark:text-slate-600">·</span>
          Last payload price ₹{Number(storedDemoPayload.product_price).toLocaleString("en-IN")}
        </p>
      )}
      {evaluateResponse && !loading && <EvaluateProductResult data={evaluateResponse} />}
    </section>
  );
}

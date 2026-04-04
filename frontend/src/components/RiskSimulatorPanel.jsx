import React, { useState, useEffect, useCallback } from "react";
import { SlidersHorizontal, RefreshCw } from "lucide-react";
import { evaluateSimulator, mapFullEvaluationToRiskData, ApiError } from "@/services/api";
import { RISK_CONFIG } from "@/utils/riskEngine";

export default function RiskSimulatorPanel({ addLog }) {
  const [buyerOrders, setBuyerOrders] = useState(12);
  const [buyerDisputeRate, setBuyerDisputeRate] = useState(8);
  const [orderValue, setOrderValue] = useState(5500);
  const [sellerOrders, setSellerOrders] = useState(40);
  const [sellerComplaintRate, setSellerComplaintRate] = useState(5);
  const [newPair, setNewPair] = useState(false);
  const [newDevice, setNewDevice] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [live, setLive] = useState(null);

  const runEvaluate = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const full = await evaluateSimulator({
        buyerSuccessfulOrders: buyerOrders,
        buyerDisputeRatePercent: buyerDisputeRate,
        sellerSuccessfulOrders: sellerOrders,
        sellerComplaintRatePercent: sellerComplaintRate,
        orderValueInr: orderValue,
        isNewPair: newPair,
        isNewDevice: newDevice,
      });
      const mapped = mapFullEvaluationToRiskData(full);
      setLive(mapped);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e.message || e);
      setErr(msg);
      setLive(null);
      if (addLog) addLog(`Simulator API: ${msg}`, "high");
    } finally {
      setLoading(false);
    }
  }, [
    addLog,
    buyerOrders,
    buyerDisputeRate,
    orderValue,
    sellerOrders,
    sellerComplaintRate,
    newPair,
    newDevice,
  ]);

  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(() => {
      runEvaluate().then(() => {
        if (cancelled) return;
      });
    }, 320);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [runEvaluate]);

  const level = live?.level || "medium";
  const cfg = RISK_CONFIG[level];
  const score = live?.score ?? 0;

  return (
    <div
      className="trust-gradient-accent rounded-2xl overflow-hidden"
      data-testid="risk-simulator-panel"
    >
      <div className="px-4 py-3 border-b border-teal-100/90 flex items-center justify-between gap-2 bg-gradient-to-r from-teal-50/85 via-white/55 to-cyan-50/50">
        <div className="flex items-center gap-2 min-w-0">
          <SlidersHorizontal className="w-4 h-4 text-teal-700 dark:text-teal-400 flex-shrink-0" />
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-wider text-teal-900 dark:text-teal-200">
              Risk simulator
            </p>
            <p className="text-[10px] text-teal-700/90 dark:text-teal-400/90 truncate">
              Drag sliders — score recalculates from past-order style signals + value
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={runEvaluate}
          disabled={loading}
          className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-semibold bg-white dark:bg-slate-800 border border-teal-200 dark:border-teal-700 text-teal-800 dark:text-teal-200 hover:bg-teal-50/80 dark:hover:bg-teal-950/50 disabled:opacity-50"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      <div className="p-4 space-y-4">
        <div>
          <div className="flex justify-between text-[11px] font-medium text-slate-600 dark:text-slate-300 mb-1">
            <span>Buyer successful orders</span>
            <span className="font-mono text-slate-900 dark:text-slate-100">{buyerOrders}</span>
          </div>
          <input
            type="range"
            min={0}
            max={80}
            value={buyerOrders}
            onChange={(e) => setBuyerOrders(Number(e.target.value))}
            className="w-full accent-teal-600"
          />
        </div>

        <div>
          <div className="flex justify-between text-[11px] font-medium text-slate-600 dark:text-slate-300 mb-1">
            <span>Buyer dispute rate</span>
            <span className="font-mono text-slate-900 dark:text-slate-100">{buyerDisputeRate}%</span>
          </div>
          <input
            type="range"
            min={0}
            max={50}
            step={1}
            value={buyerDisputeRate}
            onChange={(e) => setBuyerDisputeRate(Number(e.target.value))}
            className="w-full accent-rose-500"
          />
        </div>

        <div>
          <div className="flex justify-between text-[11px] font-medium text-slate-600 dark:text-slate-300 mb-1">
            <span>Order value (INR)</span>
            <span className="font-mono text-slate-900 dark:text-slate-100">₹{orderValue.toLocaleString("en-IN")}</span>
          </div>
          <input
            type="range"
            min={500}
            max={25000}
            step={100}
            value={orderValue}
            onChange={(e) => setOrderValue(Number(e.target.value))}
            className="w-full accent-amber-500"
          />
        </div>

        <div>
          <div className="flex justify-between text-[11px] font-medium text-slate-600 dark:text-slate-300 mb-1">
            <span>Seller successful orders</span>
            <span className="font-mono text-slate-900 dark:text-slate-100">{sellerOrders}</span>
          </div>
          <input
            type="range"
            min={0}
            max={120}
            value={sellerOrders}
            onChange={(e) => setSellerOrders(Number(e.target.value))}
            className="w-full accent-teal-600"
          />
        </div>

        <div>
          <div className="flex justify-between text-[11px] font-medium text-slate-600 dark:text-slate-300 mb-1">
            <span>Seller complaint rate</span>
            <span className="font-mono text-slate-900 dark:text-slate-100">{sellerComplaintRate}%</span>
          </div>
          <input
            type="range"
            min={0}
            max={50}
            value={sellerComplaintRate}
            onChange={(e) => setSellerComplaintRate(Number(e.target.value))}
            className="w-full accent-orange-500"
          />
        </div>

        <div className="flex flex-wrap gap-3 text-xs">
          <label className="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={newPair}
              onChange={(e) => setNewPair(e.target.checked)}
              className="rounded border-slate-300 text-teal-600"
            />
            <span className="text-slate-700 dark:text-slate-300">New buyer–seller pair</span>
          </label>
          <label className="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={newDevice}
              onChange={(e) => setNewDevice(e.target.checked)}
              className="rounded border-slate-300 text-teal-600"
            />
            <span className="text-slate-700 dark:text-slate-300">New device / context</span>
          </label>
        </div>

        {err && (
          <p className="text-[11px] text-rose-700 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/35 border border-rose-200 dark:border-rose-800/50 rounded-lg px-2 py-1.5">
            {err} — start the API on port 8000 for live scores.
          </p>
        )}

        <div
          className="rounded-xl border p-3 flex items-center justify-between gap-3"
          style={{ borderColor: cfg.border, backgroundColor: cfg.bgSoft }}
        >
          <div>
            <p className="text-[10px] uppercase font-bold text-slate-500 dark:text-slate-400">Live risk score</p>
            <p className="text-2xl font-mono font-bold text-slate-900 dark:text-slate-100">
              {loading ? "…" : live ? score.toFixed(1) : "—"}
            </p>
          </div>
          <span
            className="px-2.5 py-1 rounded-full text-[10px] font-bold uppercase"
            style={{ backgroundColor: cfg.color, color: "#fff" }}
          >
            {loading ? "…" : live ? level : "—"}
          </span>
        </div>
        <p className="text-[10px] text-slate-500 dark:text-slate-400 leading-relaxed">
          Products stay labeled from historical orders and disputes; this panel is a what-if on the same
          TrustOS engine (<code className="text-teal-800 dark:text-teal-300 font-mono text-[9px]">/simulator/evaluate</code>).
        </p>
      </div>
    </div>
  );
}

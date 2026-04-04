import React, { useState, useEffect, useMemo } from 'react';
import { Lock, CreditCard, Shield, ChevronRight, CheckCircle, Clock, CircleDot, SkipForward } from 'lucide-react';
import { RISK_CONFIG } from '@/utils/riskEngine';
import { initiatePayment, scenarioFromRiskLevel, ApiError } from '@/services/api';

const CONTRACT_TO_UI_STATUS = {
  CAPTURED: { key: 'Captured', label: 'Captured' },
  AUTHORIZED: { key: 'Authorized', label: 'Authorized' },
  HELD: { key: 'Held', label: 'Held' },
};

function phaseIcon(state) {
  if (state === 'complete') return CheckCircle;
  if (state === 'active') return CircleDot;
  if (state === 'skipped') return SkipForward;
  return Clock;
}

function defaultLifecycleFromLevel(level) {
  if (level === 'low') {
    return {
      provider: 'Razorpay Simulation',
      phases: [
        { id: 'authorized', label: 'AUTHORIZED', description: 'Payment authorized', state: 'complete' },
        { id: 'held', label: 'HELD', description: 'Escrow bypassed', state: 'skipped' },
        { id: 'captured', label: 'CAPTURED', description: 'Low risk settlement', state: 'complete' },
      ],
      current_phase: 'CAPTURED',
    };
  }
  if (level === 'high') {
    return {
      provider: 'Razorpay Simulation',
      phases: [
        { id: 'authorized', label: 'AUTHORIZED', description: 'Authorization recorded', state: 'complete' },
        { id: 'held', label: 'HELD', description: 'Full hold', state: 'active' },
        { id: 'captured', label: 'CAPTURED', description: 'After verification', state: 'pending' },
      ],
      current_phase: 'HELD',
    };
  }
  return {
    provider: 'Razorpay Simulation',
    phases: [
      { id: 'authorized', label: 'AUTHORIZED', description: 'Capture delayed', state: 'complete' },
      { id: 'held', label: 'HELD', description: 'TrustOS escrow', state: 'active' },
      { id: 'captured', label: 'CAPTURED', description: 'After confirmation / timer', state: 'pending' },
    ],
    current_phase: 'AUTHORIZED',
  };
}

export default function PaymentScreen({ selectedProduct, riskData, onContinue }) {
  const [processing, setProcessing] = useState(true);
  const [contractError, setContractError] = useState(null);
  const [contractStatus, setContractStatus] = useState(null);
  const [lifecycle, setLifecycle] = useState(null);
  const cfg = RISK_CONFIG[riskData.level];

  useEffect(() => {
    let cancelled = false;
    const scenario = riskData.apiScenario || scenarioFromRiskLevel(riskData.level);
    setContractError(null);
    setContractStatus(null);
    setLifecycle(null);
    setProcessing(true);
    initiatePayment({ scenario })
      .then((res) => {
        if (!cancelled) {
          setContractStatus(res?.status ?? null);
          setLifecycle(res?.lifecycle ?? null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setContractError(err instanceof ApiError ? err.message : String(err.message || err));
        }
      })
      .finally(() => {
        if (!cancelled) setProcessing(false);
      });
    return () => {
      cancelled = true;
    };
  }, [riskData.level, riskData.apiScenario]);

  const effectiveLifecycle = useMemo(() => {
    if (lifecycle?.phases?.length) return lifecycle;
    return defaultLifecycleFromLevel(riskData.level);
  }, [lifecycle, riskData.level]);

  const StatusIcon = riskData.level === 'low' ? CheckCircle : riskData.level === 'medium' ? Clock : Lock;
  const mapped = contractStatus ? CONTRACT_TO_UI_STATUS[contractStatus] : null;
  const displayStatusLabel = mapped
    ? `${mapped.label} ${cfg.paymentIcon}`
    : `${cfg.paymentStatus} ${cfg.paymentIcon}`;

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="animate-fade-in">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">Step 2 of 5</p>
        <h1 className="font-display text-3xl font-semibold text-slate-900 dark:text-slate-100 tracking-tight">Payment Processing</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1">TrustOS is managing settlement based on transaction risk.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-5 gap-4 animate-fade-in-delay-1">
        {/* Order Summary */}
        <div className="sm:col-span-2 trust-card rounded-2xl p-5">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-4">Order Summary</p>
          <div className="flex gap-3 mb-4">
            <img src={selectedProduct.image} alt={selectedProduct.name} className="w-14 h-14 rounded-xl object-cover border border-slate-100 dark:border-slate-600" />
            <div>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{selectedProduct.name}</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">{selectedProduct.category}</p>
              <p className="text-lg font-bold font-mono text-slate-900 dark:text-slate-100 mt-1">{selectedProduct.priceLabel}</p>
            </div>
          </div>
          <div className="space-y-2 text-xs text-slate-600 dark:text-slate-300 border-t border-slate-100 dark:border-slate-700/60 pt-3">
            <div className="flex justify-between">
              <span className="text-slate-400 dark:text-slate-500">Buyer</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">{selectedProduct.buyer.name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400 dark:text-slate-500">Seller</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">{selectedProduct.seller.name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400 dark:text-slate-500">Risk Level</span>
              <span className="font-bold uppercase" style={{ color: cfg.color }}>{riskData.level}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400 dark:text-slate-500">Risk Score</span>
              <span className="font-mono font-semibold text-slate-900 dark:text-slate-100">{riskData.score.toFixed(1)}</span>
            </div>
          </div>
        </div>

        {/* Payment Panel */}
        <div className="sm:col-span-3 space-y-4">
          {/* Credit Card Visual */}
          <div
            className="rounded-2xl p-6 text-white relative overflow-hidden"
            style={{
              background:
                'linear-gradient(145deg, hsl(196 55% 18%) 0%, hsl(215 36% 14%) 45%, hsl(196 45% 22%) 100%)',
            }}
            data-testid="payment-card-visual"
          >
            <div className="absolute top-0 right-0 w-48 h-48 rounded-full opacity-10" style={{ background: 'radial-gradient(circle, #94a3b8, transparent)', transform: 'translate(30%, -30%)' }} />
            <div className="relative z-10">
              <div className="flex justify-between items-start mb-8">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 bg-white/20 rounded-lg flex items-center justify-center">
                    <Shield className="w-4 h-4 text-white" />
                  </div>
                  <span className="font-display text-xs font-semibold opacity-90 tracking-wide">TrustOS</span>
                </div>
                <CreditCard className="w-5 h-5 opacity-50" />
              </div>
              <p className="font-mono text-base tracking-widest opacity-70 mb-1">**** **** **** 4829</p>
              <div className="flex justify-between items-end">
                <div>
                  <p className="text-[10px] opacity-50 uppercase tracking-wider">Amount</p>
                  <p className="text-2xl font-bold font-mono">{selectedProduct.priceLabel}</p>
                </div>
                <div className="text-right">
                  <p className="text-[10px] opacity-50 uppercase tracking-wider">Merchant</p>
                  <p className="text-xs font-semibold">{selectedProduct.seller.name}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Status Card */}
          <div
            className="trust-card rounded-2xl p-5 dark:!border-opacity-60"
            style={{ borderColor: cfg.border }}
            data-testid="payment-status-card"
          >
            {processing ? (
              <div className="flex items-center gap-3">
                <svg className="animate-spin-slow w-5 h-5 text-slate-400" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <span className="text-sm text-slate-600 dark:text-slate-300 animate-blink">Calling TrustOS payment contract...</span>
              </div>
            ) : contractError ? (
              <div className="text-sm text-rose-700 dark:text-rose-300">
                <p className="font-semibold mb-1">Could not reach payment API</p>
                <p className="text-xs text-rose-600 dark:text-rose-400">{contractError}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">Showing UI defaults from risk evaluation. Ensure the backend is running on port 8000.</p>
              </div>
            ) : (
              <div className="animate-scale-in">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-full flex items-center justify-center" style={{ backgroundColor: cfg.bgSoft }}>
                      <StatusIcon className="w-4 h-4" style={{ color: cfg.color }} />
                    </div>
                    <div>
                      <p className="text-xs text-slate-400 dark:text-slate-500 uppercase tracking-wider font-semibold">Payment Status</p>
                      <p className="text-base font-bold" style={{ color: cfg.textDark }}>
                        {displayStatusLabel}
                      </p>
                    </div>
                  </div>
                  <span className="px-2.5 py-1 rounded-full text-xs font-bold"
                    style={{ backgroundColor: cfg.bgSoft, color: cfg.textDark, border: `1px solid ${cfg.border}` }}>
                    {riskData.level.toUpperCase()} RISK
                  </span>
                </div>
                {contractStatus && (
                  <p className="text-[10px] font-mono text-slate-400 dark:text-slate-500 mb-1">API: /initiate-payment → {contractStatus}</p>
                )}
                <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">{cfg.paymentNote}</p>

                {/* Razorpay-style settlement lifecycle */}
                <div className="mt-5 pt-4 border-t border-slate-100 dark:border-slate-700/60">
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                      💳 {effectiveLifecycle.provider || 'Razorpay Simulation'}
                    </p>
                    <span className="text-[9px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-mono">
                      AUTHORIZED · HELD · CAPTURED
                    </span>
                  </div>
                  <div className="space-y-0">
                    {effectiveLifecycle.phases.map((ph, idx) => {
                      const Icon = phaseIcon(ph.state);
                      const isLast = idx === effectiveLifecycle.phases.length - 1;
                      const lineDone = ph.state === 'complete' || ph.state === 'skipped';
                      return (
                        <div key={ph.id || ph.label} className="flex gap-3">
                          <div className="flex flex-col items-center w-8 flex-shrink-0">
                            <div
                              className={`w-8 h-8 rounded-full flex items-center justify-center border-2 ${
                                ph.state === 'complete'
                                  ? 'bg-emerald-500 border-emerald-500 text-white'
                                  : ph.state === 'active'
                                    ? 'bg-blue-600 border-blue-600 text-white ring-4 ring-blue-100'
                                    : ph.state === 'skipped'
                                      ? 'bg-slate-100 border-slate-200 text-slate-400 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-500'
                                      : 'bg-white border-slate-200 text-slate-300 dark:bg-slate-900/50 dark:border-slate-600 dark:text-slate-500'
                              }`}
                            >
                              <Icon className="w-4 h-4" />
                            </div>
                            {!isLast && (
                              <div
                                className={`w-0.5 flex-1 min-h-[14px] ${lineDone ? 'bg-emerald-300 dark:bg-teal-600' : 'bg-slate-200 dark:bg-slate-600'}`}
                              />
                            )}
                          </div>
                          <div className={`pb-4 ${isLast ? '' : ''}`}>
                            <p className="text-xs font-bold font-mono tracking-wide text-slate-900 dark:text-slate-100">{ph.label}</p>
                            <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">{ph.description}</p>
                            <p className="text-[9px] uppercase font-semibold mt-1 text-slate-400 dark:text-slate-500">
                              {ph.state === 'complete' && 'Phase complete'}
                              {ph.state === 'active' && 'Current phase'}
                              {ph.state === 'pending' && 'Awaiting settlement'}
                              {ph.state === 'skipped' && 'Not applicable'}
                            </p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* TrustOS note */}
          <div className="flex items-center gap-2 px-4 py-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-600/50" data-testid="trustos-note">
            <Lock className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500 flex-shrink-0" />
            <p className="text-xs text-slate-500 dark:text-slate-400">
              <span className="font-semibold text-slate-700 dark:text-slate-200">Settlement controlled by TrustOS.</span>{' '}
              We don't control payment initiation — we control <em>when money moves.</em>
            </p>
          </div>

          {!processing && (
            <button
              onClick={onContinue}
              data-testid="continue-to-delivery-btn"
              className="w-full flex items-center justify-center gap-2 py-3.5 bg-teal-950 text-white rounded-xl font-semibold text-sm hover:bg-teal-900 shadow-trust transition-all duration-200 animate-fade-in"
            >
              Continue to Delivery Tracking
              <ChevronRight className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

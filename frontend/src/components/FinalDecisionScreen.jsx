import React from 'react';
import { CheckCircle2, XCircle, ArrowRight, Shield, RotateCcw } from 'lucide-react';
import { RISK_CONFIG } from '@/utils/riskEngine';

export default function FinalDecisionScreen({
  selectedProduct,
  riskData,
  deliveryTimestamps,
  verificationResult,
  finalOutcome,
  contractVerifyResult,
  contractSettleResult,
  onReset,
}) {
  const isSuccess = finalOutcome === 'released';
  const cfg = RISK_CONFIG[riskData.level];

  const verifyMethodMap = {
    low: 'Silent Auto-Confirm (30s)',
    medium: 'Buyer Confirmation',
    high: 'OTP + Video + Checklist',
  };

  const journeyRows = [
    {
      phase: 'Risk Assessment',
      details: `Score: ${riskData.score.toFixed(1)} / 100 · BT=${riskData.bt.toFixed(0)} · ST=${riskData.st.toFixed(0)}`,
      status: riskData.level.toUpperCase(),
      statusStyle: { backgroundColor: cfg.bgSoft, color: cfg.textDark, border: `1px solid ${cfg.border}` },
    },
    {
      phase: 'Payment',
      details: `${selectedProduct.priceLabel} charged to buyer`,
      status: cfg.paymentStatus,
      statusStyle: { backgroundColor: cfg.bgSoft, color: cfg.textDark, border: `1px solid ${cfg.border}` },
    },
    {
      phase: 'Delivery',
      details: deliveryTimestamps?.delivered ? `Delivered at ${deliveryTimestamps.delivered}` : 'Simulated delivery',
      status: 'Complete',
      statusStyle: { backgroundColor: '#ECFDF5', color: '#047857', border: '1px solid #A7F3D0' },
    },
    {
      phase: 'Verification',
      details: verifyMethodMap[riskData.level],
      status: verificationResult === 'passed' ? 'Passed' : 'Failed',
      statusStyle: verificationResult === 'passed'
        ? { backgroundColor: '#ECFDF5', color: '#047857', border: '1px solid #A7F3D0' }
        : { backgroundColor: '#FFF1F2', color: '#BE123C', border: '1px solid #FECDD3' },
    },
    {
      phase: 'Settlement',
      details: isSuccess ? `Released to ${selectedProduct.seller.name}` : `Refunded to ${selectedProduct.buyer.name}`,
      status: isSuccess ? 'Released' : 'Refunded',
      statusStyle: isSuccess
        ? { backgroundColor: '#ECFDF5', color: '#047857', border: '1px solid #A7F3D0' }
        : { backgroundColor: '#EFF6FF', color: '#1D4ED8', border: '1px solid #BFDBFE' },
    },
    ...(contractVerifyResult || contractSettleResult
      ? [
          {
            phase: 'API contract',
            details: [
              contractVerifyResult && `verify → ${contractVerifyResult.result}`,
              contractSettleResult && `settle → ${contractSettleResult.status}`,
            ]
              .filter(Boolean)
              .join(' · '),
            status: 'OK',
            statusStyle: { backgroundColor: '#F1F5F9', color: '#334155', border: '1px solid #E2E8F0' },
          },
        ]
      : []),
  ];

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="animate-fade-in">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">Step 5 of 5</p>
        <h1 className="font-display text-3xl font-semibold text-slate-900 dark:text-slate-100 tracking-tight">Settlement Complete</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1">TrustOS has finalized the transaction.</p>
      </div>

      {/* Outcome Banner */}
      <div
        className={`animate-scale-in rounded-2xl p-8 text-center border shadow-sm ${isSuccess ? 'bg-emerald-50 border-emerald-200 dark:bg-emerald-950/30 dark:border-emerald-800/40' : 'bg-blue-50 border-blue-200 dark:bg-blue-950/30 dark:border-blue-800/40'}`}
        data-testid="final-outcome-banner"
      >
        <div className={`w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 ${isSuccess ? 'bg-emerald-500 pulse-ring-green' : 'bg-blue-500'}`}>
          {isSuccess
            ? <CheckCircle2 className="w-8 h-8 text-white" />
            : <XCircle className="w-8 h-8 text-white" />
          }
        </div>
        <h2
          className={`font-display text-2xl font-semibold mb-2 tracking-tight ${isSuccess ? 'text-teal-800 dark:text-teal-300' : 'text-sky-800 dark:text-sky-300'}`}
        >
          {isSuccess ? 'Payment Released to Seller' : 'Refunded to Buyer'}
        </h2>
        <p className={`text-4xl font-bold font-mono mb-3 ${isSuccess ? 'text-teal-700 dark:text-teal-400' : 'text-sky-700 dark:text-sky-400'}`}>
          {selectedProduct.priceLabel}
        </p>
        <p className={`text-sm ${isSuccess ? 'text-emerald-600 dark:text-emerald-400' : 'text-blue-600 dark:text-blue-400'}`}>
          {isSuccess
            ? `Funds transferred to ${selectedProduct.seller.name}`
            : `Funds returned to ${selectedProduct.buyer.name}`
          }
        </p>
        <div className="mt-4 flex items-center justify-center gap-2 text-xs text-slate-500 dark:text-slate-400">
          <Shield className="w-3.5 h-3.5" />
          <span>Settlement processed by TrustOS Engine v2.4.1</span>
        </div>
      </div>

      {/* Journey Summary Table */}
      <div className="trust-card rounded-2xl overflow-hidden animate-fade-in-delay-2" data-testid="journey-table">
        <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-700/60 flex items-center gap-2">
          <ArrowRight className="w-4 h-4 text-slate-400 dark:text-slate-500" />
          <h3 className="font-semibold text-slate-900 dark:text-slate-100">Transaction Journey</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50 dark:bg-slate-900/50">
              <tr>
                {['Phase', 'Details', 'Status'].map(h => (
                  <th key={h} className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50 dark:divide-slate-700/50">
              {journeyRows.map((row, i) => (
                <tr key={i} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40 transition-colors" data-testid={`journey-row-${i}`}>
                  <td className="px-5 py-4 text-sm font-semibold text-slate-900 dark:text-slate-100">{row.phase}</td>
                  <td className="px-5 py-4 text-xs text-slate-500 dark:text-slate-400 font-mono">{row.details}</td>
                  <td className="px-5 py-4">
                    <span className="px-2.5 py-1 rounded-full text-xs font-semibold" style={row.statusStyle}>
                      {row.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Participants */}
      <div className="grid grid-cols-2 gap-4 animate-fade-in-delay-3">
        {[
          { label: 'Buyer', person: selectedProduct.buyer, outcome: isSuccess ? 'Order fulfilled' : 'Refund issued' },
          { label: 'Seller', person: selectedProduct.seller, outcome: isSuccess ? 'Payment received' : 'Order disputed' },
        ].map(({ label, person, outcome }) => (
          <div key={label} className="trust-card rounded-xl p-4 flex items-center gap-3">
            <img src={person.avatar} alt={person.name} className="w-10 h-10 rounded-full object-cover" />
            <div>
              <p className="text-xs text-slate-400 dark:text-slate-500 uppercase font-semibold">{label}</p>
              <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{person.name}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">{outcome}</p>
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={onReset}
        data-testid="new-transaction-btn"
        className="w-full flex items-center justify-center gap-2 py-4 bg-teal-950 text-white rounded-xl font-bold text-sm hover:bg-teal-900 shadow-trust transition-all duration-200 animate-fade-in-delay-4"
      >
        <RotateCcw className="w-4 h-4" />
        Start New Transaction
      </button>
    </div>
  );
}

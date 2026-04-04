import React from 'react';
import { Shield, RotateCcw, Check, LayoutDashboard } from 'lucide-react';

const STEPS = [
  { id: 'order', label: 'Order', num: 1 },
  { id: 'payment', label: 'Payment', num: 2 },
  { id: 'delivery', label: 'Delivery', num: 3 },
  { id: 'post_delivery', label: 'Verify', num: 4 },
  { id: 'final', label: 'Settlement', num: 5 },
];

const STEP_ORDER = ['order', 'payment', 'delivery', 'post_delivery', 'final'];

export default function Navbar({ step, onReset, showAdmin, onToggleAdmin, txCount }) {
  const currentIdx = STEP_ORDER.indexOf(step);

  return (
    <nav className="sticky top-0 z-50 border-b border-teal-800/12 bg-gradient-trust-nav backdrop-blur-md shadow-trust-soft transition-[background,box-shadow] duration-300">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 gap-4">
          {/* Logo */}
          <div className="flex items-center gap-2.5 flex-shrink-0" data-testid="trustos-logo">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-teal-600 via-teal-700 to-cyan-900 flex items-center justify-center shadow-trust-card ring-1 ring-white/25 shadow-[0_0_22px_-4px_rgba(45,212,191,0.45)]">
              <Shield className="w-[18px] h-[18px] text-white icon-glow-teal-sm drop-shadow-[0_0_6px_rgba(255,255,255,0.45)]" strokeWidth={2.25} />
            </div>
            <span className="font-display text-xl font-semibold tracking-tight text-slate-900">
              Trust<span className="text-teal-700/90">OS</span>
            </span>
            <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold bg-teal-50 text-teal-800 border border-teal-100/80 ml-0.5">
              Verified settlement
            </span>
          </div>

          {/* Step Indicator - hidden when admin open */}
          {!showAdmin && (
            <div className="hidden md:flex items-center gap-0 flex-1 justify-center" data-testid="step-indicator">
              {STEPS.map((s, idx) => {
                const isComplete = idx < currentIdx;
                const isActive = idx === currentIdx;
                const isFuture = idx > currentIdx;
                return (
                  <React.Fragment key={s.id}>
                    <div className="flex flex-col items-center gap-1">
                      <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-all duration-300 ${
                        isComplete ? 'bg-teal-600 text-white shadow-sm shadow-teal-500/35' :
                        isActive ? 'bg-gradient-to-br from-teal-700 to-cyan-800 text-white shadow-md ring-2 ring-teal-200/60 shadow-[0_0_16px_-2px_rgba(45,212,191,0.45)]' :
                        'bg-slate-100 text-slate-400 border border-slate-200/90'
                      }`}>
                        {isComplete ? <Check className="w-3.5 h-3.5" /> : s.num}
                      </div>
                      <span className={`text-[10px] font-medium ${isActive ? 'text-teal-900' : isFuture ? 'text-slate-400' : 'text-teal-600'}`}>
                        {s.label}
                      </span>
                    </div>
                    {idx < STEPS.length - 1 && (
                      <div className={`w-10 h-0.5 mb-4 mx-1 transition-all duration-300 ${idx < currentIdx ? 'bg-teal-400' : 'bg-slate-200'}`} />
                    )}
                  </React.Fragment>
                );
              })}
            </div>
          )}
          {showAdmin && <div className="flex-1" />}

          {/* Mobile step label */}
          {!showAdmin && (
            <div className="md:hidden text-sm font-medium text-slate-600">
              Step {currentIdx + 1} / {STEPS.length}
            </div>
          )}

          {/* Right actions */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={onToggleAdmin}
              data-testid="admin-dashboard-btn"
              className={`relative flex items-center gap-1.5 px-3 py-1.5 text-sm font-semibold rounded-lg transition-all duration-150 ${
                showAdmin
                  ? 'bg-gradient-to-r from-teal-800 to-cyan-900 text-white shadow-trust'
                  : 'bg-slate-100/90 text-slate-700 hover:bg-teal-50 hover:text-teal-900 border border-transparent hover:border-teal-100'
              }`}
            >
              <LayoutDashboard className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Monitor</span>
              {txCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-teal-500 text-white text-[9px] font-bold flex items-center justify-center ring-2 ring-white">
                  {txCount > 9 ? '9+' : txCount}
                </span>
              )}
            </button>

            {step !== 'order' && !showAdmin && (
              <button
                onClick={onReset}
                data-testid="reset-button"
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-600 hover:text-teal-900 hover:bg-teal-50/80 rounded-lg transition-colors duration-150"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">New Tx</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}

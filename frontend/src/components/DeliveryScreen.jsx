import React, { useState } from 'react';
import { Package, Truck, CheckCircle2, Clock, ChevronRight, MapPin, QrCode, ShieldCheck, ShieldAlert, FastForward } from 'lucide-react';
import { RISK_CONFIG } from '@/utils/riskEngine';

const STAGES = [
  { id: 'placed', label: 'Order Placed', desc: 'Seller preparing your order', Icon: Package },
  { id: 'shipped', label: 'Shipped', desc: 'Package in transit to you', Icon: Truck },
  { id: 'delivered', label: 'Delivered', desc: 'Package delivered to your address', Icon: CheckCircle2 },
];

const STAGE_ORDER = ['placed', 'shipped', 'delivered'];

function TimelineStep({ stage, currentStage, timestamps, isLast }) {
  const currentIdx = STAGE_ORDER.indexOf(currentStage);
  const stageIdx = STAGE_ORDER.indexOf(stage.id);
  const isDone = stageIdx <= currentIdx;
  const isActive = stageIdx === currentIdx;

  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center">
        <div className={`w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all duration-500 ${
          isDone && !isActive ? 'bg-emerald-500 border-emerald-500' :
          isActive ? 'bg-teal-900 border-teal-900 shadow-sm' :
          'bg-white border-slate-200 dark:bg-slate-800 dark:border-slate-600'
        }`}>
          {isDone && !isActive
            ? <CheckCircle2 className="w-5 h-5 text-white" />
            : <stage.Icon className={`w-5 h-5 ${isActive ? 'text-white' : 'text-slate-300'}`} />
          }
        </div>
        {!isLast && (
          <div className={`w-0.5 h-12 mt-1 transition-all duration-700 ${isDone ? 'bg-emerald-400 dark:bg-teal-500' : 'bg-slate-200 dark:bg-slate-600'}`} />
        )}
      </div>
      <div className="pb-8 flex-1">
        <div className="flex items-center gap-2 mb-0.5">
          <p className={`text-sm font-semibold transition-colors ${isDone ? 'text-slate-900 dark:text-slate-100' : 'text-slate-400 dark:text-slate-500'}`}>
            {stage.label}
          </p>
          {isActive && (
            <span className="px-2 py-0.5 bg-teal-900 text-white text-[10px] font-semibold rounded-full animate-pulse">
              CURRENT
            </span>
          )}
        </div>
        <p className={`text-xs ${isDone ? 'text-slate-500 dark:text-slate-400' : 'text-slate-300 dark:text-slate-600'}`}>{stage.desc}</p>
        {timestamps[stage.id] && (
          <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1 font-mono">{timestamps[stage.id]}</p>
        )}
      </div>
    </div>
  );
}

export default function DeliveryScreen({ selectedProduct, riskData, deliveryStage, deliveryTimestamps, onDeliveryUpdate, onProceed }) {
  const cfg = RISK_CONFIG[riskData.level];
  const currentIdx = STAGE_ORDER.indexOf(deliveryStage);
  const isComplete = deliveryStage === 'delivered';
  const [qrDemo, setQrDemo] = useState(null);
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=120x120&data=TRUSTOS-DEL-${selectedProduct.id}&color=0f172a&bgcolor=f8fafc`;

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="animate-fade-in">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">Step 3 of 5</p>
        <h1 className="font-display text-3xl font-semibold text-slate-900 dark:text-slate-100 tracking-tight">Delivery Tracking</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1">Payment remains {cfg.paymentStatus.toLowerCase()} until delivery is confirmed.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 animate-fade-in-delay-1">
        {/* Order Info */}
        <div className="trust-card rounded-2xl p-4">
          <p className="text-xs text-slate-400 dark:text-slate-500 uppercase tracking-wider font-semibold mb-3">Order Details</p>
          <img src={selectedProduct.image} alt={selectedProduct.name} className="w-full h-24 object-cover rounded-xl mb-3" />
          <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{selectedProduct.name}</p>
          <p className="text-lg font-bold font-mono text-slate-900 dark:text-slate-100">{selectedProduct.priceLabel}</p>
          <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-700/60">
            <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
              <MapPin className="w-3 h-3 text-slate-400" />
              <span>Delivering to buyer</span>
            </div>
          </div>
        </div>

        {/* Timeline */}
        <div className="sm:col-span-2 trust-card rounded-2xl p-6 animate-fade-in-delay-2">
          <div className="flex items-center justify-between mb-6">
            <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500">Delivery Timeline</p>
            <span className="px-2.5 py-1 rounded-full text-xs font-bold"
              style={{ backgroundColor: cfg.bgSoft, color: cfg.textDark, border: `1px solid ${cfg.border}` }}>
              {cfg.paymentStatus}
            </span>
          </div>
          {STAGES.map((stage, idx) => (
            <TimelineStep
              key={stage.id}
              stage={stage}
              currentStage={deliveryStage}
              timestamps={deliveryTimestamps}
              isLast={idx === STAGES.length - 1}
            />
          ))}

          {/* Action Button */}
          <div className="border-t border-slate-100 dark:border-slate-700/60 pt-4 animate-fade-in-delay-3">
            {!isComplete ? (
              <button
                onClick={() => onDeliveryUpdate(STAGE_ORDER[currentIdx + 1])}
                data-testid="simulate-delivery-btn"
                className="w-full flex items-center justify-center gap-2 py-3 bg-teal-950 text-white rounded-xl font-semibold text-sm hover:bg-teal-900 shadow-trust transition-all duration-200"
              >
                {deliveryStage === 'placed' ? (
                  <><Truck className="w-4 h-4" /> Simulate Dispatch</>
                ) : (
                  <><CheckCircle2 className="w-4 h-4" /> Simulate Delivery</>
                )}
              </button>
            ) : (
              <div className="space-y-3 animate-scale-in">
                <div className="flex items-center gap-2 px-4 py-3 bg-emerald-50 dark:bg-emerald-950/35 rounded-xl border border-emerald-200 dark:border-emerald-800/40">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                  <p className="text-sm text-emerald-700 dark:text-emerald-300 font-medium">Package delivered successfully!</p>
                </div>
                <button
                  onClick={onProceed}
                  data-testid="proceed-to-verification-btn"
                  className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl font-bold text-white text-sm transition-all duration-200 hover:opacity-90"
                  style={{ backgroundColor: cfg.color }}
                >
                  Proceed to {riskData.level === 'low' ? 'Auto-Confirmation' : riskData.level === 'medium' ? 'Delivery Confirmation' : 'Verification'}
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 px-4 py-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-600/50 animate-fade-in-delay-4">
        <Clock className="w-4 h-4 text-slate-400 dark:text-slate-500" />
        <p className="text-xs text-slate-500 dark:text-slate-400">
          <span className="font-semibold text-slate-700 dark:text-slate-200">{selectedProduct.priceLabel}</span> stays {cfg.paymentStatus.toLowerCase()} until post-delivery verification is complete.
        </p>
      </div>

      {/* Static QR demo — real vs fake seal (icons only) */}
      <div className="max-w-2xl trust-card rounded-2xl p-5 animate-fade-in-delay-4">
        <div className="flex items-center gap-2 mb-3">
          <QrCode className="w-4 h-4 text-slate-600 dark:text-slate-400" />
          <p className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Route seal check (static QR demo)</p>
          <FastForward className="w-3.5 h-3.5 text-amber-500 ml-auto" title="Fast-forward to post-delivery from next step" />
        </div>
        <div className="flex flex-col sm:flex-row gap-4 items-center sm:items-start">
          <div className="flex-shrink-0 rounded-xl border-2 border-slate-200 dark:border-slate-600 overflow-hidden bg-slate-50 dark:bg-slate-900/40 p-2">
            <img src={qrUrl} alt="Static delivery QR" className="w-[120px] h-[120px] object-contain" />
          </div>
          <div className="flex-1 space-y-3 w-full">
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Courier label QR is static for this demo. Tap an outcome to see how TrustOS would flag the seal at handoff.
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setQrDemo('real')}
                className={`inline-flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold border transition-all ${
                  qrDemo === 'real'
                    ? 'bg-emerald-50 border-emerald-300 text-emerald-800 dark:bg-emerald-950/40 dark:border-emerald-700 dark:text-emerald-200'
                    : 'bg-white dark:bg-slate-800/80 border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:border-emerald-200'
                }`}
              >
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                Authentic seal
              </button>
              <button
                type="button"
                onClick={() => setQrDemo('fake')}
                className={`inline-flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold border transition-all ${
                  qrDemo === 'fake'
                    ? 'bg-rose-50 border-rose-300 text-rose-800 dark:bg-rose-950/35 dark:border-rose-800 dark:text-rose-200'
                    : 'bg-white dark:bg-slate-800/80 border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:border-rose-200'
                }`}
              >
                <ShieldAlert className="w-4 h-4 text-rose-600" />
                Suspicious / fake
              </button>
            </div>
            {qrDemo === 'real' && (
              <p className="text-[11px] text-emerald-700 dark:text-emerald-300 flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 flex-shrink-0" />
                Hash matches TrustOS registry — proceed to post-delivery checks.
              </p>
            )}
            {qrDemo === 'fake' && (
              <p className="text-[11px] text-rose-700 dark:text-rose-300 flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5 flex-shrink-0" />
                Mismatch detected — would trigger enhanced verification or hold.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

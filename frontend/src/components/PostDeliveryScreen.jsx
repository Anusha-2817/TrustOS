import React, { useState, useEffect, useRef } from 'react';
import { Shield, CheckCircle2, AlertTriangle, Camera, Check, Clock, Upload, Eye, Box, QrCode, Scan, FastForward, Video, BadgeCheck, BadgeX } from 'lucide-react';
import { InputOTP, InputOTPGroup, InputOTPSlot, InputOTPSeparator } from '@/components/ui/input-otp';
import { Checkbox } from '@/components/ui/checkbox';
import { RISK_CONFIG } from '@/utils/riskEngine';

const DEMO_OTP = '847291';

/* ── Shared QR Scanner Component ─────────────────────── */
function QRScan({ productId, onVerified, addLog }) {
  const [scanning, setScanning] = useState(false);
  const [verified, setVerified] = useState(false);
  const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=TRUSTOS-SEAL-${productId}&color=0f172a&bgcolor=f8fafc`;

  const handleScan = () => {
    setScanning(true);
    addLog('QR seal authentication in progress...', 'info');
    setTimeout(() => {
      setScanning(false);
      setVerified(true);
      addLog('Package QR seal verified: AUTHENTIC ✓', 'low');
      if (onVerified) onVerified();
    }, 2000);
  };

  return (
    <div className="trust-card rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <QrCode className="w-4 h-4 text-slate-600 dark:text-slate-400" />
        <h4 className="text-sm font-semibold text-slate-900 dark:text-slate-100">QR Package Seal Verification</h4>
      </div>
      <div className="flex gap-4 items-center">
        <div className="relative flex-shrink-0">
          {verified ? (
            <div className="w-24 h-24 bg-emerald-50 rounded-xl flex items-center justify-center border-2 border-emerald-300 animate-scale-in">
              <CheckCircle2 className="w-10 h-10 text-emerald-500" />
            </div>
          ) : (
            <div className="relative w-24 h-24">
              <img src={qrUrl} alt="Package QR" className="w-24 h-24 rounded-xl border border-slate-200 dark:border-slate-600 object-cover" />
              {scanning && (
                <div className="absolute inset-0 bg-slate-900/60 rounded-xl flex items-center justify-center scan-line overflow-hidden">
                  <Scan className="w-8 h-8 text-emerald-400 animate-pulse" />
                </div>
              )}
            </div>
          )}
        </div>
        <div className="flex-1">
          {verified ? (
            <div className="animate-fade-in">
              <p className="text-sm font-bold text-emerald-700">Seal Authenticated</p>
              <p className="text-xs text-emerald-600 mt-0.5">Package integrity confirmed by TrustOS</p>
              <div className="mt-2 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                <span className="text-[10px] font-mono text-emerald-600">ID: SEAL-{productId.toUpperCase()}</span>
              </div>
            </div>
          ) : (
            <>
              <p className="text-xs text-slate-500 dark:text-slate-400 mb-3 leading-relaxed">Scan the QR code on the package to verify authenticity seal before confirming.</p>
              <button
                onClick={handleScan}
                disabled={scanning}
                data-testid="qr-scan-btn"
                className="flex items-center gap-2 px-4 py-2 bg-teal-950 text-white rounded-lg text-xs font-semibold hover:bg-teal-900 disabled:opacity-60 transition-all"
              >
                <Scan className="w-3.5 h-3.5" />
                {scanning ? 'Scanning...' : 'Tap to Scan'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const LOW_SILENT_SHORT_SEC = 32; // demo stand-in for 30 min – 1 hr
const LOW_SILENT_LONG_SEC = 40; // demo stand-in for 2 – 8 hr
const MEDIUM_WINDOW_SEC = 72; // demo stand-in for 8 hr; notify 1 hr before end → at 63s elapsed (7/8)

/* ── LOW RISK: Silent timers (short + long) ─────────── */
function LowRiskVerification({ onComplete, addLog }) {
  const [phase, setPhase] = useState('short'); // short | long | done
  const [seconds, setSeconds] = useState(LOW_SILENT_SHORT_SEC);
  const [longSeconds, setLongSeconds] = useState(LOW_SILENT_LONG_SEC);

  useEffect(() => {
    if (phase === 'short') {
      if (seconds <= 0) {
        addLog('LOW: Short silent window complete (≈30 min–1 hr in production).', 'low');
        setPhase('long');
        return;
      }
      const t = setInterval(() => setSeconds((s) => s - 1), 1000);
      return () => clearInterval(t);
    }
    if (phase === 'long') {
      if (longSeconds <= 0) {
        addLog('LOW: Long silent settlement window complete (≈2–8 hr). No issue → auto-release.', 'low');
        setPhase('done');
        setTimeout(() => onComplete('passed'), 600);
        return;
      }
      const t = setInterval(() => setLongSeconds((s) => s - 1), 1000);
      return () => clearInterval(t);
    }
  }, [phase, seconds, longSeconds, addLog, onComplete]);

  const shortPct = ((LOW_SILENT_SHORT_SEC - seconds) / LOW_SILENT_SHORT_SEC) * 100;
  const longPct = ((LOW_SILENT_LONG_SEC - longSeconds) / LOW_SILENT_LONG_SEC) * 100;

  return (
    <div className="space-y-5 max-w-lg" data-testid="low-risk-verification">
      {phase === 'short' && (
        <div className="trust-card rounded-2xl border-emerald-200 dark:border-emerald-800/45 dark:bg-slate-800/80 p-6 text-center">
          <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 mb-2">
            Silent window — 30 min to 1 hr (demo timer)
          </p>
          <div className="relative w-28 h-28 mx-auto mb-4">
            <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
              <circle cx="50" cy="50" r="40" fill="none" stroke="#D1FAE5" strokeWidth="8" />
              <circle
                cx="50"
                cy="50"
                r="40"
                fill="none"
                stroke="#10B981"
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray="251"
                strokeDashoffset={251 * (1 - shortPct / 100)}
                style={{ transition: 'stroke-dashoffset 1s linear' }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-bold font-mono text-slate-900 dark:text-slate-100">{seconds}</span>
              <span className="text-xs text-slate-400 dark:text-slate-500">sec</span>
            </div>
          </div>
          <h3 className="font-display text-lg font-semibold text-slate-900 dark:text-slate-100 mb-1 tracking-tight">
            Silent confirmation
          </h3>
        <p className="text-sm text-slate-500 dark:text-slate-400">
            No banner. If you do not report an issue, we move to the longer settlement hold next.
          </p>
          <div className="mt-3 px-4 py-2 bg-emerald-50 rounded-lg border border-emerald-200 inline-flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs text-emerald-700 font-medium">LOW RISK — observation only</span>
          </div>
        </div>
      )}

      {phase === 'long' && (
        <div className="trust-card rounded-2xl border-emerald-200 dark:border-emerald-800/45 dark:bg-slate-800/80 p-6">
          <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400 mb-2">
            Silent settlement — 2 hr to 8 hr (demo timer)
          </p>
          <h3 className="font-display text-lg font-semibold text-slate-900 dark:text-slate-100 mb-2 tracking-tight">
            Funds complete automatically if silent
          </h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
            Production: money moves when you do not open a dispute before this window ends.
          </p>
          <div className="h-3 bg-slate-100 dark:bg-slate-900/60 rounded-full overflow-hidden border border-slate-200 dark:border-slate-600 mb-2">
            <div
              className="h-full bg-emerald-500 transition-all duration-1000"
              style={{ width: `${longPct}%` }}
            />
          </div>
          <p className="text-center text-sm font-mono text-slate-700 dark:text-slate-300">{longSeconds}s left (demo)</p>
        </div>
      )}

      {phase === 'done' && (
        <div className="bg-emerald-50 rounded-2xl border border-emerald-200 p-6 text-center animate-scale-in">
          <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto mb-2" />
          <p className="text-sm font-semibold text-emerald-800">Both silent windows cleared — releasing payment…</p>
        </div>
      )}

      {phase !== 'done' && (
        <button
          onClick={() => {
            addLog('Dispute raised by buyer during silent window.', 'high');
            onComplete('failed');
          }}
          data-testid="report-issue-btn-low"
          className="w-full py-3 border border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-xl text-sm font-medium hover:bg-slate-50 dark:hover:bg-slate-800 hover:text-slate-900 dark:hover:text-slate-100 transition-colors"
        >
          <AlertTriangle className="w-4 h-4 inline mr-2 text-amber-500" />
          Report an Issue
        </button>
      )}
    </div>
  );
}

const MEDIUM_NOTIFY_ELAPSED = 63; // 7/8 of 72s ≈ “1 hr left” in an 8 hr window

/* ── MEDIUM RISK: 2-8hr silent window + notify + QR + Confirmation ────── */
function MediumRiskVerification({ product, onComplete, addLog }) {
  const [phase, setPhase] = useState('timer'); // 'timer' | 'verify'
  const [elapsed, setElapsed] = useState(0);
  const [qrVerified, setQrVerified] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [fileName, setFileName] = useState('');
  const fileRef = useRef();
  const notifiedRef = useRef(false);

  useEffect(() => {
    if (phase !== 'timer') return;
    if (elapsed >= MEDIUM_NOTIFY_ELAPSED && !notifiedRef.current) {
      notifiedRef.current = true;
      addLog('Push notification (demo): ~1 hour until auto-capture if you do not report an issue.', 'medium');
    }
  }, [phase, elapsed, addLog]);

  useEffect(() => {
    if (phase !== 'timer') return;
    if (elapsed >= MEDIUM_WINDOW_SEC) {
      addLog('MEDIUM: Silent 2–8 hr window ended with no dispute — unlock receipt confirmation.', 'medium');
      setPhase('verify');
    }
  }, [phase, elapsed, addLog]);

  useEffect(() => {
    if (phase !== 'timer') return;
    if (elapsed >= MEDIUM_WINDOW_SEC) return;
    const t = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(t);
  }, [phase, elapsed]);

  const handleFastForward = () => {
    addLog('Confirmation window fast-forwarded (demo mode).', 'medium');
    addLog('MEDIUM RISK: Awaiting buyer QR scan + confirmation...', 'medium');
    setPhase('verify');
  };

  const handleConfirm = () => {
    if (!qrVerified) return;
    setConfirmed(true);
    addLog('Buyer confirmed delivery receipt.', 'medium');
    setTimeout(() => onComplete('passed'), 600);
  };

  const progressPct = Math.min(100, (elapsed / MEDIUM_WINDOW_SEC) * 100);

  if (phase === 'timer') {
    return (
      <div className="space-y-4 max-w-lg" data-testid="medium-timer-phase">
        <div className="trust-card rounded-2xl border-amber-200 dark:border-amber-800/40 dark:bg-slate-800/80 p-6">
          <div className="flex items-center gap-3 mb-5">
            <div className="w-10 h-10 bg-amber-50 dark:bg-amber-950/50 rounded-full flex items-center justify-center border border-amber-200 dark:border-amber-800/40">
              <Clock className="w-5 h-5 text-amber-500 dark:text-amber-400" />
            </div>
            <div>
              <p className="text-xs text-amber-600 dark:text-amber-400 font-bold uppercase tracking-wider">Silent settlement window</p>
              <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">2 hr – 8 hr (demo clock)</h3>
            </div>
          </div>

          <div className="mb-4">
            <div className="flex justify-between text-[11px] text-slate-500 dark:text-slate-400 mb-2 font-medium">
              <span>Delivered</span>
              <span className="text-amber-600 dark:text-amber-400">No issue → funds move</span>
              <span>Window end</span>
            </div>
            <div className="relative h-4 bg-slate-100 dark:bg-slate-900/60 rounded-full overflow-hidden border border-slate-200 dark:border-slate-600">
              <div
                className="absolute inset-y-0 left-0 bg-amber-400 rounded-full transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              />
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-rose-400 z-10"
                style={{ left: `${(MEDIUM_NOTIFY_ELAPSED / MEDIUM_WINDOW_SEC) * 100}%` }}
                title="1 hr before end — notification sent"
              />
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-[10px] font-mono text-slate-600 dark:text-slate-400">{elapsed}s / {MEDIUM_WINDOW_SEC}s demo</span>
              <span className="text-[10px] text-amber-700 dark:text-amber-400 font-semibold">Silent unless you report</span>
            </div>
          </div>

          {elapsed >= MEDIUM_NOTIFY_ELAPSED && (
            <div className="mb-4 flex items-start gap-2 px-3 py-2.5 rounded-xl bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800/50 text-xs text-blue-900 dark:text-blue-200">
              <Clock className="w-4 h-4 flex-shrink-0 mt-0.5" />
              <span>
                <span className="font-semibold">Heads-up:</span> In production you would be notified about{' '}
                <span className="font-mono">~1 hour</span> remaining before automatic capture if you have not reported an issue.
              </span>
            </div>
          )}

          <div className="bg-amber-50 dark:bg-amber-950/30 rounded-xl border border-amber-200 dark:border-amber-800/40 p-3 mb-4">
            <p className="text-xs text-amber-800 dark:text-amber-200 leading-relaxed">
              <span className="font-semibold">TrustOS behavior:</span> Payment stays authorized/held while this silent timer runs.
              If you <em>do not</em> report a problem, settlement can complete automatically at the end of the window; you still confirm receipt in the next step after the timer (or use fast-forward).
            </p>
          </div>

          <button
            onClick={handleFastForward}
            data-testid="fast-forward-btn"
            className="w-full flex items-center justify-center gap-2.5 py-3.5 border-2 border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40 rounded-xl font-bold text-sm hover:bg-amber-100 dark:hover:bg-amber-950/60 active:scale-[0.99] transition-all group"
          >
            <FastForward className="w-4 h-4 group-hover:scale-110 transition-transform" />
            Fast-forward Confirmation Window
            <span className="text-[10px] text-amber-500 dark:text-amber-400 bg-amber-100 dark:bg-amber-950/60 px-2 py-0.5 rounded-full border border-amber-300 dark:border-amber-800">DEMO</span>
          </button>
        </div>

        <button
          onClick={() => { addLog('Dispute raised by buyer during window.', 'high'); onComplete('failed'); }}
          data-testid="report-issue-btn-medium"
          className="w-full py-3 border border-slate-200 dark:border-slate-600 text-slate-500 dark:text-slate-400 rounded-xl text-sm hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
        >
          <AlertTriangle className="w-4 h-4 inline mr-2 text-amber-500" />
          Report an Issue
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4 max-w-lg animate-fade-in" data-testid="medium-verify-phase">
      <div className="flex items-center gap-2 px-4 py-3 bg-amber-50 dark:bg-amber-950/35 rounded-xl border border-amber-200 dark:border-amber-800/40">
        <FastForward className="w-4 h-4 text-amber-500 dark:text-amber-400" />
        <p className="text-xs text-amber-700 dark:text-amber-300 font-semibold">Confirmation window unlocked — please verify package & confirm.</p>
      </div>

      {/* QR Scan */}
      <QRScan productId={product.id} onVerified={() => setQrVerified(true)} addLog={addLog} />

      {/* Confirmation */}
      <div className="trust-card rounded-2xl border-amber-200 dark:border-amber-800/40 dark:bg-slate-800/80 p-5">
        <div className="flex gap-3 p-3 bg-amber-50 dark:bg-amber-950/35 rounded-xl border border-amber-200 dark:border-amber-800/40 mb-4">
          <img src={product.image} alt={product.name} className="w-12 h-12 rounded-lg object-cover" />
          <div>
            <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{product.name}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">{product.priceLabel} — verify upon receipt</p>
          </div>
        </div>

        <div
          className="border-2 border-dashed border-slate-200 dark:border-slate-600 rounded-xl p-4 text-center cursor-pointer hover:border-amber-300 hover:bg-amber-50/50 dark:hover:bg-amber-950/20 transition-all mb-4"
          onClick={() => fileRef.current?.click()}
          data-testid="upload-area"
        >
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={e => setFileName(e.target.files?.[0]?.name || '')} />
          <Upload className="w-6 h-6 text-slate-300 dark:text-slate-500 mx-auto mb-2" />
          <p className="text-xs text-slate-500 dark:text-slate-400">{fileName || 'Attach delivery photo (optional)'}</p>
        </div>

        {!confirmed ? (
          <button
            onClick={handleConfirm}
            disabled={!qrVerified}
            data-testid="confirm-delivery-btn"
            className="w-full py-4 bg-amber-500 hover:bg-amber-600 text-white rounded-xl font-bold text-sm transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed pulse-ring-amber"
          >
            <CheckCircle2 className="w-4 h-4 inline mr-2" />
            {qrVerified ? 'I received my order' : 'Scan QR first to confirm'}
          </button>
        ) : (
          <div className="flex items-center gap-2 justify-center py-4 text-emerald-600 animate-scale-in">
            <CheckCircle2 className="w-5 h-5" />
            <span className="font-semibold">Confirmed! Releasing payment...</span>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── HIGH RISK: OTP + Video + QR + Checklist ──────────── */
function HighRiskVerification({ product, onComplete, addLog }) {
  const [verifyStep, setVerifyStep] = useState(1);
  const [otp, setOtp] = useState('');
  const [otpError, setOtpError] = useState('');
  const [scanning, setScanning] = useState(false);
  const [scanDone, setScanDone] = useState(false);
  const [videoDemo, setVideoDemo] = useState(null); // 'real' | 'fake' | null
  const [qrVerified, setQrVerified] = useState(false);
  const [checklist, setChecklist] = useState({ seal: false, open: false, show: false });

  const handleVerifyOTP = () => {
    if (otp !== DEMO_OTP) {
      setOtpError('Incorrect OTP. Please check and try again.');
      addLog('OTP verification failed. Retry required.', 'high');
      return;
    }
    setOtpError('');
    addLog('OTP verified successfully.', 'low');
    setVerifyStep(2);
  };

  const handleStartCamera = () => {
    if (!videoDemo) {
      addLog('Pick Real or Fake stream (demo) before starting video.', 'high');
      return;
    }
    setScanning(true);
    addLog(`Video verification stream active (${videoDemo === 'real' ? 'trusted' : 'spoofed'} demo)...`, 'info');
    setTimeout(() => {
      setScanDone(true);
      setScanning(false);
      if (videoDemo === 'real') {
        addLog('Video attestation: LIVE feed — identity signal OK (demo).', 'low');
      } else {
        addLog('Video attestation: SPOOFED feed flagged — would block in production (demo).', 'high');
      }
    }, 2800);
  };

  const handleSubmit = () => {
    const allChecked = checklist.seal && checklist.open && checklist.show;
    if (!allChecked || !qrVerified) return;
    addLog('All verification checks passed.', 'low');
    onComplete('passed');
  };

  const progressLabels = ['OTP', 'Video', 'QR Seal', 'Checklist'];

  return (
    <div className="space-y-5 max-w-lg" data-testid="high-risk-verification">
      {/* Progress */}
      <div className="trust-card rounded-2xl border-rose-200 dark:border-rose-900/50 dark:bg-slate-800/80 p-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
          <p className="text-xs font-bold uppercase tracking-widest text-rose-600 dark:text-rose-400">High Risk — 4-Factor Verification</p>
        </div>
        <div className="flex items-center gap-1">
          {progressLabels.map((label, i) => (
            <React.Fragment key={label}>
              <div className="flex flex-col items-center gap-1">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                  i + 1 < verifyStep ? 'bg-emerald-500 text-white' :
                  i + 1 === verifyStep ? 'bg-rose-600 text-white' :
                  'bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500'
                }`}>
                  {i + 1 < verifyStep ? <Check className="w-3.5 h-3.5" /> : i + 1}
                </div>
                <span className={`text-[9px] font-medium ${i + 1 === verifyStep ? 'text-rose-600' : i + 1 < verifyStep ? 'text-emerald-600' : 'text-slate-400'}`}>
                  {label}
                </span>
              </div>
              {i < 3 && <div className={`flex-1 h-0.5 mb-4 mx-0.5 ${i + 1 < verifyStep ? 'bg-emerald-400 dark:bg-teal-600' : 'bg-slate-200 dark:bg-slate-600'}`} />}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Step 1: OTP */}
      {verifyStep === 1 && (
        <div className="trust-card rounded-2xl p-6 animate-fade-in" data-testid="otp-step">
          <h3 className="font-display text-lg font-semibold text-slate-900 dark:text-slate-100 mb-1 tracking-tight">OTP Verification</h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">Enter the 6-digit code sent to your registered device (****6789).</p>
          <div className="flex items-center gap-2 px-3 py-2 bg-rose-50 dark:bg-rose-950/35 rounded-lg border border-rose-200 dark:border-rose-800/50 mb-5">
            <Eye className="w-3.5 h-3.5 text-rose-500" />
            <p className="text-xs text-rose-600 dark:text-rose-300 font-mono font-semibold">Demo OTP: {DEMO_OTP}</p>
          </div>
          <div className="flex justify-center mb-4">
            <InputOTP maxLength={6} value={otp} onChange={setOtp} data-testid="otp-input">
              <InputOTPGroup>
                <InputOTPSlot index={0} />
                <InputOTPSlot index={1} />
                <InputOTPSlot index={2} />
              </InputOTPGroup>
              <InputOTPSeparator />
              <InputOTPGroup>
                <InputOTPSlot index={3} />
                <InputOTPSlot index={4} />
                <InputOTPSlot index={5} />
              </InputOTPGroup>
            </InputOTP>
          </div>
          {otpError && <p className="text-xs text-rose-600 text-center mb-3">{otpError}</p>}
          <button onClick={handleVerifyOTP} disabled={otp.length < 6} data-testid="verify-otp-btn"
            className="w-full py-3.5 bg-rose-600 text-white rounded-xl font-semibold text-sm hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all">
            Verify OTP
          </button>
        </div>
      )}

      {/* Step 2: Video */}
      {verifyStep === 2 && (
        <div className="trust-card rounded-2xl p-6 animate-fade-in" data-testid="video-step">
          <div className="flex items-center gap-2 mb-2">
            <Video className="w-4 h-4 text-slate-600 dark:text-slate-400" />
            <h3 className="font-display text-lg font-semibold text-slate-900 dark:text-slate-100 tracking-tight">Video Verification</h3>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-3">Static demo window — choose a simulated feed, then start verification.</p>
          <div className="flex flex-wrap gap-2 mb-4">
            <button
              type="button"
              onClick={() => { setVideoDemo('real'); setScanDone(false); }}
              className={`inline-flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold border transition-all ${
                videoDemo === 'real' ? 'bg-emerald-50 border-emerald-300 text-emerald-800 dark:bg-emerald-950/40 dark:border-emerald-700 dark:text-emerald-200' : 'bg-slate-50 border-slate-200 text-slate-600 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-300'
              }`}
            >
              <BadgeCheck className="w-4 h-4 text-emerald-600" />
              Real / live (demo)
            </button>
            <button
              type="button"
              onClick={() => { setVideoDemo('fake'); setScanDone(false); }}
              className={`inline-flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-semibold border transition-all ${
                videoDemo === 'fake' ? 'bg-rose-50 border-rose-300 text-rose-800 dark:bg-rose-950/35 dark:border-rose-800 dark:text-rose-200' : 'bg-slate-50 border-slate-200 text-slate-600 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-300'
              }`}
            >
              <BadgeX className="w-4 h-4 text-rose-600" />
              Fake / spoof (demo)
            </button>
          </div>
          <div className="relative bg-slate-900 rounded-xl h-40 flex items-center justify-center overflow-hidden border-2 border-slate-700 mb-4 scan-line">
            {scanDone ? (
              <div className="text-center animate-scale-in px-4">
                {videoDemo === 'real' ? (
                  <>
                    <BadgeCheck className="w-10 h-10 text-emerald-400 mx-auto mb-2" />
                    <p className="text-emerald-400 text-sm font-semibold">Live feed accepted</p>
                  </>
                ) : (
                  <>
                    <BadgeX className="w-10 h-10 text-rose-400 mx-auto mb-2" />
                    <p className="text-rose-400 text-sm font-semibold">Spoofed feed — would fail policy</p>
                  </>
                )}
              </div>
            ) : scanning ? (
              <div className="text-center">
                <div className="w-12 h-12 border-2 border-emerald-400 rounded-full mx-auto mb-2 animate-pulse" />
                <p className="text-emerald-400 text-xs animate-blink">Analyzing static frame…</p>
              </div>
            ) : (
              <div className="text-center">
                <Camera className="w-10 h-10 text-slate-500 dark:text-slate-400 mx-auto mb-2" />
                <p className="text-slate-500 dark:text-slate-400 text-xs">Camera preview (simulated)</p>
              </div>
            )}
            <div className="absolute top-2 left-2 w-5 h-5 border-t-2 border-l-2 border-emerald-400 rounded-tl" />
            <div className="absolute top-2 right-2 w-5 h-5 border-t-2 border-r-2 border-emerald-400 rounded-tr" />
            <div className="absolute bottom-2 left-2 w-5 h-5 border-b-2 border-l-2 border-emerald-400 rounded-bl" />
            <div className="absolute bottom-2 right-2 w-5 h-5 border-b-2 border-r-2 border-emerald-400 rounded-br" />
          </div>
          {!scanDone ? (
            <button onClick={handleStartCamera} disabled={scanning} data-testid="start-camera-btn"
              className="w-full py-3.5 bg-teal-950 text-white rounded-xl font-semibold text-sm hover:bg-teal-900 disabled:opacity-60 transition-all">
              {scanning ? 'Verifying...' : 'Start camera verification'}
            </button>
          ) : (
            <button
              onClick={() => videoDemo === 'real' && setVerifyStep(3)}
              disabled={videoDemo !== 'real'}
              data-testid="proceed-to-qr-btn"
              className="w-full py-3.5 bg-emerald-600 text-white rounded-xl font-semibold text-sm hover:bg-emerald-700 transition-all animate-scale-in disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Check className="w-4 h-4 inline mr-2" />
              Proceed to QR seal scan
            </button>
          )}
          {scanDone && videoDemo === 'fake' && (
            <p className="text-[11px] text-rose-600 mt-2 text-center">Demo: spoof path blocks progress — pick Real to continue the happy path.</p>
          )}
        </div>
      )}

      {/* Step 3: QR */}
      {verifyStep === 3 && (
        <div className="trust-card rounded-2xl p-6 animate-fade-in" data-testid="qr-step">
          <h3 className="font-display text-lg font-semibold text-slate-900 dark:text-slate-100 mb-1 tracking-tight">Package QR Verification</h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">Scan the QR code on the package seal to confirm authenticity.</p>
          <QRScan productId={product.id} onVerified={() => setQrVerified(true)} addLog={addLog} />
          {qrVerified && (
            <button onClick={() => setVerifyStep(4)} data-testid="proceed-to-checklist-btn"
              className="w-full mt-4 py-3.5 bg-emerald-600 text-white rounded-xl font-semibold text-sm hover:bg-emerald-700 transition-all animate-scale-in">
              <Check className="w-4 h-4 inline mr-2" />
              Proceed to Checklist
            </button>
          )}
        </div>
      )}

      {/* Step 4: Checklist */}
      {verifyStep === 4 && (
        <div className="trust-card rounded-2xl p-6 animate-fade-in" data-testid="checklist-step">
          <h3 className="font-display text-lg font-semibold text-slate-900 dark:text-slate-100 mb-1 tracking-tight">Package Checklist</h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-5">Complete all checks to confirm receipt of your {product.name}.</p>
          <div className="space-y-3 mb-6">
            {[
              { key: 'seal', label: 'Package seal is intact & unbroken', icon: Shield },
              { key: 'open', label: 'Open package on camera showing contents', icon: Box },
              { key: 'show', label: 'Display product clearly to camera', icon: Eye },
            ].map(({ key, label, icon: Icon }) => (
              <div
                key={key}
                className={`flex items-center gap-3 p-3.5 rounded-xl border transition-all cursor-pointer ${checklist[key] ? 'bg-emerald-50 border-emerald-200 dark:bg-emerald-950/30 dark:border-emerald-800/50' : 'bg-slate-50 border-slate-200 hover:border-slate-300 dark:bg-slate-900/40 dark:border-slate-600 dark:hover:border-slate-500'}`}
                onClick={() => setChecklist(c => ({ ...c, [key]: !c[key] }))}
                data-testid={`checklist-${key}`}
              >
                <Checkbox checked={checklist[key]} onCheckedChange={v => setChecklist(c => ({ ...c, [key]: v }))}
                  className="border-slate-300 data-[state=checked]:bg-emerald-500 data-[state=checked]:border-emerald-500" />
                <Icon className={`w-4 h-4 flex-shrink-0 ${checklist[key] ? 'text-emerald-600' : 'text-slate-400'}`} />
                <span className={`text-sm font-medium ${checklist[key] ? 'text-emerald-700 dark:text-emerald-300' : 'text-slate-600 dark:text-slate-300'}`}>{label}</span>
                {checklist[key] && <Check className="w-4 h-4 text-emerald-500 ml-auto" />}
              </div>
            ))}
          </div>
          <button onClick={handleSubmit} disabled={!(checklist.seal && checklist.open && checklist.show && qrVerified)}
            data-testid="submit-verification-btn"
            className="w-full py-4 bg-rose-600 text-white rounded-xl font-bold text-sm hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all pulse-ring-red">
            Submit Verification
          </button>
        </div>
      )}

      <button onClick={() => { addLog('Dispute raised by buyer during high-risk verification.', 'high'); onComplete('failed'); }}
        data-testid="report-issue-btn-high"
        className="w-full py-3 border border-slate-200 dark:border-slate-600 text-slate-500 dark:text-slate-400 rounded-xl text-sm hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors">
        <AlertTriangle className="w-4 h-4 inline mr-2 text-rose-500" />
        Dispute Order
      </button>
    </div>
  );
}

export default function PostDeliveryScreen({ selectedProduct, riskData, onComplete, addLog }) {
  return (
    <div className="space-y-6">
      <div className="animate-fade-in">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">Step 4 of 5</p>
        <h1 className="font-display text-3xl font-semibold text-slate-900 dark:text-slate-100 tracking-tight">Post-Delivery Verification</h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1">
          {riskData.level === 'low' && 'Low-friction silent window — no action required.'}
          {riskData.level === 'medium' && 'Confirmation window active — fast-forward and verify to release payment.'}
          {riskData.level === 'high' && 'High-value transaction requires 4-factor verification.'}
        </p>
      </div>
      <div className="animate-fade-in-delay-1">
        {riskData.level === 'low' && <LowRiskVerification onComplete={onComplete} addLog={addLog} />}
        {riskData.level === 'medium' && <MediumRiskVerification product={selectedProduct} onComplete={onComplete} addLog={addLog} />}
        {riskData.level === 'high' && <HighRiskVerification product={selectedProduct} onComplete={onComplete} addLog={addLog} />}
      </div>
    </div>
  );
}

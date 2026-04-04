import React, { useState, useEffect, useRef } from 'react';
import { Activity, TrendingUp, Filter, CheckCircle2, XCircle, Clock, ArrowUpRight, Wifi, WifiOff } from 'lucide-react';
import { RISK_CONFIG } from '@/utils/riskEngine';

const SEEDED_TX = [
  { productName: 'Cloud API Subscription', priceLabel: '$49.00/mo', riskLevel: 'low', riskScore: 25.0, paymentStatus: 'Captured', outcome: 'released', buyerName: 'R. Thompson', sellerName: 'DigitalCloud Inc.', minsAgo: 45 },
  { productName: 'MacBook Pro M3 Max', priceLabel: '$3,499.00', riskLevel: 'high', riskScore: 114.4, paymentStatus: 'Held', outcome: 'released', buyerName: 'S. Williams', sellerName: 'TechMart Official', minsAgo: 38 },
  { productName: 'Collectible Sneakers', priceLabel: '$195.00', riskLevel: 'high', riskScore: 120.3, paymentStatus: 'Held', outcome: 'refunded', buyerName: 'T. Park', sellerName: 'Sole Collector Co.', minsAgo: 32 },
  { productName: 'Limited Edition Sneakers', priceLabel: '$299.00', riskLevel: 'medium', riskScore: 51.5, paymentStatus: 'Authorized', outcome: 'released', buyerName: 'J. Kim', sellerName: 'UrbanKicks Store', minsAgo: 28 },
  { productName: 'Swiss Luxury Watch', priceLabel: '$850.00', riskLevel: 'medium', riskScore: 59.6, paymentStatus: 'Authorized', outcome: 'released', buyerName: 'C. Anderson', sellerName: 'LuxeTime Boutique', minsAgo: 22 },
  { productName: 'Cloud API Subscription', priceLabel: '$49.00/mo', riskLevel: 'low', riskScore: 25.0, paymentStatus: 'Captured', outcome: 'released', buyerName: 'K. Martinez', sellerName: 'DigitalCloud Inc.', minsAgo: 18 },
  { productName: 'Collectible Sneakers', priceLabel: '$195.00', riskLevel: 'high', riskScore: 120.3, paymentStatus: 'Held', outcome: 'released', buyerName: 'B. Johnson', sellerName: 'Sole Collector Co.', minsAgo: 14 },
  { productName: 'MacBook Pro M3 Max', priceLabel: '$3,499.00', riskLevel: 'high', riskScore: 114.4, paymentStatus: 'Held', outcome: 'refunded', buyerName: 'D. Wilson', sellerName: 'TechMart Official', minsAgo: 10 },
  { productName: 'Swiss Luxury Watch', priceLabel: '$850.00', riskLevel: 'medium', riskScore: 59.6, paymentStatus: 'Authorized', outcome: 'released', buyerName: 'P. Garcia', sellerName: 'LuxeTime Boutique', minsAgo: 7 },
  { productName: 'Limited Edition Sneakers', priceLabel: '$299.00', riskLevel: 'medium', riskScore: 51.5, paymentStatus: 'Authorized', outcome: 'released', buyerName: 'A. Chen', sellerName: 'UrbanKicks Store', minsAgo: 4 },
];

const LIVE_POOL = [
  { productName: 'Cloud API Subscription', priceLabel: '$49.00/mo', riskLevel: 'low', riskScore: 25.0, paymentStatus: 'Captured', outcome: 'released', buyerName: 'M. Lee', sellerName: 'DigitalCloud Inc.' },
  { productName: 'Collectible Sneakers', priceLabel: '$195.00', riskLevel: 'high', riskScore: 120.3, paymentStatus: 'Held', outcome: 'released', buyerName: 'F. Santos', sellerName: 'Sole Collector Co.' },
  { productName: 'Limited Edition Sneakers', priceLabel: '$299.00', riskLevel: 'medium', riskScore: 51.5, paymentStatus: 'Authorized', outcome: 'released', buyerName: 'G. Brown', sellerName: 'UrbanKicks Store' },
  { productName: 'Swiss Luxury Watch', priceLabel: '$850.00', riskLevel: 'medium', riskScore: 59.6, paymentStatus: 'Authorized', outcome: 'refunded', buyerName: 'L. Davis', sellerName: 'LuxeTime Boutique' },
  { productName: 'MacBook Pro M3 Max', priceLabel: '$3,499.00', riskLevel: 'high', riskScore: 114.4, paymentStatus: 'Held', outcome: 'released', buyerName: 'H. Miller', sellerName: 'TechMart Official' },
  { productName: 'Cloud API Subscription', priceLabel: '$49.00/mo', riskLevel: 'low', riskScore: 25.0, paymentStatus: 'Captured', outcome: 'released', buyerName: 'N. Taylor', sellerName: 'DigitalCloud Inc.' },
  { productName: 'Collectible Sneakers', priceLabel: '$195.00', riskLevel: 'high', riskScore: 120.3, paymentStatus: 'Held', outcome: 'refunded', buyerName: 'O. Clark', sellerName: 'Sole Collector Co.' },
  { productName: 'Swiss Luxury Watch', priceLabel: '$850.00', riskLevel: 'medium', riskScore: 59.6, paymentStatus: 'Authorized', outcome: 'released', buyerName: 'Q. Evans', sellerName: 'LuxeTime Boutique' },
  { productName: 'Limited Edition Sneakers', priceLabel: '$299.00', riskLevel: 'medium', riskScore: 51.5, paymentStatus: 'Authorized', outcome: 'released', buyerName: 'I. Nguyen', sellerName: 'UrbanKicks Store' },
  { productName: 'MacBook Pro M3 Max', priceLabel: '$3,499.00', riskLevel: 'high', riskScore: 114.4, paymentStatus: 'Held', outcome: 'released', buyerName: 'W. Robinson', sellerName: 'TechMart Official' },
];

function timeAgo(ts) {
  const sec = Math.floor((Date.now() - ts) / 1000);
  if (sec < 10) return 'just now';
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  return `${Math.floor(min / 60)}h ago`;
}

function TxRow({ tx, idx }) {
  const cfg = RISK_CONFIG[tx.riskLevel];
  const isReleased = tx.outcome === 'released';
  return (
    <div className={`flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors ${tx.isNew ? 'animate-fade-in' : ''} ${tx.isUser ? 'bg-blue-50/50 dark:bg-blue-950/25' : ''}`}
      data-testid={`tx-row-${idx}`}>
      {/* Risk indicator */}
      <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: cfg.color }} />

      {/* Product + parties */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-semibold text-slate-900 dark:text-slate-100 truncate">{tx.productName}</p>
          {tx.isUser && (
            <span className="flex-shrink-0 text-[10px] font-bold bg-blue-100 text-blue-700 dark:bg-blue-900/60 dark:text-blue-200 px-2 py-0.5 rounded-full">YOU</span>
          )}
          {tx.isNew && !tx.isUser && (
            <span className="flex-shrink-0 text-[10px] font-bold bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300 px-2 py-0.5 rounded-full animate-blink">NEW</span>
          )}
        </div>
        <p className="text-xs text-slate-400 dark:text-slate-500 truncate">{tx.buyerName} → {tx.sellerName}</p>
      </div>

      {/* Risk badge */}
      <span className="hidden sm:inline-flex flex-shrink-0 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase"
        style={{ backgroundColor: cfg.bgSoft, color: cfg.textDark, border: `1px solid ${cfg.border}` }}>
        {tx.riskLevel}
      </span>

      {/* Score */}
      <span className="hidden md:block flex-shrink-0 font-mono text-xs text-slate-500 dark:text-slate-400 w-12 text-right">{tx.riskScore.toFixed(0)}</span>

      {/* Amount */}
      <span className="flex-shrink-0 text-sm font-bold font-mono text-slate-900 dark:text-slate-100">{tx.priceLabel}</span>

      {/* Outcome */}
      <div className={`flex items-center gap-1 flex-shrink-0 px-2.5 py-1 rounded-full text-xs font-semibold ${isReleased ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300' : 'bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300'}`}>
        {isReleased ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
        {isReleased ? 'Released' : 'Refunded'}
      </div>

      {/* Time */}
      <span className="hidden lg:block flex-shrink-0 text-[10px] text-slate-400 dark:text-slate-500 font-mono w-16 text-right">{timeAgo(tx.timestamp)}</span>
    </div>
  );
}

export default function AdminDashboard({ userTransactions }) {
  const [filter, setFilter] = useState('all');
  const [isLive, setIsLive] = useState(true);
  const poolIdxRef = useRef(0);
  const [allTx, setAllTx] = useState(() =>
    SEEDED_TX.map((t, i) => ({
      ...t,
      id: `seed-${i}`,
      timestamp: Date.now() - t.minsAgo * 60000,
      isNew: false,
      isUser: false,
    }))
  );

  // Add user transactions to top when they complete
  useEffect(() => {
    if (!userTransactions.length) return;
    const latest = userTransactions[0];
    setAllTx(prev => {
      if (prev.find(t => t.id === latest.id)) return prev;
      return [{ ...latest, isNew: true, isUser: true }, ...prev];
    });
  }, [userTransactions]);

  // Live simulation ticker
  useEffect(() => {
    if (!isLive) return;
    const delay = () => 2500 + Math.random() * 3500;
    let timer;
    const tick = () => {
      const base = LIVE_POOL[poolIdxRef.current % LIVE_POOL.length];
      poolIdxRef.current++;
      setAllTx(prev => [{ ...base, id: `live-${Date.now()}`, timestamp: Date.now(), isNew: true, isUser: false }, ...prev.slice(0, 99)]);
      timer = setTimeout(tick, delay());
    };
    timer = setTimeout(tick, delay());
    return () => clearTimeout(timer);
  }, [isLive]);

  const filtered = filter === 'all' ? allTx : allTx.filter(t => t.riskLevel === filter);
  const stats = {
    total: allTx.length,
    low: allTx.filter(t => t.riskLevel === 'low').length,
    medium: allTx.filter(t => t.riskLevel === 'medium').length,
    high: allTx.filter(t => t.riskLevel === 'high').length,
    releaseRate: allTx.length ? ((allTx.filter(t => t.outcome === 'released').length / allTx.length) * 100).toFixed(1) : 0,
  };

  const STAT_CARDS = [
    { label: 'Total Tx', value: stats.total, color: 'text-slate-900 dark:text-slate-100', bg: 'bg-slate-50 border-slate-200 dark:bg-slate-800/60 dark:border-slate-600' },
    { label: 'LOW', value: stats.low, color: 'text-emerald-700 dark:text-emerald-400', bg: 'bg-emerald-50 border-emerald-200 dark:bg-emerald-950/35 dark:border-emerald-800/40' },
    { label: 'MEDIUM', value: stats.medium, color: 'text-amber-700 dark:text-amber-400', bg: 'bg-amber-50 border-amber-200 dark:bg-amber-950/30 dark:border-amber-800/40' },
    { label: 'HIGH', value: stats.high, color: 'text-rose-700 dark:text-rose-400', bg: 'bg-rose-50 border-rose-200 dark:bg-rose-950/30 dark:border-rose-800/40' },
    { label: 'Released', value: `${stats.releaseRate}%`, color: 'text-slate-700 dark:text-slate-200', bg: 'bg-slate-50 border-slate-200 dark:bg-slate-800/60 dark:border-slate-600', icon: TrendingUp },
  ];

  return (
    <div className="space-y-6 animate-fade-in" data-testid="admin-dashboard">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 dark:text-slate-500 mb-1">TrustOS Console</p>
          <h1 className="font-display text-3xl font-semibold text-slate-900 dark:text-slate-100 tracking-tight">Transaction Monitor</h1>
          <p className="text-slate-500 dark:text-slate-400 mt-1">Live settlement feed across all TrustOS-controlled transactions.</p>
        </div>
        <button
          onClick={() => setIsLive(l => !l)}
          data-testid="live-toggle-btn"
          className={`flex items-center gap-2 px-4 py-2 rounded-xl border font-semibold text-sm transition-all ${isLive ? 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-950/40 dark:border-emerald-800/50 dark:text-emerald-300 dark:hover:bg-emerald-950/55' : 'bg-slate-100 border-slate-200 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-400 dark:hover:bg-slate-700'}`}
        >
          {isLive ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
          {isLive ? 'LIVE' : 'Paused'}
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {STAT_CARDS.map(s => (
          <div key={s.label} className={`rounded-xl border p-4 ${s.bg}`} data-testid={`stat-${s.label.toLowerCase()}`}>
            <p className="text-xs text-slate-500 dark:text-slate-400 uppercase tracking-wider font-semibold mb-1">{s.label}</p>
            <p className={`text-2xl font-bold font-mono ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>

      {/* Filter + Feed */}
      <div className="trust-card rounded-2xl overflow-hidden" data-testid="tx-feed">
        {/* Filters */}
        <div className="flex items-center gap-2 px-5 py-3.5 border-b border-slate-100 dark:border-slate-700/60 bg-slate-50/50 dark:bg-slate-900/40">
          <Filter className="w-3.5 h-3.5 text-slate-400 dark:text-slate-500" />
          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 mr-1">Filter:</span>
          {['all', 'low', 'medium', 'high'].map(f => {
            const colors = {
              all: 'bg-teal-950 text-white',
              low: 'bg-emerald-500 text-white',
              medium: 'bg-amber-500 text-white',
              high: 'bg-rose-500 text-white',
            };
            return (
              <button key={f} onClick={() => setFilter(f)} data-testid={`filter-${f}`}
                className={`px-3 py-1 rounded-full text-xs font-bold uppercase transition-all ${filter === f ? colors[f] : 'bg-white dark:bg-slate-800 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700'}`}>
                {f}{f !== 'all' && ` (${stats[f]})`}
              </button>
            );
          })}
          <div className="ml-auto flex items-center gap-2">
            {isLive && <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />}
            <span className="text-[11px] text-slate-400 dark:text-slate-500 font-mono">{filtered.length} transactions</span>
          </div>
        </div>

        {/* Column headers */}
        <div className="flex items-center gap-3 px-5 py-2 border-b border-slate-100 dark:border-slate-700/60 bg-slate-50 dark:bg-slate-900/40">
          <div className="w-2 flex-shrink-0" />
          <div className="flex-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">Product / Parties</div>
          <div className="hidden sm:block w-16 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 text-center">Risk</div>
          <div className="hidden md:block w-12 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 text-right">Score</div>
          <div className="w-20 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 text-right">Amount</div>
          <div className="w-20 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 text-center">Outcome</div>
          <div className="hidden lg:block w-16 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500 text-right">Time</div>
        </div>

        {/* Feed */}
        <div className="divide-y divide-slate-50 dark:divide-slate-700/50 max-h-[500px] overflow-y-auto logs-scroll">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-slate-400 dark:text-slate-500">
              <Activity className="w-10 h-10 mb-3 opacity-40" />
              <p className="text-sm font-medium">No transactions yet</p>
              <p className="text-xs mt-1">Complete a transaction to see it here</p>
            </div>
          ) : (
            filtered.map((tx, i) => <TxRow key={tx.id} tx={tx} idx={i} />)
          )}
        </div>
      </div>
    </div>
  );
}

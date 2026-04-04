import React, { useEffect, useRef, useState } from 'react';
import { Terminal, ChevronUp, ChevronDown } from 'lucide-react';

const TYPE_COLORS = {
  system: 'text-sky-400',
  info: 'text-slate-300',
  low: 'text-teal-400',
  medium: 'text-amber-400',
  high: 'text-rose-400',
};

function formatTs(ts) {
  return new Date(ts).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export default function LogsPanel({ logs, mobile }) {
  const bottomRef = useRef(null);
  const [collapsed, setCollapsed] = useState(true);

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  if (mobile) {
    return (
      <div className="bg-[hsl(215_36%_9%)] border-t border-teal-950/40" data-testid="logs-panel-mobile">
        <button
          onClick={() => setCollapsed(c => !c)}
          className="w-full flex items-center justify-between px-4 py-2.5 text-slate-400 hover:text-slate-200 transition-colors"
          data-testid="logs-toggle-btn"
        >
          <div className="flex items-center gap-2">
            <Terminal className="w-3.5 h-3.5" />
            <span className="text-xs font-mono font-medium">TrustOS Engine Log</span>
            <span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-pulse shadow-[0_0_8px_hsl(168_60%_45%/0.6)]" />
          </div>
          {collapsed ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
        {!collapsed && (
          <div className="h-40 overflow-y-auto logs-scroll px-4 pb-3">
            {logs.map((log, i) => (
              <div key={i} className="flex gap-2 py-0.5">
                <span className="text-slate-600 font-mono text-[10px] flex-shrink-0 pt-px">{formatTs(log.ts)}</span>
                <span className={`font-mono text-[11px] leading-relaxed ${TYPE_COLORS[log.type] || 'text-slate-300'}`}>{log.message}</span>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-2xl overflow-hidden border border-teal-950/30 shadow-trust" data-testid="logs-panel">
      <div className="bg-[hsl(215_36%_9%)] px-4 py-3 flex items-center justify-between border-b border-teal-900/25">
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-teal-400/90" />
          <span className="text-xs font-mono font-semibold text-slate-200">TrustOS Engine Log</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-teal-400 animate-blink shadow-[0_0_6px_hsl(168_55%_48%/0.5)]" />
          <span className="text-[10px] text-teal-400 font-mono font-semibold tracking-wide">LIVE</span>
        </div>
      </div>
      <div className="bg-[hsl(215_36%_9%)] h-[calc(100vh-220px)] overflow-y-auto logs-scroll px-4 py-3 space-y-0.5">
        {logs.map((log, i) => (
          <div key={i} className="flex gap-2 py-0.5 animate-fade-in">
            <span className="text-slate-600 font-mono text-[10px] flex-shrink-0 pt-px whitespace-nowrap">{formatTs(log.ts)}</span>
            <span className={`font-mono text-[11px] leading-relaxed break-all ${TYPE_COLORS[log.type] || 'text-slate-300'}`}>
              {log.message}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

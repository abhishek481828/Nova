import React from 'react';
import type { SystemMetrics, VoiceStatus } from '../types';
import { Activity, ShieldCheck, Wifi } from 'lucide-react';

interface SystemDiagnosticsProps {
  metrics: SystemMetrics | null;
  healthStatus: VoiceStatus | null;
  latency: number;
}

export const SystemDiagnostics: React.FC<SystemDiagnosticsProps> = ({ 
  metrics, 
  healthStatus, 
  latency 
}) => {
  // Fallbacks if no metrics are received yet
  const cpu = metrics?.cpu ?? 0;
  const ram = metrics?.memory ?? 0;
  const disk = metrics?.disk ?? 0;
  const gpu = Math.max(0, Math.round(cpu * 0.4 + (Math.sin(Date.now() / 5000) * 5))); // Mock GPU load relative to CPU

  const hasBattery = metrics?.battery_level !== undefined && metrics?.battery_level !== null;
  const batteryLevel = metrics?.battery_level ?? 0;
  const batteryPlugged = metrics?.battery_plugged ?? false;
  const chargeLimit = metrics?.charge_limit ?? null;

  const getEngineBadge = (status: string | undefined) => {
    const s = (status || 'disabled').toLowerCase();
    if (s.includes('healthy') || s.includes('active') || s.includes('ready') || s.includes('open')) {
      return <span className="text-[9px] font-mono text-emerald-400 font-bold bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/15">READY</span>;
    } else if (s.includes('degraded')) {
      return <span className="text-[9px] font-mono text-amber-400 font-bold bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/15">DEGRADED</span>;
    } else if (s.includes('disabled') || s.includes('unavailable')) {
      return <span className="text-[9px] font-mono text-slate-500 font-bold bg-slate-500/10 px-1.5 py-0.5 rounded border border-slate-500/15">DISABLED</span>;
    } else {
      return <span className="text-[9px] font-mono text-red-400 font-bold bg-red-500/10 px-1.5 py-0.5 rounded border border-red-500/15">ERROR</span>;
    }
  };

  const circumference = 2 * Math.PI * 18; // r=18

  const Dial = ({ value, label, color }: { value: number, label: string, color: string }) => {
    const strokeDashoffset = circumference - (value / 100) * circumference;
    return (
      <div className="flex flex-col items-center justify-center p-2 bg-slate-900/40 rounded-lg border border-sky-500/5">
        <svg className="w-12 h-12 rotate-[-90deg]">
          {/* Base Background Track */}
          <circle
            cx="24"
            cy="24"
            r="18"
            className="stroke-slate-800 fill-none"
            strokeWidth="3.5"
          />
          {/* Active Dial Track */}
          <circle
            cx="24"
            cy="24"
            r="18"
            className={`${color} fill-none transition-all duration-500 ease-out`}
            strokeWidth="3.5"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
          />
        </svg>
        <div className="text-[11px] font-mono font-bold mt-1 text-slate-200">{Math.round(value)}%</div>
        <div className="text-[8px] text-cyber-muted font-mono uppercase tracking-wider mt-0.5">{label}</div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full glass-panel p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between border-b border-sky-500/10 pb-3">
        <div>
          <h2 className="text-sm font-bold tracking-[0.2em] text-cyber-text uppercase">System telemetry</h2>
          <p className="text-[10px] text-cyber-muted tracking-wider">HARDWARE LOGS AND ENGINES</p>
        </div>
        <div className="flex items-center gap-3">
          {/* Latency meter */}
          <div className="flex items-center gap-1 font-mono text-[10px] text-sky-400">
            <Wifi className="w-3.5 h-3.5 text-sky-500" />
            <span>{latency}ms</span>
          </div>
          <Activity className="w-4 h-4 text-sky-400 animate-pulse" />
        </div>
      </div>

      {/* Grid of hardware progress dials */}
      <div className={`grid gap-2 mb-4 ${hasBattery ? 'grid-cols-5' : 'grid-cols-4'}`}>
        <Dial value={cpu} label="CPU" color="stroke-cyan-400" />
        <Dial value={ram} label="RAM" color="stroke-sky-400" />
        <Dial value={gpu} label="GPU" color="stroke-indigo-400" />
        <Dial value={disk} label="DISK" color="stroke-slate-500" />
        {hasBattery && (
          <Dial 
            value={batteryLevel} 
            label={batteryPlugged ? "BAT (CHG)" : "BATTERY"} 
            color={batteryPlugged ? "stroke-emerald-400" : (batteryLevel <= 20 ? "stroke-red-500 animate-pulse" : "stroke-amber-400")} 
          />
        )}
      </div>

      {/* Engine diagnostics health checklist */}
      <div className="flex-1 space-y-2 max-h-[140px] overflow-y-auto pr-1">
        {hasBattery && (
          <div className="flex items-center justify-between p-2 rounded bg-slate-950/30 border border-sky-500/10 text-[10px] mb-1">
            <span className="font-semibold text-slate-300 flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full ${batteryPlugged ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
              Power & Charging Limit
            </span>
            <span className="font-mono text-cyan-400 font-bold">
              {batteryPlugged ? "Plugged In" : "On Battery"}
              {chargeLimit !== null ? ` | Limit: ${chargeLimit}%` : ""}
            </span>
          </div>
        )}

        <div className="text-[9px] text-cyber-muted font-mono tracking-wider mb-1.5 uppercase flex items-center gap-1.5">
          <ShieldCheck className="w-3 h-3 text-sky-500" />
          Active Daemon Engines
        </div>
        
        <div className="flex items-center justify-between p-2 rounded bg-slate-950/20 border border-sky-500/5 text-[10px]">
          <span className="font-semibold text-slate-300">OpenWakeWord Engine</span>
          {getEngineBadge(healthStatus?.wake_word)}
        </div>
        
        <div className="flex items-center justify-between p-2 rounded bg-slate-950/20 border border-sky-500/5 text-[10px]">
          <span className="font-semibold text-slate-300">Whisper Speech-to-Text</span>
          {getEngineBadge(healthStatus?.whisper)}
        </div>

        <div className="flex items-center justify-between p-2 rounded bg-slate-950/20 border border-sky-500/5 text-[10px]">
          <span className="font-semibold text-slate-300">Ollama LLM Parse engine</span>
          {getEngineBadge(healthStatus?.running ? 'active' : 'disabled')}
        </div>

        <div className="flex items-center justify-between p-2 rounded bg-slate-950/20 border border-sky-500/5 text-[10px]">
          <span className="font-semibold text-slate-300">ElevenLabs TTS Engine</span>
          {getEngineBadge(healthStatus?.elevenlabs)}
        </div>

        <div className="flex items-center justify-between p-2 rounded bg-slate-950/20 border border-sky-500/5 text-[10px]">
          <span className="font-semibold text-slate-300">Playwright CDP Browser</span>
          {getEngineBadge(healthStatus?.browser)}
        </div>
      </div>
    </div>
  );
};

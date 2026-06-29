import React from 'react';
import { Globe, Compass, ExternalLink, Link, List } from 'lucide-react';
import type { VoiceStatus } from '../types';

interface BrowserMonitorProps {
  healthStatus: VoiceStatus | null;
  currentUrl: string;
  currentTitle: string;
  currentAction: string;
  navProgress: number;
}

export const BrowserMonitor: React.FC<BrowserMonitorProps> = ({ 
  healthStatus, 
  currentUrl, 
  currentTitle, 
  currentAction, 
  navProgress 
}) => {
  const browserHealth = healthStatus?.browser || 'Inactive';
  const isOnline = browserHealth.toLowerCase().includes('active') || browserHealth.toLowerCase().includes('open') || browserHealth.toLowerCase().includes('healthy');

  // Hardcoded mockup of recent tabs since playwright handles these headless/dynamically
  const openTabs = [
    { title: currentTitle || 'New Tab', url: currentUrl || 'about:blank', active: true },
    { title: 'YouTube Media Player', url: 'https://youtube.com', active: false },
    { title: 'ChatGPT Interface', url: 'https://chatgpt.com', active: false },
    { title: 'GitHub Repository', url: 'https://github.com', active: false }
  ];

  return (
    <div className="flex flex-col h-full glass-panel p-4">
      {/* Header */}
      <div className="mb-4 flex items-center justify-between border-b border-sky-500/10 pb-3">
        <div>
          <h2 className="text-sm font-bold tracking-[0.2em] text-cyber-text uppercase">Browser Monitor</h2>
          <p className="text-[10px] text-cyber-muted tracking-wider">PLAYWRIGHT CDP AUTOMATION</p>
        </div>

        {/* Connection Status Badge */}
        <span className={`flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded border ${
          isOnline 
            ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
            : 'bg-slate-500/10 text-slate-400 border-slate-500/20'
        }`}>
          {isOnline ? 'CDP_ACTIVE' : 'CDP_OFFLINE'}
        </span>
      </div>

      {/* Connection Offline view */}
      {!isOnline ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center p-4 text-cyber-muted">
          <Globe className="w-10 h-10 text-slate-600 mb-2 animate-pulse" />
          <p className="text-xs font-semibold">Chromium is currently inactive.</p>
          <p className="text-[10px] mt-0.5 max-w-[200px]">Launch browser tasks via command actions to activate remote monitoring.</p>
        </div>
      ) : (
        <div className="flex-1 flex flex-col space-y-4">
          
          {/* Current URL bar */}
          <div className="relative">
            <div className="flex items-center gap-2 bg-slate-950/80 rounded-lg border border-sky-500/15 p-2 font-mono text-[10px] text-sky-400 select-all">
              <Link className="w-3.5 h-3.5 text-sky-500 flex-shrink-0" />
              <span className="truncate flex-1">{currentUrl || 'about:blank'}</span>
              <a href={currentUrl} target="_blank" rel="noreferrer" className="hover:text-cyan-300">
                <ExternalLink className="w-3.5 h-3.5 flex-shrink-0" />
              </a>
            </div>
            
            {/* Loading progress bar */}
            {navProgress < 100 && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-sky-950 rounded-b-lg overflow-hidden">
                <div 
                  className="h-full bg-cyan-400 transition-all duration-300 shadow-[0_0_8px_#00f2fe]"
                  style={{ width: `${navProgress}%` }}
                />
              </div>
            )}
          </div>

          {/* Current Browser Status & Info */}
          <div className="grid grid-cols-2 gap-3 text-[11px]">
            <div className="p-2 bg-slate-900/40 rounded-lg border border-sky-500/5">
              <span className="text-[9px] text-cyber-muted block uppercase tracking-wider font-mono">Active Tab</span>
              <span className="font-semibold text-slate-200 truncate block mt-0.5">{currentTitle || 'No active tab'}</span>
            </div>
            <div className="p-2 bg-slate-900/40 rounded-lg border border-sky-500/5">
              <span className="text-[9px] text-cyber-muted block uppercase tracking-wider font-mono">Status Action</span>
              <span className="font-semibold text-amber-400 truncate block mt-0.5 uppercase tracking-wide">{currentAction || 'Idle'}</span>
            </div>
          </div>

          {/* Open Tabs mockup section */}
          <div className="flex-1 overflow-y-auto space-y-2 max-h-[140px] pr-1">
            <div className="text-[9px] text-cyber-muted font-mono tracking-wider mb-1.5 uppercase flex items-center gap-1.5">
              <List className="w-3 h-3" />
              Open Tab Orbits ({openTabs.length})
            </div>
            {openTabs.map((tab, idx) => (
              <div 
                key={idx} 
                className={`flex items-center justify-between p-2 rounded border text-[10px] ${
                  tab.active 
                    ? 'bg-sky-500/5 border-sky-500/20 text-sky-300' 
                    : 'bg-slate-950/20 border-sky-500/5 text-slate-400'
                }`}
              >
                <div className="flex items-center gap-2 truncate">
                  <Compass className={`w-3.5 h-3.5 flex-shrink-0 ${tab.active ? 'text-sky-400 animate-spin-slow' : 'text-slate-600'}`} />
                  <span className="truncate font-medium">{tab.title}</span>
                </div>
                <span className="text-[8px] font-mono opacity-60 ml-2 truncate max-w-[80px]">{tab.url.replace('https://', '')}</span>
              </div>
            ))}
          </div>

        </div>
      )}
    </div>
  );
};

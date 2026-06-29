import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { NovaEvent } from '../types';
import { ChevronDown, ChevronUp, Search, SlidersHorizontal } from 'lucide-react';

interface EventTimelineProps {
  events: NovaEvent[];
}

export const EventTimeline: React.FC<EventTimelineProps> = ({ events }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedModule, setSelectedModule] = useState<string>('ALL');
  const [expandedEventId, setExpandedEventId] = useState<number | null>(null);

  // Derive unique list of modules for selection tags
  const modulesList = ['ALL', ...Array.from(new Set(events.map(e => e.module.toUpperCase())))];

  // Filters logic
  const filteredEvents = events.filter(e => {
    const matchesSearch = 
      e.event.toLowerCase().includes(searchQuery.toLowerCase()) ||
      e.module.toLowerCase().includes(searchQuery.toLowerCase()) ||
      JSON.stringify(e.metadata || {}).toLowerCase().includes(searchQuery.toLowerCase());
      
    const matchesModule = selectedModule === 'ALL' || e.module.toUpperCase() === selectedModule;
    
    return matchesSearch && matchesModule;
  });

  const getModuleBadgeColor = (mod: string) => {
    const m = mod.toLowerCase();
    if (m === 'core') return 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20';
    if (m === 'voice') return 'bg-red-500/10 text-red-400 border-red-500/20';
    if (m === 'stt') return 'bg-purple-500/10 text-purple-400 border-purple-500/20';
    if (m === 'llm') return 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20';
    if (m === 'browser') return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
    if (m === 'executor') return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    if (m === 'logger') return 'bg-slate-500/10 text-slate-400 border-slate-500/20';
    return 'bg-sky-500/10 text-sky-400 border-sky-500/20';
  };

  const getStatusColor = (status: string) => {
    const s = status.toLowerCase();
    if (s === 'success') return 'bg-emerald-500';
    if (s === 'failed' || s === 'error') return 'bg-red-500';
    if (s === 'running') return 'bg-sky-400 animate-pulse';
    return 'bg-slate-500';
  };

  const toggleExpand = (idx: number) => {
    setExpandedEventId(expandedEventId === idx ? null : idx);
  };

  const getFormattedTime = (isoString: string) => {
    try {
      const d = new Date(isoString);
      if (isNaN(d.getTime())) return '00:00:00';
      return d.toLocaleTimeString();
    } catch {
      return '00:00:00';
    }
  };

  return (
    <div className="flex flex-col h-full glass-panel p-4">
      {/* Header */}
      <div className="mb-4 border-b border-sky-500/10 pb-3 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold tracking-[0.2em] text-cyber-text uppercase">Mission Logs & Timeline</h2>
          <p className="text-[10px] text-cyber-muted tracking-wider">CHRONOLOGICAL EVENT DISPATCHER</p>
        </div>
        
        {/* Search Input Bar */}
        <div className="relative flex-1 max-w-xs">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search events, actions..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-950/80 border border-sky-500/15 rounded-lg pl-8 pr-3 py-1.5 text-xs text-cyber-text placeholder-slate-500 focus:outline-none focus:border-cyan-400 transition-colors"
          />
        </div>
      </div>

      {/* Module filtering tags list */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        <span className="flex items-center gap-1 text-[9px] font-mono text-cyber-muted mr-1.5 select-none uppercase">
          <SlidersHorizontal className="w-3 h-3" />
          Filter:
        </span>
        {modulesList.map(mod => (
          <button
            key={mod}
            onClick={() => setSelectedModule(mod)}
            className={`px-2 py-0.5 rounded text-[9px] font-mono border transition-all duration-150 ${
              selectedModule === mod 
                ? 'bg-sky-500/15 border-sky-500/35 text-sky-300 shadow-[0_0_8px_rgba(56,189,248,0.1)]' 
                : 'bg-slate-950/20 border-sky-500/5 text-slate-400 hover:border-sky-500/15'
            }`}
          >
            {mod}
          </button>
        ))}
      </div>

      {/* Scrollable Logs timeline */}
      <div className="flex-1 overflow-y-auto pr-1 space-y-2 max-h-[300px]">
        {filteredEvents.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-6 text-cyber-muted">
            <p className="text-xs">No matching system events found.</p>
          </div>
        ) : (
          filteredEvents.map((evt, idx) => {
            const isExpanded = expandedEventId === idx;
            return (
              <div 
                key={idx} 
                className="rounded-lg border border-sky-500/5 bg-slate-900/[0.15] hover:bg-slate-900/[0.25] transition-all duration-200"
              >
                <div 
                  onClick={() => toggleExpand(idx)}
                  className="flex items-center justify-between p-2.5 cursor-pointer select-none"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    {/* Status Dot */}
                    <span className={`w-2 h-2 rounded-full ${getStatusColor(evt.status)} flex-shrink-0`} />
                    
                    {/* Log timestamp */}
                    <span className="text-[10px] font-mono text-cyber-muted flex-shrink-0">
                      [{getFormattedTime(evt.timestamp)}]
                    </span>
                    
                    {/* Module Tag */}
                    <span className={`text-[8px] font-mono font-bold px-1.5 py-0.2 rounded border uppercase flex-shrink-0 ${getModuleBadgeColor(evt.module)}`}>
                      {evt.module}
                    </span>

                    {/* Event name */}
                    <span className="text-xs font-semibold text-slate-200 truncate tracking-wide">
                      {evt.event}
                    </span>
                  </div>

                  <div className="text-cyber-muted">
                    {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </div>
                </div>

                {/* Collapsible details pane */}
                <AnimatePresence>
                  {isExpanded && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                      className="overflow-hidden border-t border-sky-500/5"
                    >
                      <div className="p-3 bg-slate-950/50 text-[10px] font-mono text-cyber-muted">
                        <div className="mb-1 text-slate-400 font-semibold uppercase tracking-wider text-[8px]">Event Metadata Payload</div>
                        <pre className="overflow-x-auto bg-black/40 p-2 rounded max-h-36 text-[10px] text-cyan-300/80">
                          <code>{JSON.stringify(evt.metadata, null, 2)}</code>
                        </pre>
                        <div className="mt-2 flex gap-4 text-[9px] text-slate-500">
                          <span>Status code: {evt.status.toUpperCase()}</span>
                          <span>Timestamp: {evt.timestamp}</span>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

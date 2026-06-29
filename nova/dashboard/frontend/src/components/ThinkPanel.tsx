import React from 'react';
import { CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react';

interface ThinkingStep {
  id: string;
  label: string;
  getStatus: (activeState: string, lastEvent: string | null) => 'pending' | 'active' | 'success' | 'failed';
}

interface ThinkPanelProps {
  activeState: string;
  lastEventName: string | null;
}

export const ThinkPanel: React.FC<ThinkPanelProps> = ({ activeState, lastEventName }) => {
  const steps: ThinkingStep[] = [
    {
      id: 'wake',
      label: 'Wake word detected',
      getStatus: (state) => {
        if (state === 'WAKE_DETECTED' || state === 'LISTENING' || state === 'TRANSCRIBING' || state === 'EXECUTING' || state === 'SPEAKING') {
          return 'success';
        }
        return 'pending';
      }
    },
    {
      id: 'record',
      label: 'Recording command',
      getStatus: (state) => {
        if (state === 'LISTENING') return 'active';
        if (state === 'TRANSCRIBING' || state === 'EXECUTING' || state === 'SPEAKING') return 'success';
        return 'pending';
      }
    },
    {
      id: 'stt',
      label: 'Speech recognized (STT)',
      getStatus: (state, lastEvent) => {
        if (state === 'TRANSCRIBING') return 'active';
        if (state === 'EXECUTING' || state === 'SPEAKING') return 'success';
        if (lastEvent === 'transcription_complete' && state === 'VOICE_IDLE') return 'success';
        return 'pending';
      }
    },
    {
      id: 'intent',
      label: 'Intent parsed (LLM)',
      getStatus: (state) => {
        // Active during initial EXECUTING parsing phase, success once actions are running
        if (state === 'EXECUTING') return 'active';
        if (state === 'SPEAKING') return 'success';
        return 'pending';
      }
    },
    {
      id: 'plan',
      label: 'Planning operations',
      getStatus: (state, lastEvent) => {
        if (lastEvent === 'action_parsed' && state === 'EXECUTING') return 'active';
        if (state === 'SPEAKING' || (lastEvent === 'task_completed')) return 'success';
        return 'pending';
      }
    },
    {
      id: 'exec',
      label: 'Executing action tasks',
      getStatus: (state, lastEvent) => {
        if (state === 'EXECUTING' && lastEvent === 'command_executing') return 'active';
        if (state === 'SPEAKING' || lastEvent === 'task_completed') return 'success';
        return 'pending';
      }
    },
    {
      id: 'completed',
      label: 'Completed sequence',
      getStatus: (_, lastEvent) => {
        if (lastEvent === 'task_completed') {
          return 'success';
        }
        return 'pending';
      }
    }
  ];

  const renderIcon = (status: 'pending' | 'active' | 'success' | 'failed') => {
    switch (status) {
      case 'success':
        return <CheckCircle2 className="w-4 h-4 text-emerald-400 drop-shadow-[0_0_4px_rgba(16,185,129,0.3)]" />;
      case 'active':
        return <Loader2 className="w-4 h-4 text-sky-400 animate-spin" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-500" />;
      case 'pending':
      default:
        return <Circle className="w-4 h-4 text-slate-600" />;
    }
  };

  return (
    <div className="flex flex-col h-full glass-panel p-4">
      {/* Title */}
      <div className="mb-4 border-b border-sky-500/10 pb-3">
        <h2 className="text-sm font-bold tracking-[0.2em] text-cyber-text uppercase">Live Thinking Matrix</h2>
        <p className="text-[10px] text-cyber-muted tracking-wider">SEQUENCE PROCESSING STAGES</p>
      </div>

      {/* Step List */}
      <div className="flex-1 flex flex-col justify-center space-y-4">
        {steps.map(step => {
          const status = step.getStatus(activeState, lastEventName);
          return (
            <div 
              key={step.id} 
              className={`flex items-center gap-3.5 px-3 py-2.5 rounded-lg border transition-all duration-200 ${
                status === 'active' 
                  ? 'border-sky-500/20 bg-sky-500/[0.04]' 
                  : status === 'success'
                  ? 'border-transparent bg-emerald-500/[0.01]'
                  : 'border-transparent'
              }`}
            >
              <div>
                {renderIcon(status)}
              </div>
              <div className="flex-1">
                <span className={`text-xs font-semibold ${
                  status === 'active' 
                    ? 'text-sky-300 font-mono tracking-wide' 
                    : status === 'success'
                    ? 'text-slate-300 font-medium'
                    : 'text-slate-500'
                }`}>
                  {step.label}
                </span>
              </div>
              
              {/* Optional state tag */}
              {status === 'active' && (
                <span className="text-[8px] font-mono font-bold text-sky-400 bg-sky-500/10 px-1.5 py-0.5 rounded animate-pulse">
                  PROCESSING
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

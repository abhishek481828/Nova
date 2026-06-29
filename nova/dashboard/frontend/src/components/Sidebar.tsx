import React from 'react';
import { 
  Mic, 
  Globe, 
  Cpu, 
  Database, 
  Cpu as AutomationIcon, 
  FolderOpen, 
  Grid, 
  Settings 
} from 'lucide-react';
import type { VoiceStatus } from '../types';

interface SidebarProps {
  healthStatus: VoiceStatus | null;
  activeState: string;
}

type SubsystemStatus = 'online' | 'offline' | 'busy' | 'error';

interface SubsystemItem {
  id: string;
  name: string;
  icon: React.ReactNode;
  getStatus: (health: VoiceStatus | null, state: string) => SubsystemStatus;
}

export const Sidebar: React.FC<SidebarProps> = ({ healthStatus, activeState }) => {
  const subsystems: SubsystemItem[] = [
    {
      id: 'voice',
      name: 'Voice Subsystem',
      icon: <Mic className="w-4 h-4" />,
      getStatus: (health) => {
        if (!health) return 'offline';
        const mic = health.microphone.toLowerCase();
        const whisper = health.whisper.toLowerCase();
        if (mic.includes('fail') || whisper.includes('fail')) return 'error';
        if (activeState === 'LISTENING' || activeState === 'SPEAKING') return 'busy';
        if (mic.includes('active') || mic.includes('healthy') || mic.includes('ready')) return 'online';
        return 'offline';
      }
    },
    {
      id: 'browser',
      name: 'Browser automation',
      icon: <Globe className="w-4 h-4" />,
      getStatus: (health) => {
        if (!health) return 'offline';
        const br = health.browser.toLowerCase();
        if (br.includes('fail') || br.includes('error')) return 'error';
        if (activeState === 'EXECUTING' && br.includes('active')) return 'busy';
        if (br.includes('active') || br.includes('healthy') || br.includes('open')) return 'online';
        return 'offline';
      }
    },
    {
      id: 'llm',
      name: 'Intent parser LLM',
      icon: <Cpu className="w-4 h-4" />,
      getStatus: (health) => {
        if (!health) return 'offline';
        // Since LLM health isn't direct in VoiceStatus, tie to execution cycle
        if (activeState === 'TRANSCRIBING') return 'busy';
        if (health.running) return 'online';
        return 'offline';
      }
    },
    {
      id: 'memory',
      name: 'Context memory',
      icon: <Database className="w-4 h-4" />,
      getStatus: () => {
        // Core DB is local memory
        return 'online';
      }
    },
    {
      id: 'automation',
      name: 'Shell Executor',
      icon: <AutomationIcon className="w-4 h-4" />,
      getStatus: (_, state) => {
        if (state === 'EXECUTING') return 'busy';
        return 'online';
      }
    },
    {
      id: 'files',
      name: 'File Manager',
      icon: <FolderOpen className="w-4 h-4" />,
      getStatus: () => 'online'
    },
    {
      id: 'plugins',
      name: 'Action handlers',
      icon: <Grid className="w-4 h-4" />,
      getStatus: () => 'online'
    },
    {
      id: 'settings',
      name: 'System Config',
      icon: <Settings className="w-4 h-4" />,
      getStatus: () => 'online'
    }
  ];

  const getStatusBadge = (status: SubsystemStatus) => {
    switch (status) {
      case 'online':
        return (
          <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            ONLINE
          </span>
        );
      case 'busy':
        return (
          <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium font-mono bg-purple-500/10 text-purple-400 border border-purple-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-ping" />
            BUSY
          </span>
        );
      case 'error':
        return (
          <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium font-mono bg-red-500/10 text-red-400 border border-red-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
            ERROR
          </span>
        );
      case 'offline':
      default:
        return (
          <span className="flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium font-mono bg-slate-500/10 text-slate-400 border border-slate-500/20">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
            OFFLINE
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col h-full glass-panel border-r border-cyber-panelBorder p-4">
      {/* Title */}
      <div className="mb-6">
        <h2 className="text-sm font-bold tracking-[0.2em] text-cyber-text uppercase">Nova Subsystems</h2>
        <p className="text-[10px] text-cyber-muted tracking-wider">REALTIME CORE CONNECTIONS</p>
      </div>

      {/* Subsystem Navigation List */}
      <nav className="flex-1 space-y-2.5 overflow-y-auto pr-1">
        {subsystems.map(sub => {
          const status = sub.getStatus(healthStatus, activeState);
          return (
            <div 
              key={sub.id} 
              className="flex items-center justify-between p-3 rounded-lg border border-transparent hover:border-sky-500/10 hover:bg-sky-500/[0.02] transition-all duration-200"
            >
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-sky-500/5 text-sky-400 border border-sky-500/10">
                  {sub.icon}
                </div>
                <div>
                  <div className="text-xs font-semibold text-cyber-text tracking-wide">{sub.name}</div>
                  <div className="text-[9px] text-cyber-muted font-mono">{sub.id.toUpperCase()}://local</div>
                </div>
              </div>
              <div>
                {getStatusBadge(status)}
              </div>
            </div>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div className="mt-6 pt-4 border-t border-sky-500/5 flex flex-col gap-1 text-[10px] text-cyber-muted font-mono">
        <div>DAEMON: online</div>
        <div>CLIENT: v3.2.0-rc1</div>
        <div>HOST: nixos-desktop</div>
      </div>
    </div>
  );
};

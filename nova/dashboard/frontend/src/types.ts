export interface NovaEvent {
  timestamp: string;
  module: string;
  event: string;
  status: 'running' | 'success' | 'failed' | 'idle';
  metadata: Record<string, any>;
}

export interface VoiceStatus {
  running: boolean;
  state: string;
  wake_word: string;
  whisper: string;
  elevenlabs: string;
  browser: string;
  microphone: string;
  health: string;
}

export interface SystemMetrics {
  cpu: number;
  memory: number;
  disk: number;
  browser_active: boolean;
}

export interface ToastMessage {
  id: string;
  title: string;
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
  timestamp: string;
}

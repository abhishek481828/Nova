import { useEffect, useState, useRef } from 'react';
import { Sidebar } from './components/Sidebar';
import { NovaCore } from './components/NovaCore';
import { ChatPanel } from './components/ChatPanel';
import type { ChatMessage } from './components/ChatPanel';
import { ThinkPanel } from './components/ThinkPanel';
import { BrowserMonitor } from './components/BrowserMonitor';
import { SystemDiagnostics } from './components/SystemDiagnostics';
import { EventTimeline } from './components/EventTimeline';
import { ToastContainer } from './components/ToastContainer';
import type { NovaEvent, SystemMetrics, VoiceStatus, ToastMessage } from './types';
import { Shield, Power } from 'lucide-react';

function App() {
  const [activeState, setActiveState] = useState<string>('INACTIVE');
  const [healthStatus, setHealthStatus] = useState<VoiceStatus | null>(null);
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
  const [events, setEvents] = useState<NovaEvent[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [latency, setLatency] = useState<number>(12);
  const [currentUrl, setCurrentUrl] = useState<string>('about:blank');
  const [currentTitle, setCurrentTitle] = useState<string>('New Tab');
  const [currentAction, setCurrentAction] = useState<string>('IDLE');
  const [navProgress, setNavProgress] = useState<number>(100);
  const [socketStatus, setSocketStatus] = useState<'CONNECTING' | 'ONLINE' | 'OFFLINE'>('CONNECTING');

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const activeUserMsgIdRef = useRef<string | null>(null);
  const isTextQueryPending = useRef<boolean>(false);

  // Trigger floating notifications helper
  const addToast = (title: string, message: string, type: ToastMessage['type'] = 'info') => {
    const id = Math.random().toString(36).substring(2, 9);
    const newToast: ToastMessage = {
      id,
      title,
      message,
      type,
      timestamp: new Date().toLocaleTimeString()
    };
    setToasts(prev => [newToast, ...prev].slice(0, 5)); // Keep last 5 toasts

    // Dismiss toast automatically after 5 seconds
    setTimeout(() => {
      dismissToast(id);
    }, 5000);
  };

  const dismissToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  };

  // Send a typed text command over WebSocket to the backend
  const sendTextInput = (text: string) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      isTextQueryPending.current = true;
      // Append user bubble directly to conversation panel state
      const localId = Math.random().toString(36).substring(2, 9);
      setMessages(prev => [
        ...prev,
        {
          id: localId,
          sender: 'user',
          text,
          timestamp: new Date().toLocaleTimeString()
        }
      ]);

      // Emit command event JSON
      socketRef.current.send(JSON.stringify({
        action: "user_text_input",
        text
      }));
      addToast('Command Sent', `Forwarding to core: "${text}"`, 'success');
    } else {
      addToast('Connection Offline', 'Cannot send command. WebSocket offline.', 'error');
    }
  };

  // Connect to backend websocket server
  const connectWebSocket = () => {
    if (socketRef.current) {
      socketRef.current.close();
    }

    setSocketStatus('CONNECTING');
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Port 11436 is hardcoded as per system specifications
    const wsHost = window.location.hostname === 'localhost' || !window.location.hostname 
      ? '127.0.0.1:11436' 
      : `${window.location.hostname}:11436`;
      
    const wsUrl = `${wsProtocol}//${wsHost}/ws`;
    
    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      setSocketStatus('ONLINE');
      addToast('System Link Connected', 'Established high-speed socket link to Nova Core.', 'success');
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };

    ws.onmessage = (event) => {
      try {
        const payload: NovaEvent = JSON.parse(event.data);
        handleIncomingEvent(payload);
      } catch (err) {
        console.error('Error parsing event frame', err);
      }
    };

    ws.onclose = () => {
      setSocketStatus('OFFLINE');
      addToast('System Link Disconnected', 'Retrying connection in 3 seconds...', 'warning');
      reconnectTimeoutRef.current = window.setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = () => {
      ws.close();
    };
  };

  useEffect(() => {
    connectWebSocket();
    return () => {
      if (socketRef.current) socketRef.current.close();
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };
  }, []);

  // Central Event Routing Matrix
  const handleIncomingEvent = (evt: NovaEvent) => {
    // Append to live chronological log timeline (cap at 200 logs to preserve RAM)
    setEvents(prev => [evt, ...prev].slice(0, 200));

    // Calculate latency mock variance
    setLatency(() => {
      const base = 8;
      const jitter = Math.round(Math.random() * 6);
      return base + jitter;
    });

    switch (evt.event) {
      case 'health_status':
        const voiceHealth: VoiceStatus = evt.metadata as VoiceStatus;
        setHealthStatus(voiceHealth);
        if (voiceHealth.state) {
          setActiveState(voiceHealth.state);
        }
        break;

      case 'system_metrics':
        setMetrics(evt.metadata as SystemMetrics);
        break;

      case 'voice_state_change':
        const newState = evt.metadata.state || 'INACTIVE';
        setActiveState(newState);
        
        if (newState === 'LISTENING') {
          // Push new user bubble structure
          const userMsgId = Math.random().toString(36).substring(2, 9);
          activeUserMsgIdRef.current = userMsgId;
          setMessages(prev => [
            ...prev,
            {
              id: userMsgId,
              sender: 'user',
              text: 'Listening for operators command...',
              timestamp: new Date().toLocaleTimeString(),
              isStreaming: true
            }
          ]);
        }
        break;

      case 'speech_started':
        setActiveState('LISTENING');
        break;

      case 'speech_finished':
        if (evt.status === 'failed') {
          addToast('Recording Aborted', 'No vocal input captured by system.', 'warning');
          // Update last user message
          if (activeUserMsgIdRef.current) {
            setMessages(prev => prev.map(m => 
              m.id === activeUserMsgIdRef.current 
                ? { ...m, text: '[Recording failed/Aborted]', isStreaming: false } 
                : m
            ));
            activeUserMsgIdRef.current = null;
          }
        }
        break;

      case 'transcription_partial':
        setActiveState('TRANSCRIBING');
        // Update user message to reflect transcribing state
        if (activeUserMsgIdRef.current) {
          setMessages(prev => prev.map(m => 
            m.id === activeUserMsgIdRef.current 
              ? { ...m, text: 'Recognizing vocal command...' } 
              : m
          ));
        }
        break;

      case 'transcription_complete':
        if (evt.status === 'success') {
          const raw = evt.metadata.raw_text || '';
          const corrected = evt.metadata.corrected_text || raw;
          
          if (activeUserMsgIdRef.current) {
            setMessages(prev => prev.map(m => 
              m.id === activeUserMsgIdRef.current 
                ? { ...m, text: corrected, isStreaming: false } 
                : m
            ));
            activeUserMsgIdRef.current = null;
          } else {
            // Backup creation
            setMessages(prev => [
              ...prev,
              {
                id: Math.random().toString(36).substring(2, 9),
                sender: 'user',
                text: corrected,
                timestamp: new Date().toLocaleTimeString()
              }
            ]);
          }
          addToast('Speech Heard', `Recognized: "${corrected}"`, 'success');
        } else {
          addToast('Transcription Error', evt.metadata.error || 'Whisper pipeline failed.', 'error');
        }
        break;

      case 'llm_started':
        setActiveState('TRANSCRIBING');
        setCurrentAction('PARSING INTENT');
        break;

      case 'llm_finished':
        setCurrentAction('IDLE');
        if (evt.status === 'success') {
          addToast('Intent Parsed', 'Model processed intent successfully.', 'success');
        } else {
          addToast('Intent Parse Error', evt.metadata.error || 'Ollama parser crashed.', 'error');
        }
        break;

      case 'tts_started':
        setActiveState('SPEAKING');
        const speakText = evt.metadata.text || '';
        setMessages(prev => [
          ...prev,
          {
            id: Math.random().toString(36).substring(2, 9),
            sender: 'nova',
            text: speakText,
            timestamp: new Date().toLocaleTimeString()
          }
        ]);
        addToast('Voice Synthesizing', speakText.length > 30 ? speakText.substring(0, 30) + '...' : speakText, 'info');
        break;

      case 'tts_finished':
        setActiveState('VOICE_IDLE');
        break;

      case 'browser_opening':
        setCurrentAction('LAUNCHING BROWSER');
        setNavProgress(30);
        addToast('Browser Automator', 'Spinning up Chromium CDP profile...', 'info');
        break;

      case 'browser_connected':
        setCurrentAction('BROWSER ACTIVE');
        setNavProgress(100);
        addToast('Browser Connected', 'CDP Remote debugger active.', 'success');
        break;

      case 'youtube_search':
        setCurrentAction('YOUTUBE PLAYBACK');
        setCurrentUrl('https://youtube.com');
        setCurrentTitle(`Play: ${evt.metadata.query}`);
        setNavProgress(evt.status === 'success' ? 100 : 50);
        if (evt.status === 'running') {
          addToast('YouTube automation', `Searching track: "${evt.metadata.query}"`, 'info');
        } else if (evt.status === 'success') {
          addToast('Song Playing', `Playing: "${evt.metadata.title}"`, 'success');
        } else {
          addToast('YouTube Error', evt.metadata.error || 'Failed to locate video.', 'error');
        }
        break;

      case 'action_parsed':
        setActiveState('EXECUTING');
        const act = evt.metadata.action || '';
        setCurrentAction(`RUNNING: ${act.toUpperCase()}`);
        if (evt.metadata.parameters?.url) {
          setCurrentUrl(evt.metadata.parameters.url);
          setCurrentTitle(evt.metadata.parameters.url);
          setNavProgress(40);
        }
        break;

      case 'task_completed':
        setActiveState('VOICE_IDLE');
        setCurrentAction('IDLE');
        setNavProgress(100);
        
        const actionCompleted = evt.metadata.action || 'Unknown';
        const msgResult = evt.metadata.message || 'Execution completed.';
        
        if (evt.status === 'success') {
          addToast('Task Completed', `Successfully executed: ${actionCompleted}`, 'success');
          // Log output to chat if browser navigate
          if (actionCompleted === 'open' && evt.metadata.message) {
            // Find page title if present
            const tabTitle = evt.metadata.message.includes('focused') ? 'focused page' : 'page';
            setCurrentTitle(tabTitle);
          }
          
          if (isTextQueryPending.current) {
            setMessages(prev => [
              ...prev,
              {
                id: Math.random().toString(36).substring(2, 9),
                sender: 'nova',
                text: msgResult,
                timestamp: new Date().toLocaleTimeString()
              }
            ]);
            isTextQueryPending.current = false;
          }
        } else {
          addToast('Task Failed', `Failed action: ${actionCompleted}`, 'error');
          if (isTextQueryPending.current) {
            setMessages(prev => [
              ...prev,
              {
                id: Math.random().toString(36).substring(2, 9),
                sender: 'nova',
                text: `Error executing ${actionCompleted}: ${msgResult}`,
                timestamp: new Date().toLocaleTimeString()
              }
            ]);
            isTextQueryPending.current = false;
          }
        }
        break;
      
      case 'command_executing':
        addToast('Command Executing', `Shell: ${evt.metadata.command}`, 'info');
        break;

      default:
        break;
    }
  };

  return (
    <div className="h-screen w-screen bg-cyber-bg text-cyber-text flex flex-col font-sans overflow-hidden">
      
      {/* Top Banner Control Header */}
      <header className="h-14 flex-shrink-0 flex items-center justify-between px-6 border-b border-cyber-panelBorder glass-panel z-20">
        <div className="flex items-center gap-3">
          <Shield className="w-5 h-5 text-cyan-400 drop-shadow-[0_0_8px_rgba(0,242,254,0.4)]" />
          <div>
            <h1 className="text-sm font-bold tracking-[0.3em] uppercase glow-text-cyan">Nova Mission Control</h1>
            <p className="text-[9px] text-cyber-muted tracking-wider font-mono">SECURE AI DESKTOP SHELL</p>
          </div>
        </div>

        {/* WebSocket Daemon Connection State Badge */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${
              socketStatus === 'ONLINE' ? 'bg-emerald-500 animate-pulse' : 
              socketStatus === 'CONNECTING' ? 'bg-amber-500 animate-ping' : 'bg-red-500'
            }`} />
            <span className="text-[10px] font-mono font-bold tracking-wider">
              DAEMON_{socketStatus}
            </span>
          </div>

          <div className="w-px h-6 bg-sky-500/10" />

          {/* Core System Status Button */}
          <button className="flex items-center gap-1.5 px-3 py-1 rounded bg-red-500/10 border border-red-500/35 hover:bg-red-500/20 text-[10px] font-mono font-bold text-red-400 transition-colors">
            <Power className="w-3.5 h-3.5" />
            STANDBY
          </button>
        </div>
      </header>

      {/* Main Workspace Grid Layout */}
      <div className="flex-1 flex overflow-hidden">
        
        {/* Left Subsystem Sidebar Panel (w-72) */}
        <aside className="w-72 flex-shrink-0 h-full">
          <Sidebar healthStatus={healthStatus} activeState={activeState} />
        </aside>

        {/* Center / Right Multi-column Grid workspace */}
        <main className="flex-1 grid grid-cols-12 gap-4 p-4 overflow-hidden">
          
          {/* Main Visualizer Core (Grid cols 1 to 4) */}
          <section className="col-span-4 h-full flex flex-col gap-4">
            <div className="flex-1 min-h-[300px]">
              <div className="h-full glass-panel flex items-center justify-center p-4">
                <NovaCore state={activeState} />
              </div>
            </div>
            {/* Live steps panel */}
            <div className="flex-shrink-0 h-[280px]">
              <ThinkPanel activeState={activeState} lastEventName={events[0]?.event || null} />
            </div>
          </section>

          {/* Dialogue & Console Output Columns (Grid cols 5 to 8) */}
          <section className="col-span-4 h-full flex flex-col gap-4">
            <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
              <ChatPanel messages={messages} activeState={activeState} onSendText={sendTextInput} />
            </div>
            {/* Browser panel */}
            <div className="flex-shrink-0 h-[250px]">
              <BrowserMonitor 
                healthStatus={healthStatus} 
                currentUrl={currentUrl} 
                currentTitle={currentTitle} 
                currentAction={currentAction}
                navProgress={navProgress}
              />
            </div>
          </section>

          {/* Right Metrics & Log Timelines (Grid cols 9 to 12) */}
          <section className="col-span-4 h-full flex flex-col gap-4">
            <div className="flex-shrink-0 h-[220px]">
              <SystemDiagnostics 
                metrics={metrics} 
                healthStatus={healthStatus} 
                latency={latency} 
              />
            </div>
            {/* Log events timeline */}
            <div className="flex-1 min-h-[200px]">
              <EventTimeline events={events} />
            </div>
          </section>

        </main>
      </div>

      {/* Floating sliding Notifications container */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}

export default App;

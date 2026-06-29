import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { User, Send } from 'lucide-react';

export interface ChatMessage {
  id: string;
  sender: 'user' | 'nova';
  text: string;
  timestamp: string;
  isStreaming?: boolean;
}

interface ChatPanelProps {
  messages: ChatMessage[];
  activeState: string;
  onSendText?: (text: string) => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({ messages, activeState, onSendText }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [inputText, setInputText] = useState('');

  // Auto-scroll to the bottom of the dialogue stream
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [messages, activeState]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim()) return;
    if (onSendText) {
      onSendText(inputText.trim());
      setInputText('');
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0 glass-panel p-4 overflow-hidden">
      {/* Header */}
      <div className="flex-shrink-0 mb-4 flex items-center justify-between border-b border-sky-500/10 pb-3">
        <div>
          <h2 className="text-sm font-bold tracking-[0.2em] text-cyber-text uppercase">Dialogue Stream</h2>
          <p className="text-[10px] text-cyber-muted tracking-wider">LIVE TRANSLATION AND FEEDBACK</p>
        </div>
        
        {/* Core State Indicator in Chat */}
        {activeState !== 'INACTIVE' && activeState !== 'VOICE_IDLE' && (
          <span className="flex items-center gap-1.5 text-[10px] font-semibold text-sky-400 bg-sky-500/10 px-2 py-0.5 rounded border border-sky-500/20">
            <span className="w-1.5 h-1.5 bg-sky-400 rounded-full animate-ping" />
            {activeState}
          </span>
        )}
      </div>

      {/* Message Scroll Area */}
      <div 
        ref={containerRef}
        className="flex-1 min-h-0 overflow-y-auto space-y-4 pr-1 scroll-smooth"
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-6 text-cyber-muted">
            <div className="text-3xl mb-2">💬</div>
            <p className="text-xs">No active dialogue stream recorded.</p>
            <p className="text-[10px] mt-1 opacity-70">Say your wake word "Nova" or type a command below.</p>
          </div>
        ) : (
          <AnimatePresence initial={false}>
            {messages.map(msg => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 15, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.25, ease: "easeOut" }}
                className={`flex gap-3 ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {/* Nova Avatar Icon */}
                {msg.sender === 'nova' && (
                  <div className="flex items-center justify-center w-7 h-7 rounded-full bg-cyan-500/15 text-cyan-400 border border-sky-500/20 select-none text-[11px] font-bold">
                    N
                  </div>
                )}

                {/* Message Bubble */}
                <div 
                  className={`max-w-[75%] rounded-xl p-3 text-xs leading-relaxed border ${
                    msg.sender === 'user' 
                      ? 'bg-sky-500/10 border-sky-500/20 text-sky-100 rounded-tr-none' 
                      : 'bg-slate-900/50 border-sky-500/10 text-slate-200 rounded-tl-none'
                  } ${msg.isStreaming ? 'animate-pulse' : ''}`}
                >
                  <div className="flex items-center justify-between gap-6 mb-1 text-[9px] text-cyber-muted font-mono select-none">
                    <span>{msg.sender === 'user' ? 'OPERATOR' : 'NOVA CORESYSTEM'}</span>
                    <span>{msg.timestamp}</span>
                  </div>

                  <p className="whitespace-pre-line font-medium tracking-wide">
                    {msg.text}
                    {msg.isStreaming && (
                      <span className="inline-block w-1.5 h-3 ml-1 bg-cyan-400 animate-pulse" />
                    )}
                  </p>
                </div>

                {/* User Avatar Icon */}
                {msg.sender === 'user' && (
                  <div className="flex items-center justify-center w-7 h-7 rounded-full bg-sky-500/20 text-sky-300 border border-sky-500/30 select-none">
                    <User className="w-3.5 h-3.5" />
                  </div>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </div>

      {/* Input box */}
      <form onSubmit={handleSubmit} className="flex-shrink-0 mt-4 flex gap-2 border-t border-sky-500/10 pt-3">
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder="Type a command to Nova..."
          className="flex-1 bg-slate-950/45 border border-sky-500/15 rounded-lg px-3 py-2 text-xs text-cyber-text placeholder-cyber-muted focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400/20 transition-all font-sans font-medium"
        />
        <button
          type="submit"
          className="flex items-center justify-center w-8 h-8 rounded-lg bg-cyan-500/10 border border-sky-500/20 text-cyan-400 hover:bg-cyan-500/20 active:scale-95 transition-all"
        >
          <Send className="w-3.5 h-3.5" />
        </button>
      </form>
    </div>
  );
};

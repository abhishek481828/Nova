import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface NovaCoreProps {
  state: string;
}

export const NovaCore: React.FC<NovaCoreProps> = ({ state }) => {
  const normalizedState = (state || 'INACTIVE').toUpperCase();

  // Helper to determine core colors and styling
  const getColor = () => {
    switch (normalizedState) {
      case 'VOICE_IDLE':
      case 'WAKE_DETECTED':
        return { main: '#00f2fe', glow: 'rgba(0, 242, 254, 0.4)', text: 'cyan' };
      case 'LISTENING':
      case 'PUSH_TO_TALK':
        return { main: '#ef4444', glow: 'rgba(239, 68, 68, 0.5)', text: 'red' };
      case 'TRANSCRIBING':
        return { main: '#a855f7', glow: 'rgba(168, 85, 247, 0.4)', text: 'purple' };
      case 'EXECUTING':
        return { main: '#eab308', glow: 'rgba(234, 179, 8, 0.4)', text: 'yellow' };
      case 'SPEAKING':
        return { main: '#10b981', glow: 'rgba(16, 185, 129, 0.4)', text: 'green' };
      case 'ERROR':
        return { main: '#f97316', glow: 'rgba(249, 115, 22, 0.5)', text: 'orange' };
      case 'INACTIVE':
      default:
        return { main: '#475569', glow: 'rgba(71, 85, 105, 0.2)', text: 'slate' };
    }
  };

  const colors = getColor();

  // Core Pulse Animations based on state
  const getPulseTransition = (): any => {
    switch (normalizedState) {
      case 'LISTENING':
        return { duration: 0.6, repeat: Infinity, ease: "easeInOut" };
      case 'TRANSCRIBING':
        return { duration: 1.5, repeat: Infinity, ease: "easeInOut" };
      case 'EXECUTING':
        return { duration: 1.0, repeat: Infinity, ease: "linear" };
      case 'SPEAKING':
        return { duration: 0.8, repeat: Infinity, ease: "easeInOut" };
      case 'INACTIVE':
        return { duration: 5.0, repeat: Infinity, ease: "easeInOut" };
      default:
        return { duration: 3.0, repeat: Infinity, ease: "easeInOut" };
    }
  };

  return (
    <div className="relative flex flex-col items-center justify-center w-full h-full min-h-[320px]">
      {/* Background Ring Effects */}
      <AnimatePresence>
        {normalizedState === 'LISTENING' && (
          <>
            <motion.div
              initial={{ scale: 0.8, opacity: 0.8 }}
              animate={{ scale: 2.2, opacity: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 1.5, repeat: Infinity, ease: "easeOut" }}
              className="absolute w-44 h-44 rounded-full border border-red-500/30 pointer-events-none"
              style={{ boxShadow: '0 0 30px rgba(239, 68, 68, 0.2)' }}
            />
            <motion.div
              initial={{ scale: 0.8, opacity: 0.8 }}
              animate={{ scale: 1.6, opacity: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 1.5, delay: 0.5, repeat: Infinity, ease: "easeOut" }}
              className="absolute w-44 h-44 rounded-full border border-red-400/20 pointer-events-none"
            />
          </>
        )}
      </AnimatePresence>

      {/* Main Rotating Orbits (Thinking / Transcribing State) */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <motion.div
          animate={normalizedState === 'TRANSCRIBING' ? { rotate: 360 } : { rotate: 0 }}
          transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
          className="relative w-64 h-64 flex items-center justify-center"
        >
          {normalizedState === 'TRANSCRIBING' && (
            <>
              {/* Floating Orbiting Nodes */}
              <div className="absolute top-0 w-3 h-3 bg-purple-500 rounded-full shadow-[0_0_10px_#a855f7]" />
              <div className="absolute bottom-0 w-3 h-3 bg-blue-500 rounded-full shadow-[0_0_10px_#3b82f6]" />
              <div className="absolute left-0 w-3 h-3 bg-cyan-500 rounded-full shadow-[0_0_10px_#00f2fe]" />
            </>
          )}
        </motion.div>
      </div>

      {/* Outer Rotating Gear (Executing State) */}
      <AnimatePresence>
        {normalizedState === 'EXECUTING' && (
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1, rotate: 360 }}
            exit={{ opacity: 0, scale: 0.8 }}
            transition={{ rotate: { duration: 4, repeat: Infinity, ease: "linear" }, opacity: { duration: 0.3 } }}
            className="absolute w-52 h-52 border-2 border-dashed border-yellow-500/40 rounded-full pointer-events-none"
          />
        )}
      </AnimatePresence>

      {/* Bouncing Audio Waveforms (Speaking State) */}
      <div className="absolute flex gap-1 items-end h-16 bottom-6 pointer-events-none">
        {normalizedState === 'SPEAKING' && 
          Array.from({ length: 9 }).map((_, i) => (
            <motion.div
              key={i}
              animate={{ height: [8, Math.random() * 45 + 10, 8] }}
              transition={{
                duration: 0.4 + (i * 0.05),
                repeat: Infinity,
                ease: "easeInOut"
              }}
              className="w-1.5 bg-green-500 rounded-full shadow-[0_0_8px_#10b981]"
            />
          ))
        }
      </div>

      {/* Core Body Container */}
      <motion.div
        animate={{
          scale: normalizedState === 'LISTENING' ? [1, 1.15, 1] : [1, 1.05, 1],
          boxShadow: `0 0 50px ${colors.glow}`,
        }}
        transition={getPulseTransition()}
        className="relative z-10 w-36 h-36 rounded-full flex items-center justify-center glass-panel"
        style={{ borderColor: colors.main }}
      >
        {/* State Icon Indicator */}
        <AnimatePresence mode="wait">
          <motion.div
            key={normalizedState}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="text-4xl select-none"
          >
            {normalizedState === 'VOICE_IDLE' && '👂'}
            {normalizedState === 'WAKE_DETECTED' && '🔔'}
            {normalizedState === 'LISTENING' && '🎤'}
            {normalizedState === 'PUSH_TO_TALK' && '🎤'}
            {normalizedState === 'TRANSCRIBING' && '🧠'}
            {normalizedState === 'EXECUTING' && '⚡'}
            {normalizedState === 'SPEAKING' && '🔊'}
            {normalizedState === 'ERROR' && '⚠️'}
            {normalizedState === 'INACTIVE' && '💤'}
          </motion.div>
        </AnimatePresence>

        {/* Small Inner Orbit Indicator Ring */}
        <motion.div 
          animate={{ rotate: -360 }}
          transition={{ duration: 8, repeat: Infinity, ease: "linear" }}
          className="absolute inset-2 border border-sky-500/10 rounded-full"
        />
      </motion.div>

      {/* State Text Readout */}
      <div className="mt-8 text-center">
        <div className="text-xs uppercase tracking-[0.25em] text-cyber-muted">Nova System Core</div>
        <motion.div 
          key={normalizedState}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-lg font-semibold font-mono tracking-wider mt-1"
          style={{ color: colors.main }}
        >
          {normalizedState.replace('_', ' ')}
        </motion.div>
      </div>
    </div>
  );
};

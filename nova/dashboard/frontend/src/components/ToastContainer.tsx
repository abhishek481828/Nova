import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import type { ToastMessage } from '../types';
import { AlertTriangle, CheckCircle, Info, X } from 'lucide-react';

interface ToastContainerProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export const ToastContainer: React.FC<ToastContainerProps> = ({ toasts, onDismiss }) => {
  const getToastIcon = (type: string) => {
    switch (type) {
      case 'success':
        return <CheckCircle className="w-4 h-4 text-emerald-400" />;
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-amber-400" />;
      case 'error':
        return <AlertTriangle className="w-4 h-4 text-red-400" />;
      case 'info':
      default:
        return <Info className="w-4 h-4 text-sky-400 animate-pulse" />;
    }
  };

  const getBorderColor = (type: string) => {
    switch (type) {
      case 'success':
        return 'border-emerald-500/35 shadow-[0_0_15px_rgba(16,185,129,0.15)]';
      case 'warning':
        return 'border-amber-500/35 shadow-[0_0_15px_rgba(245,158,11,0.15)]';
      case 'error':
        return 'border-red-500/35 shadow-[0_0_15px_rgba(239,68,68,0.15)]';
      case 'info':
      default:
        return 'border-sky-500/35 shadow-[0_0_15px_rgba(56,189,248,0.15)]';
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 max-w-sm w-full pointer-events-none">
      <AnimatePresence>
        {toasts.map(toast => (
          <motion.div
            key={toast.id}
            layout
            initial={{ opacity: 0, x: 100, scale: 0.9 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: 80, scale: 0.95 }}
            transition={{ duration: 0.25, type: "spring", stiffness: 180, damping: 20 }}
            className={`pointer-events-auto flex gap-3 p-3.5 rounded-xl border glass-panel bg-slate-950/90 ${getBorderColor(toast.type)}`}
          >
            {/* Status Icon */}
            <div className="flex-shrink-0 mt-0.5">
              {getToastIcon(toast.type)}
            </div>

            {/* Content body */}
            <div className="flex-grow min-w-0">
              <div className="flex items-center justify-between gap-4">
                <span className="text-[10px] font-bold font-mono uppercase tracking-wider text-slate-300">
                  {toast.title}
                </span>
                <span className="text-[8px] font-mono text-slate-500 select-none">
                  {toast.timestamp}
                </span>
              </div>
              <p className="text-xs text-slate-200 mt-1 select-text font-medium leading-relaxed">
                {toast.message}
              </p>
            </div>

            {/* Dismiss Cross Icon */}
            <button 
              onClick={() => onDismiss(toast.id)}
              className="flex-shrink-0 self-start text-slate-500 hover:text-slate-200 transition-colors p-0.5 rounded hover:bg-white/5"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
};

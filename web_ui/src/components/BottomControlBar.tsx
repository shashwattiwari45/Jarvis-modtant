import React from 'react';
import { Mic, Shield, MessageSquare, Zap } from 'lucide-react';
import { JarvisState } from '../types';

interface BottomControlBarProps {
  state: JarvisState;
  automationMode: boolean;
  onToggleListen: () => void;
  onToggleAutomation: () => void;
  onToggleChat: () => void;
}

export const BottomControlBar: React.FC<BottomControlBarProps> = ({
  state,
  automationMode,
  onToggleListen,
  onToggleAutomation,
  onToggleChat,
}) => {
  return (
    <footer className="fixed bottom-8 left-0 right-0 z-30 flex flex-col items-center justify-center pointer-events-auto space-y-3">
      {/* State caption */}
      <div className="text-[11px] font-mono tracking-[0.25em] text-slate-400 uppercase flex items-center space-x-2">
        <span
          className={`w-2 h-2 rounded-full ${
            automationMode
              ? 'bg-red-500 animate-ping'
              : state === 'thinking'
              ? 'bg-purple-400 animate-bounce'
              : state === 'listening'
              ? 'bg-cyan-400 animate-ping'
              : state === 'speaking'
              ? 'bg-emerald-400 animate-pulse'
              : 'bg-cyan-500/60'
          }`}
        ></span>
        <span>
          {automationMode
            ? 'AUTOMATION OVERDRIVE ACTIVE - CIRCLE RED'
            : state === 'thinking'
            ? 'JARVIS THINKING (FAST ROTATION)'
            : state === 'listening'
            ? 'JARVIS LISTENING (SLOW ROTATION)'
            : state === 'speaking'
            ? 'JARVIS SPEAKING (VOICE MODULATED)'
            : 'JARVIS IDLE - AWAITING COMMAND'}
        </span>
      </div>

      {/* Floating Action Bar */}
      <div className="flex items-center space-x-6 px-6 py-2.5 rounded-full hud-glass border border-slate-800/80 shadow-2xl">
        {/* Voice Input Mic */}
        <button
          onClick={onToggleListen}
          className={`w-11 h-11 rounded-full flex items-center justify-center border transition-all duration-300 ${
            state === 'listening'
              ? 'border-cyan-400 bg-cyan-950/90 text-cyan-300 box-glow-cyan scale-110'
              : automationMode
              ? 'border-red-900/80 bg-red-950/40 text-red-400 hover:border-red-500'
              : 'border-cyan-500/40 bg-slate-900/80 text-cyan-400 hover:border-cyan-400 hover:bg-cyan-950/50 hover:scale-105'
          }`}
          title={state === 'listening' ? 'Stop Listening' : 'Start Voice Input'}
        >
          <Mic className={`w-5 h-5 ${state === 'listening' ? 'animate-pulse' : ''}`} />
        </button>

        {/* Center RED Automation Mode Toggle */}
        <button
          onClick={onToggleAutomation}
          className={`w-12 h-12 rounded-full flex items-center justify-center border transition-all duration-300 ${
            automationMode
              ? 'border-red-500 bg-red-600/30 text-red-100 box-glow-red scale-110 animate-pulse-glow'
              : 'border-slate-700 bg-slate-900/90 text-slate-300 hover:border-red-500 hover:text-red-400 hover:bg-red-950/40 hover:scale-105'
          }`}
          title="Toggle Automation Mode (Red Ring Shader)"
        >
          {automationMode ? (
            <Shield className="w-5 h-5 text-red-400 fill-red-500/40" />
          ) : (
            <Zap className="w-5 h-5 text-slate-300" />
          )}
        </button>

        {/* Chat Drawer Toggle */}
        <button
          onClick={onToggleChat}
          className={`w-11 h-11 rounded-full flex items-center justify-center border transition-all duration-300 ${
            automationMode
              ? 'border-red-900/80 bg-red-950/40 text-red-400 hover:border-red-500'
              : 'border-cyan-500/40 bg-slate-900/80 text-cyan-400 hover:border-cyan-400 hover:bg-cyan-950/50 hover:scale-105'
          }`}
          title="Toggle Command Chat Console"
        >
          <MessageSquare className="w-5 h-5" />
        </button>
      </div>
    </footer>
  );
};

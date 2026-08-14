import React from 'react';
import { Mic, MessageSquare, Zap, ShieldAlert, Volume2, VolumeX, Cpu } from 'lucide-react';
import { JarvisState } from '../types';

interface LeftControlDockProps {
  state: JarvisState;
  automationMode: boolean;
  onToggleListen: () => void;
  onToggleChat: () => void;
  onToggleAutomation: () => void;
  audioMuted: boolean;
  onToggleMute: () => void;
  isChatOpen: boolean;
}

export const LeftControlDock: React.FC<LeftControlDockProps> = ({
  state,
  automationMode,
  onToggleListen,
  onToggleChat,
  onToggleAutomation,
  audioMuted,
  onToggleMute,
  isChatOpen,
}) => {
  return (
    <aside className="fixed left-6 top-1/2 -translate-y-1/2 z-30 flex flex-col items-center space-y-4 pointer-events-auto">
      {/* Mic Trigger */}
      <button
        onClick={onToggleListen}
        className={`w-12 h-12 flex items-center justify-center rounded-sm border transition-all duration-300 ${
          state === 'listening'
            ? 'border-cyan-400 bg-cyan-950/80 text-cyan-300 box-glow-cyan scale-105'
            : automationMode
            ? 'border-red-900/60 bg-red-950/30 text-red-400 hover:border-red-500 hover:bg-red-900/40'
            : 'border-slate-800 bg-slate-950/60 text-slate-400 hover:border-cyan-500/70 hover:text-cyan-400 hover:bg-cyan-950/30'
        }`}
        title={state === 'listening' ? 'Stop Listening' : 'Start Voice Input'}
      >
        <Mic className={`w-5 h-5 ${state === 'listening' ? 'animate-pulse text-cyan-300' : ''}`} />
      </button>

      {/* Chat Command Input Toggle */}
      <button
        onClick={onToggleChat}
        className={`w-12 h-12 flex items-center justify-center rounded-sm border transition-all duration-300 ${
          isChatOpen
            ? automationMode
              ? 'border-red-500 bg-red-950/80 text-red-300 box-glow-red'
              : 'border-cyan-400 bg-cyan-950/80 text-cyan-300 box-glow-cyan'
            : 'border-slate-800 bg-slate-950/60 text-slate-400 hover:border-cyan-500/70 hover:text-cyan-400 hover:bg-cyan-950/30'
        }`}
        title="Open JARVIS AI Chat Command Center"
      >
        <MessageSquare className="w-5 h-5" />
      </button>

      {/* Automation Mode RED Overdrive Trigger */}
      <button
        onClick={onToggleAutomation}
        className={`w-12 h-12 flex items-center justify-center rounded-sm border transition-all duration-300 ${
          automationMode
            ? 'border-red-500 bg-red-900/70 text-red-200 box-glow-red scale-105 animate-pulse-glow'
            : 'border-slate-800 bg-slate-950/60 text-slate-400 hover:border-red-500 hover:text-red-400 hover:bg-red-950/30'
        }`}
        title={automationMode ? 'Deactivate Red Automation' : 'Activate Red Automation Overdrive'}
      >
        {automationMode ? (
          <ShieldAlert className="w-5 h-5 text-red-400" />
        ) : (
          <Zap className="w-5 h-5" />
        )}
      </button>

      {/* Audio SFX Mute Toggle */}
      <button
        onClick={onToggleMute}
        className="w-12 h-12 flex items-center justify-center rounded-sm border border-slate-800 bg-slate-950/60 text-slate-400 hover:border-slate-600 hover:text-slate-200 transition-all duration-200"
        title={audioMuted ? 'Unmute Audio Feedback' : 'Mute Audio Feedback'}
      >
        {audioMuted ? <VolumeX className="w-5 h-5 text-slate-500" /> : <Volume2 className="w-5 h-5 text-slate-300" />}
      </button>

      {/* Bottom HUD telemetry circles matching reference screenshot */}
      <div className="pt-4 flex flex-col items-center space-y-2 opacity-60">
        <div className={`w-2.5 h-2.5 rounded-full border ${automationMode ? 'border-red-500 bg-red-500/40' : 'border-cyan-400 bg-cyan-400/40'}`}></div>
        <div className="w-2 h-2 rounded-full border border-slate-600"></div>
        <div className="w-1.5 h-1.5 rounded-full border border-slate-700"></div>
      </div>
    </aside>
  );
};

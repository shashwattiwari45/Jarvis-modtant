import React, { useState, useEffect } from 'react';
import { JarvisState } from '../types';
import { Shield, ShieldAlert, Activity, Minus, Square, X } from 'lucide-react';

interface TopBarProps {
  state: JarvisState;
  automationMode: boolean;
  onToggleAutomation: () => void;
  onOpenDiagnostics: () => void;
  audioMuted: boolean;
  onToggleMute: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  state,
  automationMode,
  onToggleAutomation,
  onOpenDiagnostics,
}) => {
  const [timeStr, setTimeStr] = useState<string>('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTimeStr(now.toLocaleTimeString('en-US', { hour12: false }) + ' UTC');
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const getStateBadge = () => {
    if (automationMode) {
      return {
        label: '● AUTOMATION OVERDRIVE',
        colorClass: 'text-red-500 border-red-500/60 bg-red-950/40 glow-red animate-pulse-glow',
      };
    }

    switch (state) {
      case 'listening':
        return {
          label: '● LISTENING...',
          colorClass: 'text-cyan-400 border-cyan-500/60 bg-cyan-950/40 glow-cyan',
        };
      case 'thinking':
        return {
          label: '⚡ PROCESSING QUERY',
          colorClass: 'text-purple-400 border-purple-500/60 bg-purple-950/40 glow-purple animate-pulse',
        };
      case 'speaking':
        return {
          label: '🔊 VOICE TRANSMITTING',
          colorClass: 'text-emerald-400 border-emerald-500/60 bg-emerald-950/40',
        };
      default:
        return {
          label: '● ONLINE',
          colorClass: 'text-cyan-400 border-cyan-500/30 bg-cyan-950/20 glow-cyan',
        };
    }
  };

  const badge = getStateBadge();

  return (
    <header className="fixed top-0 left-0 right-0 z-30 flex items-center justify-between px-6 py-4 pointer-events-auto">
      {/* Brand Title */}
      <div className="flex items-center space-x-3">
        <div className="flex flex-col">
          <div className="flex items-center space-x-2">
            <h1 className={`text-xl font-light tracking-[0.4em] ${automationMode ? 'text-red-500 glow-red' : 'text-cyan-400 glow-cyan'}`}>
              J A R V I S
            </h1>
            <span className="text-[10px] font-mono tracking-widest text-slate-500 uppercase">
              v4.2 HUD
            </span>
          </div>
          <span className="text-[10px] font-mono tracking-widest text-slate-400 flex items-center space-x-2">
            <span className={`inline-block w-1.5 h-1.5 rounded-full ${automationMode ? 'bg-red-500 animate-ping' : 'bg-cyan-400 animate-pulse'}`}></span>
            <span>SYSTEM DIRECTORY: ACTIVE</span>
          </span>
        </div>
      </div>

      {/* Center Status Pill */}
      <div className="hidden md:flex items-center space-x-4">
        <div
          className={`px-3 py-1 text-xs font-mono tracking-wider border rounded-sm transition-all duration-300 ${badge.colorClass}`}
        >
          {badge.label}
        </div>

        {/* Diagnostics Trigger Button */}
        <button
          onClick={onOpenDiagnostics}
          className={`flex items-center space-x-1.5 px-3 py-1 text-xs font-mono border rounded-sm transition-all duration-200 ${
            automationMode
              ? 'border-red-500/40 text-red-400 hover:bg-red-500/20'
              : 'border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/20'
          }`}
        >
          <Activity className="w-3.5 h-3.5" />
          <span>DIAGNOSTICS</span>
        </button>
      </div>

      {/* Right Controls */}
      <div className="flex items-center space-x-4">
        {/* Automation Mode Toggle Button */}
        <button
          onClick={onToggleAutomation}
          className={`flex items-center space-x-2 px-3.5 py-1.5 text-xs font-mono border rounded-sm transition-all duration-300 ${
            automationMode
              ? 'border-red-500 bg-red-900/60 text-red-200 box-glow-red font-semibold'
              : 'border-slate-700 bg-slate-900/60 text-slate-300 hover:border-red-500/70 hover:text-red-400'
          }`}
          title="Toggle Overdrive Automation Mode"
        >
          {automationMode ? (
            <ShieldAlert className="w-4 h-4 text-red-400 animate-pulse" />
          ) : (
            <Shield className="w-4 h-4 text-slate-400" />
          )}
          <span className="tracking-wider">
            {automationMode ? 'AUTOMATION: ACTIVE' : 'AUTOMATION: STANDBY'}
          </span>
        </button>

        {/* Real-time Clock */}
        <div className="hidden lg:block text-xs font-mono tracking-widest text-slate-400 px-2 py-1 bg-slate-950/40 border border-slate-800/80 rounded-sm">
          {timeStr}
        </div>

        {/* Window controls decoration matching screenshot */}
        <div className="flex items-center space-x-2 text-slate-500 text-xs pl-2">
          <Minus className="w-3.5 h-3.5 hover:text-cyan-400 cursor-pointer" />
          <Square className="w-3 h-3 hover:text-cyan-400 cursor-pointer" />
          <X className="w-3.5 h-3.5 hover:text-red-400 cursor-pointer" />
        </div>
      </div>
    </header>
  );
};

import React, { useState, useEffect } from 'react';
import { JarvisState } from '../types';
import { Activity, Cpu, Thermometer, Gauge, Zap, X } from 'lucide-react';

interface SystemDiagnosticsModalProps {
  isOpen: boolean;
  onClose: () => void;
  state: JarvisState;
  automationMode: boolean;
  audioLevel: number;
  onTestThinking: () => void;
}

export const SystemDiagnosticsModal: React.FC<SystemDiagnosticsModalProps> = ({
  isOpen,
  onClose,
  state,
  automationMode,
  audioLevel,
  onTestThinking,
}) => {
  const [fps, setFps] = useState(60);
  const [cpu, setCpu] = useState(14);
  const [temp, setTemp] = useState(36.4);

  useEffect(() => {
    if (!isOpen) return;

    const interval = setInterval(() => {
      // Simulate slight realistic HUD metric jitter
      setFps(Math.floor(58 + Math.random() * 3));
      setCpu(Math.floor(12 + Math.random() * (state === 'thinking' ? 45 : 8)));
      setTemp(Number((35.8 + (state === 'thinking' ? 4.2 : 0) + Math.random() * 0.8).toFixed(1)));
    }, 1000);

    return () => clearInterval(interval);
  }, [isOpen, state]);

  if (!isOpen) return null;

  const getSpeedLabel = () => {
    if (state === 'thinking') return 'FAST (4.8x - 6.0x)';
    if (state === 'listening') return 'SLOW (0.5x)';
    if (state === 'speaking') return 'DYNAMIC VOICE MODULATED';
    return 'STANDARD IDLE (1.2x)';
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-md pointer-events-auto">
      <div
        className={`w-full max-w-lg rounded-md border shadow-2xl overflow-hidden font-mono text-xs ${
          automationMode
            ? 'hud-glass-red border-red-500 box-glow-red'
            : 'hud-glass border-cyan-500 box-glow-cyan'
        }`}
      >
        {/* Header */}
        <div
          className={`flex items-center justify-between px-5 py-3 border-b ${
            automationMode ? 'bg-red-950/70 border-red-800' : 'bg-slate-950/70 border-slate-800'
          }`}
        >
          <div className="flex items-center space-x-2">
            <Activity className={`w-4 h-4 ${automationMode ? 'text-red-400' : 'text-cyan-400'}`} />
            <h3 className="font-semibold text-slate-200 tracking-wider">
              JARVIS TELEMETRY & SHADER DIAGNOSTICS
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-100 p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Diagnostic Metrics Grid */}
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            {/* FPS */}
            <div className="p-3 rounded bg-slate-950/50 border border-slate-800 flex items-center space-x-3">
              <Gauge className={`w-5 h-5 ${automationMode ? 'text-red-400' : 'text-cyan-400'}`} />
              <div>
                <div className="text-[10px] text-slate-400">SHADER RENDER RATE</div>
                <div className="text-sm font-bold text-slate-100">{fps} FPS</div>
              </div>
            </div>

            {/* CPU */}
            <div className="p-3 rounded bg-slate-950/50 border border-slate-800 flex items-center space-x-3">
              <Cpu className={`w-5 h-5 ${automationMode ? 'text-red-400' : 'text-purple-400'}`} />
              <div>
                <div className="text-[10px] text-slate-400">NEURAL LOAD</div>
                <div className="text-sm font-bold text-slate-100">{cpu}%</div>
              </div>
            </div>

            {/* Thermals */}
            <div className="p-3 rounded bg-slate-950/50 border border-slate-800 flex items-center space-x-3">
              <Thermometer className={`w-5 h-5 ${automationMode ? 'text-red-400' : 'text-amber-400'}`} />
              <div>
                <div className="text-[10px] text-slate-400">CORE TEMP</div>
                <div className="text-sm font-bold text-slate-100">{temp}°C</div>
              </div>
            </div>

            {/* Circle Color */}
            <div className="p-3 rounded bg-slate-950/50 border border-slate-800 flex items-center space-x-3">
              <Zap className={`w-5 h-5 ${automationMode ? 'text-red-500' : 'text-cyan-400'}`} />
              <div>
                <div className="text-[10px] text-slate-400">RING COLOR MODE</div>
                <div className={`text-xs font-bold ${automationMode ? 'text-red-400' : 'text-cyan-300'}`}>
                  {automationMode ? 'CRIMSON RED' : 'CYAN BLUE'}
                </div>
              </div>
            </div>
          </div>

          {/* Shader Rotation Speed Status */}
          <div className="p-3 rounded bg-slate-950/60 border border-slate-800 space-y-1.5">
            <div className="flex justify-between text-[11px]">
              <span className="text-slate-400">RING ROTATION SPEED STATE:</span>
              <span className={`font-bold ${state === 'thinking' ? 'text-purple-400' : state === 'listening' ? 'text-cyan-400' : 'text-slate-200'}`}>
                {getSpeedLabel()}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 leading-relaxed">
              - Fast rotation triggered during THINKING phase.<br />
              - Slow rotation triggered during LISTENING phase.<br />
              - Dynamic modulation triggered during SPEAKING phase.<br />
              - Red coloration triggered when AUTOMATION MODE is active.
            </p>
          </div>

          {/* Audio Input Meter */}
          <div className="p-3 rounded bg-slate-950/60 border border-slate-800 space-y-1.5">
            <div className="flex justify-between text-[11px]">
              <span className="text-slate-400">AUDIO INPUT LEVEL:</span>
              <span className="font-bold text-cyan-300">{Math.round(audioLevel * 100)}%</span>
            </div>
            <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden border border-slate-800">
              <div
                className={`h-full transition-all duration-100 ${automationMode ? 'bg-red-500' : 'bg-cyan-400'}`}
                style={{ width: `${Math.max(4, audioLevel * 100)}%` }}
              ></div>
            </div>
          </div>

          {/* Test thinking speed trigger */}
          <button
            onClick={onTestThinking}
            className={`w-full py-2.5 rounded text-xs font-bold tracking-wider border transition-colors ${
              automationMode
                ? 'border-red-600 bg-red-950/80 text-red-200 hover:bg-red-900'
                : 'border-purple-600 bg-purple-950/80 text-purple-200 hover:bg-purple-900'
            }`}
          >
            ⚡ TEST THINKING FAST ROTATION
          </button>
        </div>
      </div>
    </div>
  );
};

import React, { useState, useEffect } from 'react';
import { AutomationTask } from '../types';
import { ShieldAlert, Play, CheckCircle2, AlertTriangle, Cpu, Terminal, RefreshCw, X } from 'lucide-react';

interface AutomationPanelProps {
  isOpen: boolean;
  onClose: () => void;
  tasks: AutomationTask[];
  onTriggerTask: (taskName: string) => void;
}

export const AutomationPanel: React.FC<AutomationPanelProps> = ({
  isOpen,
  onClose,
  tasks,
  onTriggerTask,
}) => {
  const [customMacro, setCustomMacro] = useState('');

  if (!isOpen) return null;

  const handleRunCustomMacro = (e: React.FormEvent) => {
    e.preventDefault();
    if (!customMacro.trim()) return;
    onTriggerTask(customMacro.trim());
    setCustomMacro('');
  };

  return (
    <div className="fixed left-6 top-24 bottom-24 w-80 z-40 flex flex-col pointer-events-auto">
      <div className="flex-1 flex flex-col rounded-md hud-glass-red border border-red-500/60 box-glow-red overflow-hidden font-mono">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-red-950/70 border-b border-red-800/80">
          <div className="flex items-center space-x-2">
            <ShieldAlert className="w-4 h-4 text-red-400 animate-pulse" />
            <span className="text-xs font-bold text-red-200 tracking-wider">
              AUTOMATION OVERDRIVE
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-red-400 hover:text-red-200 p-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Subheader status */}
        <div className="p-3 bg-red-950/40 border-b border-red-900/60 text-[10px] text-red-300/80 leading-relaxed">
          <span>● CORE SHADER: RED (AUTOMATION MODE)</span>
          <br />
          <span>Subroutines executing in background threads with real-time feedback.</span>
        </div>

        {/* Active Automated Tasks List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-3">
          {tasks.map((task) => (
            <div
              key={task.id}
              className="p-3 rounded-sm bg-red-950/40 border border-red-900/60 text-xs space-y-2"
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-red-200 flex items-center space-x-1.5">
                  {task.status === 'running' && <RefreshCw className="w-3 h-3 text-red-400 animate-spin" />}
                  {task.status === 'completed' && <CheckCircle2 className="w-3 h-3 text-emerald-400" />}
                  {task.status === 'error' && <AlertTriangle className="w-3 h-3 text-amber-400" />}
                  <span>{task.name}</span>
                </span>
                <span className="text-[10px] text-red-400 font-bold">{task.progress}%</span>
              </div>

              {/* Progress Bar */}
              <div className="w-full bg-red-950/80 h-1.5 rounded-full overflow-hidden border border-red-900/60">
                <div
                  className="bg-red-500 h-full transition-all duration-300"
                  style={{ width: `${task.progress}%` }}
                ></div>
              </div>

              {/* Logs */}
              <div className="p-2 rounded bg-black/60 text-[10px] text-red-300/80 space-y-0.5 max-h-20 overflow-y-auto automation-scrollbar">
                {task.logs.slice(-3).map((log, i) => (
                  <div key={i} className="leading-tight truncate">
                    &gt; {log}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Trigger Custom Automation */}
        <form onSubmit={handleRunCustomMacro} className="p-3 border-t border-red-900/80 flex items-center space-x-2">
          <input
            type="text"
            value={customMacro}
            onChange={(e) => setCustomMacro(e.target.value)}
            placeholder="Run macro routine..."
            className="flex-1 bg-black/60 border border-red-900/80 rounded-sm px-2.5 py-1.5 text-xs text-red-100 placeholder-red-700 focus:outline-none focus:border-red-500"
          />
          <button
            type="submit"
            disabled={!customMacro.trim()}
            className="p-1.5 rounded-sm border border-red-600 bg-red-900/80 text-red-100 hover:bg-red-800 disabled:opacity-40"
          >
            <Play className="w-3.5 h-3.5" />
          </button>
        </form>
      </div>
    </div>
  );
};

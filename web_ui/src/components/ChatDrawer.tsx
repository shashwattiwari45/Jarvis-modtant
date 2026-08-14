import React, { useState, useRef, useEffect } from 'react';
import { ChatMessage, JarvisState } from '../types';
import { Send, Mic, Volume2, VolumeX, X, Sparkles, Terminal, ShieldAlert } from 'lucide-react';
import { jarvisAudio } from '../utils/audioSynthesizer';

interface ChatDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  messages: ChatMessage[];
  onSendMessage: (text: string) => void;
  state: JarvisState;
  automationMode: boolean;
  onToggleListen: () => void;
  autoTTS: boolean;
  onToggleAutoTTS: () => void;
}

export const ChatDrawer: React.FC<ChatDrawerProps> = ({
  isOpen,
  onClose,
  messages,
  onSendMessage,
  state,
  automationMode,
  onToggleListen,
  autoTTS,
  onToggleAutoTTS,
}) => {
  const [inputText, setInputText] = useState('');
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const suggestedPrompts = [
    'Run full system diagnostic scan',
    'Activate red automation mode',
    'What is your current neural status?',
    'Simulate fast thinking routine',
    'Execute sub-routine 847',
  ];

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || state === 'thinking') return;
    onSendMessage(inputText.trim());
    setInputText('');
  };

  const handlePromptClick = (prompt: string) => {
    if (state === 'thinking') return;
    onSendMessage(prompt);
  };

  return (
    <aside className="fixed right-6 top-20 bottom-24 w-full max-w-md z-40 flex flex-col pointer-events-auto">
      <div
        className={`flex-1 flex flex-col rounded-md border shadow-2xl overflow-hidden transition-all duration-300 ${
          automationMode
            ? 'hud-glass-red border-red-500/50 box-glow-red'
            : 'hud-glass border-cyan-500/40 box-glow-cyan'
        }`}
      >
        {/* Header */}
        <div
          className={`flex items-center justify-between px-4 py-3 border-b ${
            automationMode ? 'border-red-900/60 bg-red-950/40' : 'border-slate-800 bg-slate-950/60'
          }`}
        >
          <div className="flex items-center space-x-2">
            <Terminal className={`w-4 h-4 ${automationMode ? 'text-red-400' : 'text-cyan-400'}`} />
            <h2 className="text-xs font-mono tracking-widest uppercase font-semibold text-slate-200">
              JARVIS AI COMMAND CONSOLE
            </h2>
          </div>

          <div className="flex items-center space-x-2">
            {/* Auto Voice Output Toggle */}
            <button
              onClick={onToggleAutoTTS}
              className={`p-1.5 rounded-sm border transition-colors ${
                autoTTS
                  ? automationMode
                    ? 'border-red-500 bg-red-900/40 text-red-300'
                    : 'border-cyan-500 bg-cyan-900/40 text-cyan-300'
                  : 'border-slate-800 text-slate-500 hover:text-slate-300'
              }`}
              title={autoTTS ? 'Auto Speech Synthesis ON' : 'Auto Speech Synthesis OFF'}
            >
              {autoTTS ? <Volume2 className="w-3.5 h-3.5" /> : <VolumeX className="w-3.5 h-3.5" />}
            </button>

            {/* Close drawer */}
            <button
              onClick={onClose}
              className="p-1.5 rounded-sm border border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Message History Stream */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 font-mono text-xs">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-6 text-slate-400 space-y-2">
              <Sparkles className={`w-8 h-8 ${automationMode ? 'text-red-500' : 'text-cyan-400'}`} />
              <p className="text-xs tracking-wider">AWAITING VOICE OR TEXT COMMANDS</p>
              <p className="text-[10px] text-slate-400">Speak or type to prompt JARVIS AI neural core.</p>
            </div>
          ) : (
            messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${
                  msg.role === 'user' ? 'items-end' : 'items-start'
                }`}
              >
                <div className="flex items-center space-x-2 text-[10px] text-slate-400 mb-1">
                  <span>{msg.role === 'user' ? 'SIR' : 'JARVIS AI'}</span>
                  <span>•</span>
                  <span>{msg.timestamp}</span>
                </div>
                <div
                  className={`p-3 rounded-sm max-w-[85%] leading-relaxed whitespace-pre-wrap ${
                    msg.role === 'user'
                      ? 'bg-slate-800/80 border border-slate-700 text-slate-100'
                      : automationMode
                      ? 'bg-red-950/60 border border-red-800/80 text-red-100'
                      : 'bg-cyan-950/60 border border-cyan-800/80 text-cyan-100'
                  }`}
                >
                  {msg.content}
                </div>
              </div>
            ))
          )}

          {/* Thinking Indicator */}
          {state === 'thinking' && (
            <div className="flex items-center space-x-2 text-xs font-mono text-slate-400 animate-pulse pt-2">
              <span className={`w-2 h-2 rounded-full ${automationMode ? 'bg-red-500' : 'bg-purple-400'}`}></span>
              <span>Processing neural query... (Ring rotating fast)</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Quick Suggestion Chips */}
        <div className="px-3 py-2 border-t border-slate-800/80 flex items-center space-x-1.5 overflow-x-auto no-scrollbar">
          {suggestedPrompts.map((prompt, i) => (
            <button
              key={i}
              onClick={() => handlePromptClick(prompt)}
              disabled={state === 'thinking'}
              className="px-2.5 py-1 text-[10px] font-mono whitespace-nowrap rounded-sm border border-slate-800 bg-slate-900/60 text-slate-300 hover:border-cyan-500/50 hover:text-cyan-300 transition-colors disabled:opacity-50"
            >
              {prompt}
            </button>
          ))}
        </div>

        {/* Input Form */}
        <form onSubmit={handleSubmit} className="p-3 border-t border-slate-800/80 flex items-center space-x-2">
          {/* Voice Mic Input */}
          <button
            type="button"
            onClick={onToggleListen}
            className={`p-2.5 rounded-sm border transition-colors ${
              state === 'listening'
                ? 'border-cyan-400 bg-cyan-900/60 text-cyan-200 animate-pulse'
                : 'border-slate-800 bg-slate-900/60 text-slate-400 hover:text-cyan-400'
            }`}
            title="Speak Command"
          >
            <Mic className="w-4 h-4" />
          </button>

          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder={state === 'listening' ? 'Listening...' : 'Type command for JARVIS...'}
            disabled={state === 'thinking'}
            className="flex-1 bg-slate-950/80 border border-slate-800 rounded-sm px-3 py-2 text-xs font-mono text-slate-100 placeholder-slate-400 focus:outline-none focus:border-cyan-500/70"
          />

          <button
            type="submit"
            disabled={!inputText.trim() || state === 'thinking'}
            className={`p-2.5 rounded-sm border transition-colors ${
              automationMode
                ? 'border-red-600 bg-red-900/80 text-red-100 hover:bg-red-800 disabled:opacity-40'
                : 'border-cyan-600 bg-cyan-900/80 text-cyan-100 hover:bg-cyan-800 disabled:opacity-40'
            }`}
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </aside>
  );
};

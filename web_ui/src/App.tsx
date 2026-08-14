import React, { useState, useEffect, useRef, useCallback } from 'react';
import { JarvisState, ChatMessage, AutomationTask } from './types';
import { JarvisCanvas } from './components/JarvisCanvas';
import { TopBar } from './components/TopBar';
import { LeftControlDock } from './components/LeftControlDock';
import { BottomControlBar } from './components/BottomControlBar';
import { ChatDrawer } from './components/ChatDrawer';
import { AutomationPanel } from './components/AutomationPanel';
import { SystemDiagnosticsModal } from './components/SystemDiagnosticsModal';
import { jarvisAudio } from './utils/audioSynthesizer';

const CHAT_STORAGE_KEY = 'jarvis_web_chat_v2';
const SESSION_STORAGE_KEY = 'jarvis_cloud_session_v2';

function loadStoredMessages(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (Array.isArray(parsed) && parsed.length) return parsed;
  } catch {}
  return [{
    id: 'init-1',
    role: 'assistant',
    content: 'Good day, sir. All core matrices online. Persistent cloud memory is active.',
    timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
  }];
}

function loadStoredSession(): string | null {
  try { return localStorage.getItem(SESSION_STORAGE_KEY); } catch { return null; }
}

export default function App() {
  const [state, setState] = useState<JarvisState>('idle');
  const [automationMode, setAutomationMode] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [audioMuted, setAudioMuted] = useState(false);
  const [cloudSessionId, setCloudSessionId] = useState<string | null>(loadStoredSession);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isAutomationOpen, setIsAutomationOpen] = useState(false);
  const [isDiagnosticsOpen, setIsDiagnosticsOpen] = useState(false);
  const [autoTTS, setAutoTTS] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>(loadStoredMessages);

  useEffect(() => {
    try { localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages.slice(-100))); } catch {}
  }, [messages]);

  useEffect(() => {
    try {
      if (cloudSessionId) localStorage.setItem(SESSION_STORAGE_KEY, cloudSessionId);
    } catch {}
  }, [cloudSessionId]);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    const sendHeartbeat = async () => { try { await fetch('/api/device/heartbeat', { method: 'POST' }); } catch {} };
    sendHeartbeat();
    timer = setInterval(sendHeartbeat, 60_000);
    return () => { if (timer) clearInterval(timer); };
  }, []);

  const [tasks, setTasks] = useState<AutomationTask[]>([
    { id: 'task-1', name: 'Cyber Security Sweep', category: 'Security', status: 'idle', progress: 0, logs: ['Ready to execute.'] },
    { id: 'task-2', name: 'Neural Node Optimizer', category: 'AI Engine', status: 'idle', progress: 0, logs: ['Awaiting overdrive signal.'] },
    { id: 'task-3', name: 'System Diagnostic Sweep', category: 'Maintenance', status: 'idle', progress: 0, logs: ['Standby mode.'] },
  ]);

  const recognitionRef = useRef<any>(null);
  const stopMicRef = useRef<(() => void) | null>(null);

  const handleToggleMute = () => {
    const nextMute = !audioMuted;
    setAudioMuted(nextMute);
    jarvisAudio.setMute(nextMute);
  };

  const triggerAutomatedTasks = useCallback(() => {
    setTasks((prev) => prev.map((t) => ({ ...t, status: 'running', progress: 10, logs: [...t.logs, 'Initializing automated thread...'] })));
    let progress = 10;
    const interval = setInterval(() => {
      progress += 15;
      if (progress >= 100) {
        clearInterval(interval);
        setTasks((prev) => prev.map((t) => ({ ...t, status: 'completed', progress: 100, logs: [...t.logs, 'Macro execution complete. 100% verified.'] })));
      } else {
        setTasks((prev) => prev.map((t) => ({ ...t, progress, logs: [...t.logs, `Progressing: ${progress}%...`] })));
      }
    }, 800);
  }, []);

  const handleToggleAutomation = () => {
    const nextMode = !automationMode;
    setAutomationMode(nextMode);
    jarvisAudio.playStateSound(nextMode ? 'automation_on' : 'automation_off');
    if (nextMode) {
      setIsAutomationOpen(true);
      triggerAutomatedTasks();
      setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'system', content: '[AUTOMATION OVERDRIVE ACTIVATED] Core ring converted to Crimson Red.', timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }) }]);
    } else {
      setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'system', content: '[AUTOMATION STANDBY] Core ring reverted to Cyan Blue.', timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }) }]);
    }
  };

  const handleTriggerCustomTask = (taskName: string) => {
    const newTask: AutomationTask = { id: Date.now().toString(), name: taskName, category: 'User Routine', status: 'running', progress: 20, logs: [`Initiated custom macro: "${taskName}"`] };
    setTasks((prev) => [newTask, ...prev]);
    let progress = 20;
    const interval = setInterval(() => {
      progress += 25;
      if (progress >= 100) {
        clearInterval(interval);
        setTasks((prev) => prev.map((t) => t.id === newTask.id ? { ...t, status: 'completed', progress: 100, logs: [...t.logs, 'Macro finished successfully.'] } : t));
      } else {
        setTasks((prev) => prev.map((t) => t.id === newTask.id ? { ...t, progress, logs: [...t.logs, `Executing stage ${progress}%`] } : t));
      }
    }, 600);
  };

  const handleSendMessage = async (text: string) => {
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content: text, timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }) };
    const historyForRequest = messages.slice(-12).map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, userMsg]);
    setState('thinking');
    jarvisAudio.playStateSound('thinking');

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, automationMode, session_id: cloudSessionId, history: historyForRequest }),
      });
      const data = await response.json();
      if (data.session_id) setCloudSessionId(data.session_id);
      const replyText = data.reply || 'Request processed successfully, sir.';
      setMessages((prev) => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content: replyText, timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }) }]);

      if (autoTTS) {
        jarvisAudio.speak(replyText, () => setState('speaking'), () => { setState('idle'); setAudioLevel(0); }, (level) => setAudioLevel(level));
      } else {
        setTimeout(() => setState('idle'), 800);
      }
    } catch (err) {
      console.error('Error contacting JARVIS Cloud:', err);
      setMessages((prev) => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content: 'The cloud link is temporarily unavailable. Local interface protocols remain active.', timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }) }]);
      setState('idle');
    }
  };

  const handleToggleListen = async () => {
    if (state === 'listening') {
      stopMicRef.current?.();
      stopMicRef.current = null;
      try { recognitionRef.current?.stop(); } catch {}
      setState('idle');
      setAudioLevel(0);
      return;
    }

    jarvisAudio.stopSpeaking();
    setState('listening');
    jarvisAudio.playStateSound('listening');
    stopMicRef.current = await jarvisAudio.startMicAnalyzer((level) => setAudioLevel(level));

    const SpeechRecognitionClass = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognitionClass) {
      try {
        const recognition = new SpeechRecognitionClass();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';
        recognition.onresult = (event: any) => {
          const transcript = event.results[0][0].transcript;
          if (transcript) { stopMicRef.current?.(); handleSendMessage(transcript); }
        };
        recognition.onerror = () => { stopMicRef.current?.(); setState('idle'); setAudioLevel(0); };
        recognition.onend = () => stopMicRef.current?.();
        recognition.start();
        recognitionRef.current = recognition;
      } catch (e) { console.warn('SpeechRecognition initialization error:', e); }
    } else {
      setTimeout(() => { stopMicRef.current?.(); handleSendMessage('Run quick system diagnostic scan'); }, 3500);
    }
  };

  const handleTestThinking = () => {
    setIsDiagnosticsOpen(false);
    handleSendMessage('Simulate fast thinking routine');
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-black select-none">
      <JarvisCanvas state={state} automationMode={automationMode} audioLevel={audioLevel} onCanvasClick={() => { if (!isChatOpen && !isAutomationOpen) setIsChatOpen(true); }} />
      <div className="fixed inset-0 scanlines opacity-40 pointer-events-none z-10" />
      <TopBar state={state} automationMode={automationMode} onToggleAutomation={handleToggleAutomation} onOpenDiagnostics={() => setIsDiagnosticsOpen(true)} audioMuted={audioMuted} onToggleMute={handleToggleMute} />
      <LeftControlDock state={state} automationMode={automationMode} onToggleListen={handleToggleListen} onToggleChat={() => setIsChatOpen(!isChatOpen)} onToggleAutomation={handleToggleAutomation} audioMuted={audioMuted} onToggleMute={handleToggleMute} isChatOpen={isChatOpen} />
      <BottomControlBar state={state} automationMode={automationMode} onToggleListen={handleToggleListen} onToggleAutomation={handleToggleAutomation} onToggleChat={() => setIsChatOpen(!isChatOpen)} />
      <ChatDrawer isOpen={isChatOpen} onClose={() => setIsChatOpen(false)} messages={messages} onSendMessage={handleSendMessage} state={state} automationMode={automationMode} onToggleListen={handleToggleListen} autoTTS={autoTTS} onToggleAutoTTS={() => setAutoTTS(!autoTTS)} />
      <AutomationPanel isOpen={isAutomationOpen} onClose={() => setIsAutomationOpen(false)} tasks={tasks} onTriggerTask={handleTriggerCustomTask} />
      <SystemDiagnosticsModal isOpen={isDiagnosticsOpen} onClose={() => setIsDiagnosticsOpen(false)} state={state} automationMode={automationMode} audioLevel={audioLevel} onTestThinking={handleTestThinking} />
    </div>
  );
}

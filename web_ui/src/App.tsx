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
const WAKE_MODE_KEY = 'jarvis_wake_mode_v1';

function loadStoredMessages(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(CHAT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (Array.isArray(parsed) && parsed.length) return parsed;
  } catch {}
  return [{
    id: 'init-1',
    role: 'assistant',
    content: 'JARVIS online. Private memory, intelligent routing and wake control ready.',
    timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
  }];
}

function loadStoredSession(): string | null {
  try { return localStorage.getItem(SESSION_STORAGE_KEY); } catch { return null; }
}

function loadWakeMode(): boolean {
  try { return localStorage.getItem(WAKE_MODE_KEY) === '1'; } catch { return false; }
}

const WAKE_PHRASES = [
  /\bwake up\s+jarvis\b/i,
  /\bhey\s+jarvis\b/i,
  /\bokay\s+jarvis\b/i,
  /\bok\s+jarvis\b/i,
];
const SLEEP_PHRASE = /\b(?:go to sleep|sleep|stand by|standby)\s+jarvis\b/i;

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
  const [wakeMode, setWakeMode] = useState(loadWakeMode);
  const [messages, setMessages] = useState<ChatMessage[]>(loadStoredMessages);

  const recognitionRef = useRef<any>(null);
  const stopMicRef = useRef<(() => void) | null>(null);
  const startRecognitionRef = useRef<((wakeListening: boolean) => void) | null>(null);
  const manualStopRef = useRef(false);
  const wakeArmedRef = useRef(false);
  const wakeModeRef = useRef(wakeMode);
  const stateRef = useRef<JarvisState>(state);
  const recognitionRunningRef = useRef(false);

  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => {
    wakeModeRef.current = wakeMode;
    try { localStorage.setItem(WAKE_MODE_KEY, wakeMode ? '1' : '0'); } catch {}
  }, [wakeMode]);
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
    const sendHeartbeat = async () => { try { await fetch('/api/device/heartbeat', { method: 'POST', credentials: 'include' }); } catch {} };
    sendHeartbeat();
    timer = setInterval(sendHeartbeat, 60_000);
    return () => { if (timer) clearInterval(timer); };
  }, []);

  const [tasks, setTasks] = useState<AutomationTask[]>([
    { id: 'task-1', name: 'Cyber Security Sweep', category: 'Security', status: 'idle', progress: 0, logs: ['Ready to execute.'] },
    { id: 'task-2', name: 'Neural Node Optimizer', category: 'AI Engine', status: 'idle', progress: 0, logs: ['Awaiting overdrive signal.'] },
    { id: 'task-3', name: 'System Diagnostic Sweep', category: 'Maintenance', status: 'idle', progress: 0, logs: ['Standby mode.'] },
  ]);

  const addSystemMessage = useCallback((content: string) => {
    setMessages((prev) => [...prev, {
      id: `sys-${Date.now()}-${Math.random()}`,
      role: 'system',
      content,
      timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
    }]);
  }, []);

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
      addSystemMessage('[AUTOMATION OVERDRIVE ACTIVATED] Core ring converted to Crimson Red.');
    } else {
      addSystemMessage('[AUTOMATION STANDBY] Core ring reverted to Cyan Blue.');
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

  const handleSendMessage = useCallback(async (text: string) => {
    const cleanText = text.trim();
    if (!cleanText) return;

    if (WAKE_PHRASES.some((pattern) => pattern.test(cleanText))) {
      wakeModeRef.current = true;
      setWakeMode(true);
      wakeArmedRef.current = true;
      addSystemMessage('[WAKE MODE] JARVIS is now listening continuously. Say “sleep Jarvis” to pause.');
      return;
    }
    if (SLEEP_PHRASE.test(cleanText)) {
      wakeArmedRef.current = false;
      wakeModeRef.current = false;
      setWakeMode(false);
      addSystemMessage('[WAKE MODE] JARVIS is standing by.');
      return;
    }

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: cleanText,
      timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
    };
    const historyForRequest = messages.slice(-12).map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, userMsg]);
    setState('thinking');
    jarvisAudio.playStateSound('thinking');

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: cleanText, automationMode, session_id: cloudSessionId, history: historyForRequest }),
      });
      const data = await response.json();
      if (response.status === 401) throw new Error('OWNER_AUTH_REQUIRED');
      if (!response.ok) throw new Error(data.error || 'Cloud request failed');
      if (data.session_id) setCloudSessionId(data.session_id);
      const replyText = data.reply || 'Request processed successfully, sir.';
      setMessages((prev) => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content: replyText, timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }) }]);

      if (autoTTS) {
        jarvisAudio.speak(
          replyText,
          () => setState('speaking'),
          () => {
            setState('idle');
            setAudioLevel(0);
            if (wakeModeRef.current && wakeArmedRef.current && !recognitionRunningRef.current) {
              window.setTimeout(() => startRecognitionRef.current?.(true), 180);
            }
          },
          (level) => setAudioLevel(level),
        );
      } else {
        setTimeout(() => {
          setState('idle');
          if (wakeModeRef.current && wakeArmedRef.current && !recognitionRunningRef.current) {
            startRecognitionRef.current?.(true);
          }
        }, 800);
      }
    } catch (err) {
      console.error('Error contacting JARVIS Cloud:', err);
      const message = err instanceof Error && err.message === 'OWNER_AUTH_REQUIRED'
        ? 'Owner authentication expired. Reload the HUD to unlock JARVIS again.'
        : 'The cloud link is temporarily unavailable. Local interface protocols remain active.';
      setMessages((prev) => [...prev, { id: (Date.now() + 1).toString(), role: 'assistant', content: message, timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }) }]);
      setState('idle');
    }
  }, [addSystemMessage, automationMode, autoTTS, cloudSessionId, messages]);

  const stopRecognition = useCallback(() => {
    manualStopRef.current = true;
    try { recognitionRef.current?.stop(); } catch {}
    recognitionRef.current = null;
    recognitionRunningRef.current = false;
  }, []);

  const startRecognition = useCallback((wakeListening: boolean) => {
    const SpeechRecognitionClass = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognitionClass) {
      addSystemMessage('Voice recognition is unavailable in this browser. Try Chrome/Edge.');
      return;
    }

    stopRecognition();
    manualStopRef.current = false;
    const recognition = new SpeechRecognitionClass();
    recognition.continuous = wakeListening;
    recognition.interimResults = true;
    recognition.lang = 'en-IN';
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      recognitionRunningRef.current = true;
      setState('listening');
    };

    recognition.onresult = (event: any) => {
      let finalText = '';
      let latestInterim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i]?.[0]?.transcript || '';
        if (event.results[i].isFinal) finalText += `${transcript} `;
        else latestInterim += `${transcript} `;
      }

      if ((finalText || latestInterim).trim() && stateRef.current === 'speaking') {
        jarvisAudio.stopSpeaking();
      }

      if (!finalText.trim()) return;
      const transcript = finalText.trim();

      if (!wakeListening) {
        if (WAKE_PHRASES.some((pattern) => pattern.test(transcript))) {
          wakeModeRef.current = true;
          setWakeMode(true);
          wakeArmedRef.current = true;
          addSystemMessage('[WAKE MODE] JARVIS is now listening continuously.');
          stopRecognition();
          window.setTimeout(() => startRecognition(true), 120);
          return;
        }
        stopRecognition();
        stopMicRef.current?.();
        handleSendMessage(transcript);
        return;
      }

      if (!wakeArmedRef.current) {
        if (WAKE_PHRASES.some((pattern) => pattern.test(transcript))) {
          wakeArmedRef.current = true;
          addSystemMessage('[WAKE] I\'m listening.');
        }
        return;
      }

      if (SLEEP_PHRASE.test(transcript)) {
        wakeArmedRef.current = false;
        wakeModeRef.current = false;
        setWakeMode(false);
        addSystemMessage('[WAKE MODE] JARVIS is standing by.');
        return;
      }

      stopRecognition();
      stopMicRef.current?.();
      handleSendMessage(transcript);
    };

    recognition.onerror = (event: any) => {
      recognitionRunningRef.current = false;
      if (wakeListening && wakeModeRef.current && !manualStopRef.current && event?.error !== 'not-allowed') {
        window.setTimeout(() => startRecognition(true), 500);
      } else {
        setState('idle');
        setAudioLevel(0);
      }
    };

    recognition.onend = () => {
      recognitionRunningRef.current = false;
      if (wakeListening && wakeModeRef.current && !manualStopRef.current) {
        window.setTimeout(() => startRecognition(true), 250);
      }
    };

    try {
      recognition.start();
      recognitionRef.current = recognition;
    } catch (error) {
      console.warn('SpeechRecognition initialization error:', error);
      recognitionRunningRef.current = false;
    }
  }, [addSystemMessage, handleSendMessage, stopRecognition]);

  startRecognitionRef.current = startRecognition;

  const handleToggleListen = async () => {
    if (recognitionRunningRef.current || state === 'listening') {
      stopRecognition();
      stopMicRef.current?.();
      stopMicRef.current = null;
      setState('idle');
      setAudioLevel(0);
      return;
    }

    jarvisAudio.stopSpeaking();
    setState('listening');
    jarvisAudio.playStateSound('listening');
    stopMicRef.current = await jarvisAudio.startMicAnalyzer((level) => {
      setAudioLevel(level);
      if (stateRef.current === 'speaking' && level > 0.10) jarvisAudio.stopSpeaking();
    });

    if (wakeModeRef.current) {
      wakeArmedRef.current = false;
      startRecognition(true);
    } else {
      startRecognition(false);
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

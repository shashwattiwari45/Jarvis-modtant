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

export default function App() {
  const [state, setState] = useState<JarvisState>('idle');
  const [automationMode, setAutomationMode] = useState<boolean>(false);
  const [audioLevel, setAudioLevel] = useState<number>(0);
  const [audioMuted, setAudioMuted] = useState<boolean>(false);
  const [cloudSessionId, setCloudSessionId] = useState<string | null>(null);

  // UI Panels
  const [isChatOpen, setIsChatOpen] = useState<boolean>(false);
  const [isAutomationOpen, setIsAutomationOpen] = useState<boolean>(false);
  const [isDiagnosticsOpen, setIsDiagnosticsOpen] = useState<boolean>(false);

  // Auto speech synthesis toggle
  const [autoTTS, setAutoTTS] = useState<boolean>(true);

  // Chat conversation
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'init-1',
      role: 'assistant',
      content: 'Good day, sir. All core matrices online. Ring shader active on WebGL Canvas.',
      timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
    },
  ]);

  // Register this UI as a cloud-connected Jarvis device and keep presence alive.
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;

    const sendHeartbeat = async () => {
      try {
        await fetch('/api/device/heartbeat', { method: 'POST' });
      } catch {
        // UI remains usable if the cloud is temporarily unavailable.
      }
    };

    sendHeartbeat();
    timer = setInterval(sendHeartbeat, 60_000);

    return () => {
      if (timer) clearInterval(timer);
    };
  }, []);

  // Automated Macro Tasks when Automation Mode is enabled
  const [tasks, setTasks] = useState<AutomationTask[]>([
    {
      id: 'task-1',
      name: 'Cyber Security Sweep',
      category: 'Security',
      status: 'idle',
      progress: 0,
      logs: ['Ready to execute.'],
    },
    {
      id: 'task-2',
      name: 'Neural Node Optimizer',
      category: 'AI Engine',
      status: 'idle',
      progress: 0,
      logs: ['Awaiting overdrive signal.'],
    },
    {
      id: 'task-3',
      name: 'System Diagnostic Sweep',
      category: 'Maintenance',
      status: 'idle',
      progress: 0,
      logs: ['Standby mode.'],
    },
  ]);

  // Web Speech Recognition reference
  const recognitionRef = useRef<any>(null);
  const stopMicRef = useRef<(() => void) | null>(null);

  const handleToggleMute = () => {
    const nextMute = !audioMuted;
    setAudioMuted(nextMute);
    jarvisAudio.setMute(nextMute);
  };

  const triggerAutomatedTasks = useCallback(() => {
    setTasks((prev) =>
      prev.map((t) => ({
        ...t,
        status: 'running',
        progress: 10,
        logs: [...t.logs, 'Initializing automated thread...'],
      }))
    );

    let progressCount = 10;
    const interval = setInterval(() => {
      progressCount += 15;
      if (progressCount >= 100) {
        progressCount = 100;
        clearInterval(interval);
        setTasks((prev) =>
          prev.map((t) => ({
            ...t,
            status: 'completed',
            progress: 100,
            logs: [...t.logs, 'Macro execution complete. 100% verified.'],
          }))
        );
      } else {
        setTasks((prev) =>
          prev.map((t) => ({
            ...t,
            progress: progressCount,
            logs: [...t.logs, `Progressing: ${progressCount}%...`],
          }))
        );
      }
    }, 800);
  }, []);

  // Toggle Automation Mode
  const handleToggleAutomation = () => {
    const nextMode = !automationMode;
    setAutomationMode(nextMode);
    jarvisAudio.playStateSound(nextMode ? 'automation_on' : 'automation_off');

    if (nextMode) {
      setIsAutomationOpen(true);
      triggerAutomatedTasks();

      const newMsg: ChatMessage = {
        id: Date.now().toString(),
        role: 'system',
        content: '[AUTOMATION OVERDRIVE ACTIVATED] Core ring shader converted to Crimson Red. Macro task subroutines running in background.',
        timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
      };
      setMessages((prev) => [...prev, newMsg]);
    } else {
      const newMsg: ChatMessage = {
        id: Date.now().toString(),
        role: 'system',
        content: '[AUTOMATION STANDBY] Core ring shader reverted to Cyan Blue.',
        timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
      };
      setMessages((prev) => [...prev, newMsg]);
    }
  };

  const handleTriggerCustomTask = (taskName: string) => {
    const newTask: AutomationTask = {
      id: Date.now().toString(),
      name: taskName,
      category: 'User Routine',
      status: 'running',
      progress: 20,
      logs: [`Initiated custom macro: "${taskName}"`],
    };
    setTasks((prev) => [newTask, ...prev]);

    let progressCount = 20;
    const interval = setInterval(() => {
      progressCount += 25;
      if (progressCount >= 100) {
        progressCount = 100;
        clearInterval(interval);
        setTasks((prev) =>
          prev.map((t) =>
            t.id === newTask.id
              ? { ...t, status: 'completed', progress: 100, logs: [...t.logs, 'Macro finished successfully.'] }
              : t
          )
        );
      } else {
        setTasks((prev) =>
          prev.map((t) =>
            t.id === newTask.id
              ? { ...t, progress: progressCount, logs: [...t.logs, `Executing stage ${progressCount}%`] }
              : t
          )
        );
      }
    }, 600);
  };

  // Process User Query through Jarvis Cloud and preserve the cloud session across requests.
  const handleSendMessage = async (text: string) => {
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setState('thinking');
    jarvisAudio.playStateSound('thinking');

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          automationMode,
          session_id: cloudSessionId,
          history: messages.map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      const data = await response.json();
      if (data.session_id) setCloudSessionId(data.session_id);
      const replyText = data.reply || 'Request processed successfully, sir.';

      const botMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: replyText,
        timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
      };

      setMessages((prev) => [...prev, botMsg]);

      if (autoTTS) {
        jarvisAudio.speak(
          replyText,
          () => setState('speaking'),
          () => {
            setState('idle');
            setAudioLevel(0);
          },
          (level) => setAudioLevel(level)
        );
      } else {
        setTimeout(() => setState('idle'), 800);
      }
    } catch (err) {
      console.error('Error contacting JARVIS Cloud:', err);
      const errorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'I apologize, sir. The cloud link is temporarily unavailable. Local interface protocols remain active.',
        timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
      };
      setMessages((prev) => [...prev, errorMsg]);
      setState('idle');
    }
  };

  // Toggle Voice Recognition / Microphone Listening Mode
  const handleToggleListen = async () => {
    if (state === 'listening') {
      if (stopMicRef.current) {
        stopMicRef.current();
        stopMicRef.current = null;
      }
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch (e) {}
      }
      setState('idle');
      setAudioLevel(0);
      return;
    }

    jarvisAudio.stopSpeaking();
    setState('listening');
    jarvisAudio.playStateSound('listening');

    const cleanupAnalyzer = await jarvisAudio.startMicAnalyzer((level) => setAudioLevel(level));
    stopMicRef.current = cleanupAnalyzer;

    const SpeechRecognitionClass =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (SpeechRecognitionClass) {
      try {
        const recognition = new SpeechRecognitionClass();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';

        recognition.onresult = (event: any) => {
          const transcript = event.results[0][0].transcript;
          if (transcript) {
            if (stopMicRef.current) stopMicRef.current();
            handleSendMessage(transcript);
          }
        };

        recognition.onerror = () => {
          if (stopMicRef.current) stopMicRef.current();
          setState('idle');
          setAudioLevel(0);
        };

        recognition.onend = () => {
          if (stopMicRef.current) stopMicRef.current();
        };

        recognition.start();
        recognitionRef.current = recognition;
      } catch (e) {
        console.warn('SpeechRecognition initialization error:', e);
      }
    } else {
      setTimeout(() => {
        if (stopMicRef.current) stopMicRef.current();
        handleSendMessage('Run quick system diagnostic scan');
      }, 3500);
    }
  };

  const handleTestThinking = () => {
    setIsDiagnosticsOpen(false);
    handleSendMessage('Simulate fast thinking routine');
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-black select-none">
      <JarvisCanvas
        state={state}
        automationMode={automationMode}
        audioLevel={audioLevel}
        onCanvasClick={() => {
          if (!isChatOpen && !isAutomationOpen) setIsChatOpen(true);
        }}
      />

      <div className="fixed inset-0 scanlines opacity-40 pointer-events-none z-10" />

      <TopBar
        state={state}
        automationMode={automationMode}
        onToggleAutomation={handleToggleAutomation}
        onOpenDiagnostics={() => setIsDiagnosticsOpen(true)}
        audioMuted={audioMuted}
        onToggleMute={handleToggleMute}
      />

      <LeftControlDock
        state={state}
        automationMode={automationMode}
        onToggleListen={handleToggleListen}
        onToggleChat={() => setIsChatOpen(!isChatOpen)}
        onToggleAutomation={handleToggleAutomation}
        audioMuted={audioMuted}
        onToggleMute={handleToggleMute}
        isChatOpen={isChatOpen}
      />

      <BottomControlBar
        state={state}
        automationMode={automationMode}
        onToggleListen={handleToggleListen}
        onToggleAutomation={handleToggleAutomation}
        onToggleChat={() => setIsChatOpen(!isChatOpen)}
      />

      <ChatDrawer
        isOpen={isChatOpen}
        onClose={() => setIsChatOpen(false)}
        messages={messages}
        onSendMessage={handleSendMessage}
        state={state}
        automationMode={automationMode}
        onToggleListen={handleToggleListen}
        autoTTS={autoTTS}
        onToggleAutoTTS={() => setAutoTTS(!autoTTS)}
      />

      <AutomationPanel
        isOpen={isAutomationOpen}
        onClose={() => setIsAutomationOpen(false)}
        tasks={tasks}
        onTriggerTask={handleTriggerCustomTask}
      />

      <SystemDiagnosticsModal
        isOpen={isDiagnosticsOpen}
        onClose={() => setIsDiagnosticsOpen(false)}
        state={state}
        automationMode={automationMode}
        audioLevel={audioLevel}
        onTestThinking={handleTestThinking}
      />
    </div>
  );
}

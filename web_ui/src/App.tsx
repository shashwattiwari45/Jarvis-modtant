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

  // Sound Mute Sync
  const handleToggleMute = () => {
    const nextMute = !audioMuted;
    setAudioMuted(nextMute);
    jarvisAudio.setMute(nextMute);
  };

  // Toggle Automation Mode
  const handleToggleAutomation = () => {
    const nextMode = !automationMode;
    setAutomationMode(nextMode);
    jarvisAudio.playStateSound(nextMode ? 'automation_on' : 'automation_off');

    if (nextMode) {
      setIsAutomationOpen(true);
      // Automatically trigger running macro tasks
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

  // Run tasks in automation mode
  const triggerAutomatedTasks = () => {
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

  // Process User Query with Express API & Speech Synthesis
  const handleSendMessage = async (text: string) => {
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
    };

    setMessages((prev) => [...prev, userMsg]);

    // 1. Enter THINKING state (Ring rotates FAST!)
    setState('thinking');
    jarvisAudio.playStateSound('thinking');

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          automationMode,
          history: messages.map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      const data = await response.json();
      const replyText = data.reply || 'Request processed successfully, sir.';

      const botMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: replyText,
        timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
      };

      setMessages((prev) => [...prev, botMsg]);

      // 2. Speak response with voice (Ring rotates dynamically with voice modulation!)
      if (autoTTS) {
        jarvisAudio.speak(
          replyText,
          () => {
            setState('speaking');
          },
          () => {
            setState('idle');
            setAudioLevel(0);
          },
          (level) => {
            setAudioLevel(level);
          }
        );
      } else {
        setTimeout(() => {
          setState('idle');
        }, 800);
      }
    } catch (err) {
      console.error('Error contacting JARVIS AI backend:', err);
      const errorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'I apologize, sir. A brief neural latency occurred. All local protocols remain active.',
        timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
      };
      setMessages((prev) => [...prev, errorMsg]);
      setState('idle');
    }
  };

  // Toggle Voice Recognition / Microphone Listening Mode
  const handleToggleListen = async () => {
    if (state === 'listening') {
      // Stop listening
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

    // Stop speaking if currently speaking
    jarvisAudio.stopSpeaking();

    // Enter LISTENING state (Ring rotates SLOW!)
    setState('listening');
    jarvisAudio.playStateSound('listening');

    // Start mic audio level analyzer
    const cleanupAnalyzer = await jarvisAudio.startMicAnalyzer((level) => {
      setAudioLevel(level);
    });
    stopMicRef.current = cleanupAnalyzer;

    // Check for browser SpeechRecognition API
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
      // Fallback for browsers without SpeechRecognition
      setTimeout(() => {
        if (stopMicRef.current) stopMicRef.current();
        handleSendMessage('Run quick system diagnostic scan');
      }, 3500);
    }
  };

  // Test thinking fast rotation
  const handleTestThinking = () => {
    setIsDiagnosticsOpen(false);
    handleSendMessage('Simulate fast thinking routine');
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-black select-none">
      {/* Background WebGL Core Canvas Ring */}
      <JarvisCanvas
        state={state}
        automationMode={automationMode}
        audioLevel={audioLevel}
        onCanvasClick={() => {
          if (!isChatOpen && !isAutomationOpen) {
            setIsChatOpen(true);
          }
        }}
      />

      {/* CRT Scanline Overlay */}
      <div className="fixed inset-0 scanlines opacity-40 pointer-events-none z-10" />

      {/* Top Header Bar */}
      <TopBar
        state={state}
        automationMode={automationMode}
        onToggleAutomation={handleToggleAutomation}
        onOpenDiagnostics={() => setIsDiagnosticsOpen(true)}
        audioMuted={audioMuted}
        onToggleMute={handleToggleMute}
      />

      {/* Left Vertical Dock */}
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

      {/* Bottom Control Bar */}
      <BottomControlBar
        state={state}
        automationMode={automationMode}
        onToggleListen={handleToggleListen}
        onToggleAutomation={handleToggleAutomation}
        onToggleChat={() => setIsChatOpen(!isChatOpen)}
      />

      {/* Sliding AI Chat Console Drawer */}
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

      {/* Automation Overdrive Red Mode Panel */}
      <AutomationPanel
        isOpen={isAutomationOpen}
        onClose={() => setIsAutomationOpen(false)}
        tasks={tasks}
        onTriggerTask={handleTriggerCustomTask}
      />

      {/* System Diagnostics Modal */}
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

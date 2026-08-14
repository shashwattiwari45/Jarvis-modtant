// Audio Synthesizer and Web Speech API helper for JARVIS

class JarvisAudioSystem {
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private micStream: MediaStream | null = null;
  private micSource: MediaStreamAudioSourceNode | null = null;
  private isMuted: boolean = false;

  private initCtx() {
    if (!this.audioCtx) {
      const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioCtxClass) {
        this.audioCtx = new AudioCtxClass();
      }
    }
    if (this.audioCtx && this.audioCtx.state === 'suspended') {
      this.audioCtx.resume();
    }
  }

  // Play high-tech HUD beep sound
  public playBeep(freq = 880, type: OscillatorType = 'sine', duration = 0.08) {
    if (this.isMuted) return;
    try {
      this.initCtx();
      if (!this.audioCtx) return;

      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();

      osc.type = type;
      osc.frequency.setValueAtTime(freq, this.audioCtx.currentTime);

      gain.gain.setValueAtTime(0.08, this.audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + duration);

      osc.connect(gain);
      gain.connect(this.audioCtx.destination);

      osc.start();
      osc.stop(this.audioCtx.currentTime + duration);
    } catch (e) {
      // Audio context play error handled
    }
  }

  // Play state transition sound (e.g. Thinking / Automation Red mode alert)
  public playStateSound(state: 'listening' | 'thinking' | 'speaking' | 'automation_on' | 'automation_off') {
    if (this.isMuted) return;
    try {
      this.initCtx();
      if (!this.audioCtx) return;

      const now = this.audioCtx.currentTime;
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();

      if (state === 'automation_on') {
        // High alert descending-ascending alarm chime
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(220, now);
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.2);
        gain.gain.setValueAtTime(0.12, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
      } else if (state === 'thinking') {
        // High freq pulsing chime
        osc.type = 'sine';
        osc.frequency.setValueAtTime(1200, now);
        osc.frequency.exponentialRampToValueAtTime(1600, now + 0.15);
        gain.gain.setValueAtTime(0.06, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
      } else if (state === 'listening') {
        // Low warm tone
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(440, now);
        osc.frequency.linearRampToValueAtTime(554, now + 0.12);
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
      } else {
        // Speaking start
        osc.type = 'sine';
        osc.frequency.setValueAtTime(660, now);
        osc.frequency.linearRampToValueAtTime(880, now + 0.1);
        gain.gain.setValueAtTime(0.05, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.1);
      }

      osc.connect(gain);
      gain.connect(this.audioCtx.destination);
      osc.start();
      osc.stop(now + 0.3);
    } catch (e) {
      // Audio error handled
    }
  }

  // Toggle Mute
  public setMute(muted: boolean) {
    this.isMuted = muted;
  }

  public getMute() {
    return this.isMuted;
  }

  // Start Mic Analyzer for real-time sound levels
  public async startMicAnalyzer(onAudioLevel: (level: number) => void): Promise<() => void> {
    try {
      this.initCtx();
      if (!this.audioCtx) return () => {};

      this.micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.analyser = this.audioCtx.createAnalyser();
      this.analyser.fftSize = 64;

      this.micSource = this.audioCtx.createMediaStreamSource(this.micStream);
      this.micSource.connect(this.analyser);

      const dataArray = new Uint8Array(this.analyser.frequencyBinCount);
      let animId: number;

      const update = () => {
        if (this.analyser) {
          this.analyser.getByteFrequencyData(dataArray);
          let sum = 0;
          for (let i = 0; i < dataArray.length; i++) {
            sum += dataArray[i];
          }
          const avg = sum / dataArray.length;
          const normalized = Math.min(1.0, avg / 128);
          onAudioLevel(normalized);
        }
        animId = requestAnimationFrame(update);
      };

      update();

      return () => {
        cancelAnimationFrame(animId);
        if (this.micStream) {
          this.micStream.getTracks().forEach((track) => track.stop());
          this.micStream = null;
        }
        if (this.micSource) {
          this.micSource.disconnect();
          this.micSource = null;
        }
      };
    } catch (err) {
      console.warn("Microphone access unavailable or denied", err);
      return () => {};
    }
  }

  // Speak text using Web Speech API with SpeechSynthesis
  public speak(
    text: string,
    onStart: () => void,
    onEnd: () => void,
    onSpeechBoundary?: (level: number) => void
  ) {
    if (this.isMuted || !('speechSynthesis' in window)) {
      // Speech synthesis not available or muted - simulate speech duration
      onStart();
      const duration = Math.min(6000, Math.max(1800, text.length * 55));
      let elapsed = 0;
      const interval = setInterval(() => {
        elapsed += 100;
        if (onSpeechBoundary) {
          onSpeechBoundary(0.3 + Math.sin(elapsed / 100) * 0.4);
        }
        if (elapsed >= duration) {
          clearInterval(interval);
          onEnd();
        }
      }, 100);
      return;
    }

    window.speechSynthesis.cancel(); // Stop current speech
    const utterance = new SpeechSynthesisUtterance(text);

    // Pick a crisp English voice if possible
    const voices = window.speechSynthesis.getVoices();
    const jarvisVoice = voices.find(
      (v) => v.lang.startsWith('en') && (v.name.includes('Daniel') || v.name.includes('UK') || v.name.includes('Google') || v.name.includes('Natural'))
    ) || voices.find((v) => v.lang.startsWith('en'));

    if (jarvisVoice) {
      utterance.voice = jarvisVoice;
    }

    utterance.pitch = 0.95; // Slightly lower pitched for JARVIS authority
    utterance.rate = 1.05;  // Slightly faster crisp speed

    let boundaryInterval: any;

    utterance.onstart = () => {
      onStart();
      let step = 0;
      boundaryInterval = setInterval(() => {
        step++;
        if (onSpeechBoundary) {
          onSpeechBoundary(0.2 + Math.abs(Math.sin(step * 0.4)) * 0.7);
        }
      }, 80);
    };

    utterance.onend = () => {
      if (boundaryInterval) clearInterval(boundaryInterval);
      onEnd();
    };

    utterance.onerror = () => {
      if (boundaryInterval) clearInterval(boundaryInterval);
      onEnd();
    };

    window.speechSynthesis.speak(utterance);
  }

  public stopSpeaking() {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  }
}

export const jarvisAudio = new JarvisAudioSystem();

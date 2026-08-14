// JARVIS audio system: HUD tones, microphone analysis and a male-first browser voice.

class JarvisAudioSystem {
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private micStream: MediaStream | null = null;
  private micSource: MediaStreamAudioSourceNode | null = null;
  private isMuted = false;
  private voices: SpeechSynthesisVoice[] = [];
  private voicesReady = false;

  constructor() {
    if ('speechSynthesis' in window) {
      this.refreshVoices();
      window.speechSynthesis.addEventListener('voiceschanged', () => this.refreshVoices());
    }
  }

  private refreshVoices() {
    if (!('speechSynthesis' in window)) return;
    const voices = window.speechSynthesis.getVoices();
    if (voices.length) {
      this.voices = voices;
      this.voicesReady = true;
    }
  }

  private initCtx() {
    if (!this.audioCtx) {
      const AudioCtxClass = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioCtxClass) this.audioCtx = new AudioCtxClass();
    }
    if (this.audioCtx?.state === 'suspended') this.audioCtx.resume().catch(() => {});
  }

  public playBeep(freq = 880, type: OscillatorType = 'sine', duration = 0.08) {
    if (this.isMuted) return;
    try {
      this.initCtx();
      if (!this.audioCtx) return;
      const now = this.audioCtx.currentTime;
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, now);
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + duration);
      osc.connect(gain);
      gain.connect(this.audioCtx.destination);
      osc.start(now);
      osc.stop(now + duration);
    } catch {}
  }

  public playStateSound(state: 'listening' | 'thinking' | 'speaking' | 'automation_on' | 'automation_off') {
    if (this.isMuted) return;
    try {
      this.initCtx();
      if (!this.audioCtx) return;
      const now = this.audioCtx.currentTime;
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();

      if (state === 'automation_on') {
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(220, now);
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.2);
        gain.gain.setValueAtTime(0.12, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
      } else if (state === 'thinking') {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(1200, now);
        osc.frequency.exponentialRampToValueAtTime(1600, now + 0.15);
        gain.gain.setValueAtTime(0.06, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
      } else if (state === 'listening') {
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(440, now);
        osc.frequency.linearRampToValueAtTime(554, now + 0.12);
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
      } else {
        osc.type = 'sine';
        osc.frequency.setValueAtTime(660, now);
        osc.frequency.linearRampToValueAtTime(880, now + 0.1);
        gain.gain.setValueAtTime(0.05, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.1);
      }

      osc.connect(gain);
      gain.connect(this.audioCtx.destination);
      osc.start(now);
      osc.stop(now + 0.3);
    } catch {}
  }

  public setMute(muted: boolean) {
    this.isMuted = muted;
  }

  public getMute() {
    return this.isMuted;
  }

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
      let animId = 0;
      const update = () => {
        if (this.analyser) {
          this.analyser.getByteFrequencyData(dataArray);
          let sum = 0;
          for (const value of dataArray) sum += value;
          onAudioLevel(Math.min(1, (sum / dataArray.length) / 128));
        }
        animId = requestAnimationFrame(update);
      };
      update();

      return () => {
        cancelAnimationFrame(animId);
        this.micStream?.getTracks().forEach((track) => track.stop());
        this.micStream = null;
        this.micSource?.disconnect();
        this.micSource = null;
      };
    } catch (err) {
      console.warn('Microphone access unavailable or denied', err);
      return () => {};
    }
  }

  private chooseMaleVoice(): SpeechSynthesisVoice | undefined {
    if (!this.voicesReady) this.refreshVoices();
    const voices = this.voices.length ? this.voices : (window.speechSynthesis?.getVoices() || []);
    if (!voices.length) return undefined;

    const preferredMaleNames = [
      'Microsoft Ravi',
      'Ravi',
      'Microsoft David',
      'David',
      'Microsoft Mark',
      'Mark',
      'Guy',
      'Daniel',
      'Alex',
      'Google UK English Male',
      'Google US English Male',
      'Male',
    ];

    // Prefer an Indian English male voice when the browser exposes one.
    for (const name of preferredMaleNames.slice(0, 2)) {
      const exact = voices.find((v) => v.name.toLowerCase().includes(name.toLowerCase()) && /^en[-_]in/i.test(v.lang));
      if (exact) return exact;
    }

    for (const name of preferredMaleNames) {
      const match = voices.find((v) => v.name.toLowerCase().includes(name.toLowerCase()) && /^en/i.test(v.lang));
      if (match) return match;
    }

    const indian = voices.find((v) => /^en[-_]in/i.test(v.lang));
    if (indian) return indian;
    return voices.find((v) => /^en[-_]gb/i.test(v.lang)) || voices.find((v) => /^en/i.test(v.lang));
  }

  public speak(text: string, onStart: () => void, onEnd: () => void, onSpeechBoundary?: (level: number) => void) {
    if (!this.isMuted && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      this.refreshVoices();
      const utterance = new SpeechSynthesisUtterance(text);
      const voice = this.chooseMaleVoice();
      if (voice) utterance.voice = voice;

      utterance.lang = voice?.lang || 'en-IN';
      utterance.pitch = 0.78;
      utterance.rate = 1.02;
      utterance.volume = 1;

      let boundaryInterval: ReturnType<typeof setInterval> | null = null;
      utterance.onstart = () => {
        onStart();
        let step = 0;
        boundaryInterval = setInterval(() => {
          step += 1;
          onSpeechBoundary?.(0.18 + Math.abs(Math.sin(step * 0.42)) * 0.72);
        }, 80);
      };
      utterance.onend = () => {
        if (boundaryInterval) clearInterval(boundaryInterval);
        onSpeechBoundary?.(0);
        onEnd();
      };
      utterance.onerror = () => {
        if (boundaryInterval) clearInterval(boundaryInterval);
        onSpeechBoundary?.(0);
        onEnd();
      };

      window.speechSynthesis.speak(utterance);
      return;
    }

    // Visual fallback when browser speech is unavailable or muted.
    onStart();
    const duration = Math.min(6000, Math.max(1400, text.length * 42));
    let elapsed = 0;
    const interval = setInterval(() => {
      elapsed += 100;
      onSpeechBoundary?.(0.25 + Math.abs(Math.sin(elapsed / 120)) * 0.5);
      if (elapsed >= duration) {
        clearInterval(interval);
        onSpeechBoundary?.(0);
        onEnd();
      }
    }, 100);
  }

  public stopSpeaking() {
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  }
}

export const jarvisAudio = new JarvisAudioSystem();

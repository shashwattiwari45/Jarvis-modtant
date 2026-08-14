// JARVIS audio system: Hindi/Hinglish-aware TTS, HUD tones and microphone analysis.
import * as SanscriptModule from '@indic-transliteration/sanscript';

type VoiceMode = 'english' | 'hindi';
interface SpeechSegment { text: string; mode: VoiceMode; }
const Sanscript = (SanscriptModule as any).default || SanscriptModule;

const HINGLISH_WORDS = new Set([
  'aaj','abhi','acha','achha','accha','aise','apna','apni','apne','aur','bas','bhai','bro','bhi','bht','bahut',
  'bol','bolo','bata','batao','chahta','chahti','chalo','chal','cheez','de','di','do','ek','fir','phir','gaya','gayi',
  'gaye','hai','hain','ho','hua','hogi','hoga','ka','kaa','kar','karo','karna','karne','karti','karte','kya','kyu',
  'kyon','kyunki','ke','ki','ko','koi','kr','kuch','main','mein','mera','meri','mere','mujhe','mujhko','na','nahi',
  'nahin','ne','par','pe','raha','rahe','rahi','sab','sach','saath','se','sirf','the','thi','tha','toh','to','tum',
  'tumhara','tumhari','tumhare','umeed','wala','wali','wale','ya','ye','yahi','yahan','uska','uski','uske','unka',
  'unki','unke','kahan','kaise','kyun','kab','kitna','kitni','kitne','mujhse','tujhe','tera','teri','tere','apko',
  'aap','aapka','aapki','aapke','haan','han','theek','thik','scene','yaar','zara','zyada','kam','ab','naya','nayi',
  'naye','hamara','hum','humko','humari','bana','banao','banaya','chahiye','sakta','sakti','sakte','rakh','rakho',
  'le','lelo','dekh','dekho','sun','suno','samajh','samjha','samjho','pata','pakka','jaldi','slow','mat','matlab',
  'waise','vaise','bilkul','shayad','lagta','lagti','lagega','karu','karoon','mil','milega','mili','milta','milti',
  'rahega','rahegi','jaisa','jaise','ja','jao','aao','aana','jana','jaana','aaya','aayi','aaye','karke','bolna',
  'pooch','poochho','puch','pucho','isko','usko','idhar','udhar','andar','bahar','upar','neeche','saamne','pehle',
  'baad','kal','dobara','ekdum','mast','sahi','galat','problem','dikha','dikhao','kholo','band','bandh','chalu',
  'chalao','ruk','ruko','wait','sunna','sunao','karwado','karwa','karwao'
]);

function hasDevanagari(text: string): boolean { return /[\u0900-\u097F]/.test(text); }
function normalizeToken(token: string): string { return token.toLowerCase().replace(/^[^a-z]+|[^a-z]+$/g, ''); }
function looksHinglish(text: string): boolean {
  if (!text || hasDevanagari(text)) return false;
  const words = text.toLowerCase().match(/[a-zA-Z']+/g) || [];
  if (words.length < 2) return false;
  const hits = words.filter((w) => HINGLISH_WORDS.has(normalizeToken(w))).length;
  return hits >= 2 || hits / words.length >= 0.35;
}
function transliterateHindiWord(word: string): string {
  try {
    if (!word || !/[a-z]/i.test(word)) return word;
    return String(Sanscript.t(word, 'hk', 'devanagari', { syncope: true }) || word);
  } catch { return word; }
}
function prepareHinglish(text: string): string {
  return text.split(/(\s+)/).map((token) => {
    if (!/[a-zA-Z]/.test(token)) return token;
    const normalized = normalizeToken(token);
    if (!normalized || !HINGLISH_WORDS.has(normalized)) return token;
    const converted = transliterateHindiWord(normalized);
    const prefix = token.match(/^[^a-zA-Z]*/)?.[0] || '';
    const suffix = token.match(/[^a-zA-Z]*$/)?.[0] || '';
    return `${prefix}${converted}${suffix}`;
  }).join('');
}
function buildSpeechSegments(text: string): SpeechSegment[] {
  const clean = text.trim();
  if (!clean) return [];
  if (hasDevanagari(clean)) {
    const segments: SpeechSegment[] = [];
    let current = '';
    let currentMode: VoiceMode | null = null;
    const flush = () => {
      const value = current.trim();
      if (value) segments.push({ text: value, mode: currentMode || 'english' });
      current = '';
    };
    for (const token of clean.match(/\s+|[\u0900-\u097F]+|[^\u0900-\u097F\s]+/g) || []) {
      if (/\s+/.test(token)) { current += token; continue; }
      const mode: VoiceMode = hasDevanagari(token) ? 'hindi' : 'english';
      if (currentMode && currentMode !== mode) flush();
      currentMode = mode;
      current += token;
    }
    flush();
    return segments;
  }
  if (looksHinglish(clean)) return [{ text: prepareHinglish(clean), mode: 'hindi' }];
  return [{ text: clean, mode: 'english' }];
}
function waitForVoices(): Promise<SpeechSynthesisVoice[]> {
  if (!('speechSynthesis' in window)) return Promise.resolve([]);
  const synth = window.speechSynthesis;
  const initial = synth.getVoices();
  if (initial.length) return Promise.resolve(initial);
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      synth.removeEventListener('voiceschanged', finish);
      resolve(synth.getVoices());
    };
    synth.addEventListener('voiceschanged', finish);
    window.setTimeout(finish, 1200);
  });
}
function scoreVoice(voice: SpeechSynthesisVoice, mode: VoiceMode): number {
  const lang = voice.lang.toLowerCase();
  const name = voice.name.toLowerCase();
  const maleHints = ['male','ravi','madhur','hemant','david','daniel','george','alex','aaron','mark','guy'];
  const femaleHints = ['female','heera','veena','susan','zira','samantha'];
  const isHindi = lang === 'hi-in' || lang.startsWith('hi-');
  const isIndianEnglish = lang === 'en-in';
  const isEnglish = lang.startsWith('en-');
  let score = 0;
  if (mode === 'hindi') {
    if (lang === 'hi-in') score += 120;
    else if (isHindi) score += 90;
    else if (isIndianEnglish) score += 25;
    else if (isEnglish) score += 5;
  } else {
    if (isIndianEnglish) score += 120;
    else if (isEnglish) score += 55;
  }
  if (maleHints.some((h) => name.includes(h))) score += 35;
  if (femaleHints.some((h) => name.includes(h))) score -= 25;
  if (name.includes('natural')) score += 8;
  if (name.includes('google')) score += 5;
  if (voice.localService) score += 3;
  if (voice.default) score += 1;
  return score;
}
function selectVoice(voices: SpeechSynthesisVoice[], mode: VoiceMode): SpeechSynthesisVoice | undefined {
  return [...voices].sort((a, b) => scoreVoice(b, mode) - scoreVoice(a, mode))[0];
}

class JarvisAudioSystem {
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private micStream: MediaStream | null = null;
  private micSource: MediaStreamAudioSourceNode | null = null;
  private isMuted = false;

  public constructor() {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.addEventListener('voiceschanged', () => {});
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
      this.initCtx(); if (!this.audioCtx) return;
      const now = this.audioCtx.currentTime;
      const osc = this.audioCtx.createOscillator(); const gain = this.audioCtx.createGain();
      osc.type = type; osc.frequency.setValueAtTime(freq, now);
      gain.gain.setValueAtTime(0.08, now); gain.gain.exponentialRampToValueAtTime(0.001, now + duration);
      osc.connect(gain); gain.connect(this.audioCtx.destination); osc.start(now); osc.stop(now + duration);
    } catch {}
  }

  public playStateSound(state: 'listening' | 'thinking' | 'speaking' | 'automation_on' | 'automation_off') {
    if (this.isMuted) return;
    try {
      this.initCtx(); if (!this.audioCtx) return;
      const now = this.audioCtx.currentTime; const osc = this.audioCtx.createOscillator(); const gain = this.audioCtx.createGain();
      if (state === 'automation_on') { osc.type='sawtooth'; osc.frequency.setValueAtTime(220, now); osc.frequency.exponentialRampToValueAtTime(880, now+0.2); gain.gain.setValueAtTime(0.12, now); gain.gain.exponentialRampToValueAtTime(0.001, now+0.3); }
      else if (state === 'thinking') { osc.type='sine'; osc.frequency.setValueAtTime(1200, now); osc.frequency.exponentialRampToValueAtTime(1600, now+0.15); gain.gain.setValueAtTime(0.06, now); gain.gain.exponentialRampToValueAtTime(0.001, now+0.15); }
      else if (state === 'listening') { osc.type='triangle'; osc.frequency.setValueAtTime(440, now); osc.frequency.linearRampToValueAtTime(554, now+0.12); gain.gain.setValueAtTime(0.08, now); gain.gain.exponentialRampToValueAtTime(0.001, now+0.15); }
      else { osc.type='sine'; osc.frequency.setValueAtTime(660, now); osc.frequency.linearRampToValueAtTime(880, now+0.1); gain.gain.setValueAtTime(0.05, now); gain.gain.exponentialRampToValueAtTime(0.001, now+0.1); }
      osc.connect(gain); gain.connect(this.audioCtx.destination); osc.start(now); osc.stop(now+0.3);
    } catch {}
  }

  public setMute(muted: boolean) { this.isMuted = muted; }
  public getMute() { return this.isMuted; }

  public async startMicAnalyzer(onAudioLevel: (level: number) => void): Promise<() => void> {
    try {
      this.initCtx(); if (!this.audioCtx) return () => {};
      this.micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.analyser = this.audioCtx.createAnalyser(); this.analyser.fftSize = 64;
      this.micSource = this.audioCtx.createMediaStreamSource(this.micStream); this.micSource.connect(this.analyser);
      const dataArray = new Uint8Array(this.analyser.frequencyBinCount); let animId = 0;
      const update = () => { if (this.analyser) { this.analyser.getByteFrequencyData(dataArray); let sum=0; for (const value of dataArray) sum+=value; onAudioLevel(Math.min(1,(sum/dataArray.length)/128)); } animId=requestAnimationFrame(update); };
      update();
      return () => { cancelAnimationFrame(animId); this.micStream?.getTracks().forEach((track)=>track.stop()); this.micStream=null; this.micSource?.disconnect(); this.micSource=null; };
    } catch (err) { console.warn('Microphone access unavailable or denied', err); return () => {}; }
  }

  public async speak(text: string, onStart: () => void, onEnd: () => void, onSpeechBoundary?: (level: number) => void) {
    if (this.isMuted || !('speechSynthesis' in window)) {
      onStart(); const duration=Math.min(6000,Math.max(1400,text.length*42)); let elapsed=0;
      const interval=setInterval(()=>{ elapsed+=100; onSpeechBoundary?.(0.25+Math.abs(Math.sin(elapsed/120))*0.5); if(elapsed>=duration){clearInterval(interval); onSpeechBoundary?.(0); onEnd();}},100); return;
    }

    window.speechSynthesis.cancel();
    const voices = await waitForVoices();
    const segments = buildSpeechSegments(text);
    if (!segments.length) { onEnd(); return; }

    let completed=0; let speakingStarted=false; let boundaryTimer: number | null=null;
    const finish=()=>{ if(boundaryTimer!==null){clearInterval(boundaryTimer);boundaryTimer=null;} onSpeechBoundary?.(0); onEnd(); };
    const speakSegment=(index:number)=>{
      if(index>=segments.length){finish();return;}
      const segment=segments[index];
      const utterance=new SpeechSynthesisUtterance(segment.text);
      const voice=selectVoice(voices,segment.mode);
      if(voice) utterance.voice=voice;
      utterance.lang=segment.mode==='hindi'?'hi-IN':'en-IN';
      utterance.pitch=segment.mode==='hindi'?0.9:0.92;
      utterance.rate=segment.mode==='hindi'?0.94:1.02;
      utterance.volume=1;
      utterance.onstart=()=>{ if(!speakingStarted){speakingStarted=true;onStart();} let step=0; if(boundaryTimer!==null) clearInterval(boundaryTimer); boundaryTimer=window.setInterval(()=>{step++;onSpeechBoundary?.(0.18+Math.abs(Math.sin(step*0.42))*0.72);},80); };
      utterance.onend=()=>{ completed++; if(completed===segments.length) finish(); else speakSegment(index+1); };
      utterance.onerror=()=>{ completed++; if(completed===segments.length) finish(); else speakSegment(index+1); };
      window.speechSynthesis.speak(utterance);
    };
    speakSegment(0);
  }

  public stopSpeaking() { if ('speechSynthesis' in window) window.speechSynthesis.cancel(); }
}

export { buildSpeechSegments };
export const jarvisAudio = new JarvisAudioSystem();

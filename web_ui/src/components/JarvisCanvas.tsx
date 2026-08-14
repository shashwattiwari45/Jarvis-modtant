import React, { useEffect, useRef } from 'react';
import { JarvisState } from '../types';

interface JarvisCanvasProps {
  state: JarvisState;
  automationMode: boolean;
  audioLevel: number;
  onCanvasClick?: () => void;
}

export const JarvisCanvas: React.FC<JarvisCanvasProps> = ({
  state,
  automationMode,
  audioLevel,
  onCanvasClick,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef(state);
  const automationRef = useRef(automationMode);
  const audioRef = useRef(audioLevel);

  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => { automationRef.current = automationMode; }, [automationMode]);
  useEffect(() => { audioRef.current = audioLevel; }, [audioLevel]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    let animationId = 0;
    let frame = 0;
    let width = 1;
    let height = 1;
    let dpr = 1;

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(1, Math.floor(rect.width));
      height = Math.max(1, Math.floor(rect.height));
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null;
    resize();
    observer?.observe(canvas);
    window.addEventListener('resize', resize);

    const ring = (cx: number, cy: number, radius: number, widthPx: number, alpha: number, start: number, end: number, color: string) => {
      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.strokeStyle = color;
      ctx.lineWidth = widthPx;
      ctx.shadowBlur = 18;
      ctx.shadowColor = color;
      ctx.beginPath();
      ctx.arc(cx, cy, radius, start, end);
      ctx.stroke();
      ctx.restore();
    };

    const draw = () => {
      frame += 0.016;
      const currentState = stateRef.current;
      const automation = automationRef.current;
      const level = Math.max(0, Math.min(1, audioRef.current));

      ctx.clearRect(0, 0, width, height);

      const bg = ctx.createRadialGradient(width * 0.5, height * 0.52, 20, width * 0.5, height * 0.52, Math.max(width, height) * 0.75);
      bg.addColorStop(0, automation ? 'rgba(40,4,8,0.32)' : 'rgba(2,16,25,0.30)');
      bg.addColorStop(1, 'rgba(0,0,0,0.03)');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, width, height);

      const cx = width * 0.5;
      const cy = height * 0.52;
      const radius = Math.min(width, height) * 0.205;
      const color = automation ? '#ff3030' : currentState === 'thinking' ? '#b46cff' : '#00dcff';
      const speed = currentState === 'thinking' ? 2.5 : currentState === 'listening' ? 0.75 : currentState === 'speaking' ? 1.25 + level * 1.7 : automation ? 0.95 : 0.65;
      const pulse = Math.sin(frame * speed * 3.2) * 2.8 + level * 8;
      const rotation = frame * speed;

      ring(cx, cy, radius + pulse, 2.2, 0.86, 0, Math.PI * 2, color);
      ring(cx, cy, radius + 11 + pulse * 0.45, 1.05, 0.58, rotation * 0.35, rotation * 0.35 + Math.PI * 1.72, color);
      ring(cx, cy, radius + 21, 0.8, 0.42, -rotation * 0.55, -rotation * 0.55 + Math.PI * 1.25, color);

      for (let i = 0; i < 4; i++) {
        const start = rotation * (i % 2 ? -0.7 : 0.45) + i * (Math.PI / 2);
        ring(cx, cy, radius + 31 + (i % 2) * 5, 1.2, 0.55, start, start + Math.PI * 0.22, color);
      }

      ctx.save();
      ctx.translate(cx, cy);
      ctx.strokeStyle = color;
      ctx.globalAlpha = 0.32;
      ctx.lineWidth = 1;
      for (let i = 0; i < 36; i++) {
        const a = (Math.PI * 2 * i) / 36 + rotation * 0.08;
        const r1 = radius + 42;
        const r2 = r1 + (i % 3 === 0 ? 7 : 3);
        ctx.beginPath();
        ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
        ctx.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
        ctx.stroke();
      }
      ctx.restore();

      const coreRadius = 20 + level * 12 + Math.sin(frame * 4) * 1.5;
      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreRadius * 2.8);
      core.addColorStop(0, automation ? 'rgba(255,70,70,0.98)' : 'rgba(200,250,255,0.98)');
      core.addColorStop(0.18, automation ? 'rgba(255,50,50,0.70)' : 'rgba(0,220,255,0.75)');
      core.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = core;
      ctx.beginPath();
      ctx.arc(cx, cy, coreRadius * 2.8, 0, Math.PI * 2);
      ctx.fill();

      ctx.save();
      ctx.translate(cx, cy);
      ctx.strokeStyle = color;
      ctx.lineWidth = currentState === 'listening' || currentState === 'speaking' ? 1.8 : 1.1;
      ctx.globalAlpha = 0.92;
      ctx.shadowBlur = 12;
      ctx.shadowColor = color;
      ctx.beginPath();
      const waveWidth = Math.min(width * 0.32, 360);
      const samples = 120;
      for (let i = 0; i <= samples; i++) {
        const x = -waveWidth / 2 + (waveWidth * i) / samples;
        const nx = i / samples;
        const envelope = Math.pow(Math.sin(Math.PI * nx), 0.72);
        const boost = currentState === 'thinking' ? 1.35 : currentState === 'speaking' ? 1.55 : 1;
        const amp = (5 + level * 20) * envelope * boost;
        const y = Math.sin(nx * 28 + frame * speed * 5.5) * amp + Math.sin(nx * 63 - frame * speed * 8) * amp * 0.25;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.restore();

      animationId = requestAnimationFrame(draw);
    };

    draw();
    return () => {
      cancelAnimationFrame(animationId);
      observer?.disconnect();
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <div className="fixed inset-0 w-full h-full cursor-pointer z-0 overflow-hidden pointer-events-none" onClick={onCanvasClick}>
      <canvas ref={canvasRef} className="block w-full h-full pointer-events-auto" aria-label="JARVIS animated core" />
    </div>
  );
};

import React, { useEffect, useRef } from 'react';
import { JarvisState } from '../types';

interface JarvisCanvasProps {
  state: JarvisState;
  automationMode: boolean;
  audioLevel: number; // 0.0 to 1.0
  onCanvasClick?: () => void;
}

export const JarvisCanvas: React.FC<JarvisCanvasProps> = ({
  state,
  automationMode,
  audioLevel,
  onCanvasClick,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // Smooth uniform interpolation targets
  const targetSpeedRef = useRef<number>(1.2);
  const currentSpeedRef = useRef<number>(1.2);

  const targetAudioRef = useRef<number>(0);
  const currentAudioRef = useRef<number>(0);

  const targetColorRef = useRef<[number, number, number]>([0.0, 0.898, 1.0]);
  const currentColorRef = useRef<[number, number, number]>([0.0, 0.898, 1.0]);

  // Update target values based on state and automationMode
  useEffect(() => {
    // Determine Target Color
    if (automationMode) {
      // RED mode when automation is activated
      targetColorRef.current = [1.0, 0.15, 0.15];
    } else if (state === 'thinking') {
      // Purple / Violet core during deep thinking
      targetColorRef.current = [0.72, 0.35, 1.0];
    } else {
      // Classic JARVIS Cyan
      targetColorRef.current = [0.0, 0.898, 1.0];
    }

    // Determine Target Rotation Speed
    // - thinking: rotate fast
    // - listening: rotate slow
    // - speaking: rotate dynamically with voice
    // - idle: normal speed
    if (state === 'thinking') {
      targetSpeedRef.current = automationMode ? 6.0 : 4.8;
    } else if (state === 'listening') {
      targetSpeedRef.current = 0.5;
    } else if (state === 'speaking') {
      targetSpeedRef.current = 2.4 + audioLevel * 1.5;
    } else {
      // idle
      targetSpeedRef.current = automationMode ? 1.8 : 1.2;
    }
  }, [state, automationMode, audioLevel]);

  useEffect(() => {
    targetAudioRef.current = audioLevel;
  }, [audioLevel]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (!gl) return;

    let animationFrameId: number;

    const syncSize = () => {
      if (!canvas) return;
      const w = canvas.clientWidth || window.innerWidth;
      const h = canvas.clientHeight || window.innerHeight;
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
    };

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(syncSize);
      resizeObserver.observe(canvas);
    }
    syncSize();

    // Vertex Shader
    const vs = `
      attribute vec2 a_position;
      varying vec2 v_texCoord;
      void main() {
        v_texCoord = a_position * 0.5 + 0.5;
        gl_Position = vec4(a_position, 0.0, 1.0);
      }
    `;

    // Fragment Shader
    const fs = `
      precision highp float;
      varying vec2 v_texCoord;
      uniform float u_time;
      uniform vec2 u_resolution;
      uniform vec2 u_mouse;
      uniform float u_speed;
      uniform vec3 u_color;
      uniform float u_automation;
      uniform float u_audio_level;
      uniform float u_state; // 0=idle, 1=listening, 2=thinking, 3=speaking

      // Simplex 2D noise
      vec3 permute(vec3 x) { return mod(((x*34.0)+1.0)*x, 289.0); }
      float snoise(vec2 v){
        const vec4 C = vec4(0.211324865405187, 0.366025403784439,
                 -0.577350269189626, 0.024390243902439);
        vec2 i  = floor(v + dot(v, C.yy) );
        vec2 x0 = v -   i + dot(i, C.xx);
        vec2 i1;
        i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
        vec4 x12 = x0.xyxy + C.xxzz;
        x12.xy -= i1;
        i = mod(i, 289.0);
        vec3 p = permute( permute( i.y + vec3(0.0, i1.y, 1.0 ))
        + i.x + vec3(0.0, i1.x, 1.0 ));
        vec3 m = max(0.5 - vec4(dot(x0,x0), dot(x12.xy,x12.xy),
          dot(x12.zw,x12.zw), 0.0), 0.0);
        m = m*m ;
        m = m*m ;
        vec3 x = 2.0 * fract(p * C.www) - 1.0;
        vec3 h = abs(x) - 0.5;
        vec3 ox = floor(x + 0.5);
        vec3 a0 = x - ox;
        m *= 1.79284291400159 - 0.85373472095314 * ( a0*a0 + h*h );
        vec3 g;
        g.x  = a0.x  * x0.x  + h.x  * x0.y;
        g.yz = a0.yz * x12.xz + h.yz * x12.yw;
        return 130.0 * dot(m, g);
      }

      void main() {
        vec2 uv = v_texCoord;
        vec2 centered_uv = (uv - 0.5) * 2.0;
        centered_uv.x *= u_resolution.x / u_resolution.y;

        float dist = length(centered_uv);
        float angle = atan(centered_uv.y, centered_uv.x);

        // Core Base Color from uniform
        vec3 color = u_color;

        // Dynamic Ring Radii modulation based on state & audio
        float audio_expand = u_audio_level * 0.05;
        float pulse = sin(u_time * (u_speed * 1.5)) * 0.015;

        float r1 = 0.45 + pulse + audio_expand;
        float r2 = 0.47 + pulse * 0.5;
        float r3 = 0.49 - pulse * 0.5;

        // Concentric Rings
        float ring1 = smoothstep(0.008, 0.0, abs(dist - r1));
        float ring2 = smoothstep(0.005, 0.0, abs(dist - r2));
        float ring3 = smoothstep(0.003, 0.0, abs(dist - r3));

        // Rotating ring segments
        // In thinking state (u_state == 2.0) or high speed, segments spin rapidly with opposite direction inner ring
        float rot_dir1 = u_time * u_speed;
        float rot_dir2 = -u_time * u_speed * 0.7;

        float segments1 = step(0.4, sin(angle * 12.0 + rot_dir1));
        float segments2 = step(0.6, cos(angle * 8.0 + rot_dir2));

        float rotating_ring1 = smoothstep(0.012, 0.0, abs(dist - (r1 + 0.06))) * segments1;
        float rotating_ring2 = smoothstep(0.008, 0.0, abs(dist - (r1 - 0.04))) * segments2;

        // Outer tech tick marks (radar notches)
        float ticks = step(0.92, sin(angle * 36.0 + rot_dir1 * 0.2)) * smoothstep(0.004, 0.0, abs(dist - (r1 + 0.09)));

        // Central Waveform Line
        // Wave amplitude scales up when listening or speaking
        float wave_amp = 0.08 + u_audio_level * 0.25;
        if (u_state == 2.0) { // thinking
          wave_amp = 0.15 + sin(u_time * 15.0) * 0.05;
        }

        float wave_freq = 12.0;
        float wave_y = snoise(vec2(centered_uv.x * wave_freq - u_time * (u_speed * 2.0), u_time * 0.5)) * wave_amp;
        
        // Mask wave line inside center horizontal axis
        float wave_mask = step(abs(centered_uv.x), 0.75);
        float wave_line = smoothstep(0.012, 0.0, abs(centered_uv.y - wave_y)) * wave_mask;

        // Secondary harmonic wave line
        float wave_y2 = snoise(vec2(centered_uv.x * 20.0 + u_time * (u_speed * 3.0), u_time)) * (wave_amp * 0.6);
        float wave_line2 = smoothstep(0.006, 0.0, abs(centered_uv.y - wave_y2)) * wave_mask * 0.6;

        // Combine HUD ring layers
        float final_alpha = ring1 * 0.7 + ring2 * 0.5 + ring3 * 0.4 + rotating_ring1 * 0.85 + rotating_ring2 * 0.75 + ticks * 0.9 + wave_line + wave_line2;

        // Luminous Bloom Glow
        float glow_dist = abs(dist - r1);
        vec3 glow = color * (0.025 / max(0.001, glow_dist));

        // Additional center radial core glow
        float center_core = smoothstep(0.2, 0.0, dist) * (0.2 + u_audio_level * 0.3);

        vec3 final_color = color * final_alpha + glow * 0.6 + color * center_core;

        // Automation Warning Glitch Effect (Red Overdrive)
        if (u_automation > 0.5) {
          float glitch_scan = step(0.97, sin(uv.y * 120.0 + u_time * 10.0));
          final_color += vec3(0.5, 0.0, 0.0) * glitch_scan;
        }

        // Atmosphere background (tech grid + noise)
        float bg_noise = snoise(uv * 12.0 + u_time * 0.05) * 0.03;
        vec3 bg_color = (u_automation > 0.5) ? vec3(0.05, 0.005, 0.01) : vec3(0.008, 0.015, 0.025);
        bg_color += bg_noise;

        gl_FragColor = vec4(mix(bg_color, final_color, final_alpha + length(glow) * 0.25), 0.95);
      }
    `;

    const compileShader = (type: number, source: string) => {
      const shader = gl.createShader(type);
      if (!shader) return null;
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error('Shader compilation error:', gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
      }
      return shader;
    };

    const vertShader = compileShader(gl.VERTEX_SHADER, vs);
    const fragShader = compileShader(gl.FRAGMENT_SHADER, fs);
    if (!vertShader || !fragShader) return;

    const prog = gl.createProgram();
    if (!prog) return;
    gl.attachShader(prog, vertShader);
    gl.attachShader(prog, fragShader);
    gl.linkProgram(prog);

    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      console.error('Program link error:', gl.getProgramInfoLog(prog));
      return;
    }

    gl.useProgram(prog);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
      gl.STATIC_DRAW
    );

    const posAttr = gl.getAttribLocation(prog, 'a_position');
    gl.enableVertexAttribArray(posAttr);
    gl.vertexAttribPointer(posAttr, 2, gl.FLOAT, false, 0, 0);

    const uTime = gl.getUniformLocation(prog, 'u_time');
    const uRes = gl.getUniformLocation(prog, 'u_resolution');
    const uMouse = gl.getUniformLocation(prog, 'u_mouse');
    const uSpeed = gl.getUniformLocation(prog, 'u_speed');
    const uColor = gl.getUniformLocation(prog, 'u_color');
    const uAutomation = gl.getUniformLocation(prog, 'u_automation');
    const uAudioLevel = gl.getUniformLocation(prog, 'u_audio_level');
    const uState = gl.getUniformLocation(prog, 'u_state');

    let mousePos = { x: canvas.width / 2, y: canvas.height / 2 };

    const handleMouseMove = (e: MouseEvent) => {
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      if (rect.width && rect.height) {
        const nx = (e.clientX - rect.left) / rect.width;
        const ny = 1.0 - (e.clientY - rect.top) / rect.height;
        mousePos.x = nx * canvas.width;
        mousePos.y = ny * canvas.height;
      }
    };

    window.addEventListener('mousemove', handleMouseMove);

    let startTime = performance.now();

    const render = () => {
      const now = performance.now();
      const elapsedSeconds = (now - startTime) * 0.001;

      // Smoothly interpolate current uniforms towards targets
      currentSpeedRef.current += (targetSpeedRef.current - currentSpeedRef.current) * 0.08;
      currentAudioRef.current += (targetAudioRef.current - currentAudioRef.current) * 0.12;

      currentColorRef.current = [
        currentColorRef.current[0] + (targetColorRef.current[0] - currentColorRef.current[0]) * 0.08,
        currentColorRef.current[1] + (targetColorRef.current[1] - currentColorRef.current[1]) * 0.08,
        currentColorRef.current[2] + (targetColorRef.current[2] - currentColorRef.current[2]) * 0.08,
      ];

      syncSize();
      gl.viewport(0, 0, canvas.width, canvas.height);

      if (uTime) gl.uniform1f(uTime, elapsedSeconds);
      if (uRes) gl.uniform2f(uRes, canvas.width, canvas.height);
      if (uMouse) gl.uniform2f(uMouse, mousePos.x, mousePos.y);
      if (uSpeed) gl.uniform1f(uSpeed, currentSpeedRef.current);
      if (uColor) gl.uniform3f(uColor, currentColorRef.current[0], currentColorRef.current[1], currentColorRef.current[2]);
      if (uAutomation) gl.uniform1f(uAutomation, automationMode ? 1.0 : 0.0);
      if (uAudioLevel) gl.uniform1f(uAudioLevel, currentAudioRef.current);

      let stateVal = 0.0;
      if (state === 'listening') stateVal = 1.0;
      else if (state === 'thinking') stateVal = 2.0;
      else if (state === 'speaking') stateVal = 3.0;

      if (uState) gl.uniform1f(uState, stateVal);

      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('mousemove', handleMouseMove);
      if (resizeObserver) resizeObserver.disconnect();
    };
  }, [automationMode, state]);

  return (
    <div
      className="fixed inset-0 w-full h-full cursor-pointer z-0 overflow-hidden"
      onClick={onCanvasClick}
    >
      <canvas
        ref={canvasRef}
        className="block w-full h-full pointer-events-auto"
      />
    </div>
  );
};

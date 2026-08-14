export type JarvisState = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

export interface AutomationTask {
  id: string;
  name: string;
  category: string;
  status: 'idle' | 'running' | 'completed' | 'error';
  progress: number; // 0 to 100
  logs: string[];
}

export interface SystemMetrics {
  fps: number;
  cpuUsage: number;
  memoryMB: number;
  temp: number;
  neuralNodes: number;
  audioInputLevel: number;
}

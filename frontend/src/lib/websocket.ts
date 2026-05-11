export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface GazePayload {
  type: 'gaze';
  ts: number;
  x: number;
  y: number;
}

interface AckPayload {
  type: 'ack';
  ts: number;
  frame_size: number;
}

type ServerMessage = GazePayload | AckPayload;

type GazeHandler = (payload: GazePayload) => void;
type StatusHandler = (status: ConnectionStatus) => void;

const INITIAL_RETRY_MS = 1_000;
const MAX_RETRY_MS = 30_000;
const WS_BASE = 'ws://localhost:8000';

class GazeWebSocket {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private retryDelay = INITIAL_RETRY_MS;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private alive = false;

  private onGaze?: GazeHandler;
  private onStatus?: StatusHandler;

  constructor(sessionId: string) {
    this.sessionId = sessionId;
  }

  connect(onGaze: GazeHandler, onStatus: StatusHandler): void {
    this.onGaze = onGaze;
    this.onStatus = onStatus;
    this.alive = true;
    this.open();
  }

  private open(): void {
    this.onStatus?.('connecting');

    const w = typeof window !== 'undefined' ? window.innerWidth : 1920;
    const h = typeof window !== 'undefined' ? window.innerHeight : 1080;
    const ws = new WebSocket(`${WS_BASE}/ws/gaze/${this.sessionId}?w=${w}&h=${h}`);
    ws.binaryType = 'arraybuffer';
    this.ws = ws;

    ws.onopen = () => {
      this.retryDelay = INITIAL_RETRY_MS;
      this.onStatus?.('connected');
    };

    ws.onmessage = (evt: MessageEvent) => {
      if (typeof evt.data !== 'string') return;
      try {
        const msg = JSON.parse(evt.data) as ServerMessage;
        if (msg.type === 'gaze') {
          this.onGaze?.(msg);
        }
      } catch {
        // ignore malformed JSON
      }
    };

    ws.onclose = () => {
      this.onStatus?.('disconnected');
      if (this.alive) this.scheduleReconnect();
    };

    ws.onerror = () => {
      this.onStatus?.('error');
    };
  }

  private scheduleReconnect(): void {
    const delay = this.retryDelay;
    this.retryDelay = Math.min(this.retryDelay * 2, MAX_RETRY_MS);
    this.retryTimer = setTimeout(() => {
      if (this.alive) this.open();
    }, delay);
  }

  sendFrame(blob: Blob): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(blob);
    }
  }

  disconnect(): void {
    this.alive = false;
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }
}

let singleton: GazeWebSocket | null = null;

export function getGazeSocket(sessionId: string): GazeWebSocket {
  if (!singleton) singleton = new GazeWebSocket(sessionId);
  return singleton;
}

export function destroyGazeSocket(): void {
  singleton?.disconnect();
  singleton = null;
}

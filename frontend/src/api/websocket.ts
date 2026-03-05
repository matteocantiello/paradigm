import type { ClientMessage, ServerMessage } from "./ws-types";

export type ConnectionStatus = "disconnected" | "connecting" | "connected" | "reconnecting";

export interface WebSocketCallbacks {
  onMessage: (msg: ServerMessage) => void;
  onStatusChange: (status: ConnectionStatus) => void;
}

const BASE_DELAY = 1000;
const MAX_DELAY = 30_000;
const HEARTBEAT_INTERVAL = 30_000; // Send ping every 30s

export class ParadigmWebSocket {
  private ws: WebSocket | null = null;
  private callbacks: WebSocketCallbacks;
  private sessionId: string | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private intentionalClose = false;

  constructor(callbacks: WebSocketCallbacks) {
    this.callbacks = callbacks;
  }

  connect(sessionId: string) {
    this.sessionId = sessionId;
    this.intentionalClose = false;
    this.reconnectAttempts = 0;
    this._connect();
  }

  disconnect() {
    this.intentionalClose = true;
    this._stopHeartbeat();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close(1000);
      this.ws = null;
    }
    this.callbacks.onStatusChange("disconnected");
  }

  send(msg: ClientMessage) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  get status(): ConnectionStatus {
    if (!this.ws) return "disconnected";
    switch (this.ws.readyState) {
      case WebSocket.CONNECTING:
        return "connecting";
      case WebSocket.OPEN:
        return "connected";
      default:
        return "disconnected";
    }
  }

  private _connect() {
    if (!this.sessionId) return;

    const wsBase =
      import.meta.env.VITE_WS_BASE_URL ??
      `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.hostname}:8000`;
    // Include API key as query param for WebSocket auth
    const apiKey = localStorage.getItem("paradigm_api_key");
    const authQuery = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : "";
    const url = `${wsBase}/api/v1/sessions/${this.sessionId}/ws${authQuery}`;

    this.callbacks.onStatusChange(
      this.reconnectAttempts > 0 ? "reconnecting" : "connecting"
    );

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.callbacks.onStatusChange("connected");
      this._startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        // Silently consume server pong responses
        if (msg.type === "pong") return;
        this.callbacks.onMessage(msg as ServerMessage);
      } catch {
        console.error("Failed to parse WS message:", event.data);
      }
    };

    this.ws.onclose = (event) => {
      this.ws = null;
      this._stopHeartbeat();
      if (this.intentionalClose || event.code === 4004) {
        this.callbacks.onStatusChange("disconnected");
        return;
      }
      this._scheduleReconnect();
    };

    this.ws.onerror = () => {
      // onclose will fire after onerror
    };
  }

  private _startHeartbeat() {
    this._stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping" }));
      }
    }, HEARTBEAT_INTERVAL);
  }

  private _stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private _scheduleReconnect() {
    // Always reconnect — no attempt limit. Backoff caps at 30s.
    this.callbacks.onStatusChange("reconnecting");
    const delay = Math.min(MAX_DELAY, BASE_DELAY * Math.pow(2, this.reconnectAttempts));
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this._connect();
    }, delay);
  }
}

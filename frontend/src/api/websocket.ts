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
  // Returning to a backgrounded tab reconnects IMMEDIATELY (throttled timers
  // may have let the connection lapse and delayed the scheduled reconnect).
  private onVisible = () => {
    if (document.visibilityState !== "visible") return;
    if (this.intentionalClose || !this.sessionId || this.ws) return;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.reconnectAttempts = 0;
    this._connect();
  };

  constructor(callbacks: WebSocketCallbacks) {
    this.callbacks = callbacks;
    document.addEventListener("visibilitychange", this.onVisible);
  }

  connect(sessionId: string) {
    this.sessionId = sessionId;
    this.intentionalClose = false;
    this.reconnectAttempts = 0;
    this._connect();
  }

  disconnect() {
    this.intentionalClose = true;
    document.removeEventListener("visibilitychange", this.onVisible);
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

    // Default to the SAME origin (no hardcoded :8000) so it works behind a
    // reverse proxy in production — Caddy proxies /api/* incl. the WS. Dev
    // overrides this with VITE_WS_BASE_URL=ws://localhost:8000 (.env.development).
    const wsBase =
      import.meta.env.VITE_WS_BASE_URL ||
      `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
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
      // Terminal close codes must NOT trigger reconnects: 4001 unauthorized
      // (would 403-loop forever), 4004 session not found. Everything else —
      // including 1000 — reconnects: the server closes IDLE connections with
      // 1000 when a backgrounded tab's throttled timers stop the heartbeat,
      // and treating that as final left the UI permanently frozen while the
      // run continued. Deliberate client closes are covered by intentionalClose.
      const TERMINAL_CLOSE_CODES = [4001, 4004];
      if (this.intentionalClose || TERMINAL_CLOSE_CODES.includes(event.code)) {
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

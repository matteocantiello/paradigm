import type { Ev } from "./types";

export interface ThreadSummary {
  id: string;
  title: string;
  status: string;
  date: string | null;
  n_events: number;
}

export async function fetchThreads(): Promise<ThreadSummary[]> {
  const res = await fetch("/api/threads");
  if (!res.ok) throw new Error(`threads: HTTP ${res.status}`);
  return res.json();
}

export async function fetchEvents(threadId: string): Promise<Ev[]> {
  const res = await fetch(`/api/threads/${encodeURIComponent(threadId)}/events`);
  if (!res.ok) throw new Error(`events: HTTP ${res.status}`);
  const events: Ev[] = await res.json();
  events.sort((a, b) => a.seq - b.seq);
  return events;
}

export function artifactUrl(threadId: string, path: string): string {
  return `/api/threads/${encodeURIComponent(threadId)}/artifacts/${path}`;
}

/** Live data source (SSE). onEvent receives events in arrival order. */
export function openEventStream(
  threadId: string,
  onEvent: (e: Ev) => void,
  onEnd?: () => void,
): () => void {
  const es = new EventSource(`/api/threads/${encodeURIComponent(threadId)}/stream`);
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data));
    } catch {
      // skip malformed line
    }
  };
  es.addEventListener("end", () => {
    es.close();
    onEnd?.();
  });
  return () => es.close();
}

import { useEffect, useRef, useState } from "react";
import { fetchEvents, openEventStream } from "./api";
import type { Ev } from "./types";

export type ConnState = "connecting" | "live" | "ended" | "error";

/**
 * Live event source: seeds from the events array (so a reload mid-run recovers
 * full state), then tails via SSE. Dedupes by seq, keeps the list sorted.
 */
export function useLiveEvents(threadId: string): { events: Ev[]; conn: ConnState } {
  const [events, setEvents] = useState<Ev[]>([]);
  const [conn, setConn] = useState<ConnState>("connecting");
  const seenRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    let closed = false;
    seenRef.current = new Set();
    setEvents([]);
    setConn("connecting");

    const push = (incoming: Ev[]) => {
      const fresh = incoming.filter((e) => !seenRef.current.has(e.seq));
      if (fresh.length === 0) return;
      for (const e of fresh) seenRef.current.add(e.seq);
      setEvents((prev) => {
        const next = prev.concat(fresh);
        next.sort((a, b) => a.seq - b.seq);
        return next;
      });
    };

    // Seed with the current full history, THEN tail (SSE replays from start too,
    // but the dedupe makes the overlap harmless and the snapshot makes first
    // paint instant rather than waiting on the stream).
    fetchEvents(threadId)
      .then((seed) => {
        if (closed) return;
        push(seed);
      })
      .catch(() => {
        /* SSE will still deliver */
      });

    const close = openEventStream(
      threadId,
      (e) => {
        if (closed) return;
        push([e]);
        setConn("live");
      },
      () => {
        if (!closed) setConn("ended");
      },
    );

    return () => {
      closed = true;
      close();
    };
  }, [threadId]);

  return { events, conn };
}

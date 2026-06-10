import { useEffect, useMemo, useRef, useState } from "react";
import { applyEvent, buildState, initialState } from "./reducer";
import type { DashboardState, Ev } from "./types";

/**
 * Dashboard state at `cursor` (number of events applied).
 * Forward movement applies incrementally; backward seeks rebuild from zero
 * (cheap: a 1-hour run is a few thousand events).
 */
export function useReplayState(events: Ev[], cursor: number): DashboardState {
  const cacheRef = useRef<{ events: Ev[]; cursor: number; state: DashboardState } | null>(null);

  return useMemo(() => {
    const cache = cacheRef.current;
    if (!cache || cache.events !== events || cursor < cache.cursor) {
      const state = buildState(events, cursor);
      cacheRef.current = { events, cursor, state };
    } else {
      for (let i = cache.cursor; i < cursor && i < events.length; i++) {
        applyEvent(cache.state, events[i]);
      }
      cache.cursor = cursor;
    }
    // New top-level identity so React re-renders; inner collections are shared.
    return { ...cacheRef.current!.state };
  }, [events, cursor]);
}

/** Cumulative virtual-time offsets (ms) with long idle gaps clamped. */
function buildTimeline(events: Ev[], maxGapMs = 15_000): number[] {
  const timeline: number[] = new Array(events.length);
  let acc = 0;
  let prev: number | null = null;
  for (let i = 0; i < events.length; i++) {
    const t = Date.parse(events[i].ts);
    if (prev !== null && Number.isFinite(t)) {
      acc += Math.min(Math.max(t - prev, 0), maxGapMs);
    }
    if (Number.isFinite(t)) prev = t;
    timeline[i] = acc;
  }
  return timeline;
}

export interface Playback {
  cursor: number;
  playing: boolean;
  speed: number;
  atEnd: boolean;
  play: () => void;
  pause: () => void;
  setSpeed: (s: number) => void;
  seek: (cursor: number) => void;
}

/** Timestamp-paced playback over the event list (replay mode). */
export function usePlayback(events: Ev[], initialCursor?: number): Playback {
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(5);
  const timeline = useMemo(() => buildTimeline(events), [events]);
  const clockRef = useRef(0); // virtual ms elapsed
  const speedRef = useRef(speed);
  speedRef.current = speed;

  // Jump straight to a deep-linked position (or the end for finished threads)
  useEffect(() => {
    const start = Math.min(initialCursor ?? events.length, events.length);
    setCursor(start);
    clockRef.current = start > 0 ? (timeline[start - 1] ?? 0) : 0;
    setPlaying(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      clockRef.current += (now - last) * speedRef.current;
      last = now;
      setCursor((c) => {
        let next = c;
        while (next < events.length && timeline[next] <= clockRef.current) next++;
        return next;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, events, timeline]);

  useEffect(() => {
    if (cursor >= events.length && playing) setPlaying(false);
  }, [cursor, events.length, playing]);

  return {
    cursor,
    playing,
    speed,
    atEnd: cursor >= events.length,
    play: () => {
      if (cursor >= events.length) {
        clockRef.current = 0;
        setCursor(0);
      }
      setPlaying(true);
    },
    pause: () => setPlaying(false),
    setSpeed,
    seek: (c: number) => {
      const clamped = Math.max(0, Math.min(c, events.length));
      setCursor(clamped);
      clockRef.current = clamped > 0 ? (timeline[clamped - 1] ?? 0) : 0;
    },
  };
}

export { initialState };

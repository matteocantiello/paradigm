import type { Playback } from "@/lib/replay/engine";
import type { Ev } from "@/lib/replay/types";
import { useMemo } from "react";

const SPEEDS = [1, 5, 20, 60];

/** Transport controls: << step back · play/pause · step forward >> + timeline + speed. */
export function ReplayScrubber({ events, playback }: { events: Ev[]; playback: Playback }) {
  const marks = useMemo(() => {
    const out: { idx: number; kind: "phase" | "debate" }[] = [];
    events.forEach((e, i) => {
      if (e.type === "phase.started") out.push({ idx: i, kind: "phase" });
      if (e.type === "debate.started") out.push({ idx: i, kind: "debate" });
    });
    return out;
  }, [events]);

  const cur = playback.cursor > 0 ? events[Math.min(playback.cursor, events.length) - 1] : null;
  const btn =
    "flex h-8 min-w-9 items-center justify-center rounded-md border border-border bg-card text-sm text-foreground transition-colors hover:border-primary hover:text-primary disabled:opacity-40";

  return (
    <footer className="flex items-center gap-3 border-t border-border bg-background px-4 py-2.5">
      <button
        className={btn}
        title="Step back"
        onClick={() => playback.seek(playback.cursor - 1)}
        disabled={playback.cursor <= 0}
      >
        ⏮
      </button>
      <button
        className={btn}
        title={playback.playing ? "Pause" : "Play"}
        onClick={playback.playing ? playback.pause : playback.play}
      >
        {playback.playing ? "⏸" : "▶"}
      </button>
      <button
        className={btn}
        title="Step forward"
        onClick={() => playback.seek(playback.cursor + 1)}
        disabled={playback.cursor >= events.length}
      >
        ⏭
      </button>
      <select
        className="h-8 rounded-md border border-border bg-card px-2 text-xs text-foreground"
        value={playback.speed}
        onChange={(e) => playback.setSpeed(Number(e.target.value))}
        title="Playback speed"
      >
        {SPEEDS.map((s) => (
          <option key={s} value={s}>
            {s}×
          </option>
        ))}
      </select>
      <div className="relative flex h-8 flex-1 items-center">
        <div className="pointer-events-none absolute inset-0">
          {events.length > 0 &&
            marks.map((m, i) => (
              <span
                key={i}
                className={`absolute top-2 h-4 w-0.5 rounded ${
                  m.kind === "phase" ? "bg-accent-cyan/60" : "bg-primary"
                }`}
                style={{ left: `${(m.idx / events.length) * 100}%` }}
              />
            ))}
        </div>
        <input
          type="range"
          className="relative z-10 w-full accent-[var(--primary)]"
          min={0}
          max={events.length}
          value={playback.cursor}
          onChange={(e) => playback.seek(Number(e.target.value))}
        />
      </div>
      <span className="min-w-28 text-right text-xs tabular-nums text-muted-foreground">
        {cur ? `seq ${cur.seq}` : "start"} / {events.length}
      </span>
    </footer>
  );
}

import { useMemo, useState } from "react";
import type { Playback } from "../replay";
import type { Ev } from "../types";

const SPEEDS = [1, 5, 20, 60];

export function Scrubber({
  events,
  playback,
  shareable,
}: {
  events: Ev[];
  playback: Playback;
  shareable?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const marks = useMemo(() => {
    const out: { idx: number; kind: "phase" | "debate" }[] = [];
    events.forEach((e, i) => {
      if (e.type === "phase.started") out.push({ idx: i, kind: "phase" });
      if (e.type === "debate.started") out.push({ idx: i, kind: "debate" });
    });
    return out;
  }, [events]);

  const cur = playback.cursor > 0 ? events[Math.min(playback.cursor, events.length) - 1] : null;

  return (
    <footer className="scrubber">
      <button
        className="scrub-btn"
        onClick={playback.playing ? playback.pause : playback.play}
        title={playback.playing ? "Pause" : "Play"}
      >
        {playback.playing ? "⏸" : "▶"}
      </button>
      <select
        className="speed-select"
        value={playback.speed}
        onChange={(e) => playback.setSpeed(Number(e.target.value))}
      >
        {SPEEDS.map((s) => (
          <option key={s} value={s}>
            {s}×
          </option>
        ))}
      </select>
      <div className="timeline">
        <div className="marks">
          {events.length > 0 &&
            marks.map((m, i) => (
              <span
                key={i}
                className={`mark ${m.kind}`}
                style={{ left: `${(m.idx / events.length) * 100}%` }}
              />
            ))}
        </div>
        <input
          type="range"
          min={0}
          max={events.length}
          value={playback.cursor}
          onChange={(e) => playback.seek(Number(e.target.value))}
        />
      </div>
      <span className="scrub-pos">
        {cur ? `seq ${cur.seq}` : "start"} / {events.length}
      </span>
      {shareable && (
        <button
          className="scrub-btn"
          style={{ width: "auto", padding: "0 10px" }}
          title="Copy a link to this exact moment"
          onClick={() => {
            const url = new URL(window.location.href);
            if (cur) url.searchParams.set("t", String(cur.seq));
            else url.searchParams.delete("t");
            window.history.replaceState({}, "", url);
            navigator.clipboard?.writeText(url.toString()).catch(() => {});
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          }}
        >
          {copied ? "✓ copied" : "🔗 share"}
        </button>
      )}
    </footer>
  );
}

import { useEffect, useRef } from "react";

// Field accents for the generated cover, hue-matched to the topic pills.
const TOPIC_ACCENT: Record<string, string> = {
  astro: "#8b8ff0",
  physics: "#6ea8ff",
  cs: "#5fd0a8",
  math: "#d488e0",
  stat: "#e3b463",
  bio: "#6bd08a",
  med: "#f08a9a",
  econ: "#5fcbc0",
  eess: "#7fd6e3",
  other: "#9aa0c0",
};

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(a: number): () => number {
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Procedural cover for a paper with no thumbnail-worthy figure — a flowing
 * "envelope/field" of contour lines + scattered sample points, deterministic
 * from the paper id and tinted by its field. Evokes data without faking a
 * specific result. Canvas over hand-authored SVG, per the design guidance.
 */
export function GeneratedCover({ seed, topic }: { seed: string; topic?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const accent = TOPIC_ACCENT[topic ?? "other"] ?? TOPIC_ACCENT.other;

  useEffect(() => {
    const cv = ref.current;
    if (!cv) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = cv.clientWidth || 300;
    const h = cv.clientHeight || 188;
    cv.width = w * dpr;
    cv.height = h * dpr;
    const x = cv.getContext("2d");
    if (!x) return;
    x.scale(dpr, dpr);
    const rnd = mulberry32(hash(seed));

    const g = x.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "#161a2e");
    g.addColorStop(1, "#0b0e1c");
    x.fillStyle = g;
    x.fillRect(0, 0, w, h);

    x.strokeStyle = accent;
    x.globalAlpha = 0.06;
    x.lineWidth = 1;
    for (let i = 1; i < 6; i++) {
      x.beginPath();
      x.moveTo((i * w) / 6, 0);
      x.lineTo((i * w) / 6, h);
      x.stroke();
    }
    for (let i = 1; i < 4; i++) {
      x.beginPath();
      x.moveTo(0, (i * h) / 4);
      x.lineTo(w, (i * h) / 4);
      x.stroke();
    }

    const lines = 5 + Math.floor(rnd() * 3);
    for (let l = 0; l < lines; l++) {
      const amp = h * (0.06 + rnd() * 0.16);
      const ph = rnd() * Math.PI * 2;
      const freq = 0.8 + rnd() * 1.7;
      const base = h * (0.2 + (0.62 * l) / lines);
      x.beginPath();
      for (let px = 0; px <= w; px += 6) {
        const y = base + Math.sin(((px / w) * Math.PI * freq * 2) + ph) * amp * (1 - (px / w) * 0.3);
        if (px === 0) x.moveTo(px, y);
        else x.lineTo(px, y);
      }
      x.globalAlpha = 0.1 + 0.1 * (l / lines);
      x.strokeStyle = accent;
      x.lineWidth = 1.4;
      x.stroke();
    }

    const n = reduce ? 60 : 90 + Math.floor(rnd() * 60);
    for (let i = 0; i < n; i++) {
      const px = rnd() * w;
      const py = h * (0.15 + rnd() * 0.8);
      const key = rnd() < 0.12;
      x.globalAlpha = key ? 0.9 : 0.28;
      x.fillStyle = key ? accent : "#c8ccea";
      x.beginPath();
      x.arc(px, py, key ? 2.1 : 1.1, 0, 7);
      x.fill();
      if (key) {
        x.globalAlpha = 0.18;
        x.beginPath();
        x.arc(px, py, 5.5, 0, 7);
        x.fill();
      }
    }
    x.globalAlpha = 1;
  }, [seed, accent]);

  return <canvas ref={ref} className="h-full w-full" aria-hidden="true" />;
}

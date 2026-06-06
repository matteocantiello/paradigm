import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toString();
}

export function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + "..." : s;
}

/**
 * "Authors (Year)" byline that degrades gracefully — never renders a bare "(?)".
 * Some providers (e.g. alphaXiv listings) return papers without author names or a
 * year; show whatever we have, or nothing.
 */
export function formatByline(authors: string | string[], year?: string): string {
  const a = (Array.isArray(authors) ? authors.join(", ") : authors || "").trim();
  const y = (year || "").trim();
  const hasYear = y !== "" && y !== "?";
  if (a && hasYear) return `${a} (${y})`;
  if (a) return a;
  if (hasYear) return `(${y})`;
  return "";
}

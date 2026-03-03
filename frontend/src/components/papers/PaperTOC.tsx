import { useMemo } from "react";
import { cn } from "@/lib/utils";

interface TocEntry {
  id: string;
  text: string;
  level: number;
}

interface PaperTOCProps {
  body: string;
}

export function PaperTOC({ body }: PaperTOCProps) {
  const entries = useMemo(() => {
    const result: TocEntry[] = [];
    const lines = body.split("\n");
    for (const line of lines) {
      const match = line.match(/^(#{2,3})\s+(.+)/);
      if (match) {
        const level = match[1].length;
        const text = match[2].trim();
        const id = text
          .toLowerCase()
          .replace(/[^\w\s-]/g, "")
          .replace(/\s+/g, "-");
        result.push({ id, text, level });
      }
    }
    return result;
  }, [body]);

  if (entries.length === 0) return null;

  const scrollTo = (id: string) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <nav className="space-y-0.5">
      <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
        Contents
      </h3>
      {entries.map((entry, i) => (
        <button
          key={i}
          onClick={() => scrollTo(entry.id)}
          className={cn(
            "block w-full text-left text-xs py-1 hover:text-foreground transition-colors truncate",
            entry.level === 2
              ? "text-muted-foreground pl-0"
              : "text-muted-foreground/70 pl-3"
          )}
        >
          {entry.text}
        </button>
      ))}
    </nav>
  );
}

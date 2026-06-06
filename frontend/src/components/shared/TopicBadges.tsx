import { TOPIC_COLORS, TOPIC_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface TopicBadgesProps {
  topics?: string[] | null;
  className?: string;
  /** Compact pills (used in dense list cards). */
  size?: "sm" | "xs";
}

/**
 * Colored pills for a research item's broad fields (arXiv-style). Multiple badges
 * signal cross-disciplinary work ("Econ + Astro") — cross-pollination is a feature.
 * Renders nothing when there are no topics, so callers can drop it in unconditionally.
 */
export function TopicBadges({ topics, className, size = "sm" }: TopicBadgesProps) {
  const list = (topics ?? []).filter(Boolean);
  if (list.length === 0) return null;

  const pad = size === "xs" ? "px-1.5 py-0 text-[10px]" : "px-2 py-0.5 text-[11px]";

  return (
    <div className={cn("flex flex-wrap items-center gap-1", className)}>
      {list.map((topic) => {
        const color = TOPIC_COLORS[topic] ?? TOPIC_COLORS.other;
        const label = TOPIC_LABELS[topic] ?? topic;
        return (
          <span
            key={topic}
            className={cn(
              "inline-flex items-center rounded-full border font-medium leading-none",
              pad,
              color
            )}
            title={`Field: ${label}`}
          >
            {label}
          </span>
        );
      })}
    </div>
  );
}

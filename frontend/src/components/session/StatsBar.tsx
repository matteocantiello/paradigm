import { Clock, FileText, Search, Coins, RotateCw } from "lucide-react";
import { formatElapsed, formatTokens } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface StatsBarProps {
  roundNum: number;
  maxRounds: number;
  papersFound: number;
  totalSearches: number;
  totalTokens: number;
  elapsedSeconds: number;
  onPapersClick?: () => void;
}

export function StatsBar({
  roundNum,
  maxRounds,
  papersFound,
  totalSearches,
  totalTokens,
  elapsedSeconds,
  onPapersClick,
}: StatsBarProps) {
  const stats = [
    { icon: RotateCw, label: "Round", value: `${roundNum}/${maxRounds}` },
    { icon: FileText, label: "Papers", value: String(papersFound), clickable: true },
    { icon: Search, label: "Searches", value: String(totalSearches) },
    { icon: Coins, label: "Tokens", value: formatTokens(totalTokens) },
    { icon: Clock, label: "Elapsed", value: formatElapsed(elapsedSeconds) },
  ];

  return (
    <div className="flex items-center gap-0 px-3 py-2 border-b border-border">
      {stats.map(({ icon: Icon, label, value, clickable }, idx) => {
        const isClickable = clickable && papersFound > 0 && onPapersClick;

        const content = (
          <div className="flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg bg-card/50 backdrop-blur-sm">
            <Icon className="h-3.5 w-3.5 text-muted-foreground" />
            <span className={cn(
              "text-sm font-semibold tabular-nums text-primary",
              isClickable && "bg-primary/10 px-2 rounded-full cursor-pointer hover:bg-primary/20 transition-colors"
            )}>
              {value}
            </span>
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</span>
          </div>
        );

        return (
          <div key={label} className="flex items-center">
            {idx > 0 && <span className="mx-1 h-6 w-px bg-border" />}
            {isClickable ? (
              <button onClick={onPapersClick} className="transition-colors">
                {content}
              </button>
            ) : (
              content
            )}
          </div>
        );
      })}
    </div>
  );
}

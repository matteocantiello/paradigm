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
    <div className="flex items-center gap-1 px-3 py-1.5 text-xs text-muted-foreground border-b border-border">
      {stats.map(({ icon: Icon, label, value, clickable }, idx) => {
        const isClickable = clickable && papersFound > 0 && onPapersClick;

        const content = (
          <>
            <Icon className="h-3 w-3" />
            <span className={cn(
              "font-medium text-foreground",
              isClickable && "bg-indigo-500/20 text-indigo-300 px-1.5 rounded-full"
            )}>
              {value}
            </span>
            <span>{label}</span>
          </>
        );

        return (
          <div key={label} className="flex items-center">
            {idx > 0 && (
              <span className="mx-2 h-3 w-px bg-border" />
            )}
            {isClickable ? (
              <button
                onClick={onPapersClick}
                className="flex items-center gap-1 hover:text-foreground transition-colors cursor-pointer"
              >
                {content}
              </button>
            ) : (
              <div className="flex items-center gap-1">
                {content}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

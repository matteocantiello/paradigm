import { Clock, FileText, Search, Coins, RotateCw } from "lucide-react";
import { formatElapsed, formatTokens } from "@/lib/utils";

interface StatsBarProps {
  roundNum: number;
  maxRounds: number;
  papersFound: number;
  totalSearches: number;
  totalTokens: number;
  elapsedSeconds: number;
}

export function StatsBar({
  roundNum,
  maxRounds,
  papersFound,
  totalSearches,
  totalTokens,
  elapsedSeconds,
}: StatsBarProps) {
  const stats = [
    { icon: RotateCw, label: "Round", value: `${roundNum}/${maxRounds}` },
    { icon: FileText, label: "Papers", value: String(papersFound) },
    { icon: Search, label: "Searches", value: String(totalSearches) },
    { icon: Coins, label: "Tokens", value: formatTokens(totalTokens) },
    { icon: Clock, label: "Elapsed", value: formatElapsed(elapsedSeconds) },
  ];

  return (
    <div className="flex items-center gap-4 px-3 py-1.5 text-xs text-muted-foreground border-b border-border">
      {stats.map(({ icon: Icon, label, value }) => (
        <div key={label} className="flex items-center gap-1">
          <Icon className="h-3 w-3" />
          <span className="font-medium text-foreground">{value}</span>
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}

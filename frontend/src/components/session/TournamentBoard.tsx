import type { KnowledgeState } from "@/stores/sessionStore";
import { HYPOTHESIS_STATUS_COLORS } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface TournamentBoardProps {
  knowledge: KnowledgeState;
}

type Standing = {
  id: string;
  statement: string;
  elo: number;
  status: string;
  rank: number;
  wins: number;
  losses: number;
  delta: number | null; // Elo change since the previous update (null = newcomer)
};

const ELO_MIN = 1000;
const ELO_MAX = 2000;
const MAX_MATCHUPS = 12;

/** Build Elo-ranked standings with W–L records and per-hypothesis movement. */
function buildStandings(knowledge: KnowledgeState): Standing[] {
  const { tournamentRankings, hypotheses, matchupResults, previousElo } = knowledge;

  // Prefer the explicit tournament rankings; fall back to Elo-rated hypotheses.
  const base =
    tournamentRankings.length > 0
      ? tournamentRankings.map((r) => ({
          id: r.hypothesis_id,
          statement: r.statement,
          elo: r.elo_rating,
          status: r.status,
        }))
      : hypotheses
          .filter((h) => h.elo_rating != null)
          .map((h) => ({
            id: h.id,
            statement: h.statement,
            elo: h.elo_rating ?? 0,
            status: h.status,
          }));

  // Win/loss tallies from head-to-head matchups.
  const wins: Record<string, number> = {};
  const losses: Record<string, number> = {};
  for (const m of matchupResults) {
    const { hypothesis_a_id: a, hypothesis_b_id: b, winner_id: w } = m;
    if (w === a) {
      wins[a] = (wins[a] ?? 0) + 1;
      losses[b] = (losses[b] ?? 0) + 1;
    } else if (w === b) {
      wins[b] = (wins[b] ?? 0) + 1;
      losses[a] = (losses[a] ?? 0) + 1;
    }
  }

  return [...base]
    .sort((x, y) => y.elo - x.elo)
    .map((s, i) => {
      const prev = previousElo[s.id];
      return {
        ...s,
        rank: i + 1,
        wins: wins[s.id] ?? 0,
        losses: losses[s.id] ?? 0,
        delta: prev == null ? null : Math.round(s.elo - prev),
      };
    });
}

function Movement({ delta }: { delta: number | null }) {
  if (delta == null) {
    return <span className="text-[9px] text-sky-400/80 font-medium">new</span>;
  }
  if (delta > 0) {
    return (
      <span className="text-[9px] text-emerald-400 font-medium tabular-nums">▲{delta}</span>
    );
  }
  if (delta < 0) {
    return (
      <span className="text-[9px] text-red-400 font-medium tabular-nums">▼{Math.abs(delta)}</span>
    );
  }
  return <span className="text-[9px] text-muted-foreground/60">=</span>;
}

function EloMeter({ elo }: { elo: number }) {
  const pct = Math.max(0, Math.min(100, ((elo - ELO_MIN) / (ELO_MAX - ELO_MIN)) * 100));
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-14 rounded-full bg-muted/40 overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-400 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[10px] tabular-nums text-muted-foreground w-8 text-right">
        {Math.round(elo)}
      </span>
    </div>
  );
}

const RANK_ACCENT = ["text-amber-300", "text-zinc-300", "text-orange-400"];

export function TournamentBoard({ knowledge }: TournamentBoardProps) {
  const standings = buildStandings(knowledge);
  if (standings.length === 0) return null;

  // id -> short label ("H1", "H2", …) by current rank, for the matchup feed.
  const label: Record<string, string> = {};
  for (const s of standings) label[s.id] = `H${s.rank}`;

  const recentMatchups = [...knowledge.matchupResults].slice(-MAX_MATCHUPS).reverse();

  return (
    <div className="space-y-2">
      {/* Header */}
      <div className="flex items-center gap-1.5 px-1">
        <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
          Tournament
        </span>
        {knowledge.tournamentStatus && (
          <span className="text-[9px] font-medium px-1.5 py-0.5 rounded-full bg-violet-500/15 text-violet-300 uppercase tracking-wide">
            {knowledge.tournamentStatus.replace(/_/g, " ")}
          </span>
        )}
        <span className="ml-auto text-[10px] tabular-nums text-muted-foreground/70">
          {standings.length} hypotheses
        </span>
      </div>

      {knowledge.tournamentSummary && (
        <p className="text-[11px] text-muted-foreground/90 px-1 leading-snug">
          {knowledge.tournamentSummary}
        </p>
      )}

      {/* Standings */}
      <div className="space-y-1">
        {standings.map((s) => (
          <div
            key={s.id}
            className="flex items-start gap-2 px-1.5 py-1 rounded bg-muted/20 border border-border/40"
          >
            <span
              className={cn(
                "text-[11px] font-bold tabular-nums w-5 text-center shrink-0 pt-0.5",
                RANK_ACCENT[s.rank - 1] ?? "text-muted-foreground"
              )}
            >
              {s.rank}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className="text-[10px] font-bold text-indigo-300 shrink-0">
                  {label[s.id]}
                </span>
                <Movement delta={s.delta} />
                <span
                  className={cn(
                    "text-[9px] font-medium ml-auto shrink-0",
                    HYPOTHESIS_STATUS_COLORS[s.status] ?? "text-muted-foreground"
                  )}
                >
                  {s.status.replace(/_/g, " ")}
                </span>
              </div>
              <div className="text-[11px] text-foreground/90 leading-tight line-clamp-2">
                {s.statement}
              </div>
              <div className="flex items-center gap-2 mt-1">
                <EloMeter elo={s.elo} />
                {(s.wins > 0 || s.losses > 0) && (
                  <span className="text-[10px] tabular-nums text-muted-foreground/80">
                    <span className="text-emerald-400">{s.wins}W</span>
                    <span className="mx-0.5 text-muted-foreground/40">–</span>
                    <span className="text-red-400">{s.losses}L</span>
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Matchup feed */}
      {recentMatchups.length > 0 && (
        <div className="pt-0.5">
          <div className="text-[10px] font-medium text-muted-foreground/70 uppercase tracking-wider px-1 mb-1">
            Recent matchups
          </div>
          <div className="space-y-0.5">
            {recentMatchups.map((m, i) => {
              const winnerIsA = m.winner_id === m.hypothesis_a_id;
              const winnerLabel = label[m.winner_id] ?? "?";
              const loserId = winnerIsA ? m.hypothesis_b_id : m.hypothesis_a_id;
              const loserLabel = label[loserId] ?? "?";
              return (
                <div
                  key={i}
                  className="text-[10px] px-1.5 py-0.5 leading-snug text-muted-foreground"
                  title={m.judge_reasoning}
                >
                  <span className="font-bold text-emerald-400">{winnerLabel}</span>
                  <span className="mx-1 text-muted-foreground/50">beat</span>
                  <span className="font-medium text-foreground/70">{loserLabel}</span>
                  {m.margin != null && (
                    <span className="ml-1 text-[9px] tabular-nums text-muted-foreground/50">
                      ·{" "}
                      {m.margin <= 1
                        ? `${Math.round(m.margin * 100)}%`
                        : Math.round(m.margin)}
                    </span>
                  )}
                  {m.judge_reasoning && (
                    <span className="text-muted-foreground/60">
                      {" — "}
                      {m.judge_reasoning.slice(0, 64)}
                      {m.judge_reasoning.length > 64 ? "…" : ""}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

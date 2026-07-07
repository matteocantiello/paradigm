import { useCallback, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLaunchCycle } from "@/hooks/useLaunchCycle";
import { getModelTiers } from "@/api/client";
import { AGENT_THEMES, SELECTABLE_TEAM_ROLES } from "@/lib/constants";
import { DatasetPicker } from "./DatasetPicker";
import { formatSize } from "@/lib/datasets";
import { cn } from "@/lib/utils";
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  Check,
  Crown,
  Leaf,
  Loader2,
  Play,
  UserCheck,
  X,
} from "lucide-react";

const TIER_ICONS: Record<string, typeof Crown> = { premium: Crown, open: Leaf };

const MIN_PROMPT_CHARS = 15;

const STEPS = ["Prompt", "Mode", "Team", "Review"] as const;
type Step = (typeof STEPS)[number];

const MODES = [
  { value: "directed", label: "Directed", desc: "Focused research on a specific question" },
  { value: "explore", label: "Explore", desc: "Open-ended exploration of a topic" },
  { value: "test", label: "Test", desc: "Quick test run with minimal rounds" },
];

const SUPERVISION = [
  {
    value: false,
    icon: Bot,
    label: "Autonomous",
    desc: "The agents run end-to-end on their own. You can watch live and steer with messages.",
  },
  {
    value: true,
    icon: UserCheck,
    label: "Interactive",
    desc: "You decide with the agents: pick the winning hypotheses, approve the experiment plan, and gate phase transitions.",
  },
];

const ALL_ROLES: string[] = [...SELECTABLE_TEAM_ROLES];

interface SetupWizardProps {
  onClose: () => void;
  initialPrompt?: string;
  initialFiles?: File[];
}

export function SetupWizard({ onClose, initialPrompt, initialFiles }: SetupWizardProps) {
  // Opened from the hero console (or a retry) the prompt is already written —
  // asking again is redundant. Skip straight to supervision + team.
  const hasPrefill = (initialPrompt ?? "").trim().length >= MIN_PROMPT_CHARS;
  const steps: Step[] = hasPrefill ? ["Mode", "Team", "Review"] : [...STEPS];
  const [step, setStep] = useState<Step>(hasPrefill ? "Mode" : "Prompt");
  const [prompt, setPrompt] = useState(initialPrompt ?? "");
  const [mode, setMode] = useState("directed");
  const [interactive, setInteractive] = useState(false);
  // Model tier — null until the user picks or the server default loads.
  const [modelTier, setModelTier] = useState<string | null>(null);
  const { data: tiersData } = useQuery({
    queryKey: ["model-tiers"],
    queryFn: getModelTiers,
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const tiers = tiersData?.tiers ?? [];
  const effectiveTier = modelTier ?? tiersData?.default ?? null;
  const [roles, setRoles] = useState<string[]>([...ALL_ROLES]);
  const [files, setFiles] = useState<File[]>(initialFiles ?? []);

  const { launch, stage, error, busy, uploadIndex, isRetry } = useLaunchCycle();

  const stepIdx = steps.indexOf(step);
  const promptOk = prompt.trim().length >= MIN_PROMPT_CHARS;
  const teamOk = roles.length > 0;
  const canNext =
    (step === "Prompt" && promptOk) || step === "Mode" || (step === "Team" && teamOk);

  const toggleRole = (role: string) => {
    setRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]
    );
  };

  const handleSubmit = useCallback(() => {
    void launch({
      prompt,
      mode,
      // null = use the default team ("all selected" is the same thing; the Team
      // step blocks an empty selection, which would otherwise mean ZERO agents).
      teamRoles: roles.length === ALL_ROLES.length ? null : roles,
      files,
      interactive,
      modelTier: effectiveTier,
    });
  }, [launch, prompt, mode, roles, files, interactive, effectiveTier]);

  // Esc closes (except mid-submit, when closing would hide the upload progress).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const stageLabel =
    stage === "creating"
      ? "Creating cycle…"
      : stage === "uploading"
        ? `Uploading ${files[uploadIndex]?.name ?? "dataset"} (${uploadIndex + 1}/${files.length})…`
        : stage === "starting"
          ? "Starting session…"
          : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="relative w-full max-w-2xl rounded-xl border border-border/50 bg-card/95 backdrop-blur-md p-6 shadow-2xl shadow-primary/5">
        {/* Close */}
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          aria-label="Close"
          className="absolute right-4 top-4 rounded-lg p-1.5 text-muted-foreground hover:bg-accent/40 hover:text-foreground disabled:opacity-40 transition-all"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Step indicators — horizontal progress bar */}
        <div className="flex items-center gap-0 mb-8 pr-8">
          {steps.map((s, i) => (
            <div key={s} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center gap-1.5">
                <div
                  className={cn(
                    "flex items-center justify-center h-7 w-7 rounded-full text-xs font-semibold transition-all",
                    i === stepIdx
                      ? "bg-primary text-primary-foreground ring-2 ring-primary/30"
                      : i < stepIdx
                        ? "bg-emerald-500/20 text-emerald-400"
                        : "bg-muted text-muted-foreground"
                  )}
                >
                  {i < stepIdx ? <Check className="h-3.5 w-3.5" /> : i + 1}
                </div>
                <span
                  className={cn(
                    "text-[10px] uppercase tracking-wider",
                    i === stepIdx ? "font-semibold text-foreground" : "text-muted-foreground"
                  )}
                >
                  {s}
                </span>
              </div>
              {i < steps.length - 1 && (
                <div className={cn(
                  "flex-1 h-0.5 mx-2 mb-5 rounded-full",
                  i < stepIdx ? "bg-emerald-500/40" : "bg-border"
                )} />
              )}
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="min-h-[240px]">
          {step === "Prompt" && (
            <div>
              <label className="block text-sm font-semibold mb-2">Research Prompt</label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Describe the research question or topic…"
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm resize-y min-h-[10rem] h-40 placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 transition-all"
                maxLength={10000}
                autoFocus
              />
              <p className="text-xs text-muted-foreground mt-1.5 font-mono">
                {prompt.length}/10000
                {!promptOk && prompt.trim().length > 0 && (
                  <span className="ml-2 text-yellow-400">
                    at least {MIN_PROMPT_CHARS} characters
                  </span>
                )}
              </p>

              <div className="mt-4">
                <DatasetPicker files={files} onChange={setFiles} />
                <p className="text-[10px] text-muted-foreground mt-1.5">
                  Attached files are staged into the sandbox; the agents receive a schema
                  card (columns, types, sample rows) for each one.
                </p>
              </div>
            </div>
          )}

          {step === "Mode" && (
            <div className="space-y-5">
              {tiers.length > 0 && (
                <div>
                  <label className="block text-sm font-semibold mb-2">Models</label>
                  <div className="grid grid-cols-2 gap-2">
                    {tiers.map((t) => {
                      const Icon = TIER_ICONS[t.id] ?? Crown;
                      const selected = effectiveTier === t.id;
                      return (
                        <button
                          key={t.id}
                          onClick={() => setModelTier(t.id)}
                          disabled={!t.available}
                          title={t.available ? undefined : "API key not configured"}
                          className={cn(
                            "rounded-lg border p-3 text-left transition-all",
                            selected
                              ? "border-primary/50 bg-primary/5 glow-sm"
                              : "border-border hover:border-primary/30 hover:bg-accent/30",
                            !t.available && "opacity-40 cursor-not-allowed"
                          )}
                        >
                          <div className="flex items-center gap-2 text-sm font-semibold">
                            <Icon
                              className={cn(
                                "h-4 w-4",
                                selected ? "text-primary" : "text-muted-foreground"
                              )}
                            />
                            {t.label}
                          </div>
                          <div className="text-xs text-muted-foreground mt-1">{t.description}</div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div>
                <label className="block text-sm font-semibold mb-2">Supervision</label>
                <div className="grid grid-cols-2 gap-2">
                  {SUPERVISION.map((s) => {
                    const Icon = s.icon;
                    const selected = interactive === s.value;
                    return (
                      <button
                        key={s.label}
                        onClick={() => setInteractive(s.value)}
                        className={cn(
                          "rounded-lg border p-3 text-left transition-all",
                          selected
                            ? "border-primary/50 bg-primary/5 glow-sm"
                            : "border-border hover:border-primary/30 hover:bg-accent/30"
                        )}
                      >
                        <div className="flex items-center gap-2 text-sm font-semibold">
                          <Icon
                            className={cn(
                              "h-4 w-4",
                              selected ? "text-primary" : "text-muted-foreground"
                            )}
                          />
                          {s.label}
                        </div>
                        <div className="text-xs text-muted-foreground mt-1">{s.desc}</div>
                      </button>
                    );
                  })}
                </div>
                {interactive && (
                  <p className="mt-2 text-[11px] text-muted-foreground">
                    Decision prompts wait up to 5 minutes; if you step away, the agents
                    proceed with their own best choice.
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-semibold mb-2">Research Mode</label>
                {MODES.map((m) => (
                  <button
                    key={m.value}
                    onClick={() => setMode(m.value)}
                    className={cn(
                      "w-full rounded-lg border p-3 text-left transition-all",
                      mode === m.value
                        ? "border-primary/50 bg-primary/5 glow-sm"
                        : "border-border hover:border-primary/30 hover:bg-accent/30"
                    )}
                  >
                    <div className="text-sm font-semibold">{m.label}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">{m.desc}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === "Team" && (
            <div>
              <label className="block text-sm font-semibold mb-2">Agent Team</label>
              <div className="grid grid-cols-2 gap-2">
                {ALL_ROLES.map((role) => {
                  const theme = AGENT_THEMES[role]!;
                  const Icon = theme.icon;
                  const selected = roles.includes(role);
                  return (
                    <button
                      key={role}
                      onClick={() => toggleRole(role)}
                      aria-pressed={selected}
                      className={cn(
                        "flex items-center gap-2 rounded-lg border p-2.5 text-sm transition-all",
                        selected
                          ? "border-primary/50 bg-primary/5"
                          : "border-border bg-muted/20 hover:border-primary/30"
                      )}
                    >
                      <div className={cn(
                        "flex items-center justify-center h-7 w-7 rounded-full",
                        selected ? "bg-accent/50" : "bg-muted/50"
                      )}>
                        <Icon className={cn("h-4 w-4", selected ? theme.color : "text-muted-foreground/50")} />
                      </div>
                      <span className={cn("flex-1 text-left font-medium", !selected && "text-muted-foreground")}>
                        {theme.label}
                      </span>
                      <div
                        className={cn(
                          "flex h-4.5 w-4.5 items-center justify-center rounded-full border transition-all",
                          selected
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-border"
                        )}
                      >
                        {selected && <Check className="h-3 w-3" />}
                      </div>
                    </button>
                  );
                })}
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                {teamOk
                  ? `${roles.length}/${ALL_ROLES.length} roles on the team. Peer reviewers are added automatically.`
                  : "Select at least one role."}
              </p>
            </div>
          )}

          {step === "Review" && (
            <div className="space-y-3">
              <div className="rounded-lg bg-muted/30 p-3">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Prompt</div>
                <p className="text-sm max-h-28 overflow-y-auto whitespace-pre-wrap">{prompt}</p>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg bg-muted/30 p-3">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Mode</div>
                  <p className="text-sm capitalize font-medium">{mode}</p>
                </div>
                <div className="rounded-lg bg-muted/30 p-3">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Supervision</div>
                  <p className="text-sm font-medium">{interactive ? "Interactive" : "Autonomous"}</p>
                </div>
                <div className="rounded-lg bg-muted/30 p-3">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Models</div>
                  <p className="text-sm font-medium">
                    {tiers.find((t) => t.id === effectiveTier)?.label ?? "Server default"}
                  </p>
                </div>
              </div>
              <div className="rounded-lg bg-muted/30 p-3">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Team</div>
                <p className="text-sm">{roles.map((r) => AGENT_THEMES[r]?.label ?? r).join(", ")}</p>
              </div>
              <div className="rounded-lg bg-muted/30 p-3">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                  Datasets{files.length > 0 ? ` (${files.length})` : ""}
                </div>
                {files.length > 0 ? (
                  <p className="mb-2 text-sm font-mono">
                    {files.map((f) => `${f.name} (${formatSize(f.size)})`).join(", ")}
                  </p>
                ) : (
                  <p className="mb-2 text-sm text-muted-foreground">None attached.</p>
                )}
                <DatasetPicker files={files} onChange={setFiles} compact disabled={busy} />
              </div>
              {stageLabel && (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {stageLabel}
                </p>
              )}
              {error && (
                <p className="text-sm text-red-400 bg-red-500/10 rounded-lg p-3">
                  Error: {error}
                  {isRetry && " — the cycle was created; Retry resumes without duplicating it."}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-6">
          <button
            onClick={stepIdx === 0 ? onClose : () => setStep(steps[stepIdx - 1])}
            disabled={busy}
            className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent/30 disabled:opacity-40 transition-all"
          >
            <ArrowLeft className="h-4 w-4" />
            {stepIdx === 0 ? "Cancel" : "Back"}
          </button>

          {step === "Review" ? (
            <button
              onClick={handleSubmit}
              disabled={busy}
              className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-primary to-primary/80 px-5 py-2 text-sm font-semibold text-primary-foreground hover:shadow-lg hover:shadow-primary/20 disabled:opacity-50 transition-all"
            >
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {error && isRetry ? "Retry" : "Start Research"}
            </button>
          ) : (
            <button
              onClick={() => setStep(steps[stepIdx + 1])}
              disabled={!canNext}
              className="flex items-center gap-1 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-all"
            >
              Next
              <ArrowRight className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateCycle, useStartSession } from "@/hooks/useCycles";
import { AGENT_THEMES, SELECTABLE_TEAM_ROLES } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { ArrowLeft, ArrowRight, Play, Loader2, Check } from "lucide-react";

const STEPS = ["Prompt", "Mode", "Team", "Review"] as const;
type Step = (typeof STEPS)[number];

const MODES = [
  { value: "directed", label: "Directed", desc: "Focused research on a specific question" },
  { value: "explore", label: "Explore", desc: "Open-ended exploration of a topic" },
  { value: "test", label: "Test", desc: "Quick test run with minimal rounds" },
];

const ALL_ROLES: string[] = [...SELECTABLE_TEAM_ROLES];

interface SetupWizardProps {
  onClose: () => void;
}

export function SetupWizard({ onClose }: SetupWizardProps) {
  const [step, setStep] = useState<Step>("Prompt");
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState("directed");
  const [roles, setRoles] = useState<string[]>([...ALL_ROLES]);

  const navigate = useNavigate();
  const createCycle = useCreateCycle();
  const startSession = useStartSession();

  const stepIdx = STEPS.indexOf(step);
  const canNext =
    (step === "Prompt" && prompt.trim().length >= 1) ||
    step === "Mode" ||
    step === "Team" ||
    step === "Review";

  const toggleRole = (role: string) => {
    setRoles((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role]
    );
  };

  const handleSubmit = useCallback(async () => {
    try {
      const cycle = await createCycle.mutateAsync({
        seed_prompt: prompt.trim(),
        mode,
        // null = use the default team. Send null for "all selected" AND for
        // "none selected" — an empty list would otherwise run with ZERO agents.
        team_roles:
          roles.length === 0 || roles.length === ALL_ROLES.length ? null : roles,
      });
      const session = await startSession.mutateAsync(cycle.cycle_id);
      navigate(`/session/${session.session_id}`);
    } catch (err) {
      console.error("Failed to create cycle:", err);
    }
  }, [prompt, mode, roles, createCycle, startSession, navigate]);

  const isSubmitting = createCycle.isPending || startSession.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-xl border border-border/50 bg-card/95 backdrop-blur-md p-6 shadow-2xl shadow-primary/5">
        {/* Step indicators — horizontal progress bar */}
        <div className="flex items-center gap-0 mb-8">
          {STEPS.map((s, i) => (
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
              {i < STEPS.length - 1 && (
                <div className={cn(
                  "flex-1 h-0.5 mx-2 mb-5 rounded-full",
                  i < stepIdx ? "bg-emerald-500/40" : "bg-border"
                )} />
              )}
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="min-h-[200px]">
          {step === "Prompt" && (
            <div>
              <label className="block text-sm font-semibold mb-2">Research Prompt</label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Describe the research question or topic..."
                className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm resize-y min-h-[12rem] h-48 placeholder:text-muted-foreground/40 focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 transition-all"
                maxLength={10000}
              />
              <p className="text-xs text-muted-foreground mt-1.5 font-mono">
                {prompt.length}/10000 characters
              </p>
            </div>
          )}

          {step === "Mode" && (
            <div className="space-y-2">
              <label className="block text-sm font-semibold mb-2">Research Mode</label>
              {MODES.map((m) => (
                <button
                  key={m.value}
                  onClick={() => setMode(m.value)}
                  className={cn(
                    "w-full rounded-lg border p-3.5 text-left transition-all",
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
                      className={cn(
                        "flex items-center gap-2 rounded-lg border p-2.5 text-sm transition-all",
                        selected
                          ? "border-primary/50 bg-primary/5"
                          : "border-border opacity-40 hover:opacity-70"
                      )}
                    >
                      <div className={cn(
                        "flex items-center justify-center h-7 w-7 rounded-full",
                        selected ? "bg-accent/50" : "bg-muted/50"
                      )}>
                        <Icon className={cn("h-4 w-4", theme.color)} />
                      </div>
                      <span className="font-medium">{theme.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {step === "Review" && (
            <div className="space-y-4">
              <div className="rounded-lg bg-muted/30 p-3">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Prompt</div>
                <p className="text-sm max-h-32 overflow-y-auto whitespace-pre-wrap">{prompt}</p>
              </div>
              <div className="rounded-lg bg-muted/30 p-3">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Mode</div>
                <p className="text-sm capitalize font-medium">{mode}</p>
              </div>
              <div className="rounded-lg bg-muted/30 p-3">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Team</div>
                <p className="text-sm">{roles.map((r) => AGENT_THEMES[r]?.label ?? r).join(", ")}</p>
              </div>
              {(createCycle.isError || startSession.isError) && (
                <p className="text-sm text-red-400 bg-red-500/10 rounded-lg p-3">
                  Error: {(createCycle.error ?? startSession.error)?.message}
                </p>
              )}
            </div>
          )}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-6">
          <button
            onClick={stepIdx === 0 ? onClose : () => setStep(STEPS[stepIdx - 1])}
            className="flex items-center gap-1 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-accent/30 transition-all"
          >
            <ArrowLeft className="h-4 w-4" />
            {stepIdx === 0 ? "Cancel" : "Back"}
          </button>

          {step === "Review" ? (
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-primary to-primary/80 px-5 py-2 text-sm font-semibold text-primary-foreground hover:shadow-lg hover:shadow-primary/20 disabled:opacity-50 transition-all"
            >
              {isSubmitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              Start Research
            </button>
          ) : (
            <button
              onClick={() => setStep(STEPS[stepIdx + 1])}
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

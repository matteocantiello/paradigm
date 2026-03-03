import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateCycle, useStartSession } from "@/hooks/useCycles";
import { AGENT_THEMES } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { ArrowLeft, ArrowRight, Play, Loader2 } from "lucide-react";

const STEPS = ["Prompt", "Mode", "Team", "Review"] as const;
type Step = (typeof STEPS)[number];

const MODES = [
  { value: "directed", label: "Directed", desc: "Focused research on a specific question" },
  { value: "explore", label: "Explore", desc: "Open-ended exploration of a topic" },
  { value: "test", label: "Test", desc: "Quick test run with minimal rounds" },
];

const ALL_ROLES = Object.keys(AGENT_THEMES);

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
        team_roles: roles.length === ALL_ROLES.length ? null : roles,
      });
      const session = await startSession.mutateAsync(cycle.cycle_id);
      navigate(`/session/${session.session_id}`);
    } catch (err) {
      console.error("Failed to create cycle:", err);
    }
  }, [prompt, mode, roles, createCycle, startSession, navigate]);

  const isSubmitting = createCycle.isPending || startSession.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-xl">
        {/* Step indicators */}
        <div className="flex items-center gap-2 mb-6">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              {i > 0 && <div className="h-px w-6 bg-border" />}
              <div
                className={cn(
                  "flex items-center justify-center h-6 w-6 rounded-full text-xs font-medium",
                  i === stepIdx
                    ? "bg-primary text-primary-foreground"
                    : i < stepIdx
                      ? "bg-green-500/20 text-green-400"
                      : "bg-muted text-muted-foreground"
                )}
              >
                {i + 1}
              </div>
              <span
                className={cn(
                  "text-sm",
                  i === stepIdx ? "font-medium" : "text-muted-foreground"
                )}
              >
                {s}
              </span>
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="min-h-[200px]">
          {step === "Prompt" && (
            <div>
              <label className="block text-sm font-medium mb-2">Research Prompt</label>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Describe the research question or topic..."
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none h-32 placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                maxLength={10000}
              />
              <p className="text-xs text-muted-foreground mt-1">
                {prompt.length}/10000 characters
              </p>
            </div>
          )}

          {step === "Mode" && (
            <div className="space-y-2">
              <label className="block text-sm font-medium mb-2">Research Mode</label>
              {MODES.map((m) => (
                <button
                  key={m.value}
                  onClick={() => setMode(m.value)}
                  className={cn(
                    "w-full rounded-md border p-3 text-left transition-colors",
                    mode === m.value
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  )}
                >
                  <div className="text-sm font-medium">{m.label}</div>
                  <div className="text-xs text-muted-foreground">{m.desc}</div>
                </button>
              ))}
            </div>
          )}

          {step === "Team" && (
            <div>
              <label className="block text-sm font-medium mb-2">Agent Team</label>
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
                        "flex items-center gap-2 rounded-md border p-2 text-sm transition-colors",
                        selected
                          ? "border-primary bg-primary/5"
                          : "border-border opacity-50 hover:opacity-80"
                      )}
                    >
                      <Icon className={cn("h-4 w-4", theme.color)} />
                      <span>{theme.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {step === "Review" && (
            <div className="space-y-3">
              <div>
                <div className="text-xs text-muted-foreground">Prompt</div>
                <p className="text-sm mt-0.5 line-clamp-3">{prompt}</p>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Mode</div>
                <p className="text-sm mt-0.5 capitalize">{mode}</p>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Team</div>
                <p className="text-sm mt-0.5">{roles.map((r) => AGENT_THEMES[r]?.label ?? r).join(", ")}</p>
              </div>
              {(createCycle.isError || startSession.isError) && (
                <p className="text-sm text-red-400">
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
            className="flex items-center gap-1 rounded-md px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            {stepIdx === 0 ? "Cancel" : "Back"}
          </button>

          {step === "Review" ? (
            <button
              onClick={handleSubmit}
              disabled={isSubmitting}
              className="flex items-center gap-1.5 rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
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
              className="flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
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

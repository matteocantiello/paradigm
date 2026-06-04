import { useState, useEffect, useRef, useCallback } from "react";
import {
  Cog,
  Container,
  BookOpen,
  Brain,
  Database,
  Quote,
  FileText,
  type LucideIcon,
} from "lucide-react";
import { useSettings, useUpdateSettings } from "@/hooks/useSettings";
import { SettingsSection } from "@/components/settings/SettingsSection";
import {
  ToggleField,
  NumberField,
  SelectField,
  TextField,
} from "@/components/settings/SettingsField";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";
import { ErrorState } from "@/components/shared/ErrorState";
import type { AllSettings } from "@/api/client";

// --- Tab definitions ---

interface TabDef {
  id: keyof AllSettings;
  label: string;
  icon: LucideIcon;
  description: string;
}

const TABS: TabDef[] = [
  { id: "orchestrator", label: "Orchestrator", icon: Cog, description: "Research cycle behavior" },
  { id: "sandbox", label: "Sandbox", icon: Container, description: "Code execution environment" },
  { id: "literature", label: "Literature", icon: BookOpen, description: "Search and retrieval" },
  { id: "knowledge", label: "Knowledge", icon: Brain, description: "World model and evidence" },
  { id: "memory", label: "Memory", icon: Database, description: "Agent episodic memory" },
  { id: "citation", label: "Citation", icon: Quote, description: "Grounding and novelty" },
  { id: "journal", label: "Journal", icon: FileText, description: "Paper output formats" },
];

// --- Helpers ---

type SectionState = Record<string, unknown>;

// --- Hooks for per-section form state with auto-save ---

function useSectionForm(
  section: string,
  remote: SectionState | undefined,
  save: (section: string, diff: Record<string, unknown>) => void,
) {
  const [local, setLocal] = useState<SectionState>({});
  const initialized = useRef(false);

  useEffect(() => {
    if (remote && !initialized.current) {
      setLocal({ ...remote });
      initialized.current = true;
    }
  }, [remote]);

  const set = useCallback(
    (field: string, value: unknown) => {
      setLocal((prev) => {
        const next = { ...prev, [field]: value };
        // Auto-save the changed field
        save(section, { [field]: value });
        return next;
      });
    },
    [section, save],
  );

  const reset = useCallback(() => {
    if (remote) {
      setLocal({ ...remote });
      // Save all remote values to reset to defaults
      save(section, { ...remote });
    }
  }, [remote, section, save]);

  return { local, set, reset };
}

// --- Main page ---

export function SettingsPage() {
  const { data, isLoading, error, refetch } = useSettings();
  const mutation = useUpdateSettings();
  const [activeTab, setActiveTab] = useState<keyof AllSettings>("orchestrator");
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [savingSection, setSavingSection] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSave = useCallback(
    (section: string, diff: Record<string, unknown>) => {
      if (Object.keys(diff).length === 0) return;
      setSavingSection(section);
      setSaveError(null);
      mutation.mutate(
        { section, body: diff },
        {
          onSuccess: () => setSavingSection(null),
          onError: (err) => {
            setSavingSection(null);
            setSaveError(err.message);
          },
        },
      );
    },
    [mutation],
  );

  // Per-section form states
  const orchestrator = useSectionForm(
    "orchestrator",
    data?.orchestrator as unknown as SectionState | undefined,
    handleSave,
  );
  const sandbox = useSectionForm(
    "sandbox",
    data?.sandbox as unknown as SectionState | undefined,
    handleSave,
  );
  const literature = useSectionForm(
    "literature",
    data?.literature as unknown as SectionState | undefined,
    handleSave,
  );
  const knowledge = useSectionForm(
    "knowledge",
    data?.knowledge as unknown as SectionState | undefined,
    handleSave,
  );
  const memory = useSectionForm(
    "memory",
    data?.memory as unknown as SectionState | undefined,
    handleSave,
  );
  const citation = useSectionForm(
    "citation",
    data?.citation as unknown as SectionState | undefined,
    handleSave,
  );
  const journal = useSectionForm(
    "journal",
    data?.journal as unknown as SectionState | undefined,
    handleSave,
  );

  const handleTabClick = (id: keyof AllSettings) => {
    setActiveTab(id);
    sectionRefs.current[id]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <LoadingSpinner />
      </div>
    );
  }

  if (error) {
    return <ErrorState message={error.message} onRetry={() => refetch()} />;
  }

  if (!data) return null;

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configure runtime parameters for the research platform
        </p>
      </div>

      <div className="flex gap-6">
        {/* Left tab strip */}
        <nav className="sticky top-4 self-start w-48 shrink-0 space-y-0.5">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => handleTabClick(id)}
              className={`flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                activeTab === id
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </nav>

        {/* Right content */}
        <div className="flex-1 space-y-6 min-w-0">
          {/* Orchestrator */}
          <SettingsSection
            ref={(el) => { sectionRefs.current.orchestrator = el; }}
            id="orchestrator"
            icon={Cog}
            title="Orchestrator"
            description="Research cycle behavior and phase control"
            saving={savingSection === "orchestrator"}
            error={savingSection === "orchestrator" ? saveError : null}
            onReset={orchestrator.reset}
          >
            <NumberField
              label="Max rounds per phase"
              description="Maximum agent turns within a single phase"
              value={orchestrator.local.max_rounds_per_phase as number}
              onChange={(v) => orchestrator.set("max_rounds_per_phase", v)}
              min={1}
              max={50}
            />
            <ToggleField
              label="Enable checkpointing"
              description="Save compressed state snapshots during research"
              value={orchestrator.local.enable_checkpointing as boolean}
              onChange={(v) => orchestrator.set("enable_checkpointing", v)}
            />
            <ToggleField
              label="Enable writing"
              description="Run the paper writing phase after research"
              value={orchestrator.local.enable_writing as boolean}
              onChange={(v) => orchestrator.set("enable_writing", v)}
            />
            <NumberField
              label="Max review iterations"
              description="Internal review rounds before submission"
              value={orchestrator.local.max_review_iterations as number}
              onChange={(v) => orchestrator.set("max_review_iterations", v)}
              min={1}
              max={20}
            />
            <ToggleField
              label="Enable peer review"
              description="Submit papers to the peer review pipeline"
              value={orchestrator.local.enable_peer_review as boolean}
              onChange={(v) => orchestrator.set("enable_peer_review", v)}
            />
            <NumberField
              label="Number of reviewers"
              description="Reviewers assigned per paper"
              value={orchestrator.local.num_reviewers as number}
              onChange={(v) => orchestrator.set("num_reviewers", v)}
              min={1}
              max={5}
            />
            <ToggleField
              label="Enable experimentation"
              description="Allow agents to run code experiments"
              value={orchestrator.local.enable_experimentation as boolean}
              onChange={(v) => orchestrator.set("enable_experimentation", v)}
            />
            <ToggleField
              label="Enable debates"
              description="Focused debate sub-routine when agents disagree"
              value={orchestrator.local.enable_debates as boolean}
              onChange={(v) => orchestrator.set("enable_debates", v)}
            />
            <NumberField
              label="Max debate exchanges"
              description="Back-and-forth turns per debate"
              value={orchestrator.local.max_debate_exchanges as number}
              onChange={(v) => orchestrator.set("max_debate_exchanges", v)}
              min={1}
              max={10}
            />
            <ToggleField
              label="Enable convergence detection"
              description="Auto-advance phase when agents converge"
              value={orchestrator.local.enable_convergence_detection as boolean}
              onChange={(v) => orchestrator.set("enable_convergence_detection", v)}
            />
            <NumberField
              label="Convergence threshold"
              description="Confidence threshold for convergence (0-1)"
              value={orchestrator.local.convergence_confidence_threshold as number}
              onChange={(v) => orchestrator.set("convergence_confidence_threshold", v)}
              min={0}
              max={1}
              step={0.05}
            />
            <ToggleField
              label="Enable execution sprints"
              description="Multi-round sprint execution with review gates"
              value={orchestrator.local.enable_execution_sprints as boolean}
              onChange={(v) => orchestrator.set("enable_execution_sprints", v)}
            />
            <NumberField
              label="Execution sprints"
              description="Number of sprint iterations"
              value={orchestrator.local.num_execution_sprints as number}
              onChange={(v) => orchestrator.set("num_execution_sprints", v)}
              min={1}
              max={10}
            />
            <ToggleField
              label="Enable verification kernel"
              description="Re-execute results in a fresh sandbox; accept only what reproduces"
              value={orchestrator.local.enable_verification as boolean}
              onChange={(v) => orchestrator.set("enable_verification", v)}
            />
            <NumberField
              label="Verification tolerance"
              description="Relative tolerance for reproducing RESULT[...] metrics"
              value={orchestrator.local.verification_tolerance as number}
              onChange={(v) => orchestrator.set("verification_tolerance", v)}
              min={0}
              max={1}
              step={0.000001}
            />
            <ToggleField
              label="Abort on verification failure"
              description="Stop before writing if no experiment reproduces"
              value={orchestrator.local.abort_on_verification_failure as boolean}
              onChange={(v) => orchestrator.set("abort_on_verification_failure", v)}
            />
            <ToggleField
              label="Best-first experiment ordering"
              description="Prefer non-buggy experiments within a round"
              value={orchestrator.local.enable_best_first_nodes as boolean}
              onChange={(v) => orchestrator.set("enable_best_first_nodes", v)}
            />
            <ToggleField
              label="Step restart"
              description="Resume failed multi-step experiments from prior artifacts"
              value={orchestrator.local.enable_step_restart as boolean}
              onChange={(v) => orchestrator.set("enable_step_restart", v)}
            />
            <SelectField
              label="Human gate mode"
              description="Human checkpoints at problem-selection / pre-registration / verification"
              value={orchestrator.local.human_gate_mode as string}
              onChange={(v) => orchestrator.set("human_gate_mode", v)}
              options={[
                { value: "off", label: "Off (autonomous)" },
                { value: "advisory", label: "Advisory (surface, don't block)" },
                { value: "blocking", label: "Blocking (require approval)" },
              ]}
            />
            <ToggleField
              label="Figure-aware review"
              description="Editor visually inspects the actual figures during review"
              value={orchestrator.local.enable_multimodal_review as boolean}
              onChange={(v) => orchestrator.set("enable_multimodal_review", v)}
            />
            <NumberField
              label="Max review figures"
              description="Cap on figures sent to the vision model"
              value={orchestrator.local.max_review_figures as number}
              onChange={(v) => orchestrator.set("max_review_figures", v)}
              min={1}
              max={20}
            />
          </SettingsSection>

          {/* Sandbox */}
          <SettingsSection
            ref={(el) => { sectionRefs.current.sandbox = el; }}
            id="sandbox"
            icon={Container}
            title="Sandbox"
            description="Docker code execution environment"
            saving={savingSection === "sandbox"}
            error={savingSection === "sandbox" ? saveError : null}
            onReset={sandbox.reset}
          >
            <ToggleField
              label="Enabled"
              description="Enable Docker sandbox for code execution"
              value={sandbox.local.enabled as boolean}
              onChange={(v) => sandbox.set("enabled", v)}
            />
            <SelectField
              label="Network mode"
              description="Docker network mode for sandbox containers"
              value={sandbox.local.network_mode as string}
              onChange={(v) => sandbox.set("network_mode", v)}
              options={[
                { value: "none", label: "None (isolated)" },
                { value: "bridge", label: "Bridge (network access)" },
              ]}
            />
            <NumberField
              label="CPU limit"
              description="Maximum CPU cores for sandbox"
              value={sandbox.local.cpu_limit as number}
              onChange={(v) => sandbox.set("cpu_limit", v)}
              min={0.5}
              max={16}
              step={0.5}
            />
            <TextField
              label="Memory limit"
              description="Container memory limit (e.g. 2g, 512m)"
              value={sandbox.local.memory_limit as string}
              onChange={(v) => sandbox.set("memory_limit", v)}
              placeholder="2g"
            />
            <NumberField
              label="Execution timeout"
              description="Max seconds per code execution"
              value={sandbox.local.execution_timeout as number}
              onChange={(v) => sandbox.set("execution_timeout", v)}
              min={10}
              max={3600}
            />
          </SettingsSection>

          {/* Literature */}
          <SettingsSection
            ref={(el) => { sectionRefs.current.literature = el; }}
            id="literature"
            icon={BookOpen}
            title="Literature"
            description="Search, retrieval, and citation graph traversal"
            saving={savingSection === "literature"}
            error={savingSection === "literature" ? saveError : null}
            onReset={literature.reset}
          >
            <NumberField
              label="Max results per search"
              description="Maximum papers returned per keyword search"
              value={literature.local.max_results_per_search as number}
              onChange={(v) => literature.set("max_results_per_search", v)}
              min={1}
              max={200}
            />
            <ToggleField
              label="Enable PDF fetch"
              description="Download and extract text from PDFs"
              value={literature.local.enable_pdf_fetch as boolean}
              onChange={(v) => literature.set("enable_pdf_fetch", v)}
            />
            <NumberField
              label="Follow budget per round"
              description="Max reference-chasing actions per round"
              value={literature.local.follow_budget_per_round as number}
              onChange={(v) => literature.set("follow_budget_per_round", v)}
              min={0}
              max={20}
            />
            <NumberField
              label="Cited-by budget per round"
              description="Max citation-forward searches per round"
              value={literature.local.cited_by_budget_per_round as number}
              onChange={(v) => literature.set("cited_by_budget_per_round", v)}
              min={0}
              max={20}
            />
            <NumberField
              label="Read budget per round"
              description="Max deep-reading actions per round"
              value={literature.local.read_budget_per_round as number}
              onChange={(v) => literature.set("read_budget_per_round", v)}
              min={0}
              max={20}
            />
            <NumberField
              label="Max read chars"
              description="Character limit for deep-read extraction"
              value={literature.local.max_read_chars as number}
              onChange={(v) => literature.set("max_read_chars", v)}
              min={1000}
              max={50000}
              step={1000}
            />
          </SettingsSection>

          {/* Knowledge */}
          <SettingsSection
            ref={(el) => { sectionRefs.current.knowledge = el; }}
            id="knowledge"
            icon={Brain}
            title="Knowledge"
            description="World model, evidence graph, hypothesis tournament"
            saving={savingSection === "knowledge"}
            error={savingSection === "knowledge" ? saveError : null}
            onReset={knowledge.reset}
          >
            <ToggleField
              label="Enable world model"
              description="Maintain a shared world model across agents"
              value={knowledge.local.enable_world_model as boolean}
              onChange={(v) => knowledge.set("enable_world_model", v)}
            />
            <ToggleField
              label="Enable evidence graph"
              description="Track evidence relationships between claims"
              value={knowledge.local.enable_evidence_graph as boolean}
              onChange={(v) => knowledge.set("enable_evidence_graph", v)}
            />
            <ToggleField
              label="Enable hypothesis tournament"
              description="Elo-rated competition between hypotheses"
              value={knowledge.local.enable_hypothesis_tournament as boolean}
              onChange={(v) => knowledge.set("enable_hypothesis_tournament", v)}
            />
            <ToggleField
              label="Enable pre-registration"
              description="Freeze falsifiable predictions before execution"
              value={knowledge.local.enable_preregistration as boolean}
              onChange={(v) => knowledge.set("enable_preregistration", v)}
            />
            <ToggleField
              label="Require refutation condition"
              description="Drop hypotheses that lack a falsifiable refutation rule"
              value={knowledge.local.prereg_require_refutation as boolean}
              onChange={(v) => knowledge.set("prereg_require_refutation", v)}
            />
            <SelectField
              label="If no rules can be frozen"
              description="Behavior when no falsifiable prediction survives"
              value={knowledge.local.prereg_on_empty as string}
              onChange={(v) => knowledge.set("prereg_on_empty", v)}
              options={[
                { value: "advisory", label: "Advisory (warn and continue)" },
                { value: "blocking", label: "Blocking (abort the cycle)" },
              ]}
            />
          </SettingsSection>

          {/* Memory */}
          <SettingsSection
            ref={(el) => { sectionRefs.current.memory = el; }}
            id="memory"
            icon={Database}
            title="Memory"
            description="Agent episodic memory system"
            saving={savingSection === "memory"}
            error={savingSection === "memory" ? saveError : null}
            onReset={memory.reset}
          >
            <ToggleField
              label="Enabled"
              description="Enable episodic memory for agents"
              value={memory.local.enabled as boolean}
              onChange={(v) => memory.set("enabled", v)}
            />
            <NumberField
              label="Max memories per prompt"
              description="Memories injected per agent prompt"
              value={memory.local.max_memories_per_prompt as number}
              onChange={(v) => memory.set("max_memories_per_prompt", v)}
              min={0}
              max={20}
            />
          </SettingsSection>

          {/* Citation */}
          <SettingsSection
            ref={(el) => { sectionRefs.current.citation = el; }}
            id="citation"
            icon={Quote}
            title="Citation"
            description="Citation grounding and novelty checking"
            saving={savingSection === "citation"}
            error={savingSection === "citation" ? saveError : null}
            onReset={citation.reset}
          >
            <ToggleField
              label="Enable citation grounding"
              description="Verify claims against literature via Perplexity"
              value={citation.local.enable_citation_grounding as boolean}
              onChange={(v) => citation.set("enable_citation_grounding", v)}
            />
            <ToggleField
              label="Enable novelty check"
              description="Check paper novelty against existing literature"
              value={citation.local.enable_novelty_check as boolean}
              onChange={(v) => citation.set("enable_novelty_check", v)}
            />
            <ToggleField
              label="Enable seed discovery"
              description="Discover seed papers to bootstrap literature search"
              value={citation.local.enable_seed_discovery as boolean}
              onChange={(v) => citation.set("enable_seed_discovery", v)}
            />
            <ToggleField
              label="Drop unresolved citations"
              description="Drop references that don't resolve to real metadata (vs. bare URLs)"
              value={citation.local.drop_unresolved_citations as boolean}
              onChange={(v) => citation.set("drop_unresolved_citations", v)}
            />
          </SettingsSection>

          {/* Journal */}
          <SettingsSection
            ref={(el) => { sectionRefs.current.journal = el; }}
            id="journal"
            icon={FileText}
            title="Journal"
            description="Paper output formats (markdown is always written)"
            saving={savingSection === "journal"}
            error={savingSection === "journal" ? saveError : null}
            onReset={journal.reset}
          >
            <ToggleField
              label="Enable LaTeX output"
              description="Also write a journal-ready .tex alongside the markdown paper"
              value={journal.local.enable_latex_output as boolean}
              onChange={(v) => journal.set("enable_latex_output", v)}
            />
            <SelectField
              label="LaTeX journal preset"
              description="Document class / style for the .tex output"
              value={journal.local.latex_journal as string}
              onChange={(v) => journal.set("latex_journal", v)}
              options={[
                { value: "none", label: "Plain article" },
                { value: "arxiv", label: "arXiv" },
                { value: "neurips", label: "NeurIPS" },
              ]}
            />
            <ToggleField
              label="Compile PDF"
              description="Also compile the .tex to PDF (requires a LaTeX engine on the server)"
              value={journal.local.compile_pdf as boolean}
              onChange={(v) => journal.set("compile_pdf", v)}
            />
          </SettingsSection>
        </div>
      </div>
    </div>
  );
}

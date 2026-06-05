import type { LucideIcon } from "lucide-react";
import {
  Lightbulb,
  BarChart3,
  FlaskConical,
  Link,
  Search,
  PenTool,
  FileEdit,
  ClipboardList,
} from "lucide-react";

// Agent theme map — mirrors src/paradigm/display/theme.py
export interface AgentTheme {
  icon: LucideIcon;
  color: string;
  label: string;
}

export const AGENT_THEMES: Record<string, AgentTheme> = {
  theorist: {
    icon: Lightbulb,
    color: "text-blue-400",
    label: "Theorist",
  },
  analyst: {
    icon: BarChart3,
    color: "text-amber-400",
    label: "Analyst",
  },
  experimentalist: {
    icon: FlaskConical,
    color: "text-emerald-400",
    label: "Experimentalist",
  },
  synthesizer: {
    icon: Link,
    color: "text-fuchsia-400",
    label: "Synthesizer",
  },
  skeptic: {
    icon: Search,
    color: "text-rose-400",
    label: "Skeptic",
  },
  writer: {
    icon: PenTool,
    color: "text-cyan-400",
    label: "Writer",
  },
  editor: {
    icon: FileEdit,
    color: "text-yellow-300",
    label: "Editor",
  },
  reviewer: {
    icon: ClipboardList,
    color: "text-slate-300",
    label: "Reviewer",
  },
};

// Phase icons and display order — mirrors src/paradigm/display/theme.py
export const PHASE_ICONS: Record<string, string> = {
  seeding: "🌱",
  ideation: "💡",
  planning: "📐",
  literature: "📚",
  execution: "⚙️",
  post_execution: "💬",
  writing: "📝",
  internal: "🔎",
  submitted: "📨",
  peer_review: "🧑‍⚖️",
  revision: "🔄",
  published: "✅",
  rejected: "❌",
};

export const PHASE_DISPLAY_ORDER = [
  "seeding",
  "ideation",
  "planning",
  "execution",
  "post_execution",
  "writing",
  "internal",
  "submitted",
  "peer_review",
  "published",
] as const;

export const PHASE_LABELS: Record<string, string> = {
  seeding: "Seeding",
  ideation: "Ideation",
  planning: "Planning",
  literature: "Literature",
  execution: "Execution",
  post_execution: "Discussion",
  writing: "Writing",
  internal: "Review",
  submitted: "Submitted",
  peer_review: "Peer Review",
  revision: "Revision",
  published: "Published",
  rejected: "Rejected",
};

// Event categories → colors for the event log
export const EVENT_COLORS: Record<string, string> = {
  phase: "text-blue-400",
  search: "text-yellow-400",
  debate: "text-amber-400",
  experiment: "text-emerald-400",
  writing: "text-cyan-400",
  review: "text-purple-400",
  error: "text-red-400",
  success: "text-emerald-400",
  info: "text-muted-foreground",
  warning: "text-yellow-400",
  knowledge: "text-primary",
};

// Knowledge panel color maps
export const HYPOTHESIS_STATUS_COLORS: Record<string, string> = {
  supported: "text-emerald-400",
  under_investigation: "text-yellow-400",
  weakened: "text-orange-400",
  refuted: "text-red-400",
  proposed: "text-blue-400",
};

export const ENTITY_TYPE_COLORS: Record<string, string> = {
  object: "bg-blue-500/20 text-blue-300",
  mechanism: "bg-purple-500/20 text-purple-300",
  observable: "bg-emerald-500/20 text-emerald-300",
  instrument: "bg-cyan-500/20 text-cyan-300",
  model: "bg-amber-500/20 text-amber-300",
  concept: "bg-pink-500/20 text-pink-300",
};


export const CONFLICT_TYPE_COLORS: Record<string, string> = {
  unresolved: "text-red-400 border-red-500/30",
  resolved: "text-emerald-400 border-emerald-500/30",
  partial: "text-yellow-400 border-yellow-500/30",
};

export function getAgentRole(agentId: string): string {
  const parts = agentId.split("-");
  return parts[parts.length - 1] ?? agentId;
}

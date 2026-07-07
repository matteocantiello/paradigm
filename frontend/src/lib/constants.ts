import type { LucideIcon } from "lucide-react";
import {
  Lightbulb,
  BarChart3,
  FlaskConical,
  Link,
  Search,
  PenTool,
  FileEdit,
  FileSearch,
  UserRound,
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
    icon: FileSearch,
    color: "text-teal-400",
    label: "Reviewer",
  },
  // Peer reviewers get ids like "peer-reviewer-0" (getAgentRole -> "peer-reviewer").
  "peer-reviewer": {
    icon: FileSearch,
    color: "text-teal-400",
    label: "Reviewer",
  },
  // The human steering the run (local-echo bubbles in the messages panel).
  operator: {
    icon: UserRound,
    color: "text-primary",
    label: "You",
  },
};

// Roles a user can compose into a research team. This is NOT all of AGENT_THEMES:
// "reviewer"/"peer-reviewer" are auto-created by the orchestrator for peer review
// and are not valid factory roles to put on a team (doing so crashes create_team).
export const SELECTABLE_TEAM_ROLES = [
  "theorist",
  "analyst",
  "experimentalist",
  "synthesizer",
  "skeptic",
  "writer",
  "editor",
] as const;

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

// Topic badges — broad arXiv-style fields. Keys MUST match the backend taxonomy
// in src/paradigm/agents/topics.py. A paper/cycle can carry several (cross-
// pollination). `border` colors keep each pill readable on the dark theme.
export const TOPIC_LABELS: Record<string, string> = {
  astro: "Astro",
  physics: "Physics",
  cs: "CS",
  math: "Math",
  stat: "Stats",
  bio: "Bio",
  med: "Med",
  econ: "Econ",
  eess: "EESS",
  other: "Other",
};

export const TOPIC_COLORS: Record<string, string> = {
  astro: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
  physics: "bg-blue-500/15 text-blue-300 border-blue-500/30",
  cs: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  math: "bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/30",
  stat: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  bio: "bg-green-500/15 text-green-300 border-green-500/30",
  med: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  econ: "bg-teal-500/15 text-teal-300 border-teal-500/30",
  eess: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  other: "bg-slate-500/15 text-slate-300 border-slate-500/30",
};

export function getAgentRole(agentId: string): string {
  // Agent ids are `${role}-${index}` (e.g. "theorist-0"). The role is everything
  // before the trailing numeric index — NOT the index itself.
  const parts = agentId.split("-");
  if (parts.length > 1 && /^\d+$/.test(parts[parts.length - 1])) {
    return parts.slice(0, -1).join("-");
  }
  return agentId;
}

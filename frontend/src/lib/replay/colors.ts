/** Agent role colors (mirrors the terminal UI palette). */
const ROLE_COLORS: Record<string, string> = {
  theorist: "#6ba3f8",
  analyst: "#f0964c",
  experimentalist: "#46c98f",
  synthesizer: "#d877dd",
  skeptic: "#ef6464",
  writer: "#46c4d8",
  editor: "#e3c455",
};

export function agentColor(agentId: string | null | undefined): string {
  if (!agentId) return "#8d93a5";
  const role = agentId.replace(/-\d+$/, "");
  return ROLE_COLORS[role] ?? "#8d93a5";
}

export function agentShort(agentId: string | null | undefined): string {
  if (!agentId) return "engine";
  return agentId.replace(/-\d+$/, "");
}

export const STATUS_COLORS: Record<string, string> = {
  proposed: "#8d93a5",
  under_investigation: "#6ba3f8",
  supported: "#46c98f",
  contradicted: "#ef6464",
  refined: "#e3c455",
  abandoned: "#5a5f6e",
};

export const PHASE_LABELS: Record<string, string> = {
  seeding: "Seeding",
  ideation: "Ideation",
  planning: "Planning",
  pre_registration: "Pre-reg",
  execution: "Execution",
  verification: "Verify",
  post_execution: "Post-exec",
  writing: "Writing",
  internal: "Review",
  submitted: "Submitted",
  peer_review: "Peer Review",
  revision: "Revision",
  published: "Published",
  rejected: "Rejected",
};

import type { CaseStage } from "../../api/types";

export const CASE_STAGES: readonly CaseStage[] = [
  "new",
  "under_review",
  "documents_needed",
  "negotiating",
  "settled",
  "closed",
] as const;

export const STAGE_LABELS: Record<CaseStage, string> = {
  new: "New",
  under_review: "Under review",
  documents_needed: "Documents needed",
  negotiating: "Negotiating",
  settled: "Settled",
  closed: "Closed",
};

/** Plain-language "what's happening now" copy shown under the progress tracker. */
export const STAGE_EXPLANATIONS: Record<CaseStage, string> = {
  new: "We've received your case and our team is taking a first look. Nothing is needed from you right now — we'll be in touch soon.",
  under_review:
    "Our team is reviewing your answers and gathering the records that support your claim. Nothing is needed from you right now.",
  documents_needed:
    "We need a few documents from you to keep things moving — check the updates below and upload them in the documents section.",
  negotiating:
    "We're negotiating with the insurance company on your behalf. This back-and-forth can take a few rounds; we'll post every meaningful development here.",
  settled:
    "Your case has settled. We're completing the final paperwork and will confirm the details with you directly.",
  closed: "This case is closed. The full history stays available here whenever you need it.",
};

export function formatRange(min: number | null, max: number | null): string | null {
  if (min === null && max === null) return null;
  const fmt = (n: number) => `$${n.toLocaleString()}`;
  if (min !== null && max !== null) return `${fmt(min)} – ${fmt(max)}`;
  return fmt((min ?? max)!);
}

export function claimErrorMessage(code: string): string {
  switch (code) {
    case "token_used":
      return "This link has already been used. If you already created your account, just log in.";
    case "token_expired":
      return "This link has expired. Enter your email below and we'll send you a fresh one.";
    default:
      return "This link isn't valid. Enter your email below and we'll send you a new one.";
  }
}

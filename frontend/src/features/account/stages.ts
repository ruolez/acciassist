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

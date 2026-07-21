import type { CaseEstimateAdmin } from "../../api/types";

/** One line of the "how we got this number" breakdown. */
export type ReceiptRow = {
  id: string;
  label: string;
  /** Formatted figure shown on the right; empty for annotation-only rows. */
  amount: string;
  detail?: string;
  kind: "line" | "adjustment" | "deduction" | "total";
};

type Range = { low: number; high: number };

type AssemblyTrace = {
  specials?: { total?: number };
  general_damages?: { tier?: number; low?: number; high?: number; cap?: number | null };
  gross_before_liability?: Range;
  after_liability?: Range & { defendant_pct?: number; rule?: string | null };
  comps_anchor?: Range & { weighted_median?: number | null };
  width?: { value?: number; missing_driver_count?: number };
  adversarial_floor?: { pct_of_specials?: number | null; low?: number };
  policy_cap?: number | null;
};

const RULE_LABELS: Record<string, string> = {
  pure: "fault reduces the award proportionally in this state",
  modified_50: "being 50%+ at fault would bar recovery in this state",
  modified_51: "being 51%+ at fault would bar recovery in this state",
  contributory: "any fault can bar recovery entirely in this state",
};

function usd(n: number): string {
  return `$${Math.round(n).toLocaleString()}`;
}

function usdRange(low: number, high: number): string {
  return low === high ? usd(low) : `${usd(low)} – ${usd(high)}`;
}

function differs(a: Range | undefined, b: Range | undefined): boolean {
  if (!a || !b) return false;
  return Math.round(a.low) !== Math.round(b.low) || Math.round(a.high) !== Math.round(b.high);
}

/** Build the plain-language receipt from a completed estimate. Returns []
 * when there is nothing meaningful to show (gated result, missing trace). */
export function buildReceipt(estimate: CaseEstimateAdmin): ReceiptRow[] {
  const result = estimate.result;
  const trace = estimate.internals?.assembly_trace as AssemblyTrace | undefined;
  if (!result || result.gated || !trace) return [];
  const rows: ReceiptRow[] = [];

  const specialsTotal = trace.specials?.total;
  if (specialsTotal !== undefined) {
    rows.push({
      id: "specials",
      kind: "line",
      label: "Losses we can point to",
      amount: usd(specialsTotal),
      detail:
        "Medical bills, lost pay, and out-of-pocket costs — weighted down where documentation is missing.",
    });
  }

  const gen = trace.general_damages;
  if (gen?.low !== undefined && gen.high !== undefined) {
    const capped = gen.cap != null && gen.high >= gen.cap;
    rows.push({
      id: "general",
      kind: "line",
      label: "Pain & suffering",
      amount: usdRange(gen.low, gen.high),
      detail:
        `Injury severity ${gen.tier ?? "?"} of 5 sets the multiplier on documented medical losses` +
        (capped ? " (capped by state law)." : "."),
    });
  }

  const liability = trace.after_liability;
  if (liability && differs(liability, trace.gross_before_liability)) {
    const pct = liability.defendant_pct;
    const ruleNote = liability.rule ? RULE_LABELS[liability.rule] : undefined;
    rows.push({
      id: "fault",
      kind: "adjustment",
      label: "Adjusted for shared fault",
      amount: usdRange(liability.low, liability.high),
      detail:
        (pct !== undefined
          ? `The other side is held about ${Math.round(pct)}% at fault`
          : "Fault is shared") + (ruleNote ? ` — ${ruleNote}.` : "."),
    });
  }

  const comps = trace.comps_anchor;
  if (comps?.weighted_median != null && differs(comps, trace.after_liability)) {
    rows.push({
      id: "comps",
      kind: "adjustment",
      label: "Compared with similar cases",
      amount: usdRange(comps.low, comps.high),
      detail: `Pulled toward real reported outcomes for similar injuries (typical result ${usd(comps.weighted_median)}).`,
    });
  }

  const width = trace.width?.value;
  if (width !== undefined) {
    const missing = trace.width?.missing_driver_count ?? 0;
    rows.push({
      id: "uncertainty",
      kind: "adjustment",
      label: "Widened for what we don't know yet",
      amount: `±${Math.round(width * 100)}%`,
      detail:
        missing > 0
          ? `${missing} missing or undocumented fact${missing === 1 ? "" : "s"} make the range wider.`
          : "Reflects the natural spread across our evaluations.",
    });
  }

  if (trace.adversarial_floor?.pct_of_specials != null) {
    rows.push({
      id: "floor",
      kind: "adjustment",
      label: "Stress-tested against the defense",
      amount: "",
      detail:
        "A simulated insurance adjuster argued for the lowest defensible offer; the bottom of the range is anchored near it.",
    });
  }

  if (trace.policy_cap != null) {
    rows.push({
      id: "cap",
      kind: "adjustment",
      label: "Insurance policy limit",
      amount: usd(trace.policy_cap),
      detail: "The at-fault party's known insurance limits cap what can realistically be recovered.",
    });
  }

  // The row columns are the authoritative figures; `result` mirrors them but
  // may predate a schema change.
  const grossMin = estimate.gross_min ?? estimate.payout_min;
  const grossMax = estimate.gross_max ?? estimate.payout_max;
  if (grossMin != null && grossMax != null) {
    rows.push({
      id: "gross",
      kind: "total",
      label: "Estimated settlement range",
      amount: usdRange(grossMin, grossMax),
    });
  }

  if (result.fee_pct != null) {
    rows.push({
      id: "fee",
      kind: "deduction",
      label: `AcciAssist service fee (${result.fee_pct}%)`,
      amount: `− ${result.fee_pct}%`,
      detail: "Instead of an attorney's typical 33–40% contingency cut.",
    });
  }
  if (estimate.case_cost_min != null && estimate.case_cost_max != null) {
    rows.push({
      id: "costs",
      kind: "deduction",
      label: "Case costs",
      amount: `− ${usdRange(estimate.case_cost_min, estimate.case_cost_max)}`,
      detail: "Records retrieval, expert review, filing, and negotiation overhead.",
    });
  }
  rows.push({
    id: "liens",
    kind: "deduction",
    label: "Estimated medical liens",
    amount: "− varies",
    detail: "Health insurers are often entitled to repayment out of the settlement.",
  });
  if (estimate.net_min != null && estimate.net_max != null) {
    rows.push({
      id: "net",
      kind: "total",
      label: "Estimated in the client's pocket",
      amount: usdRange(estimate.net_min, estimate.net_max),
    });
  }

  return rows;
}

/** Plain-language confidence: "Medium · range ±18%". */
export function confidenceLabel(
  confidence: string | null,
  width: number | null | undefined,
): string {
  const word = confidence
    ? confidence.charAt(0).toUpperCase() + confidence.slice(1)
    : "—";
  return width != null ? `${word} · range ±${Math.round(width * 100)}%` : word;
}

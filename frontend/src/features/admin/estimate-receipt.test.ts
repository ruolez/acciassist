import { describe, expect, it } from "vitest";

import type { CaseEstimateAdmin, EstimateResult } from "../../api/types";
import { buildReceipt, confidenceLabel } from "./estimate-receipt";

function estimate(overrides: {
  result?: Partial<EstimateResult> | null;
  trace?: Record<string, unknown> | undefined;
}): CaseEstimateAdmin {
  const result: EstimateResult | null =
    overrides.result === null
      ? null
      : {
          gated: null,
          gross_min: 20000,
          gross_max: 45000,
          net_min: 9000,
          net_max: 24000,
          case_cost_min: 5000,
          case_cost_max: 15000,
          fee_pct: 33.3,
          width: 0.18,
          confidence: "medium",
          summary: "",
          drivers: [],
          reducers: [],
          improvements: [],
          warnings: [],
          disclaimer: "",
          ...overrides.result,
        };
  return {
    status: "completed",
    payout_min: 20000,
    payout_max: 45000,
    case_cost_min: 5000,
    case_cost_max: 15000,
    gross_min: 20000,
    gross_max: 45000,
    net_min: 9000,
    net_max: 24000,
    confidence: "medium",
    reasoning: null,
    missing_info: null,
    result,
    internals: overrides.trace ? { assembly_trace: overrides.trace } : {},
    stage_status: null,
    model: "m",
    error: null,
    updated_at: "2026-07-20T00:00:00Z",
  };
}

const FULL_TRACE = {
  specials: { total: 18400 },
  general_damages: { tier: 3, low: 55200, high: 82800, cap: null },
  gross_before_liability: { low: 73600, high: 101200 },
  after_liability: { low: 66240, high: 91080, defendant_pct: 90, rule: "pure" },
  comps_anchor: { weighted_median: 95000, low: 70000, high: 96000 },
  width: { value: 0.18, missing_driver_count: 2 },
  adversarial_floor: { pct_of_specials: 70, low: 20000 },
  policy_cap: null,
};

describe(buildReceipt, () => {
  it("builds the full story in order with formatted figures", () => {
    const rows = buildReceipt(estimate({ trace: FULL_TRACE }));
    expect(rows.map((r) => r.id)).toEqual([
      "specials", "general", "fault", "comps", "uncertainty", "floor",
      "gross", "fee", "costs", "liens", "net",
    ]);
    const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
    expect(byId.specials.amount).toBe("$18,400");
    expect(byId.general.amount).toBe("$55,200 – $82,800");
    expect(byId.general.detail).toContain("severity 3 of 5");
    expect(byId.fault.detail).toContain("90% at fault");
    expect(byId.uncertainty.amount).toBe("±18%");
    expect(byId.gross.amount).toBe("$20,000 – $45,000");
    expect(byId.gross.kind).toBe("total");
    expect(byId.fee.amount).toBe("− 33.3%");
    expect(byId.net.amount).toBe("$9,000 – $24,000");
  });

  it("omits fault, comps, floor and cap rows when they changed nothing", () => {
    const rows = buildReceipt(
      estimate({
        trace: {
          ...FULL_TRACE,
          after_liability: { ...FULL_TRACE.gross_before_liability, defendant_pct: 100,
                            rule: "pure" },
          comps_anchor: { weighted_median: null, low: 73600, high: 101200 },
          adversarial_floor: { pct_of_specials: null, low: 0 },
          policy_cap: null,
        },
      }),
    );
    const ids = rows.map((r) => r.id);
    expect(ids).not.toContain("fault");
    expect(ids).not.toContain("comps");
    expect(ids).not.toContain("floor");
    expect(ids).not.toContain("cap");
  });

  it("includes the policy cap row when limits capped the estimate", () => {
    const rows = buildReceipt(estimate({ trace: { ...FULL_TRACE, policy_cap: 25000 } }));
    const cap = rows.find((r) => r.id === "cap");
    expect(cap?.amount).toBe("$25,000");
  });

  it("returns nothing without a trace or for gated results", () => {
    expect(buildReceipt(estimate({ trace: undefined }))).toEqual([]);
    expect(
      buildReceipt(
        estimate({
          trace: FULL_TRACE,
          result: {
            gated: { code: "sol_expired", title: "t", explanation: "e" },
          },
        }),
      ),
    ).toEqual([]);
  });
});

describe(confidenceLabel, () => {
  it("spells out confidence with the range width", () => {
    expect(confidenceLabel("medium", 0.18)).toBe("Medium · range ±18%");
    expect(confidenceLabel(null, null)).toBe("—");
    expect(confidenceLabel("low", undefined)).toBe("Low");
  });
});

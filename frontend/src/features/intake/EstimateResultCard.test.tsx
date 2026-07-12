import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PublicEstimate } from "../../api/types";
import { EstimateResultCard } from "./EstimateResultCard";

const FALLBACK = { fallbackMin: 5000, fallbackMax: 25000, fallbackNote: "Static note." };

function completedEstimate(overrides: Partial<PublicEstimate> = {}): PublicEstimate {
  return {
    status: "completed",
    payout_min: 40000,
    payout_max: 90000,
    net_min: 18000,
    net_max: 51000,
    fee_pct_assumed: 33.3,
    drivers: ["You were rear-ended."],
    reducers: ["A treatment gap will be used against you."],
    improvements: ["Copies of your medical bills."],
    warnings: [
      {
        code: "sol_approaching",
        severity: "time_critical",
        message: "The filing deadline is near.",
        deadline: "2026-09-01",
      },
    ],
    gated: null,
    disclaimer: "This is not legal advice.",
    ...overrides,
  };
}

describe("EstimateResultCard", () => {
  it("shows the calculating placeholder while pending", () => {
    render(
      <EstimateResultCard estimate={undefined} calculating={true} {...FALLBACK} />,
    );
    expect(screen.getByText("Calculating your estimate…")).toBeInTheDocument();
  });

  it("renders gross, net, factors, warning and disclaimer for a pipeline result", () => {
    render(
      <EstimateResultCard
        estimate={completedEstimate()}
        calculating={false}
        {...FALLBACK}
      />,
    );
    expect(screen.getByText("$40,000 – $90,000")).toBeInTheDocument();
    expect(screen.getByText("$18,000 – $51,000")).toBeInTheDocument();
    expect(screen.getByText(/assumed 33.3% attorney fee/)).toBeInTheDocument();
    expect(screen.getByText("You were rear-ended.")).toBeInTheDocument();
    expect(screen.getByText("A treatment gap will be used against you.")).toBeInTheDocument();
    expect(screen.getByText("Copies of your medical bills.")).toBeInTheDocument();
    expect(screen.getByText(/filing deadline is near/)).toBeInTheDocument();
    expect(screen.getByText("This is not legal advice.")).toBeInTheDocument();
    expect(screen.queryByText("Static note.")).not.toBeInTheDocument();
  });

  it("renders the gate explanation without any dollar range when gated", () => {
    render(
      <EstimateResultCard
        estimate={completedEstimate({
          payout_min: 0,
          payout_max: 0,
          net_min: 0,
          net_max: 0,
          gated: {
            code: "sol_expired",
            title: "The filing deadline appears to have passed",
            explanation: "The claim is likely time-barred.",
          },
        })}
        calculating={false}
        {...FALLBACK}
      />,
    );
    expect(
      screen.getByText("The filing deadline appears to have passed"),
    ).toBeInTheDocument();
    expect(screen.getByText("The claim is likely time-barred.")).toBeInTheDocument();
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
  });

  it("falls back to the static range when the estimate failed", () => {
    render(
      <EstimateResultCard
        estimate={{ ...completedEstimate(), status: "failed" }}
        calculating={false}
        {...FALLBACK}
      />,
    );
    expect(screen.getByText("$5,000 – $25,000")).toBeInTheDocument();
    expect(screen.getByText("Static note.")).toBeInTheDocument();
  });

  it("shows a plain range for legacy completed rows without a pipeline result", () => {
    render(
      <EstimateResultCard
        estimate={{
          status: "completed",
          payout_min: 10000,
          payout_max: 30000,
          net_min: null,
          net_max: null,
          fee_pct_assumed: null,
          drivers: null,
          reducers: null,
          improvements: null,
          warnings: null,
          gated: null,
          disclaimer: null,
        }}
        calculating={false}
        {...FALLBACK}
      />,
    );
    expect(screen.getByText("$10,000 – $30,000")).toBeInTheDocument();
    expect(screen.getByText("Static note.")).toBeInTheDocument();
  });
});

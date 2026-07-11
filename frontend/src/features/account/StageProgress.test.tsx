import { render } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import type { CaseStage } from "../../api/types";
import { CASE_STAGES, claimErrorMessage, formatRange } from "./stages";
import { StageProgress } from "./StageProgress";

function stepStates(stage: CaseStage): string[] {
  const { container } = render(<StageProgress stage={stage} />);
  return Array.from(container.querySelectorAll(".stage-step")).map((el) => {
    if (el.classList.contains("current")) return "current";
    if (el.classList.contains("done")) return "done";
    return "todo";
  });
}

describe("StageProgress", () => {
  test("first stage: nothing done, first current", () => {
    expect(stepStates("new")).toEqual([
      "current",
      "todo",
      "todo",
      "todo",
      "todo",
      "todo",
    ]);
  });

  test("middle stage marks earlier steps done", () => {
    expect(stepStates("negotiating")).toEqual([
      "done",
      "done",
      "done",
      "current",
      "todo",
      "todo",
    ]);
  });

  test("terminal stage marks all earlier steps done", () => {
    expect(stepStates("closed")).toEqual([
      "done",
      "done",
      "done",
      "done",
      "done",
      "current",
    ]);
  });

  test("renders one step per stage", () => {
    const { container } = render(<StageProgress stage="new" />);
    expect(container.querySelectorAll(".stage-step")).toHaveLength(CASE_STAGES.length);
  });
});

describe("formatRange", () => {
  test("formats a full range with thousands separators", () => {
    expect(formatRange(5000, 25000)).toBe("$5,000 – $25,000");
  });

  test("returns null when both bounds are missing", () => {
    expect(formatRange(null, null)).toBeNull();
  });

  test("falls back to the single available bound", () => {
    expect(formatRange(null, 9000)).toBe("$9,000");
  });
});

describe("claimErrorMessage", () => {
  test("distinguishes used, expired, and invalid tokens", () => {
    const messages = ["token_used", "token_expired", "invalid_token"].map(claimErrorMessage);
    expect(new Set(messages).size).toBe(3);
    expect(messages[0]).toContain("already been used");
    expect(messages[1]).toContain("expired");
  });
});

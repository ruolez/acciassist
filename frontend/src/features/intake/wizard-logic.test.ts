import { describe, expect, it } from "vitest";

import type { IntakeStart, Question, QuestionType } from "../../api/types";
import {
  boundsError,
  isAnswered,
  isPageComplete,
  progressPercent,
  reconcileStoredState,
} from "./wizard-logic";

function makeQuestion(type: QuestionType, overrides: Partial<Question> = {}): Question {
  return {
    id: 1,
    slug: "q",
    type,
    prompt: "Q?",
    help_text: null,
    is_required: true,
    display_order: 0,
    page_group: null,
    config: {},
    options: [],
    ...overrides,
  };
}

describe("isAnswered", () => {
  it("treats a non-empty string as answered for text questions", () => {
    expect(isAnswered(makeQuestion("short_text"), "hello")).toBe(true);
  });

  it("treats whitespace-only text as unanswered", () => {
    expect(isAnswered(makeQuestion("short_text"), "   ")).toBe(false);
  });

  it("treats a non-empty array as answered for multi_choice", () => {
    expect(isAnswered(makeQuestion("multi_choice"), ["neck"])).toBe(true);
  });

  it("treats an empty array as unanswered for multi_choice", () => {
    expect(isAnswered(makeQuestion("multi_choice"), [])).toBe(false);
  });

  it("treats boolean false as a valid yes_no answer", () => {
    expect(isAnswered(makeQuestion("yes_no"), false)).toBe(true);
  });

  it("treats null as unanswered for yes_no", () => {
    expect(isAnswered(makeQuestion("yes_no"), null)).toBe(false);
  });

  it("treats 0 as a valid number answer", () => {
    expect(isAnswered(makeQuestion("number"), 0)).toBe(true);
  });
});

describe("isPageComplete", () => {
  it("requires all required questions to be answered", () => {
    const q1 = makeQuestion("short_text", { id: 1 });
    const q2 = makeQuestion("yes_no", { id: 2 });
    expect(isPageComplete([q1, q2], { 1: "x" })).toBe(false);
    expect(isPageComplete([q1, q2], { 1: "x", 2: true })).toBe(true);
  });

  it("ignores optional questions that are blank", () => {
    const required = makeQuestion("short_text", { id: 1, is_required: true });
    const optional = makeQuestion("short_text", { id: 2, is_required: false });
    expect(isPageComplete([required, optional], { 1: "x" })).toBe(true);
  });
});

describe("boundsError", () => {
  const bounded = makeQuestion("number", { config: { min: 1, max: 10 } });

  it("returns null for unanswered values", () => {
    expect(boundsError(bounded, null)).toBeNull();
  });

  it("flags numbers outside min/max, allows boundaries", () => {
    expect(boundsError(bounded, 0)).toBe("Enter a number of at least 1");
    expect(boundsError(bounded, 11)).toBe("Enter a number no higher than 10");
    expect(boundsError(bounded, 1)).toBeNull();
    expect(boundsError(bounded, 10)).toBeNull();
  });

  it("flags future dates when disallow_future is set", () => {
    const q = makeQuestion("date", { config: { disallow_future: true } });
    const future = new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10);
    expect(boundsError(q, future)).toBe("This date can't be in the future");
    expect(boundsError(q, "2020-01-15")).toBeNull();
  });

  it("ignores dates when disallow_future is not set", () => {
    const q = makeQuestion("date");
    expect(boundsError(q, "2999-01-01")).toBeNull();
  });

  it("flags text over max_length", () => {
    const q = makeQuestion("short_text", { config: { max_length: 5 } });
    expect(boundsError(q, "abcdef")).toBe("Keep it under 5 characters");
    expect(boundsError(q, "abcde")).toBeNull();
  });

  it("blocks page completion even for optional out-of-bounds answers", () => {
    const optional = makeQuestion("number", {
      id: 1,
      is_required: false,
      config: { min: 1 },
    });
    expect(isPageComplete([optional], { 1: 0 })).toBe(false);
    expect(isPageComplete([optional], {})).toBe(true);
  });
});

describe("progressPercent", () => {
  it("computes percentage from page index and total", () => {
    expect(progressPercent(0, 10)).toBe(0);
    expect(progressPercent(3, 10)).toBe(30);
  });

  it("returns 0 when there are no pages", () => {
    expect(progressPercent(0, 0)).toBe(0);
  });
});

describe("reconcileStoredState", () => {
  const opt = (value: string) => ({ id: 0, label: value, value, display_order: 0 });
  const freshStart = (questions: Question[]): IntakeStart => ({
    session_id: "s",
    injury_type: {
      id: 1,
      slug: "t",
      name: "T",
      description: null,
      display_order: 0,
      is_published: true,
    },
    pages: questions.map((q, i) => ({ page_index: i, questions: [q] })),
    total_pages: questions.length,
  });

  it("drops answers for questions that no longer exist", () => {
    const fresh = freshStart([makeQuestion("yes_no", { id: 1 })]);
    const result = reconcileStoredState({ 1: true, 99: "gone" }, 0, fresh);
    expect(result.answers).toEqual({ 1: true });
  });

  it("drops a single_choice answer whose option value was removed", () => {
    const q = makeQuestion("single_choice", { id: 1, options: [opt("store"), opt("home")] });
    const result = reconcileStoredState({ 1: "sidewalk" }, 0, freshStart([q]));
    expect(result.answers).toEqual({});
  });

  it("filters multi_choice answers to surviving option values", () => {
    const q = makeQuestion("multi_choice", { id: 1, options: [opt("neck"), opt("back")] });
    const result = reconcileStoredState({ 1: ["neck", "knee"] }, 0, freshStart([q]));
    expect(result.answers).toEqual({ 1: ["neck"] });
  });

  it("drops a multi_choice answer when no selected value survives", () => {
    const q = makeQuestion("multi_choice", { id: 1, options: [opt("neck")] });
    const result = reconcileStoredState({ 1: ["knee"] }, 0, freshStart([q]));
    expect(result.answers).toEqual({});
  });

  it("clamps a page index that is beyond the current page count", () => {
    const fresh = freshStart([makeQuestion("yes_no", { id: 1 })]);
    expect(reconcileStoredState({}, 5, fresh).pageIndex).toBe(0);
  });
});

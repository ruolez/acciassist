import { describe, expect, it } from "vitest";

import type { Question, QuestionType } from "../../api/types";
import { isAnswered, isPageComplete, progressPercent } from "./wizard-logic";

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

describe("progressPercent", () => {
  it("computes percentage from page index and total", () => {
    expect(progressPercent(0, 10)).toBe(0);
    expect(progressPercent(3, 10)).toBe(30);
  });

  it("returns 0 when there are no pages", () => {
    expect(progressPercent(0, 0)).toBe(0);
  });
});

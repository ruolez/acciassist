import { describe, expect, it } from "vitest";

import { findUnknownTokens } from "./template-tokens";

const known = new Set(["what-happened", "pain_level"]);

describe("findUnknownTokens", () => {
  it("flags tokens matching no question slug", () => {
    expect(findUnknownTokens("Story: {{what-hapened}}", known)).toEqual(["what-hapened"]);
  });

  it("does not flag known slugs, including whitespace variants", () => {
    expect(
      findUnknownTokens("A {{what-happened}} B {{ pain_level }}", known),
    ).toEqual([]);
  });

  it("dedupes repeated unknown tokens and keeps appearance order", () => {
    expect(
      findUnknownTokens("{{zzz}} {{aaa}} {{zzz}}", known),
    ).toEqual(["zzz", "aaa"]);
  });

  it("returns nothing for a body without tokens", () => {
    expect(findUnknownTokens("plain prose only", known)).toEqual([]);
  });
});

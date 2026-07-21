import { describe, expect, test } from "vitest";

import { formatBytes, humanize, relativeTime } from "./format";

describe("humanize", () => {
  test.each([
    ["in_progress", "In progress"],
    ["lead_received", "Lead received"],
    ["completed", "Completed"],
    ["stage_changed", "Stage changed"],
  ])("turns %s into %s", (raw, expected) => {
    expect(humanize(raw)).toBe(expected);
  });
});

describe("formatBytes", () => {
  test.each([
    [512, "512 B"],
    [2048, "2 KB"],
    [1_468_006, "1.4 MB"],
  ])("renders %d bytes as %s", (bytes, expected) => {
    expect(formatBytes(bytes)).toBe(expected);
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-07-20T12:00:00Z");
  const at = (isoOffsetMs: number) => new Date(now.getTime() - isoOffsetMs).toISOString();

  test.each([
    [30_000, "just now"],
    [5 * 60_000, "5m ago"],
    [3 * 3_600_000, "3h ago"],
    [24 * 3_600_000, "1 day ago"],
    [3 * 24 * 3_600_000, "3 days ago"],
  ])("renders an offset of %dms as %s", (offset, expected) => {
    expect(relativeTime(at(offset), now)).toBe(expected);
  });

  test("falls back to a locale date beyond a week", () => {
    const old = new Date("2026-06-01T12:00:00Z");
    expect(relativeTime(old.toISOString(), now)).toBe(old.toLocaleDateString());
  });
});

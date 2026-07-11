import { describe, expect, it } from "vitest";

import type { Question } from "../../api/types";
import { groupIntoPages, mergeWithNext, moveQuestion, splitPage, toPayload } from "./page-layout";

function q(id: number, displayOrder: number, pageGroup: number | null): Question {
  return {
    id,
    slug: `q${id}`,
    type: "short_text",
    prompt: `Q${id}?`,
    help_text: null,
    is_required: true,
    display_order: displayOrder,
    page_group: pageGroup,
    config: {},
    options: [],
  };
}

const ids = (pages: Question[][]) => pages.map((p) => p.map((x) => x.id));

describe("groupIntoPages", () => {
  it("puts null-group questions on their own pages, even consecutive ones", () => {
    expect(ids(groupIntoPages([q(1, 0, null), q(2, 1, null)]))).toEqual([[1], [2]]);
  });

  it("merges consecutive questions sharing a group", () => {
    expect(ids(groupIntoPages([q(1, 0, 1), q(2, 1, 1), q(3, 2, null)]))).toEqual([
      [1, 2],
      [3],
    ]);
  });

  it("does not merge the same group value across a break", () => {
    expect(ids(groupIntoPages([q(1, 0, 1), q(2, 1, null), q(3, 2, 1)]))).toEqual([
      [1],
      [2],
      [3],
    ]);
  });

  it("sorts by display_order before grouping", () => {
    expect(ids(groupIntoPages([q(2, 5, null), q(1, 0, null)]))).toEqual([[1], [2]]);
  });
});

describe("moveQuestion", () => {
  const pages = [[q(1, 0, null)], [q(2, 1, 1), q(3, 2, 1)], [q(4, 3, null)]];

  it("moves a question into the target's page", () => {
    expect(moveQuestion(pages, 1, 3)).toEqual([[2, 3, 1], [4]]);
  });

  it("moving upward inserts before the target", () => {
    expect(moveQuestion(pages, 4, 2)).toEqual([[1], [4, 2, 3]]);
  });

  it("drops a page emptied by the move", () => {
    expect(moveQuestion(pages, 1, 2)).toEqual([[2, 1, 3], [4]]);
  });

  it("no-ops when dropped on itself", () => {
    expect(moveQuestion(pages, 2, 2)).toEqual([[1], [2, 3], [4]]);
  });
});

describe("splitPage / mergeWithNext", () => {
  const pages = [[q(1, 0, 0), q(2, 1, 0), q(3, 2, 0)], [q(4, 3, null)]];

  it("splits a page after the given position", () => {
    expect(splitPage(pages, 0, 0)).toEqual([[1], [2, 3], [4]]);
    expect(splitPage(pages, 0, 1)).toEqual([[1, 2], [3], [4]]);
  });

  it("ignores splits at the page end or out of range", () => {
    expect(splitPage(pages, 0, 2)).toEqual([[1, 2, 3], [4]]);
    expect(splitPage(pages, 5, 0)).toEqual([[1, 2, 3], [4]]);
  });

  it("merges a page with the next one", () => {
    expect(mergeWithNext(pages, 0)).toEqual([[1, 2, 3, 4]]);
  });

  it("ignores merging the last page", () => {
    expect(mergeWithNext(pages, 1)).toEqual([[1, 2, 3], [4]]);
  });
});

describe("toPayload", () => {
  it("round-trips groupIntoPages output into the endpoint shape", () => {
    const questions = [q(1, 0, null), q(2, 1, 7), q(3, 2, 7)];
    expect(toPayload(groupIntoPages(questions))).toEqual([[1], [2, 3]]);
  });
});

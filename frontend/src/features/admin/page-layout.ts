import type { Question } from "../../api/types";

/** TS mirror of the backend build_pages: sort by display_order, group
 * consecutive runs of the same non-null page_group; null = own page. */
export function groupIntoPages(questions: Question[]): Question[][] {
  const sorted = [...questions].sort((a, b) => a.display_order - b.display_order);
  const pages: Question[][] = [];
  let currentGroup: number | null = null;
  for (const q of sorted) {
    if (q.page_group !== null && q.page_group === currentGroup && pages.length > 0) {
      pages[pages.length - 1].push(q);
    } else {
      pages.push([q]);
      currentGroup = q.page_group;
    }
  }
  return pages;
}

/** Layout as id pages — the layout endpoint's payload shape. */
export function toPayload(pages: Question[][]): number[][] {
  return pages.map((page) => page.map((q) => q.id));
}

function dropEmpty(pages: number[][]): number[][] {
  return pages.filter((page) => page.length > 0);
}

/** Move a dragged question next to the question it was dropped on; the moved
 * question joins the target's page. Returns id pages. */
export function moveQuestion(
  pages: Question[][],
  activeId: number,
  overId: number,
): number[][] {
  if (activeId === overId) return toPayload(pages);
  const idPages = toPayload(pages).map((page) => page.filter((id) => id !== activeId));
  for (const page of idPages) {
    const overIndex = page.indexOf(overId);
    if (overIndex !== -1) {
      // Insert after the target when the drag came from earlier in the flat
      // order, before it otherwise — matches how a vertical list feels.
      const flatBefore = pages.flat().map((q) => q.id);
      const cameFromAbove = flatBefore.indexOf(activeId) < flatBefore.indexOf(overId);
      page.splice(cameFromAbove ? overIndex + 1 : overIndex, 0, activeId);
      break;
    }
  }
  return dropEmpty(idPages);
}

/** Split a page in two after position `afterPos` (0-based, within the page). */
export function splitPage(
  pages: Question[][],
  pageIndex: number,
  afterPos: number,
): number[][] {
  const idPages = toPayload(pages);
  const page = idPages[pageIndex];
  if (!page || afterPos < 0 || afterPos >= page.length - 1) return idPages;
  idPages.splice(pageIndex, 1, page.slice(0, afterPos + 1), page.slice(afterPos + 1));
  return idPages;
}

/** Merge a page with the one after it. */
export function mergeWithNext(pages: Question[][], pageIndex: number): number[][] {
  const idPages = toPayload(pages);
  if (pageIndex < 0 || pageIndex >= idPages.length - 1) return idPages;
  idPages.splice(pageIndex, 2, [...idPages[pageIndex], ...idPages[pageIndex + 1]]);
  return idPages;
}

from collections.abc import Sequence
from typing import Protocol


class _Pageable(Protocol):
    display_order: int
    page_group: int | None


def build_pages(questions: Sequence[_Pageable]) -> list[list[_Pageable]]:
    """Group ordered questions into wizard pages.

    Questions are first sorted by ``display_order``. A question with a null
    ``page_group`` always gets its own page. Consecutive questions sharing the
    same non-null ``page_group`` are shown together on one page.
    """
    ordered = sorted(questions, key=lambda q: q.display_order)
    pages: list[list[_Pageable]] = []
    current_group: int | None = None
    for q in ordered:
        if q.page_group is not None and q.page_group == current_group and pages:
            pages[-1].append(q)
        else:
            pages.append([q])
            current_group = q.page_group
    return pages

from dataclasses import dataclass

from app.services.pagination import build_pages


@dataclass
class FakeQ:
    display_order: int
    page_group: int | None


class TestBuildPages:
    def test_null_groups_each_get_own_page(self):
        qs = [FakeQ(0, None), FakeQ(1, None), FakeQ(2, None)]
        assert build_pages(qs) == [[qs[0]], [qs[1]], [qs[2]]]

    def test_same_group_shares_one_page(self):
        a, b, c = FakeQ(0, 1), FakeQ(1, 1), FakeQ(2, None)
        assert build_pages([a, b, c]) == [[a, b], [c]]

    def test_orders_by_display_order_before_grouping(self):
        a, b = FakeQ(2, None), FakeQ(0, None)
        assert build_pages([a, b]) == [[b], [a]]

    def test_distinct_groups_split(self):
        a, b = FakeQ(0, 1), FakeQ(1, 2)
        assert build_pages([a, b]) == [[a], [b]]

    def test_non_consecutive_same_group_value_does_not_merge_across_break(self):
        # group 1, then a solo null, then group 1 again -> three pages
        a, b, c = FakeQ(0, 1), FakeQ(1, None), FakeQ(2, 1)
        assert build_pages([a, b, c]) == [[a], [b], [c]]

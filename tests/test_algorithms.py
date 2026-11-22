import random
import unittest
from dataclasses import dataclass
from datetime import date

from splitmate.core.algorithms import (
    bubble_sort, contains_ignore_case, equals_ignore_case, linear_search_all, linear_search_first,
)


@dataclass
class Rec:
    name: str
    total: int = 0
    when: date = date(2026, 1, 1)


class SubstringTests(unittest.TestCase):
    def test_contains(self):
        cases = [
            ("Warung Padang", "padang", True), ("Warung Padang", "WARUNG", True), ("Warung Padang", "ung pa", True),
            ("Warung Padang", "padangs", False), ("aaab", "aab", True), ("aaab", "abb", False),
            ("abc", "abcd", False), ("abc", "", True), ("", "", True), ("", "a", False),
            ("  spaced   out ", "spaced out", True), (None, "x", False), (None, "", True),
        ]
        for text, query, expected in cases:
            with self.subTest(text=text, query=query):
                self.assertEqual(contains_ignore_case(text, query), expected)

    def test_equals(self):
        self.assertTrue(equals_ignore_case("  Dina ", "dina"))
        self.assertTrue(equals_ignore_case("Dina  Putri", "dina putri"))
        self.assertFalse(equals_ignore_case("Dina", "Dinah"))


class LinearSearchTests(unittest.TestCase):
    def setUp(self):
        self.records = [Rec("Warung Padang"), Rec("Kopi Sore"), Rec("Pecel Lele"), Rec("Padang Hijau"), Rec("Bakso")]

    def test_first_returns_earliest_match(self):
        self.assertIs(linear_search_first(self.records, lambda r: r.name, "padang"), self.records[0])

    def test_first_none_when_absent(self):
        self.assertIsNone(linear_search_first(self.records, lambda r: r.name, "sushi"))

    def test_all_keeps_original_order(self):
        found = linear_search_all(self.records, lambda r: r.name, "padang")
        self.assertEqual([r.name for r in found], ["Warung Padang", "Padang Hijau"])

    def test_empty_query_matches_everything(self):
        self.assertEqual(len(linear_search_all(self.records, lambda r: r.name, "")), 5)
        self.assertEqual(len(linear_search_all(self.records, lambda r: r.name, "   ")), 5)

    def test_exact_mode_whole_string_only(self):
        self.assertIsNone(linear_search_first(self.records, lambda r: r.name, "Kopi", exact=True))
        self.assertIs(linear_search_first(self.records, lambda r: r.name, " kopi sore ", exact=True), self.records[1])

    def test_empty_list(self):
        self.assertIsNone(linear_search_first([], lambda r: r.name, "x"))
        self.assertEqual(linear_search_all([], lambda r: r.name, "x"), [])

    def test_does_not_modify_input(self):
        before = list(self.records)
        linear_search_all(self.records, lambda r: r.name, "a")
        self.assertEqual(self.records, before)

    def test_agrees_with_builtin_oracle_on_random_data(self):
        rng = random.Random(7)
        alphabet = "ab c"
        words = ["".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8))) for _ in range(300)]
        records = [Rec(w) for w in words]
        for _ in range(200):
            query = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 3)))
            norm_q = " ".join(query.split()).casefold()
            expected = [r for r in records if norm_q in " ".join(r.name.split()).casefold()]
            self.assertEqual(linear_search_all(records, lambda r: r.name, query), expected)


class BubbleSortTests(unittest.TestCase):
    def test_ascending_and_descending(self):
        data = [5, 2, 9, 1, 5, 6]
        self.assertEqual(bubble_sort(data, key=lambda x: x), [1, 2, 5, 5, 6, 9])
        self.assertEqual(bubble_sort(data, key=lambda x: x, descending=True), [9, 6, 5, 5, 2, 1])

    def test_edge_sizes(self):
        self.assertEqual(bubble_sort([], key=lambda x: x), [])
        self.assertEqual(bubble_sort([3], key=lambda x: x), [3])
        self.assertEqual(bubble_sort([2, 1], key=lambda x: x), [1, 2])

    def test_already_sorted_and_reversed(self):
        self.assertEqual(bubble_sort([1, 2, 3, 4], key=lambda x: x), [1, 2, 3, 4])
        self.assertEqual(bubble_sort([4, 3, 2, 1], key=lambda x: x), [1, 2, 3, 4])

    def test_input_not_mutated(self):
        data = [3, 1, 2]
        bubble_sort(data, key=lambda x: x)
        self.assertEqual(data, [3, 1, 2])

    def test_stable_for_equal_keys(self):
        records = [Rec("a", 10), Rec("b", 5), Rec("c", 10), Rec("d", 5), Rec("e", 10)]
        asc = bubble_sort(records, key=lambda r: r.total)
        self.assertEqual([r.name for r in asc], ["b", "d", "a", "c", "e"])
        desc = bubble_sort(records, key=lambda r: r.total, descending=True)
        self.assertEqual([r.name for r in desc], ["a", "c", "e", "b", "d"])

    def test_sorts_by_date_objects_not_text(self):
        records = [Rec("x", when=date(2026, 11, 9)), Rec("y", when=date(2026, 11, 18)), Rec("z", when=date(2025, 12, 31))]
        asc = bubble_sort(records, key=lambda r: r.when)
        self.assertEqual([r.name for r in asc], ["z", "x", "y"])

    def test_matches_builtin_sorted_on_random_data(self):
        rng = random.Random(42)
        for _ in range(300):
            data = [rng.randint(-50, 50) for _ in range(rng.randint(0, 40))]
            self.assertEqual(bubble_sort(data, key=lambda x: x), sorted(data))
            self.assertEqual(bubble_sort(data, key=lambda x: x, descending=True), sorted(data, reverse=True))

    def test_matches_stable_builtin_for_records(self):
        rng = random.Random(3)
        records = [Rec(str(i), rng.randint(0, 5)) for i in range(60)]
        self.assertEqual(bubble_sort(records, key=lambda r: r.total), sorted(records, key=lambda r: r.total))
        self.assertEqual(
            bubble_sort(records, key=lambda r: r.total, descending=True),
            sorted(records, key=lambda r: r.total, reverse=True),
        )


if __name__ == "__main__":
    unittest.main()

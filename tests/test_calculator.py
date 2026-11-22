import random
import unittest
from fractions import Fraction

from splitmate.core.calculator import build_payments, distribute, expected_total, reconcile, split_item
from splitmate.core.errors import CalculationError
from splitmate.core.models import Assignment, Item, SplitMode, Transaction

from .helpers import DINA, RAKA, SARI, make_group, make_worked_example

ORDER = [DINA, RAKA, SARI]


class DistributeTests(unittest.TestCase):
    def test_equal_thirds_extra_rupiah_goes_to_first(self):
        self.assertEqual(distribute(10000, [1, 1, 1]), [3334, 3333, 3333])
        self.assertEqual(distribute(10, [1, 1, 1]), [4, 3, 3])
        self.assertEqual(distribute(11, [1, 1, 1]), [4, 4, 3])

    def test_worked_example_charges(self):
        weights = [37334, 34333, 41333]
        self.assertEqual(distribute(5650, weights), [1867, 1717, 2066])
        self.assertEqual(distribute(11865, weights), [3920, 3605, 4340])
        self.assertEqual(distribute(-15, weights), [-5, -5, -5])

    def test_zero_amount(self):
        self.assertEqual(distribute(0, [3, 4]), [0, 0])
        self.assertEqual(distribute(0, [0, 0]), [0, 0])
        self.assertEqual(distribute(0, []), [])

    def test_zero_weight_member_gets_nothing(self):
        self.assertEqual(distribute(100, [0, 1, 1]), [0, 50, 50])
        self.assertEqual(distribute(101, [0, 1, 1]), [0, 51, 50])

    def test_single_member_gets_everything(self):
        self.assertEqual(distribute(12345, [999]), [12345])

    def test_negative_amount_mirrors_positive(self):
        for weights in ([1, 1, 1], [5, 3, 2], [7, 1]):
            positive = distribute(1001, weights)
            self.assertEqual(distribute(-1001, weights), [-x for x in positive])

    def test_errors(self):
        with self.assertRaises(CalculationError):
            distribute(100, [0, 0])
        with self.assertRaises(CalculationError):
            distribute(100, [])
        with self.assertRaises(CalculationError):
            distribute(100, [1, -1])
        for bad_amount in (1.5, "100", True):
            with self.subTest(bad=bad_amount), self.assertRaises(CalculationError):
                distribute(bad_amount, [1, 1])
        with self.assertRaises(CalculationError):
            distribute(100, [1.0, 1])

    def test_property_sum_exact_and_each_share_is_floor_or_ceiling(self):
        rng = random.Random(2026)
        for _ in range(3000):
            n = rng.randint(1, 7)
            weights = [rng.choice([0, 0, rng.randint(1, 200000)]) for _ in range(n)]
            if sum(weights) == 0:
                weights[0] = rng.randint(1, 1000)
            amount = rng.randint(-100000, 5000000)
            result = distribute(amount, weights)
            self.assertEqual(sum(result), amount)
            total = sum(weights)
            for share, weight in zip(result, weights):
                exact = Fraction(amount * weight, total)
                self.assertLess(abs(Fraction(share) - exact), 1, (amount, weights, result))
                if weight == 0:
                    self.assertEqual(share, 0)


class SplitItemTests(unittest.TestCase):
    def test_equal_split_remainder_to_earliest_joined(self):
        item = Item("i", "Sambal", 10000, 1, SplitMode.EQUAL, [Assignment(SARI), Assignment(DINA), Assignment(RAKA)])
        self.assertEqual(split_item(item, ORDER), {DINA: 3334, RAKA: 3333, SARI: 3333})

    def test_equal_split_two_of_three_members(self):
        item = Item("i", "Pizza", 30000, 1, SplitMode.EQUAL, [Assignment(RAKA), Assignment(SARI)])
        self.assertEqual(split_item(item, ORDER), {RAKA: 15000, SARI: 15000})

    def test_equal_split_uses_total_price_for_quantity_above_one(self):
        item = Item("i", "Es Teh", 6000, 3, SplitMode.EQUAL, [Assignment(DINA), Assignment(RAKA)])
        self.assertEqual(split_item(item, ORDER), {DINA: 9000, RAKA: 9000})

    def test_by_quantity(self):
        item = Item("i", "Es Teh", 6000, 3, SplitMode.BY_QUANTITY, [Assignment(RAKA, 2), Assignment(DINA, 1)])
        self.assertEqual(split_item(item, ORDER), {DINA: 6000, RAKA: 12000})

    def test_by_quantity_must_assign_every_unit(self):
        item = Item("i", "Es Teh", 6000, 3, SplitMode.BY_QUANTITY, [Assignment(DINA, 1), Assignment(RAKA, 1)])
        with self.assertRaises(CalculationError):
            split_item(item, ORDER)

    def test_by_quantity_over_assigned(self):
        item = Item("i", "Es Teh", 6000, 3, SplitMode.BY_QUANTITY, [Assignment(DINA, 3), Assignment(RAKA, 1)])
        with self.assertRaises(CalculationError):
            split_item(item, ORDER)

    def test_by_quantity_needs_positive_quantities(self):
        item = Item("i", "Es Teh", 6000, 2, SplitMode.BY_QUANTITY, [Assignment(DINA, 2), Assignment(RAKA, 0)])
        with self.assertRaises(CalculationError):
            split_item(item, ORDER)
        item = Item("i", "Es Teh", 6000, 2, SplitMode.BY_QUANTITY, [Assignment(DINA, 2), Assignment(RAKA, None)])
        with self.assertRaises(CalculationError):
            split_item(item, ORDER)

    def test_unassigned_duplicate_and_unknown_member(self):
        with self.assertRaises(CalculationError):
            split_item(Item("i", "X", 1000, 1), ORDER)
        with self.assertRaises(CalculationError):
            split_item(Item("i", "X", 1000, 1, SplitMode.EQUAL, [Assignment(DINA), Assignment(DINA)]), ORDER)
        with self.assertRaises(CalculationError):
            split_item(Item("i", "X", 1000, 1, SplitMode.EQUAL, [Assignment("mem_ghost")]), ORDER)

    def test_zero_priced_item(self):
        item = Item("i", "Free dessert", 0, 1, SplitMode.EQUAL, [Assignment(DINA), Assignment(RAKA)])
        self.assertEqual(split_item(item, ORDER), {DINA: 0, RAKA: 0})


class BuildPaymentsTests(unittest.TestCase):
    def test_worked_example_matches_design_document(self):
        tx = make_worked_example()
        payments = build_payments(tx, ORDER)
        self.assertEqual([p.member_id for p in payments], ORDER)
        self.assertEqual([p.subtotal for p in payments], [37334, 34333, 41333])
        self.assertEqual([p.service_share for p in payments], [1867, 1717, 2066])
        self.assertEqual([p.tax_share for p in payments], [3920, 3605, 4340])
        self.assertEqual([p.rounding_share for p in payments], [-5, -5, -5])
        self.assertEqual([p.discount_share for p in payments], [0, 0, 0])
        self.assertEqual([p.total for p in payments], [43116, 39650, 47734])
        self.assertEqual(sum(p.total for p in payments), tx.grand_total)
        self.assertEqual(reconcile(tx), 0)
        self.assertEqual(expected_total(tx), 130500)

    def test_discount_is_deducted_proportionally(self):
        tx = make_worked_example()
        tx.discount = 10000
        tx.grand_total = expected_total(tx)
        payments = build_payments(tx, ORDER)
        self.assertEqual(sum(p.discount_share for p in payments), 10000)
        self.assertEqual(sum(p.total for p in payments), tx.grand_total)
        self.assertEqual(reconcile(tx), 0)
        # larger spender gets the larger discount share
        self.assertGreater(payments[2].discount_share, payments[1].discount_share)

    def test_member_with_no_items_is_not_charged(self):
        tx = Transaction("t", "g", "Two of three", "2026-11-18", items=[
            Item("a", "Rice", 20000, 1, SplitMode.EQUAL, [Assignment(DINA)]),
            Item("b", "Tea", 10000, 1, SplitMode.EQUAL, [Assignment(RAKA)]),
        ], tax=3000, grand_total=33000)
        payments = build_payments(tx, ORDER)
        self.assertEqual([p.member_id for p in payments], [DINA, RAKA])
        self.assertEqual([p.total for p in payments], [22000, 11000])

    def test_unassigned_item_blocks_calculation(self):
        with self.assertRaises(CalculationError):
            build_payments(make_worked_example(assign_last_item=False), ORDER)

    def test_zero_subtotal_blocks_calculation(self):
        tx = Transaction("t", "g", "Free", "2026-11-18", items=[
            Item("a", "Freebie", 0, 1, SplitMode.EQUAL, [Assignment(DINA)])], tax=100, grand_total=100)
        with self.assertRaises(CalculationError):
            build_payments(tx, ORDER)

    def test_negative_charges_rejected(self):
        tx = make_worked_example()
        tx.tax = -1
        with self.assertRaises(CalculationError):
            build_payments(tx, ORDER)

    def test_reconcile_reports_direction_and_size(self):
        tx = make_worked_example()
        tx.grand_total = 131500
        self.assertEqual(reconcile(tx), 1000)
        tx.grand_total = 130000
        self.assertEqual(reconcile(tx), -500)

    def test_property_payments_always_sum_to_expected_total(self):
        rng = random.Random(99)
        for trial in range(1500):
            member_ids = [f"m{i}" for i in range(rng.randint(2, 6))]
            items = []
            for index in range(rng.randint(1, 6)):
                quantity = rng.randint(1, 4)
                chosen = rng.sample(member_ids, rng.randint(1, len(member_ids)))
                if quantity > 1 and rng.random() < 0.5:
                    remaining, assignments = quantity, []
                    for member in chosen:
                        if remaining == 0:
                            break
                        take = rng.randint(1, remaining)
                        assignments.append(Assignment(member, take))
                        remaining -= take
                    if remaining:
                        assignments[0].quantity += remaining
                    items.append(Item(f"i{index}", "x", rng.randint(0, 90000), quantity, SplitMode.BY_QUANTITY, assignments))
                else:
                    items.append(Item(f"i{index}", "x", rng.randint(0, 90000), quantity, SplitMode.EQUAL,
                                      [Assignment(m) for m in chosen]))
            if sum(i.total_price for i in items) == 0:
                items[0].unit_price = 1000
            tx = Transaction("t", "g", "random", "2026-11-18", items=items,
                             discount=rng.choice([0, rng.randint(0, 20000)]),
                             service_charge=rng.randint(0, 30000), tax=rng.randint(0, 40000),
                             rounding_adjustment=rng.randint(-99, 99))
            payments = build_payments(tx, member_ids)
            self.assertEqual(sum(p.total for p in payments), expected_total(tx), trial)
            self.assertEqual(sum(p.subtotal for p in payments), tx.subtotal)
            self.assertEqual(sum(p.service_share for p in payments), tx.service_charge)
            self.assertEqual(sum(p.tax_share for p in payments), tx.tax)
            self.assertEqual(sum(p.discount_share for p in payments), tx.discount)
            self.assertEqual(sum(p.rounding_share for p in payments), tx.rounding_adjustment)


if __name__ == "__main__":
    unittest.main()

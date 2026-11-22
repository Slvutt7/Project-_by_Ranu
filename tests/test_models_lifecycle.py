import unittest

from splitmate.core.errors import (
    CalculationError, DuplicateMemberError, FinalizationError, RemovedMemberError, ValidationError,
)
from splitmate.core.lifecycle import complete_transaction, derive_status, finalization_blockers, reopen_for_edit
from splitmate.core.models import Assignment, Group, Item, Member, SplitMode, Status, Transaction

from .helpers import DINA, RAKA, SARI, STAMP, make_group, make_worked_example


class GroupTests(unittest.TestCase):
    def test_add_member_and_duplicate_prevention(self):
        group = Group("g", "Kost")
        member = group.add_member("mem_1", "  Dina   Putri ", STAMP)
        self.assertEqual(member.name, "Dina Putri")
        with self.assertRaises(DuplicateMemberError) as ctx:
            group.add_member("mem_2", "dina putri", STAMP)
        self.assertNotIsInstance(ctx.exception, RemovedMemberError)
        self.assertEqual(len(group.members), 1)

    def test_removed_member_name_offers_restore(self):
        group = make_group()
        group.deactivate_member(DINA)
        with self.assertRaises(RemovedMemberError) as ctx:
            group.add_member("mem_new", "Dina", STAMP)
        self.assertEqual(ctx.exception.member.member_id, DINA)
        group.restore_member(DINA)
        self.assertTrue(group.find_member_by_id(DINA).active)

    def test_blank_and_overlong_names(self):
        group = Group("g", "Kost")
        for bad in ("", "   ", None, "x" * 51):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                group.add_member("m", bad, STAMP)

    def test_deactivate_keeps_member_and_order(self):
        group = make_group()
        group.deactivate_member(RAKA)
        self.assertEqual([m.name for m in group.active_members()], ["Dina", "Sari"])
        self.assertEqual(group.member_order(), [DINA, RAKA, SARI])
        with self.assertRaises(ValidationError):
            group.deactivate_member("mem_ghost")

    def test_search_members(self):
        group = make_group()
        self.assertEqual([m.name for m in group.search_members("a")], ["Dina", "Raka", "Sari"])
        self.assertEqual([m.name for m in group.search_members("sar")], ["Sari"])
        group.deactivate_member(SARI)
        self.assertEqual(group.search_members("sar"), [])
        self.assertEqual([m.name for m in group.search_members("sar", include_removed=True)], ["Sari"])

    def test_dict_round_trip(self):
        group = make_group()
        group.deactivate_member(RAKA)
        self.assertEqual(Group.from_dict(group.to_dict()), group)


class ItemTests(unittest.TestCase):
    def test_total_price(self):
        self.assertEqual(Item("i", "Tea", 6000, 3).total_price, 18000)

    def test_assignment_states(self):
        equal = Item("i", "x", 100, 2, SplitMode.EQUAL)
        self.assertFalse(equal.is_fully_assigned())
        equal.assignments = [Assignment(DINA)]
        self.assertTrue(equal.is_fully_assigned())

        by_qty = Item("i", "x", 100, 3, SplitMode.BY_QUANTITY, [Assignment(DINA, 2)])
        self.assertFalse(by_qty.is_fully_assigned())
        self.assertEqual(by_qty.assigned_units(), 2)
        by_qty.assignments.append(Assignment(RAKA, 1))
        self.assertTrue(by_qty.is_fully_assigned())
        by_qty.assignments.append(Assignment(SARI, 1))
        self.assertTrue(by_qty.is_over_assigned())
        self.assertFalse(by_qty.is_fully_assigned())


class TransactionLifecycleTests(unittest.TestCase):
    def test_dict_round_trip_draft_and_completed(self):
        draft = make_worked_example()
        self.assertEqual(Transaction.from_dict(draft.to_dict()), draft)
        self.assertNotIn("payments", draft.to_dict())
        complete_transaction(draft, make_group(), "2026-11-18T13:20:00")
        self.assertEqual(Transaction.from_dict(draft.to_dict()), draft)
        self.assertIn("payments", draft.to_dict())

    def test_status_progression(self):
        tx = Transaction("t", "grp_7f3a9c21", "Lunch", "2026-11-18", created_at=STAMP, updated_at=STAMP)
        self.assertEqual(derive_status(tx), Status.DRAFT)
        full = make_worked_example(assign_last_item=False)
        self.assertEqual(derive_status(full), Status.PENDING_ASSIGNMENT)
        full.items[-1].assignments = [Assignment(SARI)]
        self.assertEqual(derive_status(full), Status.READY_FOR_REVIEW)

    def test_blockers_name_the_problem(self):
        tx = make_worked_example(assign_last_item=False)
        self.assertEqual(finalization_blockers(tx), ["Sate Padang isn't assigned to anyone."])

    def test_partial_quantity_assignment_blocks(self):
        tx = make_worked_example()
        tx.items[2].assignments = [Assignment(DINA, 1), Assignment(RAKA, 1)]
        self.assertEqual(finalization_blockers(tx), ["Es Teh: 2 of 3 units assigned."])

    def test_over_assignment_blocks(self):
        tx = make_worked_example()
        tx.items[2].assignments = [Assignment(DINA, 2), Assignment(RAKA, 2)]
        self.assertIn("Es Teh: 4 units assigned but only 3 bought.", finalization_blockers(tx))

    def test_receipt_total_mismatch_blocks_with_exact_difference(self):
        tx = make_worked_example()
        tx.grand_total = 131500
        self.assertEqual(finalization_blockers(tx),
                         ["The receipt total is Rp1.000 higher than the items and charges add up to."])
        tx.grand_total = 130000
        self.assertEqual(finalization_blockers(tx),
                         ["The receipt total is Rp500 lower than the items and charges add up to."])
        self.assertEqual(derive_status(tx), Status.PENDING_ASSIGNMENT)

    def test_header_problems_block(self):
        tx = make_worked_example()
        tx.name, tx.transaction_date, tx.group_id = " ", "18/11/2026", ""
        problems = finalization_blockers(tx)
        self.assertIn("Enter a transaction name.", problems)
        self.assertIn("Enter a valid date.", problems)
        self.assertIn("Choose a group.", problems)

    def test_unknown_member_blocks(self):
        tx = make_worked_example()
        problems = finalization_blockers(tx, known_member_ids=[DINA, RAKA])
        self.assertTrue(any("isn't in the group" in p for p in problems))
        self.assertEqual(finalization_blockers(tx, known_member_ids=[DINA, RAKA, SARI]), [])

    def test_complete_transaction_stores_payments_and_snapshot(self):
        tx, group = make_worked_example(), make_group()
        complete_transaction(tx, group, "2026-11-18T13:20:00")
        self.assertEqual(tx.status, Status.COMPLETED)
        self.assertEqual(tx.completed_at, "2026-11-18T13:20:00")
        self.assertEqual([p.total for p in tx.payments], [43116, 39650, 47734])
        self.assertEqual([m.name for m in tx.members_snapshot], ["Dina", "Raka", "Sari"])

    def test_complete_refuses_and_leaves_transaction_unchanged(self):
        tx = make_worked_example(assign_last_item=False)
        with self.assertRaises(FinalizationError) as ctx:
            complete_transaction(tx, make_group(), "now")
        self.assertEqual(ctx.exception.problems, ["Sate Padang isn't assigned to anyone."])
        self.assertEqual(tx.status, Status.DRAFT)
        self.assertEqual(tx.payments, [])

    def test_complete_wrong_group(self):
        tx, group = make_worked_example(), make_group()
        group.group_id = "grp_other"
        with self.assertRaises(FinalizationError):
            complete_transaction(tx, group, "now")

    def test_snapshot_survives_later_member_rename_or_removal(self):
        tx, group = make_worked_example(), make_group()
        complete_transaction(tx, group, "2026-11-18T13:20:00")
        group.deactivate_member(DINA)
        group.find_member_by_id(RAKA).name = "Raka (renamed)"
        self.assertEqual([m.name for m in tx.members_snapshot], ["Dina", "Raka", "Sari"])

    def test_reopen_returns_independent_copy_and_recalculates(self):
        original, group = make_worked_example(), make_group()
        complete_transaction(original, group, "2026-11-18T13:20:00")
        draft = reopen_for_edit(original)
        self.assertEqual(draft.status, Status.READY_FOR_REVIEW)
        self.assertEqual(draft.payments, [])
        draft.items[0].unit_price = 30000
        draft.grand_total = 132500
        complete_transaction(draft, group, "2026-11-19T09:00:00")
        self.assertEqual(draft.completed_at, "2026-11-18T13:20:00")   # first completion time kept
        self.assertEqual(original.items[0].unit_price, 28000)          # original untouched
        self.assertEqual([p.total for p in original.payments], [43116, 39650, 47734])
        self.assertEqual(sum(p.total for p in draft.payments), 132500)

    def test_reopen_only_for_completed(self):
        with self.assertRaises(CalculationError):
            reopen_for_edit(make_worked_example())


if __name__ == "__main__":
    unittest.main()

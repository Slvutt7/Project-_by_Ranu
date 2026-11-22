import copy
import unittest

from splitmate.core.errors import UnsupportedSchemaError
from splitmate.core.lifecycle import complete_transaction
from splitmate.storage.validators import SCHEMA_VERSION, validate_groups, validate_transactions

from .helpers import make_group, make_worked_example


def groups_data():
    return {"schema_version": SCHEMA_VERSION, "groups": [make_group().to_dict()]}


def transactions_data(completed=True):
    tx = make_worked_example()
    if completed:
        complete_transaction(tx, make_group(), "2026-11-18T13:20:00")
    return {"schema_version": SCHEMA_VERSION, "transactions": [tx.to_dict()]}


class GroupValidationTests(unittest.TestCase):
    def test_valid_data_has_no_problems(self):
        self.assertEqual(validate_groups(groups_data()), [])
        self.assertEqual(validate_groups({"schema_version": 1, "groups": []}), [])

    def assert_problem(self, data, fragment):
        problems = validate_groups(data)
        self.assertTrue(any(fragment in p for p in problems), f"{fragment!r} not in {problems}")

    def test_structure_problems(self):
        self.assert_problem([], "top level")
        self.assert_problem({"schema_version": 1}, "groups: must be a list")
        self.assert_problem({"groups": []}, "schema_version")
        self.assert_problem({"schema_version": "1", "groups": []}, "schema_version")
        self.assert_problem({"schema_version": True, "groups": []}, "schema_version")

    def test_newer_schema_is_not_corruption(self):
        with self.assertRaises(UnsupportedSchemaError):
            validate_groups({"schema_version": SCHEMA_VERSION + 1, "groups": []})

    def test_field_problems(self):
        data = groups_data(); data["groups"][0]["name"] = "  "
        self.assert_problem(data, "name")
        data = groups_data(); data["groups"][0]["archived"] = "no"
        self.assert_problem(data, "archived")
        data = groups_data(); data["groups"][0]["members"][0]["active"] = 1
        self.assert_problem(data, "active")
        data = groups_data(); data["groups"][0]["created_at"] = "yesterday"
        self.assert_problem(data, "created_at")

    def test_duplicate_ids_and_names(self):
        data = groups_data(); data["groups"][0]["members"][1]["member_id"] = data["groups"][0]["members"][0]["member_id"]
        self.assert_problem(data, "duplicate ID")
        data = groups_data(); data["groups"].append(copy.deepcopy(data["groups"][0]))
        self.assert_problem(data, "duplicate ID")
        data = groups_data(); data["groups"][0]["members"][1]["name"] = " DINA "
        self.assert_problem(data, "appears twice")


class TransactionValidationTests(unittest.TestCase):
    def assert_problem(self, data, fragment, **kwargs):
        problems = validate_transactions(data, **kwargs)
        self.assertTrue(any(fragment in p for p in problems), f"{fragment!r} not in {problems}")

    def mutate(self, fn, completed=True):
        data = transactions_data(completed)
        fn(data["transactions"][0])
        return data

    def test_valid_completed_and_draft(self):
        self.assertEqual(validate_transactions(transactions_data(True)), [])
        self.assertEqual(validate_transactions(transactions_data(False)), [])
        self.assertEqual(validate_transactions({"schema_version": 1, "transactions": []}), [])

    def test_empty_draft_is_allowed(self):
        data = transactions_data(False)
        data["transactions"][0]["items"] = []
        data["transactions"][0]["status"] = "DRAFT"
        data["transactions"][0]["subtotal"] = 0
        self.assertEqual(validate_transactions(data), [])

    def test_cross_file_group_reference(self):
        data = transactions_data()
        self.assertEqual(validate_transactions(data, group_ids=["grp_7f3a9c21"]), [])
        self.assert_problem(data, "doesn't match any group", group_ids=["grp_other"])

    def test_money_must_be_whole_integers(self):
        self.assert_problem(self.mutate(lambda t: t["items"][0].__setitem__("unit_price", 28000.5)), "unit_price")
        self.assert_problem(self.mutate(lambda t: t["items"][0].__setitem__("unit_price", "28000")), "unit_price")
        self.assert_problem(self.mutate(lambda t: t["items"][0].__setitem__("unit_price", True)), "unit_price")
        self.assert_problem(self.mutate(lambda t: t["items"][0].__setitem__("unit_price", -1)), "unit_price")
        self.assert_problem(self.mutate(lambda t: t["items"][0].__setitem__("quantity", 0)), "quantity")
        self.assert_problem(self.mutate(lambda t: t["charges"].__setitem__("tax", -5)), "tax")
        self.assert_problem(self.mutate(lambda t: t.__setitem__("grand_total", 130500.0)), "grand_total")

    def test_negative_rounding_adjustment_is_allowed(self):
        self.assertEqual(validate_transactions(transactions_data()), [])  # fixture has -15

    def test_enum_and_date_problems(self):
        self.assert_problem(self.mutate(lambda t: t.__setitem__("status", "DONE")), "status")
        self.assert_problem(self.mutate(lambda t: t.__setitem__("source", "fax")), "source")
        self.assert_problem(self.mutate(lambda t: t.__setitem__("transaction_date", "18/11/2026")), "transaction_date")
        self.assert_problem(self.mutate(lambda t: t.__setitem__("transaction_date", "2026-02-30")), "transaction_date")
        self.assert_problem(self.mutate(lambda t: t["items"][0].__setitem__("split_mode", "HALF")), "split_mode")

    def test_duplicate_ids(self):
        data = transactions_data()
        data["transactions"].append(copy.deepcopy(data["transactions"][0]))
        self.assert_problem(data, "duplicate ID")
        self.assert_problem(self.mutate(lambda t: t["items"][1].__setitem__("item_id", "itm_01")), "duplicate ID")

    def test_inconsistent_totals_are_detected(self):
        self.assert_problem(self.mutate(lambda t: t["items"][0].__setitem__("total_price", 99)), "total_price")
        self.assert_problem(self.mutate(lambda t: t.__setitem__("subtotal", 1)), "subtotal")
        self.assert_problem(self.mutate(lambda t: t["payments"][0].__setitem__("total", 1)), "doesn't match its parts")
        self.assert_problem(self.mutate(lambda t: t.__setitem__("grand_total", 999999)), "grand_total")
        self.assert_problem(self.mutate(lambda t: t["charges"].__setitem__("tax", 1)), "tax_share")

    def test_completed_requires_payments_and_snapshot(self):
        self.assert_problem(self.mutate(lambda t: t.pop("payments")), "payments")
        self.assert_problem(self.mutate(lambda t: t.pop("members_snapshot")), "members_snapshot")
        self.assert_problem(self.mutate(lambda t: t.__setitem__("payments", [])), "payments")

    def test_payment_member_must_be_in_snapshot(self):
        self.assert_problem(self.mutate(lambda t: t["payments"][0].__setitem__("member_id", "mem_ghost")), "not found in members_snapshot")

    def test_assignment_problems(self):
        self.assert_problem(self.mutate(lambda t: t["items"][0]["assignments"].append({"member_id": t["items"][0]["assignments"][0]["member_id"]})), "assigned twice")
        self.assert_problem(self.mutate(lambda t: t["items"][2]["assignments"][0].__setitem__("quantity", 0)), "quantity")
        self.assert_problem(self.mutate(lambda t: t["items"][0]["assignments"][0].__setitem__("member_id", "mem_ghost")), "missing from members_snapshot")

    def test_wrong_types_do_not_crash(self):
        for broken in ([], {"schema_version": 1, "transactions": "x"}, {"schema_version": 1, "transactions": [5]},
                       {"schema_version": 1, "transactions": [{}]}):
            with self.subTest(broken=broken):
                self.assertTrue(validate_transactions(broken))
        self.assert_problem(self.mutate(lambda t: t.__setitem__("items", "nope")), "items")
        self.assert_problem(self.mutate(lambda t: t.__setitem__("charges", None)), "charges")

    def test_newer_schema(self):
        with self.assertRaises(UnsupportedSchemaError):
            validate_transactions({"schema_version": 99, "transactions": []})


if __name__ == "__main__":
    unittest.main()

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from splitmate.core.errors import DataFileError, DataValidationError, UnsupportedSchemaError
from splitmate.storage.ids import new_id
from splitmate.storage.json_store import JsonStore
from splitmate.storage.validators import validate_groups

from .helpers import make_group


def make_data(name="Lunch Squad"):
    group = make_group()
    group.name = name
    return {"schema_version": 1, "groups": [group.to_dict()]}


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "data"
        self.tick = 0
        self.store = JsonStore(self.dir, max_backups=5, clock=self._clock)

    def _clock(self):
        self.tick += 1
        return datetime(2026, 11, 18, 13, 0, 0) + timedelta(seconds=self.tick)

    def backups(self):
        folder = self.dir / "backups"
        return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


class SaveLoadTests(StoreTestCase):
    def test_missing_file(self):
        result = self.store.load("groups.json", validate_groups)
        self.assertEqual((result.status, result.data), ("missing", None))

    def test_round_trip_and_unicode(self):
        data = make_data("Kelompok Makan Siang \u2615 Dina\u2019s")
        self.store.save("groups.json", data, validate_groups)
        result = self.store.load("groups.json", validate_groups)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data, data)
        raw = (self.dir / "groups.json").read_text(encoding="utf-8")
        self.assertIn("\u2615", raw)  # stored as readable UTF-8, not \u escapes

    def test_creates_data_directory(self):
        self.assertFalse(self.dir.exists())
        self.store.save("groups.json", make_data(), validate_groups)
        self.assertTrue((self.dir / "groups.json").exists())

    def test_no_temp_file_left_behind(self):
        self.store.save("groups.json", make_data(), validate_groups)
        self.store.save("groups.json", make_data("Second"), validate_groups)
        leftovers = [p.name for p in self.dir.iterdir() if p.name.startswith(".")]
        self.assertEqual(leftovers, [])

    def test_invalid_data_is_never_written(self):
        self.store.save("groups.json", make_data(), validate_groups)
        before = (self.dir / "groups.json").read_text(encoding="utf-8")
        bad = make_data()
        bad["groups"][0]["name"] = ""
        with self.assertRaises(DataValidationError) as ctx:
            self.store.save("groups.json", bad, validate_groups)
        self.assertTrue(ctx.exception.problems)
        self.assertEqual((self.dir / "groups.json").read_text(encoding="utf-8"), before)

    def test_failed_replace_keeps_old_file_and_cleans_temp(self):
        self.store.save("groups.json", make_data("Original"), validate_groups)
        with mock.patch("splitmate.storage.json_store.os.replace", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(DataFileError) as ctx:
                self.store.save("groups.json", make_data("Changed"), validate_groups)
        self.assertIn("No space left", str(ctx.exception))
        self.assertEqual(self.store.load("groups.json", validate_groups).data["groups"][0]["name"], "Original")
        self.assertEqual([p.name for p in self.dir.iterdir() if p.name.startswith(".")], [])


class BackupTests(StoreTestCase):
    def test_first_save_has_no_backup_second_does(self):
        self.store.save("groups.json", make_data("v1"), validate_groups)
        self.assertEqual(self.backups(), [])
        self.store.save("groups.json", make_data("v2"), validate_groups)
        self.assertEqual(len(self.backups()), 1)

    def test_backups_are_pruned_to_the_limit_keeping_newest(self):
        for version in range(1, 16):
            self.store.save("groups.json", make_data(f"v{version}"), validate_groups)
        names = self.backups()
        self.assertEqual(len(names), 5)
        newest = json.loads((self.dir / "backups" / names[-1]).read_text(encoding="utf-8"))
        self.assertEqual(newest["groups"][0]["name"], "v14")  # backup of the state before the last save

    def test_groups_and_transactions_backups_do_not_mix(self):
        tx_validator = lambda data: []
        for n in range(3):
            self.store.save("groups.json", make_data(f"g{n}"), validate_groups)
            self.store.save("transactions.json", {"schema_version": 1, "n": n}, tx_validator)
        self.assertEqual(len([b for b in self.backups() if b.startswith("groups-")]), 2)
        self.assertEqual(len([b for b in self.backups() if b.startswith("transactions-")]), 2)


class RecoveryTests(StoreTestCase):
    def test_corrupt_file_restored_from_newest_valid_backup(self):
        self.store.save("groups.json", make_data("v1"), validate_groups)
        self.store.save("groups.json", make_data("v2"), validate_groups)
        self.store.save("groups.json", make_data("v3"), validate_groups)
        (self.dir / "groups.json").write_text("{ this is not json", encoding="utf-8")
        result = self.store.load("groups.json", validate_groups)
        self.assertEqual(result.status, "restored")
        self.assertEqual(result.data["groups"][0]["name"], "v2")
        self.assertIn("Restored from the backup of 18 Nov 2026", result.message)
        self.assertTrue(any(p.name.startswith("groups.json.corrupt-") for p in self.dir.iterdir()))
        # the restored data is now the live file, and a second load is clean
        again = self.store.load("groups.json", validate_groups)
        self.assertEqual((again.status, again.data["groups"][0]["name"]), ("ok", "v2"))

    def test_skips_damaged_backups(self):
        for version in range(1, 4):
            self.store.save("groups.json", make_data(f"v{version}"), validate_groups)
        newest_backup = sorted((self.dir / "backups").iterdir())[-1]
        newest_backup.write_text("garbage", encoding="utf-8")
        (self.dir / "groups.json").write_text("[]", encoding="utf-8")
        result = self.store.load("groups.json", validate_groups)
        self.assertEqual(result.status, "restored")
        self.assertEqual(result.data["groups"][0]["name"], "v1")

    def test_structurally_invalid_json_counts_as_damaged(self):
        self.store.save("groups.json", make_data("v1"), validate_groups)
        self.store.save("groups.json", make_data("v2"), validate_groups)
        broken = make_data("v2")
        broken["groups"][0]["members"][0]["active"] = "yes"
        (self.dir / "groups.json").write_text(json.dumps(broken), encoding="utf-8")
        self.assertEqual(self.store.load("groups.json", validate_groups).status, "restored")

    def test_corrupt_file_without_backup_resets_but_keeps_the_damaged_file(self):
        self.dir.mkdir(parents=True)
        (self.dir / "groups.json").write_bytes(b"\xff\xfe not utf8 \x00")
        result = self.store.load("groups.json", validate_groups)
        self.assertEqual((result.status, result.data), ("reset", None))
        self.assertIn("Started with an empty list", result.message)
        self.assertFalse((self.dir / "groups.json").exists())
        kept = [p for p in self.dir.iterdir() if p.name.startswith("groups.json.corrupt-")]
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].read_bytes(), b"\xff\xfe not utf8 \x00")

    def test_empty_file_is_treated_as_corrupt(self):
        self.dir.mkdir(parents=True)
        (self.dir / "groups.json").write_text("", encoding="utf-8")
        self.assertEqual(self.store.load("groups.json", validate_groups).status, "reset")

    def test_two_corruptions_in_the_same_second_do_not_overwrite_evidence(self):
        frozen = JsonStore(self.dir, clock=lambda: datetime(2026, 11, 18, 13, 0, 0))
        self.dir.mkdir(parents=True)
        for text in ("one", "two"):
            (self.dir / "groups.json").write_text(text, encoding="utf-8")
            frozen.load("groups.json", validate_groups)
        kept = sorted(p.read_text(encoding="utf-8") for p in self.dir.iterdir() if ".corrupt-" in p.name)
        self.assertEqual(kept, ["one", "two"])


class NewerSchemaTests(StoreTestCase):
    def test_newer_file_is_refused_and_untouched(self):
        self.dir.mkdir(parents=True)
        path = self.dir / "groups.json"
        path.write_text(json.dumps({"schema_version": 99, "groups": []}), encoding="utf-8")
        with self.assertRaises(UnsupportedSchemaError):
            self.store.load("groups.json", validate_groups)
        with self.assertRaises(UnsupportedSchemaError):
            self.store.save("groups.json", make_data(), validate_groups)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], 99)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["groups.json"])  # no quarantine, no backup


class IdTests(unittest.TestCase):
    def test_format_and_uniqueness(self):
        ids = {new_id("mem") for _ in range(500)}
        self.assertEqual(len(ids), 500)
        for value in ids:
            self.assertRegex(value, r"^mem_[0-9a-f]{8}$")

    def test_avoids_collisions_with_existing(self):
        values = iter(["aaaaaaaa", "aaaaaaaa", "bbbbbbbb"])
        result = new_id("grp", existing=["grp_aaaaaaaa"], suffix_factory=lambda: next(values))
        self.assertEqual(result, "grp_bbbbbbbb")


if __name__ == "__main__":
    unittest.main()

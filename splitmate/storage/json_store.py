"""Safe JSON persistence.

Writes: validate -> temp file in the same folder -> flush + fsync -> copy the
existing file into backups/ -> atomic os.replace. A crash at any point leaves
either the old file or the new file, never a half-written one.

Reads: parse -> validate. A damaged file is renamed to <name>.corrupt-<time>
(never deleted), then the newest valid backup is restored; if there is none the
caller starts empty. A file from a newer SplitMate is refused, not "repaired".
"""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..core.dates import format_date
from ..core.errors import DataFileError, DataValidationError, UnsupportedSchemaError
from .validators import SCHEMA_VERSION

Validator = Callable[[Any], List[str]]

_STAMP_FORMAT = "%Y%m%d-%H%M%S-%f"
_BACKUP_STAMP = re.compile(r"-(\d{8})-(\d{6})-\d{6}\.json$")


@dataclass
class LoadResult:
    """status: 'ok' | 'missing' | 'restored' | 'reset'. `message` is user-presentable."""

    data: Optional[Dict[str, Any]]
    status: str
    message: Optional[str] = None


class JsonStore:
    def __init__(self, data_dir: Path, max_backups: int = 20,
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self.data_dir = Path(data_dir)
        self.backup_dir = self.data_dir / "backups"
        self.max_backups = max_backups
        self._clock = clock

    # ------------------------------------------------------------------ public

    def path(self, filename: str) -> Path:
        return self.data_dir / filename

    def load(self, filename: str, validate: Validator) -> LoadResult:
        path = self.path(filename)
        if not path.exists():
            return LoadResult(None, "missing")
        try:
            return LoadResult(self._read_valid(path, validate), "ok")
        except UnsupportedSchemaError:
            raise
        except DataFileError:
            pass  # damaged: fall through to recovery

        quarantined = self._quarantine(path)
        for backup in self._backups_newest_first(filename):
            try:
                data = self._read_valid(backup, validate)
            except DataFileError:
                continue
            self._restore(backup, path)
            return LoadResult(
                data, "restored",
                f"{filename} couldn't be read. Restored from the backup of {self._describe_backup(backup)}. "
                f"The damaged file was kept as {quarantined.name}.",
            )
        return LoadResult(
            None, "reset",
            f"{filename} couldn't be read and no usable backup exists. Started with an empty list. "
            f"The damaged file was kept as {quarantined.name}.",
        )

    def save(self, filename: str, data: Dict[str, Any], validate: Validator) -> None:
        problems = validate(data)
        if problems:
            raise DataValidationError(problems)  # nothing is written

        path = self.path(filename)
        self._refuse_if_newer_on_disk(path)
        payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        temp = path.with_name(f".{filename}.tmp")
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(temp, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if path.exists():
                self._backup(path, filename)
            os.replace(temp, path)
        except OSError as exc:
            self._remove_quietly(temp)
            raise DataFileError(
                f"Couldn't save {filename}: {exc.strerror or exc}. Your previous data is unchanged."
            ) from exc

    # ----------------------------------------------------------------- reading

    def _read_valid(self, path: Path, validate: Validator) -> Dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            raise DataFileError(f"{path.name} can't be read: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DataFileError(f"{path.name} isn't valid JSON: {exc.msg} (line {exc.lineno}).") from exc
        problems = validate(data)  # may raise UnsupportedSchemaError
        if problems:
            raise DataValidationError(problems)
        return data

    def _refuse_if_newer_on_disk(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # unreadable file: handled by load(), not a version problem
        version = existing.get("schema_version") if isinstance(existing, dict) else None
        if isinstance(version, int) and not isinstance(version, bool) and version > SCHEMA_VERSION:
            raise UnsupportedSchemaError(
                f"{path.name} was written by a newer version of SplitMate and was not changed."
            )

    # ----------------------------------------------------- backups & recovery

    def _stamp(self) -> str:
        return self._clock().strftime(_STAMP_FORMAT)

    def _backup(self, path: Path, filename: str) -> None:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # never keep a damaged file as a "backup"
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(filename).stem
        shutil.copy2(path, self.backup_dir / f"{stem}-{self._stamp()}.json")
        for old in self._backups_newest_first(filename)[self.max_backups:]:
            self._remove_quietly(old)

    def _backups_newest_first(self, filename: str) -> List[Path]:
        if not self.backup_dir.exists():
            return []
        stem = Path(filename).stem
        found = [p for p in self.backup_dir.iterdir()
                 if p.name.startswith(f"{stem}-") and _BACKUP_STAMP.search(p.name)]
        return sorted(found, key=lambda p: p.name, reverse=True)  # timestamps sort chronologically

    def _quarantine(self, path: Path) -> Path:
        stamp = self._clock().strftime("%Y%m%d-%H%M%S")
        target = path.with_name(f"{path.name}.corrupt-{stamp}")
        counter = 1
        while target.exists():
            counter += 1
            target = path.with_name(f"{path.name}.corrupt-{stamp}-{counter}")
        os.replace(path, target)
        return target

    def _restore(self, backup: Path, path: Path) -> None:
        temp = path.with_name(f".{path.name}.restore")
        shutil.copy2(backup, temp)
        os.replace(temp, path)

    @staticmethod
    def _describe_backup(backup: Path) -> str:
        match = _BACKUP_STAMP.search(backup.name)
        if not match:
            return backup.name
        day, clock = match.group(1), match.group(2)
        iso = f"{day[:4]}-{day[4:6]}-{day[6:8]}"
        return f"{format_date(iso)} {clock[:2]}:{clock[2:4]}"

    @staticmethod
    def _remove_quietly(path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass

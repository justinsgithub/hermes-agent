"""Crash-safe per-profile retain outbox for Hindsight.

Each turn is one atomically written JSON record containing every bounded part
and its immutable network request.  Mutable delivery state lives beside (not
inside) that request.  Records are removed only after all parts have received a
server acknowledgement and a durable per-session completion range is written.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterable

_LOCKS_GUARD = threading.Lock()
_LOCKS: dict[str, threading.RLock] = {}


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class DurableRetainOutbox:
    """Owner-only journal scoped by ``HERMES_HOME``."""

    schema_version = 1

    def __init__(self, hermes_home: Path, *, poison_attempts: int = 5):
        self.root = Path(hermes_home) / "hindsight" / "outbox-v1"
        self.records_dir = self.root / "records"
        self.state_dir = self.root / "state"
        self.poison_attempts = max(1, int(poison_attempts))
        self._lock = _path_lock(self.root)
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for path in (self.root, self.records_dir, self.state_dir):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                path.chmod(0o700)
            except OSError:
                pass

    @contextmanager
    def _exclusive(self) -> Generator[None, None, None]:
        """Serialize journal mutations across threads and Hermes processes."""

        lock_path = self.root / ".lock"
        with self._lock:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            locked = False
            try:
                try:
                    if hasattr(os, "fchmod"):
                        os.fchmod(descriptor, 0o600)
                except (AttributeError, OSError):
                    pass
                if os.name == "nt":
                    import msvcrt

                    if os.fstat(descriptor).st_size == 0:
                        os.write(descriptor, b"\0")
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
                else:
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                locked = True
                yield
            finally:
                try:
                    if locked and os.name == "nt":
                        import msvcrt

                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                    elif locked:
                        import fcntl

                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                finally:
                    os.close(descriptor)

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _atomic_write(self, path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            try:
                if hasattr(os, "fchmod"):
                    os.fchmod(descriptor, 0o600)
            except (AttributeError, OSError):
                pass
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            self._fsync_directory(path.parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _record_path(self, turn_id: str) -> Path:
        return self.records_dir / f"{turn_id}.json"

    @staticmethod
    def _state_key(bank_id: str, session_id: str) -> str:
        return hashlib.sha256(f"{bank_id}\0{session_id}".encode("utf-8")).hexdigest()

    def _state_path(self, bank_id: str, session_id: str) -> Path:
        return self.state_dir / f"{self._state_key(bank_id, session_id)}.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def put_turn(self, record: dict[str, Any]) -> None:
        """Atomically persist one complete turn before it can be dispatched."""

        turn_id = str(record.get("turn_id") or "")
        if not turn_id:
            raise ValueError("outbox turn_id is required")
        parts = record.get("parts")
        if not isinstance(parts, list) or not parts:
            raise ValueError("outbox turn requires at least one part")
        for index, part in enumerate(parts):
            if part.get("part_index") != index:
                raise ValueError("outbox part indexes must be contiguous")
            if not part.get("operation_id") or not isinstance(part.get("request"), dict):
                raise ValueError("outbox part operation_id and request are required")
        record = dict(record)
        record["schema_version"] = self.schema_version
        record.setdefault("created_at", _utc_now())
        path = self._record_path(turn_id)
        with self._exclusive():
            if path.exists():
                existing = self._read(path)
                if existing != record:
                    raise ValueError(f"outbox turn {turn_id} already exists with different content")
                return
            self._atomic_write(path, record)

    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            output: list[dict[str, Any]] = []
            for path in sorted(self.records_dir.glob("*.json")):
                try:
                    record = self._read(path)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                record["_path"] = str(path)
                output.append(record)
            output.sort(key=lambda item: (int(item.get("turn_index", 0)), str(item.get("turn_id", ""))))
            return output

    def get(self, turn_id: str) -> dict[str, Any] | None:
        path = self._record_path(turn_id)
        with self._lock:
            if not path.exists():
                return None
            return self._read(path)

    def pending_jobs(self) -> list[tuple[str, int]]:
        jobs: list[tuple[str, int]] = []
        for record in self.records():
            if not record.get("ready", False):
                continue
            for part in record.get("parts", []):
                state = part.get("delivery", {})
                if state.get("acked") or state.get("poisoned"):
                    continue
                jobs.append((str(record["turn_id"]), int(part["part_index"])))
        return jobs

    def promote_session(self, bank_id: str, session_id: str, *, through_turn: int | None = None) -> list[tuple[str, int]]:
        """Make buffered turns dispatchable without mutating their requests."""

        promoted: list[tuple[str, int]] = []
        with self._exclusive():
            for record in self.records():
                if record.get("bank_id") != bank_id or record.get("session_id") != session_id:
                    continue
                if through_turn is not None and int(record.get("turn_index", 0)) > through_turn:
                    continue
                if not record.get("ready", False):
                    record.pop("_path", None)
                    record["ready"] = True
                    self._atomic_write(self._record_path(str(record["turn_id"])), record)
                for part in record.get("parts", []):
                    delivery = part.get("delivery", {})
                    if not delivery.get("acked") and not delivery.get("poisoned"):
                        promoted.append((str(record["turn_id"]), int(part["part_index"])))
        return promoted

    def promote_abandoned_sessions(
        self,
        active_bank_id: str,
        active_session_id: str,
    ) -> list[tuple[str, int]]:
        """Release buffered intents left by sessions other than the active one."""

        abandoned = sorted(
            {
                (str(record.get("bank_id", "")), str(record.get("session_id", "")))
                for record in self.records()
                if (
                    str(record.get("bank_id", "")),
                    str(record.get("session_id", "")),
                )
                != (active_bank_id, active_session_id)
            }
        )
        jobs: list[tuple[str, int]] = []
        for bank_id, session_id in abandoned:
            jobs.extend(self.promote_session(bank_id, session_id))
        return jobs

    def request_for(self, turn_id: str, part_index: int) -> dict[str, Any] | None:
        record = self.get(turn_id)
        if record is None or not record.get("ready", False):
            return None
        parts = record.get("parts", [])
        if part_index < 0 or part_index >= len(parts):
            return None
        part = parts[part_index]
        delivery = part.get("delivery", {})
        if delivery.get("acked") or delivery.get("poisoned"):
            return None
        return dict(part["request"])

    def mark_failure(self, turn_id: str, part_index: int, error: Exception) -> bool:
        """Record a non-content error digest; return whether another retry is allowed."""

        with self._exclusive():
            record = self.get(turn_id)
            if record is None:
                return False
            part = record["parts"][part_index]
            delivery = dict(part.get("delivery", {}))
            attempts = int(delivery.get("attempts", 0)) + 1
            delivery.update(
                {
                    "attempts": attempts,
                    "last_attempt_at": _utc_now(),
                    "last_error_sha256": hashlib.sha256(
                        f"{type(error).__name__}:{error}".encode("utf-8", errors="replace")
                    ).hexdigest(),
                    "poisoned": attempts >= self.poison_attempts,
                }
            )
            part["delivery"] = delivery
            self._atomic_write(self._record_path(turn_id), record)
            return not delivery["poisoned"]

    def mark_acknowledged(self, turn_id: str, part_index: int) -> None:
        """Persist the ACK, then finalize the turn only when every part is ACKed."""

        with self._exclusive():
            record = self.get(turn_id)
            if record is None:
                return
            part = record["parts"][part_index]
            delivery = dict(part.get("delivery", {}))
            delivery.update({"acked": True, "acknowledged_at": _utc_now(), "poisoned": False})
            part["delivery"] = delivery
            path = self._record_path(turn_id)
            self._atomic_write(path, record)
            if not all(bool(item.get("delivery", {}).get("acked")) for item in record["parts"]):
                return
            self._record_completed_range(record)
            # The completion ledger is durable before deletion.  A crash at
            # any earlier point leaves the exact operation request replayable.
            path.unlink(missing_ok=True)
            self._fsync_directory(self.records_dir)

    def _record_completed_range(self, record: dict[str, Any]) -> None:
        bank_id = str(record["bank_id"])
        session_id = str(record["session_id"])
        path = self._state_path(bank_id, session_id)
        if path.exists():
            try:
                state = self._read(path)
            except (OSError, ValueError, json.JSONDecodeError):
                state = {}
        else:
            state = {}
        contiguous = int(state.get("contiguous_acked_turn", 0) or 0)
        completed = {
            int(value)
            for value in state.get("completed_turns", [])
            if isinstance(value, int) or str(value).isdigit()
            if int(value) > contiguous
        }
        completed_turn = int(record["turn_index"])
        if completed_turn > contiguous:
            completed.add(completed_turn)
        while contiguous + 1 in completed:
            contiguous += 1
            completed.discard(contiguous)
        state = {
            "schema_version": self.schema_version,
            "bank_id": bank_id,
            "session_id": session_id,
            "contiguous_acked_turn": contiguous,
            "completed_turns": sorted(completed),
            "updated_at": _utc_now(),
        }
        self._atomic_write(path, state)

    def completed_state(self, bank_id: str, session_id: str) -> dict[str, Any]:
        path = self._state_path(bank_id, session_id)
        with self._lock:
            if not path.exists():
                return {
                    "contiguous_acked_turn": 0,
                    "completed_turns": [],
                }
            return self._read(path)

    def max_known_turn(self, bank_id: str, session_id: str) -> int:
        state = self.completed_state(bank_id, session_id)
        values = [int(state.get("contiguous_acked_turn", 0) or 0)]
        values.extend(int(value) for value in state.get("completed_turns", []))
        for record in self.records():
            if record.get("bank_id") == bank_id and record.get("session_id") == session_id:
                values.append(int(record.get("turn_index", 0)))
        return max(values, default=0)

    def contiguous_acked_turn(self, bank_id: str, session_id: str) -> int:
        return int(self.completed_state(bank_id, session_id).get("contiguous_acked_turn", 0))

    def recover_acknowledged_turns(self) -> None:
        """Finish cleanup after a crash between final ACK persistence and unlink."""

        with self._exclusive():
            for record in self.records():
                parts: Iterable[dict[str, Any]] = record.get("parts", [])
                if parts and all(bool(part.get("delivery", {}).get("acked")) for part in parts):
                    self._record_completed_range(record)
                    self._record_path(str(record["turn_id"])).unlink(missing_ok=True)
            self._fsync_directory(self.records_dir)

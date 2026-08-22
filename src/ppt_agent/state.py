from __future__ import annotations

import json
import os
import secrets
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .errors import PptAgentError
from .paths import state_root

DEFAULT_LOCK_LEASE_SECONDS = 1800.0


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_lenient(path: Path, default: Any) -> Any:
    try:
        return _read_json(path, default)
    except (OSError, ValueError):
        return default


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temp, path)


def _process_alive(pid: int) -> bool:
    """Best-effort process liveness; False means dead or unverifiable."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_created_after(pid: int, timestamp: float) -> bool | None:
    """Whether the process started after the wall-clock timestamp.

    None means unverifiable (dead process, insufficient rights, or non-Windows
    platform without a creation-time source).
    """
    if pid <= 0:
        return None
    if os.name != "nt":
        return None
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation = ctypes.c_ulonglong()
        exit_time = ctypes.c_ulonglong()
        kernel_time = ctypes.c_ulonglong()
        user_time = ctypes.c_ulonglong()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return None
        created_epoch = creation.value / 10_000_000.0 - 11644473600.0
        return created_epoch > timestamp + 1.0
    finally:
        kernel32.CloseHandle(handle)


def _holder_genuine(pid: int, lock_created: float) -> bool | None:
    """True = live process that created the lock; False = dead or reused PID;
    None = unverifiable (fall back to lease expiry)."""
    if pid <= 0:
        return False
    created_after = _process_created_after(pid, lock_created)
    if created_after is True:
        # 该 PID 在锁创建之后才启动：原持有者已死，PID 被复用。
        return False
    alive = _process_alive(pid)
    if not alive:
        return False
    if created_after is False:
        # 进程确在锁创建前启动：真正的持有者，绝不因时间过期被抢占。
        return True
    return None  # 无法核验创建时间（非 Windows 等）→ 交给租约兜底


class StateStore:
    def __init__(self, document_id: str):
        self.document_id = document_id
        root = state_root()
        self.baseline_path = root / "state" / document_id / "baseline.json"
        self.review_path = root / "state" / document_id / "review.json"
        self.requests_path = root / "requests" / document_id / "recent.json"
        self.lock_path = root / "locks" / f"{document_id}.lock"
        self.render_dir = root / "renders" / document_id
        self.journal_path = root / "transactions" / document_id / "journal.json"
        override = os.environ.get("PPT_AGENT_LOCK_LEASE_SECONDS")
        try:
            self.lease_seconds = float(override) if override else DEFAULT_LOCK_LEASE_SECONDS
        except ValueError:
            self.lease_seconds = DEFAULT_LOCK_LEASE_SECONDS

    # -- plain state ---------------------------------------------------------

    def baseline(self) -> dict[str, Any] | None:
        return _read_json(self.baseline_path, None)

    def save_baseline(self, value: dict[str, Any]) -> None:
        atomic_write_json(self.baseline_path, value)

    def review(self) -> dict[str, Any] | None:
        return _read_json(self.review_path, None)

    def save_review(self, value: dict[str, Any]) -> None:
        atomic_write_json(self.review_path, value)

    def requests(self) -> dict[str, Any]:
        return _read_json(self.requests_path, {})

    def save_requests(self, value: dict[str, Any]) -> None:
        trimmed = dict(list(value.items())[-100:])
        atomic_write_json(self.requests_path, trimmed)

    # -- publish journal (candidate <-> request record transaction) ----------

    def journal(self) -> dict[str, Any] | None:
        """严格读取事务日志：不存在 → None；存在但损坏 → 结构化阻断。

        WAL 是恢复的唯一依据，损坏时绝不能当作"无事务"继续写入。
        """
        if not self.journal_path.exists():
            return None
        try:
            value = json.loads(self.journal_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PptAgentError(
                "TRANSACTION_JOURNAL_CORRUPT",
                "事务日志损坏，已禁止写入以保护文档状态",
                "report_bug",
                details={"journal": str(self.journal_path)},
            ) from exc
        if not isinstance(value, dict):
            raise PptAgentError(
                "TRANSACTION_JOURNAL_CORRUPT",
                "事务日志内容无效，已禁止写入以保护文档状态",
                "report_bug",
                details={"journal": str(self.journal_path)},
            )
        return value

    def save_journal(self, entry: dict[str, Any]) -> None:
        atomic_write_json(self.journal_path, entry)

    def mark_journal(self, status: str) -> None:
        entry = self.journal()
        if entry is not None:
            entry["status"] = status
            atomic_write_json(self.journal_path, entry)

    def clear_journal(self) -> None:
        try:
            self.journal_path.unlink()
        except FileNotFoundError:
            pass

    # -- lease lock ----------------------------------------------------------

    @property
    def guard_path(self) -> Path:
        return self.lock_path.with_name(self.lock_path.name + ".guard")

    def _lock_payload(self, token: str) -> dict[str, Any]:
        return {
            "token": token,
            "pid": os.getpid(),
            "created_at": time.time(),
            "lease_seconds": self.lease_seconds,
        }

    def _acquire_fresh(self, token: str) -> bool:
        try:
            descriptor = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, json.dumps(self._lock_payload(token), separators=(",", ":")).encode())
            os.close(descriptor)
        except FileExistsError:
            return False
        return self._owns(token)

    def _owns(self, token: str) -> bool:
        content = _read_json_lenient(self.lock_path, {})
        return isinstance(content, dict) and content.get("token") == token

    def _content_stale(self, content: dict[str, Any] | None) -> bool:
        """Dead holder, reused PID, or corrupt content = stale.

        A genuine live holder is never stale, no matter how old the lease is.
        Only when liveness/creation-time cannot be verified does the lease
        expiry act as the fallback decision.
        """
        if not isinstance(content, dict):
            return True
        try:
            holder_pid = int(content.get("pid", 0))
        except (TypeError, ValueError):
            return True
        try:
            created = float(content.get("created_at", 0) or 0)
        except (TypeError, ValueError):
            created = 0
        genuine = _holder_genuine(holder_pid, created)
        if genuine is True:
            return False
        if genuine is False:
            return True
        try:
            lease = float(content.get("lease_seconds", DEFAULT_LOCK_LEASE_SECONDS))
        except (TypeError, ValueError):
            lease = DEFAULT_LOCK_LEASE_SECONDS
        return time.time() - created > lease

    def _acquire_guard(self, token: str, deadline: float) -> int | None:
        """Exclusive takeover guard, held open so Windows forbids its removal."""
        payload = json.dumps(
            {"token": token, "pid": os.getpid(), "created_at": time.time()},
            separators=(",", ":"),
        ).encode()
        while True:
            try:
                descriptor = os.open(self.guard_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, payload)
                return descriptor
            except FileExistsError:
                content = _read_json_lenient(self.guard_path, None)
                if self._content_stale(content):
                    try:
                        self.guard_path.unlink()
                    except OSError:
                        pass  # 持有者仍开着文件（Windows 下删除被拒）→ 稍后重试
                if time.monotonic() >= deadline:
                    return None
                time.sleep(0.02)

    def _release_guard(self, descriptor: int, token: str) -> None:
        os.close(descriptor)
        content = _read_json_lenient(self.guard_path, None)
        if isinstance(content, dict) and content.get("token") == token:
            try:
                self.guard_path.unlink()
            except FileNotFoundError:
                pass

    def _takeover_if_stale(self, token: str) -> bool:
        """Guard-serialized takeover.

        The original lock bytes are snapshotted up front; inside the exclusive
        guard the current bytes must equal that snapshot (unconditionally —
        including a corrupt/missing snapshot) and the current content must
        still be stale, otherwise the takeover is abandoned. Two waiters can
        therefore never both win, even when the initial lock is corrupt.
        """
        try:
            snapshot = self.lock_path.read_bytes()
        except FileNotFoundError:
            snapshot = None
        if not self._content_stale(_read_json_lenient(self.lock_path, None)):
            return False
        guard_token = secrets.token_hex(16)
        descriptor = self._acquire_guard(guard_token, time.monotonic() + 5.0)
        if descriptor is None:
            return False
        try:
            try:
                current_bytes = self.lock_path.read_bytes()
            except FileNotFoundError:
                current_bytes = None
            if current_bytes != snapshot:
                # 锁文件在守卫取得前已被他人改写（含从损坏恢复为正常新锁）。
                return False
            if not self._content_stale(_read_json_lenient(self.lock_path, None)):
                return False
            temp = self.lock_path.with_name(f".{self.lock_path.name}.{token}.tmp")
            try:
                temp.write_text(json.dumps(self._lock_payload(token), separators=(",", ":")), encoding="utf-8")
                os.replace(temp, self.lock_path)
            finally:
                try:
                    temp.unlink()
                except FileNotFoundError:
                    pass
            return self._owns(token)
        finally:
            self._release_guard(descriptor, guard_token)

    @contextmanager
    def lock(self, wait_seconds: float = 0) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_hex(16)
        deadline = time.monotonic() + wait_seconds
        while True:
            if self._acquire_fresh(token):
                break
            if self._takeover_if_stale(token):
                if self._owns(token):
                    break
                continue
            if time.monotonic() >= deadline:
                raise PptAgentError("DOCUMENT_LOCKED", "文档正在被另一个写操作处理", "retry", True)
            time.sleep(0.1)
        try:
            yield
        finally:
            if self._owns(token):
                try:
                    self.lock_path.unlink()
                except FileNotFoundError:
                    pass


def now_iso() -> str:
    return datetime.now(UTC).isoformat()

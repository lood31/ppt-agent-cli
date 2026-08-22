from __future__ import annotations

import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .paths import accepted_path, candidate_path, document_id, revision
from .state import StateStore, now_iso

# WAL 四态：
#   prepared         发布可能已发生也可能没有 → 只能回滚（逐文件幂等）
#   rollback_pending 回滚已决定并部分执行      → 继续回滚
#   committed        业务提交完成（record 已写） → 补齐/确认 record，清理
#   cleanup_pending  业务提交成功、清理失败      → 只清理，绝不报业务失败

VALID_STATUSES = {"prepared", "rollback_pending", "committed", "cleanup_pending"}
VALID_ACTIONS = {"apply", "accept", "discard", "create"}
_TEMP_TOKEN = re.compile(r"[a-z0-9_]{8}", re.ASCII)


def _diagnose(message: str) -> None:
    print(f"ppt-agent: {message}", file=sys.stderr)


@contextmanager
def write_transaction(source: Path, wait: float = 0) -> Iterator[StateStore]:
    """统一写事务入口：同一文档锁 → 恢复 pending journal → 交给调用方变更。

    create / apply / accept / discard 都必须从这里进入，保证：
    1. 与 apply 使用同一把租约锁（互斥）；
    2. 执行任何变更前先恢复上一次崩溃遗留的事务（失败不发布）。
    """
    store = StateStore(document_id(source))
    with store.lock(wait):
        recover_transactions(store, source)
        yield store


def commit_publish(
    store: StateStore,
    entry: dict[str, Any],
    publish: Callable[[], None],
    record: Callable[[], None],
    rollback: Callable[[], None],
    refresh: Callable[[], None] | None = None,
    cleanup: Callable[[], None] | None = None,
) -> None:
    """journaled 提交：prepared → publish → refresh? → committed → record → cleanup。

    回滚决定必须先持久化为 rollback_pending 才允许执行回滚；持久化失败时
    不修改任何文件，让恢复器按已持久化状态收敛。
    进入最终提交点（record 成功）后，清理类失败只留下可恢复 WAL 并返回
    业务成功，绝不改变本次业务结果。
    """
    store.save_journal(entry)
    try:
        publish()
        if refresh is not None:
            refresh()
        store.mark_journal("committed")
    except Exception:
        _begin_rollback(store, rollback)
        raise
    try:
        record()
    except Exception:
        _begin_rollback(store, rollback)
        raise
    # 最终提交点之后：清理失败不得报业务失败。
    try:
        if cleanup is not None:
            cleanup()
    except Exception as exc:
        try:
            store.mark_journal("cleanup_pending")
        except Exception:
            _diagnose(f"事务清理失败且无法写入 cleanup_pending，将在下次写命令时重试：{exc}")
        else:
            _diagnose(f"事务清理失败，将在下次写命令时重试：{exc}")
        return
    try:
        store.clear_journal()
    except Exception as exc:
        _diagnose(f"事务日志清理失败，将在下次写命令时重试：{exc}")


def _begin_rollback(store: StateStore, rollback: Callable[[], None]) -> None:
    # 状态转换先于文件副作用：写失败则直接上抛，不执行任何回滚动作。
    store.mark_journal("rollback_pending")
    try:
        rollback()
    except Exception:
        raise  # WAL 保持 rollback_pending，由下次入口继续回滚
    try:
        store.clear_journal()
    except Exception as exc:
        _diagnose(f"回滚完成但日志清理失败，将在下次写命令时重试：{exc}")


def _validate_entry(entry: dict[str, Any], source: Path, store: StateStore) -> None:
    """journal 形状与路径校验：不猜测恢复策略，不合法即结构化阻断。"""

    def corrupt(reason: str) -> None:
        from .errors import PptAgentError

        raise PptAgentError(
            "TRANSACTION_JOURNAL_CORRUPT",
            "事务日志内容无效，已禁止写入以保护文档状态",
            "report_bug",
            details={"reason": reason},
        )

    if "status" not in entry:
        corrupt("缺少 status")
    status = entry["status"]
    if not isinstance(status, str) or status not in VALID_STATUSES:
        corrupt(f"未知状态：{status!r}")
    if "action" not in entry:
        corrupt("缺少 action")
    action = entry["action"]
    if not isinstance(action, str) or action not in VALID_ACTIONS:
        corrupt(f"未知动作：{action!r}")

    def require_string(key: str) -> None:
        if not isinstance(entry.get(key), str) or not entry[key]:
            corrupt(f"{action} 缺少 {key}")

    if action == "apply":
        require_string("request_id")
        require_string("new_revision")
        require_string("temp")
        if status == "committed" and not isinstance(entry.get("result"), dict):
            corrupt("committed apply 缺少 result")
    elif action == "accept":
        require_string("new_revision")
        require_string("temp")
        require_string("candidate_backup")
        baseline = entry.get("baseline")
        if status in {"committed", "cleanup_pending"} and not isinstance(baseline, dict):
            corrupt(f"{status} accept 缺少 baseline")
        if baseline is not None and not isinstance(baseline, dict):
            corrupt("accept baseline 不是对象")
    elif action == "discard":
        require_string("candidate_backup")
    else:  # create
        if status == "cleanup_pending":
            corrupt("create 不允许 cleanup_pending")
        require_string("new_revision")
        require_string("temp")

    candidate = candidate_path(source)
    accepted = accepted_path(source)
    formal_paths = {
        source.resolve(),
        candidate.resolve(),
        accepted.resolve(),
        store.baseline_path.resolve(),
        store.review_path.resolve(),
        store.requests_path.resolve(),
        store.journal_path.resolve(),
        store.lock_path.resolve(),
    }

    allowed_exact: dict[str, Path] = {}
    temp_target: Path | None = None
    if action in {"apply", "create"}:
        temp_target = candidate
    elif action == "accept":
        temp_target = accepted
    if action == "apply":
        allowed_exact["backup"] = candidate.with_name(f".{candidate.stem}.backup.pptx")
    elif action == "accept":
        allowed_exact.update({
            "backup": accepted.with_name(f".{accepted.stem}.backup.pptx"),
            "candidate_backup": candidate.with_name(f".{candidate.stem}.moved.pptx"),
        })
    elif action == "discard":
        allowed_exact["candidate_backup"] = candidate.with_name(f".{candidate.stem}.moved.pptx")

    for key in ("temp", "backup", "candidate_backup"):
        value = entry.get(key)
        if value is None:
            continue
        if not isinstance(value, str):
            corrupt(f"{key} 不是路径字符串")
        try:
            resolved = Path(value).resolve()
        except (OSError, RuntimeError, ValueError):
            corrupt(f"{key} 路径无法解析")
        if resolved in formal_paths:
            corrupt(f"{key} 指向正式文档或状态文件：{value}")
        if key == "temp" and temp_target is not None:
            target_parent = temp_target.parent.resolve()
            prefix = f".{temp_target.stem}."
            name = resolved.name.casefold()
            prefix_folded = prefix.casefold()
            suffix = ".pptx"
            token = name[len(prefix_folded):-len(suffix)] if name.startswith(prefix_folded) and name.endswith(suffix) else ""
            if resolved.parent != target_parent or _TEMP_TOKEN.fullmatch(token) is None:
                corrupt(f"{action} 的 temp 不是派生临时文件：{value}")
        elif key in allowed_exact:
            if resolved != allowed_exact[key].resolve():
                corrupt(f"{action} 的 {key} 不是派生备份文件：{value}")
        else:
            corrupt(f"{action} 不允许 {key}")


def recover_transactions(store: StateStore, source: Path) -> None:
    """按 WAL 状态恢复。journal 损坏由 store.journal() 结构化阻断。

    只有恢复动作与清理全部成功后才清除 journal；中途失败保留 WAL 并重新抛出。
    """
    entry = store.journal()
    if entry is None:
        return
    _validate_entry(entry, source, store)
    candidate = candidate_path(source)
    accepted = accepted_path(source)
    action = entry["action"]
    status = entry["status"]
    if status == "cleanup_pending":
        _cleanup_entry(entry)
    elif status == "committed":
        if action == "accept":
            _ensure_baseline(store, entry)
        elif action == "apply":
            _ensure_record(store, entry)
        _cleanup_entry(entry)
    else:  # prepared / rollback_pending：只能继续回滚
        if action == "accept":
            _rollback_accept(candidate, accepted, entry)
        elif action == "discard":
            _rollback_discard(candidate, entry)
        elif action == "create":
            _rollback_create(candidate, entry)
        else:
            _rollback_apply(candidate, entry)
        _cleanup_entry(entry)
    store.clear_journal()


def _entry_paths(entry: dict[str, Any]) -> list[Path | None]:
    result: list[Path | None] = []
    for key in ("temp", "backup", "candidate_backup"):
        value = entry.get(key)
        result.append(Path(value) if value else None)
    return result


def _cleanup_entry(entry: dict[str, Any]) -> None:
    for path in _entry_paths(entry):
        if path is not None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def _ensure_record(store: StateStore, entry: dict[str, Any]) -> None:
    requests = store.requests()
    request_id = entry.get("request_id")
    if request_id and request_id not in requests:
        requests[request_id] = {
            "request_hash": entry.get("request_hash", ""),
            "result": entry.get("result", {}),
            "created_at": entry.get("created_at", now_iso()),
        }
        store.save_requests(requests)


def _ensure_baseline(store: StateStore, entry: dict[str, Any]) -> None:
    baseline = entry.get("baseline")
    if baseline:
        current_baseline = store.baseline()
        if current_baseline is None or current_baseline.get("revision") != baseline.get("revision"):
            # journal 中的 baseline 是本次 accept 的权威结果。
            store.save_baseline(baseline)


def _rollback_apply(candidate: Path, entry: dict[str, Any]) -> None:
    backup = Path(entry["backup"]) if entry.get("backup") else None
    new_revision = entry.get("new_revision")
    if candidate.exists() and new_revision and revision(candidate) == new_revision:
        if backup is not None and backup.exists():
            os.replace(backup, candidate)
        else:
            candidate.unlink(missing_ok=True)


def _rollback_accept(candidate: Path, accepted: Path, entry: dict[str, Any]) -> None:
    """逐文件独立、幂等回滚：accepted 与 candidate 各自按自身状态恢复。"""
    backup = Path(entry["backup"]) if entry.get("backup") else None
    candidate_backup = Path(entry["candidate_backup"]) if entry.get("candidate_backup") else None
    new_revision = entry.get("new_revision")
    if accepted.exists() and new_revision and revision(accepted) == new_revision:
        if backup is not None and backup.exists():
            os.replace(backup, accepted)
        else:
            accepted.unlink(missing_ok=True)
    if not candidate.exists() and candidate_backup is not None and candidate_backup.exists():
        os.replace(candidate_backup, candidate)


def _rollback_discard(candidate: Path, entry: dict[str, Any]) -> None:
    candidate_backup = Path(entry["candidate_backup"]) if entry.get("candidate_backup") else None
    if not candidate.exists() and candidate_backup is not None and candidate_backup.exists():
        os.replace(candidate_backup, candidate)


def _rollback_create(candidate: Path, entry: dict[str, Any]) -> None:
    new_revision = entry.get("new_revision")
    if candidate.exists() and new_revision and revision(candidate) == new_revision:
        candidate.unlink(missing_ok=True)

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ppt_agent import service
from ppt_agent.errors import PptAgentError
from ppt_agent.paths import accepted_path, candidate_path, document_id, revision
from ppt_agent.state import StateStore
from ppt_agent.txn import recover_transactions

FIXTURE = Path("fixtures/synthetic/synthetic.pptx")


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, StateStore]:
    source = tmp_path / "deck.pptx"
    shutil.copy2(FIXTURE, source)
    monkeypatch.setenv("PPT_AGENT_STATE_DIR", str(tmp_path / "state"))
    return source, StateStore(document_id(source))


def _patch(source: Path, operations: list[dict], request_id: str = "req") -> Path:
    patch = {
        "request_id": request_id,
        "document_id": document_id(source),
        "revision": revision(source),
        "operations": operations,
    }
    patch_path = source.parent / f"{request_id}.json"
    patch_path.write_text(json.dumps(patch), encoding="utf-8")
    return patch_path


def _temp_for(target: Path, token: str = "abcdefgh") -> Path:
    return target.with_name(f".{target.stem}.{token}.pptx")


def _apply(source: Path, patch: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setattr(service.wps, "finalize", lambda path: {"wps_version": "test"})
    monkeypatch.setattr(service.wps, "reopen_verify", lambda path: {"wps_version": "test"})
    return service.apply(source, patch, allow_risk={"external_relationship"})


def test_happy_path_cleans_journal_and_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    response = _apply(source, _patch(source, [{"op": "set_text", "object": "s0:s2", "text": "changed"}]), monkeypatch)

    assert response["ok"] is True
    candidate = candidate_path(source)
    assert candidate.exists()
    assert store.journal() is None
    assert not list(tmp_path.glob("*.backup.pptx"))
    assert store.requests()  # 骞傜瓑璁板綍瀛樺湪


def test_prepared_before_publish_recovers_to_no_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    original = source.read_bytes()
    temp = _temp_for(candidate_path(source))
    shutil.copy2(source, temp)
    new_revision = revision(temp)
    store.save_journal({
        "status": "prepared",
        "action": "apply",
        "request_id": "req-crash-1",
        "request_hash": "hash",
        "base_revision": revision(source),
        "new_revision": new_revision,
        "temp": str(temp),
        "backup": None,
        "result": {"ok": True},
        "created_at": "now",
    })

    recover_transactions(store, source)

    assert not candidate.exists()
    assert not temp.exists()
    assert store.journal() is None
    assert store.requests() == {}
    assert source.read_bytes() == original


def test_prepared_after_publish_rolls_candidate_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    backup = source.parent / ".deck.agent.candidate.backup.pptx"
    shutil.copy2(source, candidate)
    backup_bytes = candidate.read_bytes()
    temp = _temp_for(candidate)
    shutil.copy2(source, temp)
    with temp.open("ab") as stream:
        stream.write(b"staged-change")
    new_revision = revision(temp)
    store.save_journal({
        "status": "prepared",
        "action": "apply",
        "request_id": "req-crash-2",
        "request_hash": "hash",
        "base_revision": revision(source),
        "new_revision": new_revision,
        "temp": str(temp),
        "backup": str(backup),
        "result": {"ok": True},
        "created_at": "now",
    })
    shutil.copy2(source, backup)  # backup of the pre-publish candidate
    shutil.copy2(temp, candidate)  # simulate publish

    recover_transactions(store, source)

    assert candidate.read_bytes() == backup_bytes
    assert not temp.exists()
    assert not backup.exists()
    assert store.journal() is None
    assert store.requests() == {}


def test_prepared_after_publish_without_prior_candidate_removes_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    temp = _temp_for(candidate)
    shutil.copy2(source, temp)
    with temp.open("ab") as stream:
        stream.write(b"staged-change")
    new_revision = revision(temp)
    store.save_journal({
        "status": "prepared",
        "action": "apply",
        "request_id": "req-crash-3",
        "request_hash": "hash",
        "base_revision": None,
        "new_revision": new_revision,
        "temp": str(temp),
        "backup": None,
        "result": {"ok": True},
        "created_at": "now",
    })
    shutil.copy2(temp, candidate)  # publish happened; no prior candidate

    recover_transactions(store, source)

    assert not candidate.exists()
    assert not temp.exists()
    assert store.journal() is None
    assert store.requests() == {}


def test_committed_without_record_restores_record_and_keeps_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    temp = _temp_for(candidate)
    shutil.copy2(source, temp)
    with temp.open("ab") as stream:
        stream.write(b"staged-change")
    new_revision = revision(temp)
    result_payload = {"ok": True, "command": "apply", "revision": new_revision}
    store.save_journal({
        "status": "committed",
        "action": "apply",
        "request_id": "req-crash-4",
        "request_hash": "hash",
        "base_revision": revision(source),
        "new_revision": new_revision,
        "temp": str(temp),
        "backup": None,
        "result": result_payload,
        "created_at": "now",
    })
    shutil.copy2(temp, candidate)

    recover_transactions(store, source)

    assert candidate.exists()
    requests = store.requests()
    assert requests["req-crash-4"]["result"] == result_payload
    assert store.journal() is None


def test_committed_with_record_keeps_candidate_and_cleans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    backup = source.parent / ".deck.agent.candidate.backup.pptx"
    temp = _temp_for(candidate)
    shutil.copy2(source, temp)
    with temp.open("ab") as stream:
        stream.write(b"staged-change")
    new_revision = revision(temp)
    result_payload = {"ok": True, "command": "apply", "revision": new_revision}
    store.save_requests({"req-crash-5": {"request_hash": "hash", "result": result_payload, "created_at": "now"}})
    store.save_journal({
        "status": "committed",
        "action": "apply",
        "request_id": "req-crash-5",
        "request_hash": "hash",
        "base_revision": revision(source),
        "new_revision": new_revision,
        "temp": str(temp),
        "backup": str(backup),
        "result": result_payload,
        "created_at": "now",
    })
    shutil.copy2(source, backup)
    shutil.copy2(temp, candidate)

    recover_transactions(store, source)

    assert candidate.exists()
    assert store.requests()["req-crash-5"]["result"] == result_payload
    assert not backup.exists()
    assert store.journal() is None


def test_save_requests_failure_rolls_back_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    original = source.read_bytes()
    monkeypatch.setattr(service.wps, "finalize", lambda path: {"wps_version": "test"})
    monkeypatch.setattr(service.wps, "reopen_verify", lambda path: {"wps_version": "test"})

    def failing_save(value: dict) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(store, "save_requests", failing_save)
    monkeypatch.setattr("ppt_agent.txn.StateStore", lambda doc_id: store)

    with pytest.raises(OSError):
        service.apply(source, _patch(source, [{"op": "set_text", "object": "s0:s2", "text": "changed"}]), allow_risk={"external_relationship"})

    assert not candidate_path(source).exists()
    assert source.read_bytes() == original
    assert store.journal() is None
    assert store.requests() == {}
    leftovers = [item for item in source.parent.iterdir() if item.name.startswith(".")]
    assert leftovers == []


def test_crash_recovery_runs_at_next_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """prepared+published 的崩溃现场，在下一次 apply 时被自动回滚，然后正常执行。"""
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    temp = _temp_for(candidate)
    shutil.copy2(source, temp)
    with temp.open("ab") as stream:
        stream.write(b"staged-change")
    new_revision = revision(temp)
    store.save_journal({
        "status": "prepared",
        "action": "apply",
        "request_id": "req-crash-6",
        "request_hash": "hash",
        "base_revision": None,
        "new_revision": new_revision,
        "temp": str(temp),
        "backup": None,
        "result": {"ok": True},
        "created_at": "now",
    })
    shutil.copy2(temp, candidate)

    response = _apply(source, _patch(source, [{"op": "set_text", "object": "s0:s2", "text": "recovered"}], request_id="req-next"), monkeypatch)

    assert response["ok"] is True
    assert store.requests().get("req-crash-6") is None
    assert store.requests()["req-next"]["result"]["ok"] is True
    assert store.journal() is None


def _make_review(store: StateStore, candidate: Path, token: str = "tok") -> None:
    import hashlib

    store.save_review({
        "candidate_revision": revision(candidate),
        "review_token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "qa_error_count": 0,
        "qa_issues": [],
    })


def test_prepared_published_apply_rolls_back_before_accept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """accept 入口必须先恢复崩溃现场：不接受本应回滚的 candidate 内容。"""
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    original = source.read_bytes()
    backup = candidate.with_name(f".{candidate.stem}.backup.pptx")
    temp = _temp_for(candidate)
    shutil.copy2(source, candidate)
    shutil.copy2(candidate, backup)
    shutil.copy2(candidate, temp)
    with temp.open("ab") as stream:
        stream.write(b"staged-change")
    new_revision = revision(temp)
    store.save_journal({
        "status": "prepared",
        "action": "apply",
        "request_id": "req-crash-7",
        "request_hash": "hash",
        "base_revision": revision(candidate),
        "new_revision": new_revision,
        "temp": str(temp),
        "backup": str(backup),
        "result": {"ok": True},
        "created_at": "now",
    })
    shutil.copy2(temp, candidate)  # 发布已发生
    _make_review(store, backup)  # review 对应恢复后的 candidate 内容

    response = service.accept(candidate, revision(backup), "tok")

    assert response["ok"] is True
    assert accepted_path(source).read_bytes() == original
    assert not candidate.exists()
    assert store.journal() is None


def test_accept_baseline_failure_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    shutil.copy2(source, candidate)
    _make_review(store, candidate)
    original_candidate = candidate.read_bytes()
    accepted = accepted_path(source)
    monkeypatch.setattr("ppt_agent.txn.StateStore", lambda doc_id: store)

    def failing_save_baseline(value: dict) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(store, "save_baseline", failing_save_baseline)

    with pytest.raises(OSError):
        service.accept(candidate, revision(candidate), "tok")

    assert not accepted.exists()
    assert candidate.exists()
    assert candidate.read_bytes() == original_candidate
    assert store.journal() is None
    assert store.baseline() is None


def test_discard_prepared_recovery_restores_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    shutil.copy2(source, candidate)
    original = candidate.read_bytes()
    moved = candidate.with_name(f".{candidate.stem}.moved.pptx")
    store.save_journal({
        "status": "prepared",
        "action": "discard",
        "candidate_backup": str(moved),
        "created_at": "now",
    })
    os_replace = __import__("os").replace
    os_replace(candidate, moved)  # publish 已发生

    recover_transactions(store, source)

    assert candidate.exists()
    assert candidate.read_bytes() == original
    assert not moved.exists()
    assert store.journal() is None


def test_create_prepared_published_recovery_removes_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    temp = _temp_for(candidate)
    shutil.copy2(source, temp)
    with temp.open("ab") as stream:
        stream.write(b"staged-change")
    new_revision = revision(temp)
    store.save_journal({
        "status": "prepared",
        "action": "create",
        "new_revision": new_revision,
        "temp": str(temp),
        "created_at": "now",
    })
    shutil.copy2(temp, candidate)  # 发布已发生

    recover_transactions(store, source)

    assert not candidate.exists()
    assert not temp.exists()
    assert store.journal() is None


def test_committed_accept_recovery_overwrites_old_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    accepted = accepted_path(source)
    shutil.copy2(source, candidate)
    old_baseline = {"schema_version": "2.1", "document_id": document_id(source), "revision": "sha256:old", "file_hash": "sha256:old"}
    store.save_baseline(old_baseline)
    new_baseline = {"schema_version": "2.1", "document_id": document_id(source), "revision": "sha256:new", "file_hash": "sha256:new"}
    shutil.copy2(candidate, accepted)
    store.save_journal({
        "status": "committed",
        "action": "accept",
        "new_revision": revision(accepted),
        "temp": str(_temp_for(accepted)),
        "backup": None,
        "candidate_backup": str(candidate.with_name(f".{candidate.stem}.moved.pptx")),
        "baseline": new_baseline,
        "created_at": "now",
    })

    recover_transactions(store, source)

    assert store.baseline()["revision"] == "sha256:new"
    assert store.journal() is None


def test_recovery_failure_keeps_journal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    accepted = accepted_path(source)
    shutil.copy2(source, candidate)
    baseline = {"schema_version": "2.1", "document_id": document_id(source), "revision": "sha256:new", "file_hash": "sha256:new"}
    store.save_journal({
        "status": "committed",
        "action": "accept",
        "new_revision": revision(candidate),
        "temp": str(_temp_for(accepted)),
        "backup": None,
        "candidate_backup": str(candidate.with_name(f".{candidate.stem}.moved.pptx")),
        "baseline": baseline,
        "created_at": "now",
    })

    def failing_save(value: dict) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(store, "save_baseline", failing_save)
    with pytest.raises(OSError):
        recover_transactions(store, source)
    assert store.journal() is not None  # WAL 保留，供下次继续恢复

    monkeypatch.undo()
    recover_transactions(store, source)
    assert store.baseline()["revision"] == "sha256:new"
    assert store.journal() is None


def test_accept_publish_failure_rolls_back_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    accepted = accepted_path(source)
    shutil.copy2(source, candidate)
    original_candidate = candidate.read_bytes()
    _make_review(store, candidate)
    monkeypatch.setattr("ppt_agent.txn.StateStore", lambda doc_id: store)

    real_replace = __import__("os").replace
    calls = {"count": 0}

    def failing_replace(src, dst):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("simulated second replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(service.os, "replace", failing_replace)

    with pytest.raises(OSError):
        service.accept(candidate, revision(candidate), "tok")

    assert not accepted.exists()
    assert candidate.exists()
    assert candidate.read_bytes() == original_candidate
    assert store.journal() is None
    assert store.baseline() is None


def test_crashed_accept_then_next_accept_recovers_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    accepted = accepted_path(source)
    original = source.read_bytes()
    backup = accepted.with_name(f".{accepted.stem}.backup.pptx")
    moved = candidate.with_name(f".{candidate.stem}.moved.pptx")
    temp = _temp_for(accepted)
    shutil.copy2(source, candidate)
    shutil.copy2(source, backup)
    shutil.copy2(source, temp)
    with temp.open("ab") as stream:
        stream.write(b"crashed-accept-change")
    new_revision = revision(temp)
    store.save_journal({
        "status": "prepared",
        "action": "accept",
        "new_revision": new_revision,
        "temp": str(temp),
        "backup": str(backup),
        "candidate_backup": str(moved),
        "baseline": None,
        "created_at": "now",
    })
    # 崩溃发生在 publish 完成之后：accepted=新内容、candidate 已移走。
    __import__("os").replace(candidate, moved)
    __import__("os").replace(temp, accepted)
    _make_review(store, backup)  # 恢复后的 candidate 内容 = 旧 accepted

    response = service.accept(candidate, revision(backup), "tok")

    assert response["ok"] is True
    assert accepted.read_bytes() == original
    assert not candidate.exists()
    assert store.journal() is None
    assert store.baseline() is not None


def test_rollback_pending_partial_rollback_converges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """上一次回滚恢复了 accepted 但 candidate 恢复失败：WAL=rollback_pending。
    下次恢复必须逐文件继续：恢复 candidate，而不是 roll-forward。"""
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    accepted = accepted_path(source)
    original = source.read_bytes()
    moved = candidate.with_name(f".{candidate.stem}.moved.pptx")
    shutil.copy2(source, accepted)  # 旧 accepted 已在前一次回滚中恢复
    shutil.copy2(source, moved)  # candidate 仍滞留于备份

    store.save_journal({
        "status": "rollback_pending",
        "action": "accept",
        "new_revision": "sha256:" + "f" * 64,  # 新 accepted 已不在
        "temp": str(_temp_for(accepted)),
        "backup": None,
        "candidate_backup": str(moved),
        "baseline": None,
        "created_at": "now",
    })

    recover_transactions(store, source)

    assert candidate.exists()
    assert candidate.read_bytes() == original
    assert accepted.read_bytes() == original
    assert not moved.exists()
    assert store.journal() is None
    assert store.baseline() is None  # 回滚路径不得写入 baseline


def test_record_failure_rollback_failure_keeps_rollback_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ppt_agent.txn import commit_publish

    source, store = _setup(tmp_path, monkeypatch)
    events: list[str] = []

    def publish() -> None:
        events.append("publish")

    def record() -> None:
        raise OSError("record failed")

    def rollback() -> None:
        events.append("rollback")
        raise OSError("rollback failed")

    with pytest.raises(OSError):
        commit_publish(store, {
            "status": "prepared", "action": "apply", "request_id": "req-x", "request_hash": "h",
            "new_revision": "sha256:" + "0" * 64, "result": {"ok": True}, "created_at": "now",
        }, publish, record, rollback)

    assert events == ["publish", "rollback"]
    assert store.journal()["status"] == "rollback_pending"


def test_cleanup_failure_marks_cleanup_pending_without_business_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ppt_agent.txn import commit_publish

    source, store = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr("ppt_agent.txn.StateStore", lambda doc_id: store)

    def cleanup() -> None:
        raise OSError("cleanup failed")

    commit_publish(store, {
        "status": "prepared", "action": "apply", "request_id": "req-c", "request_hash": "h",
        "new_revision": "sha256:" + "0" * 64, "temp": str(_temp_for(candidate_path(source))),
        "result": {"ok": True}, "created_at": "now",
    }, lambda: None, lambda: None, lambda: None, cleanup=cleanup)

    assert store.journal()["status"] == "cleanup_pending"

    recover_transactions(store, source)
    assert store.journal() is None


def test_corrupt_journal_blocks_writes_and_keeps_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    store.journal_path.parent.mkdir(parents=True, exist_ok=True)
    store.journal_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(PptAgentError) as caught:
        recover_transactions(store, source)
    assert caught.value.code == "TRANSACTION_JOURNAL_CORRUPT"
    assert store.journal_path.read_text(encoding="utf-8") == "{broken"  # 原文件保留供诊断

    # 写事务入口同样被阻断，不会覆盖 WAL。
    with pytest.raises(PptAgentError):
        _apply(source, _patch(source, [{"op": "set_text", "object": "s0:s2", "text": "x"}]), monkeypatch)


def _guarded_mark_failing(status_to_fail: str):
    def guarded(self, status: str) -> None:
        if status == status_to_fail:
            raise OSError(f"journal write failed for {status}")

        from ppt_agent.state import StateStore

        StateStore.mark_journal(self, status)

    return guarded


def test_rollback_pending_persist_failure_skips_rollback_committed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ppt_agent.txn import commit_publish

    source, store = _setup(tmp_path, monkeypatch)
    events: list[str] = []
    entry = {
        "status": "prepared", "action": "apply", "request_id": "req-x", "request_hash": "h",
        "new_revision": "sha256:" + "0" * 64, "temp": str(_temp_for(candidate_path(source))),
        "result": {"ok": True}, "created_at": "now",
    }

    def record() -> None:
        raise OSError("record failed")

    def rollback() -> None:
        events.append("rollback")

    monkeypatch.setattr(store, "mark_journal", _guarded_mark_failing("rollback_pending").__get__(store))

    with pytest.raises(OSError):
        commit_publish(store, entry, lambda: None, record, rollback)

    assert events == []  # 回滚决定未持久化 → 不执行任何文件副作用
    assert store.journal()["status"] == "committed"

    monkeypatch.undo()
    recover_transactions(store, source)  # 按已持久化的 committed roll-forward
    assert store.requests()["req-x"]["result"] == {"ok": True}
    assert store.journal() is None


def test_rollback_pending_persist_failure_skips_rollback_prepared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ppt_agent.txn import commit_publish

    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    events: list[str] = []
    shutil.copy2(source, candidate)
    new_revision = revision(candidate)
    entry = {
        "status": "prepared", "action": "apply", "request_id": "req-p", "request_hash": "h",
        "new_revision": new_revision, "temp": str(_temp_for(candidate)),
        "result": {"ok": True}, "created_at": "now",
    }

    def publish() -> None:
        raise OSError("publish failed")

    def rollback() -> None:
        events.append("rollback")

    monkeypatch.setattr(store, "mark_journal", _guarded_mark_failing("rollback_pending").__get__(store))

    with pytest.raises(OSError):
        commit_publish(store, entry, publish, lambda: None, rollback)

    assert events == []  # 不修改文件
    assert store.journal()["status"] == "prepared"

    monkeypatch.undo()
    recover_transactions(store, source)  # 按 prepared 回滚
    assert not candidate.exists()
    assert store.journal() is None
    assert store.requests() == {}


def test_post_commit_clear_failure_returns_business_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ppt_agent.txn import commit_publish

    source, store = _setup(tmp_path, monkeypatch)
    entry = {
        "status": "prepared", "action": "apply", "request_id": "req-c2", "request_hash": "h",
        "new_revision": "sha256:" + "0" * 64, "temp": str(_temp_for(candidate_path(source))),
        "result": {"ok": True}, "created_at": "now",
    }

    def failing_clear() -> None:
        raise OSError("unlink busy")

    monkeypatch.setattr(store, "clear_journal", failing_clear)
    commit_publish(store, entry, lambda: None, lambda: None, lambda: None)  # 不得抛异常

    assert store.journal()["status"] == "committed"

    monkeypatch.undo()
    recover_transactions(store, source)
    assert store.journal() is None
    assert store.requests()["req-c2"]["result"] == {"ok": True}


def test_cleanup_and_mark_failure_still_returns_business_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ppt_agent.txn import commit_publish

    source, store = _setup(tmp_path, monkeypatch)
    entry = {
        "status": "prepared", "action": "apply", "request_id": "req-c3", "request_hash": "h",
        "new_revision": "sha256:" + "0" * 64, "temp": str(_temp_for(candidate_path(source))),
        "result": {"ok": True}, "created_at": "now",
    }

    def failing_cleanup() -> None:
        raise OSError("cleanup failed")

    monkeypatch.setattr(store, "mark_journal", _guarded_mark_failing("cleanup_pending").__get__(store))
    commit_publish(store, entry, lambda: None, lambda: None, lambda: None, cleanup=failing_cleanup)  # 不得抛异常

    assert store.journal()["status"] == "committed"

    monkeypatch.undo()
    recover_transactions(store, source)
    assert store.journal() is None


@pytest.mark.parametrize("entry", [
    {},  # status/action 都不得猜测
    {"action": "discard", "candidate_backup": "unused"},
    {"status": "prepared"},
    {"status": "weird", "action": "apply"},
    {"status": "prepared", "action": "merge"},
    {"status": "prepared", "action": "apply", "request_id": "r", "temp": "unused"},
    {
        "status": "committed", "action": "apply", "request_id": "r",
        "new_revision": "sha256:new", "temp": "unused",
    },  # committed apply 缺少 result
    {"status": "prepared", "action": "accept", "temp": "unused", "candidate_backup": "unused"},
    {
        "status": "committed", "action": "accept", "new_revision": "sha256:new",
        "temp": "unused", "candidate_backup": "unused",
    },  # committed accept 缺少 baseline
    {"status": "prepared", "action": "discard"},
    {
        "status": "cleanup_pending", "action": "create", "new_revision": "sha256:new",
        "temp": "unused",
    },
])
def test_journal_validation_rejects_invalid_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: dict
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    store.save_journal(entry)

    with pytest.raises(PptAgentError) as caught:
        recover_transactions(store, source)
    assert caught.value.code == "TRANSACTION_JOURNAL_CORRUPT"
    assert store.journal_path.exists()  # WAL 保留


def test_journal_validation_rejects_formal_files_without_deleting_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    accepted = accepted_path(source)
    shutil.copy2(source, candidate)
    shutil.copy2(source, accepted)
    store.save_baseline({"revision": "sha256:baseline"})
    store.save_review({"candidate_revision": "sha256:review"})
    store.save_requests({"req": {"result": {"ok": True}}})
    protected = [
        source,
        candidate,
        accepted,
        store.baseline_path,
        store.review_path,
        store.requests_path,
    ]

    for path in protected:
        before = path.read_bytes()
        store.save_journal({
            "status": "cleanup_pending",
            "action": "apply",
            "request_id": "req-malicious",
            "new_revision": "sha256:new",
            "temp": str(path),
            "result": {"ok": True},
        })

        with pytest.raises(PptAgentError) as caught:
            recover_transactions(store, source)

        assert caught.value.code == "TRANSACTION_JOURNAL_CORRUPT"
        assert path.read_bytes() == before
        assert store.journal_path.exists()


@pytest.mark.parametrize("path_key", ["temp", "backup", "candidate_backup"])
def test_journal_validation_rejects_non_derived_same_directory_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path_key: str
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    ordinary = source.parent / f"ordinary-{path_key}.pptx"
    ordinary.write_bytes(b"must-survive")
    entry = {
        "status": "prepared",
        "action": "accept",
        "new_revision": "sha256:new",
        "temp": str(_temp_for(accepted_path(source))),
        "backup": None,
        "candidate_backup": str(candidate.with_name(f".{candidate.stem}.moved.pptx")),
        "baseline": None,
    }
    entry[path_key] = str(ordinary)
    store.save_journal(entry)

    with pytest.raises(PptAgentError) as caught:
        recover_transactions(store, source)

    assert caught.value.code == "TRANSACTION_JOURNAL_CORRUPT"
    assert ordinary.read_bytes() == b"must-survive"
    assert store.journal_path.exists()


def test_journal_validation_rejects_temp_name_with_non_mkstemp_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, store = _setup(tmp_path, monkeypatch)
    candidate = candidate_path(source)
    lookalike = candidate.with_name(f".{candidate.stem}.not-a-temp.pptx")
    lookalike.write_bytes(b"must-survive")
    store.save_journal({
        "status": "prepared",
        "action": "apply",
        "request_id": "req-lookalike",
        "new_revision": "sha256:new",
        "temp": str(lookalike),
        "backup": None,
        "result": {"ok": True},
    })

    with pytest.raises(PptAgentError) as caught:
        recover_transactions(store, source)

    assert caught.value.code == "TRANSACTION_JOURNAL_CORRUPT"
    assert lookalike.read_bytes() == b"must-survive"
    assert store.journal_path.exists()

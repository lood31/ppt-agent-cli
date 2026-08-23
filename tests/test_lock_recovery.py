from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ppt_agent.errors import PptAgentError
from ppt_agent.state import StateStore, _process_alive


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> StateStore:
    monkeypatch.setenv("PPT_AGENT_STATE_DIR", str(tmp_path / "state"))
    return StateStore("doc-id")


def _dead_pid() -> int:
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def test_process_alive_detects_live_and_dead() -> None:
    assert _process_alive(0) is False
    assert _process_alive(-1) is False
    assert _process_alive(1 << 30) is False  # unrealistic pid on this machine
    assert _process_alive(_dead_pid()) is False


def test_lock_is_released_after_normal_use(store: StateStore) -> None:
    with store.lock():
        assert store.lock_path.exists()
    assert not store.lock_path.exists()


def test_live_holder_within_lease_blocks(store: StateStore) -> None:
    import os

    store.lock_path.parent.mkdir(parents=True, exist_ok=True)
    store.lock_path.write_text(json.dumps({
        "token": "other", "pid": os.getpid(),
        "created_at": time.time(), "lease_seconds": 1800.0,
    }), encoding="utf-8")
    with pytest.raises(PptAgentError) as caught:
        with store.lock(wait_seconds=0):
            pass
    assert caught.value.code == "DOCUMENT_LOCKED"


def test_dead_holder_lock_is_taken_over(store: StateStore) -> None:
    dead_pid = _dead_pid()
    store.lock_path.parent.mkdir(parents=True, exist_ok=True)
    store.lock_path.write_text(json.dumps({
        "token": "dead-holder", "pid": dead_pid,
        "created_at": time.time(), "lease_seconds": 1800.0,
    }), encoding="utf-8")
    with store.lock(wait_seconds=0):
        content = json.loads(store.lock_path.read_text(encoding="utf-8"))
        assert content["token"] != "dead-holder"
        assert content["pid"] != dead_pid
    assert not store.lock_path.exists()


def test_expired_lease_does_not_steal_from_live_holder(store: StateStore) -> None:
    import os

    store.lock_path.parent.mkdir(parents=True, exist_ok=True)
    # 租约几乎立即过期，但持有者为本进程（创建时间早于锁时间）→ 真持有者，不得抢占。
    store.lock_path.write_text(json.dumps({
        "token": "live-holder", "pid": os.getpid(),
        "created_at": time.time(), "lease_seconds": 0.0001,
    }), encoding="utf-8")
    with pytest.raises(PptAgentError) as caught:
        with store.lock(wait_seconds=0):
            pass
    assert caught.value.code == "DOCUMENT_LOCKED"
    content = json.loads(store.lock_path.read_text(encoding="utf-8"))
    assert content["token"] == "live-holder"


def test_reused_pid_is_taken_over_even_when_alive(store: StateStore) -> None:
    # 活进程，但其启动时间晚于锁创建时间 → 判定为 PID 复用 → 接管。
    holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
    try:
        store.lock_path.parent.mkdir(parents=True, exist_ok=True)
        store.lock_path.write_text(json.dumps({
            "token": "reused-holder", "pid": holder.pid,
            "created_at": time.time() - 3600, "lease_seconds": 1800.0,
        }), encoding="utf-8")
        with store.lock(wait_seconds=0):
            content = json.loads(store.lock_path.read_text(encoding="utf-8"))
            assert content["token"] != "reused-holder"
        assert not store.lock_path.exists()
    finally:
        holder.terminate()
        holder.wait()


def test_corrupted_lock_file_is_treated_as_stale(store: StateStore) -> None:
    store.lock_path.parent.mkdir(parents=True, exist_ok=True)
    store.lock_path.write_text("{broken", encoding="utf-8")
    with store.lock(wait_seconds=0):
        assert store.lock_path.exists()
    assert not store.lock_path.exists()


def test_guard_release_retries_transient_windows_share_violation(
    store: StateStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.lock_path.parent.mkdir(parents=True, exist_ok=True)
    token = "guard-owner"
    descriptor = store._acquire_guard(token, time.monotonic() + 1)
    assert descriptor is not None
    original_unlink = Path.unlink
    attempts = 0

    def transient_failure(path: Path, *args, **kwargs) -> None:
        nonlocal attempts
        if path == store.guard_path and attempts == 0:
            attempts += 1
            raise PermissionError(32, "sharing violation", str(path))
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", transient_failure)
    store._release_guard(descriptor, token)

    assert attempts == 1
    assert not store.guard_path.exists()


def test_holder_does_not_delete_successor_lock(store: StateStore) -> None:
    store.lock_path.parent.mkdir(parents=True, exist_ok=True)
    first = store.lock_path
    with store.lock():
        pass
    assert not first.exists()


WORKER_SCRIPT = """
import json, sys, time
from pathlib import Path
from ppt_agent.state import StateStore

store = StateStore("contention-doc")
with store.lock(wait_seconds=10):
    start = time.perf_counter()
    time.sleep(0.4)
    end = time.perf_counter()
Path(sys.argv[1]).write_text(json.dumps({"start": start, "end": end}), encoding="utf-8")
"""


def test_two_process_contention_has_single_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PPT_AGENT_STATE_DIR", str(tmp_path / "state"))
    outputs = [tmp_path / f"worker-{index}.json" for index in range(4)]
    processes = [
        subprocess.Popen([sys.executable, "-c", WORKER_SCRIPT, str(output)])
        for output in outputs
    ]
    for process in processes:
        assert process.wait(timeout=60) == 0

    intervals = []
    for output in outputs:
        data = json.loads(output.read_text(encoding="utf-8"))
        intervals.append((data["start"], data["end"]))
    events: list[tuple[float, int]] = []
    for start, end in intervals:
        events.append((start, 1))
        events.append((end, -1))
    events.sort()
    active = 0
    peak = 0
    for _, delta in events:
        active += delta
        peak = max(peak, active)
    assert peak == 1, f"max concurrent writers was {peak}"


WORKER_SCRIPT_RACE = """
import json, os, sys, time
from pathlib import Path
from ppt_agent.state import StateStore

store = StateStore("contention-doc")
# 先对初始（损坏）锁做一次快照读取，确保所有进程在同一损坏现场起跑。
try:
    store.lock_path.read_bytes()
except FileNotFoundError:
    pass
ready_dir = Path(sys.argv[2])
(ready_dir / (str(os.getpid()) + ".ready")).write_text("1", encoding="utf-8")
worker_count = int(sys.argv[3])
deadline = time.time() + 30
while len(list(ready_dir.glob("*.ready"))) < worker_count:
    if time.time() > deadline:
        sys.exit(2)
    time.sleep(0.01)
with store.lock(wait_seconds=15):
    start = time.perf_counter()
    time.sleep(0.4)
    end = time.perf_counter()
Path(sys.argv[1]).write_text(json.dumps({"start": start, "end": end}), encoding="utf-8")
"""


def test_corrupt_initial_lock_four_process_contention_single_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PPT_AGENT_STATE_DIR", str(tmp_path / "state"))
    # 预置损坏的初始锁：所有等待者先在 barrier 同步，再一起竞争接管。
    lock_dir = tmp_path / "state" / "locks"
    lock_dir.mkdir(parents=True)
    (lock_dir / "contention-doc.lock").write_text("{broken", encoding="utf-8")
    ready_dir = tmp_path / "ready"
    ready_dir.mkdir()

    outputs = [tmp_path / f"worker-{index}.json" for index in range(4)]
    processes = [
        subprocess.Popen([sys.executable, "-c", WORKER_SCRIPT_RACE, str(output), str(ready_dir), "4"])
        for output in outputs
    ]
    for process in processes:
        assert process.wait(timeout=90) == 0

    intervals = []
    for output in outputs:
        data = json.loads(output.read_text(encoding="utf-8"))
        intervals.append((data["start"], data["end"]))
    events: list[tuple[float, int]] = []
    for start, end in intervals:
        events.append((start, 1))
        events.append((end, -1))
    events.sort()
    active = 0
    peak = 0
    for _, delta in events:
        active += delta
        peak = max(peak, active)
    assert peak == 1, f"max concurrent writers was {peak}"

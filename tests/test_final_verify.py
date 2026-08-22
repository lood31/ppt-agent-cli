from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from pptx import Presentation
from pptx.oxml.ns import qn

from ppt_agent import service
from ppt_agent.errors import PptAgentError
from ppt_agent.ooxml import transitions_by_slide
from ppt_agent.paths import candidate_path, document_id, revision
from ppt_agent.state import StateStore

FIXTURE = Path("fixtures/synthetic/synthetic.pptx")


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    source = tmp_path / "deck.pptx"
    shutil.copy2(FIXTURE, source)
    monkeypatch.setenv("PPT_AGENT_STATE_DIR", str(tmp_path / "state"))
    return source


def _patch(source: Path, operations: list[dict]) -> Path:
    patch = {
        "document_id": document_id(source),
        "revision": revision(source),
        "operations": operations,
    }
    patch_path = source.parent / "patch.json"
    patch_path.write_text(json.dumps(patch), encoding="utf-8")
    return patch_path


def _noop_wps(path: Path) -> dict:
    return {"wps_version": "test"}


def test_final_reopen_verify_sees_restored_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _setup(tmp_path, monkeypatch)
    order: list[str] = []
    seen: list[dict | None] = []

    def recording_finalize(path: Path) -> dict:
        order.append("finalize")
        return {"wps_version": "test"}

    def recording_reopen(path: Path) -> dict:
        order.append("reopen")
        seen.append(transitions_by_slide(path)[0])
        return {"slide_count": 4, "wps_version": "test"}

    monkeypatch.setattr(service.wps, "finalize", recording_finalize)
    monkeypatch.setattr(service.wps, "reopen_verify", recording_reopen)

    response = service.apply(source, _patch(source, [{
        "op": "set_slide", "slide": 0, "transition": {"type": "push", "dir": "l", "speed": "fast"},
    }]), allow_risk={"external_relationship"})

    assert response["ok"] is True
    assert order == ["finalize", "reopen"]
    assert seen == [{"type": "push", "dir": "l", "speed": "fast"}]
    assert response["wps_version"] == "test"
    candidate = candidate_path(source)
    assert transitions_by_slide(candidate)[0] == {"type": "push", "dir": "l", "speed": "fast"}


def test_final_read_only_reopen_keeps_file_hash_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _setup(tmp_path, monkeypatch)
    recorded_hashes: list[str] = []

    def hashing_reopen(path: Path) -> dict:
        recorded_hashes.append(hashlib.sha256(path.read_bytes()).hexdigest())
        return {"slide_count": 4, "wps_version": "test"}

    monkeypatch.setattr(service.wps, "finalize", _noop_wps)
    monkeypatch.setattr(service.wps, "reopen_verify", hashing_reopen)

    service.apply(source, _patch(source, [{
        "op": "set_slide", "slide": 0, "transition": {"type": "fade"},
    }]), allow_risk={"external_relationship"})

    candidate = candidate_path(source)
    final_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    assert recorded_hashes == [final_hash]


def test_final_reopen_that_modifies_file_blocks_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _setup(tmp_path, monkeypatch)
    original = source.read_bytes()

    def modifying_reopen(path: Path) -> dict:
        with path.open("ab") as stream:
            stream.write(b"tamper")
        return {"slide_count": 4, "wps_version": "test"}

    monkeypatch.setattr(service.wps, "finalize", _noop_wps)
    monkeypatch.setattr(service.wps, "reopen_verify", modifying_reopen)

    with pytest.raises(PptAgentError) as caught:
        service.apply(source, _patch(source, [{
            "op": "set_slide", "slide": 0, "transition": {"type": "fade"},
        }]), allow_risk={"external_relationship"})

    assert caught.value.code == "WPS_REOPEN_MODIFIED_FILE"
    assert not candidate_path(source).exists()
    assert source.read_bytes() == original
    assert StateStore(document_id(source)).requests() == {}


def test_final_reopen_failure_publishes_nothing_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _setup(tmp_path, monkeypatch)
    original = source.read_bytes()

    def failing_reopen(path: Path) -> dict:
        raise PptAgentError("WPS_REOPEN_FAILED", "WPS 重开失败", "retry", retryable=True)

    monkeypatch.setattr(service.wps, "finalize", _noop_wps)
    monkeypatch.setattr(service.wps, "reopen_verify", failing_reopen)

    with pytest.raises(PptAgentError) as caught:
        service.apply(source, _patch(source, [{
            "op": "set_slide", "slide": 0, "transition": {"type": "fade"},
        }]), allow_risk={"external_relationship"})

    assert caught.value.code == "WPS_REOPEN_FAILED"
    assert not candidate_path(source).exists()
    assert source.read_bytes() == original
    assert StateStore(document_id(source)).requests() == {}
    leftovers = [item for item in source.parent.iterdir() if item.name.startswith(".")]
    assert leftovers == []


def test_transition_type_mismatch_after_wps_blocks_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _setup(tmp_path, monkeypatch)
    original = source.read_bytes()

    def type_switching_finalize(path: Path) -> dict:
        # Simulate WPS rewriting the transition to a different effect type.
        prs = Presentation(path)
        sld = prs.slides[0]._element
        tr = sld.find(qn("p:transition"))
        assert tr is not None
        for child in tr:
            child.tag = qn("p:wipe")
            break
        prs.save(path)
        return {"wps_version": "test"}

    monkeypatch.setattr(service.wps, "finalize", type_switching_finalize)
    monkeypatch.setattr(service.wps, "reopen_verify", _noop_wps)

    with pytest.raises(PptAgentError) as caught:
        service.apply(source, _patch(source, [{
            "op": "set_slide", "slide": 0, "transition": {"type": "push", "dir": "l"},
        }]), allow_risk={"external_relationship"})

    assert caught.value.code == "TRANSITION_FIDELITY_FAILED"
    assert not candidate_path(source).exists()
    assert source.read_bytes() == original
    assert StateStore(document_id(source)).requests() == {}


def test_push_then_none_batch_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(service.wps, "finalize", _noop_wps)
    monkeypatch.setattr(service.wps, "reopen_verify", _noop_wps)

    response = service.apply(source, _patch(source, [
        {"op": "set_slide", "slide": 0, "transition": {"type": "push", "dir": "l"}},
        {"op": "set_slide", "slide": 0, "transition": "none"},
    ]), allow_risk={"external_relationship"})

    assert response["ok"] is True
    assert transitions_by_slide(candidate_path(source))[0] is None


def test_push_none_push_batch_restores_final_transition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(service.wps, "finalize", _noop_wps)
    monkeypatch.setattr(service.wps, "reopen_verify", _noop_wps)

    response = service.apply(source, _patch(source, [
        {"op": "set_slide", "slide": 0, "transition": {"type": "push", "dir": "l"}},
        {"op": "set_slide", "slide": 0, "transition": "none"},
        {"op": "set_slide", "slide": 0, "transition": {"type": "push", "dir": "r"}},
    ]), allow_risk={"external_relationship"})

    assert response["ok"] is True
    assert transitions_by_slide(candidate_path(source))[0] == {"type": "push", "dir": "r"}


def test_engine_then_wps_transition_last_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _setup(tmp_path, monkeypatch)
    calls: list[str] = []

    def recording_wps(path: Path, operations: list[dict]) -> dict:
        calls.extend(operation["op"] for operation in operations)
        return {"applied": len(operations), "wps_version": "test"}

    monkeypatch.setattr(service.wps, "apply_wps_operations", recording_wps)
    monkeypatch.setattr(service.wps, "reopen_verify", _noop_wps)

    response = service.apply(source, _patch(source, [
        {"op": "set_slide", "slide": 0, "transition": {"type": "push", "dir": "l"}},
        {"op": "set_transition", "slide": 0, "transition": "fade"},
    ]), allow_risk={"external_relationship"})

    assert response["ok"] is True
    assert calls == ["set_transition"]
    # WPS wrote last: no stale push restore should have failed or leaked in.


def test_wps_then_engine_transition_last_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(service.wps, "apply_wps_operations",
                        lambda path, operations: {"applied": len(operations), "wps_version": "test"})
    monkeypatch.setattr(service.wps, "finalize", _noop_wps)
    monkeypatch.setattr(service.wps, "reopen_verify", _noop_wps)

    response = service.apply(source, _patch(source, [
        {"op": "set_transition", "slide": 0, "transition": "fade"},
        {"op": "set_slide", "slide": 0, "transition": {"type": "push", "dir": "l"}},
    ]), allow_risk={"external_relationship"})

    assert response["ok"] is True
    assert transitions_by_slide(candidate_path(source))[0] == {"type": "push", "dir": "l"}

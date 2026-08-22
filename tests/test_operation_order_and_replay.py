from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from ppt_agent import service
from ppt_agent.paths import document_id, revision

FIXTURE = Path("fixtures/synthetic/synthetic.pptx")
IMAGE = Path("fixtures/synthetic/synthetic-image.png")

_replay_counter = 0


def _apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operations: list[dict],
    *,
    finalize: object | None = None,
) -> dict:
    global _replay_counter
    _replay_counter += 1
    case_dir = tmp_path / f"case-{_replay_counter}"
    case_dir.mkdir()
    source = case_dir / "deck.pptx"
    shutil.copy2(FIXTURE, source)
    monkeypatch.setenv("PPT_AGENT_STATE_DIR", str(case_dir / "state"))
    if finalize is None:
        finalize = lambda path: {"wps_version": "test"}
    monkeypatch.setattr(service.wps, "finalize", finalize)
    monkeypatch.setattr(service.wps, "reopen_verify", lambda path: {"wps_version": "test"})
    patch = {
        "document_id": document_id(source),
        "revision": revision(source),
        "operations": operations,
    }
    patch_path = case_dir / "patch.json"
    patch_path.write_text(json.dumps(patch), encoding="utf-8")
    return service.apply(source, patch_path, allow_risk={"external_relationship"})


def test_mixed_operations_execute_in_declared_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, list[str]]] = []
    real_apply_operations = service.apply_operations

    def recording_engine(source: Path, operations: list[dict], output: Path) -> dict:
        calls.append(("engine", [operation["op"] for operation in operations]))
        return real_apply_operations(source, operations, output)

    def recording_wps(path: Path, operations: list[dict]) -> dict:
        calls.append(("wps", [operation["op"] for operation in operations]))
        return {"applied": len(operations), "wps_version": "test"}

    def recording_finalize(path: Path) -> dict:
        calls.append(("finalize", []))
        return {"wps_version": "test"}

    monkeypatch.setattr(service, "apply_operations", recording_engine)
    monkeypatch.setattr(service.wps, "apply_wps_operations", recording_wps)

    response = _apply(tmp_path, monkeypatch, [
        {"op": "set_transition", "slide": 0, "transition": "fade"},
        {"op": "set_text", "object": "s0:s2", "text": "transition first, then text"},
    ], finalize=recording_finalize)

    assert response["ok"] is True
    assert calls == [
        ("wps", ["set_transition"]),
        ("engine", ["set_text"]),
        ("finalize", []),
    ]


def test_consecutive_operations_batch_by_kind_without_reordering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, list[str]]] = []
    real_apply_operations = service.apply_operations

    def recording_engine(source: Path, operations: list[dict], output: Path) -> dict:
        calls.append(("engine", [operation["op"] for operation in operations]))
        return real_apply_operations(source, operations, output)

    def recording_wps(path: Path, operations: list[dict]) -> dict:
        calls.append(("wps", [operation["op"] for operation in operations]))
        return {"applied": len(operations), "wps_version": "test"}

    def recording_finalize(path: Path) -> dict:
        calls.append(("finalize", []))
        return {"wps_version": "test"}

    monkeypatch.setattr(service, "apply_operations", recording_engine)
    monkeypatch.setattr(service.wps, "apply_wps_operations", recording_wps)

    response = _apply(tmp_path, monkeypatch, [
        {"op": "set_text", "object": "s0:s2", "text": "first"},
        {"op": "set_style", "object": "s0:s2", "font_size": 28},
        {"op": "set_transition", "slide": 1, "transition": "fade"},
        {"op": "add_animation", "object": "s0:s5", "effect": "fade"},
        {"op": "move", "object": "s0:s5", "x": 1.0, "y": 1.0},
    ], finalize=recording_finalize)

    assert response["ok"] is True
    assert calls == [
        ("engine", ["set_text", "set_style"]),
        ("wps", ["set_transition", "add_animation"]),
        ("engine", ["move"]),
        ("finalize", []),
    ]


def test_batch_ending_with_wps_skips_finalize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[str]]] = []
    real_apply_operations = service.apply_operations

    def recording_engine(source: Path, operations: list[dict], output: Path) -> dict:
        calls.append(("engine", [operation["op"] for operation in operations]))
        return real_apply_operations(source, operations, output)

    def recording_wps(path: Path, operations: list[dict]) -> dict:
        calls.append(("wps", [operation["op"] for operation in operations]))
        return {"applied": len(operations), "wps_version": "test"}

    def fail_if_finalized(path: Path) -> dict:
        raise AssertionError("finalize must not run when the batch ends with WPS operations")

    monkeypatch.setattr(service, "apply_operations", recording_engine)
    monkeypatch.setattr(service.wps, "apply_wps_operations", recording_wps)

    response = _apply(tmp_path, monkeypatch, [
        {"op": "set_text", "object": "s0:s2", "text": "engine first"},
        {"op": "set_transition", "slide": 0, "transition": "fade"},
    ], finalize=fail_if_finalized)

    assert response["ok"] is True
    assert calls == [
        ("engine", ["set_text"]),
        ("wps", ["set_transition"]),
    ]


def test_wps_only_apply_skips_finalize(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    def recording_wps(path: Path, operations: list[dict]) -> dict:
        calls.append(("wps", [operation["op"] for operation in operations]))
        return {"applied": len(operations), "wps_version": "test"}

    def fail_if_called(path: Path) -> dict:
        raise AssertionError("finalize must not run when WPS operations executed")

    monkeypatch.setattr(service.wps, "apply_wps_operations", recording_wps)
    monkeypatch.setattr(service.wps, "finalize", fail_if_called)

    response = _apply(tmp_path, monkeypatch, [
        {"op": "set_transition", "slide": 0, "transition": "none"},
    ])

    assert response["ok"] is True
    assert calls == [("wps", ["set_transition"])]


# Real-engine replay: every schema branch that previously passed validation but
# failed at execution must now either be rejected at schema level or succeed.

def test_replay_text_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for text in [
        "plain string",
        ["line one", "line two"],
        [{"text": "paragraph dict"}],
        [{"runs": [{"text": "mixed ", "bold": True}, {"text": "runs"}]}],
    ]:
        response = _apply(tmp_path, monkeypatch, [{"op": "set_text", "object": "s0:s2", "text": text}])
        assert response["ok"] is True


def test_replay_move_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = _apply(tmp_path, monkeypatch, [{"op": "move", "object": "s0:s5", "x": 1.0, "y": 0.8}])
    assert response["ok"] is True
    response = _apply(tmp_path, monkeypatch, [{"op": "move", "object": "s0:s5", "dx": 0.25, "dy": 0.0}])
    assert response["ok"] is True


def test_replay_resize_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = _apply(tmp_path, monkeypatch, [{"op": "resize", "object": "s0:s2", "width": 4.0, "height": 1.5}])
    assert response["ok"] is True
    response = _apply(tmp_path, monkeypatch, [{"op": "resize", "object": "s0:s2", "scale": 0.8}])
    assert response["ok"] is True


def test_replay_add_shape_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = _apply(tmp_path, monkeypatch, [{
        "op": "add_shape", "slide": 0, "kind": "textbox",
        "x": 1, "y": 2, "width": 4, "height": 1.5, "text": "label",
    }])
    assert response["ok"] is True
    response = _apply(tmp_path, monkeypatch, [{
        "op": "add_shape", "slide": 0, "kind": "line", "from": [0, 0], "to": [5, 5],
    }])
    assert response["ok"] is True


def test_replay_swap_image_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image = str(IMAGE.resolve())
    for operation in [
        {"op": "swap_image", "object": "s0:s4", "image": image},
        {"op": "swap_image", "rid": "rId3", "slide": 0, "image": image},
        {"op": "swap_image", "media": "image1.png", "image": image},
    ]:
        response = _apply(tmp_path, monkeypatch, [operation])
        assert response["ok"] is True


def test_replay_set_theme_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for operation in [
        {"op": "set_theme", "colors": {"accent1": "BB7B19"}},
        {"op": "set_theme", "fonts": {"major": "Georgia"}},
        {"op": "set_theme", "colors": {"accent2": "112233"}, "fonts": {"minor": "Arial"}},
    ]:
        response = _apply(tmp_path, monkeypatch, [operation])
        assert response["ok"] is True


def test_replay_add_table_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = {"op": "add_table", "slide": 1, "at": [0.5, 1.5], "size": [9, 3]}
    response = _apply(tmp_path, monkeypatch, [{**base, "rows": [["A", "B"], ["1", "2"]]}])
    assert response["ok"] is True
    response = _apply(tmp_path, monkeypatch, [{
        **base,
        "rows": [["A", "B"], ["1", "2"]],
        "fills": [["112233", "none"], [None, "445566"]],
        "col_widths": [4.5, 4.5],
    }])
    assert response["ok"] is True


def test_replay_set_slide_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for operation in [
        {"op": "set_slide", "slide": 0, "hidden": True},
        {"op": "set_slide", "slide": 0, "background": "FFFFFF"},
        {"op": "set_slide", "slide": 0, "transition": "none"},
        {"op": "set_slide", "slide": 0, "transition": {"type": "fade"}},
        {"op": "set_slide", "slide": 0, "transition": {"type": "push", "dir": "l"}},
        {"op": "set_slide", "slide": 0, "transition": {"type": "split", "orient": "horz", "dir": "in"}},
    ]:
        response = _apply(tmp_path, monkeypatch, [operation])
        assert response["ok"] is True


def test_replay_duplicate_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    response = _apply(tmp_path, monkeypatch, [{"op": "duplicate", "object": "s0:s5", "offset": [0, 1.2]}])
    assert response["ok"] is True
    response = _apply(tmp_path, monkeypatch, [{"op": "duplicate", "object": "s0:s5", "at": [1.0, 2.0]}])
    assert response["ok"] is True


def test_replay_misc_branches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cases = [
        {"op": "replace_text", "from": "保真测试稿", "to": "替换后", "scope": "deck"},
        {"op": "replace_color", "from": "143846", "to": "112233", "scope": "deck"},
        {"op": "set_notes", "slide": 0, "notes": "讲者备注"},
        {"op": "set_props", "title": "项目汇报", "author": "团队"},
        {"op": "set_style", "object": "s0:s2", "font_size": 32},
        {"op": "set_style", "object": "s0:s5", "fill": "112233", "rotation": 15},
        {"op": "reorder", "object": "s0:s5", "z": "front"},
        {"op": "copy_shape", "from_slide": 0, "shape": "s5", "slide": 1, "at": [1, 2]},
        {"op": "add_picture", "slide": 1, "image": str(IMAGE.resolve()), "at": [1, 2], "width": 2},
        {"op": "add_slide", "layout": 0, "at": 2},
        {"op": "set_text", "object": "s0:s8", "text": "cell text", "cell": [0, 1]},
        {"op": "add_row", "object": "s0:s8", "cells": ["A", "B", "C"], "at": 1},
        {"op": "add_col", "object": "s0:s8", "cells": ["X", "Y"], "at": 1},
        {"op": "delete_row", "object": "s0:s8", "row": 1},
        {"op": "delete_col", "object": "s0:s8", "col": 2},
        {"op": "delete", "object": "s0:s7"},
    ]
    for operation in cases:
        response = _apply(tmp_path, monkeypatch, [operation])
        assert response["ok"] is True, operation


def test_schema_rejected_forms_never_reach_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ppt_agent.errors import PptAgentError

    rejected = [
        {"op": "add_shape", "slide": 0, "kind": "line", "from": [0, 0], "to": [5, 5], "text": "x"},
        {"op": "add_table", "slide": 1, "at": [0, 0], "size": [9, 3],
         "rows": [["A", "B"], ["1", "2"]], "fills": [["112233"]]},
        {"op": "set_theme", "colors": {}},
        {"op": "swap_image", "rid": "rId3", "image": str(IMAGE.resolve())},
        {"op": "set_slide", "slide": 0, "transition": {"type": "fade", "dir": "l"}},
        {"op": "set_text", "object": "s0:s2", "text": [{"text": "a", "runs": [{"text": "b"}]}]},
    ]
    for operation in rejected:
        with pytest.raises(PptAgentError) as caught:
            _apply(tmp_path, monkeypatch, [operation])
        assert caught.value.code == "INVALID_PATCH", operation
        assert caught.value.details["document_unchanged"] is True

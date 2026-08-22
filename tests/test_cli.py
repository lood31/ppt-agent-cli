from __future__ import annotations

import io
import json

import pytest

from ppt_agent import cli, service
from ppt_agent.errors import PptAgentError
from ppt_agent.models import OPERATION_GUIDE, OPERATION_MODELS, OPERATION_USE_WHEN


COMMANDS = [
    (["doctor"], "doctor"),
    (["capabilities"], "capabilities"),
    (["inspect", "deck.pptx"], "inspect"),
    (["diff", "deck.pptx", "other.pptx"], "diff"),
    (["create", "spec.json", "--output", "deck.pptx"], "create"),
    (["apply", "deck.pptx", "patch.json"], "apply"),
    (["render", "deck.pptx"], "render"),
    (["qa", "deck.pptx"], "qa"),
    (["template", "inspect", "deck.pptx"], "template"),
    (["cache", "status"], "cache_status"),
    (["accept", "deck.agent.candidate.pptx", "--revision", "r", "--review-token", "t"], "accept"),
    (["discard", "deck.pptx"], "discard"),
    (["schema", "apply"], None),
]


@pytest.mark.parametrize(("argv", "target"), COMMANDS)
def test_thirteen_commands_dispatch(argv: list[str], target: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake(*args, **kwargs):
        nonlocal called
        called = True
        return service.result(argv[0])

    if target:
        monkeypatch.setattr(service, target, fake)
    payload = cli._dispatch(cli._parser().parse_args(argv))
    assert called is (target is not None)
    assert payload["ok"] is True


def test_main_success_is_json_and_exit_zero(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "_dispatch", lambda args: {"ok": True, "command": args.command})
    with pytest.raises(SystemExit) as caught:
        cli.main(["doctor"])
    assert caught.value.code == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "command": "doctor"}


def test_main_domain_error_is_json_and_exit_one(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    def fail(args):
        raise PptAgentError("TEST_FAILURE", "测试失败", "retry", retryable=True)

    monkeypatch.setattr(cli, "_dispatch", fail)
    with pytest.raises(SystemExit) as caught:
        cli.main(["doctor"])
    assert caught.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["error_code"] == "TEST_FAILURE"
    assert payload["retryable"] is True
    assert payload["next_action"] == "retry"


@pytest.mark.parametrize(
    "argv",
    [
        ["apply", "deck.pptx", "patch.json"],
        ["apply", "deck.pptx", "--patch", "patch.json"],
    ],
)
def test_apply_patch_file_forms_dispatch_first_time(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake(file, patch, **kwargs):
        captured.update({"file": file, "patch": patch, **kwargs})
        return service.result("apply")

    monkeypatch.setattr(service, "apply", fake)
    payload = cli._dispatch(cli._parser().parse_args(argv))

    assert payload["ok"] is True
    assert str(captured["patch"]) == "patch.json"
    assert captured["patch_text"] is None


def test_apply_stdin_passes_complete_patch_request(monkeypatch: pytest.MonkeyPatch) -> None:
    patch = {"document_id": "doc", "revision": "sha256:" + "0" * 64, "operations": []}
    captured = {}

    def fake(file, patch_path, **kwargs):
        captured.update({"patch_path": patch_path, **kwargs})
        return service.result("apply")

    monkeypatch.setattr(service, "apply", fake)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(json.dumps(patch)))
    payload = cli._dispatch(cli._parser().parse_args(["apply", "deck.pptx", "-"]))

    assert payload["ok"] is True
    assert captured["patch_path"] is None
    assert json.loads(captured["patch_text"]) == patch


def test_inspect_accepts_and_echoes_ignored_allow_risk(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake(file, **kwargs):
        captured.update({"file": file, **kwargs})
        return service.result("inspect", data={"ignored_allow_risk": sorted(kwargs["allow_risk"])})

    monkeypatch.setattr(service, "inspect", fake)
    args = cli._parser().parse_args([
        "inspect",
        "deck.pptx",
        "--for",
        "content",
        "--allow-risk",
        "external_relationship",
    ])
    payload = cli._dispatch(args)

    assert captured["allow_risk"] == {"external_relationship"}
    assert payload["data"]["ignored_allow_risk"] == ["external_relationship"]


@pytest.mark.parametrize("inline", ['{"operations":[]}', '[{"op":"delete"}]'])
def test_apply_inline_json_returns_exact_usage(inline: str) -> None:
    with pytest.raises(PptAgentError) as caught:
        cli._dispatch(cli._parser().parse_args(["apply", "deck.pptx", inline]))

    assert caught.value.code == "INVALID_PATCH_ARGUMENT"
    assert caught.value.details["corrected_usage"] == [
        "ppt-agent apply deck.pptx patch.json",
        "ppt-agent apply deck.pptx --patch patch.json",
        "Get-Content patch.json -Raw | ppt-agent apply deck.pptx -",
    ]


def test_schema_apply_single_operation_is_compact_and_actionable() -> None:
    args = cli._parser().parse_args(["schema", "apply", "--op", "move"])
    payload = cli._dispatch(args)
    data = payload["data"]
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    assert data["op"] == "move"
    assert data["example"] == {"op": "move", "object": "s0:s2", "x": 1.05, "y": 0.6}
    assert data["schema"]["oneOf"] == [
        {
            "required": ["x", "y"],
            "properties": {"x": {"not": {"type": "null"}}, "y": {"not": {"type": "null"}}},
        },
        {
            "required": ["dx", "dy"],
            "properties": {"dx": {"not": {"type": "null"}}, "dy": {"not": {"type": "null"}}},
        },
    ]
    assert data["wps"] is False
    assert len(encoded) < 8 * 1024


def test_schema_apply_defaults_to_compact_operation_catalog() -> None:
    payload = cli._dispatch(cli._parser().parse_args(["schema", "apply"]))
    data = payload["data"]
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    assert data["operations"] == [
        {"op": op, "use_when": OPERATION_USE_WHEN[op], "wps": OPERATION_GUIDE[op]["wps"]}
        for op in OPERATION_MODELS
    ]
    assert data["next_action"] == "ppt-agent schema apply --op <name>"
    assert data["full_schema"] == "ppt-agent schema apply --full"
    assert "schema" not in data
    assert len(encoded) < 8 * 1024


@pytest.mark.parametrize("meta_operation", ["query", "list", "catalog", "查询", "列表"])
def test_schema_meta_operation_returns_catalog_without_retry(meta_operation: str) -> None:
    payload = cli._dispatch(cli._parser().parse_args(["schema", "apply", "--op", meta_operation]))

    assert payload["ok"] is True
    assert payload["data"]["interpreted_as"] == "operation_catalog"
    assert payload["data"]["operations"]


def test_unknown_schema_operation_is_structured() -> None:
    args = cli._parser().parse_args(["schema", "apply", "--op", "moev"])

    with pytest.raises(PptAgentError) as caught:
        cli._dispatch(args)

    assert caught.value.code == "UNKNOWN_OPERATION"
    assert "move" in caught.value.details["nearest"]


def test_argparse_error_uses_json_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["inspect"])

    payload = json.loads(capsys.readouterr().out)
    assert caught.value.code == 1
    assert payload["error_code"] == "INVALID_ARGUMENT"
    assert payload["next_action"] == "use_corrected_usage"


def test_schema_apply_full_is_explicit() -> None:
    payload = cli._dispatch(cli._parser().parse_args(["schema", "apply", "--full"]))

    assert "schema" in payload["data"]
    assert "operations" in payload["data"]["schema"]["properties"]


@pytest.mark.parametrize("op", sorted(OPERATION_MODELS))
def test_every_operation_has_a_valid_discoverable_example(op: str) -> None:
    guide = OPERATION_GUIDE[op]
    operation = OPERATION_MODELS[op].model_validate(guide["example"])

    assert operation.op == op
    assert guide["errors"]
    assert isinstance(guide["wps"], bool)
    assert OPERATION_USE_WHEN[op]

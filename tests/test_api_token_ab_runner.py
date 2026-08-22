from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import run_api_token_ab as runner


def test_current_ab_standard_is_luna_max() -> None:
    assert runner.MODEL == "gpt-5.6-luna"
    assert runner.REASONING_EFFORT == "max"
    assert "memories" in runner.B_CODEX_FLAGS
    assert "plugins" in runner.B_CODEX_FLAGS
    assert "skill_search" in runner.B_CODEX_FLAGS
    assert any("anthropics-skills-pptx" in item and "enabled=false" in item for item in runner.B_CODEX_FLAGS)


def test_a_arm_isolated_from_product_and_prior_evidence() -> None:
    rule = runner.A_RULE
    assert "只使用已安装的 pptx skill" in rule
    for forbidden in ("README", "DESIGN", "memory", "ppt-agent", "其他实验输出", "递归搜索项目目录"):
        assert forbidden in rule
    assert str(runner.A_PYTHON) in rule
    assert str(runner.A_THUMBNAIL) in rule
    assert "markitdown 未安装，不要调用" in rule
    assert "不要直接调用 pdftoppm" in rule
    assert f"& '{runner.A_PYTHON}' '{runner.A_THUMBNAIL}'" in rule
    assert runner.CODEX_PACKAGE == "@openai/codex@0.148.0"


def test_a_runtime_requires_fixed_qa_dependencies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    python = tmp_path / "python.exe"
    thumbnail = tmp_path / "thumbnail.py"
    python.write_bytes(b"stub")
    thumbnail.write_text("# stub\n", encoding="utf-8")
    monkeypatch.setattr(runner, "A_PYTHON", python)
    monkeypatch.setattr(runner, "A_THUMBNAIL", thumbnail)
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: runner.subprocess.CompletedProcess(args[0], 1, "", "missing defusedxml"),
    )

    with pytest.raises(RuntimeError, match="QA 依赖不完整"):
        runner.validate_a_runtime()


def test_runtime_preflight_requires_code_mode_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    codex = tmp_path / "codex.exe"
    codex.write_bytes(b"stub")
    monkeypatch.setattr(runner, "CODEX_EXE", codex)

    with pytest.raises(FileNotFoundError, match="code-mode host"):
        runner.validate_codex_runtime()


def _make_a_run(root: Path) -> Path:
    run = root / "token-api" / "baseline"
    usage = []
    for scenario, names in runner.INPUT_NAMES.items():
        work = run / f"scenario-{scenario}" / "A"
        work.mkdir(parents=True)
        for name in names:
            (work / name).write_bytes(f"{scenario}:{name}".encode())
        (work / "events.jsonl").write_text('{"type":"turn.completed"}\n', encoding="utf-8")
        (work / "output.pptx").write_bytes(f"output:{scenario}".encode())
        usage.append(
            {
                "scenario": scenario,
                "arm": "A",
                "model": runner.MODEL,
                "returncode": 0,
                "output_exists": True,
                "turn_completed_events": 1,
                "input_tokens": 100,
            }
        )
    (run / "usage.json").write_text(json.dumps(usage), encoding="utf-8")
    return run


def test_frozen_a_is_reused_as_exact_b_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_root = tmp_path / "token-api"
    _make_a_run(tmp_path)
    manifest_path = tmp_path / "baseline.json"
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "TOKEN_API_ROOT", token_root)
    monkeypatch.setattr(runner, "codex_version", lambda: "codex-cli test")

    manifest = runner.freeze_a("baseline", manifest_path)
    validated = runner.load_and_validate_baseline(manifest_path)
    out = tmp_path / "new-run"
    runner.prepare_b(out, validated, completed=set(), scenarios=list(runner.TASKS))

    assert manifest["protocol_sha256"] == runner.canonical_sha256(runner.a_protocol_payload())
    for scenario, names in runner.INPUT_NAMES.items():
        for name in names:
            assert (out / f"scenario-{scenario}" / "B" / name).read_bytes() == (
                token_root / "baseline" / f"scenario-{scenario}" / "A" / name
            ).read_bytes()


def test_frozen_a_rejects_tampered_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_root = tmp_path / "token-api"
    _make_a_run(tmp_path)
    manifest_path = tmp_path / "baseline.json"
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "TOKEN_API_ROOT", token_root)
    monkeypatch.setattr(runner, "codex_version", lambda: "codex-cli test")
    runner.freeze_a("baseline", manifest_path)

    (token_root / "baseline" / "scenario-01" / "A" / "content.json").write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match="缺失或被改动"):
        runner.load_and_validate_baseline(manifest_path)


def test_frozen_a_rejects_protocol_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_root = tmp_path / "token-api"
    _make_a_run(tmp_path)
    manifest_path = tmp_path / "baseline.json"
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "TOKEN_API_ROOT", token_root)
    monkeypatch.setattr(runner, "codex_version", lambda: "codex-cli test")
    runner.freeze_a("baseline", manifest_path)
    monkeypatch.setattr(runner, "MODEL", "different-model")

    with pytest.raises(ValueError, match="A 实验协议已漂移"):
        runner.load_and_validate_baseline(manifest_path)


def test_frozen_a_allows_b_protocol_to_evolve(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_root = tmp_path / "token-api"
    _make_a_run(tmp_path)
    manifest_path = tmp_path / "baseline.json"
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "TOKEN_API_ROOT", token_root)
    monkeypatch.setattr(runner, "codex_version", lambda: "codex-cli test")
    runner.freeze_a("baseline", manifest_path)
    monkeypatch.setattr(runner, "B_RULE", "new B-only interface contract")

    assert runner.load_and_validate_baseline(manifest_path)["baseline_run_id"] == "baseline"


def test_run_a_reuses_only_frozen_fixture_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_root = tmp_path / "token-api"
    _make_a_run(tmp_path)
    fixture_manifest = tmp_path / "fixture-baseline.json"
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "TOKEN_API_ROOT", token_root)
    monkeypatch.setattr(runner, "codex_version", lambda: "codex-cli test")
    monkeypatch.setattr(runner, "validate_codex_runtime", lambda: "codex-cli test")
    monkeypatch.setattr(runner, "validate_a_runtime", lambda: None)
    runner.freeze_a("baseline", fixture_manifest)

    def fake_run_one(out: Path, scenario: str, arm: str) -> dict[str, object]:
        work = out / f"scenario-{scenario}" / arm
        (work / "events.jsonl").write_text("{}\n", encoding="utf-8")
        (work / "output.pptx").write_bytes(b"new-luna-output")
        return {
            "scenario": scenario,
            "arm": arm,
            "model": runner.MODEL,
            "returncode": 0,
            "output_exists": True,
            "turn_completed_events": 1,
        }

    monkeypatch.setattr(runner, "run_one", fake_run_one)
    runner.run_a("luna-a", scenarios=["01"], fixture_manifest_path=fixture_manifest)

    assert (token_root / "luna-a" / "scenario-01" / "A" / "content.json").read_bytes() == (
        token_root / "baseline" / "scenario-01" / "A" / "content.json"
    ).read_bytes()
    usage = json.loads((token_root / "luna-a" / "usage.json").read_text(encoding="utf-8"))
    assert len(usage) == 1
    assert usage[0]["arm"] == "A"
    assert usage[0]["model"] == "gpt-5.6-luna"


def test_run_a_rejects_protocol_drift_before_resuming(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_root = tmp_path / "token-api"
    _make_a_run(tmp_path)
    fixture_manifest = tmp_path / "fixture-baseline.json"
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "TOKEN_API_ROOT", token_root)
    monkeypatch.setattr(runner, "codex_version", lambda: "codex-cli test")
    monkeypatch.setattr(runner, "validate_codex_runtime", lambda: "codex-cli test")
    monkeypatch.setattr(runner, "validate_a_runtime", lambda: None)
    runner.freeze_a("baseline", fixture_manifest)

    run = token_root / "luna-a"
    run.mkdir(parents=True)
    (run / "usage.json").write_text(
        json.dumps([{"scenario": "01", "arm": "A", "returncode": 0, "output_exists": True, "turn_completed_events": 1}]),
        encoding="utf-8",
    )
    (run / "fixture-reference.json").write_text(json.dumps({"a_protocol_sha256": "old"}), encoding="utf-8")

    with pytest.raises(ValueError, match="必须使用新的 run id"):
        runner.run_a("luna-a", scenarios=["02"], fixture_manifest_path=fixture_manifest)


def test_b_prompt_isolation_rejects_old_skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        runner.subprocess,
        "run",
        lambda *args, **kwargs: runner.subprocess.CompletedProcess(
            args[0], 0, "anthropics-skills-pptx", ""
        ),
    )

    with pytest.raises(RuntimeError, match="禁用上下文"):
        runner.validate_b_prompt_isolation()


def test_run_one_streams_evidence_and_marks_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    work = tmp_path / "run" / "scenario-01" / "A"
    work.mkdir(parents=True)

    class FakeProcess:
        pid = 4321
        waits = 0

        def wait(self, timeout: int) -> int:
            self.waits += 1
            if self.waits == 1:
                raise runner.subprocess.TimeoutExpired("codex", timeout)
            return -9

        def kill(self) -> None:
            return None

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "RUN_TIMEOUT_SECONDS", 1)

    result = runner.run_one(tmp_path / "run", "01", "A")

    assert result["returncode"] == 124
    assert result["timed_out"] is True
    assert result["timeout_seconds"] == 1
    assert result["turn_completed_events"] == 0
    assert (work / "events.jsonl").is_file()
    assert (work / "stderr.log").is_file()


def test_freeze_a_rejects_missing_official_usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_root = tmp_path / "token-api"
    run = _make_a_run(tmp_path)
    usage_path = run / "usage.json"
    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    usage[0].pop("turn_completed_events")
    usage_path.write_text(json.dumps(usage), encoding="utf-8")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "TOKEN_API_ROOT", token_root)

    with pytest.raises(ValueError, match="官方 usage"):
        runner.freeze_a("baseline", tmp_path / "baseline.json")


def test_run_a_stops_after_first_failed_measurement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_root = tmp_path / "token-api"
    _make_a_run(tmp_path)
    fixture_manifest = tmp_path / "fixture-baseline.json"
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "TOKEN_API_ROOT", token_root)
    monkeypatch.setattr(runner, "codex_version", lambda: "codex-cli test")
    monkeypatch.setattr(runner, "validate_codex_runtime", lambda: "codex-cli test")
    monkeypatch.setattr(runner, "validate_a_runtime", lambda: None)
    runner.freeze_a("baseline", fixture_manifest)
    calls: list[str] = []

    def fail_first(out: Path, scenario: str, arm: str) -> dict[str, object]:
        calls.append(scenario)
        return {
            "scenario": scenario,
            "arm": arm,
            "returncode": 124,
            "output_exists": False,
            "turn_completed_events": 0,
        }

    monkeypatch.setattr(runner, "run_one", fail_first)
    with pytest.raises(RuntimeError, match="停止后续 API 调用"):
        runner.run_a("failed", scenarios=["01", "02"], fixture_manifest_path=fixture_manifest)

    assert calls == ["01"]

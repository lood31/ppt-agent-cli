from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TOKEN_API_ROOT = ROOT / "results" / "local" / "token-api"
BASELINE_MANIFEST = ROOT / "acceptance" / "ab" / "api-token-a-baseline.json"
LEGACY_FIXTURE_MANIFEST = ROOT / "acceptance" / "ab" / "api-token-a-baseline-gpt54.json"
CODEX_PACKAGE = "@openai/codex@0.148.0"
CODEX_RUNTIME = TOKEN_API_ROOT / "_codex_runtime_0148"
CODEX_EXE = Path(os.environ.get("PPT_AGENT_AB_CODEX_BIN", CODEX_RUNTIME / "codex.exe"))
CODEX_COMMAND = (str(CODEX_EXE),)
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "max"
RUN_TIMEOUT_SECONDS = 1200
OLD_PPTX_SKILL = Path(
    os.environ.get(
        "PPT_AGENT_AB_OLD_PPTX_SKILL",
        Path.home() / ".codex" / "skills" / "anthropics-skills-pptx" / "SKILL.md",
    )
)
B_CODEX_FLAGS = (
    "--ignore-user-config",
    "-c", f'skills.config=[{{path="{OLD_PPTX_SKILL.as_posix()}",enabled=false}}]',
    "--disable", "memories",
    "--disable", "external_agent_memory_import",
    "--disable", "plugins",
    "--disable", "skill_search",
    "--disable", "recommended_plugins",
)
B_PROMPT_PROBE_FLAGS = B_CODEX_FLAGS[1:]
A_PYTHON = Path(os.environ.get("PPT_AGENT_AB_A_PYTHON", ROOT / ".venv" / "Scripts" / "python.exe"))
A_THUMBNAIL = Path(
    os.environ.get(
        "PPT_AGENT_AB_A_THUMBNAIL",
        Path.home() / ".codex" / "skills" / "anthropics-skills-pptx" / "scripts" / "thumbnail.py",
    )
)

COMMON = """这是一次受控 API Token A/B。只完成指定 PPT 任务，不修改产品源码，不联网，不做额外功能。必须真实调用工具并生成 output.pptx；不得复制已有候选或基准输出。完成后只简短报告输出路径与是否成功。"""

TASKS = {
    "01": "依据 content.json 从零制作完整的 8 页 16:9 演讲稿。",
    "02": "编辑 source.pptx：标题改为 Python 编程作业汇报；三条正文改为目标：实现可靠文件处理、方法：测试驱动迭代、结果：关键用例全部通过；按钮改为课程验收；表格第二行改为测试、11/11、全通过；后三页标题改为模块测试结果、迭代质量趋势、代码模块占比。",
    "03": "编辑 source.pptx：第一页标题改为 MVP 真实试用记录并右移 0.25 英寸；把第一页现有图片替换为 replacement.png，保持原图片框尺寸。",
    "04": "审查 broken-source.pptx 的确定性排版问题并修复：越界标题移回页内，8pt 标题改为 32pt；其他内容不变。",
    "05": "编辑 source.pptx：第一页动画目标形状添加 fade/on_click；第一页三段正文添加 appear/with_previous 的逐段动画。",
    "06": "比较 before.pptx 与 after.pptx，识别人工修改方向；在 after.pptx 上续改第二页标题为 柱状图｜按人工风格续改，并右移 0.25 英寸。",
}

A_RULE = (
    "必须只使用已安装的 pptx skill 原工作流；创建用 PptxGenJS，编辑用 "
    f"unpack/edit/clean/pack。运行 skill 的 Python 脚本时直接使用 {A_PYTHON}，不要搜索或猜测解释器。"
    f"内容 QA 只用该解释器中已安装的 python-pptx；markitdown 未安装，不要调用。视觉 QA 在 PowerShell 直接运行 "
    f"& '{A_PYTHON}' '{A_THUMBNAIL}' output.pptx thumbnails --cols 4；路径引号不可省略；不要直接调用 pdftoppm，"
    "不要查找其他渲染器或 Python。"
    "除当前场景输入和已安装 pptx skill 文档/脚本外，禁止读取"
    "项目 README、DESIGN、POC_PLAN、agent.md、acceptance、results、memory、ppt-agent "
    "源码/测试/Schema/可执行文件或其他实验输出；禁止调用 ppt-agent；禁止递归搜索项目目录。"
)
B_RULE = f"必须只通过 {ROOT / 'dist' / 'ppt-agent.exe'} 完成。先等待 capabilities 成功返回；需要某项操作参数时，把 capabilities 列出的实际操作名填入 schema apply --op <operation>，不要把 query/查询当作操作名；结构只用 inspect --for/--fields 定向读取。Windows 下补丁优先写为 patch.json，再用 apply FILE --patch patch.json；不要用 PowerShell here-string 向 stdin 内联 JSON。inspect 若报告风险，只对任务明确需要保留的类型显式传入 --allow-risk。禁止直接编辑 PPTX/XML，禁止使用 PptxGenJS，禁止搜索项目源码、memory、现有 pptx skill 文档或递归列目录。候选完成后复制为 output.pptx。"

INPUT_NAMES = {
    "01": ("content.json",),
    "02": ("source.pptx",),
    "03": ("source.pptx", "replacement.png"),
    "04": ("broken-source.pptx",),
    "05": ("source.pptx",),
    "06": ("before.pptx", "after.pptx"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def has_official_usage(item: dict[str, object]) -> bool:
    return int(item.get("turn_completed_events", 0)) > 0


def is_successful_measurement(item: dict[str, object]) -> bool:
    return item.get("returncode") == 0 and bool(item.get("output_exists")) and has_official_usage(item)


def a_protocol_payload() -> dict[str, object]:
    return {
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "common": COMMON,
        "tasks": TASKS,
        "a_rule": A_RULE,
    }


def b_protocol_payload() -> dict[str, object]:
    return {
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
        "common": COMMON,
        "tasks": TASKS,
        "b_rule": B_RULE,
        "codex_flags": B_CODEX_FLAGS,
    }


def codex_version() -> str:
    completed = subprocess.run(
        [*CODEX_COMMAND, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
    )
    if completed.returncode != 0:
        raise RuntimeError(f"无法读取 Codex CLI 版本：{completed.stderr.strip()}")
    return completed.stdout.strip()


def validate_codex_runtime() -> str:
    if not CODEX_EXE.is_file():
        raise FileNotFoundError(
            f"Codex 运行时不存在：{CODEX_EXE}；从 {CODEX_PACKAGE} 提取 codex.exe、"
            "codex-code-mode-host.exe 和 codex-command-runner.exe 到同一目录"
        )
    host = CODEX_EXE.with_name("codex-code-mode-host.exe")
    if not host.is_file():
        raise FileNotFoundError(f"Codex code-mode host 不存在：{host}；拒绝启动付费实验")
    version = codex_version()
    if version != "codex-cli 0.148.0":
        raise RuntimeError(f"Codex CLI 版本不匹配：期望 codex-cli 0.148.0，实际 {version}")
    return version


def validate_a_runtime() -> None:
    if not A_PYTHON.is_file():
        raise FileNotFoundError(f"A 臂固定 Python 不存在：{A_PYTHON}")
    if not A_THUMBNAIL.is_file():
        raise FileNotFoundError(f"A 臂固定 thumbnail.py 不存在：{A_THUMBNAIL}")
    probe = subprocess.run(
        [
            str(A_PYTHON),
            "-c",
            "import defusedxml, PIL, pptx; print('A runtime ready')",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if probe.returncode != 0:
        raise RuntimeError(f"A 臂 QA 依赖不完整：{probe.stderr.strip()}")


def validate_b_prompt_isolation() -> None:
    completed = subprocess.run(
        [
            *CODEX_COMMAND,
            "debug",
            "prompt-input",
            *B_PROMPT_PROBE_FLAGS,
            "ppt-agent B isolation preflight",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"B 臂提示隔离探针失败：{completed.stderr.strip()}")
    forbidden = ("anthropics-skills-pptx", "memories/MEMORY.md", "<memory")
    found = [item for item in forbidden if item.lower() in completed.stdout.lower()]
    if found:
        raise RuntimeError(f"B 臂提示仍含禁用上下文：{', '.join(found)}")


def freeze_a(baseline_run_id: str, manifest_path: Path = BASELINE_MANIFEST) -> dict[str, Any]:
    baseline_dir = TOKEN_API_ROOT / baseline_run_id
    usage_path = baseline_dir / "usage.json"
    if not usage_path.is_file():
        raise FileNotFoundError(f"A 基线 usage.json 不存在：{usage_path}")
    usage = json.loads(usage_path.read_text(encoding="utf-8"))
    scenarios: dict[str, Any] = {}
    for scenario, names in INPUT_NAMES.items():
        matches = [item for item in usage if str(item.get("scenario")) == scenario and item.get("arm") == "A"]
        if (
            len(matches) != 1
            or not is_successful_measurement(matches[0])
        ):
            raise ValueError(f"场景 {scenario} 没有唯一、成功且含官方 usage 的 A 臂计量结果")
        work = baseline_dir / f"scenario-{scenario}" / "A"
        required = [*names, "events.jsonl", "output.pptx"]
        missing = [name for name in required if not (work / name).is_file()]
        if missing:
            raise FileNotFoundError(f"场景 {scenario} A 臂证据缺失：{', '.join(missing)}")
        scenarios[scenario] = {
            "inputs": [
                {
                    "name": name,
                    "path": (work / name).relative_to(ROOT).as_posix(),
                    "sha256": sha256_file(work / name),
                }
                for name in names
            ],
            "events": {
                "path": (work / "events.jsonl").relative_to(ROOT).as_posix(),
                "sha256": sha256_file(work / "events.jsonl"),
            },
            "output": {
                "path": (work / "output.pptx").relative_to(ROOT).as_posix(),
                "sha256": sha256_file(work / "output.pptx"),
            },
            "usage": matches[0],
        }
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "baseline_run_id": baseline_run_id,
        "codex_cli_version": codex_version(),
        "protocol": a_protocol_payload(),
        "protocol_sha256": canonical_sha256(a_protocol_payload()),
        "scenarios": scenarios,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_and_validate_baseline(manifest_path: Path = BASELINE_MANIFEST, *, check_cli: bool = True) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"A 基线清单不存在：{manifest_path}；先使用 --freeze-a 固化本次 A")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("不支持的 A 基线清单版本")
    expected_protocol = canonical_sha256(a_protocol_payload())
    if manifest.get("protocol_sha256") != expected_protocol or manifest.get("protocol") != a_protocol_payload():
        raise ValueError("A 实验协议已漂移：模型、推理档位、任务文本或 A 约束与封存结果不一致")
    if check_cli:
        current_cli_version = codex_version()
        if manifest.get("codex_cli_version") != current_cli_version:
            raise ValueError(
                f"Codex CLI 版本已漂移：基线为 {manifest.get('codex_cli_version')}，当前为 {current_cli_version}"
            )
    for scenario, names in INPUT_NAMES.items():
        record = manifest.get("scenarios", {}).get(scenario)
        if not record:
            raise ValueError(f"A 基线缺少场景 {scenario}")
        inputs = record.get("inputs", [])
        if tuple(item.get("name") for item in inputs) != names:
            raise ValueError(f"场景 {scenario} 的输入文件清单已漂移")
        for item in [*inputs, record.get("events", {}), record.get("output", {})]:
            path = ROOT / str(item.get("path", ""))
            if not path.is_file() or sha256_file(path) != item.get("sha256"):
                raise ValueError(f"A 基线证据缺失或被改动：{path}")
    return manifest


def prepare_b(out: Path, manifest: dict[str, Any], completed: set[str], scenarios: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for scenario in scenarios:
        if scenario in completed:
            continue
        work = out / f"scenario-{scenario}" / "B"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        for item in manifest["scenarios"][scenario]["inputs"]:
            shutil.copy2(ROOT / item["path"], work / item["name"])


def load_fixture_inputs(manifest_path: Path = LEGACY_FIXTURE_MANIFEST) -> dict[str, list[dict[str, str]]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixtures: dict[str, list[dict[str, str]]] = {}
    for scenario, names in INPUT_NAMES.items():
        inputs = manifest.get("scenarios", {}).get(scenario, {}).get("inputs", [])
        if tuple(item.get("name") for item in inputs) != names:
            raise ValueError(f"场景 {scenario} 的夹具清单无效")
        for item in inputs:
            path = ROOT / item["path"]
            if not path.is_file() or sha256_file(path) != item.get("sha256"):
                raise ValueError(f"场景 {scenario} 的夹具缺失或被改动：{path}")
        fixtures[scenario] = inputs
    return fixtures


def run_a(
    run_id: str,
    *,
    scenarios: list[str] | None = None,
    fixture_manifest_path: Path = LEGACY_FIXTURE_MANIFEST,
) -> None:
    validate_codex_runtime()
    validate_a_runtime()
    selected = scenarios or list(TASKS)
    out = TOKEN_API_ROOT / run_id
    usage_path = out / "usage.json"
    existing = json.loads(usage_path.read_text(encoding="utf-8")) if usage_path.exists() else []
    if any(item.get("arm") != "A" for item in existing):
        raise ValueError("A 基线目录含有其他实验臂，拒绝混合实验")
    fixtures = load_fixture_inputs(fixture_manifest_path)
    reference_path = out / "fixture-reference.json"
    reference = {
        "fixture_manifest": fixture_manifest_path.relative_to(ROOT).as_posix(),
        "fixture_manifest_sha256": sha256_file(fixture_manifest_path),
        "a_protocol": a_protocol_payload(),
        "a_protocol_sha256": canonical_sha256(a_protocol_payload()),
    }
    if existing:
        if not reference_path.is_file():
            raise ValueError("续跑 A 目录缺少 fixture-reference.json，拒绝混合实验")
        stored_reference = json.loads(reference_path.read_text(encoding="utf-8"))
        if canonical_sha256(stored_reference) != canonical_sha256(reference):
            raise ValueError("续跑 A 实验协议或夹具已漂移，必须使用新的 run id")
    completed = {
        str(item["scenario"])
        for item in existing
        if is_successful_measurement(item)
    }
    out.mkdir(parents=True, exist_ok=True)
    reference_path.write_text(
        json.dumps(reference, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    results = list(existing)
    for scenario in selected:
        if scenario in completed:
            print(json.dumps({"scenario": scenario, "arm": "A", "status": "retained"}, ensure_ascii=False), flush=True)
            continue
        work = out / f"scenario-{scenario}" / "A"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        for item in fixtures[scenario]:
            shutil.copy2(ROOT / item["path"], work / item["name"])
        result = run_one(out, scenario, "A")
        results = [item for item in results if not (item.get("scenario") == scenario and item.get("arm") == "A")]
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        usage_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not is_successful_measurement(result):
            raise RuntimeError(f"场景 {scenario} A 测量失败；证据已保存，停止后续 API 调用")


def run_one(out: Path, scenario: str, arm: str) -> dict[str, object]:
    work = out / f"scenario-{scenario}" / arm
    rule = A_RULE if arm == "A" else B_RULE
    prompt = f"{COMMON}\n\n实验臂 {arm} 约束：{rule}\n\n任务：{TASKS[scenario]}\n输出必须是当前目录的 output.pptx。"
    command = [
        *CODEX_COMMAND, "exec", "--ephemeral", "--json", "-m", MODEL,
        *(B_CODEX_FLAGS if arm == "B" else ()),
        "-c", f'model_reasoning_effort="{REASONING_EFFORT}"', "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox", "-C", str(work), prompt,
    ]
    events_path = work / "events.jsonl"
    stderr_path = work / "stderr.log"
    started = time.perf_counter()
    timed_out = False
    with events_path.open("w", encoding="utf-8") as events_stream, stderr_path.open("w", encoding="utf-8") as stderr_stream:
        process = subprocess.Popen(command, stdout=events_stream, stderr=stderr_stream, text=True, encoding="utf-8", errors="replace")
        try:
            returncode = process.wait(timeout=RUN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            else:
                process.kill()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            returncode = 124
    elapsed = time.perf_counter() - started
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0}
    tool_calls = 0
    turn_completed_events = 0
    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "turn.completed":
            turn_completed_events += 1
            for key in usage:
                usage[key] += int(event.get("usage", {}).get(key, 0))
        if event.get("type") == "item.started" and event.get("item", {}).get("type") in {"command_execution", "mcp_tool_call"}:
            tool_calls += 1
    return {
        "scenario": scenario,
        "arm": arm,
        "model": MODEL,
        "returncode": returncode,
        "timed_out": timed_out,
        "timeout_seconds": RUN_TIMEOUT_SECONDS,
        "elapsed_seconds": round(elapsed, 3),
        "tool_calls": tool_calls,
        "turn_completed_events": turn_completed_events,
        "output_exists": (work / "output.pptx").is_file(),
        **usage,
    }


def run_b_only(run_id: str, manifest_path: Path = BASELINE_MANIFEST, *, scenarios: list[str] | None = None) -> None:
    validate_codex_runtime()
    validate_b_prompt_isolation()
    manifest = load_and_validate_baseline(manifest_path)
    selected = scenarios or list(TASKS)
    if run_id == manifest["baseline_run_id"]:
        raise ValueError("B-only 的 run id 不得覆盖封存 A 所在目录")
    out = TOKEN_API_ROOT / run_id
    usage_path = out / "usage.json"
    existing = json.loads(usage_path.read_text(encoding="utf-8")) if usage_path.exists() else []
    reference_path = out / "baseline-reference.json"
    if existing:
        if not reference_path.is_file():
            raise ValueError("续跑目录缺少 baseline-reference.json，拒绝混合实验")
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        if reference.get("manifest_sha256") != sha256_file(manifest_path):
            raise ValueError("续跑目录引用的 A 基线与当前基线不一致")
        if reference.get("b_protocol_sha256") != canonical_sha256(b_protocol_payload()):
            raise ValueError("续跑 B 实验协议已漂移，必须使用新的 run id")
    if existing and any(item.get("arm") == "A" and item.get("source") != "frozen_a_baseline" for item in existing):
        raise ValueError("目标目录含有非封存来源的 A 结果，拒绝混合实验")
    baseline_results = []
    for scenario in TASKS:
        item = dict(manifest["scenarios"][scenario]["usage"])
        item["source"] = "frozen_a_baseline"
        item["baseline_run_id"] = manifest["baseline_run_id"]
        baseline_results.append(item)
    b_results = [item for item in existing if item.get("arm") == "B"]
    results = baseline_results + b_results
    completed = {
        str(item["scenario"])
        for item in b_results
        if is_successful_measurement(item)
    }
    prepare_b(out, manifest, completed, selected)
    reference_path.write_text(
        json.dumps(
            {
                "manifest": manifest_path.relative_to(ROOT).as_posix(),
                "manifest_sha256": sha256_file(manifest_path),
                "baseline_run_id": manifest["baseline_run_id"],
                "protocol_sha256": manifest["protocol_sha256"],
                "b_protocol": b_protocol_payload(),
                "b_protocol_sha256": canonical_sha256(b_protocol_payload()),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    usage_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for scenario in selected:
        if scenario in completed:
            print(json.dumps({"scenario": scenario, "arm": "B", "status": "retained"}, ensure_ascii=False), flush=True)
            continue
        result = run_one(out, scenario, "B")
        results = [item for item in results if not (item.get("scenario") == scenario and item.get("arm") == "B")]
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        usage_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not is_successful_measurement(result):
            raise RuntimeError(f"场景 {scenario} B 测量失败；证据已保存，停止后续 API 调用")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="封存 API Token A 基线，或只重跑可比的 B 臂")
    parser.add_argument("--run-a", action="store_true", help="用当前模型运行新的六场景 A 基线")
    parser.add_argument("--freeze-a", action="store_true", help="从既有完整实验中封存 A，不调用 API")
    parser.add_argument("--check-baseline", action="store_true", help="只校验封存 A 和实验协议，不调用 API")
    parser.add_argument("--baseline-run-id", default="api-luna-max-a-v1", help="封存 A 的既有实验目录名")
    parser.add_argument("--run-id", help="A 或 B 输出目录名；省略时自动生成")
    parser.add_argument("--scenarios", help="只运行指定场景，逗号分隔，例如 05 或 02,04")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenarios = [item.strip().zfill(2) for item in args.scenarios.split(",") if item.strip()] if args.scenarios else None
    unknown = sorted(set(scenarios or []) - TASKS.keys())
    if unknown:
        raise ValueError(f"未知场景：{', '.join(unknown)}")
    if args.run_a:
        run_id = args.run_id or args.baseline_run_id
        run_a(run_id, scenarios=scenarios)
        return
    if args.freeze_a:
        manifest = freeze_a(args.baseline_run_id)
        print(json.dumps({"status": "a_frozen", "manifest": str(BASELINE_MANIFEST), "protocol_sha256": manifest["protocol_sha256"]}, ensure_ascii=False))
        return
    if args.check_baseline:
        manifest = load_and_validate_baseline()
        print(json.dumps({"status": "a_baseline_valid", "baseline_run_id": manifest["baseline_run_id"], "scenarios": len(manifest["scenarios"])}, ensure_ascii=False))
        return
    run_id = args.run_id or os.environ.get("PPT_AGENT_AB_RUN_ID") or f"api-luna-max-b-{datetime.now():%Y%m%d-%H%M%S}"
    run_b_only(run_id, scenarios=scenarios)


if __name__ == "__main__":
    main()

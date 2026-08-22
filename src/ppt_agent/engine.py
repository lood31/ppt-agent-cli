from __future__ import annotations

import json
import os
import re
import runpy
import shutil
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from .errors import PptAgentError
from .ooxml import strip_transition_elements, transitions_by_slide


ENGINE_COMMIT = "a24b996ecff6393ccf39c4fee2b88c493fb0b693"
ENGINE_VERSION = f"hands-on-deck@{ENGINE_COMMIT[:7]}"


def _engine_script() -> Path:
    override = os.environ.get("PPT_AGENT_ENGINE_SCRIPT")
    if override:
        return Path(override).resolve()
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "vendor" / "hands_on_deck" / "deck.py"
    return Path(__file__).resolve().parents[2] / "vendor" / "hands_on_deck" / "deck.py"


def _run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    script = _engine_script()
    if not script.exists():
        raise PptAgentError("ENGINE_MISSING", "候选 PPTX 引擎文件缺失", "reinstall")
    if getattr(sys, "frozen", False):
        return _run_embedded(script, args)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    try:
        return subprocess.run(
            [sys.executable, str(script), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PptAgentError("ENGINE_TIMEOUT", "PPTX 引擎执行超时", "retry", True) from exc


def _run_embedded(script: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    stdout = StringIO()
    stderr = StringIO()
    previous_argv = sys.argv
    previous_path = list(sys.path)
    return_code = 0
    try:
        sys.argv = [str(script), *args]
        sys.path.insert(0, str(script.parent))
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit as exc:
                return_code = int(exc.code) if isinstance(exc.code, int) else (0 if exc.code is None else 1)
                if isinstance(exc.code, str):
                    stderr.write(exc.code + "\n")
    except Exception as exc:
        return_code = 1
        stderr.write(f"{type(exc).__name__}: {exc}\n")
    finally:
        sys.argv = previous_argv
        sys.path[:] = previous_path
    return subprocess.CompletedProcess(args, return_code, stdout.getvalue(), stderr.getvalue())


def _merge_transitions(path: Path, data: dict[str, Any]) -> None:
    """Override engine transition facts with an mc:AlternateContent-aware parse."""
    try:
        parsed = transitions_by_slide(path)
    except PptAgentError:
        raise
    except Exception as exc:
        raise PptAgentError(
            "TRANSITION_PARSE_FAILED",
            "切换效果解析失败",
            "report_bug",
            details={"error": str(exc)[:500]},
        ) from exc
    slides = data.get("slides")
    if not isinstance(slides, dict):
        return
    for index, value in parsed.items():
        key = str(index)
        slide_data = slides.get(key)
        if not isinstance(slide_data, dict):
            continue
        engine_value = slide_data.get("_transition")
        if engine_value == value:
            continue
        if value is None:
            slide_data.pop("_transition", None)
        else:
            slide_data["_transition"] = value


def inspect_json(path: Path, slide: int | None = None) -> dict[str, Any]:
    args = [str(path), "inspect"]
    if slide is not None:
        args.extend(["--slide", str(slide)])
    result = _run(args)
    if result.returncode != 0:
        raise PptAgentError(
            "ENGINE_INSPECT_FAILED",
            "PPTX 结构读取失败",
            "inspect_engine_output",
            details={"engine_output": (result.stdout + result.stderr)[-2000:]},
        )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PptAgentError("ENGINE_PROTOCOL_ERROR", "引擎未返回有效 JSON", "report_bug") from exc
    _merge_transitions(path, data)
    return data


def inspect_brief(path: Path, slide: int | None = None) -> str:
    args = [str(path), "inspect", "--brief"]
    if slide is not None:
        args.extend(["--slide", str(slide)])
    result = _run(args)
    if result.returncode != 0:
        raise PptAgentError("ENGINE_INSPECT_FAILED", "PPTX 紧凑读取失败", "inspect_engine_output")
    return result.stdout.strip()


def _fmt_transition(value: dict[str, Any] | None) -> str:
    if not value:
        return "none"
    return " ".join("%s=%s" % (key, value[key]) for key in sorted(value))


def _merge_transition_diff(text: str, before: Path, after: Path) -> str:
    """Replace the engine's transition lines with authoritative ones.

    The engine only sees direct p:transition children; WPS writes them inside
    mc:AlternateContent. Vendor transition lines are always removed, then one
    correct line is reinserted per slide with a real authoritative change.
    """
    try:
        transitions_before = transitions_by_slide(before)
        transitions_after = transitions_by_slide(after)
    except PptAgentError:
        raise
    except Exception as exc:
        raise PptAgentError(
            "TRANSITION_PARSE_FAILED",
            "切换效果解析失败",
            "report_bug",
            details={"error": str(exc)[:500]},
        ) from exc
    changed: dict[int, tuple[dict[str, Any] | None, dict[str, Any] | None]] = {}
    for index in range(max(len(transitions_before), len(transitions_after))):
        value_before = transitions_before.get(index)
        value_after = transitions_after.get(index)
        if value_before != value_after:
            changed[index] = (value_before, value_after)

    # Strip exact vendor transition lines only; never filter by substring.
    stripped = [line for line in text.splitlines() if not line.startswith("  ~ transition ")]

    preamble: list[str] = []
    blocks: dict[int, list[str]] = {}
    order: list[int] = []
    current: int | None = None
    for line in stripped:
        match = re.fullmatch(r"slide (\d+):", line)
        if match:
            current = int(match.group(1))
            order.append(current)
            continue
        if current is None:
            preamble.append(line)
        else:
            blocks.setdefault(current, []).append(line)

    rebuilt: list[str] = list(preamble)
    for index in order:
        block = list(blocks.get(index, []))
        if index in changed:
            block.append(
                f"  ~ transition {_fmt_transition(changed[index][0])} -> {_fmt_transition(changed[index][1])}"
            )
        if block:
            rebuilt.append(f"slide {index}:")
            rebuilt.extend(block)
    for index in sorted(changed):
        if index in order:
            continue
        rebuilt.append(f"slide {index}:")
        rebuilt.append(
            f"  ~ transition {_fmt_transition(changed[index][0])} -> {_fmt_transition(changed[index][1])}"
        )
    if any(line.startswith("slide ") and line.endswith(":") for line in rebuilt):
        rebuilt = [line for line in rebuilt if line != "No structural differences."]
    result = "\n".join(rebuilt).strip()
    return result if result else "No structural differences."


def structural_diff(before: Path, after: Path) -> str:
    result = _run([str(before), "diff", str(after)])
    if result.returncode != 0:
        raise PptAgentError(
            "ENGINE_DIFF_FAILED",
            "PPTX 结构差异计算失败",
            "inspect_engine_output",
            details={"engine_output": (result.stdout + result.stderr)[-2000:]},
        )
    return _merge_transition_diff(result.stdout.strip(), before, after)


def _object_ref(operation: dict[str, Any]) -> tuple[int | None, str | None]:
    slide = operation.get("slide")
    shape = operation.get("shape")
    value = operation.get("object")
    if value:
        match = __import__("re").fullmatch(r"s(\d+):(s\d+|o\d+)", str(value))
        if not match:
            raise PptAgentError("INVALID_OBJECT_ID", "对象 ID 必须形如 s3:s5", "reinspect")
        slide = int(match.group(1))
        shape = match.group(2)
        if shape.startswith("o"):
            shape = "s" + shape[1:]
    return slide, shape


def translate_operation(operation: dict[str, Any]) -> dict[str, Any]:
    translated = dict(operation)
    translated.pop("object", None)
    translated.pop("expect_count", None)
    slide, shape = _object_ref(operation)
    if slide is not None:
        translated["slide"] = slide
    if shape is not None:
        translated["shape"] = shape
    translated["op"] = operation["op"].replace("_", "-")

    if operation["op"] == "set_text" and isinstance(translated.get("text"), str):
        translated["text"] = [translated["text"]]
    if operation["op"] == "move":
        if "x" in translated or "y" in translated:
            translated["to"] = [translated.pop("x"), translated.pop("y")]
        elif "by" not in translated:
            translated["by"] = [translated.pop("dx"), translated.pop("dy")]
    if operation["op"] == "resize" and "scale" not in translated and "size" not in translated:
        translated["size"] = [translated.pop("width"), translated.pop("height")]
    if operation["op"] == "add_shape" and translated.get("kind") != "line":
        if "at" not in translated:
            translated["at"] = [translated.pop("x"), translated.pop("y")]
        if "size" not in translated:
            translated["size"] = [translated.pop("width"), translated.pop("height")]
    return translated


def apply_operations(source: Path, operations: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    translated = [translate_operation(operation) for operation in operations]
    patch_path = output.with_suffix(".patch.json")
    patch_path.write_text(json.dumps({"ops": translated}, ensure_ascii=False), encoding="utf-8")
    engine_source = source
    preclean: Path | None = None
    transition_slides = {
        operation["slide"]
        for operation in translated
        if operation.get("op") == "set-slide" and "transition" in operation
    }
    try:
        if transition_slides:
            # Remove stale direct and mc:AlternateContent-wrapped transitions
            # so set-slide can replace or delete WPS-written effects.
            preclean = output.with_suffix(".preclean.pptx")
            shutil.copy2(source, preclean)
            strip_transition_elements(preclean, transition_slides)
            engine_source = preclean
        result = _run([str(engine_source), "apply", str(patch_path), "-o", str(output)])
    finally:
        try:
            patch_path.unlink()
        except FileNotFoundError:
            pass
        if preclean is not None:
            try:
                preclean.unlink()
            except FileNotFoundError:
                pass
    if result.returncode != 0:
        try:
            output.unlink()
        except FileNotFoundError:
            pass
        raise PptAgentError(
            "PATCH_REJECTED",
            "批量修改未通过预验证，未发布任何文件",
            "fix_patch",
            details={"engine_output": (result.stdout + result.stderr)[-3000:], "document_unchanged": True},
        )
    return {"engine_output": result.stdout.strip()[-2000:]}

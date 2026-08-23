from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import tempfile
import time
from difflib import get_close_matches
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from . import __version__
from .creation import create_presentation
from .engine import ENGINE_COMMIT, ENGINE_VERSION, _engine_script, apply_operations, inspect_brief, inspect_json, structural_diff
from .errors import PptAgentError
from .models import CreateSpec, OPERATIONS, PatchRequest, SCHEMA_VERSION
from .ooxml import enforce_risk_policy, restore_transition_options, security_scan, validate_pptx
from .paths import accepted_path, candidate_path, canonical_path, document_id, revision, source_path, state_root
from .plan import build_execution_plan
from .qa import run_qa
from .state import StateStore, now_iso
from .txn import commit_publish, write_transaction
from . import wps


STANDARD_OPS = {name for name, spec in OPERATIONS.items() if spec.backend == "engine"}
WPS_OPS = {name for name, spec in OPERATIONS.items() if spec.backend == "wps"}


def _read_json_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig")


def _generated_request_id(raw_patch: dict[str, Any]) -> str:
    payload = {key: value for key, value in raw_patch.items() if key != "request_id"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"auto-{hashlib.sha256(encoded).hexdigest()[:24]}"


def _corrected_patch_example(source: Path, operations: Any) -> dict[str, Any]:
    candidate = candidate_path(source)
    accepted = accepted_path(source)
    base = candidate if candidate.exists() else accepted if accepted.exists() else source
    example = {
        "document_id": document_id(source),
        "revision": revision(base),
        "operations": operations if isinstance(operations, list) and operations else [
            {"op": "set_text", "object": "s0:s2", "text": "新标题"}
        ],
    }
    example["request_id"] = _generated_request_id(example)
    return {key: example[key] for key in ("request_id", "document_id", "revision", "operations")}


def result(command: str, *, path: Path | None = None, data: dict[str, Any] | None = None, rev: str | None = None, wps_version: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "command": command,
        "document_id": document_id(source_path(path)) if path else None,
        "revision": rev or (revision(path) if path and path.exists() else None),
        "engine_version": ENGINE_VERSION,
        "wps_version": wps_version,
        "data": data or {},
    }


def _ensure_stable_revision(path: Path, expected: str) -> None:
    current = revision(path)
    if current != expected:
        raise PptAgentError(
            "REVISION_CONFLICT",
            "文档在只读操作期间发生变化，请重试",
            "retry_read",
            retryable=True,
            details={
                "expected_revision": expected,
                "current_revision": current,
                "document_unchanged": True,
            },
        )


def doctor() -> dict[str, Any]:
    import platform

    engine = _engine_script()
    pdftoppm = _pdftoppm()
    wps_probe = wps.probe()
    checks = {
        "windows": os.name == "nt",
        "python": platform.python_version(),
        "python_supported": tuple(map(int, platform.python_version_tuple())) >= (3, 12, 0),
        "engine_present": engine.exists(),
        "engine_commit": ENGINE_COMMIT,
        "soffice": shutil.which("soffice"),
        "pdftoppm": str(pdftoppm) if pdftoppm else None,
        "wps_com": bool(wps_probe["available"]),
        "wps_error": wps_probe["error"],
    }
    wps_version = wps_probe["version"]
    ok = bool(checks["windows"] and checks["python_supported"] and checks["engine_present"] and pdftoppm and wps_version)
    payload = result("doctor", data={"healthy": ok, "checks": checks}, wps_version=wps_version)
    payload["ok"] = ok
    if not ok:
        next_action = wps_probe["error"]["next_action"] if wps_probe["error"] else "install_or_repair_dependencies"
        payload.update({"error_code": "ENVIRONMENT_INCOMPLETE", "next_action": next_action})
    return payload


def capabilities() -> dict[str, Any]:
    return result("capabilities", data={
        "commands": ["doctor", "capabilities", "inspect", "diff", "create", "apply", "render", "qa", "template", "cache", "accept", "discard", "schema"],
        "agent_hints": {
            "operation_schema": "ppt-agent schema apply --op <operation>",
            "focused_inspect": "ppt-agent inspect FILE --for edit|content|layout|animation",
            "inspect_fields": "identity is always returned; x/y/width/height and shape.* aliases are accepted",
            "patch_input": "prefer: ppt-agent apply FILE --patch patch.json; stdin with - only when the caller reliably preserves stdin",
            "security_risks": "if inspect reports risks, explicitly pass each authorized type with --allow-risk",
            "qa_fix_suggestions": "ppt-agent qa FILE --profile presentation --suggest-fixes",
            "do_not_search_source": True,
        },
        "operations": {
            "ooxml": sorted(STANDARD_OPS),
            "wps": sorted(WPS_OPS),
            "animations": ["appear", "fade", "fly_in"],
            "animation_triggers": ["on_click", "with_previous", "after_previous"],
            "transitions": ["none", "fade", "push", "wipe"],
        },
        "unsupported": ["motion_path_animation", "word_animation", "complex_animation_chain", "smartart_edit", "media_edit", "ole_edit", "activex_edit"],
    })


def inspect(
    path: Path,
    *,
    slide: int | None = None,
    purpose: str | None = None,
    fields: list[str] | None = None,
    verbose: bool = False,
    no_state: bool = False,
    allow_risk: set[str] | None = None,
) -> dict[str, Any]:
    path = canonical_path(path)
    validate_pptx(path)
    scan = security_scan(path)
    doc_id = document_id(source_path(path))
    store = StateStore(doc_id)
    current_revision = revision(path)
    initialize_baseline = not no_state and store.baseline() is None and path == source_path(path)
    baseline_snapshot = _compact_snapshot(path) if initialize_baseline else None
    if purpose or fields:
        structure = _project_inspection(inspect_json(path, slide), purpose=purpose, fields=fields)
    else:
        structure = inspect_json(path, slide) if verbose else inspect_brief(path, slide)
    _ensure_stable_revision(path, current_revision)
    if initialize_baseline:
        store.save_baseline({
            "schema_version": SCHEMA_VERSION,
            "document_id": doc_id,
            "source_path": str(path),
            "file_hash": current_revision,
            "revision": current_revision,
            "created_at": now_iso(),
            "snapshot": baseline_snapshot,
        })
    payload = result("inspect", path=path, rev=current_revision, data={"security": scan, "structure": structure})
    payload["document_id"] = doc_id
    if allow_risk:
        payload["data"]["ignored_allow_risk"] = sorted(allow_risk)
    if purpose in INSPECT_PURPOSE_FIELDS:
        payload["data"]["patch_template"] = {
            "request_id": None,
            "document_id": doc_id,
            "revision": current_revision,
            "operations": [],
        }
        risk_types = [item["type"] for item in scan["risks"] if item["severity"] == "error"]
        apply_argv = ["apply", str(path), "--patch", "patch.json"]
        authorized_argv = list(apply_argv)
        for risk_type in risk_types:
            authorized_argv.extend(["--allow-risk", risk_type])
        payload["data"]["apply_contract"] = {
            "patch_file": "patch.json",
            "argv_after_executable": apply_argv,
            "risk_authorization_required": risk_types,
            "argv_after_explicit_risk_authorization": authorized_argv,
            "windows_stdin": "do_not_use_powershell_here_string",
        }
    return payload


def diff(path: Path, other: Path | None = None) -> dict[str, Any]:
    path = canonical_path(path)
    validate_pptx(path)
    if other is None:
        other = candidate_path(path)
    other = canonical_path(other)
    validate_pptx(other)
    from_revision = revision(path)
    to_revision = revision(other)
    changes = structural_diff(path, other)
    _ensure_stable_revision(path, from_revision)
    _ensure_stable_revision(other, to_revision)
    return result("diff", path=path, data={
        "from_revision": from_revision,
        "to_revision": to_revision,
        "changes": changes,
    }, rev=to_revision)


def create(spec_path: Path, output: Path, *, allow_risk: set[str] | None = None) -> dict[str, Any]:
    try:
        spec = CreateSpec.model_validate_json(_read_json_text(spec_path))
    except (OSError, ValidationError, ValueError) as exc:
        raise PptAgentError("INVALID_CREATE_SPEC", "创建规格不是有效 JSON 或不符合 Schema", "fix_spec", details={"validation": str(exc)[:1000]}) from exc
    source = canonical_path(output)
    candidate = candidate_path(source)
    with write_transaction(source) as store:
        if candidate.exists():
            raise PptAgentError("CANDIDATE_EXISTS", "候选版本已存在，请先 accept 或 discard", "review_candidate")
        temp = _temp_pptx(candidate)
        try:
            create_presentation(spec, temp)
            enforce_risk_policy(temp, allow_risk or set())
            verify = wps.finalize(temp)
            validate_pptx(temp)
            entry = {
                "status": "prepared",
                "action": "create",
                "new_revision": revision(temp),
                "temp": str(temp),
                "created_at": now_iso(),
            }
            commit_publish(
                store,
                entry,
                lambda: os.replace(temp, candidate),
                lambda: None,
                lambda: _unlink(candidate),
            )
        finally:
            _unlink(temp)
    return result("create", path=source, rev=revision(candidate), wps_version=verify.get("wps_version"), data={"candidate": str(candidate), "slide_count": len(spec.slides)})

def apply(
    path: Path,
    patch_path: Path | None,
    *,
    patch_text: str | None = None,
    wait: float = 0,
    restart: bool = False,
    allow_risk: set[str] | None = None,
) -> dict[str, Any]:
    source = canonical_path(source_path(path))
    if not source.exists() and not accepted_path(source).exists() and not candidate_path(source).exists():
        raise PptAgentError("FILE_NOT_FOUND", "源文件或已确认工作版不存在", "check_path")
    try:
        if patch_text is not None:
            raw_text = patch_text.lstrip("\ufeff")
        elif patch_path is not None:
            raw_text = _read_json_text(patch_path)
        else:
            raise ValueError("patch file or stdin text is required")
        raw_patch = json.loads(raw_text)
    except (OSError, ValidationError, ValueError) as exc:
        raise PptAgentError(
            "INVALID_PATCH",
            "Patch JSON 不符合 Schema",
            "fix_patch",
            details={
                "validation": str(exc)[:1200],
                "corrected_example": _corrected_patch_example(source, []),
                "document_unchanged": True,
            },
        ) from exc
    if isinstance(raw_patch, list):
        raise PptAgentError(
            "INVALID_PATCH",
            "operations 数组需要包装为完整 PatchRequest",
            "wrap_patch_request",
            details={
                "corrected_example": _corrected_patch_example(source, raw_patch),
                "document_unchanged": True,
            },
        )
    if isinstance(raw_patch, dict) and not raw_patch.get("request_id"):
        raw_patch["request_id"] = _generated_request_id(raw_patch)
    raw_operations = raw_patch.get("operations", []) if isinstance(raw_patch, dict) else []
    unknown = sorted({item.get("op") for item in raw_operations if isinstance(item, dict) and isinstance(item.get("op"), str)} - (STANDARD_OPS | WPS_OPS))
    if unknown:
        raise PptAgentError("UNSUPPORTED_OPERATION", "Patch 包含未支持操作", "query_operation_schema", details={"operations": unknown, "document_unchanged": True})
    _validate_animation_operations(raw_operations)
    try:
        request = PatchRequest.model_validate(raw_patch)
    except (ValidationError, ValueError) as exc:
        operations = raw_patch.get("operations", []) if isinstance(raw_patch, dict) else []
        raise PptAgentError(
            "INVALID_PATCH",
            "Patch JSON 不符合 Schema",
            "fix_patch",
            details={
                "validation": str(exc)[:1200],
                "corrected_example": _corrected_patch_example(source, operations),
                "document_unchanged": True,
            },
        ) from exc
    operation_dicts = [operation.model_dump(exclude_none=True, by_alias=True) for operation in request.operations]
    _validate_operations(operation_dicts)
    doc_id = document_id(source)
    if request.document_id != doc_id:
        raise PptAgentError("DOCUMENT_MISMATCH", "Patch 属于另一份文档", "reinspect", details={"document_unchanged": True})
    candidate = candidate_path(source)
    accepted = accepted_path(source)
    request_hash = hashlib.sha256(request.model_dump_json(exclude_none=True).encode()).hexdigest()
    assert request.request_id is not None

    with write_transaction(source, wait) as store:
        # 崩溃恢复可能回滚 candidate，必须在恢复后重新确定工作基线。
        base = candidate if candidate.exists() and not restart else accepted if accepted.exists() else source
        enforce_risk_policy(base, allow_risk or set())
        requests = store.requests()
        previous = requests.get(request.request_id)
        if previous:
            if previous["request_hash"] != request_hash:
                raise PptAgentError("REQUEST_ID_CONFLICT", "相同 request_id 对应了不同内容", "use_new_request_id")
            return previous["result"]
        current_revision = revision(base)
        if current_revision != request.revision:
            corrected_base = base
            if candidate.exists() and revision(candidate) == request.revision:
                corrected_base = candidate
            corrected_revision = revision(corrected_base)
            patch_input = str(patch_path) if patch_path is not None else "-"
            corrected_argv = ["apply", str(corrected_base), "--patch", patch_input]
            for risk_type in sorted(allow_risk or set()):
                corrected_argv.extend(["--allow-risk", risk_type])
            raise PptAgentError(
                "REVISION_CONFLICT",
                "文档已发生变化，请重新检查",
                "reinspect",
                True,
                {
                    "current_revision": current_revision,
                    "corrected_path": str(corrected_base),
                    "reinspect_argv": ["inspect", str(corrected_base), "--for", "edit"],
                    "corrected_argv": corrected_argv,
                    "patch_revision_matches_corrected_path": request.revision == corrected_revision,
                    "revision_update_required": None if request.revision == corrected_revision else corrected_revision,
                    "document_unchanged": True,
                },
            )
        plan = build_execution_plan(operation_dicts)
        temp = _temp_pptx(candidate)
        stale: list[Path] = []
        engine_infos: list[dict[str, Any]] = []
        wps_infos: list[dict[str, Any]] = []
        try:
            # Planner 生成的 ExecutionPlan：连续同类 operation 合并为一个 step，
            # 引擎与 WPS step 按声明顺序交替执行。
            shutil.copy2(base, temp)
            for step in plan.steps:
                if step.backend == "engine":
                    output = _temp_pptx(candidate)
                    stale.append(temp)
                    engine_infos.append(apply_operations(temp, list(step.operations), output))
                    temp = output
                else:
                    wps_infos.append(wps.apply_wps_operations(temp, list(step.operations)))
            engine_info = engine_infos[-1] if engine_infos else {"engine_output": ""}
            if plan.last_backend == "engine":
                # WPS 是事务的最终保存环境：批次以引擎操作结束时补一次 WPS 保存。
                wps_info = wps.finalize(temp)
            else:
                wps_info = wps_infos[-1]
            # 受限、可审计的 OOXML 后处理：WPS 保存会归一化切换属性
            # （丢 spd 与 dir/orient），这里只对目标页 slide XML 做外科式恢复，
            # 不重写整个包。恢复目标由 Planner 的 reducer 推出。
            restore_transition_options(temp, plan.transition_expectations)
            validate_pptx(temp)
            if plan.transition_expectations:
                # 最终字节必须经过 WPS 只读重开验证，且验证不得改变文件。
                hash_before = revision(temp)
                final_verify = wps.reopen_verify(temp)
                if revision(temp) != hash_before:
                    raise PptAgentError(
                        "WPS_REOPEN_MODIFIED_FILE",
                        "WPS 只读重开验证改变了文件",
                        "report_bug",
                    )
                wps_info = final_verify

            # 可恢复提交协议：prepared → 备份 → 发布 → committed → 幂等记录 → 清理。
            # 崩溃由下次 write_transaction 入口的 recover_transactions 恢复。
            new_revision = revision(temp)
            output = result("apply", path=source, rev=new_revision, wps_version=wps_info.get("wps_version"), data={
                "candidate": str(candidate),
                "operations_applied": len(operation_dicts),
                "format_impact": "preserved_or_explicit",
                **engine_info,
            })
            entry: dict[str, Any] = {
                "status": "prepared",
                "action": "apply",
                "request_id": request.request_id,
                "request_hash": request_hash,
                "base_revision": revision(candidate) if candidate.exists() else None,
                "new_revision": new_revision,
                "temp": str(temp),
                "backup": None,
                "result": output,
                "created_at": now_iso(),
            }
            backup: Path | None = None
            if candidate.exists():
                backup = candidate.with_name(f".{candidate.stem}.backup.pptx")
                backup_tmp = backup.with_name(f".{backup.name}.{os.getpid()}.tmp")
                shutil.copy2(candidate, backup_tmp)
                os.replace(backup_tmp, backup)
                entry["backup"] = str(backup)

            def publish() -> None:
                os.replace(temp, candidate)

            def record() -> None:
                requests[request.request_id] = {"request_hash": request_hash, "result": output, "created_at": now_iso()}
                store.save_requests(requests)

            def rollback() -> None:
                if backup is not None and backup.exists():
                    os.replace(backup, candidate)
                else:
                    _unlink(candidate)

            def cleanup() -> None:
                if backup is not None:
                    _unlink(backup)

            commit_publish(store, entry, publish, record, rollback, cleanup=cleanup)
            return output
        finally:
            _unlink(temp)
            for stale_path in stale:
                _unlink(stale_path)


def qa(path: Path, profile: str = "basic", *, suggest_fixes: bool = False) -> dict[str, Any]:
    path = canonical_path(path)
    validate_pptx(path)
    if profile not in {"basic", "presentation", "assignment"}:
        raise PptAgentError("INVALID_QA_PROFILE", "未知 QA profile", "use_capabilities")
    current_revision = revision(path)
    report = run_qa(path, profile, suggest_fixes=suggest_fixes)
    _ensure_stable_revision(path, current_revision)
    if suggest_fixes and report.get("suggested_patch"):
        report["suggested_patch"].update({
            "request_id": f"qa-{current_revision.split(':', 1)[1][:16]}",
            "document_id": document_id(source_path(path)),
            "revision": current_revision,
        })
        report["suggested_patch"] = {
            key: report["suggested_patch"][key]
            for key in ("request_id", "document_id", "revision", "operations")
        }
    return result("qa", path=path, rev=current_revision, data=report)


def render(path: Path, *, dpi: int = 96, pages: str | None = None, allow_risk: set[str] | None = None) -> dict[str, Any]:
    path = canonical_path(path)
    enforce_risk_policy(path, allow_risk or set())
    doc_id = document_id(source_path(path))
    store = StateStore(doc_id)
    current_revision = revision(path)
    render_id = current_revision.split(":", 1)[1][:16]
    target = store.render_dir / render_id
    target.mkdir(parents=True, exist_ok=True)
    pdf_path = target / f"{path.stem}.pdf"
    for stale_image in target.glob("slide-*.jpg"):
        stale_image.unlink()
    _unlink(pdf_path)
    export = wps.export_pdf(path, pdf_path)
    prefix = target / "slide"
    pdftoppm = _pdftoppm()
    if not pdftoppm:
        raise PptAgentError("PDFTOPPM_MISSING", "缺少 Poppler pdftoppm，无法生成页面图片", "run_doctor")
    command = [str(pdftoppm), "-jpeg", "-r", str(dpi)]
    if pages:
        selected = _parse_pages(pages)
        if len(selected) == 1:
            command.extend(["-f", str(selected[0] + 1), "-l", str(selected[0] + 1)])
        else:
            raise PptAgentError("UNSUPPORTED_PAGE_RANGE", "当前 render 一次只支持单页或整套", "render_one_page_or_all")
    command.extend([str(pdf_path), str(prefix)])
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    if completed.returncode != 0:
        raise PptAgentError("IMAGE_RENDER_FAILED", "PDF 转页面图片失败", "run_doctor", details={"stderr": completed.stderr[-1000:]})
    images = sorted(str(item) for item in target.glob("slide-*.jpg"))
    token = secrets.token_urlsafe(24)
    qa_result = run_qa(path, "basic")
    try:
        _ensure_stable_revision(path, current_revision)
    except PptAgentError:
        for image in target.glob("slide-*.jpg"):
            _unlink(image)
        _unlink(pdf_path)
        raise
    store.save_review({
        "candidate_revision": current_revision,
        "review_token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "created_at": now_iso(),
        "qa_error_count": qa_result["error_count"],
        "qa_issues": qa_result["issues"],
    })
    return result("render", path=path, rev=current_revision, wps_version=export.get("wps_version"), data={
        "pdf": str(pdf_path),
        "images": images,
        "candidate_revision": current_revision,
        "review_token": token,
        "qa": qa_result,
    })


def accept(candidate: Path, expected_revision: str, review_token: str, *, accept_qa_errors: bool = False) -> dict[str, Any]:
    candidate = canonical_path(candidate)
    source = source_path(candidate)
    if candidate != candidate_path(source):
        raise PptAgentError(
            "INVALID_CANDIDATE_PATH",
            "accept 仅接受 .agent.candidate.pptx 候选文件",
            "use_candidate_path",
            details={"document_unchanged": True},
        )
    doc_id = document_id(source)
    accepted = accepted_path(source)
    with write_transaction(source) as store:
        # 入口恢复可能回滚/还原 candidate：所有校验必须在恢复之后执行。
        if not candidate.exists():
            raise PptAgentError("FILE_NOT_FOUND", "候选版本不存在", "reinspect")
        validate_pptx(candidate)
        current = revision(candidate)
        if current != expected_revision:
            raise PptAgentError("REVISION_CONFLICT", "候选文件在预览后已变化", "render_again", True, {"current_revision": current})
        review = store.review()
        token_hash = hashlib.sha256(review_token.encode()).hexdigest()
        if not review or review.get("candidate_revision") != current or not hmac.compare_digest(review.get("review_token_hash", ""), token_hash):
            raise PptAgentError("REVIEW_TOKEN_INVALID", "预览令牌无效或已过期", "render_again")
        if review.get("qa_error_count", 0) and not accept_qa_errors:
            raise PptAgentError("QA_ERRORS_BLOCK_ACCEPT", "候选版本仍有 error 级 QA 问题", "fix_or_accept_explicitly", details={"issues": review.get("qa_issues", [])})
        temp = _temp_pptx(accepted)
        shutil.copy2(candidate, temp)
        backup: Path | None = None
        if accepted.exists():
            backup = accepted.with_name(f".{accepted.stem}.backup.pptx")
            backup_tmp = backup.with_name(f".{backup.name}.{os.getpid()}.tmp")
            shutil.copy2(accepted, backup_tmp)
            os.replace(backup_tmp, backup)
        candidate_backup = candidate.with_name(f".{candidate.stem}.moved.pptx")
        entry: dict[str, Any] = {
            "status": "prepared",
            "action": "accept",
            "new_revision": current,
            "temp": str(temp),
            "backup": str(backup) if backup else None,
            "candidate_backup": str(candidate_backup),
            "baseline": None,
            "created_at": now_iso(),
        }

        def publish() -> None:
            os.replace(candidate, candidate_backup)
            os.replace(temp, accepted)

        baseline_payload: dict[str, Any] = {}

        def refresh() -> None:
            baseline_payload.update({
                "schema_version": SCHEMA_VERSION,
                "document_id": doc_id,
                "source_path": str(source),
                "file_hash": current,
                "revision": current,
                "created_at": now_iso(),
                "snapshot": _compact_snapshot(accepted),
                "accepted_qa_issues": review.get("qa_issues", []) if accept_qa_errors else [],
            })
            entry["baseline"] = baseline_payload
            store.save_journal(entry)

        def rollback() -> None:
            if backup is not None and backup.exists():
                os.replace(backup, accepted)
            else:
                _unlink(accepted)
            if candidate_backup.exists():
                os.replace(candidate_backup, candidate)

        def cleanup() -> None:
            if backup is not None:
                _unlink(backup)
            _unlink(candidate_backup)

        commit_publish(store, entry, publish, lambda: store.save_baseline(baseline_payload), rollback, refresh, cleanup=cleanup)
    return result("accept", path=source, rev=current, data={"accepted": str(accepted), "original_unchanged": source.exists()})


def discard(path: Path) -> dict[str, Any]:
    source = source_path(canonical_path(path))
    candidate = candidate_path(source)
    with write_transaction(source) as store:
        if not candidate.exists():
            raise PptAgentError("CANDIDATE_NOT_FOUND", "没有可放弃的候选版本", "inspect")
        old_revision = revision(candidate)
        candidate_backup = candidate.with_name(f".{candidate.stem}.moved.pptx")
        entry = {
            "status": "prepared",
            "action": "discard",
            "candidate_backup": str(candidate_backup),
            "created_at": now_iso(),
        }
        commit_publish(
            store,
            entry,
            lambda: os.replace(candidate, candidate_backup),
            lambda: None,
            lambda: os.replace(candidate_backup, candidate) if candidate_backup.exists() else None,
            cleanup=lambda: _unlink(candidate_backup),
        )
    return result("discard", path=source, data={"discarded_revision": old_revision, "candidate_removed": True})


def cache_status() -> dict[str, Any]:
    root = state_root()
    files = [path for path in root.rglob("*") if path.is_file()] if root.exists() else []
    return result("cache", data={"state_dir": str(root), "file_count": len(files), "bytes": sum(path.stat().st_size for path in files)})


def cache_clean(older_than_days: int = 7) -> dict[str, Any]:
    render_root = state_root() / "renders"
    removed = 0
    cutoff = time.time() - older_than_days * 86400
    if render_root.exists():
        for path in sorted(render_root.rglob("*"), reverse=True):
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(); removed += 1
            elif path.is_dir():
                try: path.rmdir()
                except OSError: pass
    return result("cache", data={"removed_files": removed, "older_than_days": older_than_days})


def template(action: str, path: Path, manifest: Path | None = None, output: Path | None = None) -> dict[str, Any]:
    path = canonical_path(path)
    validate_pptx(path)
    data = inspect_json(path)
    placeholders = []
    for slide_index, shapes in data.get("slides", {}).items():
        for shape_id, shape in shapes.items():
            if isinstance(shape, dict) and (shape.get("placeholder") or str(shape.get("name", "")).lower().startswith("placeholder")):
                placeholders.append({"slide": int(slide_index), "object": f"s{slide_index}:{shape_id}", "role": "unresolved"})
    if action == "inspect":
        return result("template", path=path, data={"action": action, "placeholders": placeholders})
    if not manifest:
        raise PptAgentError("MANIFEST_REQUIRED", "模板验证与规范化需要 manifest", "provide_manifest")
    try:
        mapping = json.loads(_read_json_text(manifest))
    except (OSError, json.JSONDecodeError) as exc:
        raise PptAgentError("INVALID_MANIFEST", "模板 manifest 不是有效 JSON", "fix_manifest") from exc
    unresolved = [entry for entry in mapping.get("placeholders", []) if entry.get("role") == "unresolved"]
    if action == "validate":
        return result("template", path=path, data={"action": action, "valid": not unresolved, "unresolved": unresolved})
    if action != "normalize" or not output:
        raise PptAgentError("INVALID_TEMPLATE_ACTION", "未知模板操作或缺少输出路径", "use_capabilities")
    output = canonical_path(output)
    shutil.copy2(path, output)
    sidecar = output.with_suffix(".template.json")
    sidecar.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    return result("template", path=output, data={"action": action, "normalized": str(output), "manifest": str(sidecar)})


INSPECT_FIELD_GROUPS = {
    "type": {"type"},
    "name": {"name"},
    "text": {"paragraphs", "rows", "_notes"},
    "geometry": {"pos", "size", "rotation"},
    "style": {"fill", "gradient", "line", "line_color", "line_width", "line_dash", "anchor", "insets", "adjustments", "shadow", "alt_text"},
    "image": {"rid", "media", "alt_text", "crop"},
    "table": {"rows", "col_widths", "first_row", "banding"},
    "animation": {"animations", "_animations", "_transition"},
}
INSPECT_PURPOSE_FIELDS = {
    "text-edit": {"type", "name", "text", "table"},
    "content": {"type", "name", "text", "table"},
    "edit": {"type", "name", "text", "geometry"},
    "layout": {"type", "name", "text", "geometry"},
    "animation": {"type", "name", "text", "animation"},
}

INSPECT_IDENTITY_ALIASES = {
    "identity", "slide", "slide_id", "slide_index", "slide_no", "slide.number", "slides.index",
    "id", "object_id", "shape_id", "slides.shapes.id", "slides.shapes.object_id",
}
INSPECT_FIELD_ALIASES = {
    "x": "geometry", "y": "geometry", "left": "geometry", "top": "geometry",
    "w": "geometry", "h": "geometry", "width": "geometry", "height": "geometry",
    "pos": "geometry", "size": "geometry", "rotation": "geometry", "slide_size": "geometry",
    "shape_name": "name", "kind": "type", "shape_type": "type", "slide.title": "text",
    "animations": "animation", "paragraph_index": "animation",
    "effect": "animation", "effects": "animation", "trigger": "animation",
    "paragraphs": "animation", "duration": "animation", "delay": "animation",
    "transition": "animation", "animation.effect": "animation",
    "animation.trigger": "animation", "animation.paragraphs": "animation",
}
INSPECT_OBJECT_PREFIXES = ("shape.", "slides.shapes.")
INSPECT_COMPACT_OBJECT_FIELDS = {"type", "name", "text", "geometry"}


def _resolve_inspect_field(field: str) -> set[str] | None:
    normalized = field.strip().lower()
    if normalized in INSPECT_FIELD_GROUPS:
        return {normalized}
    if normalized in INSPECT_IDENTITY_ALIASES:
        return set()
    if normalized in {"shape.*", "slides.shapes.*"}:
        return set(INSPECT_COMPACT_OBJECT_FIELDS)
    alias = INSPECT_FIELD_ALIASES.get(normalized)
    if alias:
        return {alias}
    for prefix in INSPECT_OBJECT_PREFIXES:
        if not normalized.startswith(prefix):
            continue
        suffix = normalized[len(prefix):]
        if suffix in {"id", "object_id"}:
            return set()
        if suffix == "name":
            return {"name"}
        if suffix in {"type", "kind"}:
            return {"type"}
        if suffix in {"text", "runs.text"}:
            return {"text"}
        if suffix in {"runs.font_size", "font_size"}:
            return {"style"}
        alias = INSPECT_FIELD_ALIASES.get(suffix)
        return {alias} if alias else None
    return None


def _project_inspection(data: dict[str, Any], *, purpose: str | None, fields: list[str] | None) -> dict[str, Any]:
    requested = {"identity"}
    unknown: list[str] = []
    ignored: list[str] = []
    for field in fields or []:
        resolved = _resolve_inspect_field(field)
        if resolved is not None:
            requested.update(resolved)
        elif purpose and field.lower().startswith(INSPECT_OBJECT_PREFIXES):
            ignored.append(field)
        else:
            unknown.append(field)
    if purpose:
        if purpose not in INSPECT_PURPOSE_FIELDS:
            raise PptAgentError("INVALID_INSPECT_PURPOSE", "未知 inspect 任务类型", "use_capabilities")
        requested.update(INSPECT_PURPOSE_FIELDS[purpose])
    if unknown:
        example_fields = sorted(INSPECT_PURPOSE_FIELDS.get(purpose or "", INSPECT_FIELD_GROUPS))
        candidates = sorted(set(INSPECT_FIELD_GROUPS) | INSPECT_IDENTITY_ALIASES | set(INSPECT_FIELD_ALIASES))
        raise PptAgentError(
            "INVALID_INSPECT_FIELDS",
            "inspect --fields 包含未知字段组",
            "use_capabilities",
            details={
                "unknown": sorted(unknown),
                "allowed": sorted(set(INSPECT_FIELD_GROUPS) | {"identity"}),
                "nearest": {field: get_close_matches(field, candidates, n=3, cutoff=0.55) for field in sorted(unknown)},
                "corrected_example": {
                    "command": f"ppt-agent inspect FILE{f' --for {purpose}' if purpose else ''} --fields {','.join(example_fields)}",
                    "fields": example_fields,
                },
            },
        )
    selected_keys = set().union(*(INSPECT_FIELD_GROUPS[name] for name in requested if name != "identity"))
    slides: dict[str, Any] = {}
    for slide_index, shapes in data.get("slides", {}).items():
        projected: dict[str, Any] = {}
        for shape_id, shape in shapes.items():
            if shape_id.startswith("_"):
                if shape_id in selected_keys:
                    projected[shape_id] = shape
                continue
            if not isinstance(shape, dict):
                continue
            projected[shape_id] = {
                "identity": {
                    "slide_index": int(slide_index),
                    "shape_id": shape_id,
                    "object_id": f"s{slide_index}:{shape_id}",
                },
                **{key: value for key, value in shape.items() if key in selected_keys},
            }
        slides[str(slide_index)] = projected
    return {
        "slide_count": data.get("slide_count"),
        "slide_size": data.get("slide_size"),
        "purpose": purpose,
        "fields": sorted(requested),
        **({"ignored_fields": sorted(ignored)} if ignored else {}),
        "slides": slides,
    }


def _validate_operations(operations: list[dict[str, Any]]) -> None:
    supported = STANDARD_OPS | WPS_OPS
    unknown = sorted({operation["op"] for operation in operations} - supported)
    if unknown:
        raise PptAgentError("UNSUPPORTED_OPERATION", "Patch 包含未支持操作", "use_capabilities", details={"operations": unknown, "document_unchanged": True})
    for operation in operations:
        if "selector" in operation or "text_match" in operation:
            raise PptAgentError("SELECTOR_NOT_IMPLEMENTED", "MVP 当前仅接受精确对象 ID", "reinspect", details={"document_unchanged": True})


def _validate_animation_operations(operations: list[Any]) -> None:
    by_object: dict[str, list[dict[str, Any]]] = {}
    for operation in operations:
        if not isinstance(operation, dict) or operation.get("op") != "add_animation":
            continue
        object_id = operation.get("object")
        if isinstance(object_id, str):
            by_object.setdefault(object_id, []).append(operation)
    for object_id, animations in by_object.items():
        has_all = [item for item in animations if item.get("paragraphs") == "all"]
        has_legacy = [item for item in animations if "paragraph" in item]
        has_whole = [item for item in animations if "paragraphs" not in item and "paragraph" not in item]
        signatures = [
            (
                item.get("effect", "fade"),
                item.get("trigger", "on_click"),
                item.get("paragraphs"),
                item.get("paragraph"),
                item.get("duration"),
                item.get("delay"),
            )
            for item in animations
        ]
        if (
            len(has_all) > 1
            or (has_legacy and has_all)
            or (has_all and has_whole)
            or len(set(signatures)) != len(signatures)
            or any("paragraph" in item and "paragraphs" in item for item in animations)
        ):
            raise PptAgentError(
                "DUPLICATE_ANIMATION",
                "同一对象包含重复或冲突的整体/逐段进入动画",
                "fix_patch",
                details={"object": object_id, "document_unchanged": True},
            )


def _compact_snapshot(path: Path) -> dict[str, Any]:
    data = inspect_json(path)
    slides = {}
    for slide_index, shapes in data.get("slides", {}).items():
        slides[slide_index] = {
            shape_id: {
                "type": shape.get("type"),
                "pos": shape.get("pos"),
                "size": shape.get("size"),
                "text_hash": hashlib.sha256("\n".join(p.get("text", "") for p in shape.get("paragraphs", [])).encode()).hexdigest()[:16],
            }
            for shape_id, shape in shapes.items()
            if not shape_id.startswith("_") and isinstance(shape, dict)
        }
    return {"slide_count": data.get("slide_count"), "slides": slides}


def _temp_pptx(target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".pptx", dir=target.parent)
    os.close(descriptor)
    path = Path(name)
    path.unlink()
    return path


def _unlink(path: Path) -> None:
    try: path.unlink()
    except FileNotFoundError: pass


def _parse_pages(value: str) -> list[int]:
    try:
        pages = sorted({int(item.strip()) for item in value.split(",")})
    except ValueError as exc:
        raise PptAgentError("INVALID_PAGE", "页码必须是从 0 开始的整数", "fix_page") from exc
    if not pages or pages[0] < 0:
        raise PptAgentError("INVALID_PAGE", "页码必须是从 0 开始的整数", "fix_page")
    return pages


def _pdftoppm() -> Path | None:
    override = os.environ.get("PPT_AGENT_PDFTOPPM")
    if override and Path(override).is_file():
        return Path(override)
    found = shutil.which("pdftoppm.exe") or shutil.which("pdftoppm")
    if found:
        path = Path(found)
        if path.suffix.lower() == ".exe":
            return path
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        bundled = Path(user_profile) / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "native" / "poppler" / "Library" / "bin" / "pdftoppm.exe"
        if bundled.is_file():
            return bundled
    return None

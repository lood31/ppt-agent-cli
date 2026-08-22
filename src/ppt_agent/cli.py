from __future__ import annotations

import argparse
import json
import sys
from difflib import get_close_matches
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from . import __version__
from .errors import PptAgentError
from .models import CreateSpec, OPERATION_GUIDE, OPERATION_MODELS, OPERATION_USE_WHEN, PatchRequest, SCHEMA_VERSION
from . import service


class AgentArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise PptAgentError(
            "INVALID_ARGUMENT",
            "命令参数无效",
            "use_corrected_usage",
            details={"argument_error": message, "usage": self.format_usage().strip()},
        )


def _parser() -> argparse.ArgumentParser:
    parser = AgentArgumentParser(prog="ppt-agent", description="WPS-first PPTX adapter for AI agents")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor")
    sub.add_parser("capabilities")

    inspect = sub.add_parser("inspect")
    inspect.add_argument("file", type=Path)
    inspect.add_argument("--slide", type=int)
    inspect.add_argument("--for", dest="purpose", choices=["text-edit", "content", "edit", "layout", "animation"])
    inspect.add_argument("--fields", help="逗号分隔：type,name,text,geometry,style,image,table,animation")
    inspect.add_argument("--verbose", action="store_true")
    inspect.add_argument("--no-state", action="store_true")
    _risk_args(inspect)

    diff = sub.add_parser("diff")
    diff.add_argument("file", type=Path)
    diff.add_argument("other", type=Path, nargs="?")

    create = sub.add_parser("create")
    create.add_argument("spec", type=Path)
    create.add_argument("--output", "-o", required=True, type=Path)
    _risk_args(create)

    apply = sub.add_parser("apply")
    apply.add_argument("file", type=Path)
    apply.add_argument("patch", nargs="?")
    apply.add_argument("--patch", dest="patch_option")
    apply.add_argument("--wait", type=float, default=0)
    apply.add_argument("--restart-from-baseline", action="store_true")
    _risk_args(apply)

    render = sub.add_parser("render")
    render.add_argument("file", type=Path)
    render.add_argument("--dpi", type=int, default=96)
    render.add_argument("--pages")
    _risk_args(render)

    qa = sub.add_parser("qa")
    qa.add_argument("file", type=Path)
    qa.add_argument("--profile", choices=["basic", "presentation", "assignment"], default="basic")
    qa.add_argument("--suggest-fixes", action="store_true", help="返回可直接传给 apply 的确定性修复 patch，不修改文件")

    template = sub.add_parser("template")
    template.add_argument("action", choices=["inspect", "validate", "normalize"])
    template.add_argument("file", type=Path)
    template.add_argument("--manifest", type=Path)
    template.add_argument("--output", "-o", type=Path)

    cache = sub.add_parser("cache")
    cache.add_argument("action", choices=["status", "clean"])
    cache.add_argument("--older-than-days", type=int, default=7)

    accept = sub.add_parser("accept")
    accept.add_argument("candidate", type=Path)
    accept.add_argument("--revision", required=True)
    accept.add_argument("--review-token", required=True)
    accept.add_argument("--accept-qa-errors", action="store_true")

    discard = sub.add_parser("discard")
    discard.add_argument("file", type=Path)

    schema = sub.add_parser("schema")
    schema.add_argument("target", choices=["create", "apply"])
    schema.add_argument("--op", help="只返回一种 apply 操作的紧凑 Schema；query/list 返回操作目录")
    schema.add_argument("--full", action="store_true", help="显式返回完整联合 Schema；默认 apply 只返回紧凑操作目录")
    return parser


def _risk_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allow-risk", action="append", default=[], choices=["macro", "activex", "ole", "external_relationship", "remote_media"])


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    match args.command:
        case "doctor": return service.doctor()
        case "capabilities": return service.capabilities()
        case "inspect":
            fields = [item.strip() for item in args.fields.split(",") if item.strip()] if args.fields else None
            return service.inspect(
                args.file,
                slide=args.slide,
                purpose=args.purpose,
                fields=fields,
                verbose=args.verbose,
                no_state=args.no_state,
                allow_risk=set(args.allow_risk),
            )
        case "diff": return service.diff(args.file, args.other)
        case "create": return service.create(args.spec, args.output, allow_risk=set(args.allow_risk))
        case "apply":
            if args.patch and args.patch_option:
                raise PptAgentError("INVALID_PATCH_ARGUMENT", "只能指定一个 patch 输入", "use_patch_file_or_stdin", details={"corrected_usage": _patch_usage(args.file)})
            patch_arg = args.patch_option or args.patch
            if not patch_arg:
                raise PptAgentError("INVALID_PATCH_ARGUMENT", "缺少 PatchRequest 输入", "use_patch_file_or_stdin", details={"corrected_usage": _patch_usage(args.file)})
            if patch_arg.lstrip().startswith(("{", "[")):
                raise PptAgentError("INVALID_PATCH_ARGUMENT", "内联 JSON 不会被当作文件路径；请使用 patch 文件或标准输入", "use_patch_file_or_stdin", details={"corrected_usage": _patch_usage(args.file), "document_unchanged": True})
            patch_text = sys.stdin.read() if patch_arg == "-" else None
            patch_path = None if patch_arg == "-" else Path(patch_arg)
            return service.apply(args.file, patch_path, patch_text=patch_text, wait=args.wait, restart=args.restart_from_baseline, allow_risk=set(args.allow_risk))
        case "render": return service.render(args.file, dpi=args.dpi, pages=args.pages, allow_risk=set(args.allow_risk))
        case "qa": return service.qa(args.file, args.profile, suggest_fixes=args.suggest_fixes)
        case "template": return service.template(args.action, args.file, args.manifest, args.output)
        case "cache": return service.cache_status() if args.action == "status" else service.cache_clean(args.older_than_days)
        case "accept": return service.accept(args.candidate, args.revision, args.review_token, accept_qa_errors=args.accept_qa_errors)
        case "discard": return service.discard(args.file)
        case "schema":
            if args.op and args.target != "apply":
                raise PptAgentError("INVALID_SCHEMA_TARGET", "--op 只适用于 schema apply", "remove_op")
            if args.op:
                operation = args.op.strip().lower()
                if operation in {"query", "list", "catalog", "查询", "列表"}:
                    payload = _operation_catalog()
                    payload["data"]["interpreted_as"] = "operation_catalog"
                    return payload
                if operation not in OPERATION_MODELS:
                    raise PptAgentError(
                        "UNKNOWN_OPERATION",
                        "未知 apply 操作",
                        "choose_operation",
                        details={
                            "operation": args.op,
                            "nearest": get_close_matches(operation, OPERATION_MODELS, n=3, cutoff=0.35),
                            "allowed": sorted(OPERATION_MODELS),
                            "corrected_usage": "ppt-agent schema apply --op <operation>",
                        },
                    )
                guide = OPERATION_GUIDE[operation]
                return service.result("schema", data={
                    "target": "apply",
                    "op": operation,
                    "schema": OPERATION_MODELS[operation].model_json_schema(),
                    "example": guide["example"],
                    "common_errors": guide["errors"],
                    "units": "geometry=inches; font_size/line_width=points; slide=0-based",
                    "wps": guide["wps"],
                })
            if args.target == "apply" and not args.full:
                return _operation_catalog()
            schema = CreateSpec.model_json_schema() if args.target == "create" else PatchRequest.model_json_schema()
            return service.result("schema", data={"target": args.target, "schema": schema, "query_one_op": "ppt-agent schema apply --op <name>"})
        case _: raise PptAgentError("UNKNOWN_COMMAND", "未知命令", "use_help")


def _patch_usage(file: Path) -> list[str]:
    return [
        f"ppt-agent apply {file} patch.json",
        f"ppt-agent apply {file} --patch patch.json",
        f"Get-Content patch.json -Raw | ppt-agent apply {file} -",
    ]


def _operation_catalog() -> dict[str, Any]:
    operations = [
        {"op": op, "use_when": OPERATION_USE_WHEN[op], "wps": OPERATION_GUIDE[op]["wps"]}
        for op in OPERATION_MODELS
    ]
    return service.result("schema", data={
        "target": "apply",
        "operations": operations,
        "next_action": "ppt-agent schema apply --op <name>",
        "full_schema": "ppt-agent schema apply --full",
    })


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = _parser()
    pretty = bool(argv and "--pretty" in argv) or "--pretty" in sys.argv[1:]
    try:
        args = parser.parse_args(argv)
        pretty = args.pretty
        payload = _dispatch(args)
        exit_code = 0 if payload.get("ok") else 1
    except PptAgentError as exc:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "error_code": exc.code,
            "message_zh": exc.message_zh,
            "retryable": exc.retryable,
            "next_action": exc.next_action,
            "engine_version": service.ENGINE_VERSION,
            **(exc.details or {}),
        }
        exit_code = 1
    except ValidationError as exc:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "error_code": "VALIDATION_ERROR",
            "message_zh": "输入未通过 Schema 校验",
            "retryable": False,
            "next_action": "fix_input",
            "details": exc.errors(include_url=False),
        }
        exit_code = 1
    except Exception as exc:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "error_code": "INTERNAL_ERROR",
            "message_zh": "发生未预期错误",
            "retryable": False,
            "next_action": "report_bug",
            "details": {"type": type(exc).__name__, "message": str(exc)[:1000]},
        }
        exit_code = 1
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None, separators=None if pretty else (",", ":")))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()

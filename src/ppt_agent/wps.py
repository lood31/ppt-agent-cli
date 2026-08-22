from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Any, Iterator

from .errors import PptAgentError


EFFECTS = {"appear": 1, "fly_in": 2, "fade": 10}
TRIGGERS = {"on_click": 1, "with_previous": 2, "after_previous": 3}
TRANSITIONS = {"none": 0, "fade": 3849, "push": 3850, "wipe": 3852}


def _client():
    if os.name != "nt":
        raise PptAgentError("WPS_UNAVAILABLE", "WPS COM 仅支持 Windows", "run_on_windows")
    try:
        import win32com.client  # type: ignore[import-untyped]
    except ImportError as exc:
        raise PptAgentError("PYWIN32_MISSING", "缺少 pywin32，无法调用 WPS COM", "install_dependencies") from exc
    return win32com.client


@contextlib.contextmanager
def wps_application() -> Iterator[Any]:
    client = _client()
    app = None
    try:
        app = client.DispatchEx("KWPP.Application")
        with contextlib.suppress(Exception):
            app.Visible = False
        with contextlib.suppress(Exception):
            app.DisplayAlerts = 0
        yield app
    except PptAgentError:
        raise
    except Exception as exc:
        raise PptAgentError(
            "WPS_COM_FAILED",
            "无法启动独立 WPS 演示 COM 实例",
            "run_doctor",
            retryable=True,
            details={"com_error": str(exc)[:500]},
        ) from exc
    finally:
        if app is not None:
            with contextlib.suppress(Exception):
                app.Quit()


def version() -> str | None:
    return probe()["version"]


def probe() -> dict[str, Any]:
    try:
        with wps_application() as app:
            return {"available": True, "version": str(app.Version), "error": None}
    except PptAgentError as exc:
        return {
            "available": False,
            "version": None,
            "error": {
                "error_code": exc.code,
                "message_zh": exc.message_zh,
                "next_action": exc.next_action,
                **(exc.details or {}),
            },
        }


def _open(app: Any, path: Path, read_only: bool = False) -> Any:
    try:
        return app.Presentations.Open(str(path.resolve()), read_only, False, False)
    except Exception as exc:
        raise PptAgentError(
            "WPS_OPEN_FAILED",
            "WPS 无法无交互打开演示文稿",
            "close_dialogs_and_retry",
            retryable=True,
            details={"com_error": str(exc)[:500]},
        ) from exc


def reopen_verify(path: Path) -> dict[str, Any]:
    with wps_application() as app:
        presentation = None
        try:
            presentation = _open(app, path, read_only=True)
            return {
                "slide_count": int(presentation.Slides.Count),
                "wps_version": str(app.Version),
            }
        finally:
            if presentation is not None:
                presentation.Close()
                presentation = None


def finalize(path: Path) -> dict[str, Any]:
    """Make WPS the final writer, then reopen the result read-only."""
    with wps_application() as app:
        presentation = None
        try:
            presentation = _open(app, path)
            presentation.Save()
        finally:
            if presentation is not None:
                presentation.Close()
                presentation = None
    return reopen_verify(path)


def apply_wps_operations(path: Path, operations: list[dict[str, Any]]) -> dict[str, Any]:
    if not operations:
        return {"applied": 0, "wps_version": version()}
    with wps_application() as app:
        presentation = None
        slide = None
        shape = None
        effect = None
        applied = 0
        try:
            presentation = _open(app, path)
            for operation in operations:
                op = operation["op"]
                slide_index, shape_id = parse_object(operation)
                slide = presentation.Slides(slide_index + 1)
                if op == "add_animation":
                    if shape_id is None:
                        raise PptAgentError("INVALID_OBJECT_ID", "动画操作缺少对象 ID", "reinspect")
                    shape = shape_by_id(slide, shape_id)
                    effect_name = operation.get("effect", "fade")
                    trigger_name = operation.get("trigger", "on_click")
                    if effect_name not in EFFECTS or trigger_name not in TRIGGERS:
                        raise PptAgentError("UNSUPPORTED_OPERATION", "不支持的动画参数", "use_capabilities")
                    paragraph_level = 1 if operation.get("paragraphs") == "all" else 0
                    effect = slide.TimeLine.MainSequence.AddEffect(
                        shape,
                        EFFECTS[effect_name],
                        paragraph_level,
                        TRIGGERS[trigger_name],
                    )
                    if operation.get("duration") is not None:
                        effect.Timing.Duration = float(operation["duration"])
                    if operation.get("delay") is not None:
                        effect.Timing.TriggerDelayTime = float(operation["delay"])
                elif op == "set_transition":
                    transition = operation.get("transition", "fade")
                    if transition not in TRANSITIONS:
                        raise PptAgentError("UNSUPPORTED_OPERATION", "不支持的切换效果", "use_capabilities")
                    slide.SlideShowTransition.EntryEffect = TRANSITIONS[transition]
                elif op == "set_chart_title":
                    if shape_id is None:
                        raise PptAgentError("INVALID_OBJECT_ID", "图表操作缺少对象 ID", "reinspect")
                    shape = shape_by_id(slide, shape_id)
                    if not bool(shape.HasChart):
                        raise PptAgentError("OBJECT_TYPE_MISMATCH", "目标对象不是原生图表", "reinspect")
                    shape.Chart.HasTitle = True
                    shape.Chart.ChartTitle.Text = str(operation.get("title", ""))
                else:
                    raise PptAgentError(
                        "UNSUPPORTED_OPERATION",
                        f"WPS 层不支持操作：{op}",
                        "use_capabilities",
                        details={"document_unchanged": True},
                    )
                applied += 1
            presentation.Save()
        finally:
            if presentation is not None:
                presentation.Close()
            effect = None
            shape = None
            slide = None
            presentation = None
    result = reopen_verify(path)
    result["applied"] = applied
    return result


def export_pdf(path: Path, pdf_path: Path) -> dict[str, Any]:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with wps_application() as app:
        presentation = None
        try:
            presentation = _open(app, path, read_only=True)
            try:
                presentation.ExportAsFixedFormat(str(pdf_path.resolve()), 2)
            except Exception:
                presentation.SaveAs(str(pdf_path.resolve()), 32)
        finally:
            if presentation is not None:
                presentation.Close()
                presentation = None
        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
            raise PptAgentError("WPS_EXPORT_FAILED", "WPS 未生成有效 PDF", "retry", True)
        return {"pdf": str(pdf_path), "wps_version": str(app.Version)}


def parse_object(operation: dict[str, Any]) -> tuple[int, int | None]:
    value = operation.get("object")
    if value:
        import re

        match = re.fullmatch(r"s(\d+):(s|o)(\d+)", str(value))
        if not match:
            raise PptAgentError("INVALID_OBJECT_ID", "对象 ID 必须形如 s3:s5", "reinspect")
        return int(match.group(1)), int(match.group(3))
    slide = int(operation.get("slide", 0))
    shape = operation.get("shape")
    if shape is None:
        return slide, None
    return slide, int(str(shape).lstrip("so"))


def shape_by_id(slide: Any, shape_id: int) -> Any:
    for shape in slide.Shapes:
        if int(shape.Id) == shape_id:
            return shape
    raise PptAgentError("OBJECT_NOT_FOUND", "WPS 中找不到目标对象", "reinspect")

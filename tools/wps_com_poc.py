from __future__ import annotations

import contextlib
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import win32com.client  # type: ignore[import-untyped]


def run(source: Path, output_dir: Path, animation_shape_id: int) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    working = output_dir / "wps-com-output.pptx"
    pdf = output_dir / "wps-com-output.pdf"
    shutil.copy2(source, working)
    result: dict[str, Any] = {
        "source_sha256": sha256(source),
        "output": str(working.resolve()),
        "pdf": str(pdf.resolve()),
        "checks": {},
    }
    app = None
    presentation = None
    try:
        app = win32com.client.DispatchEx("KWPP.Application")
        result["wps_version"] = str(app.Version)
        with contextlib.suppress(Exception): app.Visible = False
        with contextlib.suppress(Exception): app.DisplayAlerts = 0
        presentation = app.Presentations.Open(str(working.resolve()), False, False, False)
        result["checks"]["slide_count"] = int(presentation.Slides.Count)
        slide = presentation.Slides(1)
        result["checks"]["shape_count"] = int(slide.Shapes.Count)
        target = next(shape for shape in slide.Shapes if int(shape.Id) == animation_shape_id)
        target.TextFrame.TextRange.Text = "动画已由 WPS COM 写入"
        effect = slide.TimeLine.MainSequence.AddEffect(target, 10, 0, 1)
        effect.Timing.Duration = 0.75
        slide.SlideShowTransition.EntryEffect = 3849
        chart_shape = next(shape for shape in presentation.Slides(2).Shapes if bool(shape.HasChart))
        chart_shape.Chart.HasTitle = True
        chart_shape.Chart.ChartTitle.Text = "WPS COM 已验证"
        presentation.Save()
        try:
            presentation.ExportAsFixedFormat(str(pdf.resolve()), 2)
        except Exception:
            presentation.SaveAs(str(pdf.resolve()), 32)
        presentation.Close(); presentation = None
        reopened = app.Presentations.Open(str(working.resolve()), True, False, False)
        try:
            sequence = reopened.Slides(1).TimeLine.MainSequence
            result["checks"]["animation_count_after_reopen"] = int(sequence.Count)
            result["checks"]["animation_effect_type"] = int(sequence(1).EffectType) if sequence.Count else None
            result["checks"]["transition_after_reopen"] = int(reopened.Slides(1).SlideShowTransition.EntryEffect)
            chart = next(shape for shape in reopened.Slides(2).Shapes if bool(shape.HasChart)).Chart
            result["checks"]["chart_title_after_reopen"] = str(chart.ChartTitle.Text)
            result["checks"]["reopen_slide_count"] = int(reopened.Slides.Count)
        finally:
            reopened.Close()
        result["checks"]["pdf_exists"] = pdf.exists() and pdf.stat().st_size > 0
        result["output_sha256"] = sha256(working)
        result["passed"] = bool(
            result["checks"].get("animation_count_after_reopen", 0) >= 1
            and result["checks"]["pdf_exists"]
            and result["checks"].get("chart_title_after_reopen") == "WPS COM 已验证"
        )
        return result
    finally:
        if presentation is not None:
            with contextlib.suppress(Exception): presentation.Close()
        if app is not None:
            with contextlib.suppress(Exception): app.Quit()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: wps_com_poc.py SOURCE.pptx OUTPUT_DIR ANIMATION_SHAPE_ID")
    print(json.dumps(run(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])), ensure_ascii=False, indent=2))

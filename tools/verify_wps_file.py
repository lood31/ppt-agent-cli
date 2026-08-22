from __future__ import annotations

import contextlib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import win32com.client  # type: ignore[import-untyped]


PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _paragraph_ranges(path: Path) -> list[dict[str, int]]:
    ranges: list[dict[str, int]] = []
    with zipfile.ZipFile(path) as package:
        slide_names = sorted(
            (name for name in package.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")),
            key=lambda name: int(Path(name).stem.removeprefix("slide")),
        )
        for slide_index, name in enumerate(slide_names):
            root = ElementTree.fromstring(package.read(name))
            for target in root.findall(f".//{{{PRESENTATION_NS}}}spTgt"):
                paragraph_range = target.find(f"./{{{PRESENTATION_NS}}}txEl/{{{PRESENTATION_NS}}}pRg")
                if paragraph_range is not None:
                    ranges.append({
                        "slide": slide_index,
                        "shape_id": int(target.attrib["spid"]),
                        "start": int(paragraph_range.attrib["st"]),
                        "end": int(paragraph_range.attrib["end"]),
                    })
    return ranges


def verify(path: Path) -> dict[str, object]:
    app = win32com.client.DispatchEx("KWPP.Application")
    presentation = None
    try:
        with contextlib.suppress(Exception): app.Visible = False
        with contextlib.suppress(Exception): app.DisplayAlerts = 0
        presentation = app.Presentations.Open(str(path.resolve()), True, False, False)
        animation_counts = [int(presentation.Slides(index).TimeLine.MainSequence.Count) for index in range(1, presentation.Slides.Count + 1)]
        animations = []
        for slide_index in range(1, presentation.Slides.Count + 1):
            sequence = presentation.Slides(slide_index).TimeLine.MainSequence
            for effect_index in range(1, sequence.Count + 1):
                effect = sequence(effect_index)
                paragraph_level = None
                with contextlib.suppress(Exception):
                    paragraph_level = int(effect.Paragraph)
                animations.append({
                    "slide": slide_index - 1,
                    "index": effect_index - 1,
                    "effect_type": int(effect.EffectType),
                    "paragraph_level": paragraph_level,
                    "trigger": int(effect.Timing.TriggerType),
                })
        chart_titles: list[str] = []
        for slide in presentation.Slides:
            for shape in slide.Shapes:
                if bool(shape.HasChart) and bool(shape.Chart.HasTitle):
                    chart_titles.append(str(shape.Chart.ChartTitle.Text))
        return {
            "file": str(path.resolve()),
            "wps_version": str(app.Version),
            "slide_count": int(presentation.Slides.Count),
            "animation_counts": animation_counts,
            "animations": animations,
            "paragraph_ranges": _paragraph_ranges(path.resolve()),
            "chart_titles": chart_titles,
        }
    finally:
        if presentation is not None:
            with contextlib.suppress(Exception): presentation.Close()
        with contextlib.suppress(Exception): app.Quit()


if __name__ == "__main__":
    print(json.dumps(verify(Path(sys.argv[1])), ensure_ascii=False, indent=2))

from __future__ import annotations

import sys
from pathlib import Path

import win32com.client


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: simulate-human-edit.py INPUT.pptx OUTPUT.pptx")
    source = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    output.write_bytes(source.read_bytes())
    app = win32com.client.DispatchEx("KWPP.Application")
    presentation = None
    try:
        try:
            app.Visible = False
        except Exception:
            pass
        try:
            app.DisplayAlerts = 0
        except Exception:
            pass
        presentation = app.Presentations.Open(str(output), False, False, False)
        slide = presentation.Slides(1)
        shape = next(item for item in slide.Shapes if int(item.Id) == 2)
        shape.TextFrame.TextRange.Text = "人工调整后的验收标题"
        shape.Left = float(shape.Left) + 18.0  # COM coordinates are points; 18 pt = 0.25 inch
        presentation.Save()
    finally:
        if presentation is not None:
            presentation.Close()
        app.Quit()


if __name__ == "__main__":
    main()

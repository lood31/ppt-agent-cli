from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation

from ppt_agent import service
from ppt_agent.paths import candidate_path


def test_create_generates_candidate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PPT_AGENT_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(service.wps, "finalize", lambda path: {"wps_version": "test", "slide_count": 2})
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({
        "slides": [
            {"layout": "title", "title": "Product", "body": ["WPS-first"]},
            {"layout": "two_column", "title": "Why", "body": ["Atomic", "Compact", "Safe", "Verified"]},
        ]
    }), encoding="utf-8-sig")
    output = tmp_path / "created.pptx"
    response = service.create(spec, output)
    candidate = candidate_path(output)
    assert response["ok"] is True
    assert candidate.exists()
    assert len(Presentation(candidate).slides) == 2


def test_apply_works_on_freshly_created_candidate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PPT_AGENT_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(service.wps, "finalize", lambda path: {"wps_version": "test", "slide_count": 1})
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"slides": [{"layout": "title", "title": "Fresh", "body": ["deck"]}]}), encoding="utf-8-sig")
    output = tmp_path / "fresh.pptx"
    service.create(spec, output)
    candidate = candidate_path(output)

    from ppt_agent.paths import document_id, revision

    patch = tmp_path / "patch.json"
    patch.write_text(json.dumps({
        "request_id": "fresh-apply",
        "document_id": document_id(output),
        "revision": revision(candidate),
        "operations": [{"op": "set_text", "object": "s0:s2", "text": "Applied after create"}],
    }), encoding="utf-8")
    response = service.apply(candidate, patch)
    assert response["ok"] is True
    assert "Applied after create" in service.inspect(candidate, no_state=True)["data"]["structure"]

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ppt_agent import service
from ppt_agent.errors import PptAgentError


def test_doctor_requires_renderer_and_reports_wps_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "_pdftoppm", lambda: None)
    monkeypatch.setattr(
        service.wps,
        "probe",
        lambda: {
            "available": False,
            "version": None,
            "error": {
                "error_code": "WPS_COM_FAILED",
                "message_zh": "无法启动独立 WPS 演示 COM 实例",
                "next_action": "run_doctor",
                "com_error": "invalid class string",
            },
        },
    )

    payload = service.doctor()

    assert payload["ok"] is False
    assert payload["data"]["checks"]["pdftoppm"] is None
    assert payload["data"]["checks"]["wps_error"]["com_error"] == "invalid class string"


def test_qa_rejects_revision_change_during_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "deck.pptx"
    path.write_bytes(b"deck")
    revisions = iter(["sha256:before", "sha256:after"])
    monkeypatch.setattr(service, "validate_pptx", lambda _path: None)
    monkeypatch.setattr(service, "revision", lambda _path: next(revisions))
    monkeypatch.setattr(
        service,
        "run_qa",
        lambda *_args, **_kwargs: {"issue_count": 0, "error_count": 0, "warning_count": 0, "issues": []},
    )

    with pytest.raises(PptAgentError) as caught:
        service.qa(path, suggest_fixes=True)

    assert caught.value.code == "REVISION_CONFLICT"
    assert caught.value.retryable is True
    assert caught.value.details["document_unchanged"] is True


def test_render_does_not_publish_review_for_changed_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "deck.agent.candidate.pptx"
    path.write_bytes(b"deck")
    state = tmp_path / "state"
    monkeypatch.setenv("PPT_AGENT_STATE_DIR", str(state))
    revisions = iter(["sha256:before", "sha256:after"])
    monkeypatch.setattr(service, "enforce_risk_policy", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "revision", lambda _path: next(revisions))
    monkeypatch.setattr(service.wps, "export_pdf", lambda _path, pdf: (pdf.write_bytes(b"pdf") or {"wps_version": "12"}))
    monkeypatch.setattr(service, "_pdftoppm", lambda: Path("pdftoppm"))
    monkeypatch.setattr(service.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stderr=""))
    monkeypatch.setattr(
        service,
        "run_qa",
        lambda *_args, **_kwargs: {"issue_count": 0, "error_count": 0, "warning_count": 0, "issues": []},
    )

    with pytest.raises(PptAgentError) as caught:
        service.render(path)

    assert caught.value.code == "REVISION_CONFLICT"
    assert not list((state / "state").rglob("review.json"))
    assert not list((state / "renders").rglob("*.pdf"))

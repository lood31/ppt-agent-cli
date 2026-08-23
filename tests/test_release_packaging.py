from __future__ import annotations

from pathlib import Path

import pytest

from tools.create_release_zip import (
    ROOT,
    PackagingError,
    build_release_zip,
    collect_licenses,
    package_license_files,
    write_sha256sums,
)


def test_current_closure_has_vendor_and_dependency_license_texts() -> None:
    items = collect_licenses(ROOT)
    paths = {item.archive_path for item in items}
    assert "LICENSE" in paths
    assert "vendor/hands_on_deck/LICENSE" in paths
    assert "vendor/hands_on_deck/NOTICE.md" in paths
    assert any("/attrs-" in f"/{path}" for path in paths)
    assert any("/packaging-" in f"/{path}" for path in paths)
    assert any("/setuptools-" in f"/{path}" for path in paths)
    assert len([path for path in paths if path.startswith("licenses/")]) >= 23


def test_missing_distribution_license_fails_closed(tmp_path: Path) -> None:
    class FakeDistribution:
        version = "1.0"
        metadata = {"Name": "fake-package"}
        files = None

    with pytest.raises(PackagingError, match="no license text"):
        package_license_files("fake-package", lambda _name: FakeDistribution())


def test_release_zip_contains_root_and_vendor_licenses(tmp_path: Path) -> None:
    output = tmp_path / "candidate.zip"
    result = build_release_zip(ROOT, output, require_root_license=True)
    assert result["root_license_included"] is True
    assert result["license_file_count"] >= 23

    import zipfile

    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "LICENSE" in names
        assert "vendor/hands_on_deck/LICENSE" in names
        assert "vendor/hands_on_deck/NOTICE.md" in names
        assert "THIRD_PARTY_NOTICES.md" in names
        assert "license-manifest.json" in names
        assert all(path.startswith("licenses/") for path in names if path.startswith("licenses/"))
        assert archive.testzip() is None


def test_sha256sums_lists_executable_and_zip(tmp_path: Path) -> None:
    output = tmp_path / "candidate.zip"
    sums = tmp_path / "SHA256SUMS"
    build_release_zip(ROOT, output)
    write_sha256sums(sums, ROOT / "dist" / "ppt-agent.exe", output)
    lines = sums.read_text(encoding="ascii").splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("  ppt-agent.exe")
    assert lines[1].endswith("  candidate.zip")

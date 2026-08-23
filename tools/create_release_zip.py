from __future__ import annotations

"""Build a release-candidate ZIP with an auditable license bundle.

The candidate mode intentionally permits a missing project ``LICENSE`` so a
copyright decision is never fabricated.  ``--require-root-license`` is the
public-release gate and fails closed until that file exists.
"""

import argparse
import hashlib
import importlib.metadata as metadata
import json
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.2.4-beta.1"
PYTHON_VERSION = "0.2.4b1"
FREEZE = ROOT / "acceptance" / "freeze" / f"v{VERSION}"

RUNTIME_PACKAGES = (
    "Pillow",
    "pydantic",
    "python-pptx",
    "pywin32",
    "typer",
    "annotated-doc",
    "annotated-types",
    "colorama",
    "lxml",
    "markdown-it-py",
    "mdurl",
    "pydantic-core",
    "Pygments",
    "rich",
    "shellingham",
    "typing-extensions",
    "typing-inspection",
    "XlsxWriter",
)
BUILD_PACKAGES = (
    "PyInstaller",
    "pyinstaller-hooks-contrib",
    "altgraph",
    "attrs",
    "packaging",
    "pefile",
    "pywin32-ctypes",
    "setuptools",
)
ALL_PACKAGES = RUNTIME_PACKAGES + BUILD_PACKAGES


class PackagingError(RuntimeError):
    """Raised when a release input is absent or inconsistent."""


@dataclass(frozen=True)
class CollectedLicense:
    package: str
    version: str
    source: Path
    archive_path: str


def _key(name: str) -> str:
    return name.strip().casefold().replace("_", "-")


def _section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        raise PackagingError(f"THIRD_PARTY_NOTICES.md is missing section: {heading}")
    end = text.find("\n## ", start + len(heading))
    return text[start:] if end < 0 else text[start:end]


def notice_packages(notices: Path) -> dict[str, str]:
    """Read package/version rows from the two declared closure tables."""

    try:
        text = notices.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PackagingError(f"missing third-party notices: {notices}") from exc

    rows: dict[str, str] = {}
    for heading in (
        "## Declared runtime dependency closure",
        "## Single-file EXE build tooling",
    ):
        for line in _section(text, heading).splitlines():
            match = re.match(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
            if not match:
                continue
            name, version = (value.strip() for value in match.groups())
            if name in {"Package", "Component"} or set(name) == {"-"}:
                continue
            key = _key(name)
            if key in rows and rows[key] != version:
                raise PackagingError(f"duplicate package with conflicting version: {name}")
            rows[key] = version

    expected = {_key(name) for name in ALL_PACKAGES}
    if set(rows) != expected:
        missing = sorted(expected - set(rows))
        extra = sorted(set(rows) - expected)
        detail = []
        if missing:
            detail.append(f"missing from notices: {', '.join(missing)}")
        if extra:
            detail.append(f"not mapped by collector: {', '.join(extra)}")
        raise PackagingError("license collector and THIRD_PARTY_NOTICES.md disagree (" + "; ".join(detail) + ")")
    return rows


def _license_relpaths(distribution: metadata.Distribution) -> list[Path]:
    files = distribution.files or ()
    selected: list[Path] = []
    for item in files:
        relative = Path(str(item))
        name = relative.name.casefold()
        if any(marker in name for marker in ("license", "copying", "notice")):
            if any(part == ".." for part in relative.parts):
                raise PackagingError(f"unsafe license path for {distribution.metadata['Name']}: {relative}")
            selected.append(relative)
    return sorted(set(selected), key=lambda path: path.as_posix().casefold())


def package_license_files(
    package: str,
    distribution_resolver: Callable[[str], metadata.Distribution] = metadata.distribution,
) -> list[CollectedLicense]:
    try:
        distribution = distribution_resolver(package)
    except metadata.PackageNotFoundError as exc:
        raise PackagingError(f"package is not installed in the build environment: {package}") from exc

    version = distribution.version
    relative_paths = _license_relpaths(distribution)
    if not relative_paths:
        raise PackagingError(f"no license text found in installed metadata for {package} {version}")

    package_dir = re.sub(r"[^A-Za-z0-9._-]+", "-", package)
    output: list[CollectedLicense] = []
    for relative in relative_paths:
        source = Path(distribution.locate_file(relative))
        if not source.is_file() or source.stat().st_size == 0:
            raise PackagingError(f"license file is missing or empty for {package}: {relative}")
        archive_path = f"licenses/{package_dir}-{version}/{relative.as_posix()}"
        output.append(CollectedLicense(package, version, source, archive_path))
    return output


def collect_licenses(root: Path = ROOT, *, require_root_license: bool = False) -> list[CollectedLicense]:
    notices = root / "THIRD_PARTY_NOTICES.md"
    declared = notice_packages(notices)
    collected: list[CollectedLicense] = []

    for package in ALL_PACKAGES:
        package_items = package_license_files(package)
        expected_version = declared[_key(package)]
        if package_items[0].version != expected_version:
            raise PackagingError(
                f"version mismatch for {package}: notices={expected_version}, installed={package_items[0].version}"
            )
        collected.extend(package_items)

    vendor_dir = root / "vendor" / "hands_on_deck"
    for relative in (Path("LICENSE"), Path("NOTICE.md")):
        source = vendor_dir / relative
        if not source.is_file() or source.stat().st_size == 0:
            raise PackagingError(f"missing vendored license/notice: {source}")
        collected.append(CollectedLicense("EveryInc/hands-on-deck", "a24b996", source, f"vendor/hands_on_deck/{relative.as_posix()}"))

    root_license = root / "LICENSE"
    if require_root_license and (not root_license.is_file() or root_license.stat().st_size == 0):
        raise PackagingError("root LICENSE is required for a public release but is absent")
    if root_license.is_file() and root_license.stat().st_size:
        collected.append(CollectedLicense("project", VERSION, root_license, "LICENSE"))
    return collected


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _add_file(archive: zipfile.ZipFile, source: Path, archive_path: str, seen: set[str]) -> None:
    if archive_path in seen:
        raise PackagingError(f"duplicate archive path: {archive_path}")
    if not source.is_file():
        raise PackagingError(f"required release input is missing: {source}")
    archive.write(source, archive_path)
    seen.add(archive_path)


def build_release_zip(
    root: Path = ROOT,
    output: Path | None = None,
    *,
    require_root_license: bool = False,
) -> dict[str, object]:
    output = output or (root / "dist" / f"ppt-agent-{VERSION}-windows-x64-rc.zip")
    exe = root / "dist" / "ppt-agent.exe"
    if not exe.is_file():
        raise PackagingError(f"missing executable: {exe}")
    freeze = root / "acceptance" / "freeze" / f"v{VERSION}"
    freeze_files = {
        "apply-schema.json": freeze / "apply-schema.json",
        "capabilities.json": freeze / "capabilities.json",
        "freeze-manifest.json": freeze / "freeze-manifest.json",
    }
    for source in freeze_files.values():
        if not source.is_file():
            raise PackagingError(f"missing freeze asset: {source}")

    licenses = collect_licenses(root, require_root_license=require_root_license)
    fixed = {
        "ppt-agent.exe": exe,
        "README.md": root / "README.md",
        "CHANGELOG.md": root / "CHANGELOG.md",
        "THIRD_PARTY_NOTICES.md": root / "THIRD_PARTY_NOTICES.md",
        "RELEASE_CHECKLIST.md": root / "RELEASE_CHECKLIST.md",
        "install.ps1": root / "tools" / "install.ps1",
        "uninstall.ps1": root / "tools" / "uninstall.ps1",
        **freeze_files,
    }
    for source in fixed.values():
        if not source.is_file():
            raise PackagingError(f"required release input is missing: {source}")

    manifest = {
        "manifest_version": "1",
        "product_version": VERSION,
        "root_license_included": any(item.archive_path == "LICENSE" for item in licenses),
        "files": [
            {
                "package": item.package,
                "version": item.version,
                "path": item.archive_path,
                "sha256": _digest(item.source),
                "size": item.source.stat().st_size,
            }
            for item in licenses
        ],
    }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(prefix=output.stem + ".", suffix=".tmp", dir=output.parent, delete=False) as handle:
            temp_path = Path(handle.name)
        seen: set[str] = set()
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for archive_path, source in fixed.items():
                _add_file(archive, source, archive_path, seen)
            for item in licenses:
                _add_file(archive, item.source, item.archive_path, seen)
            if "license-manifest.json" in seen:
                raise PackagingError("reserved archive path collision: license-manifest.json")
            archive.writestr("license-manifest.json", manifest_bytes)
        temp_path.replace(output)
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        raise

    return {
        "path": output.as_posix(),
        "sha256": _digest(output),
        "size": output.stat().st_size,
        "root_license_included": manifest["root_license_included"],
        "license_file_count": len(licenses),
        "archive_file_count": len(fixed) + len(licenses) + 1,
    }


def write_sha256sums(output: Path, exe: Path, release_zip: Path) -> None:
    lines = [f"{_digest(exe)}  {exe.name}", f"{_digest(release_zip)}  {release_zip.name}"]
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="ascii")
    temporary.replace(output)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an auditable ppt-agent release candidate ZIP")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sha256sums", type=Path)
    parser.add_argument("--require-root-license", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.root.resolve()
    output = (args.output or (root / "dist" / f"ppt-agent-{VERSION}-windows-x64-rc.zip")).resolve()
    sums = (args.sha256sums or (root / "dist" / "SHA256SUMS")).resolve()
    try:
        result = build_release_zip(root, output, require_root_license=args.require_root_license)
        write_sha256sums(sums, root / "dist" / "ppt-agent.exe", output)
    except PackagingError as exc:
        print(f"release packaging refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({**result, "sha256sums": sums.as_posix()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

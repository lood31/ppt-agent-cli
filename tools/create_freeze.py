from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.2.4-beta.1"
FREEZE = ROOT / "acceptance" / "freeze" / f"v{VERSION}"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(exe: Path, *args: str) -> dict:
    completed = subprocess.run(
        [str(exe), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def main() -> None:
    exe = ROOT / "dist" / "ppt-agent.exe"
    FREEZE.mkdir(parents=True, exist_ok=True)

    capabilities = contract(exe, "capabilities")
    apply_schema = contract(exe, "schema", "apply", "--full")
    capability_path = FREEZE / "capabilities.json"
    schema_path = FREEZE / "apply-schema.json"
    capability_path.write_text(
        json.dumps(capabilities, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    schema_path.write_text(
        json.dumps(apply_schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    fixed = [
        "LICENSE",
        "pyproject.toml",
        "uv.lock",
        "README.md",
        "CHANGELOG.md",
        "THIRD_PARTY_NOTICES.md",
        "RELEASE_CHECKLIST.md",
        "tools/build_exe.ps1",
        "tools/create_freeze.py",
        "tools/create_release_zip.py",
        "tools/create_synthetic.py",
        "tools/entrypoint.py",
        "tools/install.ps1",
        "tools/run_api_token_ab.py",
        "tools/uninstall.ps1",
        "tools/verify_wps_file.py",
        "tools/version_info.txt",
        "tools/wps_com_poc.py",
    ]
    paths = [ROOT / item for item in fixed]
    paths += sorted((ROOT / "src" / "ppt_agent").glob("*.py"))
    paths += sorted((ROOT / "vendor" / "hands_on_deck").glob("*.py"))
    paths += sorted((ROOT / "vendor" / "hands_on_deck").glob("*.md"))
    paths += [ROOT / "vendor" / "hands_on_deck" / "LICENSE"]
    paths = sorted({path.resolve() for path in paths})

    source_files = []
    tree = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        sha256 = digest(path)
        source_files.append({"path": relative, "sha256": sha256, "size": path.stat().st_size})
        tree.update(f"{relative}\0{sha256}\n".encode())

    manifest = {
        "freeze_version": "1",
        "product_version": VERSION,
        "python_package_version": "0.2.4b1",
        "schema_version": capabilities["schema_version"],
        "engine_version": capabilities["engine_version"],
        "created_at": datetime.now().astimezone().isoformat(),
        "source_tree_sha256": tree.hexdigest(),
        "exe": {"path": "dist/ppt-agent.exe", "sha256": digest(exe), "size": exe.stat().st_size},
        "capabilities": {
            "path": capability_path.relative_to(ROOT).as_posix(),
            "sha256": digest(capability_path),
        },
        "apply_schema": {
            "path": schema_path.relative_to(ROOT).as_posix(),
            "sha256": digest(schema_path),
        },
        "source_files": source_files,
        "git_freeze": False,
    }
    (FREEZE / "freeze-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (FREEZE / "README.md").write_text(
        "# v0.2.4-beta.1 release-candidate freeze\n\n"
        "This is a content-addressed release-candidate freeze, not a public release tag. "
        "Public release remains blocked until every gate in RELEASE_CHECKLIST.md passes.\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()

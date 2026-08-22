from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path


def canonical_path(path: Path) -> Path:
    return path.expanduser().resolve()


def document_id(path: Path) -> str:
    normalized = os.path.normcase(str(canonical_path(path)))
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ppt-agent:{normalized}"))


def revision(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def candidate_path(source: Path) -> Path:
    name = source.name
    suffix = ".pptx"
    stem = name[: -len(suffix)] if name.lower().endswith(suffix) else source.stem
    if stem.endswith(".agent.candidate"):
        return source
    if stem.endswith(".agent"):
        stem = stem[: -len(".agent")]
    return source.with_name(f"{stem}.agent.candidate.pptx")


def accepted_path(source: Path) -> Path:
    name = source.name
    suffix = ".pptx"
    stem = name[: -len(suffix)] if name.lower().endswith(suffix) else source.stem
    if stem.endswith(".agent.candidate"):
        stem = stem[: -len(".agent.candidate")]
    elif stem.endswith(".agent"):
        return source
    return source.with_name(f"{stem}.agent.pptx")


def source_path(source: Path) -> Path:
    name = source.name
    suffix = ".pptx"
    stem = name[: -len(suffix)] if name.lower().endswith(suffix) else source.stem
    if stem.endswith(".agent.candidate"):
        stem = stem[: -len(".agent.candidate")]
    elif stem.endswith(".agent"):
        stem = stem[: -len(".agent")]
    return source.with_name(f"{stem}.pptx")


def state_root() -> Path:
    override = os.environ.get("PPT_AGENT_STATE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        local = str(Path.home() / "AppData" / "Local")
    return Path(local) / "ppt-agent"

# Release-gate audit — 2026-08-21 22:05 (+08:00)

Scope: read-only release-candidate audit plus isolated install/ZIP smoke. No
PPT feature code, A/B result, LICENSE choice, Git metadata, tag, or public
release was changed.

## Verified

- Product package version: `pyproject.toml` and `src/ppt_agent/__init__.py`
  are `0.2.4b1` (PEP 440 spelling of the release name `0.2.4-beta.1`).
- JSON Schema: source `SCHEMA_VERSION`, frozen capabilities, and frozen apply
  schema are all `2.1`.
- Frozen manifest: every one of 31 listed source files, capabilities,
  apply-schema, and `dist/ppt-agent.exe` matches the recorded SHA-256 and
  size. The manifest source-tree digest also recomputes successfully.
- EXE metadata: FileVersion/ProductVersion are `0.2.4-beta.1`.
- EXE smoke from the source tree: `--version`, `capabilities`, and
  `schema apply --op set_text` returned success and the expected contracts.
- ZIP integrity: `ZipFile.testzip()` returned clean. Extracting the ZIP into
  an isolated directory and running `--version`, `capabilities`, and
  `schema apply --op set_text` succeeded.
- ZIP and EXE SHA-256 match `dist/SHA256SUMS`:
  - EXE: `df87346bd55c13df39bbd0a4d521e902091d2bd6b276679fdbcd70127c4b72f3`
  - ZIP: `ccbd40c7235c84d9be341d9da867938fe2d13c784755f09bc21d98bf7ee0fb50`
- Install/uninstall smoke passed with `-NoPath` in a unique temporary
  per-user Programs directory. The target was removed afterward and no user
  PATH entry was changed.
- `uv lock --check` and `uv pip check --python .venv\\Scripts\\python.exe`
  passed when `UV_CACHE_DIR` was redirected to a workspace-local audit cache.
  The default uv cache is ACL-blocked in this environment; that is an
  environment issue, not a lock mismatch.
- `git diff --check` passed. Secret-pattern scan over source, tests, tools,
  acceptance, audit, vendor, and release metadata was clean. `results/local/`
  is ignored by `.gitignore`.

## Remaining blockers / findings

1. **P0 release blocker — root LICENSE is absent.** The ZIP has no root
   `LICENSE`; the checklist and README correctly prohibit distribution until
   the copyright owner chooses and supplies one. This audit intentionally did
   not make that legal choice.
2. **P0 release blocker — third-party license bundle is incomplete.** The ZIP
   contains `HANDS_ON_DECK_LICENSE` and `THIRD_PARTY_NOTICES.md`, but not the
   required vendor `NOTICE.md` nor the full license texts for the dependency
   closure listed in `THIRD_PARTY_NOTICES.md`. Rebuild packaging only after
   the root license decision and a deterministic license-collection step.
3. **P0 release blocker — independent Git provenance is absent.** The copied
   checkout has no `.git`; the outer repository reports it as an untracked
   directory (`?? ./`). Do not treat an outer-repository commit as the RC's
   release commit, and do not tag until the checkout has an auditable history.
4. **P0 acceptance blockers remain as recorded in the 17:40 progress report:**
   Luna Max six-scenario A is not frozen, B has not run, and 3–5 successful
   real-deck trials are missing.
5. **Environment gate:** EXE `doctor` correctly returned structured
   `ENVIRONMENT_INCOMPLETE` / `WPS_COM_FAILED` because this machine has no
   registered WPS COM class. `pdftoppm` and LibreOffice were detected. A
   target Windows/WPS machine must rerun `doctor` and obtain `healthy=true`.

## No source repair made

The release wrapper scripts behaved correctly in the isolated smoke, and the
freeze hashes are internally consistent. The missing legal files, dependency
license bundle, Git provenance, Luna measurements, real-deck evidence, and
target WPS registration cannot be safely fabricated by an external audit.

## Resume order

1. Choose and add the root `LICENSE`; collect the exact third-party texts and
   rebuild the ZIP plus `SHA256SUMS`.
2. Establish independent Git history, then regenerate freeze assets from the
   final source/build outputs.
3. Complete Luna Max A freeze, then B-only and the required stability rounds.
4. Complete 3–5 real-deck trials and target-machine WPS `doctor` evidence.
5. Only after all checklist blockers are green, create the release commit/tag.

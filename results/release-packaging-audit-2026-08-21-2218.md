# Release packaging audit — 2026-08-21 22:18 (+08:00)

This change is limited to release packaging and license evidence. It does not
choose or create the project root `LICENSE`, change PPT behavior, or touch
the Luna A/B fixtures/results.

## Implemented

- Added `tools/create_release_zip.py`, a deterministic RC packager.
- It parses the two package tables in `THIRD_PARTY_NOTICES.md`, verifies that
  every declared runtime/build package is mapped, checks installed versions,
  and collects every installed metadata file whose name contains `LICENSE`,
  `COPYING`, or `NOTICE`.
- Missing packages, missing/empty license files, version drift, unsafe paths,
  missing vendor notices, duplicate archive paths, and missing freeze/build
  inputs fail closed.
- Candidate ZIPs contain exact vendor paths:
  `vendor/hands_on_deck/LICENSE` and `vendor/hands_on_deck/NOTICE.md`.
- Candidate ZIPs contain `license-manifest.json` with package/version/path/
  SHA-256/size records for the collected texts.
- `--require-root-license` is the public-release gate. It returns exit code 2
  while the copyright owner has not supplied the root license. The default RC
  mode does not invent one and records `root_license_included: false`.
- Added four regression tests and included the packager in the freeze source
  manifest. The release checklist now names the packager and exact required
  archive paths.

## Evidence

- Public gate: `python tools/create_release_zip.py --require-root-license`
  refused with `root LICENSE is required for a public release but is absent`.
- RC rebuild succeeded:
  - ZIP: `dist/ppt-agent-0.2.4-beta.1-windows-x64-rc.zip`
  - SHA-256: `66f430fcb867747105ef58015dda2006bb8a43f077752d3002bfc5b9c4f0f99a`
  - archive members: 42
  - collected license records: 31 (29 dependency/build texts + 2 vendor files)
  - `root_license_included: false`
- `dist/SHA256SUMS` was regenerated. EXE hash remains
  `df87346bd55c13df39bbd0a4d521e902091d2bd6b276679fdbcd70127c4b72f3`.
- `ZipFile.testzip()` passed. Clean-directory extraction smoke passed for
  EXE `--version`, `capabilities` (`schema_version=2.1`), and
  `schema apply --op set_text`; vendor license/notice and license manifest
  were present.
- Freeze manifest was regenerated after the packaging changes; all 32 listed
  source files, frozen Schema/capabilities, and EXE digest recompute exactly.
- Full pytest run passed: 607 tests. Targeted packaging tests: 4 passed.
- Temporary packaging/test directories were removed. A pre-existing
  `.tmp-luna-runtime-tests` directory was not touched because it belongs to
  the parallel benchmark work.

## Still not publishable

The RC is intentionally still blocked: there is no root `LICENSE`, so the
public packaging gate refuses to build a legally complete release. Git
provenance, Luna Max A/B, real-deck trials, and target-machine WPS `doctor`
evidence remain separate acceptance gates.

# v0.2.4 Beta release-candidate progress — 2026-08-21 23:15 cutoff

## Outcome

The current tree is a verified release candidate, not an approved public Beta.
Product tests, the rebuilt executable, the frozen Schema, synthetic real-WPS
animation/transition/apply/accept closure, and the completed portion of the new
Luna Max A baseline are supported by current evidence. Public release remains
blocked by the owner-license decision, Git provenance migration, missing real
user-deck trials, and the unfinished Luna Max A/B stability run.

## Frozen product and package

- Product release: `0.2.4-beta.1` (`0.2.4b1` in Python/PEP 440).
- Schema: `2.1`.
- Engine: `hands-on-deck@a24b996`.
- Full local suite: `608` tests collected and passed on 2026-08-21.
- `uv lock --check` passed (`37` packages resolved); its workspace-local
  temporary cache was removed afterward.
- Freeze manifest: `acceptance/freeze/v0.2.4-beta.1/freeze-manifest.json`.
- Freeze source tree SHA-256:
  `9c39bd002fe138b22d30574e68399892237170e0c30a4a05a0c596cf9a166869`.
- All 35 manifest entries were rehashed after the final WPS cleanup change;
  mismatch count: `0`.
- Executable SHA-256:
  `7b657b6e37df4f91e9eb1b29cebdb77b082bdc9633a02908944b1ac41d9cfc28`.
- Release-candidate ZIP SHA-256:
  `1f626754cecd3635de7829b95ea22a1c7a5277790b277d5403d4f64a57e6626f`.
- Windows VersionInfo is populated: FileVersion/ProductVersion
  `0.2.4-beta.1`, ProductName `ppt-agent`, OriginalFilename `ppt-agent.exe`.
- The ZIP has 42 entries, including 29 dependency-license files, the vendored
  engine license/notice, a generated license manifest, and third-party notices.
  It intentionally has no root `LICENSE` until the owner makes that decision.
- Clean-directory ZIP smoke passed for `--version`, `capabilities`, and
  `schema apply --op set_text`.
- The unpacked final executable's real-environment `doctor` returned
  `healthy=true`, `wps_com=true`, WPS `12.0`, with `soffice` and `pdftoppm`
  present.
- Isolated install -> `--version` -> uninstall passed; the installed executable
  hash matched the final executable and the install directory was removed.
- A targeted credential-pattern scan covered 65 source, test, tool, acceptance,
  and root text/config files and found zero API-key-like matches.
- Public-package fail-closed check passed: `--require-root-license` exited `2`
  and created neither a ZIP nor a checksum file while root `LICENSE` is absent.

## Real WPS closure

Evidence is under `results/local/wps-recheck-2026-08-21/`.

- Real WPS apply wrote one paragraph animation and one transition.
- Candidate reopened in WPS with four slides.
- Animation counts were `[1, 0, 0, 0]`; effect type `10`, trigger `1`.
- Transition values were `[3852, 0, 0, 0]`.
- QA returned zero errors and zero warnings.
- WPS rendered PDF plus four page images.
- `accept` succeeded; the source remained unchanged, the accepted document
  retained the structure, baseline advanced, and candidate/journal/lock were
  cleaned.
- Independent original-resolution visual QA passed all four pages.
- A nested-WPS lifecycle leak was fixed in `src/ppt_agent/wps.py`; the regression
  test proves reopen begins only after the writer application exits. A real
  source-level WPS regression produced no new WPS process after three seconds.

This is a synthetic closure deck. It does not count as any of the required
three-to-five desensitized real-user PPT trials.

## New Luna Max API A/B standard

The permanent standard is now the same configuration for both arms:

- model: `gpt-5.6-luna`;
- reasoning effort: `max`;
- Codex CLI runtime: exact `0.148.0` executable plus its code-mode host;
- official `turn.completed.usage` only;
- a frozen Luna A manifest is mandatory before any B-only comparison;
- the historical GPT-5.4 baseline cannot be mixed into the Luna target.

The runner, tests, and `acceptance/ab/README.md` enforce this contract. The user
explicitly authorized sending the benchmark PPTX/PNG/JSON fixtures to Luna and
the associated Token charges on 2026-08-21.

At the cutoff, successful Luna A evidence is retained under
`results/local/token-api/api-luna-max-a-v1/`. Scenarios 01–04 completed with
`returncode=0`, one official `turn.completed` event, and an output PPTX. Their
combined measured usage was 8,881,233 input tokens (8,340,480 cached), 86,131
output tokens, 134 tool calls, and 3,001.337 seconds. Thus the partial A total
for uncached input plus output is 626,884 tokens. This is not a comparison
result because scenarios 05–06 and all B measurements are missing.

Independent Luna Max original-resolution visual QA passed all 20 pages in
scenarios 01–04; non-blocking notes are recorded in `visual-qa-partial.md`.
The four event logs were replayed after shutdown: each contains exactly one
`turn.completed`, every official usage field matches `usage.json`, and every
recorded output PPTX exists. A separate final-PPTX structure check confirmed
all 28 required scenario-01 content strings across eight slides, every required
scenario-02 edit, the complete `MVP 真实试用记录` rich-text title in scenario 03,
and scenario 04's 32 pt in-bounds repaired title.
Scenario 05 was stopped immediately after `thread.started` / `turn.started` and
has no official usage or output; scenario 06 did not run. An offline
`--freeze-a` attempt correctly refused the partial evidence at scenario 05.
Incomplete/legacy zero-token rows are not baseline evidence. The remaining A
scenarios must be resumed before `--freeze-a`; B must not start against a
partial A.

## Read-only consistency decision

Do not add a global read lock for Beta. Pure `inspect` and `diff` remain
optimistic reads. Commands whose read result drives a later side effect use
before/after revision verification (notably render and QA fix suggestions).
Together with revision-bound apply, candidate state, WAL recovery, and explicit
accept/discard, this is sufficient for the Beta boundary. Strong consistency
for every read remains a post-Beta P2 unless real trials produce a reproducible
failure. The focused read-consistency regression suite passed `3/3` after the
final build.

## Unresolved release gates

1. The copyright owner must choose the root license. No default was invented.
2. The copied directory has no independent `.git`; its files combine a DS
   history with later release work. Do not copy `.git` or claim a tag. Safest
   migration is to overlay this reviewed snapshot onto a clean checkout of DS
   `main=2d2bc131d4fbefbe00c1c0847cf12f7646d6f36e`, review the 23 differing tracked
   files, then commit/tag the release candidate. The DS and outer histories have
   no common ancestor even though an orphan baseline tree matches.
3. Complete and visually verify the remaining Luna Max A scenarios, freeze A,
   run one six-scenario B-only gate, and only if it passes add two independent B
   stability rounds. Do not report Token reduction from partial evidence.
4. Complete three-to-five desensitized real PPT trials with inspect -> apply ->
   WPS reopen -> QA -> render -> manual preview -> accept/discard, recording
   manual rework and any fallback.

## Safe continuation

1. Resume only missing A scenarios with:
   `.\.venv\Scripts\python.exe tools\run_api_token_ab.py --run-a --run-id api-luna-max-a-v1 --scenarios 05,06`.
   The runner removes the incomplete scenario-05 work directory, retains the
   four successful rows, and replaces each stale failed row only after the new
   measurement returns.
2. Run fresh original-resolution visual QA for newly completed A outputs.
3. Execute `--freeze-a --baseline-run-id api-luna-max-a-v1`, then
   `--check-baseline`.
4. Run a new six-scenario B-only round. Stop and diagnose if any gate fails;
   do not immediately spend two more rounds.
5. Resolve the owner license and Git migration separately; rebuild/freeze only
   if either changes distributed bytes.

At shutdown there were zero benchmark-runtime Codex processes, zero WPS/
LibreOffice processes, zero project-root temporary directories, and no
generated PyInstaller `build/` directory or `.spec` file left behind.

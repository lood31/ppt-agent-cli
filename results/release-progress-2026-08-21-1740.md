# Release and Luna A/B progress at the 17:40 stop point

Date: 2026-08-21

## Completed in this work period

- Changed the future API benchmark standard to `gpt-5.6-luna` with reasoning
  effort `max` for both A and B.
- Archived the former GPT-5.4/high A manifest as
  `acceptance/ab/api-token-a-baseline-gpt54.json` without changing its bytes.
- Added a resumable six-scenario A runner and retained B-only reuse after a
  valid Luna A freeze.
- Pinned benchmark execution to `@openai/codex@0.148.0`; the installed 0.142.3
  client rejects Luna before inference.
- Hardened the runner so event and stderr evidence are streamed to disk during
  execution, timeouts are explicit, and the full Windows child-process tree is
  terminated.
- Added a hard evidence gate: `returncode=0` and `output.pptx` are insufficient
  without at least one official `turn.completed.usage` event.
- Added cost fail-closed behavior: after any invalid A or B measurement, the
  runner persists evidence and stops before the next paid scenario.
- Focused runner regression: 9 passed. Complete repository regression:
  602 passed.
- No benchmark `codex.exe` process remained after the interrupted attempt; the
  Codex desktop process was not touched.

## Live A/B status

The user explicitly authorized fixture transfer to Luna and A/B API charges.

The six rows currently visible in `api-luna-max-a-v1/usage.json` are 0.142.3
client rejections with zero usage and are not experimental measurements. An
upgraded 0.148.0 scenario-01 attempt did reach Luna and generated
`scenario-01/A/output.pptx` plus rendered QA assets, but the old blocking runner
timed out before it saved a complete event log and official usage. It is not a
valid A result. Scenarios 02-06 were not executed with the upgraded client; B
was not executed.

Therefore:

- Luna A baseline: not frozen.
- Luna B: not run.
- Token reduction: no conclusion.
- Quality rate: no conclusion.
- The canonical `api-token-a-baseline.json` remains the historical GPT-5.4
  baseline; the archived copy has the identical SHA-256
  `EB577CD72AA3342FEF8FA77D66946F986A10118462C6B0DFCCF051BC1B0B3038`.
- Offline `--freeze-a` rejects the incomplete Luna run, and
  `--check-baseline` rejects the historical canonical manifest because its
  model/protocol differs from the Luna Max standard. Both fail closed before
  any API call.

## Exact continuation sequence

From `D:\Libre offer-cli\ppt-agent-cli-main`:

```powershell
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --run-a --run-id api-luna-max-a-v1
```

The runner will retry invalid rows. The incomplete scenario-01 inference has
already incurred unquantified usage, so its retry is additional recovery cost.
After all six A rows have complete official usage and quality evidence:

```powershell
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --freeze-a --baseline-run-id api-luna-max-a-v1
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --check-baseline
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --run-id api-luna-max-b-YYYYMMDD
```

Do not freeze A merely because `output.pptx` exists. Require six successful
rows, official usage, event logs, WPS reopen/structure evidence, and original-
resolution visual QA. Only then may future tests become B-only.

## Release boundaries unchanged

- Root license choice is still required from the copyright owner.
- This copied project directory still lacks independent Git provenance/tagging.
- Three to five successful real, desensitized PPT trials are still missing.
- Public Beta must wait for the Luna stability result and those release gates.

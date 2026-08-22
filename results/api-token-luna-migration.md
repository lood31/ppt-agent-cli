# Luna Max API A/B migration status

Date: 2026-08-21

## New standard

All new API-level A/B measurements are defined as:

- Model: `gpt-5.6-luna`
- Reasoning effort: `max`
- Codex CLI: pinned `codex-cli 0.148.0` through the workspace runner
- Scenarios: `01` through `06`, unchanged from `DESIGN.md` section 15
- A: installed `pptx` skill workflow
- B: frozen `dist/ppt-agent.exe` workflow
- Usage: official `turn.completed.usage` fields, with total, uncached input, cached input, output, elapsed time, and tool calls recorded

The previous GPT-5.4/high evidence remains historical and is stored in
`acceptance/ab/api-token-a-baseline-gpt54.json`. It is not a Luna target and
must not be mixed into a Luna comparison.

## Offline preparation completed

- `tools/run_api_token_ab.py` uses `gpt-5.6-luna` and `max` for both arms.
- `--run-a --run-id <id>` runs or resumes the six A scenarios using the frozen fixture inputs.
- `--freeze-a --baseline-run-id <id>` writes the new `acceptance/ab/api-token-a-baseline.json` manifest.
- `--check-baseline` verifies model, reasoning effort, prompts, task text, fixture hashes, event/output hashes, and Codex CLI version without an API call.
- Future B-only runs reuse only the newly frozen Luna A manifest.
- Runner-focused unit tests: `10 passed`.
- Runner syntax check: `py_compile` passed.

## Authorized live run and current boundary

The user explicitly authorized sending the six benchmark fixtures to Luna and
the corresponding A/B API cost. The A command was attempted:

```powershell
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --run-a --run-id api-luna-max-a-v1
```

The first attempts used the installed `codex-cli 0.142.3`. Luna rejected that
client before inference, so those zero-usage rows are not measurements. The
runner is now pinned to the complete official `0.148.0` Windows runtime,
including `codex-code-mode-host.exe`; a tool-call preflight passed before the
paid run.

The first Luna A run `api-luna-max-a-v1` produced four technically successful
rows before it was invalidated:

| Scenario | Input | Cached input | Output | Tool calls | Elapsed |
|---|---:|---:|---:|---:|---:|
| 01 | 2,872,245 | 2,726,144 | 31,226 | 35 | 1049.840 s |
| 02 | 2,463,931 | 2,258,816 | 21,374 | 37 | 826.340 s |
| 03 | 1,844,299 | 1,757,696 | 16,200 | 33 | 636.692 s |
| 04 | 1,700,758 | 1,597,824 | 17,331 | 29 | 488.465 s |

Each row has `returncode=0`, exactly one official
`turn.completed`, and an output PPTX. Event replay confirmed that usage fields
match `usage.json`. Independent Luna Max original-resolution visual QA passed
all 20 pages. Partial totals are 8,881,233 input tokens, 8,340,480 cached input
tokens, 86,131 output tokens, and 134 tool calls. These are A-only partial
measurements retained for audit only, not a Token-reduction result or reusable
baseline.

On the next scenario-05 attempt, the A agent read the product `README.md`,
`DESIGN.md`, and `src/ppt_agent/` to infer animation behavior. That contaminates
the original-`pptx`-skill arm and can inflate A Token usage. The process was
terminated before `turn.completed` or output, and the whole v1 run was marked
invalid in `results/local/token-api/api-luna-max-a-v1/INVALID.md`.

The A rule now explicitly forbids product source/docs, memory, prior experiment
outputs, and recursive project search. The runner also verifies the stored A
protocol/fixture reference before a partial resume. A changed contract requires
a new run ID; it can no longer overwrite the reference while retaining old
successful rows. No B arm has run against a Luna baseline.

The runner now streams `events.jsonl` and `stderr.log` while the process is
alive, applies a 1,200-second per-scenario timeout, records timeout metadata,
and terminates the full Windows process tree. A row is resumable/freezeable only
when it also contains official `turn.completed.usage` and a real output. The
current repository suite passes all 608 collected tests. Any
invalid A or B measurement is persisted and then stops the run before the next
paid scenario.

Build the replacement baseline from all six scenarios with a new run ID:

```powershell
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --run-a --run-id api-luna-max-a-v2
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --freeze-a --baseline-run-id api-luna-max-a-v2
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --check-baseline
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --run-id api-luna-max-b-YYYYMMDD
```

Do not report Token reduction, quality pass rate, or Luna A/B conclusions
until the six A outputs are complete, independently verified, and a comparable
six-scenario Luna B run exists.

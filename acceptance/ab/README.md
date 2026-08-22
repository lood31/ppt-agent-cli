# Six-scenario A/B acceptance benchmark

This benchmark compares the frozen `v0.2.4-beta.1` release-candidate CLI
(`ppt-agent.exe --version` reports `0.2.4b1`) against the existing `pptx` skill
workflow. It is acceptance evidence, not product functionality.

## Current API standard

As of 2026-08-21, all new API-level A/B runs use the same Codex model and reasoning configuration:

- Model: `gpt-5.6-luna`
- Reasoning effort: `max`
- Codex CLI: pinned to `@openai/codex@0.148.0`, then recorded in the frozen
  manifest and required to remain unchanged
- Six scenarios: the cases frozen in `DESIGN.md` section 15

The former GPT-5.4/high evidence is historical only and is archived as
`acceptance/ab/api-token-a-baseline-gpt54.json`. It must not be used as the
new Token target or mixed into a Luna Max comparison.

To create the new A baseline after the required external-materials approval:

```powershell
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --run-a --run-id api-luna-max-a-v1
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --freeze-a --baseline-run-id api-luna-max-a-v1
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --check-baseline
```

After the Luna A manifest is frozen, all new comparisons run B only and reuse
that exact Luna A evidence:

```powershell
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --run-id api-luna-max-b-YYYYMMDD
```

The runner verifies the model, reasoning effort, prompts, task text, source
hashes, event logs, outputs, and Codex CLI version before any B call.

Rules:

- The same agent, textual material, source files, and quality gates are used for both arms.
- Arm A follows the original `pptx` skill (`PptxGenJS` for creation; unpack/edit/pack for existing decks).
- Arm A may read only its scenario inputs and the installed `pptx` skill. It may
  not read `ppt-agent` source, tests, Schema, project docs, memory, prior
  experiment outputs, or recursively search the product repository.
- Arm B uses `dist/ppt-agent.exe` from the frozen MVP.
- Textual structure/tool payload bytes are converted to approximate tokens with `ceil(bytes / 4)`; image-input costs are reported separately.
- A scenario is deliverable only if WPS can reopen it and required operations are present without unintended changes.
- Unsupported and silently degraded behavior counts as failure; it is not repaired during this benchmark.
- Raw outputs and working files live under ignored `results/local/ab/`.

The follow-up API-level benchmark uses official `turn.completed.usage` fields rather than byte estimates. Historical GPT-5.4 evidence is tracked in `results/api-token-ab.md`; new Luna evidence belongs under ignored `results/local/token-api/api-luna-max-*/`.

## Reusing the frozen API A arm

After a successful six-scenario Luna A run, that arm is frozen in
`api-token-a-baseline.json`. Until then, the canonical file still contains the
historical GPT-5.4 baseline and must not be used as a Luna target. The future
manifest records the exact model, reasoning effort, prompts, task text,
source-file hashes, A outputs, event logs, and official usage values.

Future runs execute B only:

```powershell
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --run-id api-luna-max-b-YYYYMMDD
```

Before any API call, the runner verifies the frozen A evidence and experiment protocol. It copies B inputs directly from the frozen A snapshots. Missing or changed inputs, A outputs, event logs, model, prompts, task text, Codex CLI version, or reuse of the A run directory causes a hard failure. The new `usage.json` contains the frozen A rows marked `source: frozen_a_baseline` plus the newly measured B rows.

Partial A resume is also protocol-bound. If `fixture-reference.json`, the A
prompt, or fixture manifest differs, the runner refuses the existing run ID;
all six scenarios must use a new run ID under the new contract.

The baseline can be checked without an API call:

```powershell
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --check-baseline
```

The prior GPT-5.4 B-only interface-load regressions are historical evidence in `results/api-token-b-interface-v02.md` and related reports. They do not establish Luna Max performance; the Luna migration requires a fresh six-scenario A and then fresh B-only runs.

`--freeze-a` is only for intentionally replacing the baseline after a new complete A/B experiment; it does not call the API:

```powershell
.\.venv\Scripts\python.exe tools\run_api_token_ab.py --freeze-a --baseline-run-id api-luna-max-a-v1
```

Scenarios are the six cases frozen in `DESIGN.md` section 15.

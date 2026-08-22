# v0.2.4 Beta RC progress — 2026-08-21 23:45 cutoff

## Outcome

The release candidate remains technically healthy, but the Luna Max A baseline
was correctly invalidated rather than frozen with contaminated evidence. No B
comparison was started.

## New deterministic benchmark defects found and fixed

1. The former A prompt only prohibited calling `ppt-agent`; it did not prohibit
   reading product docs/source. During scenario 05 the A agent read `README.md`,
   `DESIGN.md`, and `src/ppt_agent/` to infer animation behavior. The paid call
   was terminated before `turn.completed` and `api-luna-max-a-v1` is explicitly
   marked `INVALID.md`.
2. Partial A resume overwrote `fixture-reference.json` while retaining successful
   rows from the old prompt. The runner now compares the complete stored
   fixture/protocol reference before a resume and requires a new run ID on any
   drift.
3. The isolated A prompt did not name the Python interpreter containing the
   installed skill dependencies, so the agent guessed runtimes. The A contract
   now supplies a fixed `A_PYTHON` path and preflights it before paid work.
4. A now explicitly permits only scenario inputs plus installed `pptx` skill
   docs/scripts, and forbids product source/tests/Schema/EXE/docs, memory, prior
   experiment outputs, and recursive product search.

Focused runner tests pass `12/12`; the complete repository suite now passes all
`610` collected tests. Test temporary directories were removed.

## Luna evidence status

- `api-luna-max-a-v1`: invalid due to cross-arm product-repository contamination;
  scenarios 01–04 remain audit evidence only and cannot be reused.
- `api-luna-max-a-v2`: invalid obsolete code-mode-host preflight attempt.
- `api-luna-max-a-v2-isolated-20260821`: invalid incomplete interpreter contract.
- `api-luna-max-a-v3`, scenario 06: used the corrected isolated contract. It
  produced a structurally valid 4-slide `output.pptx`; required title and
  0.25-inch movement assertions passed, and no prohibited repository reads were
  observed. The hard cutoff occurred before `turn.completed`/`usage.json`, so it
  is not a measurement and must be rerun. Visual QA also remains incomplete.

The next valid baseline must run all six scenarios under one unchanged v3
contract. Freeze A only after every row has official usage and independent
quality evidence. Then run B-only; do not compare against any v1/v2 totals.

## Product/release state unchanged

- Product: `0.2.4-beta.1` / Python `0.2.4b1`; Schema `2.1`.
- EXE SHA-256:
  `7b657b6e37df4f91e9eb1b29cebdb77b082bdc9633a02908944b1ac41d9cfc28`.
- RC ZIP SHA-256:
  `1f626754cecd3635de7829b95ea22a1c7a5277790b277d5403d4f64a57e6626f`.
- Real synthetic WPS animation/transition/render/accept closure remains passed.
- Public release is still blocked by root-license choice, Git provenance
  migration, three-to-five desensitized real PPT trials, and complete Luna A/B
  stability evidence.

## Safe continuation

Use the current runner and a new clean run ID (recommended
`api-luna-max-a-v3-full`) for all six A scenarios. Do not resume any invalidated
directory. Monitor event logs for prohibited reads and stop immediately on
contamination. After six successful rows, perform fresh original-resolution
visual/structural QA, freeze A, validate it offline, and only then start B.

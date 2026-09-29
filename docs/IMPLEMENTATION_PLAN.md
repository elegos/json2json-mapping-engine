# Implementation plan — status

This is the milestone plan the implementation has followed since
`docs/ARCHITECTURE.md` was finalized, and where each milestone actually
stands. `ARCHITECTURE.md` is the normative spec (what the system *is*);
`spike-notes.md` is the M0.5 Oracle-runtime findings; this file tracks
*progress against the plan*, including where reality (real Oracle
behavior, or a design gap the architecture doc left open) changed the plan
along the way.

Legend: ✅ done · 🚧 partial · ⬜ not started

---

## ✅ M0 — Repo scaffolding

uv-managed Python 3.12 project, ruff + basedpyright, `pytest`. Typed
`mapper.toml` loader (`cli/config.py`) with required-key validation per
target. CI runs ruff/basedpyright/`pytest tests/track1` on every push.

**Deviation from the original plan**: CI targets **Forgejo** as primary
(`.forgejo/workflows/ci.yml`), with GitHub Actions kept as a mirror
(`.github/workflows/ci.yml`) — the original plan assumed GitHub only.

---

## ✅ M0.5 — Oracle/PL-SQL runtime spike

Findings in `docs/spike-notes.md`. Folded into building M2a rather than
being a separate hand-written-only exercise — the compiler's own generated
SQL became the spike vehicle once it existed.

**Deviation**: container image is
`container-registry.oracle.com/database/adb-free:latest-23ai` (official
Oracle Autonomous Database Free), not the originally-planned
`gvenzl/oracle-free` — swapped per explicit instruction. Connect over
plain TCP on port 1521 (service `myatp`), not the wallet/TLS listener on
1522, for spike simplicity.

**Real findings that changed the design** (see `spike-notes.md` for full
detail):
- The architecture's "~2048-byte" `RAISE_APPLICATION_ERROR` budget assumption
  was incomplete: `SQLERRM` hard-truncates to 512 bytes; even
  `DBMS_UTILITY.FORMAT_ERROR_STACK` (~1899 bytes observed) cuts the
  character stream, not at a JSON boundary. Fixed by making the generated
  code measure the payload with `LENGTHB` while building it and stop before
  either the 20-entry cap or the byte budget, whichever comes first.
- PL/SQL forbids size/scale constraints on function **RETURN types and
  parameters** (`PLS-00263`) — only variable *declarations* may carry them.
- `JSON_OBJECT(...) RETURNING CLOB` is SQL-context-only; native PL/SQL
  raises `PLS-00684`. Native PL/SQL `JSON_OBJECT()` defaults to VARCHAR2
  (4000-byte cap) — relevant to composite-value construction (see M2b).
- `JSON_ARRAY_T.put(pos, val)` **inserts** by default; replacing at a
  position requires the `OVERWRITE => TRUE` argument.
- `JSON_ELEMENT_T.compare_to()` compares generically (numbers, strings,
  dates) without needing to know the value's type ahead of time — used for
  both `sorted()` and `max`/`min` (see M2b).
- `JSON_OBJECT_T.get_*` on a missing key returns `NULL`, does not raise —
  "unchecked" without a schema means "coerces to null", not "anything goes
  including numeric operations".

---

## ✅ M1 — Schema Generator

JSON Schema → `.pyi` stubs / `@dataclass` files. Named stubs per
`oneOf`/`anyOf` alternative, `JsonObj` fallback for `patternProperties`,
required-first field ordering in dataclasses. Golden-file tested. Also
exposes a structured `SchemaTypes` API (not just rendered text) consumed
directly by the Type Checker (M2b) and the Build CLI (M3).

---

## ✅ M2a — Compiler skeleton (bootstrap mode, no fusion)

Validator (security gate), Scope Resolver, Function Linker, naive PL/SQL
Code Generator emitting the twin `map_<id>` / `map_<id>_safe` procedures.

**This milestone's shape changed significantly during M2b** (see below) —
the *initial* M2a build used zero-argument nested-closure rule functions
and an `e_field_omitted` PL/SQL exception for the "omit field" case. Both
were replaced once M2b's design discussion settled on explicit-parameter,
standalone (package-assembly-ready) functions. The "twin procedure,
per-rule error accumulation, three-way return semantics" *contract* from
M2a is unchanged; only the mechanism moved.

---

## ✅ M2b — Type Checker, built-in library, Loop Fusion Optimizer

Substantially larger than originally scoped, through several rounds of
design discussion that closed real gaps the architecture doc left open:

- **Type Checker** (`compiler/type_checker.py`): reads vs input
  `SchemaTypes`, writes vs output `SchemaTypes` (undeclared-field,
  type-compatibility, required-field-coverage checks). Two real bugs found
  and fixed after the calling-convention refactor below: read-checking
  inside a function body was still resolving names via the *caller's*
  scope (a leftover from the zero-arg-closure convention), and the
  aggregate built-ins had no entry in the parallel `infer_produced_type`
  (so writing one to a required field was always rejected as nullable).
- **Full built-in library** (`compiler/backends/plsql/builtins.py`):
  `coalesce`, `round`, `concat`, `if_else`, `split_first`, `split_nth`,
  `lookup`, `parse_date` — plus, added later (see "Case 2" below), `max`,
  `min`, `sum`, `avg`, `count`.
- **Function-calling convention (locked in, replacing M2a's original
  design)**: rule functions are root-level with **explicit typed
  parameters** — no implicit closure over `root`/`src`/the loop variable.
  Still emitted as standalone PL/SQL functions (siblings of `map_<id>`,
  not nested inside them) so a later package-assembly step (M3+) can
  selectively expose them in the package spec via the new
  `[target.plsql] export_rule_functions` config key. "Omit field" uses a
  `p_omitted OUT BOOLEAN` parameter instead of a shared exception, since a
  standalone function can't rely on an exception object declared in one
  specific caller's scope.
- **Composite output values**: `Line(LineId=..., LineAmount=...)` (keyword
  construction of a locally-declared `@dataclass`) builds the value **in
  memory** via a `.put()` sequence directly on a `JSON_OBJECT_T` — not
  round-tripped through `JSON_OBJECT()`/text (an earlier version did that
  and hit the PLS-00684 bug + the 4000-byte VARCHAR2 ceiling, both above).
- **Output arrays**: `out.<Field>.append(<expr>)`, recognized as a
  statement (no new grammar needed). One `JSON_ARRAY_T` accumulator per
  list-typed output field.
- **Loop codegen**: single-level `for` loops over a source array.
- **Loop Fusion Optimizer** (`compiler/loop_fusion.py`, standalone,
  target-agnostic — reused by the not-yet-built M5 transpiler): merges
  sibling `for` loops over a structurally identical source array;
  normalizes the bootstrap `if cond: continue` filtering idiom into a
  per-branch `IF NOT (cond)` guard, always (whether or not fusion actually
  merges anything); checks `@parallel(degree=...)` agreement across a
  fused group, resolved per `optimizer.parallel_conflict`. The
  architecture's own `sum(D)` cross-rule dependency example is
  **deliberately not implemented** — today's rule functions take explicit
  parameters with no shared mutable state, so there's no mechanism
  producing a real dependency edge to detect; building DAG/cycle-detection
  scaffolding now would only be testable against fabricated inputs.
  Revisit once an aggregation-driven cross-rule dependency actually exists.
- **Case 1 — progressive per-element index**: `for i, x in
  enumerate(root.items):` (0-based) / `enumerate(root.items, start=1)`
  (1-based) — real Python `enumerate()` syntax, binding to the PL/SQL loop
  counter that already existed internally. Paired with `sorted(root.items,
  key="field", reverse=...)` (a for-loop-iterable wrapper, not a builtin),
  lowered to a native in-place insertion sort using
  `JSON_ELEMENT_T.compare_to()` — an index is only meaningful if iteration
  order is defined. Functional-layer equivalents documented (not
  implemented — M5 territory): `@index`/`@index.N` anchors, `sort:` on the
  Loop rule.
- **Case 2 — aggregation over an array**: `max`/`min`/`sum`/`avg`/`count`
  taking `(array, field_name)` positionally. Unlike template builtins,
  these need a native loop (an accumulator), so — like dataclass
  construction — they're only valid as the direct value of a `return` /
  `out.<field> = ...` / `.append(...)`, not nested in a larger expression.
  `count` needed no loop (`{array}.get_size`).
- **Documented, not implemented**: the M5 transpiler's parameter-naming
  convention for *generated* `.map.py` (`root`/`src` always, `index` /
  `index1..indexN` only when actually referenced) — explicitly scoped as a
  generated-code convention only; hand-written bootstrap `.map.py` stays
  fully unconstrained (arbitrary structure, developer may use side effects
  and write to `out` directly instead of via functions, if they choose).

All of the above verified end-to-end against the live Oracle 23ai spike
container, not just unit-tested.

---

## ✅ M3 — Build CLI (`mapper`)

`mapper build` / `compile` / `stubs` / `check`, bootstrap mode only
(driven-mode raises a clear "not implemented yet, needs M5" error rather
than silently no-op'ing).

- Build cache keyed on `source hash + full mapper.toml raw dict` — any
  config change invalidates every cached hash project-wide, for free
  (every mapping's hash includes the same shared dict, no special-casing
  needed).
- `mapper check` never trusts the cache — it always recompiles fresh and
  diffs against `build/compiled/`, since the cache only tracks whether the
  *source* changed, not whether the committed output still matches.
- **New convention, resolving a gap the Type Checker work left open**:
  which schema pair applies to which `.map.py` file. Resolved by basename:
  `mappings/<name>.map.py` picks up `schemas/{input,output}/<name>.json`
  independently on each side, if present. Not specified anywhere in
  `ARCHITECTURE.md`; easy to override later with an explicit table in
  `mapper.toml` if this convention ever proves insufficient.
- `mapper stubs` also generates `.vscode/settings.json` / `pyrightconfig.json`
  (merged into any existing file, not blindly overwritten) and the
  `__mapping__.pyi` IDE stub — typed `Any` for `root`/`src`/`out` for now
  (a known, documented limitation: accurately typing it per-mapping needs a
  per-open-file stub-selection mechanism that doesn't exist yet).
- **Caveat found dogfooding this in the tool's own repo**: `pyrightconfig.json`
  existing at all makes pyright ignore `pyproject.toml`'s
  `[tool.basedpyright]` section entirely, regardless of what keys the
  generated file contains. Not a bug — an interaction worth knowing about
  before a project's first `mapper stubs` run. (The tool's own demo/
  verification project was built and torn down as temp-directory pytest
  fixtures for exactly this reason — it must never live inside this
  repo's own `mappings/`/`schemas/`.)

Verified end-to-end with a 3-mapping demo project (schema-checked,
no-schema, and loop+dataclass-array cases): cache hits on rerun, full
rebuild on any config change, `mapper check` correctly failing on a
manually tampered `build/compiled/*.sql`.

---

## ✅ M4 — Testing infrastructure (`mapper test --track 1|2`)

`mapper test` runs Track 1, Track 2, or both (no `--track`). Exit code 1 on
any failure.

- **Track 1** (`cli/track1.py`): runs the project's `tests/track1/` through
  pytest. Skipped with a note if the project has no such directory.
- **Track 2** (`cli/track2.py`): detects Podman (preferred) or Docker, starts
  an ephemeral `--rm` container from `[test] container_image:container_tag`
  on a random loopback port, waits for the DB (thin-mode `python-oracledb`,
  new dependency — no Oracle client needed), deploys
  `build/compiled/<mapping>.sql`, runs `map_<id>_safe` per case, removes the
  container in a `finally`. Verified live against the 23ai ADB-Free image
  (~1m40s cold start + run).
- **Case convention (new, not in ARCHITECTURE.md)**:
  `tests/golden/<mapping>/<case>.input.json` (required) and
  `<case>.expected.json` (optional). With an expected file: key-order-
  insensitive diff, PASS/FAIL. Without: output printed for inspection.
  Per-rule errors from `p_err` are always shown; a case with an expected
  file also fails if any rule errored.
- **Deploy check**: `CREATE OR REPLACE` with a compile error doesn't raise
  client-side, so deploy reads `USER_ERRORS` and fails loudly.
- **Mappings deploy one at a time**: rule functions are top-level
  `fn_<rule_id>`, so two mappings sharing a rule id would overwrite each
  other in one schema. Cases run right after their own mapping is deployed.
- No runtime: `mapper test` prints "Track 2 unavailable" and succeeds;
  `--track 2` explicitly requested exits 1.
- Deploys as `ADMIN` in its own schema; `[target.plsql] schema` is not used
  by the harness.

**Not done**: `allowed`-constraint warnings on Track 2 output (needs the
`.fn.yaml` data model, M5); Track 2 in CI (needs a runner with Docker access
to pull the Oracle image); exercising `map_<id>` (raising variant) — only the
`_safe` twin is run.

---

## ⬜ M5 — Functional layer transpiler (driven mode)

Not started. This is where several already-*documented* design decisions
from M2b become load-bearing rather than aspirational:
- `@index`/`@index.N` anchors and `sort:` on the Loop rule need real
  anchor-resolution logic (Stage 2).
- The rule-id abbreviation/collision-index algorithm (§Rule id generation)
  is exercised here for the first time — bootstrap mode never needed it.
- Stage 4 (Loop Fusion) should import `compiler/loop_fusion.py` directly,
  per the M2b design — no reimplementation.
- Stage 5's generated-`.map.py` parameter-naming convention (`root`/`src`/
  `index`/`index1..N`) needs an actual emitter following it.
- Auto/Manual mode and the validation decay rules are pure data-model work
  independent of the above.

---

## ⬜ M6 — Tauri desktop tool

Not started (Rust shell, AG Grid frontend, Gitoxide VCS, embedded LLM).
Depends on M5 existing first (the tool edits `.fn.yaml`, which needs the
transpiler to do anything with).

---

## ⬜ M7 — Migration & interoperability tooling

Not started (Excel/PDF import, reverse-import from `.map.py`,
bootstrap→driven archival). Lowest priority per the original plan — nothing
else in the system depends on it.

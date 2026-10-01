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
- **Single package deploy**: the whole `build/compiled/<package>.sql` is
  deployed once and cases call `<package>.map_<id>_safe` (see "Package
  namespacing" below).
- No runtime: `mapper test` prints "Track 2 unavailable" and succeeds;
  `--track 2` explicitly requested exits 1.
- Deploys as `ADMIN` in its own schema; `[target.plsql] schema` is not used
  by the harness.

**Not done**: `allowed`-constraint warnings on Track 2 output (needs the
`.fn.yaml` data model, M5); Track 2 in CI (needs a runner with Docker access
to pull the Oracle image); exercising `map_<id>` (raising variant) — only the
`_safe` twin is run.

---

## ✅ Package namespacing (follow-up to M3/M4)

> Superseded: the single package (and `fn_package`) became one package per mapping, see the
> backlog entry below and `docs/backends/plsql.md`.

Rule ids are unique per mapping only, so standalone top-level `fn_<rule_id>`
collided across mappings. Now all mappings compile into **one PL/SQL
package** (`[target.plsql] package`): entry points
`<package>.map_<id>` / `map_<id>_safe`, rule functions namespaced
`fn_<mapping_id>_<rule_id>`, private unless `export_rule_functions`.

- Codegen returns a `PlsqlUnit` per mapping (`compile_module`);
  `compiler/backends/plsql/package.py` assembles units into spec + body.
  `compile_source` remains as a single-mapping convenience.
- Build output changed: one `build/compiled/<package>.sql` instead of
  `<mapping>.sql` per mapping; the per-mapping cache stores the serialized
  unit (`build/cache/<file>.unit.json`). `mapper build <file>` still
  packages every mapping (needs all units); it only narrows the status report.
- Duplicate mapping ids and identifiers over 128 bytes are build errors.
- Trade-off: any mapping change recompiles the whole package body. Splitting
  into several packages would need a grouping key in `mapper.toml`; not done.
- Entry-point names kept as `map_<id>` (not bare `<id>`) to avoid clashing
  with rule functions and reserved words.

---

## ✅ M5 — Functional layer transpiler (driven mode)

The transpiler package (`transpiler/`) and driven-mode build are done, including
nested output (see "Nested output" below).

- **Stage 1** `transpiler/model.py`: strict `.fn.yaml` loader (unknown keys, bad
  kinds/types, manual-without-override → error with the rule path). Auto/Manual
  and validation data model, plus `apply_decay` (`validated`→false,
  `needs_review`→true only when `source.path`/`transform.expression` changes).
- **Rule ids** `transpiler/ids.py`: abbreviation (first 3 letters, `[]` stripped),
  sibling-collision indexing (`sub`, `sub2`), fully-qualified ids, uniqueness checks.
- **Stage 2** `anchors.py`: `$`, `@`, `@N`, `@label`, `@index`, lookup labels; skips
  string literals.
- **Stage 3** `expr.py`: expression blocks (locals mangled with the rule prefix,
  trailing expression → `return`, `return Null` / bare `return` detected).
- **Stage 4** reuses `compiler.loop_fusion.fuse_loops` — no reimplementation.
- **Stage 5** `transpile.py`: `.map.py` via `ast.unparse`, header comment recording
  options, parameter convention (`root`, `src`, `index` only if referenced).
- **CLI**: `mapper transpile`; `mapper build/compile/check` work in `mode = "driven"`
  (`mappings/functional/*.fn.yaml`). Input schema, when present, types the generated
  parameters so the Type Checker still checks reads.
- Supported: scalar fields, objects (+ `guard`), loops (`filter`, `sort`, `@index`,
  `index_start`), all nested to any depth; lookups, `format`/`format_mode`, manual
  `code_override`. Limits and deviations: `ARCHITECTURE.md`, "Implementation
  status and deliberate deviations (M5)".

**Compiler changes this forced** (found by running the generated code on Oracle 23ai
via Track 2, not by unit tests):
- `src` resolved to the `enumerate()` index variable in a `for index, src in ...` loop.
- `sorted()` sorted the *source* array in place, reordering it under later loops over
  the same array; it now sorts a `.clone`.
- `x != None` compiled to `x <> NULL` (never true); now `IS [NOT] NULL`.
- New: constant dict literals (`JSON_OBJECT_T('...')`) and the `trunc` built-in.
- The build cache key now includes the mapping's input/output schema files (a schema
  edit used to leave stale output).

- **Filter + `@index`** numbers the survivors: `.map.py` says so explicitly with
  `enumerate([x for x in <iter> if <cond>])` (real-Python semantics; a body `continue`
  still numbers skipped elements). `loop_fusion` lowers it to a guard plus an internal
  `i = __next_index__(start, k)` statement — one counter per fused branch — and codegen
  emits `v_cnt_k` (verified on Oracle, fused and unfused).

**Nested output** (compiler + transpiler): the compiler now supports, inside rule
functions, list locals, `for` loops (same iterable forms as the body), `name.append(...)`,
locals bound from rule-function calls, and dataclass fields that are lists / nested
dataclasses / rule-function calls (`omitted` -> key left out); `list[T]` annotations.
The transpiler emits one function per element, children first, with parameters
`root, src<n>..src1, src, index<n>..index1, index` (indexes only when read). Verified on
Oracle 23ai with a three-level fixture (object with `guard` omitted, filtered + sorted +
indexed inner loops, outer element/index read from the inner level).

**Not done**: per-stage on-disk artifacts;
`@parallel` from `.fn.yaml`; the desktop tool's use of `apply_decay` (M6);
`allowed` warnings on Track 2 output; error isolation between
nested members (the top-level element is the unit of failure).

---

## 📋 Backlog — smaller leftovers (untracked until now)

Independent of M6/M7; pick up in any order.

- [x] **Type Checker: bare `return` in a non-nullable rule.** A rule annotated `-> T`
      with a bare `return` / `return None` is now an error. This exposed a transpiler
      bug: guarded objects were emitted as `-> Cls` with a bare `return`; they are now
      `-> Cls | None`.
- [x] **Track 2 in CI.** Job `track2` on the `docker-dind` runner label
      (`.forgejo/workflows/ci.yml`), green. Needs `docker-cli` in the job image; the
      harness probes docker with a minimal `info --format` and, with a remote
      `DOCKER_HOST=tcp://…`, connects to that host instead of `127.0.0.1`.
- [x] **Track 2: exercise `map_<id>`** (raising variant). Each case also runs `map_<id>`
      and checks it agrees with `_safe`: same output when no rule errors, else raises the
      reserved code with `total_errors` = number of rule errors.
- [x] **`allowed`-constraint warnings** on integration-test output (`cli/allowed.py`; only
      `.fn.yaml` `allowed`, schema-derived constraints wait for M6). Warnings never fail a case;
      keywords not evaluable on a scalar field are reported, not ignored.
- [x] **Implicit `multipleOf` rounding** in the transpiler: per-rule `choices` (replaces
      `format_mode`) + `[compiler.default_choices]` (replaces `decimal_mode`); conflict with
      `format` must be resolved via `choices.conflicts`. Steps are explained by comments in
      the `.map.py`. Schema-derived `multipleOf` and the editor UI wait for M6.
- [x] **Per-stage on-disk artifacts** of the transpiler. Four stages (load, build, fuse,
      emit — the old five-stage description did not match the code): `mapper transpile
      --stage N|alias`, `--dump-stages`, `--cached`; artifacts in
      `build/transpiled/stages/<mapping>/`.
- [x] **`@parallel` from `.fn.yaml`.** Loop key `parallel: N` / `{degree: N}` → `@parallel(degree=N)`
      on the loop's element function; `@parallel(N)` is an alias of `degree=N` in the DSL.
      PL/SQL backend: `map_<id>_fn ... PARALLEL_ENABLE` SQL-callable wrapper (checked on Oracle
      by the `orders` golden cases).
- [x] **Error isolation between nested members.** A failing nested rule call leaves out
      only its member and is reported under its own rule id; the parent is emitted
      (partial, `required` not enforced). PL/SQL: rule functions that call other rule
      functions take `p__errors IN OUT NOCOPY JSON_OBJECT_T`, the entry points fold it
      into their error map. Integration case: `orders/failed_member`
      (`<case>.expected_errors.json` declares the rule ids a case must report).
- [x] **One package per mapping** for PL/SQL, replacing the single package and `fn_package`:
      `[target.plsql.mapping_packages]` table or `mapping_package_prefix`/`_suffix` (one of
      the two is required), optional `mapping_index_package` forwarding to all; one
      `build/compiled/<package>.sql` per package (`Backend.assemble` returns file name -> text).
- [x] **`J2JME_FUNCTIONS` package** (`functions_package`, overridable) for the built-ins that
      are not 1:1 with a PL/SQL function (`split_first`, `split_nth`, `lookup`); generated
      only when used, deployed first. `if_else` stays inline (lazy branches). Checked on Oracle
      by `orders` (all three). Project functions join it when the `fn/` loader exists.
- [x] **Backend dispatch on `[project] target`.** Coarse `Backend` ABC
      (`compiler/backends/base.py`), self-discovering registry, `PlsqlBackend`; pipeline,
      Function Linker (built-ins now come from the backend) and `cli/build.py` only use the
      interface; required keys/defaults of `[target.<name>]` live in the backend.
- [ ] **`enumerate(..., dense=True)` / loop `guard`** — deliberately deferred: the loop
      `filter` stays the only guard for now.

---

## ⬜ M6 — Tauri desktop tool

Rust shell (Tauri), TypeScript + React + AG Grid frontend, in `desktop/`
(`desktop/src-tauri`, `desktop/ui`). Rust owns the shell (file I/O, subprocesses, later VCS);
Python owns the pipeline semantics: the tool talks to the `mapper` CLI as a subprocess
and never re-implements build logic.

Sliced; each slice is usable on its own:

- [ ] **M6.1 — shell, grid, save.** Open a project; list `mappings/functional/*.fn.yaml`;
      editable rule grid; save; Build / Check / Test buttons showing `mapper` output.
      No git, no LLM.
      - [x] `--json` on `transpile` / `compile` / `build` / `check`: one document
            `{ok, messages, diagnostics[{severity, file, rule, message}]}`, where `rule` is
            the `rules[i].rules[j]` path the loader reports. (`test` streams pytest output;
            not JSON yet.)
      - [x] `mapper fn read` / `mapper fn write` move a `.fn.yaml` as JSON through the
            `transpiler.model` loader (`transpiler/serialize.py` writes it back); `write`
            applies `apply_decay` per rule id and refuses a tree the loader rejects. YAML
            comments and hand-edited key order are not preserved.
      - [x] Python resolution order (engine `.venv` in a checkout → bundled → `python3.12`
            → `python3` → `python`); a candidate must import the engine. Banner + disabled
            actions when none is found.
      - [x] Tauri shell (`desktop/src-tauri`), React + AG Grid UI (`desktop/ui`), fixture
            `desktop/fixtures/orders-project`; `cargo test` drives the real `mapper`.
      - [ ] Run it by hand (`cargo tauri dev`) and fix what the GUI shows — not yet done:
            nothing here could open a window.
- [x] **Target / Source editing** (`transpiler/edit.py`, served by `mapper serve` to the
      grid so edits are instant): `OrderId` → `$.OrderId`; `A.B` creates the object `A` and
      moves the field under it; `Lines.A.B` on a declared loop puts `A` in every element;
      containers get `$.` (top level) or `@.` (nested); an emptied container is flagged
      "Empty container". Open: `Source` of a *nested* field is kept as typed (its
      `@item.…` / `$.items[*].…` convention is not settled).
- [x] **Add / delete rules** (`add_rule`, `delete_rule` in `transpiler/edit.py`; toolbar
      `+ Field` / `+ Object` / `+ Loop` / `Delete`). A new rule goes inside the selected
      container, else after the selected rule, else at the end; it gets a free name
      (`NewField`, `NewField2`, …) and is incomplete on purpose: the check flags the empty
      expression / loop source, and Save refuses it until filled. Deleting a container asks
      first. Not yet: reorder (drag).
- [x] **Lookups view** (`Rules` / `Lookups` tabs): list of `@label` lookups, key/value table,
      add / delete lookup and entry. A number / `true` / `false` / `null` keeps its type,
      anything else is a string (quote it to force one). Lookups are hidden from the rule grid.
      A lookup declares its value `type` (optional; `str int number bool date datetime`): the
      loader enforces it, expressions are typed by it, the table parses typed text by it.
- [x] **M6.1b — check on edit** (`transpiler/check.py`; `mapper fn check FILE`; `check` op of
      `mapper serve`, run by the grid 150 ms after each edit). Per rule, so one bad rule
      hides no other: the loader's checks, expression syntax and anchors, duplicate
      names; and, when a schema exists, Target / Type / Req. against the output schema,
      container kind and required fields, Source and every `$.` / `@.` reference of an
      expression against the input schema. Schema constructs it cannot follow count as
      unknown. **Expression types** (`transpiler/exprtypes.py`): bottom-up inference
      (literals, operators, references, built-in results) checked against what each place
      expects, flowing down: a built-in's parameter, an operand, the field's type. E.g.
      `round(lookup($.c, $.t, 0))` into `int` checks the values of `$.t` against `round`'s
      parameter and `round`'s result against `int`; a `lookup` table read from the input
      must be an object. `number` does not fit an `int` field. Unknown (no schema, project
      functions, unfollowed constructs) is never reported. Built-in signatures live in
      `exprtypes.SIGNATURES` (a test requires every built-in to have one); only
      single-expression rules are typed. Not yet: `format` / `enum` / ranges, typing of
      manual code, aggregates, nullability. Guards and filters take any value (Python truthiness,
      ARCHITECTURE.md §Truthiness); their insides are checked.
- [x] **Source value** (`transpiler/transpile.py::_value_text`, `anchors.uses_value`): the
      Source is `value` in the expression; an empty expression passes it through; a Source
      may be a constant (`source: {constant: 27}`, typed in the grid as `27`, `"x"`, `true`,
      `null`). The check types `value` by the Source (schema node or constant). Bare words in
      the Source column stay paths (`id` → `$.id`).
- [x] **Truthiness** in conditions (`_ExprTranslator.condition`, `truthy` in the functions
      package, golden mapping `truthiness`); the golden cases are not yet run on Oracle.
- [x] **Unsaved changes.** Save is explicit (no autosave). Build / Check / Transpile ask
      "Save before continuing?" (they read the files on disk); switching file or project
      and closing the window ask too (Save / discard / Cancel).
- [x] **Path style.** Targets show and are saved without `$.` / `@.`; a bare Source is
      rewritten to `$.x` (outside a loop) or `@.x` (inside one) by the loader and by
      `set_source`; both forms are accepted (`transpiler.model.qualify_paths`).
- [x] **Paths section** (`paths:` of `.fn.yaml`: `root` override, `aliases`, `@root` reserved;
      `transpiler/paths.py`). Expanded before check and transpile, checked against the input
      schema, own **Paths** tab in the tool. The developer dialect gained constant array
      positions (`root.a.list[0].b`: type checker, PL/SQL codegen, golden mapping `positions`;
      not yet run on Oracle).
- [x] **Unsaved changes and undo/redo.** Cells that differ from the saved file are bold (rules
      matched by id, else by path; a rule with no saved counterpart is bold whole); the file
      name in the list gets a `*`. Undo / redo (↶ ↷, Ctrl+Z / Ctrl+Y) keep snapshots of the
      rules and the `mapper.toml` draft; quick successive edits of one field are one step;
      history is dropped on switching file or project and kept across Save. Inside a text
      field the field's own undo applies.
- [x] **Project properties** (`mapper.toml` form; `cli/project_config.py`, `config_read` /
      `config_check` / `config_write` of `mapper serve`). Engine sections (`[project]`,
      `[optimizer]`, `[compiler.default_choices]`, `[test]`) are described in
      `cli/project_config.py`; the target's keys come from the backend:
      `Backend.options` (`Option`: key, kind, help, required, default, choices), which the
      loader also enforces (unknown keys, value kinds) and a conformance test requires to
      cover `required_keys` / `defaults`. The form has no code of a backend's own; a backend
      without `options` shows a "edit by hand" note. Rules spanning keys stay in
      `validate_config` and show as one message. Saving goes through `tomlkit`, so comments
      and key order survive and only changed lines change; an invalid config is refused.
      Choosing another target creates its `[target.X]` section. New dependency: `tomlkit`
      (the bundled Python runtime must include it).
- [ ] **M6.2 — validation UX.** validated / needs_review states, manual-override split
      pane, function-changed warnings.
- [ ] **M6.3 — VCS.** Gitoxide save-as-commit, pull --rebase, semantic rule-level merge.
- [ ] **M6.4 — LLM assist.** Validation suggestions, expression builder (Ollama / API).

**Extra mile (needs the Python backend below).** *Try a mapping in the tool*: import an input
JSON for the open mapping, run it and show the output next to the input, with the per-rule
errors highlighted on the grid rows (as `_safe` reports them). It runs the mapping compiled by
the Python backend, not the `.map.py` executed as Python (ARCHITECTURE.md: the `.map` files are
never executed as Python). The same runner could feed `tests/golden/<mapping>/*.input.json`
cases from the tool.

Prerequisites on the dev machine: `webkit2gtk-4.1` dev packages, `tauri-cli`.

---

## ⬜ M7 — Migration & interoperability tooling

Not started (Excel/PDF import, reverse-import from `.map.py`,
bootstrap→driven archival). Lowest priority per the original plan — nothing
else in the system depends on it.

---

## ⬜ Python backend (queued, after M6)

A backend of its own (`compiler/backends/python/`, `[project] target = "python"`), lightweight:
it compiles a mapping to a Python module (rule functions, `map_<id>` / `map_<id>_safe`
twins, the same error report) and needs no database or container. It is what makes the
desktop tool's preview and error highlighting possible, and it is a second implementation that
tests the first.

**The rule that governs it: results are backend-independent.** The same input must give the
same output, and the same rule errors, whichever backend compiled the mapping. Consequences to
build in:

- [ ] The golden cases (`tests/golden/<mapping>/*.input.json`, `.expected.json`,
      `.expected_errors.json`) are the shared contract: every backend runs all of them. Track 2
      stays per target (Oracle image for PL/SQL, none for Python), the cases do not.
- [ ] Built-ins: the Python reference implementations in `builtins.py` become the Python
      backend's implementations; where PL/SQL and Python could differ (rounding, null and empty
      string, date parsing, `split_nth` beyond the end, division by zero), the difference is
      settled once, written down, and both backends follow it.
- [ ] A conformance run in CI: the same cases on both backends, comparing outputs.
- [ ] Error isolation and `required` semantics (§Runtime error semantics) implemented
      identically.
- [ ] **Target interpreter.** The Python that *runs the generated module* is the host
      project's, not the engine's own (which the tool pins to 3.12 to compile). So the target
      declares it in `[target.python]` (a version, and whether it is free-threaded, e.g.
      `python = "3.14t"`), and the backend emits code for that interpreter: syntax and library
      features it has, and `@parallel` handled accordingly. The generated module must not import the
      engine.
- [ ] `@parallel(degree=N)` for real, unlike PL/SQL (where it only yields a SQL-callable
      wrapper): the elements of the loop are mapped by up to N workers. Strategy is a
      `[target.python]` choice: `process` (`ProcessPoolExecutor`; elements and results
      are plain JSON, so pickling is cheap, but start-up and transfer only pay off for
      heavy per-element work), `thread` (`ThreadPoolExecutor`; a real speed-up only on a
      free-threaded CPython — 3.13t, supported from 3.14 — while the project pins
      `>=3.12,<3.13`), `none` (sequential, the default until measured). Which strategies are
      allowed, and what `@parallel` means, follows from the target interpreter above (a
      free-threaded target may use `thread`; an older one may only offer `process` or
      `none`; asking for an unavailable strategy is a build error, not a silent fallback). Whatever the
      strategy, the result must equal the sequential one: results collected in element order
      (`map`, not completion order) and rule errors merged in element order, so "first
      failure of a rule wins" stays deterministic. The `orders` golden cases (degree 2)
      run under every strategy.
- [ ] Then the desktop preview (Extra mile in M6).

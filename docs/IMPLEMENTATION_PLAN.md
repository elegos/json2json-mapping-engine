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

uv-managed Python 3.14 project, ruff + basedpyright, `pytest`. Typed
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
  an ephemeral `--rm` container from `[target.plsql.test] container_image:container_tag`
  (moved from the global `[test]`: the test environment is the target's; the PL/SQL part lives in
  `compiler/backends/plsql/integration.py`, `cli/track2.py` is the shared orchestration)
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
- [x] **Undefined names in code overrides.** `ExprTyper.check_block` reports a name that nothing
      defines (`'x' is not defined`, on the Status column): the scope's `root`, `src`/`srcN`,
      `index`/`indexN` (only as many as there are enclosing elements), the block's own variables
      and parameters, the function registry, the casts, `Null`. Python's builtins are not
      reported; use before assignment is not looked for.
- [ ] **`enumerate(..., dense=True)` / loop `guard`** — deliberately deferred: the loop
      `filter` stays the only guard for now.

---

## ⬜ M6 — Tauri desktop tool

Rust shell (Tauri), TypeScript + React + AG Grid frontend, in `desktop/`
(`desktop/src-tauri`, `desktop/ui`). Rust owns the shell (file I/O, subprocesses, later VCS);
Python owns the pipeline semantics: the tool talks to the `mapper` CLI as a subprocess
and never re-implements build logic.

Sliced; each slice is usable on its own:

- [x] **M6.1 — shell, grid, save.** Open a project; list `mappings/functional/*.fn.yaml`;
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
      - [x] Python resolution order (engine `.venv` in a checkout → bundled → `python3.14`
            → `python3` → `python`); a candidate must import the engine. Banner + disabled
            actions when none is found.
      - [x] Tauri shell (`desktop/src-tauri`), React + AG Grid UI (`desktop/ui`), fixture
            `desktop/fixtures/orders-project`; `cargo test` drives the real `mapper`.
      - [x] Run it by hand (`cargo tauri dev`) and fix what the GUI shows: done in several
            rounds with screencasts and screenshots (editor closing on click, editor contrast,
            no sorting and the filter field, dual fuzzy search, icons, window title, the
            Project properties tab, the schemas and golden tabs). Each later slice was
            checked in the window by the user.
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
      package, golden mapping `truthiness`); run on Oracle since: the `truthy` function read an empty string as true
      (Oracle's `to_String` keeps the quotes: `""`, never NULL), fixed.
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
      run on Oracle since; reading `list[0]` needed `TREAT(.get(0) AS JSON_OBJECT_T)`, a
      `JSON_ARRAY_T` has no `get_Object`).
- [x] **Selecting one element** (`object` with `source: $.list[condition]`;
      `transpiler/selector.py`): first matching element, omitted when none; bare names in the
      condition are fields of the element, `=` is `==`. Checked against the input schema,
      editable in the Source column, golden mapping `selection` (run on Oracle since, with the same `TREAT` fix).
- [x] **A field of a selected element** (`$.items[marker = 'TOTALS'].qty` in a Source, an
      Expression or a guard; a `paths` alias may name the element, `@totals.qty`): the first
      matching element, null when none; the condition reads the loops around the rule (`@2`).
      One generated function per distinct selection, one local variable per rule that reads it
      (`transpiler/transpile.py`, `_picker` / `_extract`). Checked and completed in the tool,
      golden mapping `pick` (run on Oracle). Not done: a selection in a filter or sort key, two in
      one path, and sharing the found element across rules (each rule looks it up again).
- [x] **Completion in the Target / Source / Expression cells** (CodeMirror 6; `complete` op of
      `mapper serve`, `transpiler/complete.py`). `$.` / `$.a.` list the input schema's fields
      (honouring `paths.root`), `@` the loop labels, lookups, aliases, `@root`, `@index`, `@.` /
      `@label.` the loop element's fields, a bare name the built-ins and `value` (in a Source:
      the current element's fields; inside `[...]` of a selecting Source: the candidate's). Target:
      the output schema's properties not used by a sibling. ↑↓ choose, Enter / Tab accept, Esc
      closes. `CodeEditor.tsx` is reusable: the multi-line editor of a rule's code override (M6.2)
      will use it with a developer-dialect completer (`root.`, `src.`).
      Not driven by hand yet (no GUI automation here).
- [x] **Function registry** (`compiler/builtins.py`, `compiler/function_registry.py`): the
      built-ins as typed Python read with `ast`; typer signatures, completion and the IDE stub
      derive from it; `fn/*.fn` of a project are read the same way and replace a built-in of the
      same name (`all_functions(project)`). The registry showed that `len` was typed but had no
      PL/SQL implementation: it is no longer a built-in. Compiling and linking the project
      functions still waits for the `.fn` loader (Phase 1).
- [x] **Row filter, no sorting.** The grid cannot be sorted (the order of the rules is the
      mapping's); a field after the toolbar filters the rows by rule id or Target (substring,
      any case), keeping the containers a match is in and the rules of a matching container, and
      ignoring folding while it is in use. A dotted text (`customer.name`, `channel.customer.name`)
      is a path of Targets from the outside in (parts may skip containers; `customer.` = everything
      inside); a space works like a dot. The text is also always read as pieces of
      the names in order (`cusnam` finds `Customer.Name`), and both results are shown together. Esc clears it. Typing anywhere outside an editor or
      another field (no Ctrl / Alt / Meta) goes to the filter, so a cell no longer starts editing
      on a key press: it opens with a click or Enter / F2.
- [x] **Unsaved changes and undo/redo.** Cells that differ from the saved file are bold (rules
      matched by id, else by path; a rule with no saved counterpart is bold whole); the mapping's
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
- [x] **M6.2 — validation UX** (`transpiler/review.py`; ops of `mapper serve`: `proposal`,
      `take_over`, `accept_proposal`, `keep_override`, `set_override`; `check`
      also answers `review`):
      - **Split pane** (`OverridePane.tsx`, developer mode, below the grid for the selected
        field): the auto code on the left (what the transpiler generates from Source and
        expression, `auto_proposals`), the `code_override` in a multi-line `CodeEditor` on the
        right. *Edit as code* starts the override as that code; *Use auto code* drops it (the
        validation is left alone); *Keep override* takes the new auto code as the baseline.
      - **Override out of date**: `transform.last_auto_version` now holds the auto *code* at
        take-over; a manual rule whose current auto code differs is flagged (red edge, ⚠️
        tooltip), which also catches changes that are not in the expression itself.
      - **One Validation column** (Developer mode only; Not validated / To review / Validated,
        over the two flags of the file). The validation marks, edges and filter are hidden in
        the functional view.
      - **Function signature changes** are the check's business, not a separate mark: the check
        now counts the arguments of every call of a registered function (`ExprTyper._arity`) and
        also checks a manual rule's `code_override` (`Checker.devcheck`: `root`, `src`, `src1`...,
        a block too). A validated rule that gets an error keeps its tick while it is
        edited and goes back to *To review* on save (`mapper fn write`, `demote_invalid`); a rule
        with errors cannot be set to *Validated*.
        A compatible signature change raises nothing; keeping a function compatible is its
        author's job.
      - **State filter** next to the text filter: validated, to review, not validated,
        override out of date, with errors (with counts; the validation ones in Developer mode).
      - Limits: a rule that cannot be transpiled makes the auto code of every rule unavailable
        (the pane shows the reason).
- [ ] **M6.3 — VCS and collaboration.** Split in three; the old "Gitoxide save-as-commit, pull
      --rebase, semantic rule-level merge" is replaced by this (ARCHITECTURE.md §VCS says
      Gitoxide first and no custom merge driver: to be updated when a slice lands). Two ways of
      working, one merge engine under both.
      - [x] **M6.3a — Rule-level merge engine.** 3-way merge of two `.fn.yaml` from a base, in the
            engine (Python, track 1 tests): rules identified by id, a conflict only on the same
            field of the same rule, text-level fallback if the YAML does not parse. **The project's
            function files too** (`fn/*.fn`: new functions and the copies of built-ins in
            `builtin_overrides.fn`): merged function by function (`merge_fn_texts`), matched by name. Exposed as a
            **git merge driver** (`.gitattributes`: `*.fn.yaml merge=j2jme`, `*.fn merge=j2jme`), so it works from any
            git client and in CI, not only inside the tool. Generated files are never merged, they
            are regenerated.
            Done: `transpiler/merge.py` (`merge3` on the raw YAML data: a `rules` list matched by
            id, a rule without one by what it writes; a reorder, an add and a delete merge too; a
            conflict keeps *ours* and is reported with its path, e.g. `rules[cust].source.path`,
            and the three values; `choices` settle it per path), `mapper merge-driver %O %A %B %P`
            (rule-level merge, else `git merge-file` with conflict markers, exit 1), and `mapper
            merge-driver-install` (git config of the clone + `.gitattributes`), tests in
            `tests/track1/merge` including a real `git merge`; `fn/*.fn` are merged function by
            function by the same driver (picked by the file name). Not done: the merge editor in the
            UI (M6.3b) and a worker op for it. Limits: comments and key order of a hand-edited
            file are lost in a rule-level merge (as in any save by the tool).
      - [x] **M6.3b — Git mode** (the Gitoxide fallback left).
        - The tool works on a folder with `mapper.toml`; the git root is found from there up. It
          commits **only the project's paths** (pathspec). In-tree (the project is part of a bigger
          repo) and submodule (the commit goes to the submodule's repo; the parent's pointer is
          outside the tool) are both supported with no submodule-specific logic.
        - Git operations through the `git` CLI as a subprocess (Gitoxide does not cover rebase,
          merge, submodules well); if `git` is not installed, fall back to Gitoxide, accepting
          that merge and the rest are less capable (what it cannot do is disabled, with a tooltip).
        - Commit = check + build; if the check fails the commit is blocked or marked WIP.
          The sources a commit and a manifest cover are the mappings, the schemas, `mapper.toml`
          **and `fn/*.fn`** (overrides and new functions), which also change what is generated.
        - **Generated artifacts (decided).** `build/compiled/*.sql` stay committed by default, with
          a `manifest.json` next to them: the hash of each source (mapping, schemas, functions,
          `mapper.toml`) and of each output (the engine version is in `mapper.toml`, see below). On request the
          tool puts them in `.gitignore` and removes them from the repo (CI then builds and
          deploys). With them committed, CI regenerates and **fails on a difference**; with them
          ignored the build simply runs. Output is deterministic only for the same mappings **and**
          the same engine version, hence `[project] engine`. This closes the open point of the CI diff check (see Release).
          Done: `cli/manifest.py` and `cli/_version.py`. `build/compiled/manifest.json` is written by
          every build (`write_package`): `manifest` (format), `target`, `sources` (hash of
          `mapper.toml`, `mappings/*.map.py`, `mappings/functional/*.fn.yaml`, `schemas/**/*.json`,
          `lookups/*.lookup.yaml`, `fn/*.fn`; CRLF read as LF) and `outputs` (hash of each artifact);
          no date or machine, so building twice gives the same file. `mapper check` also compares it:
          a source or output that is new, gone or changed is a problem; with `build/compiled`
          git-ignored (`git check-ignore`) it only builds. The tool's version is `cli/_version.py`
          (the engine is shipped without package metadata), which `packaging/release.py prepare`
          replaces with the tag's version.
          **Engine version in `mapper.toml` (decided and done).** `[project] engine`, the only place
          the version is recorded (not in the manifest), written by the tool; `cli/engine_version.py`
          (semver order), `mapper upgrade`, the global `--allow-older-engine` /
          `J2JME_ALLOW_OLDER_ENGINE`, worker ops `engine_status` / `engine_upgrade`, a new project
          carries it, the properties form cannot change it. A newer tool warns and, in the desktop
          tool, asks before updating the project (the tutorial's copy silently); an older tool refuses
          to build and the desktop tool refuses to open, unless the user accepts the risk (a ticked
          box; `--allow-older-engine`); `mapper.toml` is never moved back (ARCHITECTURE.md §Engine
          version of a project). Tests: `tests/track1/cli/test_engine_version.py`. Not verified: the
          dialogs in the running desktop tool (types, unit tests and `cargo check` pass; no run). `mapper check` is
          now a step of the offline job in both pipelines.
          **Committed or ignored (done).** `mapper artifacts status | ignore | track` and the
          desktop tool's *Generated files…* (developer mode): `ignore` writes `build/compiled/` in the
          project's `.gitignore` and stages the removal from the git index (no commit, files stay
          on disk), `track` is the opposite; both verify with `git check-ignore` and restore
          `.gitignore` if the result is not what was asked; they need `git` (no Gitoxide fallback
          yet). New projects get a `.gitignore` committing only `build/compiled`. Tests:
          `tests/track1/cli/test_artifacts_mode.py` (real repositories, also a project inside a
          bigger one). Not verified: the dialog in the running tool.
        - **Portable Linux CLI** (no desktop, no Tauri) to run `mapper` in CI: generation, and the
          comparison against the committed artifacts. Same bundled Python as the AppImage; part of
          the release (see Release artifacts).
          Done: `j2jme-cli-linux-x86_64.tar.gz` (+ `.sha256`) of every release (`cli_tarball` in
          `packaging/build.sh`: `bin/mapper`, `engine/`, `python-runtime/`, 34 MB; checked here: the
          archive unpacks and `mapper version` / `mapper check` run from it) and `install-mapper.sh`
          (also a release file): reads `[project] engine` of `mapper.toml`, downloads that version's archive
          from `<releases>/v<version>/`, checks it, unpacks it in `~/.local/share/j2jme/<version>`
          and adds `bin/` to `$GITHUB_PATH`; tests in `tests/track1/release/test_install_mapper.py`
          (a release as a `file://` folder). **Not verified**: a run in a real CI job, a release made
          by `release.yml` carrying the two files (the `dist/packages/*` glob should take them), the
          script from a draft release (needs a token). Not done: the same for Windows / macOS CI.
        - [x] Pull with rebase, the conflicts shown in the UI (merge editor on the M6.3a engine).
        - **Git mode in the tool (done, except the Gitoxide fallback).** `cli/vcs.py` and the worker
          ops `vcs_*`; the **Version control…** panel (`VersionControl.tsx`): the changes of the
          project's paths, the version notes, *Commit*, *Pull*, *Push*, and the conflict editor.
          - *Commit* = the check (rule errors, and a build of every mapping), then the build, then one
            commit of the project's paths only (`mapper.toml`, `.gitignore`, `.gitattributes`,
            `mappings/`, `schemas/`, `lookups/`, `fn/`, `tests/golden/`) **and** `build/compiled`
            (when it is committed, not ignored). The first line of the notes is the subject, the
            rest the body, followed by the rules changed per mapping (added, removed, changed with
            the groups `source` / `transform` / `description` / `other`). A failing check blocks the
            commit and lists the problems; *Commit as WIP* then commits the sources only, with `WIP: ` in
            the subject. Whatever else is staged in the repository is left alone.
          - *Pull* = `git pull --rebase --autostash`; a clean rebase is silent. The generated files
            conflict whenever both sides built (their hashes): they are never merged, the rebase
            regenerates and carries on by itself. What both sides changed in a `.fn.yaml` (a rule
            field) or an `fn/*.fn` (a function) is shown as *mine* / *theirs (remote)*, one choice
            per item, then *Settle*; the rebase goes on to the next commit, which may stop again.
            *Give up the pull* aborts. Any other file in conflict cannot be settled in the tool
            (it says so; edit it outside, or give up).
          - Tests: `tests/track1/cli/test_vcs.py` (a bare remote and two clones: state, commit, WIP,
            scope, ignored artifacts, pull, conflicts by rule and by function, abort, push, worker
            ops) and `versionControl.test.ts`. **Not verified**: the panel in the running tool.
          - **Not done**: the Gitoxide fallback when `git` is not installed (the panel says so and
            does nothing; `gix` is not a dependency of the desktop crate), and the driver
            auto-install (`mapper merge-driver-install`) is still a manual, per-clone step: the tool
            settles in the panel what git leaves, with or without it.
      - [ ] **M6.3c — Shared-folder mode (OneDrive / SharePoint).** Only when a real team needs
            it. A git repo inside a synced folder is **not supported** (it corrupts `.git`): the
            tool detects such a path and warns.
        - Nothing generated is written in the synced folder: `build/` (and the rest that is not
          authored) goes to a local folder. At the first use in a synced folder the tool warns and
          asks the user for one; it is saved **per user** (the app's config), not per project.
          Choosing one is **optional**: if the user declines, the build stops there (nothing is
          written, no error state is remembered) and the tool asks again at the next attempt;
          generation and deploy are then left to CI/CD.
          (OneDrive has no ignore file; the only exclusion is an admin policy, so the app does it.)
          `.venv` is not needed: the tool brings its own Python. The build folder is fixed at
          `build/` today (not configurable in `mapper.toml`): it has to become configurable.
        - The sync does not merge: it makes conflict copies (`file-PC.yaml`) or the last writer
          wins. So: a **base per user** (hash and snapshot of the last version seen, in the app's
          config); when the file changes on disk (watcher), or at save if the disk differs from the
          base, a 3-way merge with the M6.3a engine, true conflicts in the UI; conflict copies are
          recognised by the name and offered for merge. Saves are atomic (temp file + rename).
        - **Presence**, advisory: one file per user, `.j2jme/presence/<mapping>.<user>.json` (never
          conflicts: one writer each), shows who is editing which mapping.
        - It is eventual consistency, not real-time editing.
      - [x] **Publish (both modes).** `mapper publish [--to DIR]` and a button: build (nothing
        is published if it fails), the artifacts written to the publish directory.
        Default: the current `build/compiled`; `[publish] dir` in `mapper.toml` overrides it,
        relative or absolute (a "guest" project); a per-user override. The set is **consistent**:
        `manifest.json` removed first and written last, with the hash of each output, so a reader
        never sees half a set. What the developer does with the folder afterwards is not the
        tool's business.
        Done: `cli/publish.py` and the `publish` command (also `--json`): precedence `--to` >
        `$J2JME_PUBLISH_DIR` (the per-user choice) > `[publish] dir` > `build/compiled` (then there
        is nothing to copy). The folder is never replaced or emptied (a guest's, a synced library):
        every file is written whole (temporary file + rename) and read back against its hash, the
        old manifest goes first, the new one is written last, and only files the old manifest listed
        and the new one does not are removed (a path outside the folder in a manifest is ignored).
        `publish.verify(folder)` checks a published folder against its manifest. `[publish] dir` is a
        field of the project-properties form; a **Publish** button (developer mode) next to
        Build. Tests: `tests/track1/cli/test_publish.py`.
        Also done: the **check before publishing** (`mapper publish` runs `mapper check` first: with
        the artifacts committed they must match the sources, else nothing is published and it says
        to build and commit; `--no-check` skips it; git-ignored artifacts have nothing to compare);
        **`mapper verify [DIR]`** (a published folder against its manifest: files missing or changed,
        unfinished = no manifest; needs no project when given a folder; `--json`); and the **per-user
        folder** in the desktop tool: *Publish folder…* (developer mode) keeps a folder per project
        in the app's config folder (`publish-dirs.json`, `publish_dirs.rs`), and Publish passes it as
        `--to`, so it beats `[publish] dir`.
- [ ] **M6.4 — LLM assist.** Validation suggestions, expression builder (Ollama / API).
- [ ] **M6.5 — Schemas per mapping.** Each mapping owns its input and output JSON Schema, chosen
      in the tool; changing one forces the Targets and Sources to be validated again (the check
      re-runs on the whole mapping and the grid flags what no longer fits: ARCHITECTURE.md,
      §Schema change management, no silent drift).
      - **Layout (decided).** `mappings/functional/<name>.fn.yaml`, and in `schemas/`, flat,
        `<name>_input.schema.json` and `<name>_output.schema.json`. It replaces
        `schemas/input|output/<name>.json` everywhere (repo, `desktop/fixtures`, schema generator,
        build, `schemas_for`, tests, ARCHITECTURE.md): one layout, no fallback.
      - Done: the layout, in `compiler/schema_files.py` (one place for names and paths).
      - Done: the `schemas:` header key (`SchemasSection`), read by the check, the build and its cache key.
      - Done: unfinished rules (`is_unfinished` / `prune_unfinished` in `transpiler/model.py`): the loader accepts them, the check warns (error + build stop when the output schema requires the field: `Issue.code = "unfinished"`, `cli/build.py::_refuse_unfinished`), the transpiler leaves them out, the grid draws them apart (`isUnfinished`).
      - **Loading.** The tool takes a JSON Schema from anywhere, copies it into `schemas/` under
        the name above, and the mapping reads that copy. Replacing a schema is the same gesture.
      - **Override.** A header key of the `.fn.yaml` (`schemas: {input: …, output: …}`) points to
        a schema elsewhere; it wins over the convention. The tool never runs anything by itself
        from it: it is for a project that manages its schemas differently (a larger repository).
      - **Scaffolding from the output schema.** After loading an output schema the tool offers to
        create the rules of all its possible objects in the mapping, with Source and Expression
        empty. An existing mapping keeps its rules: only the missing ones are added, none is
        changed or deleted (rules the schema no longer knows are reported by the check, as today).
      - **Empty rules.** A rule with no Source and no Expression is drawn with a background of its
        own (light theme: from white to a light grey; dark: a grey different from the base) and
        a warning like "ignored until a Source is defined". The transpiler skips it: the output
        has nothing for that field. For a `required` field of the output schema it is an error,
        and the build stops; otherwise a warning only.
      - **Schema status in the toolbar.** Inside a mapping it must be clear at once that the
        input and output schemas are loaded: two status buttons, *Input schema* and *Output
        schema*, each with a light, green when the schema is found and readable, red when it is
        missing or does not parse (the tooltip gives the path, or the reason). Clicking one opens
        the picker to load it, or to load another in its place.
      - Done: the status buttons in the rules toolbar (`SchemaStatus.tsx`; `schemas_status` / `schema_import` ops of `mapper serve`, `compiler/schema_files.py`): green when the schema is found and readable, red when missing or not valid JSON; a click picks a file, which is copied into `schemas/` under the mapping's name (a `schemas:` override of that kind is dropped, as it would hide the copy). The list on the left shows the mapping's name (`orders`), not the file's.
      - Done: scaffolding (`transpiler/scaffold.py`, op `scaffold` of `mapper serve`). After a new output schema is loaded the tool asks whether to create the rules it describes: a field per scalar property (type from `type` / `format`, `required` from the schema), an object per object, a loop per array of objects, nested; an existing mapping keeps its rules and gets only the missing ones, at the end of their container. Not laid out (and reported): arrays of non-objects, objects with no properties listed, names that are not valid field names. Loading a schema also checks it is one (valid, with schema keywords), not any JSON.
      - Still open: what "rule validated" becomes for rules the new schema invalidates; a picker
        among the project's own schemas (only a file from outside can be loaded so far); a
        command to lay out the rules again from the schema, outside the load.
      - Still open: loading a schema over an existing one has no confirmation (offered, not
        decided); a change to the schema files made outside the tool while the mapping is open
        is not noticed (the status and the check are read at load).
- [x] **M6.6 — Create, rename and delete mappings.** Every session so far has used the `orders` fixture:
      the tool cannot make a new `.fn.yaml` (name, id, and the schemas of M6.5; an empty file
      that loads) nor delete one (with a confirmation; what depends on it: `build/`, `generated/`,
      the golden cases). Also rename, and the unsaved-changes guard that already exists for
      switching files.
      Renaming the `.fn.yaml` renames its schema files too (`<name>_input.schema.json`,
      `<name>_output.schema.json`), and a `schemas:` override that pointed at them. The tool shows the
      mapping's name, never the file name.
      - Decided: a new mapping is `id`, `name`, `rules: []` (the loader accepts no rules; building
        it fails with "mapping '<id>' is empty"). Delete removes the `.fn.yaml`, its two schema
        files and what was derived (`build/transpiled`, `build/cache`, `generated/stubs`,
        `generated/dataclasses`), and lists them in the confirmation; the golden cases stay unless the confirmation's
        checkbox *Delete also the golden records* (shown when there are any) is ticked, and the
        compiled packages go at the next build. Rename moves the files and the golden folder; the
        file's `id` (it names the PL/SQL package) follows the name when it was the old name, and the
        dialog lets the user set it by hand.
      - Decided: a new mapping whose `tests/golden/<name>/` is not empty (cases left by one deleted
        earlier) is not created until the user chooses: use the cases for the new mapping, move the
        folder to another name (`<name>_old` suggested), delete them (confirmed), or pick another
        name for the mapping. Renaming *into* a name whose golden folder exists is still refused
        (the same choice could be offered there).
      - Done: `cli/mappings.py` (ops `mapping_create`, `mapping_removal`, `mapping_delete`,
        `mapping_rename` of `mapper serve`) and, in the left list, *+ New mapping…* and, on the
        open mapping, rename (✎) and delete (✕).
- [x] **M6.7 — In-app guide and function explorer.** A help panel in the tool: what each part
      does, the syntax of Target (`A.B`, `Lines[*]`), Source (`$`, `@`, `@label`, constants,
      selectors `list[cond]`, aliases), Expression (`value`, anchors, blocks, `Null`, bare `return`,
      lookups, truthiness) and the manual override (developer dialect: `root`, `src`, `index`,
      locals), plus Developer mode and the validation states. And an *explore* list of the
      functions, built-in and the project's own (`fn/*.fn`): signature, docstring, where each comes
      from, searchable, an entry inserting a call into the cell being edited. The function list comes
      from the registry (`compiler/function_registry.py`), so it never drifts from what the check
      and the completion know; the syntax pages are written once and also checked against the
      grammar in `ARCHITECTURE.md`.
      - Decided: **start wizard.** A modal shown at launch (and from the Help menu), with: a
        bordered box listing the recent projects (the list the *Open project…* caret already
        keeps, `pushRecent`; one click opens, a missing folder is shown greyed and can be
        removed from the list); *Open project…*; *New project…*, a guided creation (folder,
        name, target backends, i.e. the project's `mapper.toml`) which can optionally go on to
        the first mapping (the *New mapping…* flow of M6.6, with its schemas of M6.5); and
        *Help*, which opens the guide. A "don't show at startup" checkbox.
      - Decided: **the guide is two books**, as in a CHM manual, with a table of contents on the
        left, a page on the right, search over all pages, back / forward:
        *Functional user* (what a mapping is, the grid, Target / Source / Expression in
        practice, validation states, golden cases, how to read errors) and *Developer*
        (`.fn` functions, the developer dialect and manual override, backends and
        `mapper.toml`, Build / Check / Test, CI). Each book opens on a short "who is this
        for" page; the wizard offers the right one. The syntax reference and the function
        explorer above are pages of these books.
      - Decided: **pages are graphic.** Each page mixes text and screenshots of the tool with
        callouts (numbered markers, arrows, boxes around the part discussed). Pages are
        markdown files with a small directive for an annotated figure (image + list of
        callouts as coordinates and text), kept in the repo and bundled into the app; the
        callouts are data, not painted into the PNG, so a screenshot can be replaced
        without redrawing them.
      - Decided: **quick tutorial (guided tour) on the live interface.** Steps highlight a real
        element of the window (a box around it, the rest dimmed, an arrow and a short
        description, *Next* / *Back* / *Close*, "3 of 8"). Steps are data (a selector
        or an anchor id on the element, the text, the placement, the state to load), so the
        tour follows the UI; a missing element shows the step as a plain card instead of
        breaking. Two tours, as the two books: functional (project list, grid, Target / Source /
        Expression, validation states, schema status, Golden tab) and developer (Developer mode,
        the manual override, function explorer, Build / Check / Test). Started from a **?**
        button at the top right of the window (a menu: *Quick tutorial*, *Guide*, *Start
        wizard*), which keeps out of the work area; it also starts by itself the first time a
        project is created or opened (once per tour, remembered in the user's settings), asking
        before it takes over ("Take a quick tour?"). It can be closed at any time, and each page of the guide has a link to the matching tour.
      - Decided: the guide is in English only, like the rest of the application.
      - Decided: the tour is written by hand, with the tool's theme (no library).
      - Decided: **the tour is a read-only guide**: simple and linear, *Back* and *Next* only
        (plus *Close*). While it runs the normal interaction is blocked (an overlay takes the
        clicks and the keys; nothing can be edited, saved or built). Each step declares the
        state of the fixture and of the interface it needs (which mapping and rule, which tab,
        a cell open for editing, a validation shown...) and the tour loads it, going forward
        or back, so a step looks the same whenever it is reached.
      - Decided: **a fixture made for the tour** (`desktop/fixtures/tour-project`, bundled with
        the app), not the `orders` one, and the tour always runs on it, never on the user's open
        project (loading states would overwrite their work). When it starts, the fixture is
        copied to a fresh temporary folder and opened from there (loading a state may still
        write derived files), so a later "retour" starts from the original data; the copy is
        deleted when the tour ends (and stale ones at startup). The user's project is closed
        before (after the unsaved-changes guard) and reopened afterwards. It is opened as a
        *tour project*: never pushed to the recent-projects list (nor to the wizard's box), and
        the window marks it (a banner "Tutorial: read-only") so it cannot be mistaken for a
        real one.
      - Decided: *Transpile* and *Build* are shown in Developer mode only; *Save* and *Check* are
        always there (a functional user saves and checks; producing the code is the developer's).
        The tours and the guide say so.
      - Decided: screenshots are tried **automatically** first: a script drives the app on the
        tour fixture and takes them, the callouts staying as data (see above); the ones that
        do not come out well are taken by hand and kept as files, replaceable one by one.
      - Decided: the guide stays HTML (the pages the app shows); no PDF or other export.
      - Decided: **New project** (from the wizard) writes `mapper.toml` and then guides the
        user through creating one or more mappings, one after the other ("Add another mapping?").
        First the project's backend (required), chosen among the available ones, with the note
        that it can be changed later in the Project properties. Per mapping: a name (required);
        an input and an output JSON Schema (both optional, loaded as in M6.5); and,
        when an output schema is given, the question whether to pre-fill the rules from it (the
        scaffolding of M6.5). Zero mappings is allowed (the wizard can be left after the
        `mapper.toml`).
      - Decided: *New project* creates the scaffolding at once: `mapper.toml`, `schemas/`,
        `mappings/functional/`, `fn/`.
      - Decided: **the backend is the project's, one active at a time.** `[project] target`
        names the active one and only its artefacts are produced; the `[target.<name>]` tables
        of the others stay in `mapper.toml` untouched, so going back finds the configuration as
        it was (this is how `cli/config.py` already reads it: the active target must have its
        table, the others are validated and ignored). *Changing the backend* therefore only
        rewrites `target`; if the new one has no table yet, one is created with its defaults and
        the form asks for the required options. No destructive confirmation is needed; a note
        says which backend is now active and that the previous one's settings are kept. The
        wizard asks for the backend once, in *New project*, not per mapping.
      - Decided: **every field of the wizard is explained** in a line or two, under or beside
        it, for a user who knows the key concepts but is not an expert: *Mapping name* (what the
        mapping is called in the tool and on disk; it names the files, and renaming is possible
        later), *Input / Output JSON Schema* (the description of the JSON the mapping reads and
        the one it produces; the input one feeds source suggestions and checks, the output one
        lists the fields to fill; optional, can be added later), *Pre-fill the rules* (creates
        an empty rule for each field of the output schema, so only the Sources remain to be
        written), *Backend* (the language the mapping is turned into and run in, e.g. PL/SQL;
        custom ones can be changed later in the Project properties). The texts live with the
        form's data, not scattered in the components, and are the same ones the guide quotes.
      - Decided: tour accessibility. Keyboard: focus moves into the step card and returns
        afterwards, Tab stays in the card, Esc closes, arrows / Enter go on. Reduced motion
        (the system setting): no animations. Screen readers (and other assistive tools for
        blind or low-vision users): the card is a dialog that names the highlighted element, if
        that comes cheap; otherwise the tour says at its start that the experience is limited,
        and a structured approach to assistive technology is left for later (it concerns the
        whole tool, not the tour).

      - Done: the start wizard (`Wizard.tsx`, texts in `wizardTexts.ts`; ops `project_backends` /
        `project_create` of `mapper serve`, `cli/project_create.py`); the guide (`Guide.tsx`,
        `guideModel.ts`, pages in `ui/src/guide/<book>/NN-name.md`, figures with callouts as data,
        search, back / forward); the function explorer (`FunctionExplorer.tsx`, op `functions`,
        `cli/functions.py`; Insert into a Source / Expression cell or the override being edited);
        the quick tours (`Tour.tsx`, steps in `tourSteps.ts`, two tours on the tutorial project
        `desktop/fixtures/tour-project`, copied by `tour_project_prepare`, never in the recent
        list); the screenshots taken by script (`ui/shots/`, `npm run shots`, callouts found in the
        page); choosing a backend in the Project properties gives it a section of defaults
        (`withTargetDefaults`), the others' tables are kept; *Transpile* and *Build* only in
        Developer mode.
      - Decided: the wizard stays lean: it asks only for the keys a backend requires without a
        default (the others are under *More options*). A backend can propose a value for a key it
        cannot default (`Option.suggest`: plsql's error code and package prefix): the form shows
        it filled in, and `project_create` writes it, so a project loads at once. A backend also
        declares limits on its options (`minimum` / `maximum`, `min_length` / `max_length`,
        `pattern` with a `pattern_hint`, `choices` of a string: plsql's error code between -20999
        and -20000, Oracle identifiers); the check says so in the backend's words, the Project
        properties and the wizard show it under the field as it is typed, and *Create project*
        waits. At the end it offers to
        open the Project properties, saying that they are behind the *Project properties…* button.
        Done, and walked through by `ui/shots/wizard-check.mjs`.
      - Still open: the tutorial project is found next to the executable or in the checkout, but
        nothing copies it into a package yet (`bundle.active` is false); the guide pages are short and want a read by someone who uses the tool.

- [x] **M6.9 — Project functions in the tool.** Creating and editing the project's `fn/*.fn`
      without an external editor: the tool is self-contained.
      - Decided: the editor lives in the function explorer, which widens to the left when a file
        is opened; it edits a whole `.fn` file (custom functions in their own files), and a
        built-in is overridden by a copy in `fn/builtin_overrides.fn`, under a warning comment
        ("changing them might break mappings"), which can be removed (the file or one function)
        to get the built-in back; the test call runs on the Python backend, and every function
        needs code for Python (the tool, the golden cases) and for the project's backend.
      - Done: `cli/fn_files.py` (list, read, check, write — a text that does not parse is
        refused —, create, delete, `override_builtin`, `call_function`: a child interpreter with a
        10 s limit, the file as edited); ops `fn_files` / `fn_read` / `fn_check` / `fn_write` /
        `fn_create` / `fn_delete` / `fn_override` / `fn_call`; `FunctionEditor.tsx` (file select,
        New file / Delete file, Save / Ctrl+S, live issues, test call, name completion);
        *Edit…* / *Override…* / *New function…* in the explorer; e2e `functions`.
      - Done (second pass): a side rail (tab *fn*) slides the explorer and, to its left, the editor over the tool (main < editor < list, no resize of the grid); *New function…* writes a stub for Python (`raise NotImplementedError`) and the project's backend (`NOT_IMPLEMENTED('<t> stub')`), both flagged as errors until replaced (`fn_add`).
      - Done (aggregates): `max`/`min`/`sum`/`avg` are lowered to a loop on PL/SQL; a project function of the same name with `@override(plsql="...")` replaces the loop (`{items}` = the `JSON_ARRAY_T`, `{field}` = the field name, `FunctionLinker.overrides`); *Override…* gives a stub and a note on how.
      - Docs: `docs/backends/writing-a-backend.md` (a verified toy backend, the contract, options, built-ins, errors, tests, "In a nutshell"); in-app guide page *Writing functions and overrides* (developer book) with three screenshots (`functions`, `function-editor`, `function-override`); all guide screenshots retaken (they now show the side rail and the Output column).
      - Done (refinements): an issue is a link to its line; *Rename…* of a project function (`cli/fn_rename.py`: the `def`, the calls in the other functions by `ast`, and in every mapping's source / expression / guard / filter / sort key / override, quotes and attribute calls left alone; a manual rule's remembered auto code is renamed with it, so nothing goes stale; no review change); a saved, added or renamed function refreshes the Output column.
      - Still open: the generated `build/` is not refreshed by a rename (rebuild).

- [x] **M6.10 — Project-wide lookups.** A lookup table (a country → currency coding, say) that
      does not change and is useful to several mappings: it can be flagged *Project wide*, lives
      in the project instead of in one mapping, and any mapping of the project reads it as
      `@label`, as it does a local lookup today. The Lookups view lists both kinds (project-wide
      ones with the mappings that read them), and a project-wide one is edited once.
      - Decided: one file per table, `lookups/<label>.lookup.yaml` (the file name is the label,
        which never changes); embedded as a constant in each mapping's package, as a local lookup
        is (no shared package); a change sends the rules that read the table, validated or
        waiting for review, back to **To review** in every mapping, adding to `validation.notes`
        a line saying what changed (`@label changed (date): added DE = 'EUR'; …`); flagging moves
        the table into the project (after a confirmation), clearing the flag copies it into each
        mapping that reads it and removes the file; deleting a table that mappings read is
        refused, naming them; a label that clashes with a lookup, loop label or alias of a
        mapping is an error.
      - Done: `transpiler/shared_lookups.py` (load, write, uses, change description, marking,
        share / unshare / delete); `FunctionalFile.shared`, read by the transpiler, the check and
        the completion; cache key of the build; ops `lookups_shared` / `lookup_save` /
        `lookup_delete` / `lookup_share` / `lookup_unshare` in `mapper serve`; the Lookups view
        (project-wide section, readers, Save / Revert / Delete, *Project wide* flag, *+ Project
        lookup*); the guide's Lookups page. Walked through by `ui/shots/lookups-check.mjs`.
      - Still open: the Lookups screenshot of the guide does not show the project-wide section;
        the tour fixture has no project-wide table.

- [ ] **M6.8 — Golden data in the tool.** Manage the cases of `tests/golden/<mapping>/` from the
      UI, so that a functional user can check on their own machine that, given an input, the
      output is the one expected: list a mapping's cases; create, rename, delete; edit the input
      JSON, the expected output and the expected rule errors (`.input.json`, `.expected.json`,
      `.expected_errors.json`) in a JSON editor; *record* the current output as the expected one
      (after looking at it); run one case or all, with PASS / FAIL, the diff and the per-rule errors
      shown on the grid rows. The cases are the shared contract of every backend (see "Python
      backend"), so what the user writes here is also what CI runs. Running locally needs the
      Python backend (no container); the editor can come first, running second.
      - Done (first slice): the *Golden* tab of a mapping (`Golden.tsx`; `cli/golden.py`, ops
        `golden_cases` / `golden_import` / `golden_rename` / `golden_delete`). It lists the cases
        and which files each has; *Import a case…* takes one file for each role (input, expected
        output, expected errors: the last two optional), a case name proposed from the input's file
        name, and copies them into `tests/golden/<mapping>/` as `<case>.input.json`,
        `<case>.expected.json`, `<case>.expected_errors.json` (the names `discover_cases` reads;
        constants in `compiler/backends/integration.py`). Files are checked before anything is
        written (JSON; errors a list of rule ids; the case must not exist). A case can be
        renamed or deleted.
      - Done (second slice): the case editor (`GoldenEditor.tsx`, `goldenEdit.ts`; ops `golden_read` /
        `golden_write` / `golden_create`, `cli/golden.py`). *New case…* makes a case with an empty
        input; its name opens the three files in JSON editors (valid / not valid, *Format*, *Add one* /
        *Remove this file* for the optional ones, *Save* refuses what is not JSON or, for the errors,
        not a list of rule ids, *Revert*). A draft survives a visit to another view; leaving the case,
        switching mapping or closing the window with unsaved changes asks first. Walked through by
        `ui/shots/golden-check.mjs`.
      - Done (third slice): *Execute all* and the ▶ of a row run the cases on the Python backend
        (ops `golden_run` / `golden_record`, `cli/golden_run.py`; the saved mapping is compiled
        afresh, the project's target does not matter, and unsaved changes are saved first or the
        run is given up). Each case gets PASS / FAIL / *output only* (no expected output) in a
        *Result* column, a tally, and a detail panel: why it failed, the rules that reported an
        error with their cause, the diff (or the output); *Record as expected…* (after a
        confirmation) takes the output, and the rules that failed, as the expected result. A
        result is dropped when the case's files change. Walked through by
        `ui/shots/golden-run-check.mjs`.
      - Done (fourth slice): the rules that failed in a run, and that the case did not expect to fail,
        are marked on their grid rows (`golden_run` answers, for each error, the row path of the rule
        whose generated function failed, whether the case expected it, and whether the rule uses
        `regexp_*`; the marks belong to the saved file that was run and go on a save or a change
        of mapping). A failure of a rule with a regular expression because Python cannot compile the
        pattern (`re.error`), on a project whose backend is not Python, is an amber warning flagged as a possible false positive (the pattern is in the
        backend's dialect, the cases run on Python's). A loop or an object is marked as a whole.
        Walked through by `ui/shots/golden-marks-check.mjs`. Still to do: the output of a run shown
        next to the input (the *Extra mile* of M6).
      - Buttons in place, disabled until the Python backend exists: ▶ on each case (run it) and
        *▶ Execute all…* next to *Import a case…*. To do after the Python backend: running one case
        or all, how the results are shown (PASS / FAIL per case, the output diff, the per-rule
        errors on the grid rows), and what the buttons wait on while a run is going.

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

## ⬜ Release artifacts and packaging (a milestone of its own, later)

`build/compiled/*.sql` stay tracked in the repository (§Build folder: they are the deployable
artifacts and show up in review). The release will carry them too, together with the rest of
what is shipped: the desktop tool's installers, the engine, and these compiled packages, so
that someone who only installs does not need the project. Still to design: what a release
contains and its layout, how it is built and published from CI (both pipelines, forgejo and
github), versioning, and the bundled Python runtime the tool already needs (see M6.1). The
CI diff against the tracked artifacts is decided (M6.3b: fail on a difference when they are
committed, with the engine version of `mapper.toml`; nothing when they are git-ignored). It needs a
**portable Linux CLI** (the engine and its Python, no desktop) as a release artifact. Also here,
after M7: check that the GitHub pipeline behaves like the forgejo one (not checked so far).

Decided for the bundled Python (not built yet): the engine and the tool's worker need Python
>= 3.14 (a project still targets any version in `[target.python]`), and only what the tool uses
to transpile, compile and run the editor is shipped: `oracledb` (with `cryptography`, native) is in
the `dev` dependency group, since only `mapper test --integration` connects to Oracle, as are the
other CI tools. **Windows**: embed the interpreter (python.org's embeddable package, with the
engine's dependencies installed beside it by `pip install --target`, `python314._pth` edited; or
python-build-standalone, which also has free-threaded 3.14t builds: to be checked for the
embeddable package); the licence of Python goes in. **Linux**: a package depending on Python 3.14
(the dependencies with native wheels, `pyyaml`, are tied to the minor version, so "Python >= 3.14"
is not enough on its own: ship a private venv / `site-packages` built for that exact version, or
bundle the interpreter in an AppImage / Flatpak). `desktop/src-tauri/src/python.rs` already looks
for a bundled interpreter after the engine's `.venv`.

- [x] **Desktop packages, first cut** (§Packaging in ARCHITECTURE). Built entirely from Linux in
      one image (`packaging/Dockerfile`, driven by `dev_scripts/package.sh`): an **AppImage**
      (Tauri's bundler), a Windows **NSIS installer** (for the user or for every user) and a
      **portable zip** (cross-built with `cargo-xwin`, NSIS 3.13 compiled in the image), and a
      macOS **dmg** (`cargo-zigbuild` + an SDK given to the build, `rcodesign`, `libdmg-hfsplus`).
      Decided: NSIS and not an MSI (Tauri's MSI needs WiX, which runs only on Windows); macOS is
      unofficial (an SDK taken from Xcode, an ad-hoc or self-signed signature, no notarisation, so
      Gatekeeper warns at the first launch), arm64 only; the Python is python-build-standalone,
      the engine's dependencies are the wheels of each target (`uv pip install --python-platform`).
      The window title is `J2JME v<Cargo.toml version> (<short commit id>)`. CI: `release.yml` in
      both pipelines: a tag `v*` makes a draft release; the tag's version replaces the one in
      Cargo.toml, `-suffix` marks a pre-release, the notes come from CHANGELOG.md (the version's
      section, else Unreleased, else none) (`packaging/release.py`, tested in
      `tests/track1/release`; a `1.2.3-beta1` version builds the Linux and Windows packages). Verified: the
      AppImage and the two Windows packages are built here, the AppImage starts under Xvfb and its
      Python runs the engine; the dmg tooling (signing, volume) runs on a stand-in `.app`.
      **Not verified**: the Windows installer and portable zip on Windows, the macOS cross-build
      (no SDK was at hand), the dmg on a Mac, `J2JME_PKG_COPY=1` (CI on dind) and `release.yml`.

---

## ✅ More built-ins (done; `decode` left out)

`replace`, `regexp_replace`, `regexp_group`, `remove_prefix`, `format_decimal`, `to_number`, `to_string`,
`to_utc`, `rfc3339_normalize`, and `round` with optional digits: reference implementations in
`compiler/builtins.py` (what the Python backend runs), PL/SQL renderings in
`compiler/backends/plsql/builtins.py` (inline templates, and the functions package for the ones that
are statements). Decided: lowercase names; `split_nth` stays (no `split_part`); regular expressions are
in the dialect of the chosen backend, the project's responsibility (a documented exception to
backend independence). **The PL/SQL renderings were checked as generated text only, not against an Oracle
instance.** The golden mapping `mappings/builtins_text.map.py` and its cases
(`tests/golden/builtins_text/`: every function, with a value read from the document, a typed
expression and a constant; a failing `to_number`) are what the PL/SQL integration tests run in CI
(`mapper test --integration`, both pipelines, nothing to configure) and what the Python backend runs
offline in track 1: a difference between the two shows up there first. The conversions are
idempotent whatever the type given: `to_string` / `to_number` of a value read from the document
go, as the JSON element, to the functions package, which looks at what it is (number, text,
boolean, list, object); of a typed expression, they are rendered by its type (`to_string_of_kind`,
`to_number_of_kind`). Known to differ: an empty string is NULL in Oracle, so the cases avoid it;
The golden cases were run against a real Oracle (`mapper test --integration` with the local container
runtime) and pass; what was found that way: the functions package must qualify `STANDARD.TO_NUMBER`
(it declares its own `to_number`), a library function that calls another is deployed with it, and
`TO_CHAR(.5, 'TM9')` writes `.5` (the number text uses an `FM` format with a `0` before the dot instead).
Still differing, and avoided by the cases: an empty string is NULL in Oracle; a `\uXXXX` escape in a JSON
string is not decoded by `to_string`. Left out for the moment, decided: `decode(expr, s1, r1, ..., default)` (Oracle's switch, where two NULLs
match); `lookup` and `if_else` cover the rest. The limits of `to_number` (a plain decimal, up to 20 digits
before the dot and 18 after; no exponent, separators or decimal comma) are in its description, which the
explorer and the guide show.

## 🟨 Python backend (first slice done)

A backend of its own (`compiler/backends/python/`, `[project] target = "python"`), lightweight:
it compiles a mapping to a Python module (rule functions, `map_<id>` / `map_<id>_safe`
twins, the same error report) and needs no database or container. It is what makes the
desktop tool's preview and error highlighting possible, and it is a second implementation that
tests the first.

**Done (first slice).** `compiler/backends/python/`: a mapping becomes `map_<id>.py` with
`map_<id>(source)` (raises `MappingError` when rules failed) and `map_<id>_safe(source)` (gives
`(output, rule errors)`), next to a shared `j2jme_runtime.py` that holds the run-time rules and the
built-ins (the reference implementations of `compiler/builtins.py`, `parse_date` with the Oracle
format tokens); a generated module imports nothing of the engine. The rules settled in the runtime:
a path through the input gives null where something is missing (never an error); arithmetic on a
null is null and an ordering comparison with a null is false (as in SQL); a failing rule is
reported once under its name and leaves its field out, the others go on; a bare `return` leaves a
field out, `return Null` or a null value puts a null; a whole number is written as an integer
(5, not 5.0). The four golden mappings and all their cases pass on it (track 1, no container); `mapper
build` / `check` / `test --integration` work with `[project] target = "python"`
(`Backend.artifact_suffix`). Option `[target.python] python` (the interpreter version) is
declared and not used yet. Project `fn/*.fn` functions: the module carries the ones a mapping calls (their Python
code, or `@override(python="...")`); one with neither (a stub written out for another target) raises
`MissingImplementation`, and the unit says which rules call it (`PythonUnit.unavailable`): the golden run
reports those rules as not run (amber row, case NOT RUN, not recordable), not as failures. The PL/SQL
backend now links `@override(plsql=...)` of project functions (it did not before) and stops the build
when a project function has none. Still to do, as listed below: `@parallel`, the target interpreter handling, the conformance run against PL/SQL, and the
points where the two could differ, once written down (rounding, null against empty string, dates).

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
      project's, not the engine's own (which the tool runs on 3.14 to compile). So the target
      declares it in `[target.python]` (a version, and whether it is free-threaded, e.g.
      `python = "3.14t"`), and the backend emits code for that interpreter: syntax and library
      features it has, and `@parallel` handled accordingly. The generated module must not import the
      engine.
- [x] `@parallel(degree=N)` for real, unlike PL/SQL (where it only yields a SQL-callable
      wrapper): the elements of the loop are mapped by up to N threads.
      Decided: `[target.python] parallel = "thread" | "none"` (default `thread`); `thread` is a real
      speed-up on a free-threaded Python (the project's `python = "3.14t"`), and on one with the
      GIL it still runs in threads, correct but not faster, and the build says so (a warning from
      `Backend.unit_warnings`). The engine and the tool's worker run on 3.14; a project targets any
      version. Whatever the strategy, the result equals the sequential one: results in element
      order (`pool.map`), and each call keeps its own errors, merged in element order, so "first
      failure of a rule wins" stays deterministic. Done: `_pmap` in the runtime, the loop rewrite in
      `codegen.py` (a loop that only appends one `@parallel` rule's value, with its filters),
      tests (also run on 3.14t). Still open: `process` (`ProcessPoolExecutor`: the generated
      modules are loaded by path, so the functions would have to be importable by the workers); a
      loop that does more than append one `@parallel` rule's value (fused loops) stays sequential.
- [ ] Then the desktop preview (Extra mile in M6).
- [ ] Then the golden runs in the tool (M6.8): the disabled ▶ buttons of the *Golden* tab (one
      case, and *Execute all…*) run the cases on this backend, and the tool shows the results
      (PASS / FAIL per case, the output diff, the per-rule errors on the grid rows). How the
      results are shown is still to be designed.
- [x] The Output column (M6.11): the grid shows, per rule, the value it gave on a golden case
      (compared with `expected.json`: red where it differs) or on any JSON file (shown only).
      Decided: one selector (`OutputInputButton`, with a light like the schema buttons) beside the
      schema buttons; the file last used is kept per project and mapping in the app's config
      folder (`input-files.json`), not in the project (a path differs per user). Done:
      `cli/golden_run.py` (`output_values`, `run_input`), op `input_run`, Tauri commands
      `input_file_get/set`, `ruleOutput.ts`, `shots/output-check.mjs`. A loop inside a loop gives a list of lists.

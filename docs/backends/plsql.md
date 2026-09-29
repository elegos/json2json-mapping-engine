# PL/SQL backend

The backend selected by `[project] target = "plsql"` (`compiler/backends/plsql/`).
It is one implementation of the target-agnostic `Backend` interface described in
[ARCHITECTURE.md](../ARCHITECTURE.md), §Target backends. This document is the reference
for what is specific to PL/SQL: configuration, the generated artifact, the variations
that a mapping can trigger (such as `@parallel`), and the known gaps.

Status: everything below is covered by the offline tests. The PL/SQL text has been run
against a real Oracle only through the integration tests (golden cases); features marked
*not run against Oracle* have not.

## Modules

| Module | Role |
|---|---|
| `backend.py` | `PlsqlBackend`: configuration, `compile_module`, cache (de)serialization, assembly, artifact path |
| `codegen.py` | Annotated AST → PL/SQL for one mapping (`PlsqlUnit`) |
| `package.py` | The units of a project → one package spec + body |
| `builtins.py` | PL/SQL templates (and Python reference implementations) of the built-in functions |

## Configuration (`[target.plsql]` in `mapper.toml`)

| Key | Required | Default | Effect today |
|---|---|---|---|
| `package` | yes | — | Name of the single generated package; the artifact is `build/compiled/<package lowercase>.sql` |
| `error_code` | yes | — | Code passed to `RAISE_APPLICATION_ERROR` by the raising entry point |
| `export_rule_functions` | no | `false` | `true` also lists every `fn_<mapping>_<rule>` in the package spec |
| `schema` | yes | — | Owner: packages are created as `<schema>.<package>`. The integration harness creates the schema (no login) and reads compile errors from it |
| `fn_package` | no | — | Second package holding the rule functions (see below) |
| `fn_prefix` / `fn_suffix` | no | `""` | Decorate entry points and rule functions (see below) |

### Names

All names come from `naming.py`:

| Object | Name |
|---|---|
| Entry points | `<fn_prefix>map_<id>[_safe\|_fn]<fn_suffix>` (the suffix always last) |
| Rule functions | `<fn_prefix>fn_<id>_<rule><fn_suffix>` |
| Packages | `[<schema>.]<package>` and, when set, `[<schema>.]<fn_package>` |

`fn_prefix`, `fn_suffix`, `schema`, `package` and `fn_package` must be plain Oracle
identifier parts (letters, digits, `_ $ #`; a prefix or name starts with a letter);
anything else is a build error, as is `fn_package` equal to `package`.

### `fn_package`

Without it, rule functions live in the main package (private unless
`export_rule_functions`). With it they move to that package, emitted **first** in
the artifact; it always lists them in its spec (the main body calls them as
`<fn_package>.fn_...`), so `export_rule_functions` has no effect. The main package
holds only the entry points.

The integration harness connects as `ADMIN`, creates `<schema>` if missing, deploys
and calls `<schema>.<package>.<entry point>`. Not run against a real Oracle yet.

## The generated artifact

One file per project: `CREATE OR REPLACE PACKAGE <package>` (spec) and
`PACKAGE BODY <package>`, each terminated with `/`.

- Mappings are sorted by id, so the output does not depend on file order.
- Duplicate mapping ids are a build error (the id is the namespace).
- Every generated identifier must fit Oracle's 128 bytes; checked at compile time.
- Trade-off: any mapping change recompiles the whole package body on deploy.

### Subprograms per mapping

| Name | Kind | In the spec | When |
|---|---|---|---|
| `map_<id>(p_src IN CLOB, p_out OUT CLOB)` | procedure | always | always; raises if any rule failed |
| `map_<id>_safe(p_src IN CLOB, p_out OUT CLOB, p_err OUT CLOB)` | procedure | always | always; never raises, returns errors in `p_err` |
| `map_<id>_fn(p_src IN CLOB) RETURN CLOB PARALLEL_ENABLE` | function | always | only if a rule function declares `@parallel` |
| `fn_<id>_<rule>(...)` | function | only with `export_rule_functions` (always, in `fn_package`, when set) | one per rule function |

Rule functions come first in the body (PL/SQL needs a name declared before use), then
the entry points.

### Data handling

- `CLOB` appears only at the boundary. `p_src` is parsed once into a `JSON_OBJECT_T`,
  the output is serialized once at the end. Everything in between is native
  `JSON_OBJECT_T` / `JSON_ARRAY_T`; no `JSON_OBJECT(...)` text round trips.
- Composite values are built with `put()` sequences; output arrays are accumulated in
  one `JSON_ARRAY_T` per list field and put on the output object once.
- Type mapping (declarations vs. function `RETURN` / parameter types, which must be
  unconstrained): `str → VARCHAR2`, `int` and `number → NUMBER`, `bool → BOOLEAN`,
  `date → DATE`, `datetime → TIMESTAMP`. Local `VARCHAR2` variables are declared
  `VARCHAR2(4000 CHAR)`; sizing from JSON Schema `maxLength` is not wired up.
- Omitting a field (bare `return`) is an `OUT BOOLEAN p_omitted` parameter on every rule
  function, checked at the call site; no shared exception.

### Errors

Behaviour common to all targets is in ARCHITECTURE.md, §Runtime error semantics. What is
PL/SQL-specific:

- Failures are accumulated per rule id in an associative array; the first failure of a
  rule wins.
- `map_<id>` raises once at the end with `RAISE_APPLICATION_ERROR(<error_code>, <json>)`.
  The payload holds at most 20 entries and is cut by a byte budget under Oracle's message
  limit, with `total_errors` / `shown` telling the caller what was left out. Read it with
  `DBMS_UTILITY.FORMAT_ERROR_STACK`, not `SQLERRM` (capped at 512 bytes).
- `map_<id>_safe` returns the same entries, uncapped, as a JSON array in `p_err`.

### Built-in functions

`coalesce`, `round`, `trunc`, `concat`, `if_else`, `split_first`, `split_nth`, `lookup`,
`parse_date`, `count`. Each has a PL/SQL template in `builtins.py` (and a Python reference
used by the tests). A project function can override one, and `@override(plsql="...")`
supplies a verbatim implementation (§Function library).

## Variations

Some mapping features change what the backend emits. All of them are opt-in from the
mapping; a mapping without them produces exactly the base artifact above.

### `@parallel(degree=N)` → SQL-callable wrapper

Trigger: at least one rule function of the mapping has `@parallel(degree=N)` or
`@parallel(N)` (from a `.fn.yaml` loop key `parallel: N`).

Output: the extra function `map_<id>_fn`, declared in the spec, whose body calls
`map_<id>` and returns its `p_out`. A comment above it lists the declaring rule functions
with their degrees and a sample query.

What it does and does not do:

- `PARALLEL_ENABLE` only matters for a function called from a SQL statement. Oracle may
  then run it in parallel-query slaves, one document per call. It cannot parallelize a
  PL/SQL loop, which is why the loop-level `@parallel` does not split a single document.
- The procedures are not SQL-callable (`OUT` parameters); that is the reason for the
  wrapper.
- The degree is the caller's: `SELECT /*+ PARALLEL(4) */ pkg.map_x_fn(doc) FROM staging`.
  The declared degrees appear only in the comment; the highest one is used in the sample.
  Oracle may still ignore the hint.
- A failing document fails the whole statement (the wrapper calls the raising twin). To
  collect errors instead, call `map_<id>_safe` from PL/SQL.
- Fusion: rules fused into one loop must agree on the degree (see ARCHITECTURE.md,
  §`@parallel(degree=N)`); `optimizer.parallel_conflict = "max" | "min"` only avoids the
  build error today, it does not choose a degree.
- *Not run against Oracle.*

Considered and not implemented:

| Mechanism | Why not |
|---|---|
| Pipelined table function `PARALLEL_ENABLE (PARTITION BY ANY)` over `JSON_TABLE` of an array (parallelism inside a document) | Needs schema-level SQL types, a different rule-function shape (elements passed as text), order restoration, and the optimizer decides whether it is really parallel |
| `DBMS_PARALLEL_EXECUTE` | Chunks a *table* and runs scheduler jobs in separate sessions: needs `CREATE JOB`, permanent staging tables, no return values. Sensible for batches of many documents, not for one CLOB |

### `export_rule_functions`

Assembly-time only: the rule functions are generated identically either way; the flag
decides whether their names also go in the spec (external reuse, unit-testing one rule).

### Loop fusion and filters

Fusion runs before the backend (it is target-agnostic); the backend sees the fused loop.
A loop over a filtered iteration with `@index` is lowered to a per-branch counter.
Disabling `[optimizer] loop_fusion` gives one PL/SQL `FOR` per source loop.

### Sorting

`sorted(..., key="field")` is an in-place insertion sort on the `JSON_ARRAY_T`, comparing
with `JSON_ELEMENT_T.compare_to()` (numbers and strings alike). It stays in native
PL/SQL, without a SQL `ORDER BY`.

## Known gaps

- Schema/package wiring (`schema`, `fn_package`) is covered by offline tests only; no run on a real Oracle.
- No `maxLength`-driven sizing of `VARCHAR2` locals.
- One package per project; a grouping key for several packages is a backlog item.
- A mapping whose root output is an array is not supported (the output accumulator is
  always a `JSON_OBJECT_T`).
- `@parallel` scaffolding is document-level only and not run against Oracle.
- The integration harness (`cli/track2.py`, `[test]` settings) is the PL/SQL one; when
  more backends exist, integration tests will be per target.

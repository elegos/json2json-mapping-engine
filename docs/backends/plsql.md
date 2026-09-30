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
| `naming.py` | Every generated name, derived from the config |
| `package.py` | The units of a project → one package (spec + body) per mapping, plus the optional index package |
| `builtins.py` | PL/SQL templates (and Python reference implementations) of the built-in functions |

## Configuration (`[target.plsql]` in `mapper.toml`)

| Key | Required | Default | Effect |
|---|---|---|---|
| `schema` | yes | — | Owner: packages are created as `<schema>.<package>`. The integration harness creates the schema (no login) and reads compile errors from it |
| `error_code` | yes | — | Code passed to `RAISE_APPLICATION_ERROR` by the raising entry point |
| `[target.plsql.mapping_packages]` | one of the two | — | Explicit table: `<mapping id> = "PACKAGE"` |
| `mapping_package_prefix` / `mapping_package_suffix` | one of the two | — | Generated: `<prefix><MAPPING ID><suffix>`, upper-cased; at least one non-empty |
| `mapping_index_package` | no | — | Extra package forwarding every entry point to the mapping's package |
| `functions_package` | no | `J2JME_FUNCTIONS` | Shared package of the built-ins that are not 1:1 with PL/SQL (see below) |
| `export_rule_functions` | no | `false` | `true` also lists every `fn_<mapping>_<rule>` in its package spec |
| `fn_prefix` / `fn_suffix` | no | `""` | Decorate entry points and rule functions (see below) |

How mappings map to packages must be stated: with neither the table nor a prefix/suffix
the config is rejected, and so it is with both. With the table, every mapping needs an entry
and every entry must name an existing mapping; two mappings cannot share a package. In the
table form, TOML requires the `[target.plsql.mapping_packages]` header after the other
`[target.plsql]` keys.

### Names

All names come from `naming.py`:

| Object | Name |
|---|---|
| Entry points | `<fn_prefix>map_<id>[_safe\|_fn]<fn_suffix>` (the suffix always last) |
| Rule functions | `<fn_prefix>fn_<id>_<rule><fn_suffix>` |
| Mapping package | from the table, or `<mapping_package_prefix><ID><mapping_package_suffix>` |
| Index package | `mapping_index_package` |
| Functions package | `functions_package` (default `J2JME_FUNCTIONS`); its functions are not decorated by `fn_prefix` / `fn_suffix` |
| Qualified | `[<schema>.]<package>` |

All configured parts must be plain Oracle identifier parts (letters, digits, `_ $ #`; a
prefix or name starts with a letter); anything else is a build error, as is a generated
name over 128 bytes, or the index package equal to a mapping's package.

### The functions package

Most built-ins are inline PL/SQL expressions. Those that have no 1:1 PL/SQL function
(`split_first`, `split_nth`, `lookup`) are functions of the shared `functions_package`
instead, so their logic exists once instead of being pasted into every call site. Their
bodies are the same expressions the inline templates used (`builtins.py`, `LIBRARY_FUNCTIONS`).

- The package is generated only when at least one mapping calls one of them, and holds only
  the functions used. Deployed first: the mapping packages call it.
- `if_else` stays inline: a function would evaluate both branches, the `CASE` does not.
  `concat`, `count` and the 1:1 ones (`coalesce`, `round`, `trunc`, `parse_date`) are inline too.
- A project function of the same name still overrides the built-in and is rendered as such.
- Project functions (`fn/`) are meant to live here as well, once the `fn/` loader exists.

### The index package

Callers that want a single, stable name set `mapping_index_package`. It declares each
entry point with exactly the signature of the mapping's package and only calls it
(`RETURN` for the `_fn` wrapper, which keeps `PARALLEL_ENABLE`). It is deployed after the
mapping packages. It depends on their specs, not their bodies, so redeploying one mapping
does not invalidate it. The integration harness calls through it when it exists, else
through the mapping's own package.

## The generated artifact

One file per package in `build/compiled/`, named `<package lowercase>.sql`: `CREATE OR
REPLACE PACKAGE <package>` (spec) and `PACKAGE BODY <package>`, each terminated with `/`.
`mapper build` removes `.sql` files that are no longer produced; `mapper check` also
reports missing and stale files.

- A mapping's package holds its entry points and its rule functions; nothing is shared
  between mappings.
- Mappings are sorted by id, so the output does not depend on file order.
- Duplicate mapping ids are a build error (the id is the namespace).
- Every generated identifier must fit Oracle's 128 bytes; checked at compile time.
- Changing one mapping changes and recompiles only its own package.

### Subprograms per mapping

| Name | Kind | In the spec | When |
|---|---|---|---|
| `map_<id>(p_src IN CLOB, p_out OUT CLOB)` | procedure | always | always; raises if any rule failed |
| `map_<id>_safe(p_src IN CLOB, p_out OUT CLOB, p_err OUT CLOB)` | procedure | always | always; never raises, returns errors in `p_err` |
| `map_<id>_fn(p_src IN CLOB) RETURN CLOB PARALLEL_ENABLE` | function | always | only if a rule function declares `@parallel` |
| `fn_<id>_<rule>(...)` | function | only with `export_rule_functions` | one per rule function |

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
- Nested members are isolated (ARCHITECTURE.md, §Nested output). A rule function that
  calls other rule functions takes `p__errors IN OUT NOCOPY JSON_OBJECT_T` (before
  `p_omitted`); each such call is wrapped in `BEGIN … EXCEPTION WHEN OTHERS`, which puts
  `SQLERRM` under the callee's rule id (first wins) and marks the member omitted. The
  entry points create the object (`v_rule_errors`), pass it to the functions that take
  it and fold its entries into `v_errors` before reporting. Leaf rule functions keep
  the plain signature.

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
- Exercised on Oracle by the `orders` golden cases: the harness calls `map_orders_fn` from
  a `SELECT … FROM dual` and compares with `_safe`. The degree itself is not observable there.

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

- Only one mapping (`orders`) has golden cases (incl. `failed_member`, the isolated nested member); prefix/suffix are covered by offline tests only.
- No `maxLength`-driven sizing of `VARCHAR2` locals.
- Project functions (`fn/`) do not yet go into the functions package: the loader does not exist.
- A mapping whose root output is an array is not supported (the output accumulator is
  always a `JSON_OBJECT_T`).
- `@parallel` scaffolding is document-level only.
- The integration harness (`cli/track2.py`, `[test]` settings) is the PL/SQL one; when
  more backends exist, integration tests will be per target.

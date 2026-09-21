# json2json-mapper — Architecture

> First draft. Based on design discussion; subject to revision.

## Overview

`json2json-mapper` is a **compiled mapping engine** for JSON-to-JSON transformations.
Developers write mapping rules in a restricted, hard-typed subset of Python syntax.
A compiler translates those rules to native code in the target runtime (initially PL/SQL).
There is no DSL interpretation at runtime — the output is ordinary compiled code.

---

## Design principles

- **Python as syntax, not runtime.** The `.map` files are valid Python that is never executed as Python. The Python AST is the compiler frontend.
- **Hard-typed.** Every variable, parameter, and return value carries an explicit type annotation. Untyped code is a compile error.
- **No stdlib, no classes, no imports.** Only Python syntax constructs are allowed. The sole permitted import (`from __mapping__ import ...`) is an IDE stub and is stripped by the compiler.
- **JSON Schema as single source of truth.** Input and output types are derived from JSON Schemas, not hand-written. Dataclasses and stubs are generated artifacts.
- **Zero runtime overhead.** Mapping logic is emitted as native functions in the target language. No JSON parsing of mapping rules at runtime.

---

## Language subset

### Permitted constructs

| Construct | Notes |
|---|---|
| `def` + type annotations | functions only, no methods |
| `@dataclass` | output type definitions only; no methods inside |
| `@decorator` | `@override`, `@parallel`, `@dataclass` |
| `if` / `elif` / `else` | statement and expression form |
| `for x in <expr>:` | iteration over JSON arrays |
| `continue` | skip current iteration (→ `CONTINUE WHEN` in PL/SQL) |
| `return` | bare `return` = omit field entirely (no emission) |
| `return Null` | emit field explicitly as JSON null (`"field": null`) |
| `return <expr>` | emit field with value |
| Local variables | `x = <expr>` inside a function or expression block; names are mangled by the compiler to avoid collision with loop variables in the wider scope |
| Operators | `+ - * / // % == != < > <= >= and or not` |
| Literals | `str`, `int`, `float`, `bool`, `None` |
| Attribute access | `root.a.b.c` → JSON path `$srcroot.a.b.c` |
| Type union | `T \| None` for nullable fields; `T \| Null` for explicitly-nullable fields |

### Blocked constructs

`class` (without `@dataclass`), `import` (other than `__mapping__`), `lambda`, `yield`,
`async`/`await`, `*args`, `**kwargs`, `global`, `nonlocal`, `exec`, `eval`,
`try`/`except`, `with`.

Local variable assignments (`x = ...`) are **permitted inside `.fn` function bodies**
and inside multi-line `.fn.yaml` expression blocks, but are **blocked in `.map` file
scope** outside of per-field function bodies. This keeps every field assignment in
`.map` files reducible to a single traceable expression, which is required for
round-trip import and loop fusion analysis.

### Type system

| DSL type | PL/SQL type | JSON Schema type |
|---|---|---|
| `str` | `VARCHAR2(4000)` | `string` |
| `int` | `NUMBER(38,0)` | `integer` |
| `number` | `NUMBER` | `number` |
| `date` | `DATE` | `string` + `format: date` |
| `datetime` | `TIMESTAMP` | `string` + `format: date-time` |
| `bool` | `BOOLEAN` | `boolean` |
| `T \| None` | nullable equivalent | `null` union or `nullable: true` |
| `Null` | explicit JSON null sentinel (see Return semantics) | `null` |
| `list[T]` | `JSON_ARRAY_T` | `array` |
| `@dataclass` | `JSON_OBJECT_T` | `object` |

Complex JSON Schema constructs (`oneOf`, `anyOf`, `patternProperties`) that cannot be
represented in this type system are emitted as opaque `JsonObj`; structural validation
for those is delegated to the post-mapping JSON Schema validator (out of scope for the engine).

### Return semantics and field emission

Three distinct return forms control how a field is emitted:

| Form | Field in output | JSON value |
|---|---|---|
| `return <expr>` | present | computed value |
| `return Null` | present | `null` |
| `return` (bare) | absent | *(not emitted)* |

`Null` is a DSL keyword, not Python's `None`. The validator treats `return Null` as
a typed sentinel and rejects it if the declared return type does not include `Null`.
A bare `return` is always valid regardless of return type — it signals that this
invocation produces no contribution to the output, equivalent to a field-level skip.

If the field designated as the loop's primary key returns bare, the entire output
record for that iteration is dropped (`primary_key` is declared in the loop header
of the `.fn.yaml`).

In PL/SQL the Code Generator emits a two-flag guard per field:

```plsql
IF NOT v_r42_skip THEN
    IF v_r42_is_null THEN
        v_out_obj.put('amount', CAST(NULL AS NUMBER));
    ELSE
        v_out_obj.put('amount', v_r42_result);
    END IF;
END IF;
```

---

## Context variables

Inside `.map` files, three magic names are available. They are not Python objects at
runtime — the compiler resolves attribute access on them to JSON path expressions.

| Name | Meaning | Scope |
|---|---|---|
| `root` | Root source document (`$srcroot`) | everywhere |
| `src` | Current source element inside a loop | inside `for` body |
| `out` | Current output element being built | inside `for` body or function body |

Inside a `for` loop, `srcroot` can be locally re-bound for path shorthand:

```python
for item in root.source.orders:
    # root is still the document root
    # src aliases item implicitly inside the loop body
    ...
```

---

## Output type contract (`@dataclass`)

Output types are declared with `@dataclass`. The compiler enforces:

1. Every `required` field in the corresponding JSON Schema is assigned before `return`.
2. Assignments to `out.<field>` must match the declared field type.
3. Assignment to an undeclared field is a compile error.

```python
@dataclass
class OrderLine:
    order_id:     int
    product_code: str
    unit_price:   number
    shipped_at:   date | None    # optional
```

---

## Input type contract (stubs)

Input schemas generate `.pyi` stub files. The compiler uses them for read-access
type checking only — accessing a non-existent field is a compile error; accessing
a subset of fields is always valid.

```
schemas/input/order_event.json   →   generated/stubs/order_event.pyi
schemas/output/order_line.json   →   generated/dataclasses/order_line.py
```

Generated files are checked into the repository and must not be edited manually.
The CI regenerates them from schemas and fails if the checked-in files are out of sync.

### Schema change management

When an input JSON Schema changes, the compiler regenerates the affected `.pyi` stubs
and compares them against the checked-in versions. If any `.fn.yaml` rule references a
path that no longer exists or has a changed type, the build **fails hard** — there is no
auto-approval path. The developer must explicitly review the affected rules, update any
`code_override` or `expression` fields that are now invalid, and re-commit before the
build is unblocked.

The tool flags affected rows in the grid with a schema-conflict indicator so the
developer can filter and resolve them before pushing. Silent schema drift is not
permitted.

---

## Custom functions

Custom functions are declared in `.fn` files using the same language subset.
They operate only on typed scalar parameters — no access to `root`, `src`, or `out`.

```python
# functions/string_fns.fn
from __mapping__ import override

@override(plsql="REGEXP_SUBSTR({s}, '[^ ]+', 1, {n})")
def split_part(s: str, n: int) -> str | None:
    parts = s.split()
    return parts[n - 1] if n <= len(parts) else None
```

**Override priority per target:**
1. `@override(target=...)` present → use verbatim
2. DSL body present → compile through pipeline
3. Neither → compile error: no implementation for this target

The Python body in a `.fn` file is the only part of the system that is also executable
as real Python. It serves as the reference implementation and can be tested with standard
Python test tooling without any Oracle dependency.

Functions are compiled to the `MAPPING_FUNCTIONS` package (PL/SQL target).
The compiler resolves function signatures from `.fn` files before compiling `.map` files.

---

## Decorators

### `@override(target="...")`

Provides a target-language verbatim implementation for a function.
Placeholders `{param_name}` are substituted with the compiled argument expressions.

```python
@override(plsql="TO_DATE({s}, {fmt})")
def parse_date(s: str, fmt: str) -> date: ...
```

### `@parallel(degree=N)`

Declares that a mapping function should execute with parallel degree `N`.
The backend decides the mechanism:

| Target | Mechanism |
|---|---|
| PL/SQL | `DBMS_PARALLEL_EXECUTE` with chunk orchestration |
| PL/SQL pipelined | `PARALLEL_ENABLE (PARTITION BY ANY)` |

The mapping file declares intent; the backend emits the appropriate scaffolding.

---

## Compiler pipeline

```
Phase 1 — Function library
  Input:  .fn files + @override annotations
  Steps:  parse Python AST → validate subset → type-check →
          resolve overrides per target → emit MAPPING_FUNCTIONS package
  Output: symbol table (function name → param types, return type)

Phase 2 — Mapping rules
  Input:  .map files + generated stubs + generated dataclasses + symbol table
  Steps:  parse Python AST → validate subset → scope resolution →
          type-check (reads vs. stubs, writes vs. dataclasses) →
          emit MAPPING_RULES package
  Output: one procedure per mapping function
          signature: map_<id>(p_src IN CLOB, p_out OUT CLOB)
```

### Compiler components

| Component | Responsibility |
|---|---|
| **Validator** (`ast.NodeVisitor`) | Block forbidden Python constructs and imports |
| **Scope Resolver** | Build `root` / `src` / `out` context chain per nested loop |
| **Type Checker** | Annotated AST: validate reads against stubs, writes against dataclasses |
| **Function Linker** | Resolve custom function calls to signatures from Phase 1 symbol table |
| **Loop Fusion Optimizer** | Build dependency DAG across all field functions; collapse loops over the same source array; topologically sort to resolve accumulation ordering |
| **Code Generator** | Annotated AST → target language source (one backend per target) |
| **Schema Generator** | JSON Schema → `.pyi` stubs and `@dataclass` files |

The Code Generator is the only target-specific component. All phases before it are
language-agnostic and reusable across backends.

### Loop Fusion Optimizer

The optimizer operates on the full set of field functions after type-checking, before
code generation. It builds a directed acyclic graph (DAG) where:

- Each node is a field function with its source scope (which array it iterates over).
- Each edge represents a data dependency: field B reads a value produced by field A
  (e.g. an accumulation over an inner array consumed in the outer loop).

From the DAG the optimizer derives the minimum set of loops and their emission order:

```
Fields on $.orders[*]:        A, B, C  → fused into 1 loop
Fields on $.orders[*].items[*]: D, E   → nested loop inside the above
Field F on $.orders[*] depends on sum(D) → D's loop is emitted first as a pre-pass
```

The optimizer emits loop groups to the Code Generator in topological order.
Cycles in the DAG (circular dependencies between fields) are a compile error.

---

## Generated artifact (PL/SQL)

Each mapping function compiles to a single stored procedure in the `MAPPING_RULES` package:

```plsql
PROCEDURE map_event_48_1 (
    p_src IN  CLOB,
    p_out OUT CLOB
) AS
    v_srcroot  JSON_OBJECT_T := JSON_OBJECT_T(p_src);
    v_out_obj  JSON_OBJECT_T := JSON_OBJECT_T();
    -- local variable declarations emitted by WrapperGen
BEGIN
    -- loop and assignment blocks emitted by LambdaEmitter / StmtEmitter
    p_out := v_out_obj.TO_CLOB();
END;
```

The mapping engine calls `MAPPING_RULES.map_<id>(p_src, p_out)` — no DSL
interpretation, no JSON rule parsing at runtime.

---

## Repository layout (proposed)

```
json2json-mapper/
├── compiler/              ← compiler source (Python)
│   ├── validator.py
│   ├── scope_resolver.py
│   ├── type_checker.py
│   ├── function_linker.py
│   ├── schema_generator.py
│   └── backends/
│       └── plsql/
│           ├── codegen.py
│           └── primitives.py   ← built-in intrinsics for PL/SQL
├── runtime/               ← IDE stubs for __mapping__ module
│   └── __mapping__.pyi
├── schemas/
│   ├── input/             ← input JSON Schemas (source of truth)
│   └── output/            ← output JSON Schemas (source of truth)
├── generated/             ← checked-in, never edited manually
│   ├── stubs/             ← .pyi files from input schemas
│   └── dataclasses/       ← .py @dataclass files from output schemas
├── functions/             ← .fn custom function files
├── mappings/              ← .map mapping rule files
└── docs/
    └── ARCHITECTURE.md
```

---

## Functional Layer

The compiler pipeline accepts `.map` files written by developers. The Functional Layer sits
above it: functional teams author mapping rules in a familiar spreadsheet-like environment;
a transpiler translates those rules into `.map` files that feed the existing compiler.

The overall extended pipeline is:

```
Functional file (.fn.yaml)
  → Transpiler → .map file (Python subset)
    → AST compiler → PL/SQL
```

`.map` files remain generated artifacts — the `.fn.yaml` is the single source of truth.

---

### Tool

A fat-client desktop application built with **Tauri** (Rust backend, web frontend).
The functional team sees a spreadsheet grid; the tool writes `.fn.yaml` files in the
background. The functional team never interacts with YAML directly.

The web frontend handles spreadsheet behaviour (keyboard navigation, copy/paste, undo)
via a standard grid component (e.g. AG Grid). The Rust backend handles: YAML parsing,
schema-aware validation, transpilation, and version control.

An LLM is embedded in the tool for two purposes:

1. **Validation suggestions** — when a rule fails to compile, the LLM proposes a corrected
   expression in natural language before showing raw errors.
2. **Expression builder** — the LLM translates the free-text `description` field into
   a candidate expression for the `transform` field.

**LLM backend options** (user-configurable):

| Option | Privacy | Cost |
|---|---|---|
| Anthropic / OpenAI API | data leaves network | pay-per-token |
| Local model via Ollama | fully on-premise | zero |

Copilot and Claude Code IDE extensions are not usable from a standalone fat-client;
they are tied to their host IDE and do not expose a callable endpoint.
A local model via Ollama is the recommended default for enterprise environments.

---

### Functional file schema (`.fn.yaml`)

Each row in the grid corresponds to one record in the `.fn.yaml`:

```yaml
- id: rule_0042
  field: Output.Orders[*].LineAmount   # output path
  type: number
  format: "0.01"                        # 2 decimal places
  required: true
  allowed: {minimum: 0}
  example: "12.50"
  description: "Line amount. Fallback to header default price if item price is null."
  source:
    loop: Orders                        # loop label (see Scope section)
    path: "@.price * @.qty"
  transform:
    expression: "round(coalesce(@.price, $.defaults.price) * @.qty, 2)"
    status: auto                        # auto | manual
    code_override: null                 # Python subset — set when status: manual
    last_auto_version: null             # snapshot of expression before first manual edit
  version:
    source_modified: 2026-09-18T09:11:00
    transform_modified: 2026-09-18T09:11:00
    description_modified: 2026-08-01T10:00:00
```

Each field group (`source`, `transform`, `description`) carries its own `*_modified`
timestamp so diffs are readable at a semantic level, not just line-level.

---

### Scope anchors

Source paths use explicit scope anchors. The default when inside a loop is `@`
(nearest enclosing array item).

| Anchor | Meaning | Generated `.map` variable |
|---|---|---|
| `$` | document root | `root` |
| `@` | current item (nearest loop) | loop variable, e.g. `order` |
| `@<label>` | item of the loop named `<label>` | that loop's variable |
| `@2` | item of the second-nearest loop | outer loop variable |

Each loop is assigned a user-friendly label in the tool. Both `@label` and `@N`
positional forms are valid and interchangeable:

```
# Nested loops: outer label "order", inner label "line"
@line.price        →  line.price
@order.discount    →  order.discount
@2.discount        →  order.discount   (positional equivalent)
$.header.vatRate   →  root.header.vatRate
```

---

### Expression language

Transformations are written as **expression blocks**: the last line is the value
returned; preceding lines may declare local variables for readability. The transpiler
mangles local variable names with a rule-id prefix to prevent collisions with loop
variables in the wider generated scope.

```yaml
transform:
  expression: |
    base = @.price * @.qty
    discount = coalesce(@.discountRate, $.defaults.discount)
    round(base * (1 - discount), 2)
```

Generates:

```python
r42_base     = order.price * order.qty
r42_discount = order.discountRate if order.discountRate is not None else root.defaults.discount
out.amount   = round(r42_base * (1 - r42_discount), 2)
```

Single-line expressions remain the common case; the multi-line form is available
when intermediate naming improves clarity.

The available functions are exactly the `.fn` custom functions defined in the function
library. The functional team does not declare new functions; if a required operation
is missing, a developer adds a `.fn` file and it becomes available.

Common patterns and their expression form:

| Natural description | Expression |
|---|---|
| A if not null, else B | `coalesce(@.A, @.B)` |
| First part split by `\|` | `split_first(@.ref, "\|")` |
| N-th part split by `;` | `split_nth(@.ref, ";", 2)` |
| Concatenate with separator | `concat(@.first, " ", @.last)` |
| If/else | `if_else(@.flag == "Y", @.valA, @.valB)` |
| Format as 2-decimal number | `round(@.amount, 2)` |
| Parse date | `parse_date(@.dt, "YYYY-MM-DD")` |
| Lookup / recode | `lookup(@.code, {A: 1, B: 2})` |
| Iterate nested array | child row with its own loop scope |
| Omit field conditionally | `return` bare in expression block |
| Emit explicit null | `return Null` in expression block |

Expressions can be arbitrarily nested to any required depth.

**Two dialects, same semantics.** The expression block is the *functional dialect*:
it uses scope anchors (`@`, `$`) and the `.fn` vocabulary. `code_override` is the
*developer dialect*: it uses Python subset directly (`root`, `src`, `out`) with no
anchor syntax. The transpiler converts the functional dialect to the developer dialect;
the compiler sees only the developer dialect.

When an operation cannot be expressed with the available function vocabulary,
the developer sets `status: manual` and writes Python subset directly in
`code_override`. The transpiler passes that block through as-is.

---

### Auto / Manual mode

Each rule's `transform` field is independently in one of two states:

**`status: auto`** — the transpiler generates the Python subset from `expression`
on every build. The developer does not touch the generated `.map` file directly.

**`status: manual`** — `code_override` contains Python subset written by a developer.
The transpiler emits `code_override` verbatim. `last_auto_version` stores the last
expression the transpiler generated before the first manual edit, as a reference.

State transitions:

```
auto ──[dev opens code editor and saves]──► manual
manual ──[dev accepts new auto proposal]──► auto   (code_override cleared)
```

When a functional user modifies `source` or `expression` on a row that has
`status: manual`, the row is flagged visually in the grid. The developer can:

1. Filter the grid to show only "functionally modified, manually overridden" rows.
2. Open a split-pane view: current `code_override` on the left, transpiler's new
   auto-generated proposal on the right.
3. Accept the auto proposal (→ `status: auto`, `code_override` cleared) or revise
   `code_override` manually and keep `status: manual`.

No manual override is silently discarded. The developer must explicitly resolve
each flagged row.

---

### Operational modes

Two project-level modes govern the relationship between the `.fn.yaml` and `.map` files:

**Bootstrap** (`mode: bootstrap` in project config)
The `.fn.yaml` generates the initial `.map` once. After that, developers own the `.map`
file directly. The `.fn.yaml` is retained as documentation but is no longer the source
of truth. Subsequent changes to the `.fn.yaml` do not regenerate the `.map`.

**Functional-driven** (`mode: driven`)
The `.fn.yaml` is always the source of truth. The `.map` is always a generated artifact.
Developer overrides live in `code_override` fields inside the `.fn.yaml`, not in the
`.map`. CI regenerates `.map` from `.fn.yaml` and fails if the committed `.map` is
out of sync (same mechanism as generated stubs).

---

### Repository layout (extended)

```
json2json-mapper/
├── mappings/
│   ├── functional/          ← .fn.yaml files — source of truth (driven mode)
│   │   └── order_event.fn.yaml
│   └── generated/           ← .map.py files — generated artifacts, never hand-edited
│       └── order_event.map.py
├── import-profiles/         ← reusable column-mapping profiles for migration imports
│   └── legacy_excel_v2.import.yaml
└── ...
```

---

### Version control

The tool embeds **Gitoxide** (pure-Rust git implementation) as its primary VCS backend.
If a specific operation is not yet supported by Gitoxide, the tool falls back to the
system `git` binary if available. If neither can perform the operation, that feature is
silently disabled and indicated via a tooltip warning on the relevant UI control.

**Save** in the tool creates a git commit scoped to the modified `.fn.yaml` files.
The commit message is composed from the free-text "version notes" field the functional
user fills before saving. The commit highlights which rows changed (by `id`) and which
field groups were touched (`source`, `transform`, or `description`).

Generated `.map.py` files are committed separately by CI, not by the tool, to keep
functional commits and generated-artifact commits distinct in history.

A remote repository is optional and user-configurable (GitHub, GitLab, Azure DevOps,
or none).

---

### Testing

Testing is split into two independent tracks.

**Track 1 — Transpiler unit tests**
The transpiler itself (`.fn.yaml` → `.map.py`) is tested with standard unit tests that
do not require any target runtime. Each test feeds a `.fn.yaml` fixture through the
transpiler and asserts the generated Python subset matches an expected snapshot.
These tests run in pure Python with no Oracle or container dependency.

**Track 2 — Target environment tests**
Testing that the generated PL/SQL behaves correctly requires the target runtime. The
tool detects whether **Podman** or **Docker** is available on the system. If found, it
offers to spin up a container using the image declared by the compiler backend
(configurable in project options; the user controls the image tag). The workflow:

1. User provides a **test input file** (JSON) — required.
2. User optionally provides an **expected output file** (JSON) for E2E golden-record
   validation. If provided, the tool diffs actual vs. expected and reports pass/fail.
   If omitted, the tool displays the mapped output for manual inspection.
3. The container is ephemeral — started for the test run, stopped and removed after.

If neither Podman nor Docker is detected, Track 2 is silently unavailable. The relevant
UI controls are disabled with a tooltip explaining the missing prerequisite.

---

### Migration from existing mapping files

To migrate pre-existing mapping files (Excel, CSV, Word, PDF, or other formats) into
`.fn.yaml`, the tool runs a structured LLM-assisted import in two steps.

**Step 1 — Column mapping (import profile)**
The user maps the source file's columns to `.fn.yaml` fields once
(source column → `field`, `type`, `source.path`, `transform.expression`, etc.).
This mapping is saved as a reusable **import profile** (`.import.yaml`), shareable
with the rest of the team. Import is a one-time operation; if a re-import is needed
later, maintaining the profile is the functional team's responsibility.

**Step 2 — LLM translation (blinkered skill)**
The tool sends each row through the LLM with a tightly constrained prompt.
The LLM receives: the column mapping, the full `.fn.yaml` schema, the scope anchor
syntax, and the available function vocabulary. Its only valid output is a `.fn.yaml`
record. The compiler validates each generated record; on failure, the error is fed
back to the LLM for a retry. Rows that fail after retry are flagged for manual review.

**Reverse import from `.map.py` (map-first scenario)**
If a `.map.py` already exists (written by a developer adopting the engine without a
prior functional file, or generated during a bootstrap), it can be reverse-imported
into `.fn.yaml` via a two-phase LLM process:

- *Phase A — Normalization*: the LLM restructures the `.map.py` into function-per-field
  form, giving each output field an explicit, unambiguous scope. If the original file
  uses shared local variables or multi-field blocks, this phase inlines and splits them.
- *Phase B — Translation*: each normalized field function is translated to a `.fn.yaml`
  record using the same blinkered skill as the forward import. The compiler validates;
  failures are flagged for manual review.

Reverse import is simpler than forward import because the source is already a formal
Python AST rather than free-form natural language. However, the golden-record tests
(Track 2) remain mandatory before marking any reverse-imported row as `validated`.

---

## Out of scope

- Post-mapping JSON Schema validation (responsibility of the consuming system)
- Mapping registry and scheduling (responsibility of the host engine, e.g. `mapping_engine_v2`)
- Multi-target compilation in a single build invocation (single target per build run)
- Fine-tuning of the embedded LLM model (uses base models via API or Ollama as-is)

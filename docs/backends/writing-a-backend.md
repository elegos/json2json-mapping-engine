# Writing a backend

A **backend** turns a checked mapping into code for one *target*: PL/SQL, Python, and whatever
you add. This guide takes you from nothing to a working backend, in small steps, with code you
can run. The [In a nutshell](#in-a-nutshell) section at the end is the quick reference.

Read [ARCHITECTURE.md](../ARCHITECTURE.md), §Target backends, for the reasons behind the design;
this page is the how-to. Two real backends are the reference: `compiler/backends/python/` (small,
runs in-process, the best one to copy) and `compiler/backends/plsql/` (large, runs on Oracle).

## 1. The big picture

```
mapping.fn.yaml ──transpile──▶ mapping.map.py ──compile──▶ CompiledUnit ──assemble──▶ files
   (what users edit)         (Python subset)     (your code)   (one per mapping)   (build/compiled/)
```

Everything before your backend is shared by all targets: the security validator, loop fusion,
scope resolution, type checking and the function linker. When your code runs, the mapping
(`.map.py`) is **already valid, fused and typed**. You only decide *how it looks in your target*.

You write one class, a subclass of `Backend`, and three methods:

| Method | You get | You give back |
|---|---|---|
| `compile_module(tree, mapping_id, scope_resolution)` | the checked tree of **one** mapping | a `CompiledUnit` (anything you need later) |
| `unit_from_json(data)` | what `unit.to_json()` wrote | the same unit (the build cache keeps units between runs) |
| `assemble(units)` | the units of **all** mappings | `{file name: text}`, the deployable files |

Everything else (options, built-ins, tests) is optional and comes in later steps.

## 2. A first backend in 5 minutes

We write a toy backend, `outline`, that makes one text file per mapping listing its rules and the
output fields it writes. It generates no real code, but it is complete: it builds, it is
configurable, and it shows the whole contract.

**Where does it go?** Two places work, and the code is the same:

- **In a project:** `compiler/backends/outline.py` in the project root. Good for a private target
  or to replace a built-in one.
- **In the tool:** `compiler/backends/outline/` (a package with an `__init__.py` that imports the
  class), for a backend that ships with it.

Nothing is registered by hand: the registry imports every module there and picks each concrete
`Backend` subclass, under its `target` name.

```python
# compiler/backends/outline.py
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, ClassVar

from compiler.backends.base import Backend, CodeGenError, CompiledUnit, Option


@dataclass
class OutlineUnit(CompiledUnit):          # 1. what compiling one mapping gives
    mapping_id: str
    rules: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:  # the build cache stores it as JSON
        return {"mapping_id": self.mapping_id, "rules": self.rules, "writes": self.writes}


class OutlineBackend(Backend):
    target: ClassVar[str] = "outline"           # the name used in mapper.toml
    artifact_suffix: ClassVar[str] = ".txt"     # extension of the files assemble() gives
    options: ClassVar[tuple[Option, ...]] = (   # the keys of [target.outline]
        Option("title", "string", "First line of every file", default="Mapping", max_length=40),
    )
    defaults: ClassVar[dict[str, Any]] = {"title": "Mapping"}

    def compile_module(self, tree, mapping_id, scope_resolution=None):   # 2. one mapping
        unit = OutlineUnit(mapping_id)
        for stmt in tree.body:
            if isinstance(stmt, ast.FunctionDef):                  # a rule
                unit.rules.append(stmt.name)
            elif isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute):
                unit.writes.append(ast.unparse(stmt.targets[0]))   # `out.OrderId = ...`
        if not unit.writes:
            raise CodeGenError(f"{mapping_id}: the mapping writes nothing")   # a build error
        return unit

    def unit_from_json(self, data):                                # 3. back from the cache
        return OutlineUnit(data["mapping_id"], data["rules"], data["writes"])

    def assemble(self, units):                                     # 4. all mappings
        files = {}
        for unit in units:
            lines = [f"{self.config['title']} {unit.mapping_id}", "rules: " + ", ".join(unit.rules)]
            lines += [f"writes {w}" for w in unit.writes]
            files[f"{unit.mapping_id}.txt"] = "\n".join(lines) + "\n"
        return files
```

Select it in `mapper.toml` and build:

```toml
[project]
target = "outline"

[target.outline]
title = "Plan"
```

```console
$ mapper build
compiled: mappings/functional/orders.fn.yaml
packages: build/compiled/orders.txt (1 mapping(s))
$ cat build/compiled/orders.txt
Plan orders
rules: oid, cur, wh, ver, chan, cust, cust_first, lines
writes out.OrderId
writes out.Currency
...
```

(`out.Lines` is missing on purpose: it is written by `out.Lines.append(...)` inside a loop, not by an
assignment. A real backend handles every statement shape; see step 3.)

You can also call the compiler from Python, which is how you test a backend:

```python
from compiler.backends.registry import create_backend
from compiler.pipeline import compile_unit

backend = create_backend("outline", {"title": "Plan"})
unit = compile_unit(open("orders.map.py").read(), "orders", backend)
print(backend.assemble([unit])["orders.txt"])
```

## 3. What a mapping looks like to your code

`mapper transpile` writes the `.map.py` of a mapping (also in `build/transpiled/`). This is the
input `compile_module` receives, as an `ast.Module`:

```python
from __mapping__ import *
__id__ = 'orders'

@dataclass
class Customer:                       # a shape of the output (an object)
    Name: str
    Code: str

def oid(root: Orders) -> str:         # a RULE: one function per rule
    return root.id

def wh(root: Orders) -> str | None:   # built-ins are plain calls, by name
    return split_nth(root.ref, ',', 2)

def lines(root: Orders, src: Ordersitem) -> LinesItem:   # a rule inside a loop gets `src`
    return LinesItem(Sku=src.sku, Qty=src.qty, Family=split_first(src.sku, '-'))

out.OrderId = oid(root)               # the statements that run the rules and write the output
for src in root.items:
    out.Lines.append(lines(root, src))
```

The parts to handle:

| In the tree | Meaning | What you do |
|---|---|---|
| `__id__ = '...'` | the mapping's id | already given to you as `mapping_id` |
| `@dataclass class X` | the shape of an output object | create your target's record / type |
| `def rule(root, src=...)` | one rule | one function in your target; its return annotation is the type |
| `root`, `src`, `index` | the input document, the current loop element and its position | read the input |
| `Name(...)` | a call to a built-in or a project function | go through the function linker (step 5) |
| `out.A = rule(root)` | write a field | write the output, and **collect the rule's error instead of stopping** |
| `for src in root.items:` / `out.L.append(...)` | a loop that builds a list | iterate and append |
| `@parallel(degree=N)` on a rule | the loop may run its elements in parallel | your target's mechanism, or ignore it |

You are not alone in this: the type checker has attached the types, the validator has removed
everything a mapping may not do, and loop fusion has already merged loops. The PL/SQL codegen is
the long reference (it supports everything), the Python one the short one.

## 4. Configuration: `[target.<name>]`

Declare every key your backend reads as an `Option`. In return you get, for free:

- the loader **rejects unknown keys and wrong values** with a clear message;
- the **project properties form** of the desktop tool, drawn from your options;
- `defaults` merged into your `self.config` (a missing key is never a `KeyError` if it is there).

```python
Option("schema", "string", "Owner of the generated packages", required=True,
       max_length=128, pattern=r"[A-Za-z][A-Za-z0-9_$#]*", pattern_hint="letters, digits, _ $ #")
Option("error_code", "int", "Code of the raised error", required=True, suggest=-20000,
       minimum=-20999, maximum=-20000)
Option("parallel", "choice", "How @parallel loops run", default="thread", choices=("thread", "none"))
```

Kinds: `string`, `int`, `bool`, `choice`, `table` (text to text). A rule that spans several keys
("this or that") goes in `validate_config(cls, section)`: raise `CodeGenError` with a message the
form shows as a whole.

## 5. Built-in and project functions

A mapping calls functions: `split_first(s, ',')`, `round(x, 2)`, and the project's own. Your
backend must say what each one is in the target. There are three sources, in this priority:

1. **A project function with `@override(<your target>="...")`**: a template with the parameters
   written `{name}`. The project's word beats everything. A project function with *no* code for
   your target stops the build ("no implementation for <target>"): never guess.
2. **A project function with a body**: it is Python, so the Python backend runs it; any other
   backend needs an `@override`.
3. **A built-in**: the reference semantics are the Python bodies in `compiler/builtins.py`.
   A backend that runs Python (like the Python one) needs nothing more. Any other target
   writes its own, as a `FunctionImpl`:

```python
from compiler.function_linker import FunctionImpl

BUILTINS = {
    "trunc": FunctionImpl("trunc", {"mytarget": "TRUNC({0}, {1})"}),     # fixed arity: {0}, {1}...
    "concat": FunctionImpl("concat", {"mytarget": lambda args: " || ".join(args)}),  # variadic
}

class MyBackend(Backend):
    @classmethod
    def builtin_implementations(cls):     # lets the tool show your templates in "Override…"
        return BUILTINS
```

In `compile_module`, build a `FunctionLinker(BUILTINS, project_implementations)` and render each
call with `linker.resolve(name).render("mytarget", [arg expressions])`. See
`compiler/backends/plsql/codegen.py` (`_t_Call`) for the full version.

**Aggregates** (`max`, `min`, `sum`, `avg`) are different: they need an accumulator, so PL/SQL
generates a loop for them. A target with a simple expression for them can use a template like any
other function. A project that overrides one with `@override(<target>=...)` replaces the loop,
with `{items}` (the list) and `{field}` (the field name) in the template.

**Warnings**: `unit_warnings(unit)` returns lines the build shows (the Python backend uses it to
say that `@parallel` is not faster on a Python with the global lock).

## 6. Errors: the contract every target keeps

A rule that fails must not stop the others. Each backend gives two entry points per mapping:

- a **safe** one: returns the output *and* the list of rule errors (`{"rule": ..., "cause": ...}`);
- a **raising** one: raises when any rule failed, and gives the same output otherwise.

The two must agree; the golden cases check it. §Runtime error semantics of ARCHITECTURE.md has the
details (what null, omitted and failed mean).

## 7. Testing

**Offline (track 1)**: compile a mapping and look at the text, no target runtime needed. This is
what the snippet at the end of step 2 does, inside `pytest`. Look at
`tests/track1/python_backend/` for a real example.

**The golden cases (track 2)** are the contract: every backend must give the same output and the
same rule errors for the same input. A case is `tests/golden/<mapping>/<case>.input.json` with
`<case>.expected.json` (and `<case>.expected_errors.json`: the rules expected to fail).
To run them with your backend, declare it:

```python
class MyBackend(Backend):
    has_integration = True

    def integration_unavailable(self) -> str | None:
        return None if shutil.which("mytool") else "mytool is not installed"   # a reason, or None

    def run_integration(self, context):          # context.cases, context.files, context.mapping_ids
        results = []
        for case in context.cases:
            output, errors = run_it_somehow(context.files, case.input_path)    # your environment
            results.append(judge(case, output, errors))      # judge compares and builds the verdict
        return results
```

`judge` (from `compiler.backends.integration`) compares the output to the expected file and the
errors to the expected ones; you only run the case. If your environment needs settings (an image,
a path), declare them as `test_options`: they live in `[target.<name>.test]`.
`mapper test --integration` then runs them; without `has_integration` the cases are skipped.
The Python backend (`compiler/backends/python/backend.py`, `run_integration`) is the shortest example.

## 8. Checklist

1. `target` set and unique; subclass in a module under `compiler/backends/` (tool or project).
2. `compile_module`, `unit_from_json`, `assemble`: the unit survives `to_json` → `unit_from_json`.
3. `options` for every key; `defaults` for the optional ones.
4. Every built-in has an implementation (or you run Python); project functions go through `@override`.
5. A rule failure gives a rule error and the others still run; the two entry points agree.
6. Offline test of the generated text, and the golden cases run.
7. A section for your target in `docs/backends/` (copy the layout of `plsql.md`).

---

## In a nutshell

**I want to…**

| …do this | …do that |
|---|---|
| add a target | `compiler/backends/<name>.py` (project) or `compiler/backends/<name>/` (tool) with a `Backend` subclass, `target = "<name>"`. Nothing to register |
| use it | `[project] target = "<name>"` in `mapper.toml`, then `mapper build` |
| make the smallest backend | implement `compile_module`, `unit_from_json`, `assemble` (a `CompiledUnit` with `to_json`) |
| read a mapping | `compile_module(tree, mapping_id, scope_resolution)`: `FunctionDef` = rule, `Assign` / `For` at top level = the run, `ClassDef` = output shape |
| fail a build | `raise CodeGenError("message")` |
| add settings | `options = (Option(...), ...)`; `defaults = {...}`; the form and the validation come free |
| check settings across keys | `validate_config(cls, section)` |
| name the output files | `artifact_suffix = ".ext"` and the keys of the dict `assemble` returns |
| order the files for deployment | `deploy_order(file_names)` |
| run built-ins in my language | `FunctionImpl(name, {"<target>": "TEMPLATE({0}, {1})" or callable})`; `builtin_implementations()` shows them in *Override…* |
| let projects replace a function | nothing: `@override(<target>="...")` in `fn/*.fn`, parameters as `{name}` |
| make an aggregate overridable | render the project's template instead of your loop when `linker.overrides(name)` |
| warn at build time | `unit_warnings(unit)` → list of lines |
| run the golden cases | `has_integration = True`, `integration_unavailable()`, `run_integration(context)` ending in `judge(case, output, errors)` |
| declare test settings | `test_options = (Option(...),)` → `[target.<name>.test]` |
| test without a runtime | `compile_unit(source, id, backend)` then `backend.assemble([unit])`, in `pytest` |
| see a mapping's input | `mapper transpile` → `build/transpiled/<name>.map.py` |
| copy something real | `compiler/backends/python/` (small), `compiler/backends/plsql/` (complete) |

**Must always be true:** same input → same output and same rule errors on every backend · a
failing rule is reported and the rest run · the raising and the safe entry point agree · no
guessing: a function with no code for the target stops the build.

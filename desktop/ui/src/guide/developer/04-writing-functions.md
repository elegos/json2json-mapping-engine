# Writing functions and overrides

When the built-in functions are not enough, you write your own, in the tool, with no external
editor. This page goes step by step; the box at the end is a one-minute summary.

A **project function** is a typed Python function in a file of `fn/`. A mapping calls it by name,
exactly like a built-in. An **override** is the same thing with a built-in's name: it replaces the
built-in in every mapping of the project.

## 1. Open the function panel

The **fn** tab on the right edge opens the [function explorer](explorer:open) over the tool (Help →
Function explorer does the same). The grid keeps its size: the panel slides over it.

```figure
{"src": "functions.png", "alt": "The function explorer, opened from the fn tab"}
```

## 2. Create a function

Press **New function…**, type a name, and choose the file: one of the project's `.fn` files, or
**New file…** (the button beside the box gives the list back). The editor opens on a stub:

```python
@override(plsql="NOT_IMPLEMENTED('plsql stub')")
def to_cents(value: str) -> str:
    """Say what it does, in one line."""
    raise NotImplementedError("python stub")
```

The stub is on purpose. A function needs code for **two** places, and it is flagged as an error
until it has both:

| For | Why | Where you write it |
|---|---|---|
| **Python** | The tool and the golden cases always run on Python, whatever the project's backend | The body of the function, or `@override(python="...")` |
| **The project's backend** (say PL/SQL) | It is what runs in production | `@override(plsql="...")` above the function |

(A project whose backend is Python needs only the body.)

## 3. Write the code

```python
@override(plsql="ROUND({amount} * 100)")
def to_cents(amount: float) -> float:
    """The amount in cents."""
    return round(amount * 100)
```

- **Types are required**: every parameter and the result. The first line of the docstring is the
  description shown in the explorer.
- **The body** is Python, with the same restricted subset as the rest, and typed scalar
  parameters only.
- **`@override(<backend>="...")`** is a *template*: the code that backend gets for a call. Write the
  parameters as `{name}`. Typing `@` in the editor offers the decorator for Python and for every
  backend.

```figure
{"src": "function-editor.png", "alt": "The function editor with the test call"}
```

The issues under the code update as you type: syntax errors, a missing type, a missing description,
no code for Python, no code for the backend, and a name that is also defined elsewhere. **Save**
(Ctrl+S) writes the file; a text that does not parse is refused, so `fn/` always reads.

### The names you can use

The **Names** button in the editor lists them. In a function body you have:

| Name | What it is |
|---|---|
| the parameters | by their names |
| every J2JME function | built-in or the project's, by name: `split_first(s, ",")` |
| `_py` | **Python's own built-ins**: `_py.len(x)`, `_py.sum(xs)`, `_py.sorted(xs)`… (typing `_py.` suggests them) |
| `re`, `json`, `operator` | Python modules, already imported |
| `Decimal`, `ROUND_HALF_UP`, `ROUND_DOWN` | for exact arithmetic and rounding |

Why `_py`? The J2JME functions shadow four Python names: inside a function `max`, `min`, `round` and
`sum` are the J2JME ones (`sum(items, field)`), not Python's. `_py.sum(values)` is Python's. That is
why a copied built-in such as `avg` reads `_py.sum(values) / _py.len(values)`.

## 4. Try it

**Test call** runs a function of the file on Python, with the text as it is: no save needed. Type the
arguments as a JSON array (`[12.5]`) and press **Run**: you see the result or the error. A function
with no Python code says so instead of running. It tests the *Python* code; the template for your
backend runs only when the project is built and tested on that backend.

## 5. Override a built-in

Select a built-in in the explorer and press **Override…**: its source is copied into
`fn/builtin_overrides.fn`, under a warning, and the editor opens on it.

```figure
{"src": "function-override.png", "alt": "A built-in copied into the overrides file"}
```

- The copy replaces the built-in **everywhere in the project**. Change it with care.
- The `@override(...)` lines show what each backend writes for the built-in today: edit them.
- To get the built-in back, delete the function from the file, or the file (**Delete file**).
- This file is only for built-in overrides: new functions go to the others.

If the open file has unsaved changes, the tool asks to save before it opens another one.

## 6. Aggregations

On PL/SQL, `count` is an expression, but `max`, `min`, `sum` and `avg` are **generated as a loop**,
so there is no template to copy: **Override…** gives a stub and a note. To change one, write an
expression that calls a function **you deploy** in the database:

```python
@override(plsql="MY_PKG.mean({items}, {field})")
def avg(items: list[Any], field: str = '') -> Any:
    return sum(i[field] for i in items) / len(items)
```

`{items}` is the list (a `JSON_ARRAY_T`) and `{field}` the field name. The loop is then not
generated, and the call can sit inside a larger expression.

## A new backend

Support for a whole new target (not a function) is a different, developer-side task: see
`docs/backends/writing-a-backend.md` in the repository.

---

## In a nutshell

| I want to… | Do this |
|---|---|
| open the panel | **fn** tab on the right edge, or Help → Function explorer |
| add a function | **New function…**: name, file (or **New file…**) → fill in the stub |
| make it work on every backend | body (Python) **and** `@override(<backend>="...")`, parameters as `{name}` |
| find the decorator | type `@` in the editor |
| use a Python built-in | `_py.len(x)`, `_py.sum(xs)`… (`max`, `min`, `round`, `sum` are the J2JME ones); **Names** lists what is available |
| indent | Tab / Shift+Tab |
| check a function | **Test call**: arguments as a JSON array, **Run** (Python only) |
| save | **Save** or Ctrl+S (not saved if the text does not parse) |
| edit an existing function | select it → **Edit…** |
| change a built-in | select it → **Override…** (copy in `fn/builtin_overrides.fn`) |
| undo an override | delete the function, or the file |
| change an aggregation on PL/SQL | `@override(plsql="MY_PKG.f({items}, {field})")` with your own function |
| clear a red issue | stub → real code; missing type → annotate; no backend code → `@override` |

**Always true:** every function needs code for Python and for the project's backend · types on every
parameter and the result · an override replaces the built-in for the whole project · the tool never
runs project code except in the test call, in a separate process with a time limit.

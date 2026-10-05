# Functions

Expressions call functions. Two kinds exist, and they are used in the same way:

- **Built-ins**, which come with the tool and exist for every backend.
- **Project functions**, written by you in `fn/*.fn`. A project function with the name of a
  built-in replaces it.

The complete, current list of both is in the [function explorer](explorer:open), which reads it from the
project itself: name, signature, description and where each comes from. This page only gives a
taste of it, since the list grows with the tool.

Some examples: `coalesce` (first value that is not null), `round`, `concat`, `if_else`,
`split_first` / `split_nth`, `lookup` (recode with a table), `parse_date`; and the aggregations
`max`, `min`, `sum`, `avg`, `count`.

In the explorer, search by name or by what a function does, read its signature and description,
and press **Insert** to put a call in the Source or Expression cell you are editing, or in the
code of a rule's override. The same functions are available in both, by the same names; the
only difference is how the arguments are written: anchors (`@.qty`, `$.rate`) in a cell,
`src.qty` and `root.rate` in override code (the developer dialect).


```figure
{"src": "functions.png", "alt": "The function explorer"}
```

## Regular expressions

`regexp_replace` and `regexp_group` take a pattern in the dialect of the backend that runs the
mapping: Python's `re`, or Oracle's `REGEXP_*`. The tool does not translate it. Look-around, named
and non-capturing groups, for example, exist in Python and not in Oracle. When a project may change
backend, keep to the common part (classes, groups, anchors, alternation, the usual quantifiers).
This is the documented exception to "the same input gives the same output on every backend".

## What a project function says for each backend

A function in `fn/*.fn` is used by every backend, and each takes what the function says **for it**:

| For | Where it comes from |
|---|---|
| **PL/SQL** | `@override(plsql="UPPER({s})")`: a template, the parameters written as `{name}`. Without it the build stops: no implementation for PL/SQL. |
| **Python** | `@override(python="{s}.upper()")`, or else the Python body of the function (its code, with the types dropped). A body that is only `...`, `pass` or `raise NotImplementedError` is not code. |

A function that replaces a built-in of the same name replaces it for every backend. One with no
code for Python still builds for PL/SQL, but the golden cases cannot run the rules that call it: the
tool says so (amber row, case NOT RUN) instead of reporting a failure. The function explorer shows
whether a function has Python code.

## Writing a function

A `.fn` file holds functions in the same restricted Python subset as the rest. They work on typed
scalar parameters only: no access to `root`, `src` or `out`. The docstring is what users see when
the function is suggested while they type.

## Aggregations

`max`, `min`, `sum`, `avg` and `count` reduce a list to one value, e.g. `max($.myList.numAttr)`.
They can appear only as the direct value of a rule, not nested in a larger expression.

On PL/SQL, `count` is an expression (`list.get_size`), while `max`, `min`, `sum` and `avg` are
**generated as a loop** with an accumulator: there is no template to copy. To change one, define a
function of the same name in `fn/` with an `@override(plsql="...")` that is an *expression* of the
parameters, `{items}` (the list, as a `JSON_ARRAY_T`) and `{field}` (the field name, as text), for
example `@override(plsql="MY_PKG.mean({items}, {field})")`, where `MY_PKG.mean` is a PL/SQL function
you deploy. The loop is then not generated, and such a call may be nested in an expression. For
Python the function's body is the code.

## One list for everything

The tool's checks, the suggestions in the grid and the stubs for your editor all read the same
list of functions, so they never disagree.

## Creating and editing project functions

You do not need an external editor. The **fn** tab on the right edge (or Help → Function explorer) slides the [function explorer](explorer:open) over the tool, and the editor slides out to its left; the grid keeps its size.


- **New function…** asks for a name and the file (`fn/<file>.fn`, made when it does not exist) and
  opens the file with a stub: a body that raises `NotImplementedError("python stub")` and, when the project's backend is not Python, `@override(<backend>="NOT_IMPLEMENTED('<backend> stub')")`. The issues list keeps flagging both until you write the real code.
- **Edit…** on a project function opens its file. The explorer grows to the left to hold the
  editor: a whole `.fn` file, with Python colours and the function names to complete. The issues
  list is live: syntax errors, a parameter or a result with no type, no description, no code for
  Python, and no code for the project's backend (`@override(plsql="…")`, say). A text that does not
  parse is not saved, so `fn/` always reads. **Save** (or Ctrl+S) writes the file.
- **Test call** runs a function of the file on the Python backend with arguments you type as a JSON
  array (`["hello big world"]`), with the text as it is: no save needed. A function with no Python
  code says so.
- **Override…** on a built-in copies its source (with the helpers it uses) into
  `fn/builtin_overrides.fn`, under a warning: *changing a built-in might break the mappings that
  call it*. The copy replaces the built-in in every mapping of the project. Delete the function, or
  the file, to get the built-in back.

Every function needs code for Python (the tool and the golden cases run on it, whatever the
project's backend) and for the project's own backend, when that is not Python.

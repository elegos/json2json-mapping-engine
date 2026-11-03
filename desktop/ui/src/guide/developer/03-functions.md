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
`max`, `min`, `sum`, `avg`, `count`, `any`, `all`; `matches` and `split_list` for texts.

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

`matches(text, pattern)` is true when the **whole** text fits the pattern. Unlike the `regexp_*`
functions its pattern is a literal in a portable subset (characters, `.`, classes, groups, `|`,
`* + ? {n,m}`; no anchors, no `\d \w \s \b`, no `(?...)`), checked when the mapping is compiled,
so it means the same on every backend: Python's `re.fullmatch`, and on PL/SQL `REGEXP_LIKE` with the
pattern anchored.

## Loops that need a library function

`split_list(text, separator)`, a loop's source over the parts of a text, is written for PL/SQL as a
function of the functions package (an empty part is a null element). `order by` on a loop is
generated, on PL/SQL, as a stable insertion sort of positions into a new array: the document's own
array is never reordered under the other loops that read it.

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

`max`, `min`, `sum`, `avg`, `count`, `any` and `all` reduce a list to one value, e.g.
`max($.myList.numAttr)`, `any(i.qty > 10 for i in $.items)`. They can be part of a larger expression
and one can be inside another, to any depth, also in the condition of a selection
(`$.packages[any(i.ref == @2.ref for i in items)]`).

On PL/SQL, `count` over a whole list is an expression (`list.get_size`), while the others, and any
aggregate with a condition, are **generated as a loop** with an accumulator, placed before the
statement that uses its value (a nested one, inside the loop of the outer one): there is no template to copy. To change one, define a
function of the same name in `fn/` with an `@override(plsql="...")` that is an *expression* of the
parameters, `{items}` (the list, as a `JSON_ARRAY_T`) and `{field}` (the field name, as text), for
example `@override(plsql="MY_PKG.mean({items}, {field})")`, where `MY_PKG.mean` is a PL/SQL function
you deploy. The loop is then not generated, and such a call may be nested in an expression. For
Python the function's body is the code.

## One list for everything

The tool's checks, the suggestions in the grid and the stubs for your editor all read the same
list of functions, so they never disagree.

## Creating and editing project functions

You do it in the tool, from the **fn** tab: see [Writing functions and overrides](page:developer/writing-functions).

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

## Writing a function

A `.fn` file holds functions in the same restricted Python subset as the rest. They work on typed
scalar parameters only: no access to `root`, `src` or `out`. The docstring is what users see when
the function is suggested while they type.

## Aggregations

`max`, `min`, `sum`, `avg` and `count` reduce a list to one value, e.g. `max($.myList.numAttr)`.
They can appear only as the direct value of a rule, not nested in a larger expression.

## One list for everything

The tool's checks, the suggestions in the grid and the stubs for your editor all read the same
list of functions, so they never disagree.

## Creating and editing project functions

For now a project function is a text file in `fn/`; the explorer shows it with the file it comes
from. Creating and editing them inside the tool is planned.

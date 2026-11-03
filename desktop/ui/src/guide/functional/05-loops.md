# Loops

A **loop** rule builds a list of the output from a list of the input: its rules are applied to
each element, and each result is one element of the output list.

| Cell of the loop's row | What it says |
|---|---|
| **Target** | The output list: `Lines[*]`. |
| **Source** | The input list: `$.items[*]`. |
| **Expression** | The loop's **filter**: only the elements for which it is true are kept (`@.qty > 0`, `not is_empty(@.weight)`). |

```figure
{"src": "loops.png", "alt": "A loop with a filter and options set"}
```

The rules inside the loop read the current element as `@` (`@.sku`), the one around it as `@2`,
and its position as `@index`.

## What a loop can run over

| Source | Meaning |
|---|---|
| `$.items[*]` | Every element of a list of the input. |
| `$` | The whole message as one element: a list of one entry built from it. With a filter, a block written only when a condition on the message holds. |
| `@2.refs[*]`, `@line.refs[*]` | A loop inside another one can start from the outer element: `@` is the loop it sits in, `@2` (or its name) the one outside it. |
| `split_list(@.notes, ",")` | The **parts of a text**: one element for each value of a list written in one text. The element is a text, read as `@`: `split_nth(@, ":", 1)`. An empty part is an empty element (`not is_empty(@)` in the filter leaves it out); a missing or empty text gives no element. |

Several loops can write into the **same** output list: the elements come out in the order of the
rules.

## Loop options (the gear)

The gear ⚙ in the **Kind** cell of a loop opens its options. The row shows a short summary of what
is set.

| Option | What it does |
|---|---|
| **Name for the element** | A label: a rule in a loop nested in this one can write `@order.price` instead of `@2.price`, and the name does not change if loops are added around. |
| **Order the list by** | One or more keys, see below. |
| **First number** | `@index` starts from 0 (default) or from 1, or any whole number. |
| **When there is nothing to list** | See below. |
| **Parallel degree** | How many workers may map the elements at once, where the target allows it. |

```figure
{"src": "loop-options.png", "alt": "The loop options dialog"}
```

### Ordering a list

Each key is an expression of the element, like SQL's `order by`, with a direction and what to do
with the elements that have no value for it:

```
to_number(split_last(@.lineCode, "-")), @.createdAt desc nulls first
```

- Keys are tried in turn: the next one breaks the ties of the one before. Elements with equal keys
  keep the order they have in the input.
- Ascending is the default, and elements with no key go **last** (`nulls first` puts them first,
  whichever the direction).
- A key that is not a plain field of the element (a computed one) must give a **number or a text
  the tool knows**: `to_number(...)`, `to_string(...)`, `upper(...)`, arithmetic. An `if_else` of two
  fields does not say which, so wrap it: `to_string(if_else(...))`. The check says so when it is
  needed.
- The order is applied **before the filter and before `@index`**: sorted, then filtered, then
  numbered; the numbers have no gaps.
- The same clause chooses the best of several in a path, see
  [choosing an element](page:functional/source).

### When there is nothing to list

| Choice | Output |
|---|---|
| default | The list is **left out**, unless the output schema requires it, and then it is an empty list. |
| **Leave the list out** | Never written when empty. The check refuses it for a list the schema requires. |
| **Write an empty list** | `[]` when no element passes. |

A list inside an object that has a guard exists only when the guard holds.

## Numbered lines

A running number is a field with the Source `@index` and no Expression. If the lines must start
from 1, set **First number** to 1 (or write `@index + 1`).

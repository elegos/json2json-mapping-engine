# Expression

The Expression says **how the value is computed** when it is not a plain copy of the Source.
Leave it empty to copy the Source as it is.

The Source's value is called `value`:

```
lookup(value, @countryCurrency, "N/A")
```

Anchors work as in the Source: `$.defaults.price`, `@.qty`, `@line.price`.

## Common patterns

| You want | Write |
|---|---|
| A if there is one, else B | `coalesce(@.A, @.B)` |
| The first part before a `\|` | `split_first(@.ref, "\|")` |
| The N-th part split by `;` | `split_nth(@.ref, ";", 2)` |
| Join with a separator | `concat(@.first, " ", @.last)` |
| If / else | `if_else(@.flag == "Y", @.valA, @.valB)` |
| Two decimals | `round(@.amount, 2)` |
| Read a date | `parse_date(@.dt, "YYYY-MM-DD")` |
| Recode with a table | `lookup(@.code, {A: 1, B: 2})` |

The functions are the ones the project has: the tool's own and those a developer adds. Typing in
the cell suggests them, with a short description of each.

## Several lines

When the computation is long, give the intermediate steps a name. The **last line** is the value:

```
base = @.price * @.qty
discount = coalesce(@.discountRate, $.defaults.discount)
round(base * (1 - discount), 2)
```

## Leaving a field out, or setting it to null

| Write | Effect |
|---|---|
| a bare `return` | The field is **omitted** from the output. |
| `return Null` | The field is in the output, with an explicit `null`. |

## What counts as false

In a condition, these are false: a missing value, `null`, `false`, `0`, `""`, `[]` and `{}`.
Everything else is true, so `"0"` and `" "` are true. To test only that a value is present, compare
it with `None`.

## When a function is missing

If what you need cannot be written with the available functions, ask a developer: they can add a
function, or write the code of that rule by hand (see the
[Developer book](page:developer/overrides)).

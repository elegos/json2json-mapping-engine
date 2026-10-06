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

| Remove a prefix | `remove_prefix(@.code, "ID-")` |
| Replace a text | `replace(@.name, "-", " ")` (leave out the replacement to remove it) |
| Replace by pattern | `regexp_replace(@.phone, "[^0-9]", "")` |
| Take a part by pattern | `regexp_group(@.ref, "([A-Z]+)-([0-9]+)", 2)` |
| Always two decimals, as text | `format_decimal(@.amount, 2)` |
| A text as a number | `to_number(@.qty)` — see the limits below |
| A value as text | `to_string(@.id)` (numbers without an exponent, whole numbers without decimals) |
| A timestamp in UTC | `to_utc(@.created)` (or `rfc3339_normalize` to keep the offset) |
| Is it empty? | `is_empty(@.name)` is true for a missing, null or empty value; `is_empty(@.qty, True)` counts a 0 as empty too (by default 0 is a valid number) |

> **`to_number` reads only a plain decimal**: an optional sign, digits and a fraction after a dot
> (`-12`, `3.75`, `.5`), with spaces around it ignored and at most 20 digits before the dot and 18
> after. An empty text gives nothing (null). An exponent (`1e3`), thousands separators (`1,200`), a
> decimal comma (`3,5`), a currency or percent sign, or any other text is an error: the rule fails
> and is reported. Clean the text first (`replace`, `regexp_replace`) if it has any of these.

> **Patterns** (`regexp_replace`, `regexp_group`) are written in the dialect of the backend the
> project uses (Python or Oracle). The tool does not translate them: making them valid for the
> chosen backend is up to the project, and it is the one case where two backends can give different
> results.

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

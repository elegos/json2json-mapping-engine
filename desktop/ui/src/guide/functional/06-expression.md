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
| Capitals / lower case | `upper(@.name)`, `lower(@.name)` |
| Without the spaces at the ends | `trim(@.name)` |
| Part of a text | `substring(@.code, 4, 2)` (the first character is 1), `left(@.code, 3)`, `right(@.code, 3)` |
| How long | `length(@.code)` |
| Fill up to a width | `pad_left(@.n, 5, "0")` (a longer text is left as it is) |
| Does it contain / start / end with | `contains(@.code, "-")`, `starts_with(@.code, "ID")`, `ends_with(@.code, "X")` |
| Absolute value, round down / up | `abs(@.x)`, `floor(@.x)`, `ceil(@.x)` |
| A date in another format | `format_date(@.dt, "DD/MM/YYYY")` (tokens `YYYY MM DD HH24 MI SS`) |
| A date written as text, with a month name or AM/PM | `parse_timestamp(@.at, "MON DD, YYYY, HH12:MI:SS AM")` (gives `2026-03-25T16:08:12`; tokens `YYYY MM MON DD HH24 HH12 MI SS AM`) |
| Milliseconds, or no fraction | `rfc3339_normalize(@.at, 3)`, `to_utc(@.at, 0)` |
| Days between two dates, a date some days later | `days_between(@.due, @.returned)`, `add_days(@.date, 30)` |
| The part after the last separator | `split_last(@.id, "-")` |
| The texts of a list in one text | `join(@.tags, ", ")`, `join((i.name for i in $.items if i.ok), ", ")` |
| Remove a prefix | `remove_prefix(@.code, "ID-")` |
| Replace a text | `replace(@.name, "-", " ")` (leave out the replacement to remove it) |
| Replace by pattern | `regexp_replace(@.phone, "[^0-9]", "")` |
| Take a part by pattern | `regexp_group(@.ref, "([A-Z]+)-([0-9]+)", 2)` |
| Always two decimals, as text | `format_decimal(@.amount, 2)` |
| A text as a number | `to_number(@.qty)` — see the limits below |
| A value as text | `to_string(@.id)` (numbers without an exponent, whole numbers without decimals) |
| A timestamp in UTC | `to_utc(@.created)` (or `rfc3339_normalize` to keep the offset) |
| Is it one of these | `@.status in ("NEW", "OPEN")`, `@.status not in ("NEW", "OPEN")` (the list is written out, all texts or all numbers; a missing value is in none) |
| Does the text have this shape | `matches(@.id, "[A-Z]{3}[0-9]{7}")` is true when the **whole** text fits |
| Is it empty? | `is_empty(@.name)` is true for a missing, null or empty value; `is_empty(@.qty, True)` counts a 0 as empty too (by default 0 is a valid number) |

### Totals and counts

| What | Write |
|---|---|
| Count, sum, greatest, smallest, average of a list | `count($.items)`, `sum($.items, "qty")`, `max($.items, "qty")`, `min(...)`, `avg(...)` |
| Only the elements that satisfy a condition | `count(i for i in $.items if i.status == "OK")`, `sum(i.qty for i in $.items if i.status == "OK" and i.qty > 10)` |
| A value computed for each element | `sum(abs(i.qty) for i in $.items)`, `max(i.qty * i.price for i in $.items)` |
| Inside a larger expression | `round(sum(i.qty for i in $.items if i.status == "OK"), 2)` |
| Is there one / are they all | `any(i.qty > 10 for i in $.items)`, `all(i.qty > 0 for i in $.items if i.status == "OK")` |
| Compared with the others | `count(s for s in $.samples if s.value > avg(x.value for x in $.samples))` |
| Counting what has no match elsewhere | `count(l for l in $.lines if not any(any(i.ref == l.ref for i in p.items) for p in $.packages))` |

`i` is any name you choose for one element, and `i.qty` is checked against the schema. An element
whose value is missing is left out. With nothing to add up, `sum` and `count` give 0; `max`, `min`
and `avg` give nothing (the field is not written). An aggregate can be inside the condition or the value of another one, to any depth (each level goes through its list once for every element of the outer one). `any` is true when one element passes, `all` when every element does; over an empty list they are false and true, and a missing value counts as false.

> **`to_number` reads only a plain decimal**: an optional sign, digits and a fraction after a dot
> (`-12`, `3.75`, `.5`), with spaces around it ignored and at most 20 digits before the dot and 18
> after. An empty text gives nothing (null). An exponent (`1e3`), thousands separators (`1,200`), a
> decimal comma (`3,5`), a currency or percent sign, or any other text is an error: the rule fails
> and is reported. Clean the text first (`replace`, `regexp_replace`) if it has any of these.

> **`matches` takes a pattern in a portable subset**, the same on every backend: characters, `.`,
> classes `[a-z]` and `[^0-9]`, groups, `|` and the quantifiers `* + ? {n,m}`. There is no `^` or `$`
> (the whole text must fit), no `\d \w \s \b` (write `[0-9]`) and no `(?...)`. A missing value
> gives nothing. The pattern must be written in the cell, not computed.

> **Patterns are the last resort.** They are slower, and the only place where backends can differ. Use
> the functions above (`substring`, `left`, `contains`, `format_date`...) when one does the job.
>
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

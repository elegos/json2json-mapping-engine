# Lookups

A **lookup** is a small table of codes and what they stand for: country to currency, status code
to description. Define it once and use it from any rule that needs to recode a value.

## The table

```figure
{"src": "lookups.png", "alt": "The Lookups view"}
```


Open the **Lookups** view of a mapping. Each lookup has:

| Part | Meaning |
|---|---|
| **Label** | The name expressions use to refer to it: label `countryCurrency` is `@countryCurrency`. |
| **Type** | Optional: the type of every value (`str`, `int`, `number`, `bool`, `date`, `datetime`). When set, it is checked. |
| **Entries** | The rows: a key and the value it stands for. |
| **Description** | What the table is for. |

## Using a lookup

In the Expression of a rule, pass the Source's value and the table to `lookup`:

```
lookup(value, @countryCurrency, "N/A")
```

The third argument is what to give when the key is not in the table. Without it the field is left
out of the output.

## A table of your own, inline

For a handful of values you can write the table in the expression itself, without a lookup:

```
lookup(@.code, {A: 1, B: 2})
```

Use a lookup when the same table is needed in more than one place, or when it is long enough to
deserve a name and a description.

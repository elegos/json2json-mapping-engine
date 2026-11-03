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

## A table for the whole project

A table that hardly changes and that several mappings need (countries, currencies, VAT rates) is
better kept once. Tick **Project wide** under a lookup and its table moves out of the mapping into
the project; every mapping then reads it as `@label`, exactly as before. The Lookups view lists
those under **Project wide**, and says which mappings read each one. Use **+ Project lookup** to
make one from scratch.

```figure
{"src": "lookups-wide.png", "alt": "A project-wide lookup in the Lookups view"}
```

- A project-wide table is edited in one place, with **Save**. A label is chosen when it is created
  and does not change afterwards.
- **When it changes**, the rules that read it, in every mapping, go back to **To review** if they
  were validated, and each gets a note saying what changed since the last validation, for example
  `@countryCurrency changed (2026-10-05): added DE = 'EUR'`. The reviewer sees at once what to
  check. Rules that were never validated are left alone.
- A mapping cannot also have a lookup with the same label: the Check says so, and the one in the
  mapping has to go.
- A table that mappings read cannot be deleted. Clear **Project wide** instead: every mapping that
  reads it gets its own copy of the table, and the project's file is removed.
- Because the mapping is read again after these changes, the tool asks you to save it first.

## A table of your own, inline

For a handful of values you can write the table in the expression itself, without a lookup:

```
lookup(@.code, {A: 1, B: 2})
```

Use a lookup when the same table is needed in more than one place, or when it is long enough to
deserve a name and a description.

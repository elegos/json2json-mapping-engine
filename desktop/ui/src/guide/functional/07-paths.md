# Paths

The **Paths** view holds two things that save typing long paths.


```figure
{"src": "paths.png", "alt": "The Paths view"}
```

## Aliases

An alias is a short name for a path of the input. If `metadata` stands for `$.metadata`, a rule
can read `@metadata.source` instead of `$.metadata.source`.

An alias can also name **one element of a list**, chosen by a condition:
`totals` = `$.items[marker = 'TOTALS']`. Then `@totals.qty` is the `qty` of the first element
that satisfies it, and empty when none does
(see [choosing an element](page:functional/source)).

An alias name cannot be the name of a lookup, of a loop label, or `root` or `index`.

## What `$` means

Paths are written from the real root of the document. When the data you map sits under a fixed
part of it, set that part in **$ means**: in every rule, `$` then stands for that path. `@root`
always reaches the real root.

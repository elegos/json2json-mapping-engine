# Paths

The **Paths** view holds two things that save typing long paths.

## Aliases

An alias is a short name for a path of the input. If `metadata` stands for `$.metadata`, a rule
can read `@metadata.source` instead of `$.metadata.source`.

An alias name cannot be the name of a lookup, of a loop label, or `root` or `index`.

## What `$` means

Paths are written from the real root of the document. When the data you map sits under a fixed
part of it, set that part in **$ means**: in every rule, `$` then stands for that path. `@root`
always reaches the real root.

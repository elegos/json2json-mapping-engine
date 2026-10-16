# Input and output checks

A mapping can refuse a message before any rule runs, or check what it wrote. That is the
**Validations** tab; its title shows how many validations each side has, for example
*Validations (I: 2, O: 1)* (the JSON Schema check counts as one).

```figure
{"src": "validations.png", "alt": "The Validations view with an input check"}
```

There are two sides: **Input**, checked before the first rule, and **Output**, checked after the last.
Each has:

- **Validate against the mapping's JSON Schema**: off by default, because the system that calls the
  mapping may already do it. It is best effort: the Oracle validator does not look at `format`, so use
  a check where exactness matters.
- **Checks**: an expression on `$` (the input, or on the output side the output) that must be **true**.

| Column | Meaning |
|---|---|
| Id | Names the check. Unique in the mapping, both sides together. |
| Expect | The condition, in the same language as an expression. |
| Code | What the report carries, and what a golden case expects. Unique in the mapping. |
| Message | Said to the caller; the code when left empty. |
| Action | **reject**: the message runs no rule and has no output. **warn**: it only adds to the report. |

Expect has the same suggestions as an Expression: `$.` lists the fields of the document being checked
(the output's on the Output side), and the functions and `@lookups` are offered too.

Only a true condition passes, and a comparison with a missing value is not true. For an optional
field write what a missing value means: `not $.vatId or length($.vatId) == 11`.

A rejection refuses the whole message. To skip one element of a list use the *Filter* of a loop
instead.

## Golden cases

A case that expects a rejection lists the codes in **Expected rejected** (`["REQ-16"]`), and one that
expects warnings in **Expected warnings**. The result of a run shows the checks that failed and fails
the case when they are not the expected ones.

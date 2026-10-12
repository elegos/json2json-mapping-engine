# Conventions to look for

A checklist of what differs between documents. Use it to know **what to look for and ask**; a
document may have conventions that are not listed (record them as new topics). Each topic: where to
look, and the question when the evidence is not enough. Store the result in the profile
(`profile.md` in the engine's `docs/import/` lists the topic names).

| Topic | Look in | Ask when |
|---|---|---|
| Index base (per context: code, prose, positional rows) | a conventions section, rules using `[0]`/`[1]`, "the first", samples next to a rule | two bases appear, or the same element is `[2]` and `[3]` in different places; never decide by habit |
| Array notation | rule paths: `[]`, `[*]`, no brackets, filters `[x = 'v']` | it is unclear whether one element, all, or a subset is meant |
| Path separator, root, name case | header notes ("all paths relative to ..."), sample payloads | prefixes differ between rows |
| Null / empty / absent | general rules, notes, "omit", "do not send", "N/A", "—" | the document uses several words and never says if they differ; what is sent when a mandatory source is missing |
| Mandatory vocabulary | the mandatory column or notes | a value is undefined (`C`, `?`), or "N" with "reject if null" |
| Scope of a condition | band titles, section headings, indentation, merged rows | a condition could bind the row, the section or the message |
| Concatenation and optional parts | `||`, `+`, `concat`, "separated by" | a part can be empty: what happens to its separator |
| Dates and numbers | format tokens, examples, "UTC", "ISO", decimal separators | source vs target format is not stated; timezone handling |
| Delimiters in composite values | "before/after the n-th delimiter", `split(...)[n]` | the delimiter can repeat or the side is unclear |
| Lookups | "decode with", table names, another sheet/file | the table is not in the document; no default for an unknown key |
| Formatting that may mean something | fill, strike-through, font colour, bold; legend | no legend and the marker changes the reading (removed? changed? to confirm?) |
| Removed / not mapped | "do not map", strike-through, empty rule next to a field | a removed field still has a rule |
| Version | file name, version sheet, column, header | sources disagree |
| Review dialogue | text like `<name> (date): ...` beside a rule | a question has no answer; two answers disagree |
| Global rules | general-rules sheet, intro, last section | a global rule conflicts with a row's own rule (the row's own rule is more specific; ask when not obvious) |
| Rule unit | header row, repeated pattern | a row holds a target field, a source node, or a continuation of the previous row |
| Language and register | everything | the language differs between parts of the document |

Evidence ranks: a statement in the document > a convention seen in several rules > a convention seen
once > what the reader would assume. Record the rank in `basis` (`document_evidence`, `inferred`,
`default`) and let the user confirm what is not a statement.

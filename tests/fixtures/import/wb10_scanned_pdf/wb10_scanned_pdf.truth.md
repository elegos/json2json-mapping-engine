# WB10 - Truth file: image-only (scanned) PDF, hostile on purpose

`ParcelLabel_rules_scan.pdf` has **no text layer** (a rotated, noisy raster of a table). There are no schemas. A text extractor returns nothing.

Expected behaviour of the reader, in order:
1. Detect that the document has no extractable text -> **say so** (`coverage.not_imported[].reason = "unreadable"`), never produce rules from nothing.
2. If an OCR capability exists: run it, mark every rule `confidence <= low` (OCR errors), and ask the user to confirm the transcription before interpreting.
3. Otherwise ask the user for a text version of the document (or to paste the table).

If the text is available, the content is (title "Parcel label mapping - rules", version **1.2**, "fields not listed are not sent"):

| Target | Rule | Intended reading (hidden schema: input `parcel{tracking, weightKg, flags[], dest{city}, express, items[]}`, output `label{...}`) |
|---|---|---|
| label.id | Copy parcel.tracking, remove the first 2 characters | `tracking[2:]`; "first 2 characters" = a prefix of length 2 (0-based slicing, not "from the 2nd"). |
| label.weightG | parcel.weightKg times 1000 | number; no rounding stated. |
| label.fragile | true if parcel.flags contains the value F, otherwise false | boolean, never omitted. |
| label.city | parcel.dest.city in capitals | upper-case. |
| label.service | if parcel.express is true then EXP, otherwise STD | `express` absent counts as not true. |
| label.parts | number of elements of parcel.items | 0 for an empty/missing list. |

There are no test files: this fixture checks behaviour (refusal to invent), not output.

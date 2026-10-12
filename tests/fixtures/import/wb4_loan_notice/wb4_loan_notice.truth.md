# WB4 - Truth file (styles D + I merged): library loans -> reminder notice

Workbook: `LoanReport_to_Notice_Mapping.xlsx` (sheets `NoticeMapping`, `Revision`).
Schemas: `wb4_loan_notice.input.schema.json`, `wb4_loan_notice.output.schema.json`. Tests: `tests/case1..3`.

## 0. Global conventions (resolved)

| Topic | Correct reading |
|---|---|
| Layout | Coloured full-width rows are **sections**; each section produces **at most one note** (or one note per element for the loop sections) inside `body.notes.items[]`. The three rows of a section (seq / qual / text) are the three fields of the same note. |
| Conditions | The condition of a section is written **only in its title**; it applies to every row of the section. Sections 1-2-3-4-5 are evaluated independently, except where a title refers to another section ("overdue present"). |
| `—` in the source column | "No source" (constant). |
| `Fixed = n` | JSON integer for `seq`; quoted values are strings. `DataType: Number/BOOLEAN` are JSON number/boolean. |
| Path separators | ` / ` (spaced slash) in the source column is a JSON path: `LoanReport / Patron / Tier` = `loanReport.patron.tier`. |
| Array notation | `Items[]`, `Fines[]` = every element (loops); `Fines[0]` = first element, **0-based**; "1st fine" in prose = the same element. |
| Index base | 0 in code-like paths (`[0]`), 1 in prose ("1st"). They point to the same element. |
| Null / empty / absent | Equivalent. `ReturnedDate`, `Reference`, `Tier`, `Title`, `HttpCode` may be `null`, `""` or missing. Output never contains `null`. |
| Date dialects | Source `GeneratedAt`: `MMM d, yyyy, h:mm:ss a` (English month abbreviation, 12-hour clock). No time zone is given: **treat it as UTC** (assumption). Target `reportTime`: `yyyy-MM-ddTHH:mm:ssZ`. Target `printStamp`: `DD-MM-YYYY HH24:MI:SS.FF` = `dd-MM-yyyy HH:mm:ss.` + **two zero digits** (`.00`). |
| "report date" | = the **date part of `GeneratedAt`** (answered in the review thread). There is no `ReportDate` field in the schema. |
| Lookup `Patron Tier` | Table missing from the workbook. Correct content: `STD -> 1`, `GOLD -> 2` (integers). Key not found or null => **omit** `tierLevel`. |
| Order of notes | Sections in the order Seq 1, 2, 3, 4/5; inside a loop section, source order. |
| Blue font / red font | Blue = example text; red = unanswered reviewer question. No functional meaning. |

## 1. Rules

| Section / row | Target | Correct interpretation | Assumptions / deliberate ambiguity -> resolution |
|---|---|---|---|
| Header 1 | `messageId` | `"LN|" + reportId`. | "Concat fixed text" prose form; the pipe is part of the value. |
| Header 2-4 | `queueId`, `priority`, `keepOrder` | `"NOTICE_QUEUE"`, `0`, `true`. | - |
| Body 1 | `body.channel` | `"MAIL"`. | `map value 'MAIL'` = constant. |
| Body 2 | `body.reportTime` | Parse `GeneratedAt`, print `yyyy-MM-ddTHH:mm:ssZ`. | **Ambiguity:** timezone of the source. Resolution: UTC. Example `4:08:12 PM` -> `16:08:12`; `12:05:00 AM` -> `00:05:00`. |
| Body 3 | `body.printStamp` | Same instant printed `dd-MM-yyyy HH:mm:ss.00`. | The note "UTC" confirms no conversion. `FF` (fraction) is always `00` because the source has no fraction. |
| Body 4 | `body.patronCard` | `patron.cardNo`. | - |
| Body 5 | `body.tierLevel` | Lookup, see section 0. | Lookup table missing and no default; open dialogue answered with "wait for the table": until then `STD`/`GOLD` as above, anything else omitted. |
| Body 6 | `body.currency` | `fines[0].currency`; omit if there are no fines. | Written `Fines[0]` (code) and "1st fine" (prose): same element. Currency of later fines is ignored. |
| Seq 1 (3 rows) | note `seq=1`, `qual="LOAN REF"`, `text=loan.reference` | Emitted only if `loan.reference` has a value. | Title says "always - if present": it means **conditional on presence**. |
| Seq 2 (3 rows) | note `seq=2`, `qual="OVERDUE"`, `text=<days>` | Emitted only if `returnedDate` has **no value** **and** `dueDate` is **strictly earlier** than the date part of `generatedAt`. `<days>` = whole calendar days between them as a string (`2026-03-20` vs `Mar 25` -> `"5"`). | Condition only in the title. "before report date" is strict (same day = not overdue). The merged cell of two source paths = both inputs of one computation. |
| Seq 3 (3 rows) | one note per fine: `seq=3`, `qual="FINE"`, `text=<amount> <currency>` plus ` (<reasonCode>)` if reason has a value | Emitted only if Seq 2 was emitted (**"overdue present"** = the OVERDUE note exists) and for each fine in order. | **Ambiguity:** `seq` for each loop item: constant `3` or incremented? Resolution (as written): **constant 3** for all items (the open reviewer question has no reply). Amount text = the JSON number as written (`1.5` -> `1.5`, `2` -> `2`; no forced decimals). Separator is a single blank. Reason in brackets only when present. |
| Seq 4 (3 rows, source cell merged vertically) | one note per item: `seq=4`, `qual="ITEM"`, `text=barcode + "|" + title` | Emitted only when `processingErrors` is **null/absent**, for each item whose `status` is **not** `RETURNED`. | **Ambiguity:** items with `status = null`. Resolution: `null != 'RETURNED'` is true => included. Title empty -> literal `NO TITLE`. |
| Seq 5 (3 rows) | note `seq=5`, `qual="ERROR"`, `text=httpCode` if it has a value else `code` | Emitted only when `processingErrors` is present (object). | Seq 4 and Seq 5 are **mutually exclusive**; Seq 1-3 are independent of errors. |
| (whole) | `body.notes` | If no note was emitted the key `notes` is **omitted**. | `items` is never an empty array. |

## 2. Revision sheet
Two entries, dates in two formats (`2026-03-04`, `12/03/2026`); no version discrepancy in this workbook.

## 3. Test coverage
- `case1`: overdue loan, two fines (with / without reason), items with and without title/status, tier GOLD. Notes: seq 1, 2 (`"5"`), 3, 3, 4, 4.
- `case2`: **null / else cases**: no reference, loan returned, no tier, no fines, only returned items => `notes` omitted; `12:05:00 AM` midnight edge.
- `case3`: `processingErrors` present with `httpCode = null` -> `code` used; Seq 5 instead of Seq 4; not overdue; tier `STD`.

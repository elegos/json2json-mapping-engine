# WB1 - Truth file (style A): reservations -> housekeeping task event

Workbook: `Mapping_ReservationToTask_v02.xlsx` (sheet `Mapping`, sheet `Version`).
Schemas: `wb1_reservation_task.input.schema.json`, `wb1_reservation_task.output.schema.json`.
Tests: `tests/case1..3`.

## 0. Global conventions (resolved, never stated in the workbook)

| Topic | Correct reading |
|---|---|
| Output envelope | One object; `batch.entries` has exactly one element; every rule in the Body band writes into `batch.entries[0].content`. Header-band rules write at the top level. |
| Index base | In code-like expressions (`rooms[0]`) the base is **0**. In prose ("1st room") and in the positional-part rows `extra1[1]`, `extra1[2]` the base is **1** (these are *segments of one string*, not array indices). |
| `[]`, `[*]`, no brackets | Each means "every element, in source order" (loop). `rooms[0]` is the first element only. A path through an array without brackets (`reservation.notes.text`) means "for each element". |
| Null / empty / absent | Treated identically: JSON `null`, `""`, and a missing key all mean "no value". Output never contains `null`; an optional target field with no value is **omitted**. |
| Mandatory column | `Y` / `Y ` (trailing blank is noise) = mandatory in the target; `N` = optional. Mandatory fields are always produced here because their sources are mandatory in the input schema. |
| Date dialects | `YYYYMMDDHH24MISS` = 14 digits `yyyyMMddHHmmss`. `UTC` in the Notes column = **convert the value to UTC** and print ISO-8601 with literal `Z`, no milliseconds. |
| Concatenation `a||'-'||b` | `||` is plain string concatenation. Unbalanced quotes in the cells are typos; the literal text between quotes is the constant. |
| Lookup table `roomtypelist` | Not in the workbook. Correct content: `STD -> 10`, `DLX -> 20`, `STE -> 30`. Key not found, null key => **omit target field** (no default). |

## 1. Rules (row numbers refer to sheet `Mapping`)

| Row | Target | Correct interpretation | Implicit assumptions / deliberate ambiguity -> resolution |
|---|---|---|---|
| 4 | `senderMessageId` | First 12 characters of `msgId`. | "Cut to 12 chars" = keep the first 12 (truncate on the right). Shorter ids are kept whole. |
| 5 | `queueId` | Constant `"Q.HOUSEKEEPING"`. | - |
| 6 | `priority` | Constant number `0`. | Note "Type : number" means JSON number, not string. |
| 7 | `keepOrder` | Constant boolean `true`. | Trailing blanks in the cells are noise. |
| 11 | `domain` | Constant `"D"`. | - |
| 12 | `level` | Constant `"ROOM"`. | Double blank after `=` is noise. |
| 13 | `statusCode` | `"S." + status` and, only if `cleaningLevel` has a value, `"-" + cleaningLevel`. | **Ambiguity:** optional second part with no separator rule. Resolution: when `cleaningLevel` is empty the dash is **also dropped** (`S.NEW`, not `S.NEW-`). Unbalanced quote in the cell is a typo. |
| 14 | `occurredAt.value` | `sentAt` parsed as `yyyyMMddHHmmss`, interpreted as **UTC**, printed `yyyy-MM-ddTHH:mm:ssZ`. | **Ambiguity:** is "Date format" the source or the target format? Resolution: source format; target is ISO-8601 with `Z`. |
| 15-16 | `locationId` | Only if `hotelCode` has a value: `"L." + hotelCode`, plus `"-" + rooms[0].number` if the first room has a number. Otherwise omit the field. | Rows 15 and 16 are **one rule** (vertical merge = continuation of the expression). **Ambiguity:** the note "dont send only the 'L.' prefix" does not say what happens if only the room number is missing. Resolution: field is still sent as `L.<hotelCode>` (no dash). Reviewer thread (answered): only the first room is used. Yellow fill = "attention", no further meaning. |
| 17-18 | `contactName` | `familyName + ", " + givenName` when both have values; if only one has a value, send **that value alone** (no comma); if neither, omit. | One rule over two merged rows. **Ambiguity:** "familyName and givenName are null" - both null vs. either null. Resolution: omit only when **both** are empty. |
| 19-20 | `extra1` | One string: `channel + "-" + number`, then `"|" + hotelCode` if `hotelCode` has a value. | `[1]`, `[2]` are **1-based positional segments** of the same target field, delimited by `|`. **Ambiguity:** row 20 says optional, no rule for the delimiter. Resolution: if segment 2 is empty there is **no trailing `|`**. |
| 21 | `extra3` | `roomtypelist[rooms[0].type]`. | `[0]` = 0-based first element. Lookup table missing in the workbook; key unknown => omit. **Open question without reply** in the Comments cell (red font); the correct answer is "omit". |
| 22 | `extra5` | If `status = "CANCELLED"` then `"CXL"`, otherwise **omit**. | Condition in prose, no else branch: implicit else = field absent. |
| 23 | `extra10` | Constant `"RSV_EVENT"`. | - |
| 24 | `extra20` | `channel + "-" + number`. | Same value as segment 1 of `extra1`. |
| 25 | `extraDate1.value` | `stay.arrival` converted to **UTC**, `yyyy-MM-ddTHH:mm:ssZ`. | **Ambiguity:** the note only says "UTC". Resolution: convert (do not preserve the offset). E.g. `14:00+01:00` -> `13:00Z`. |
| 26 | `extra15` | **Not mapped.** | **Deliberate reference to a field that does not exist** in the input schema (`reservation.loyalty.number`); the reviewer remark (unanswered) says so. The target schema has no `extra15`; implementers must not emit it. |
| 27 (band) | loop | The band text carries the loop condition: iterate over `reservation.notes[*]` and keep only notes with `type = "HK"`. | Condition lives **only in the band title**; it applies to rows 28-30. Comparison is exact, case-sensitive. |
| 28 | `memos.items[].memoNo` | Running number of the **emitted** items, starting at **1**. | "Use sequence" = consecutive counter, no gaps. |
| 29 | `memos.items[].memoKind` | Constant `"R.HK NOTE"`. | - |
| 30 | `memos.items[].memoText` | `notes.text` of the HK note. | Path without brackets = per element. **Ambiguity:** HK note with empty text. Resolution: that note is **skipped** and does not consume a sequence number. If no item remains, `memos` is omitted entirely. |

## 2. Version sheet
Dates appear in two formats (`2026-02-10`, `12/03/2026`); both are real dates (10 Feb and 12 Mar 2026). File name `v02` and last version `0.2` agree in this workbook.

## 3. Test coverage
- `case1`: all branches with values; two HK notes plus one INFO note; two rooms (only first used); offset `+01:00` converted to UTC.
- `case2`: nulls everywhere (`hotelCode`, `cleaningLevel`, room number/type, family name); empty `notes`; `Z` input; no trailing `-` / `|`.
- `case3`: **else / no-branch cases**: `CANCELLED` (rule 22 fires), unknown room type (rule 21 omits), empty-text HK note skipped, `guest = null`, negative offset converted to UTC.

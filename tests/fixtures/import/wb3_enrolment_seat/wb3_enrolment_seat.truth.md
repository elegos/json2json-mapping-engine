# WB3 - Truth file (style C): course enrolments -> timetable seats (API, one sheet per verb)

Workbook: `Enrolment_TimetableSeat_API_Mapping.xlsx` (sheets `Change_Log`, `POST`, `DELETE`).
Schemas: `wb3_enrolment_seat.input.schema.json` (field `operation` selects the sheet), `wb3_enrolment_seat.output.schema.json` (`oneOf` POST body / DELETE body).
Tests: `case1` POST, `case2` POST, `case3` DELETE.

## 0. Global conventions (resolved)

| Topic | Correct reading |
|---|---|
| Which sheet | `operation = "POST"` -> sheet `POST`; `operation = "DELETE"` -> sheet `DELETE`. |
| Paths | Source paths start at the key `enrolment` (inside the message). Target paths are relative to the body of the call. |
| Index base | Code-like `tags[0]` = **0-based**. No prose indices. |
| `[]`, `[*]`, no brackets, `[kind=...]` | `sessions[]`, `sessions[*].x` and `sessions.x` (no brackets) all mean "for every session". `tags[0]` = first only. A bracket with a condition = filter. |
| Required column | `M` = mandatory, `O` = optional, **`C` = conditional: mapped only if its source exists; never causes a reject** (this definition is *not* in the workbook). |
| Null / empty / absent | Equivalent; optional target field without value is omitted; no `null` in output. |
| Dates | `yyyy-MM-dd'T'HH:mm:ss.SSSXXX`: three millisecond digits, source offset kept, `Z` for zero offset. `yyyy-MM-dd` alone = the date **as written in the source string** (no timezone conversion). |
| Strikethrough | Struck-through rows = removed from the interface. They are **not mapped** (no explanation given in the workbook). |
| Operator precedence | In filters `AND` binds tighter than `OR`. |

## 1. Sheet POST

| Row | Target | Correct interpretation | Assumptions / deliberate ambiguity -> resolution |
|---|---|---|---|
| 3 | `senderMsgId` | `enrolment.messageId` unchanged. | - |
| 4 | `source.name` | Constant `"REG"`. | Source cell `—` = no source. |
| 5 | `sentAt` | `createdAt` printed with millis and the **same offset**. | `2026-03-01T09:00:00+01:00` -> `2026-03-01T09:00:00.000+01:00`; `Z` stays `Z`. |
| 6 | `mode` | Copy if it has a value; omit if null. | Allowed values listed in column D. |
| 8-10 | `student.campusCode/studentType/studentNumber` | Split `student.id` on `-`: part 1, part 2, and the **last** part. | **Ambiguity (repeated separator):** ids with four parts, e.g. `NORTH-UG-2024-0042`. "Trailing numeric segment" = text after the **last** `-` => `0042`. (The "after second" wording is *not* used here.) A 3-part id gives the 3rd part. |
| 11 | `primaryTag` | `tags[0]` if the array is not empty, else omit. | `[0]` 0-based; "first tag" in the comment agrees. |
| 13 | `seats[]` (filter) | Keep a session if `kind = LEC`, **or** if `kind = LAB` **and** `room` is not null. | **Ambiguity:** `A OR B AND C` without parentheses. Resolution: `A OR (B AND C)`. A LEC session without room is kept; a LAB session without room is dropped. |
| 14 | `seats[].seq` | `sessionNo`. | `[*]` = every kept session. |
| 15 | `seats[].kind` | `LEC` -> `LECTURE`; `LAB` -> `LAB`. | `ELSIF` without `ELSE`: unreachable here because the filter only lets LEC and LAB through. |
| 16 | `seats[].roomId` | `room.id` with the prefix `R.` removed (only if it starts with it). | `C` = conditional: omit when the session has no room (possible for LEC). |
| 17 | `seats[].start` | `start` in millis/offset dialect. | - |
| 18 | `seats[].end` | `end` if it has a value else **the start value**; both printed in the dialect. | `IF end IS NULL THEN start`: the *value of `start`* is used (printed in the same dialect). |
| 19 | `seatStatus` | `ACTIVE` -> `CONFIRMED`; `WAITLIST` -> `PENDING`; **anything else -> omit**. | **Ambiguity:** missing else. Resolution: field omitted (it is `O`). `DROPPED` is the tested else case. |
| 20 | `seatCount` | Number of **emitted** seats (after the filter). | **Ambiguity:** "Number of sessions" = all input sessions or filtered? Resolution: `len(seats)`. Always present (0 allowed). |
| 21-22 (struck) | `seatClass`, `printBadge` | **Not mapped.** | Strikethrough on the whole row = removed. Their sources are not in the input schema. |

## 2. Sheet DELETE

| Row | Target | Correct interpretation | Assumptions |
|---|---|---|---|
| 3 | `seatRef` | `"ENR." + enrolmentId`. | - |
| 4 | `reason` | Constant `"WITHDRAWN"`. | - |
| 5 | `effectiveDate` | First 10 characters of `withdrawnAt` (`yyyy-MM-dd`) **as written**; omit if null. | "Preserve timezone": `2026-04-02T23:50:00-04:00` -> `2026-04-02` (not converted to UTC, which would give 04-03). `C` = conditional. |

## 3. Change_Log
Four versions; dates in four formats (date cell, `17/07/2026` = 17 Jul, `20260813` = 13 Aug, `2026-09-21`). The entry "Line 14 seat kind, line 16 seat status" cites **row numbers that do not match** the current sheet (kind is row 15, status row 19): stale, informational only.

## 4. Test coverage
- `case1` (POST): four-part student id, two tags, LEC + LAB with rooms, third session LAB without room (filtered out), `ACTIVE`.
- `case2` (POST): **nulls and else branch**: `mode = null`, empty tags, LEC without room (kept, no `roomId`), `end = null` (end := start), `DROPPED` (no `seatStatus`), `Z` offset, three-part id, negative offset.
- `case3` (DELETE): date as written despite negative offset.

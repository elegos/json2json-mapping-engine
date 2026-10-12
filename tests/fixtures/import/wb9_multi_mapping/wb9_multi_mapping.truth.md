# WB9 - Truth file: two mappings in one workbook, conventions declared up front, lookups present

`Interface_Specification_v3.xlsx`: sheets `ReadMe`, `General rules`, `Map_Customer`, `Map_Returns`, `Lookups`, `History`.
Version: file name `v3` = last row of `History` (`3.0`) - consistent. Subfolders `customer_to_contact/` and `return_to_credit_note/`
hold the schemas (provided) and tests of each mapping. **Expected behaviour: the reader lists the two mappings and asks which to
import (or both in sequence).**

## Document-wide conventions (not in the mapping sheets - must be found in `ReadMe` / `General rules`)
| Source | Convention |
|---|---|
| ReadMe | array indices start at **1**; input dates `dd/MM/yyyy`, output `yyyy-MM-dd`; empty = absent/null/"" = field not sent; orange cell = to be confirmed |
| G1 | every input string is trimmed before anything else (applies to all rules; not repeated in the rows) |
| G2 | an output field without value is omitted |
| G3 | table lookups are case-insensitive |

## Map_Customer
| Target | Reading | Notes |
|---|---|---|
| contactId | trimmed `code` | trim comes from G1. |
| fullName | `upper(surname) + " " + firstName` (both trimmed) | "SURNAME First". |
| birthDate | `dd/MM/yyyy` -> `yyyy-MM-dd`; omitted when absent/empty | G2 + date convention from ReadMe. |
| primaryEmail | first email with `type == "W"`, else the first of the list (`emails[1]`), trimmed; omitted if none | "the first" = element 1 (1-based, declared elsewhere). |
| countryCode | COUNTRIES lookup of `country`, case-insensitive; not found -> `ZZ` | Table in `Lookups` (United Kingdom/France/Germany/Spain). |
| isCompany | `vatNumber` has a value | empty string and null = false (meaning of "empty" in ReadMe). |
| segment | `>= 100000` A; `>= 10000` B; else C; absent -> C | **orange cell** (to confirm): boundaries inclusive as written. |

## Map_Returns
| Target | Reading | Notes |
|---|---|---|
| noteNo | `"CN-" + trimmed number` | - |
| date | `dd/MM/yyyy` -> ISO | - |
| lines[] | one per `items` element, same order; empty list -> empty `lines` | - |
| lines.row | running number from **1** | "from 1" in the note; consistent with ReadMe. |
| lines.sku | trimmed `code` | - |
| lines.qty | `abs(quantity)` | negative in input (note). |
| lines.reasonText | REASONS lookup of `reason`, trimmed; missing/unknown -> `"Other"` | **orange cell**; here the default is always present (never omitted), unlike G2 - the row's own rule wins. |
| totalQty | sum of the output `qty` (after `abs`) | rule has no source column. |

Tests: `customer_to_contact/case1` (all branches, spaces, work email second), `case2` (unknown country, no email match, revenue
exactly 10000, no birth date), `case3` (empty strings, no emails, no revenue). `return_to_credit_note/case1` (negative quantity, unknown
reason, missing reason, trim), `case2` (date edge), `case3` (no items).

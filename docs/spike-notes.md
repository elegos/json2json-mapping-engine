# M0.5 — Oracle/PL-SQL runtime spike notes

Container: `container-registry.oracle.com/database/adb-free:latest-23ai` (Oracle
Autonomous Database Free 23ai), run via Docker. Connected with plain SQL*Net on
port 1521 (service `myatp`) for spike purposes — the image also exposes a
TLS/wallet-based listener on 1522 for production-like use, not needed here.

Startup requires `ADMIN_PASSWORD` and `WALLET_PASSWORD` env vars (12-30 chars,
upper+lower+digit; **must not contain the literal substring "admin"** — the
image's own password verifier rejects e.g. `SpikeAdmin123` for this reason,
and reports the generic length/complexity error message regardless of which
check actually failed, which is misleading until you read
`/u01/scripts/password_verifier.py` inside the image).

This spike ended up folded into building M2a (the compiler emits real PL/SQL
that was deployed and run against this same container) rather than being a
separate hand-written package — the findings below came from that combined
exercise and are the ones that matter for the compiler design.

## Findings

### 1. Twin-procedure pattern, two/three-way return semantics — confirmed as designed

Implemented via one nested `FUNCTION fn_<rule_id>` per field rule (lexically
nested inside the enclosing procedure's declare section, giving it direct
visibility of `v_srcroot` and enclosing loop variables without parameter
passing), called from a per-rule guarded block. Verified end-to-end:

- `return <expr>` → field present with value.
- `return Null` → PL/SQL `RETURN NULL;` → field present, JSON `null`.
- bare `return` → implemented as `RAISE e_field_omitted;`, caught by a
  dedicated `WHEN e_field_omitted THEN NULL;` handler at the call site
  *before* `WHEN OTHERS` → field genuinely absent from the output. This is a
  different mechanism than the architecture doc's illustrative two-flag
  (`v_..._skip` / `v_..._is_null`) snippet, but produces identical observable
  behavior and is simpler to generate correctly.
- `map_<id>_safe` returns partial `p_out` (whatever fields succeeded) plus a
  full, untruncated `p_err` JSON array, and never raises.
- `map_<id>` raises exactly once, at the end, with every accumulated failure
  described in the payload — confirmed a caller never receives a partial
  `p_out` when it exits via unhandled exception (PL/SQL does not copy `OUT`
  params back on unhandled exception, as the architecture assumed).

### 2. `RAISE_APPLICATION_ERROR` payload byte budget — architecture assumption was incomplete, fixed in codegen

This is the important finding. Tested by raising a 20-entry payload with
realistic rule ids and Oracle error text (`ORA-01722: invalid number...`)
against the live container:

| Retrieval method | Observed cap on a message > ~2000 bytes | Result |
|---|---|---|
| `SQLERRM` | **512 bytes** (hard Oracle limit) | JSON cut mid-string — **invalid** |
| `DBMS_UTILITY.FORMAT_ERROR_STACK` | ~1899 bytes for that specific test | still character-truncated, not entry-truncated |

Neither retrieval path truncates at a JSON boundary — they just cut the
character stream. The architecture doc's "~2048-byte" figure describes
Oracle's message buffer roughly correctly (closer to `FORMAT_ERROR_STACK`'s
behavior than to `SQLERRM`'s), but assumed the *compiler's* 20-entry cap alone
would keep the message under that ceiling. It doesn't: 20 entries of
realistic rule ids + Oracle error text measured 2766 bytes in the stress test
below — well past even the more generous ~1899-byte ceiling.

**Fix applied in `compiler/backends/plsql/codegen.py`** (already reflected in
the golden fixtures, not a follow-up): the generated code now measures the
candidate payload with `LENGTHB` while building the `errors` array and stops
adding entries — before the 20-entry cap, if necessary — once the next entry
would push the payload past a conservative `_ERROR_PAYLOAD_BYTE_BUDGET = 1800`
bytes. `shown` always reflects the true number of entries actually included,
so the truncation stays self-describing per the architecture's requirement,
and the emitted JSON is always complete and parseable.

Verified with a 25-rule stress fixture (`/tmp/stress_errors.map.py`, all 25
rules failing with `ORA-01476: divisor is equal to zero`, run against the
container): `total_errors=25`, `shown=20` (20-entry cap was the binding
constraint in this case, at ~1429 bytes — comfortably under the 1800-byte
budget), and the resulting JSON parses cleanly with `JSON_VALUE`.

**Caller-side consequence to document for the build/runtime integration
(M3/M4):** a caller catching `map_<id>`'s exception must read the message via
`DBMS_UTILITY.FORMAT_ERROR_STACK`, never bare `SQLERRM` (which will silently
truncate any non-trivial payload to 512 bytes). Even `FORMAT_ERROR_STACK`
appends an `ORA-06512: at "<schema>.<procedure>", line N` backtrace line
*after* the JSON payload — callers must extract the JSON body (starts right
after the `ORA-<code>: ` prefix, ends at the matching closing `}`) rather than
assuming the whole stack string is valid JSON on its own.

### 3. `VARCHAR2(n CHAR)` / `CLOB` sizing rule not yet exercised

M2a's codegen defaults every `str` field to `VARCHAR2(4000 CHAR)` (no JSON
Schema is threaded into the backend yet — see the codegen module docstring).
The actual `maxLength` ≤ 4000 → sized `VARCHAR2`, else `CLOB` rule
(§Type system) needs a dedicated check once schema info reaches the Code
Generator (M2b/M3): specifically, whether Oracle's `VARCHAR2` *function
RETURN type* restriction (no size constraint allowed, PLS-00263 — see finding
4 below) forces `CLOB`-returning nested functions to use `CLOB` even when the
JSON Schema would size a `VARCHAR2` for storage, given PL/SQL's own
declaration-vs-return-type asymmetry. Flagged for M2b/M3, not yet a problem
found, because it hasn't been tested end-to-end yet.

### 4. PL/SQL asymmetry: function RETURN types must be unconstrained

Not anticipated by the architecture doc, discovered via a compile error
(`PLS-00103`/`PLS-00263`) on the very first deploy attempt: a nested
`FUNCTION ... RETURN VARCHAR2(4000 CHAR)` is invalid — Oracle requires
function return types to be unconstrained (`VARCHAR2`, `NUMBER`, no size or
scale). Variable *declarations*, by contrast, require `VARCHAR2` to carry a
size. The Code Generator now maintains two separate DSL→PL/SQL type maps
(`_DSL_TO_PLSQL_RETURN` unconstrained, `_EXPECTED_TO_DECL_TYPE` constrained)
rather than one, to avoid emitting invalid procedures.

### 5. `JSON_OBJECT_T.get_*` on a missing key returns NULL, does not raise

Discovered while exercising the array/dataclass fixture with a source item
missing its `price` field: `p_itm.get_Number('price')` returned `NULL`
rather than raising. Arithmetic/comparisons on that `NULL` also don't raise
(`NULL * x` is just `NULL`). This means an *unchecked* (no-schema) read of a
missing key is silently lenient at the PL/SQL runtime level — a genuine
runtime error only surfaces from an actual type mismatch (e.g. reading a
string field with `get_Number`, → `ORA-01722`), not from a merely-absent
key. Consistent with "reads unchecked without schema" (§Input type
contract), but worth knowing precisely: "unchecked" here means "coerces to
null", not "anything goes silently including numeric operations" — no
further compiler action needed, just a runtime-behavior fact to design
Track 2 test fixtures around later.

## Not yet covered by this spike

- A dedicated case where the **byte budget**, not the 20-entry cap, is the
  binding constraint (would need either very long rule ids or long native
  error text; the stress test's 20-entry cap fired first). The truncation
  arithmetic is identical regardless of which threshold binds, so this is a
  low-risk gap, not a blocker — but worth a follow-up fixture once loop-array
  mappings (M2b) make 300+-rule mappings realistic to construct.
- Multibyte NLS_CHARACTERSET behavior for `LENGTHB` vs `LENGTH` — the budget
  check uses `LENGTHB` deliberately (byte length, matching Oracle's
  byte-based message limit), but this hasn't been stress-tested under a
  non-AL32UTF8 database character set.

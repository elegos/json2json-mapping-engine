# Validation

Validation is the developers' way of saying **this rule has been checked**. The grid shows it in
*Developer mode* only; if you do not see the column, you do not need it.

A rule is in one of three states:

| State | Meaning |
|---|---|
| **Not validated** | Nobody has checked it yet. |
| **To review** | It changed after being checked, or someone asked for a new look. |
| **Validated** | A developer verified it. |

## What puts a rule back to review

Changing the **Source** or the **Expression** of a validated rule: the code that was verified may
no longer do what you now ask. The developer sees it and checks again. Changing only the
description or the notes does not.

## Notes

The *Notes* column is free text. Use it to say what kind of check was done and when, for example
"confirmed with the business, 2026-09-22".

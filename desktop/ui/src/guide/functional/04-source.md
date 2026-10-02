# Source

The Source says **where the value comes from** in the input. The value is then available to the
Expression as `value`; if the Expression is empty, the field simply gets the Source's value.

## Paths

| Write | Meaning |
|---|---|
| `$.header.vatRate` | `$` is the **root** of the input document: always the same wherever the rule sits. |
| `@.price` | `@` is the **current element** of the nearest loop. |
| `price` | A bare name means `@.price` inside a loop and `$.price` outside one. |
| `@2.discount` | `@2` is the element of the second-nearest loop (the outer one). |
| `@order.discount` | `@label` is the element of the loop called `label`, or a lookup table of that name. |
| `@index` | The position of the current element in its loop, starting at 0. |

The tool spells a bare name out in full (`$.id`, `@.sku`) once you leave the cell, so that you
see which one it is.

## A constant

A Source can also be a **constant**: a number, `true` / `false`, `null` or a text. The field then
always gets that value, for example a version of the mapping.

## Choosing one element of a list

An **object** rule can take its content from a single element of a list by a condition:

```
$.myList[discriminator = 'MY DISCRIMINATOR' and other = $.rootElement]
```

- The first element for which the condition is true is used; if there is none, the object is
  **left out** of the output.
- The rules inside read that element as `@`.
- In the condition a bare name is a field of the element being tested, and `=` compares.

## When the Source changes

Changing a Source (or an Expression) takes away the **validated** mark from the rule: what was
checked is not what is written now. See [validation](page:functional/validation).

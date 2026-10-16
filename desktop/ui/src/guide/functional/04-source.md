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
- To take **the best** of several, add an order after the condition, as in SQL:
  `$.events[kind = 'K1' order by to_number(rank) desc]` is the one with the highest `rank`
  (`asc` is the default, `nulls first` / `nulls last` say where the elements with no key go; a
  computed key must be a number or a text the tool knows, see [loops](page:functional/loops)). The
  condition may be left out: `$.events[order by rank desc]`.
- The rules inside read that element as `@`.
- In the condition a bare name is a field of the element being tested, and `=` compares.

## Reading a field of a chosen element

The same condition can sit in the middle of a path, in a **Source**, an **Expression** or a
**guard**. The path then reads a field of the first element that satisfies it:

```
$.items[marker = 'TOTALS'].qty
```

- If no element satisfies the condition, the value is **empty** (null), as for a field that is
  missing from the data.
- The condition can ask about a **list inside the candidate**: `$.packages[any(i.ref == @2.ref for i in
  items)].vol` is the volume of the first package that has an item with the line's `ref`
  (`any`, `all`, `count`, see [Expression](page:functional/expression)). The condition can also
  end in an `order by`, as above.
- The condition can read the loop the rule is in: inside a loop over `$.lines[*]`,
  `$.prices[sku = @2.sku].price` is the price of the line's SKU (`@` is the price being tested,
  `@2` the line).
- A name for it, in [Paths](page:functional/paths), saves repeating it:
  `totals` = `$.items[marker = 'TOTALS']`, then `@totals.qty` and `@totals.currency`.
- The element is looked for **once in each rule**, however many times the rule reads it.
- A condition cannot hold another selection, and a loop's **filter** cannot use one. Read the value
  in a field of the loop instead.

## When the Source changes

Changing a Source (or an Expression) takes away the **validated** mark from the rule: what was
checked is not what is written now. See [validation](page:functional/validation).

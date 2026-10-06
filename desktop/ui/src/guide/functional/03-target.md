# Target

The Target names the part of the **output** a rule fills. It is written without a prefix, from
the point of view of the object or loop the rule sits in.

| Write | Meaning |
|---|---|
| `OrderId` | The field `OrderId` of the current object. |
| `Customer.Name` | The field `Name` inside the object `Customer`; the object is created for you. |
| `Lines[*]` | The list `Lines`: a loop over every element. |

A `$.` or `@.` in front of a Target is accepted and dropped when the file is saved.

## Rules inside a loop or an object

A rule inside a loop (or an object) names its field **relative to it**: inside `Lines[*]`, the
Target `Amount` is the `Amount` of each line.

## Creating the rules from the output schema

When the mapping has an **output JSON Schema**, the tool can create one empty rule for each of its
fields, so that only the Sources are left to write. It offers it when the schema is loaded, and
it never changes rules you already have. To do it again later (the schema grew), use **Lay out the
rules again** in the menu of the *Output schema* button: only the missing rules are added.

A rule with no Source and no Expression is shown with its own background: it is **ignored until
a Source is defined**. For a field the schema marks as `required` that is an error and the build
stops.

# The quick tour, step by step

The tour that **Help → Quick tour** runs, on a sample project: one picture for each step, with the part it frames.

## 1. A quick look around

```figure
{"src":"tour-functional-01.png","alt":"A quick look around","callouts":[]}
```

This is a sample project, only for the tour: nothing you see here is kept, and you can come back to it whenever you like.

Use Next and Back, or the arrow keys. Esc closes the tour.

## 2. Mappings

```figure
{"src":"tour-functional-02.png","alt":"Mappings","callouts":[]}
```

A project holds one or more mappings; this one has just orders. Click one to work on it. New mapping… creates another, and the pencil and cross rename or delete the open one.

## 3. Rules

```figure
{"src":"tour-functional-03.png","alt":"Rules","callouts":[]}
```

The mapping is a grid of rules, one row for each part of the output document. The tabs above it switch between the views of a mapping: Rules, Lookups, Paths, Validations and Golden. We look at each.

## 4. Target

```figure
{"src":"tour-functional-04.png","alt":"Target","callouts":[]}
```

The field of the output document this row fills. Dots go inside objects (Customer.Name); [*] marks a list.

## 5. Source

```figure
{"src":"tour-functional-05.png","alt":"Source","callouts":[]}
```

Where the value comes from in the input. $ is the document root, @ the current element of the loop the row sits in. A plain number or text, like 27, is a constant. $.parties[role = 'X'] picks the first element that satisfies a condition; add order by to pick the best of several: [role = 'X' order by rank desc].

## 6. Expression

```figure
{"src":"tour-functional-06.png","alt":"Expression","callouts":[]}
```

How the value is computed, when it is not copied as it is. Empty means “= Source value”. In an expression, value is the Source's value. Typing suggests fields, functions and the keywords (for, if, order by…); inside count(x for x in $.items), x. suggests the fields of an element. any and all ask whether one or every element satisfies a condition, matches checks the shape of a text.

## 7. Functions

```figure
{"src":"tour-functional-07.png","alt":"Functions","callouts":[]}
```

Expressions call functions, such as round, concat or lookup. The function explorer, from the ? menu, lists all you can use, with a description of each. Search for what you need and press Insert to put the call in the cell you are editing.

## 8. Objects

```figure
{"src":"tour-functional-08.png","alt":"Objects","callouts":[]}
```

An object rule builds a nested object of the output. Here Customer takes the first party whose role is CUSTOMER and is left out when there is none. The rules under it are indented, and @ is that party.

## 9. Loops

```figure
{"src":"tour-functional-09.png","alt":"Loops","callouts":[]}
```

A loop builds a list of the output from a list of the input, one element for each. The rules under it are applied to every element. Its Source is the input list, its Expression the filter that decides which elements are kept; the Source can also start from an outer loop (@2.refs[*]) or run over the parts of a text (split_list(@.notes, ",")).

## 10. Loop options

```figure
{"src":"tour-functional-10.png","alt":"Loop options","callouts":[]}
```

The gear opens everything else a loop can say: a name for its element, the order of the list (order by, with several keys, descending, empty values first or last), the number @index starts from, what to write when nothing is left (leave the list out or write an empty one) and the parallel degree. The order is applied before the filter and the numbering.

## 11. Schemas

```figure
{"src":"tour-functional-11.png","alt":"Schemas","callouts":[]}
```

The input and output JSON Schemas of the mapping. A green light means it is found and readable. Click to load or replace one; the output schema can also create the empty rules for you.

## 12. Importing a document

```figure
{"src":"tour-functional-12.png","alt":"Importing a document","callouts":[]}
```

The wizard (here) also opens “Import a document…”: it reads a functional specification (Excel, Word, PDF or text) and proposes the rules. A long document is read in batches, several at a time; the questions it cannot answer by itself appear while it works, and you review the result before it becomes a mapping.

## 13. Lookups

```figure
{"src":"tour-functional-13.png","alt":"Lookups","callouts":[]}
```

A lookup is a table of codes and what they stand for, such as country to currency. Its label is how expressions name it: the Currency rule of this mapping uses @countryCurrency, with N/A when the country is not in the table.

## 14. Paths

```figure
{"src":"tour-functional-14.png","alt":"Paths","callouts":[]}
```

Shortcuts for long paths. An alias is a short name for a path of the input, used as @name.field: here metadata stands for $.metadata, so the Channel rule reads @metadata.source. “$ means” changes what $ stands for, when the data you map sits under a fixed part of the document.

## 15. Validations

```figure
{"src":"tour-functional-15.png","alt":"Validations","callouts":[]}
```

Checks on the documents themselves. Each side can name a JSON Schema the input (or the output) must satisfy, and add checks of its own: an expression that must be true, and what to do when it is not, refuse the message or only flag it. Typing an expression suggests the fields of the document, as in the grid.

## 16. Golden cases

```figure
{"src":"tour-functional-16.png","alt":"Golden cases","callouts":[]}
```

Examples of an input and the output it must give. They are what protects the mapping when it changes. Import cases you have, or create one and write its input, expected output and expected errors in the editor. Execute all runs them and says which pass, with the reason for the ones that do not.

## 17. Save and check

```figure
{"src":"tour-functional-17.png","alt":"Save and check","callouts":[]}
```

Save writes your changes to the file; a dot on the button means there are changes not saved yet. Check tells you what is missing or wrong, and marks the rows concerned.

## 18. Help is always here

```figure
{"src":"tour-functional-18.png","alt":"Help is always here","callouts":[]}
```

The ? opens the guide, the function explorer and this tour again. The wizard next to it brings back the start window, with your recent projects.

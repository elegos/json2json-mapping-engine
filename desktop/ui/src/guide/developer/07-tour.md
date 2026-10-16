# The developer tour, step by step

The tour that **Help → Developer tour** runs, on a sample project: what is behind the grid, one picture for each step.

## 1. For developers

```figure
{"src":"tour-developer-01.png","alt":"For developers","callouts":[]}
```

This tour shows what is behind the grid: validation, manual code, functions, the project settings and the build. It runs on a sample project, and nothing is kept.

The grid itself (Target, Source, Expression) is the functional users' tour; take it from the ? menu if you want it.

## 2. Mappings

```figure
{"src":"tour-developer-02.png","alt":"Mappings","callouts":[]}
```

A project holds one or more mappings; this one has just orders. Click one to work on it. New mapping… creates another, and the pencil and cross rename or delete the open one.

## 3. Developer mode

```figure
{"src":"tour-developer-03.png","alt":"Developer mode","callouts":[]}
```

Switch it on to see what functional users do not need: the validation column, the code of each rule, and the Transpile, Build and Publish steps of the Check button. It is on for this tour.

## 4. Validation

```figure
{"src":"tour-developer-04.png","alt":"Validation","callouts":[]}
```

Not validated, To review, Validated. Changing a Source or an Expression puts a validated rule back to review. Look at the coloured edge of the rows: green is validated, amber needs a look.

## 5. Overrides

```figure
{"src":"tour-developer-05.png","alt":"Overrides","callouts":[]}
```

Unit price is a manual rule: its code was taken over and is written in the Python subset, with root and src instead of $ and @. The pane shows it next to what the tool would generate from the Source and Expression. A loop's order by is written there as sorted(array, key=…, reverse=…, nulls=…) inside the for; typing sorted( suggests the arguments, and x. inside a comprehension suggests the fields.

## 6. Functions

```figure
{"src":"tour-developer-06.png","alt":"Functions","callouts":[]}
```

Every function a mapping can call: the built-ins and the ones in the project's fn/ folder, such as first_word. Search them, read their signature and description, and insert a call in a cell or in the override you are editing. The same names work in override code.

## 7. Lookups

```figure
{"src":"tour-developer-07.png","alt":"Lookups","callouts":[]}
```

A lookup is a table of codes and what they stand for, such as country to currency. Its label is how expressions name it: the Currency rule of this mapping uses @countryCurrency, with N/A when the country is not in the table.

## 8. Paths

```figure
{"src":"tour-developer-08.png","alt":"Paths","callouts":[]}
```

Shortcuts for long paths. An alias is a short name for a path of the input, used as @name.field: here metadata stands for $.metadata, so the Channel rule reads @metadata.source. “$ means” changes what $ stands for, when the data you map sits under a fixed part of the document.

## 9. Validations

```figure
{"src":"tour-developer-09.png","alt":"Validations","callouts":[]}
```

Checks on the documents themselves. Each side can name a JSON Schema the input (or the output) must satisfy, and add checks of its own: an expression that must be true, and what to do when it is not, refuse the message or only flag it. Typing an expression suggests the fields of the document, as in the grid.

## 10. Golden cases

```figure
{"src":"tour-developer-10.png","alt":"Golden cases","callouts":[]}
```

Examples of an input and the output it must give. They are what protects the mapping when it changes. Import cases you have, or create one and write its input, expected output and expected errors in the editor. Execute all runs them and says which pass, with the reason for the ones that do not.

## 11. Project properties

```figure
{"src":"tour-developer-11.png","alt":"Project properties","callouts":[]}
```

The settings of mapper.toml: the active backend and its options, the optimizer and the compiler defaults. Changing the backend keeps the settings of the one you leave.

## 12. Save, transpile, build, check

```figure
{"src":"tour-developer-12.png","alt":"Save, transpile, build, check","callouts":[]}
```

Check verifies that what is committed still matches the sources, and reports what is wrong. Its caret lists the other steps: Transpile turns the rules into the intermediate Python code (.map.py), Build compiles it to the backend's code in the build folder, Publish writes the result to the publish folder.

mapper test runs the golden cases, from a terminal.

## 13. The guide

```figure
{"src":"tour-developer-13.png","alt":"The guide","callouts":[]}
```

The Developer book of the guide covers all this in more detail. Open it from the ?.

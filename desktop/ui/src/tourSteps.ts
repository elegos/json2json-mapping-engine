// The two quick tutorials. They run on the tutorial project (`desktop/fixtures/tour-project`,
// the `orders` mapping), so the rule ids and mapping names used here are that project's.
//
// Both tours walk the same views (Rules, Lookups, Paths, Golden), the function explorer and
// Save / Check, since both kinds of user work in them. The developer's tour spends its time on
// what only a developer has (Developer mode, validation, overrides, project settings, build) and
// gives only the overview of the rest. Every step gets the whole state of the interface from its
// tour's base plus its own, so Back and Next always show the same thing.
import type { TourDef, TourState, TourStep } from "./tour";

const base: TourState = {
  view: "rules",
  select: null,
  developerMode: false,
  showIds: false,
  explorer: false,
};

const compose = (
  id: TourDef["id"],
  title: string,
  state: TourState,
  steps: TourStep[],
): TourDef => ({
  id,
  title,
  steps: steps.map((step) => ({ ...step, state: { ...state, ...step.state } })),
});

// steps both tours have
const mappings: TourStep = {
  id: "mappings",
  title: "Mappings",
  label: "the list of mappings",
  text:
    "A project holds one or more mappings; this one has just orders. Click one to work on it. " +
    "New mapping… creates another, and the pencil and cross rename or delete the open one.",
  target: "nav",
  side: "right",
};

const lookups: TourStep = {
  id: "lookups",
  title: "Lookups",
  label: "the lookup tables",
  text:
    "A lookup is a table of codes and what they stand for, such as country to currency. " +
    "Its label is how expressions name it: the Currency rule of this mapping uses @countryCurrency, with N/A when the country is not in the table.",
  target: [".tabs", ".lookups"],
  side: "bottom",
  state: { view: "lookups" },
};

const paths: TourStep = {
  id: "paths",
  title: "Paths",
  label: "the Paths view",
  text:
    "Shortcuts for long paths. An alias is a short name for a path of the input, used as @name.field: here metadata stands for $.metadata, " +
    "so the Channel rule reads @metadata.source. “$ means” changes what $ stands for, when the data you map sits under a fixed part of the document.",
  target: [".tabs", ".paths"],
  side: "bottom",
  state: { view: "paths" },
};

const validations: TourStep = {
  id: "validations",
  title: "Validations",
  label: "the Validations view",
  text:
    "Checks on the documents themselves. Each side can name a JSON Schema the input (or the output) must satisfy, " +
    "and add checks of its own: an expression that must be true, and what to do when it is not, refuse the message or only flag it. " +
    "Typing an expression suggests the fields of the document, as in the grid.",
  target: [".tabs", ".validations"],
  side: "bottom",
  state: { view: "validations" },
};

const golden: TourStep = {
  id: "golden",
  title: "Golden cases",
  label: "the golden cases",
  text:
    "Examples of an input and the output it must give. They are what protects the mapping when it changes. " +
    "Import cases you have, or create one and write its input, expected output and expected errors in the editor. " +
    "Execute all runs them and says which pass, with the reason for the ones that do not.",
  target: [".tabs", ".golden"],
  side: "bottom",
  state: { view: "golden" },
};

export const FUNCTIONAL_TOUR: TourDef = compose("functional", "Quick tour", base, [
  {
    id: "welcome",
    title: "A quick look around",
    text:
      "This is a sample project, only for the tour: nothing you see here is kept, and you can come back to it whenever you like.\n\n" +
      "Use Next and Back, or the arrow keys. Esc closes the tour.",
  },
  mappings,
  {
    id: "rules",
    title: "Rules",
    label: "the Rules view",
    text:
      "The mapping is a grid of rules, one row for each part of the output document. " +
      "The tabs above it switch between the views of a mapping: Rules, Lookups, Paths, Validations and Golden. We look at each.",
    target: [".tabs", ".ag-root-wrapper"],
    side: "bottom",
  },
  {
    id: "target",
    title: "Target",
    label: "the Target column",
    text: "The field of the output document this row fills. Dots go inside objects (Customer.Name); [*] marks a list.",
    target: '.ag-header-cell[col-id="target"]',
    side: "bottom",
  },
  {
    id: "source",
    title: "Source",
    label: "the Source column",
    text:
      "Where the value comes from in the input. $ is the document root, @ the current element of the loop " +
      "the row sits in. A plain number or text, like 27, is a constant. " +
      "$.parties[role = 'X'] picks the first element that satisfies a condition; add order by to pick the best of several: [role = 'X' order by rank desc].",
    target: '.ag-header-cell[col-id="source"]',
    side: "bottom",
  },
  {
    id: "expression",
    title: "Expression",
    label: "the Expression column",
    text:
      "How the value is computed, when it is not copied as it is. Empty means “= Source value”. " +
      "In an expression, value is the Source's value. Typing suggests fields, functions and the keywords (for, if, order by…); " +
      "inside count(x for x in $.items), x. suggests the fields of an element. any and all ask whether one or every element satisfies a condition, matches checks the shape of a text.",
    target: '.ag-header-cell[col-id="expression"]',
    side: "bottom",
  },
  {
    id: "functions",
    title: "Functions",
    label: "the function explorer",
    text:
      "Expressions call functions, such as round, concat or lookup. The function explorer, from the ? menu, lists all you can use, " +
      "with a description of each. Search for what you need and press Insert to put the call in the cell you are editing.",
    target: ".explorer",
    side: "left",
    state: { explorer: true },
  },
  {
    id: "object",
    title: "Objects",
    label: "an object rule",
    text:
      "An object rule builds a nested object of the output. Here Customer takes the first party whose role is CUSTOMER " +
      "and is left out when there is none. The rules under it are indented, and @ is that party.",
    target: ".ag-row-selected",
    side: "bottom",
    state: { select: "cust" },
  },
  {
    id: "loop",
    title: "Loops",
    label: "a loop rule",
    text:
      "A loop builds a list of the output from a list of the input, one element for each. The rules under it are applied to every element. " +
      "Its Source is the input list, its Expression the filter that decides which elements are kept; the Source can also start from an outer loop (@2.refs[*]) " +
      "or run over the parts of a text (split_list(@.notes, \",\")).",
    target: ".ag-row-selected",
    side: "bottom",
    state: { select: "lines" },
  },
  {
    id: "loop-options",
    title: "Loop options",
    label: "the loop options button",
    text:
      "The gear opens everything else a loop can say: a name for its element, the order of the list (order by, with several keys, descending, empty values first or last), " +
      "the number @index starts from, what to write when nothing is left (leave the list out or write an empty one) and the parallel degree. " +
      "The order is applied before the filter and the numbering.",
    target: ".ag-row-selected button.loop-options-button",
    side: "left",
    state: { select: "lines" },
  },
  {
    id: "schemas",
    title: "Schemas",
    label: "the schema status buttons",
    text:
      "The input and output JSON Schemas of the mapping. A green light means it is found and readable. " +
      "Click to load or replace one; the output schema can also create the empty rules for you.",
    target: ".schema-status",
    side: "bottom",
  },
  {
    id: "import",
    title: "Importing a document",
    label: "the wizard button",
    text:
      "The wizard (here) also opens “Import a document…”: it reads a functional specification (Excel, Word, PDF or text) and proposes the rules. " +
      "A long document is read in batches, several at a time; the questions it cannot answer by itself appear while it works, and you review the result before it becomes a mapping.",
    target: '[data-tour="wizard"]',
    side: "bottom",
  },
  lookups,
  paths,
  validations,
  golden,
  {
    id: "check",
    title: "Save and check",
    label: "the Save and Check buttons",
    text:
      "Save writes your changes to the file; a dot on the button means there are changes not saved yet. " +
      "Check tells you what is missing or wrong, and marks the rows concerned.",
    target: '[data-tour="actions"]',
    side: "bottom",
  },
  {
    id: "help",
    title: "Help is always here",
    label: "the help button",
    text:
      "The ? opens the guide, the function explorer and this tour again. The wizard next to it brings back the start window, " +
      "with your recent projects.",
    target: '[data-tour="help"]',
    side: "bottom",
  },
]);

export const DEVELOPER_TOUR: TourDef = compose(
  "developer",
  "Developer tour",
  { ...base, developerMode: true },
  [
    {
      id: "welcome",
      title: "For developers",
      text:
        "This tour shows what is behind the grid: validation, manual code, functions, the project settings and the build. " +
        "It runs on a sample project, and nothing is kept.\n\n" +
        "The grid itself (Target, Source, Expression) is the functional users' tour; take it from the ? menu if you want it.",
    },
    mappings,
    {
      id: "mode",
      title: "Developer mode",
      label: "the Developer mode switch",
      text:
        "Switch it on to see what functional users do not need: the validation column, the code of each rule, and the Transpile, Build and Publish steps of the Check button. " +
        "It is on for this tour.",
      target: ".switches",
      side: "top",
    },
    {
      id: "validation",
      title: "Validation",
      label: "the Validation column",
      text:
        "Not validated, To review, Validated. Changing a Source or an Expression puts a validated rule back to review. " +
        "Look at the coloured edge of the rows: green is validated, amber needs a look.",
      target: '.ag-header-cell[col-id="validation"]',
      side: "bottom",
      state: { column: "validation" },
    },
    {
      id: "override",
      title: "Overrides",
      label: "the override pane",
      text:
        "Unit price is a manual rule: its code was taken over and is written in the Python subset, with root and src instead of $ and @. " +
        "The pane shows it next to what the tool would generate from the Source and Expression. " +
        "A loop's order by is written there as sorted(array, key=…, reverse=…, nulls=…) inside the for; typing sorted( suggests the arguments, and x. inside a comprehension suggests the fields.",
      target: ".override-pane",
      side: "top",
      state: { select: "unit" },
    },
    {
      id: "functions",
      title: "Functions",
      label: "the function explorer",
      text:
        "Every function a mapping can call: the built-ins and the ones in the project's fn/ folder, such as first_word. " +
        "Search them, read their signature and description, and insert a call in a cell or in the override you are editing. " +
        "The same names work in override code.",
      target: ".explorer",
      side: "left",
      state: { explorer: true },
    },
    lookups,
    paths,
    validations,
    golden,
    {
      id: "project",
      title: "Project properties",
      label: "the project settings",
      text:
        "The settings of mapper.toml: the active backend and its options, the optimizer and the compiler defaults. " +
        "Changing the backend keeps the settings of the one you leave.",
      target: "main fieldset",
      side: "right",
      state: { view: "project" },
    },
    {
      id: "build",
      title: "Save, transpile, build, check",
      label: "the Save and Check buttons",
      text:
        "Check verifies that what is committed still matches the sources, and reports what is wrong. " +
        "Its caret lists the other steps: Transpile turns the rules into the intermediate Python code " +
        "(.map.py), Build compiles it to the backend's code in the build folder, Publish writes the result " +
        "to the publish folder.\n\n" +
        "mapper test runs the golden cases, from a terminal.",
      target: '[data-tour="actions"]',
      side: "bottom",
    },
    {
      id: "guide",
      title: "The guide",
      label: "the help button",
      text: "The Developer book of the guide covers all this in more detail. Open it from the ?.",
      target: '[data-tour="help"]',
      side: "bottom",
    },
  ],
);

export const TOURS = { functional: FUNCTIONAL_TOUR, developer: DEVELOPER_TOUR } as const;

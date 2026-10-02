// The two quick tutorials. They run on the tutorial project (`desktop/fixtures/tour-project`,
// the `orders` mapping), so the rule ids and mapping names used here are that project's.
import type { TourDef, TourState } from "./tour";

const rules: TourState = {
  view: "rules",
  select: null,
  developerMode: false,
  showIds: false,
  explorer: false,
};

export const FUNCTIONAL_TOUR: TourDef = {
  id: "functional",
  title: "Quick tour",
  steps: [
    {
      id: "welcome",
      title: "A quick look around",
      text:
        "This is a sample project, only for the tour: nothing you see here is kept, and you can come back to it whenever you like.\n\n" +
        "Use Next and Back, or the arrow keys. Esc closes the tour.",
      state: rules,
    },
    {
      id: "mappings",
      title: "Mappings",
      label: "the list of mappings",
      text:
        "A project holds one or more mappings; this one has just orders. Click one to work on it. " +
        "New mapping… creates another, and the pencil and cross rename or delete the open one.",
      target: "nav",
      side: "right",
    },
    {
      id: "tabs",
      title: "Views of a mapping",
      label: "the views of the mapping",
      text:
        "Rules is the grid. Lookups holds the tables of codes, Paths the shortcuts for long paths, " +
        "and Golden the examples that prove the mapping gives the right output.",
      target: ".tabs",
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
        "the row sits in. A plain number or text, like 27, is a constant.",
      target: '.ag-header-cell[col-id="source"]',
      side: "bottom",
    },
    {
      id: "expression",
      title: "Expression",
      label: "the Expression column",
      text:
        "How the value is computed, when it is not copied as it is. Empty means “= Source value”. " +
        "In an expression, value is the Source's value. Typing suggests fields and functions.",
      target: '.ag-header-cell[col-id="expression"]',
      side: "bottom",
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
      state: { ...rules, select: "cust" },
    },
    {
      id: "loop",
      title: "Loops",
      label: "a loop rule",
      text: "A loop builds a list of the output from a list of the input, one element for each. The rules under it are applied to every element.",
      target: ".ag-row-selected",
      side: "bottom",
      state: { ...rules, select: "lines" },
    },
    {
      id: "lookups",
      title: "Lookups",
      label: "the lookup tables",
      text:
        "A lookup is a table of codes and what they stand for, such as country to currency. " +
        "Its label is how expressions name it: the Currency rule of this mapping uses @countryCurrency, with N/A when the country is not in the table.",
      target: ".lookups",
      side: "bottom",
      state: { ...rules, view: "lookups" },
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
      state: rules,
    },
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
      id: "golden",
      title: "Golden cases",
      label: "the golden cases",
      text: "Examples of an input and the output it must give. They are what protects the mapping when it changes.",
      target: ".golden",
      side: "bottom",
      state: { ...rules, view: "golden" },
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
      state: rules,
    },
  ],
};

export const DEVELOPER_TOUR: TourDef = {
  id: "developer",
  title: "Developer tour",
  steps: [
    {
      id: "welcome",
      title: "For developers",
      text:
        "This tour shows what is behind the grid: validation, manual code, functions and the project settings. " +
        "It runs on a sample project, and nothing is kept.",
      state: rules,
    },
    {
      id: "mode",
      title: "Developer mode",
      label: "the Developer mode switch",
      text: "Switch it on to see what functional users do not need: the validation column and the code of each rule.",
      target: ".switches",
      side: "top",
      state: { ...rules, developerMode: true },
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
      state: { ...rules, developerMode: true },
    },
    {
      id: "override",
      title: "Overrides",
      label: "the override pane",
      text:
        "Unit price is a manual rule: its code was taken over and is written in the Python subset, with root and src instead of $ and @. " +
        "The pane shows it next to what the tool would generate from the Source and Expression.",
      target: ".override-pane",
      side: "top",
      state: { ...rules, developerMode: true, select: "unit" },
    },
    {
      id: "functions",
      title: "Functions",
      label: "the function explorer",
      text:
        "Every function a mapping can call: the built-ins and the ones in the project's fn/ folder, such as first_word. " +
        "Search them, read their signature and description, and insert a call in the cell or the override you are editing.",
      target: ".explorer",
      side: "left",
      state: { ...rules, developerMode: true, explorer: true },
    },
    {
      id: "project",
      title: "Project properties",
      label: "the project settings",
      text:
        "The settings of mapper.toml: the active backend and its options, the optimizer and the compiler defaults. " +
        "Changing the backend keeps the settings of the one you leave.",
      target: "main fieldset",
      side: "right",
      state: { ...rules, view: "project", developerMode: true },
    },
    {
      id: "build",
      title: "Transpile, build, check",
      label: "the Save, Transpile, Build and Check buttons",
      text:
        "Developer mode adds two buttons. Transpile turns the rules into the intermediate Python code (.map.py), without compiling it. " +
        "Build does that and compiles it to the backend's code, in the build folder.\n\n" +
        "Check verifies that what is committed still matches the sources, and reports what is wrong. " +
        "mapper test runs the golden cases, from a terminal.",
      target: '[data-tour="actions"]',
      side: "bottom",
      state: { ...rules, developerMode: true },
    },
    {
      id: "guide",
      title: "The guide",
      label: "the help button",
      text: "The Developer book of the guide covers all this in more detail. Open it from the ?.",
      target: '[data-tour="help"]',
      side: "bottom",
      state: rules,
    },
  ],
};

export const TOURS = { functional: FUNCTIONAL_TOUR, developer: DEVELOPER_TOUR } as const;

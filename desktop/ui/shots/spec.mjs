// What to photograph for the guide, and which parts to number. `sel` is a CSS selector (or
// several): the callout's box is the smallest rectangle holding everything they match.
import { writeFileSync } from "node:fs";
import { join } from "node:path";

export const VIEWPORT = { width: 1440, height: 900 };

const column = (id) => `[col-id="${id}"]`;
const tab = (page, name) => page.click(`.tab:text-is("${name}")`);
const developerMode = (page) => page.getByLabel("Developer mode").check();
const help = async (page, item) => {
  await page.click('button[aria-label="Help"]');
  await page.click(`.help-menu li:text-is("${item}")`);
};
const selectRule = (page, target) => page.click(`.ag-row:has-text("${target}") ${column("kind")}`);

export const SHOTS = [
  {
    name: "grid",
    callouts: [
      { sel: "nav", text: "The mappings of the project and their buttons: project properties, new mapping; the open mapping can be renamed (✎) or deleted (✕)." },
      { sel: ".tabs", text: "The views of a mapping: rules, lookups, paths, validations and golden cases." },
      { sel: column("target"), text: "Target: the field of the output this row fills.", at: { x: 22, y: 90 } },
      { sel: column("source"), text: "Source: where the value comes from in the input.", at: { x: 40, y: 90 } },
      { sel: column("expression"), text: "Expression: how it is computed, when it is not a plain copy.", at: { x: 58, y: 90 } },
      { sel: ".add-menu", text: "Add a field, an object or a loop; Delete removes the selected rule." },
      { sel: ".schema-status", text: "The schemas of the mapping; green means it is found and readable. A click opens the menu to load one." },
      { sel: '[data-tour="actions"]', text: "Save writes the file; Check reports what is missing or wrong." },
    ],
  },
  {
    name: "lookups",
    setup: (p) => tab(p, "Lookups"),
    callouts: [
      { sel: ".lookup-list", text: "The mapping's lookups. The label, with an @, is the name expressions use for it." },
      { sel: ".lookup-head", text: "The label, the type of the values (optional, and checked when set) and a description." },
      { sel: ".lookup-detail table", text: "The entries: a key, and the value it stands for." },
    ],
  },
  {
    name: "lookups-wide",
    setup: async (p) => {
      await tab(p, "Lookups");
      // the table is made project wide the way a user does it
      await p.click('.lookup-list .file:has-text("@countryCurrency")');
      await p.click(".wide-flag input");
      await p.click('.modal button:has-text("Make it project wide")');
      await p.waitForSelector(".lookup-list .file:has-text(\"@countryCurrency\")");
      await p.waitForTimeout(800);
      await p.click(".lookup-list .file:has-text(\"@countryCurrency\")");
      await p.waitForSelector(".lookup-readers");
    },
    callouts: [
      { sel: ".lookup-section", text: "Project wide: the tables kept in the project, one place for every mapping." },
      { sel: ".lookup-list .file.current", text: "The table, still read as @label; a click opens it." },
      { sel: ".lookup-readers", text: "The mappings that read this table." },
      { sel: ".lookup-detail .toolbar", text: "Save writes the table; saving a change sends the rules that read it back to review." },
      { sel: ".lookup-detail .wide-flag", text: "Clear it to give each mapping its own copy again." },
    ],
  },
  {
    name: "paths",
    setup: (p) => tab(p, "Paths"),
    callouts: [
      { sel: ".paths-root", text: "What $ stands for in every rule, when the data sits under a fixed part of the document." },
      { sel: ".paths table", text: "The aliases: a short name, used as @name.field, for a longer path." },
    ],
  },
  {
    name: "golden",
    setup: (p) => tab(p, "Golden"),
    callouts: [
      { sel: ".golden button", first: true, text: "Import a case: an input, the output expected for it and, optionally, the rules expected to report an error." },
      { sel: ".golden-bar button:nth-child(2)", text: "New case: starts with an empty input, to fill in the editor." },
      { sel: ".golden table", text: "The cases of the mapping and the files each one has; a case can be renamed (✎) or deleted (✕)." },
    ],
  },
  {
    name: "golden-editor",
    setup: async (p) => {
      await tab(p, "Golden");
      await p.click('.golden-table button.link:text-is("two_lines")');
      await p.waitForSelector(".golden-editor .cm-content");
    },
    callouts: [
      { sel: ".golden-table button.link", first: true, text: "Click the name of a case to edit its files." },
      { sel: ".golden-editor .tabs", text: "The three files of the case: the input, the expected output and the expected errors. A dot marks a change not saved yet." },
      { sel: ".golden-json", text: "The file, as JSON." },
      { sel: ".golden-tools", text: "Whether the JSON is valid; Format indents it; Remove this file takes the optional files away." },
      { sel: ".golden-editor header", text: "Save writes the changed files; Revert goes back to the saved ones." },
    ],
  },
  {
    name: "golden-run",
    setup: async (p) => {
      await tab(p, "Golden");
      await p.click('.golden-bar button:has-text("Execute all")');
      await p.waitForSelector(".golden-summary");
      await p.click('.golden-table tr:has-text("failed_member") .result-badge');
      await p.waitForSelector(".golden-result");
    },
    callouts: [
      { sel: ".golden-bar button:nth-child(3)", text: "Execute all runs every case; the ▶ of a row runs just that one." },
      { sel: ".golden-summary", text: "How many cases passed." },
      { sel: ".golden-table th:nth-child(5), .golden-table td:nth-child(5)", text: "The result of each case: PASS, FAIL, or output only when the case has no expected output. Click it for the details." },
      { sel: ".golden-result > header", text: "The case, its verdict and Record as expected…, which makes the current output the expected one." },
      { sel: ".golden-errors", text: "The rules that reported an error, and why. Here the case expects exactly that." },
      { sel: ".golden-diff", text: "The output, or its difference from the expected one when they differ." },
    ],
  },
  {
    name: "developer",
    viewport: { width: 1900, height: 900 },
    setup: async (p) => {
      await developerMode(p);
      await selectRule(p, "Unit");
    },
    callouts: [
      { sel: ".switches label:nth-child(2)", text: "Developer mode: shows the validation of each rule and its code, and adds Transpile and Build." },
      { sel: ".ag-header-cell" + column("validation"), text: "Validation: not validated, to review, or validated. The coloured edge of a row says the same." },
      { sel: '[data-tour="actions"]', text: "Save, Transpile, Build and Check." },
      { sel: ".override-pane", text: "The code of the selected rule. Left: what the tool generates from Source and Expression. Right: the override, when the rule is manual." },
    ],
  },
  {
    name: "functions",
    setup: async (p) => {
      await p.click(".side-rail button");
      await p.waitForTimeout(500);
    },
    callouts: [
      { sel: ".side-rail", text: "The fn tab opens this panel over the tool (Help → Function explorer does the same); the grid keeps its size." },
      { sel: ".explorer-search", text: "Search by name or by what a function does." },
      { sel: ".explorer-list", text: "Every function a mapping can call. The grey tag tells whether it is built in or from a file of the project (fn/…)." },
      { sel: ".explorer-detail code", text: "The signature and what it returns." },
      { sel: ".explorer-detail button", text: "Insert puts the call in the cell, or the override, you are editing; Edit… (or Override… on a built-in) opens the editor." },
      { sel: ".explorer-bar button:first-of-type", text: "New function… adds a stub function to a file of the project, or to a new one." },
    ],
  },
  {
    name: "function-editor",
    setup: async (p) => {
      await p.click(".side-rail button");
      await p.fill(".explorer-search", "first_word");
      await p.click('.explorer-list button:has-text("first_word")');
      await p.click('.explorer-detail button:has-text("Edit…")');
      await p.waitForSelector(".fn-text .cm-content");
      await p.fill('.fn-call input[aria-label="Arguments"]', '["hello big world"]');
      await p.click('.fn-call button:has-text("Run")');
      await p.waitForSelector(".fn-result");
      await p.waitForTimeout(500);
    },
    callouts: [
      { sel: ".fn-bar", text: "The file being edited (a whole fn/*.fn), and Save (Ctrl+S). A text that does not parse is not saved." },
      { sel: ".fn-text", text: "The code: Python colours, and completion of function names and of @override." },
      { sel: ".fn-issues", text: "What is wrong, live: types, description, and the code each backend needs (here, none for PL/SQL yet)." },
      { sel: ".fn-call", text: "Test call: runs a function on Python, with the text as it is, with the arguments as a JSON array." },
      { sel: ".explorer", text: "The list stays beside the editor; the editor slides out from behind it." },
    ],
  },
  {
    name: "function-override",
    setup: async (p) => {
      await p.click(".side-rail button");
      await p.fill(".explorer-search", "trunc");
      await p.click('.explorer-list button:has-text("trunc")');
      await p.click('.explorer-detail button:has-text("Override…")');
      await p.waitForSelector(".fn-warning");
      await p.waitForTimeout(500);
    },
    callouts: [
      { sel: ".fn-warning", text: "A built-in override replaces the built-in in every mapping of the project: a warning, and the file can be deleted to get the built-in back." },
      { sel: ".fn-text", text: "A copy of the built-in. The @override line is what the backend writes for it: the code the project's backend gets." },
      { sel: ".fn-bar select", text: "The overrides live in their own file, fn/builtin_overrides.fn; new functions never go there." },
    ],
  },
  {
    name: "project",
    setup: (p) => p.click("button.project-properties"),
    callouts: [
      { sel: "main fieldset:nth-of-type(1)", text: "The mode and the active backend (target). Changing the backend keeps the settings of the one you leave." },
      { sel: "main fieldset:nth-of-type(2)", text: "The optimizer's settings." },
      { sel: "main fieldset:nth-of-type(4)", text: "The settings of the active backend; those marked * are required." },
    ],
  },
  {
    name: "wizard",
    start: "wizard",
    ready: ".wizard",
    callouts: [
      { sel: ".wizard-recent", text: "Recent projects: one click opens it. A greyed folder is no longer there." },
      { sel: ".wizard-actions button:nth-child(1)", text: "Open a project from a folder." },
      { sel: ".wizard-actions .primary", text: "Create a project, and its first mappings, step by step." },
      { sel: ".wizard-actions button:nth-child(3)", text: "Open this guide." },
      { sel: ".wizard-foot label", text: "Untick to skip this window at startup; the wizard button in the toolbar brings it back." },
    ],
  },
];

// --- the loop and what is typed in a cell ---

const rowOf = (index) => `.ag-row[row-index="${index}"]`;
const LINES_ROW = 8; // `Lines[*]` in the tutorial project
const gear = (p) => p.click(`${rowOf(LINES_ROW)} button.loop-options-button`);
const keyEditor = (p, n) => p.locator(".loop-options .order-key .cm-content").nth(n);
const typeKey = async (p, n, text) => {
  await keyEditor(p, n).click();
  await p.keyboard.type(text);
  await p.keyboard.press("Escape"); // closes the suggestions that typing opened
};
/** A user's choices in the loop dialog, as they would make them. */
const fillLoopOptions = async (p) => {
  await p.fill('.loop-options label:has-text("Name for the element") input', "item");
  await p.click('.loop-options button:has-text("Add a key")');
  await typeKey(p, 0, 'to_number(split_last(@.sku, "-"))');
  await p.click('.loop-options button:has-text("Add a key")');
  await typeKey(p, 1, "@.qty");
  await p.selectOption('.loop-options select[aria-label="Direction of key 2"]', "desc");
  await p.selectOption('.loop-options select[aria-label="Empty values of key 2"]', "first");
  await p.fill('.loop-options label:has-text("First number") input', "1");
  await p.selectOption('.loop-options label:has-text("When there is nothing") select', "list");
};

export const SHOTS_LOOPS = [
  {
    name: "loops",
    setup: async (p) => {
      // the filter, typed in the Expression cell of the loop; then its options
      await p.dblclick(`${rowOf(LINES_ROW)} ${column("expression")}`);
      await p.keyboard.type("@.qty > 0");
      await p.keyboard.press("Enter");
      await gear(p);
      await fillLoopOptions(p);
      await p.click('.loop-options button:has-text("Apply")');
      await p.waitForSelector(".loop-options", { state: "detached" });
      await p.click(`${rowOf(LINES_ROW)} ${column("type")}`);
    },
    callouts: [
      { sel: `${rowOf(LINES_ROW)} ${column("target")}`, text: "The loop's Target: the output list, with [*]. Its rules are indented under it." },
      { sel: `${rowOf(LINES_ROW)} ${column("source")}`, text: "Source: the input list the loop runs over, with [*]." },
      { sel: `${rowOf(LINES_ROW)} ${column("expression")}`, text: "Expression: the loop's filter. Only the elements for which it is true are kept." },
      { sel: `${rowOf(LINES_ROW)} button.loop-options-button`, text: "The gear: order, numbering, what to write when nothing is left. Hover it for a summary of what is set." },
      { sel: [`${rowOf(9)} ${column("source")}`, `${rowOf(10)} ${column("source")}`], text: "The rules under the loop read the current element as @." },
    ],
  },
  {
    name: "loop-options",
    setup: async (p) => {
      await gear(p);
      await fillLoopOptions(p);
    },
    callouts: [
      { sel: ".loop-options label:nth-of-type(1)", first: true, text: "A name for the element, so that a rule in a nested loop can say @item.sku instead of @2.sku." },
      { sel: ".loop-options .order-keys", text: "The order of the list, like SQL's order by: one key per line, a direction and where the elements with no value go. The next key breaks the ties of the one before." },
      { sel: ".loop-options label:has(input[inputmode=numeric])", first: true, text: "The number @index starts from." },
      { sel: ".loop-options label:has(select) ", first: true, text: "What the output has when no element is left: the list is left out, or an empty list is written." },
      { sel: ".loop-options .modal-buttons", text: "Apply keeps the choices; the gear then shows them in a few words." },
    ],
  },
  {
    name: "completion",
    setup: async (p) => {
      await p.dblclick(`${rowOf(12)} ${column("expression")}`);
      await p.keyboard.press("Control+A");
      await p.keyboard.type("count(i for i in $.items)");
      for (let n = 0; n < " for i in $.items)".length; n++) await p.keyboard.press("ArrowLeft");
      await p.keyboard.type(".");
      await p.waitForSelector('.cm-tooltip-autocomplete:has-text("sku")');
    },
    callouts: [
      { sel: `${rowOf(12)} ${column("expression")}`, text: "The cell being edited. i is the variable of the comprehension: its element is one entry of $.items." },
      { sel: ".cm-tooltip-autocomplete", text: "Typing i. suggests the fields of that element, with their types. The same works for $., @., a loop's label and, in override code, for src. and root.; the keywords (for, if, order by…) and the functions are suggested too." },
    ],
  },
  {
    name: "validations",
    setup: async (p) => {
      await tab(p, "Validations");
      const input = 'section[aria-label="Input"]';
      await p.click(`${input} button:has-text("+ Check")`);
      await p.fill(`${input} tbody tr:first-child td:nth-child(1) input`, "has_items");
      await p.click(`${input} tbody tr:first-child .cm-content`);
      await p.keyboard.type("count($.items) > 0");
      await p.keyboard.press("Escape");
      await p.fill(`${input} tbody tr:first-child td:nth-child(3) input`, "NO_ITEMS");
      await p.fill(`${input} tbody tr:first-child td:nth-child(4) input`, "The order has no items");
    },
    callouts: [
      { sel: ".validations .paths-help", text: "How a check reads: only a true condition passes, and a comparison with a missing value is not true." },
      { sel: 'section[aria-label="Input"] h2', text: "Input checks run before any rule, on the document the mapping reads; Output checks run after the last rule, on the one it wrote." },
      { sel: 'section[aria-label="Input"] .validation-schema', text: "Check the document against the mapping's JSON Schema." },
      { sel: 'section[aria-label="Input"] tbody tr', first: true, text: "A check of your own: an expression on $ that must be true, a code and a message for the report, and what to do when it is not: reject (no rule runs, no output) or warn." },
    ],
  },
];

// --- importing a document, with a stand-in for the assistant: what a run looks like ---

const openFile = (p, path) => p.evaluate((x) => (window.__openFile = x), path);
/** The Import screen, the way a user gets there: the wizard, the project, then the document. */
const importDocument = async (p, ctx, name = "orders_spec.txt") => {
  const doc = join(ctx.tmp, name);
  writeFileSync(
    doc,
    Array.from({ length: 100 }, (_, i) => `Requirement ${i + 1}: a rule of the mapping.`).join("\n\n") + "\n",
  );
  await p.click('.wizard button:has-text("Import a document")');
  await openFile(p, ctx.project);
  await p.click('.wizard button:has-text("Other project")');
  await p.waitForSelector(".import-view");
  if (await p.$('.modal button:has-text("Not now")')) await p.click('.modal button:has-text("Not now")');
  await p.waitForSelector('.imp-document h3:has-text("Import a document")');
  await openFile(p, doc);
  await p.click('.imp-document button:has-text("Choose")');
};
const startRun = async (p) => {
  await p.click('button:has-text("Start the import")');
  await p.waitForSelector(".imp-run-questions .imp-question", { timeout: 60000 });
};

export const SHOTS_IMPORT = [
  {
    name: "import-document",
    start: "wizard",
    ready: ".wizard",
    viewport: { width: 1500, height: 760 },
    setup: (p, ctx) => importDocument(p, ctx),
    callouts: [
      { sel: ".imp-steps", text: "The steps of an import: the document, the run, the questions, the review and the apply. You can go back to any step you have reached." },
      { sel: ".imp-document .prompt-field", first: true, text: "The document: Excel, Word, PDF or text. Nothing is sent anywhere but to the assistant you choose below." },
      { sel: ".imp-providers", text: "Which assistant reads it." },
      { sel: [".imp-document label:nth-of-type(3)", ".imp-document label:nth-of-type(4)", ".imp-document label:nth-of-type(5)", ".imp-document label:nth-of-type(6)"], text: "Optional: the profile, the name of the mapping and the two JSON Schemas. Left empty, the assistant proposes them and asks about what it cannot tell." },
      { sel: ".imp-document .modal-buttons .primary", text: "Start: a short document is read in one run, a long one in batches." },
    ],
  },
  {
    name: "import-run",
    start: "wizard",
    ready: ".wizard",
    viewport: { width: 1500, height: 760 },
    setup: async (p, ctx) => {
      await importDocument(p, ctx);
      await startRun(p);
      await p.click(".imp-expected summary");
    },
    callouts: [
      { sel: ".imp-batches", text: "A long document is read in batches, several at a time. The bar shows how far they have got, and the count how many are done and running." },
      { sel: ".imp-expected", text: "What the assistant expects the engine to lack for this document, counted before a single rule is written, with the rows that wait for each." },
      { sel: ".imp-run-log", text: "What the assistant is doing." },
      { sel: ".imp-run-questions .imp-question", first: true, text: "A question it could not answer from the document. The run does not wait: until you answer, the rules that depend on it use the proposal and are marked as guesses." },
      { sel: ".imp-run-questions .modal-buttons", text: "Send the answers: the batches that come next read them, and the rules already written are read again." },
    ],
  },
  {
    name: "import-review",
    start: "wizard",
    ready: ".wizard",
    viewport: { width: 1500, height: 820 },
    setup: async (p, ctx) => {
      await importDocument(p, ctx);
      await startRun(p);
      await p.locator(".imp-run-questions .imp-question").nth(0).locator("textarea").fill("3");
      await p.click('.imp-run-questions button:has-text("Send 1 answer")');
      await p.waitForSelector(".imp-review, .imp-questions", { timeout: 90000 });
      await p.click('.imp-steps button:has-text("Review")');
      await p.waitForSelector(".imp-list .imp-row");
      await p.click(".imp-list .imp-row");
    },
    callouts: [
      { sel: ".imp-levels", text: "The rules by confidence: high, medium, low, and guesses. Start from the ones that are not high." },
      { sel: ".imp-filter", text: "Only what needs a look: leave it ticked to review just the rules that are not high-confidence." },
      { sel: ".imp-list", text: "One row for each rule the assistant proposes, with the field it writes." },
      { sel: ".imp-detail .imp-rule", text: "The rule: where it reads, how it is computed, and what the assistant took it from." },
      { sel: ".imp-evidence-text", text: "The words of the document the rule comes from, with their location." },
      { sel: ".imp-review-buttons", text: "Accept the rule, or reject it. Nothing becomes a mapping until you apply the import." },
    ],
  },
];

SHOTS.push(...SHOTS_LOOPS, ...SHOTS_IMPORT);

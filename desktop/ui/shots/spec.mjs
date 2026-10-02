// What to photograph for the guide, and which parts to number. `sel` is a CSS selector (or
// several): the callout's box is the smallest rectangle holding everything they match.
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
      { sel: ".tabs", text: "The views of a mapping: rules, lookups, paths and golden cases." },
      { sel: column("target"), text: "Target: the field of the output this row fills.", at: { x: 22, y: 90 } },
      { sel: column("source"), text: "Source: where the value comes from in the input.", at: { x: 40, y: 90 } },
      { sel: column("expression"), text: "Expression: how it is computed, when it is not a plain copy.", at: { x: 58, y: 90 } },
      { sel: ".schema-status", text: "The schemas of the mapping; green means it is found and readable." },
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
    setup: (p) => help(p, "Function explorer"),
    callouts: [
      { sel: ".explorer-search", text: "Search by name or by what a function does." },
      { sel: ".explorer-list", text: "Every function a mapping can call. The grey tag tells whether it is built in or from a file of the project (fn/…)." },
      { sel: ".explorer-detail code", text: "The signature and what it returns." },
      { sel: ".explorer-detail button", text: "Insert puts the call in the cell, or the override, you are editing." },
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

// The project-function editor in the function explorer: edit a function of the project, a test
// call, override a built-in (a copy under a warning), a new function. A check, not a shot.
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { chromium } from "playwright-core";
import { createServer } from "vite";
import { bridgePlugin, makeCopy, setInitial, shim, stop } from "./bridge.mjs";

const server = await createServer({
  root: resolve(import.meta.dirname, ".."),
  configFile: false,
  plugins: [react(), bridgePlugin()],
  logLevel: "error",
  clearScreen: false,
});
await server.listen();
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1600, height: 900 } });
await context.addInitScript(shim);
await context.addInitScript(() => {
  localStorage.setItem("wizardAtStartup", "0");
  localStorage.setItem("tourOffered.functional", "1");
});
const project = makeCopy();
setInitial(project);
const page = await context.newPage();
page.on("pageerror", (e) => console.error("page error:", e.message));
await page.goto(server.resolvedUrls.local[0]);
await page.waitForSelector(".ag-row");
const fail = (m) => {
  console.error("FAIL:", m);
  process.exitCode = 1;
};
const file = (name) => readFileSync(join(project, "fn", name), "utf8");

// the rail opens the panel as an overlay: the tool keeps its size; Help gives the same panel
const mainWidth = (await page.locator("main").boundingBox()).width;
await page.click('.side-rail button:has-text("fn")');
await page.waitForFunction(() => document.querySelector(".fx.open"));
await page.click('.side-rail button:has-text("fn")');
await page.waitForFunction(() => !document.querySelector(".fx.open"));
await page.click('button[aria-label="Help"]');
await page.click('.help-menu li:text-is("Function explorer")');
await page.waitForFunction(() => document.querySelector(".fx.open"));

// a project function: Edit… opens its file, the panel grows to the left
await page.fill(".explorer-search", "first_word");
await page.click('.explorer-list button:has-text("first_word")');
await page.click('.explorer-detail button:has-text("Edit…")');
await page.waitForSelector(".fn-editor .cm-content");
await page.waitForTimeout(400);
if ((await page.locator("main").boundingBox()).width !== mainWidth) fail("the tool shrank");
const editorBox = await page.locator(".fx-editor").boundingBox();
const listBox = await page.locator(".explorer").boundingBox();
if (editorBox.x + editorBox.width > listBox.x + 1 + 340) fail("the editor is not beside the list");
if (!(await page.locator(".fx-editor").isVisible())) fail("the editor is not shown");
if (!(await page.locator(".fn-text").textContent()).includes("def first_word")) fail("the file text is not shown");
// the plsql project has no code for its backend: an error is listed
await page.waitForSelector(".fn-issues li.error");
console.log("issues:", await page.locator(".fn-issues li").allTextContents());

// test call on Python with the text as it is
await page.fill('.fn-call input[aria-label="Arguments"]', '["hello big world"]');
await page.click('.fn-call button:has-text("Run")');
await page.waitForSelector(".fn-result:not(.failed)");
if ((await page.locator(".fn-result").textContent()).trim() !== '"hello"') fail("test call result");

// a typed edit: the plsql override clears the error, Save writes the file
await page.click(".fn-text .cm-content");
await page.keyboard.press("Control+Home");
await page.keyboard.type('@override(plsql="REGEXP_SUBSTR({s}, \'[^ ]+\')")\n');
await page.waitForFunction(() => document.querySelector(".fn-issues li.ok"));
await page.click('.fn-bar button:has-text("Save")');
await page.waitForFunction(() => document.querySelector(".fn-bar .primary")?.disabled);
if (!file("text.fn").includes("@override(plsql=")) fail("the file was not saved");

// a broken text is not saved, and says where
await page.click(".fn-text .cm-content");
await page.keyboard.press("Control+End");
await page.keyboard.type("def (:\n");
await page.waitForSelector(".fn-issues li.error:has-text('syntax error')");
await page.click('.fn-bar button:has-text("Save")');
await page.waitForSelector(".wizard-error:has-text('not saved')");
await page.click(".fn-text .cm-content");
await page.keyboard.press("Control+End");
for (let i = 0; i < 14 && !(await page.locator(".fn-bar .primary").isDisabled()); i++) await page.keyboard.press("Backspace");
await page.waitForFunction(() => document.querySelector(".fn-bar .primary")?.disabled);

// override a built-in: a copy under a warning
await page.fill(".explorer-search", "split_first");
await page.click('.explorer-list button:has-text("split_first")');
await page.click('.explorer-detail button:has-text("Override…")');
await page.waitForSelector(".fn-warning");
if (!file("builtin_overrides.fn").includes("def split_first")) fail("no copy of the built-in");
if (!file("builtin_overrides.fn").startsWith("# Built-in functions")) fail("no warning at the top");

// a new function
await page.click('.explorer-bar button:has-text("New function…")');
await page.fill('.prompt input >> nth=0', "shout");
// the files offered are the project's own, never the overrides file
const offered = await page.locator('.prompt select option').allTextContents();
if (offered.join("|") !== "fn/text.fn|New file…") fail(`files offered: ${offered}`);
await page.keyboard.press("Enter");
await page.waitForFunction(() => document.querySelector(".fn-text")?.textContent.includes("def shout"));
if (!file("text.fn").includes("def shout(value: str)")) fail("the new function is not in its file");
if (!file("text.fn").includes("NOT_IMPLEMENTED('plsql stub')") || !file("text.fn").includes('NotImplementedError("python stub")')) fail("no stubs");
await page.waitForSelector(".fn-issues li.error:has-text('stub for plsql')");

// an action that replaces the open file asks first when it has unsaved changes
await page.click(".fn-text .cm-content");
await page.keyboard.press("Control+End");
await page.keyboard.type("# unsaved\n");
await page.fill(".explorer-search", "split_nth");
await page.click('.explorer-list button:has-text("split_nth")');
await page.click('.explorer-detail button:has-text("Override…")');
await page.waitForSelector('.modal button:has-text("Save and continue")');
await page.click('.modal button:has-text("Cancel")');
if (file("text.fn").includes("# unsaved")) fail("saved on cancel");
if (file("builtin_overrides.fn").includes("def split_nth")) fail("override made on cancel");
await page.click('.explorer-detail button:has-text("Override…")');
await page.click('.modal button:has-text("Save and continue")');
await page.waitForFunction(() => document.querySelector(".fn-warning"));
if (!file("text.fn").includes("# unsaved")) fail("not saved on continue");
await page.waitForFunction(() => getSelection()?.anchorNode?.parentElement?.closest(".cm-line")?.textContent.includes("def split_nth"));

// a new function in a new file: the select becomes a text box, the button gives the select back
await page.click('.explorer-bar button:has-text("New function…")');
await page.fill('.prompt input >> nth=0', "cents");
await page.selectOption('.prompt select', "");
await page.fill('.prompt input[aria-label="New file name"]', "money");
await page.click('.prompt button:has-text("▾")');
await page.waitForSelector(".prompt select");
await page.selectOption('.prompt select', "");
await page.fill('.prompt input[aria-label="New file name"]', "money");
await page.click('.prompt button:has-text("Create")');
await page.waitForFunction(() => document.querySelector(".fn-text")?.textContent.includes("def cents"));
if (!file("money.fn").includes("def cents")) fail("no file for the new function");

// typing @ offers the @override of each backend
await page.click(".fn-text .cm-content");
await page.keyboard.press("Control+End");
await page.keyboard.type("\n@ov");
await page.waitForSelector('.cm-tooltip-autocomplete li:has-text("@override(plsql")');
if (!(await page.locator('.cm-tooltip-autocomplete li:has-text("@override(python")').count())) fail("no python override offered");
console.log(process.exitCode ? "FAILED" : "ok");
await browser.close();
await server.close();
stop();

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

await page.click('button[aria-label="Help"]');
await page.click('.help-menu li:text-is("Function explorer")');
const wide = async () => (await page.locator(".explorer").boundingBox()).width;
const narrow = await wide();

// a project function: Edit… opens its file, the panel grows to the left
await page.fill(".explorer-search", "first_word");
await page.click('.explorer-list button:has-text("first_word")');
await page.click('.explorer-detail button:has-text("Edit…")');
await page.waitForSelector(".fn-editor .cm-content");
if ((await wide()) <= narrow) fail("the panel did not widen");
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
await page.keyboard.press("Control+z");

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
await page.fill('.prompt input >> nth=1', "text");
await page.keyboard.press("Enter");
await page.waitForFunction(() => document.querySelector(".fn-text")?.textContent.includes("def shout"));
if (!file("text.fn").includes("def shout(value: str)")) fail("the new function is not in its file");
console.log(process.exitCode ? "FAILED" : "ok");
await browser.close();
await server.close();
stop();

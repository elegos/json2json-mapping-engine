// The grid's Output column: a remembered JSON file, and a golden case compared with its expected
// output. A check, not a shot.
import { readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { chromium } from "playwright-core";
import { createServer } from "vite";
import { bridgePlugin, makeCopy, setInitial, setInputFile, shim, stop } from "./bridge.mjs";

const server = await createServer({
  root: resolve(import.meta.dirname, ".."),
  configFile: false,
  plugins: [react(), bridgePlugin()],
  logLevel: "error",
  clearScreen: false,
});
await server.listen();
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
await context.addInitScript(shim);
await context.addInitScript(() => {
  localStorage.setItem("wizardAtStartup", "0");
  localStorage.setItem("tourOffered.functional", "1");
});
const project = makeCopy();
setInitial(project);
const golden = join(project, "tests/golden/orders");
// a file outside the project, remembered from "last time"
const free = join(project, "..", "free-input.json");
writeFileSync(free, readFileSync(join(golden, "two_lines.input.json")));
setInputFile(project, "orders", free);
const expected = join(golden, "two_lines.expected.json");
const data = JSON.parse(readFileSync(expected, "utf8"));
data.OrderId = "WRONG";
writeFileSync(expected, JSON.stringify(data));

const page = await context.newPage();
page.on("pageerror", (e) => console.error("page error:", e.message));
await page.goto(server.resolvedUrls.local[0]);
await page.waitForSelector(".ag-row");
const button = page.locator('.schema-button:has-text("Example input file")');
const fail = (m) => {
  console.error("FAIL:", m);
  process.exitCode = 1;
};

// the remembered file: green light, values, no comparison
await page.waitForSelector('.ag-cell[col-id="output"].output-cell');
if (!(await button.getAttribute("class")).includes("ok")) fail("light is not green for the file");
if ((await button.textContent()).trim() !== "Example input file") fail("button label changed");
if (!(await button.getAttribute("title")).includes("free-input.json")) fail("the tooltip does not name the file");
const first = await page.locator('.ag-row[row-index="0"] .ag-cell[col-id="output"]').textContent();
if (first.trim() !== "A1") fail(`first rule gave ${first}`);
if ((await page.locator(".output-cell.diff, .output-cell.same").count()) !== 0) fail("a file is compared");
console.log("file:", first.trim());

// the report: no rule failed on this input, and the mapped JSON is saved where the user chooses
const report = page.locator(".run-report > button").first();
if ((await report.textContent()).trim() !== "No errors") fail(`report says ${await report.textContent()}`);
const saved = join(project, "..", "saved-output.json");
await page.evaluate((p) => (window.__saveTo = p), saved);
await page.click('button:has-text("Download mapped JSON")');
await page.waitForFunction(() => document.body.textContent.includes("Mapped JSON saved"));
const mapped = JSON.parse(readFileSync(saved, "utf8"));
if (mapped.OrderId !== "A1") fail(`the saved output has OrderId ${mapped.OrderId}`);
console.log("download: OrderId", mapped.OrderId);

// a golden case: compared with its expected output (changed on disk above)
await button.click();
await page.click('.output-menu button:has-text("two_lines")');
await page.waitForSelector(".output-cell.diff");
const diff = page.locator('.ag-row[row-index="0"] .ag-cell[col-id="output"]');
console.log("diff:", (await diff.getAttribute("class")).includes("diff"), "| same cells:", await page.locator(".output-cell.same").count());
if ((await page.locator(".output-cell.same").count()) === 0) fail("no cell agrees with the expected output");
if (!(await button.getAttribute("class")).includes("ok")) fail("light is not green for the case");

// a case where a rule fails: the report counts it, and a click lists the rule with its cause
await button.click();
await page.click('.output-menu button:has-text("failed_member")');
const failing = page.locator(".run-report > button").first();
await page.waitForFunction(() => /^\d+ errors?$/.test(document.querySelector(".run-report > button")?.textContent?.trim() ?? ""));
await failing.click();
const listed = await page.locator(".run-report-list").textContent();
if (!listed.includes("ZeroDivisionError")) fail(`the list does not give the cause: ${listed}`);
console.log("errors:", (await failing.textContent()).trim(), "|", listed.trim());
// a click on the error goes to its rule: selected, with its Source cell focused
await page.click(".run-report-list button");
await page.waitForSelector('.ag-row-selected');
await page.waitForSelector('.ag-cell-focus[col-id="source"]');
const where = await page.locator(".ag-row-selected").first().textContent();
if (!where.includes("Lines[*]")) fail(`the click went to another rule: ${where}`);
console.log("goes to:", where.slice(0, 40));

// a file that is not JSON: an alert says so, with the cause
await page.evaluate((p) => (window.__openFile = p), join(project, "..", "broken-input.json"));
writeFileSync(join(project, "..", "broken-input.json"), '{"id": "A3", "items": [');
await button.click();
await page.click('.output-menu button:has-text("Choose a JSON file")');
await page.waitForSelector(".modal");
const alertText = await page.locator(".modal p").textContent();
if (!alertText.includes("broken-input.json") || !alertText.includes("cannot be read")) fail(`the alert says: ${alertText}`);
console.log("alert:", alertText.replace(/\s+/g, " ").slice(0, 120));
await page.click('.modal button:has-text("OK")');
await page.evaluate((p) => (window.__openFile = p), free);
await button.click();
await page.click('.output-menu button:has-text("Choose a JSON file")');
await page.waitForFunction(() => document.querySelector(".run-report > button")?.textContent?.trim() === "No errors");

// the refresh button: with a change not saved it asks (once, if told to remember), saves, runs again
const edit = async (text) => {
  const cell = page.locator('.ag-row[row-index="0"] .ag-cell[col-id="description"]');
  await cell.click();
  await page.keyboard.press("Control+A");
  await page.keyboard.type(text);
  await page.keyboard.press("Enter");
};
await edit("Changed once");
await page.click('button[aria-label="Run again"]');
await page.waitForSelector(".modal");
await page.click(".modal-option input");
await page.click('.modal button:has-text("Save and run")');
await page.waitForFunction(() => !document.querySelector(".modal"));
await edit("Changed twice");
await page.click('button[aria-label="Run again"]');
await page.waitForTimeout(800);
if (await page.locator(".modal").count()) fail("asked again after Remember this decision");
const saved2 = readFileSync(join(project, "mappings/functional/orders.fn.yaml"), "utf8");
if (!saved2.includes("Changed twice")) fail("the refresh did not save the change");
console.log("refresh: saved without asking the second time");

// no output: the column stays, with its placeholder
await button.click();
await page.click('.output-menu button:has-text("No output")');
await page.waitForSelector('.ag-row[row-index="0"] .ag-cell[col-id="output"] .muted');
if (!(await button.getAttribute("class")).includes("unknown")) fail("light is not off with no input");
// "No output" is remembered: the file does not come back when the app is reopened
await page.reload();
await page.waitForSelector(".ag-row");
await page.waitForTimeout(500);
if (!(await page.locator('.schema-button:has-text("Example input file")').getAttribute("class")).includes("unknown")) fail("the file came back");
console.log(process.exitCode ? "FAILED" : "ok");
await browser.close();
await server.close();
stop();

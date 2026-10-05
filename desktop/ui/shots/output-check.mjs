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
const button = page.locator(".output-input > button");
const fail = (m) => {
  console.error("FAIL:", m);
  process.exitCode = 1;
};

// the remembered file: green light, values, no comparison
await page.waitForSelector('.ag-cell[col-id="output"].output-cell');
if (!(await button.getAttribute("class")).includes("ok")) fail("light is not green for the file");
if ((await button.textContent()).trim() !== "Expected Output file") fail("button label changed");
if (!(await button.getAttribute("title")).includes("free-input.json")) fail("the tooltip does not name the file");
const first = await page.locator('.ag-row[row-index="0"] .ag-cell[col-id="output"]').textContent();
if (first.trim() !== "A1") fail(`first rule gave ${first}`);
if ((await page.locator(".output-cell.diff, .output-cell.same").count()) !== 0) fail("a file is compared");
console.log("file:", first.trim());

// a golden case: compared with its expected output (changed on disk above)
await button.click();
await page.click('.output-menu button:has-text("two_lines")');
await page.waitForSelector(".output-cell.diff");
const diff = page.locator('.ag-row[row-index="0"] .ag-cell[col-id="output"]');
console.log("diff:", (await diff.getAttribute("class")).includes("diff"), "| same cells:", await page.locator(".output-cell.same").count());
if ((await page.locator(".output-cell.same").count()) === 0) fail("no cell agrees with the expected output");
if (!(await button.getAttribute("class")).includes("ok")) fail("light is not green for the case");

// no output: the column stays, with its placeholder
await button.click();
await page.click('.output-menu button:has-text("No output")');
await page.waitForSelector('.ag-row[row-index="0"] .ag-cell[col-id="output"] .muted');
if (!(await button.getAttribute("class")).includes("unknown")) fail("light is not off with no input");
// "No output" is remembered: the file does not come back when the app is reopened
await page.reload();
await page.waitForSelector(".ag-row");
await page.waitForTimeout(500);
if (!(await page.locator(".output-input > button").getAttribute("class")).includes("unknown")) fail("the file came back");
console.log(process.exitCode ? "FAILED" : "ok");
await browser.close();
await server.close();
stop();

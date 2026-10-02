// Runs golden cases from the tool in the headless browser: a check, not a shot.
import { readFileSync, writeFileSync } from "node:fs";
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
const context = await browser.newContext({ viewport: { width: 1280, height: 1000 } });
await context.addInitScript(shim);
await context.addInitScript(() => {
  localStorage.setItem("wizardAtStartup", "0");
  localStorage.setItem("tourOffered.functional", "1");
});
const project = makeCopy();
setInitial(project);
const expected = join(project, "tests/golden/orders/two_lines.expected.json");
const page = await context.newPage();
page.on("pageerror", (e) => console.error("page error:", e.message));
await page.goto(server.resolvedUrls.local[0]);
await page.waitForSelector(".ag-row");
await page.click('.tab:text-is("Golden")');
await page.click('.golden-bar button:has-text("Execute all")');
await page.waitForSelector(".golden-summary");
console.log("all:", (await page.textContent(".golden-summary")).trim());
console.log("badges:", (await page.locator(".golden-table .result-badge").allTextContents()).join(" "));

// a wrong expectation on disk, then run that case
const data = JSON.parse(readFileSync(expected, "utf8"));
data.OrderId = "WRONG";
writeFileSync(expected, JSON.stringify(data));
await page.click('.golden-table tr:has-text("two_lines") button[title^="Run this case"]');
await page.waitForSelector(".golden-result .result-badge.fail");
console.log("why:", (await page.textContent(".golden-why")).trim());
console.log("diff has change:", (await page.textContent(".golden-diff")).includes("WRONG"));

// record it as expected
await page.click('.golden-result button:has-text("Record as expected")');
await page.click('.modal button:has-text("Record")');
await page.waitForSelector(".golden-result .result-badge.pass");
console.log("after record:", await page.textContent(".golden-result .result-badge"), "| file:", JSON.parse(readFileSync(expected, "utf8")).OrderId);
await browser.close();
await server.close();
stop();

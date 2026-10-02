// A golden run marks the rows of the rules that failed unexpectedly: a check, not a shot.
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

async function run(label, expression) {
  const project = makeCopy();
  const file = join(project, "mappings/functional/orders.fn.yaml");
  writeFileSync(file, readFileSync(file, "utf8").replace('lookup(value, @countryCurrency, "N/A")', expression));
  setInitial(project);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript(shim);
  await context.addInitScript(() => {
    localStorage.setItem("wizardAtStartup", "0");
    localStorage.setItem("tourOffered.functional", "1");
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => console.error("page error:", e.message));
  await page.goto(server.resolvedUrls.local[0]);
  await page.waitForSelector(".ag-row");
  await page.click('.tab:text-is("Golden")');
  await page.click('.golden-bar button:has-text("Execute all")');
  await page.waitForSelector(".golden-summary");
  await page.click('.golden-table tr:has-text("two_lines") .result-badge');
  console.log(label, "| panel:", (await page.textContent(".golden-errors")).replace(/\s+/g, " ").trim());
  await page.click('.tab:text-is("Rules")');
  const row = page.locator('.ag-row:has-text("Currency")');
  const cls = await row.first().getAttribute("class");
  console.log("   row class:", /row-error/.test(cls) ? "row-error" : /row-warning/.test(cls) ? "row-warning" : "none", "| marker:", (await row.first().locator('[col-id="warn"]').textContent()).trim() || "(none)");
  await context.close();
}

await run("invalid regex   ", 'regexp_replace(value, "(", "")'); // regex rule, project target is plsql
await run("not a number    ", 'format_decimal(to_number(value), 1)');
await browser.close();
await server.close();
stop();

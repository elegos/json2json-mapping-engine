// Project-wide lookups from the tool: make a lookup project wide, change it, see the rules that
// read it go back to review with a note, give each mapping a copy again. A check, not a shot.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
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

const project = makeCopy();
const file = join(project, "mappings/functional/orders.fn.yaml");
// the Currency rule was validated by someone
writeFileSync(
  file,
  readFileSync(file, "utf8").replace("    needs_review: true\n    notes: 'functional", "    validated: true\n    notes: 'functional"),
);
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
const fail = (msg) => {
  console.error("FAIL:", msg);
  process.exitCode = 1;
};
const status = async () => (await page.textContent(".status, .statusbar, footer").catch(() => "")) ?? "";

await page.click('.tab:text-is("Lookups")');
await page.click('.lookup-list .file:has-text("@countryCurrency")');
await page.click(".wide-flag input");
await page.click('.modal button:has-text("Make it project wide")');
await page.waitForSelector('.lookup-list .file:has-text("@countryCurrency") >> nth=0');
await page.waitForTimeout(800);
const yaml = () => readFileSync(file, "utf8");
if (!existsSync(join(project, "lookups/countryCurrency.lookup.yaml"))) fail("no lookups/countryCurrency.lookup.yaml");
if (yaml().includes("kind: lookup")) fail("the lookup is still in the mapping");
console.log("shared:", (await page.locator(".lookup-list").innerText()).replace(/\s+/g, " "));

// the project-wide table: read by orders, change it
await page.click('.lookup-list .file:has-text("@countryCurrency")');
console.log("readers:", (await page.textContent(".lookup-readers"))?.trim());
await page.click('.lookup-detail button:has-text("+ Entry")');
const last = () => page.locator(".lookup-detail tbody tr").last().locator("input");
await last().nth(0).fill("DE");
await last().nth(0).blur(); // the row is drawn again under its new key
await page.waitForTimeout(200);
await last().nth(1).fill("EUR");
await last().nth(1).blur();
await page.click('.lookup-detail button:has-text("Save")');
await page.waitForTimeout(1000);
const text = yaml();
const currency = text.slice(text.indexOf("id: cur"), text.indexOf("id: wh"));
if (!/validated: true/.test(currency) && /needs_review: true/.test(currency) && /@countryCurrency changed/.test(currency)) {
  console.log("back to review, note:", /@countryCurrency changed[^\n]*/.exec(text)?.[0]);
} else fail("the rule did not go back to review with a note:\n" + currency);
console.log("status:", await status());

// give the mappings a copy again
await page.click('.lookup-detail input[type="checkbox"]');
await page.click('.modal button:has-text("Give each mapping a copy")');
await page.waitForTimeout(800);
if (existsSync(join(project, "lookups/countryCurrency.lookup.yaml"))) fail("the project file is still there");
if (!/DE: EUR/.test(yaml())) fail("the copy in the mapping lacks the new entry");
console.log("copied back:", /label: countryCurrency/.test(yaml()));
await browser.close();
await server.close();
stop();

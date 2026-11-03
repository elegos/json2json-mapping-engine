// Walks the import of a document in the headless browser, with a stand-in for the assistant:
// start from the wizard, run, answer, review, apply. A check, with a picture of each step.
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { chromium } from "playwright-core";
import { createServer } from "vite";
import { bridgePlugin, makeCopy, setInitial, shim, stop } from "./bridge.mjs";

const out = process.env.SHOTS_OUT ?? mkdtempSync(join(tmpdir(), "j2jme-import-shots-"));
mkdirSync(out, { recursive: true });
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
await context.addInitScript(() => localStorage.setItem("wizardAtStartup", "1"));
setInitial(null);
const page = await context.newPage();
page.on("pageerror", (e) => console.error("page error:", e.message));
const shot = (name) => page.screenshot({ path: join(out, `${name}.png`) });
const project = makeCopy("proj");
const docs = mkdtempSync(join(tmpdir(), "j2jme-docs-"));
const spec = join(docs, "orders_spec.txt");
writeFileSync(spec, "Orders mapping, version 2.1\n");
const slow = join(docs, "slow_spec.txt");
writeFileSync(slow, "A very long document\n");
const pick = (path) => page.evaluate((p) => (window.__openFile = p), path);
const text = (selector) => page.textContent(selector);

await page.goto(server.resolvedUrls.local[0]);
await page.waitForSelector(".wizard");
await page.click('.wizard button:has-text("Import a document")');
await pick(project);
await page.click('.wizard button:has-text("Other project")');
await page.waitForSelector(".import-view");
// a project outside git is offered git first
if (await page.$('.modal button:has-text("Not now")')) await page.click('.modal button:has-text("Not now")');
await page.waitForSelector('.imp-document h3:has-text("Import a document")');
console.log("document step, assistants:", await text(".imp-providers"));
await shot("1-document");

// a run can always be cancelled
await pick(slow);
await page.click('.imp-document button:has-text("Choose")');
await page.click('button:has-text("Start the import")');
await page.waitForSelector('.imp-run [role="status"]');
await page.waitForFunction(() => document.querySelectorAll(".imp-log div").length > 2);
await shot("2-run");
await page.click('button:has-text("Cancel the run")');
await page.waitForSelector('.imp-document h3:has-text("Import a document")');
console.log("cancelled: back on the document step, imports listed:", await page.locator(".imp-table").count());

// the real one
await pick(spec);
await page.click('.imp-document button:has-text("Choose")');
await page.click('button:has-text("Start the import")');
await page.waitForSelector(".imp-questions");
console.log("questions:", await text(".imp-questions h3"));
await shot("3-questions");
const cards = page.locator(".imp-question");
await cards.nth(0).getByRole("radio", { name: "1-based proposed" }).check();
await cards.nth(1).locator("textarea").fill("IT, FR, DE are EUR; the rest N/A");
await cards.nth(2).getByRole("radio", { name: "2 proposed" }).check();
await page.click('button:has-text("answers and continue")');
await page.waitForSelector(".imp-review");
console.log("summary:", (await text(".imp-summary")).replace(/\s+/g, " "));
await shot("4-review-rules");

// a rule in detail, accept it, and ask again with a note
await page.click('.imp-row:has-text("$.Lines[*].Family")');
console.log("detail:", (await text(".imp-rule header")).replace(/\s+/g, " "));
await page.click('.imp-rule button:has-text("Accept")');
await page.waitForSelector('.imp-row.active .imp-state.accepted');
await page.fill(".imp-rule textarea", "Two letters, as the family code table shows.");
await shot("5-rule-detail");
await page.click('button:has-text("Ask again with this note")');
await page.waitForSelector(".imp-review");
await page.click('.imp-filter input'); // show every rule
console.log("rules listed:", await page.locator(".imp-row").count());
for (const tab of ["Validations", "Lookups", "Cases", "Discrepancies", "Coverage", "Schemas & profile"]) {
  await page.click(`.imp-review .tab:has-text("${tab}")`);
  await page.waitForTimeout(150);
  await shot(`6-${tab.split(" ")[0].toLowerCase()}`);
}
console.log("cases tab:", (await text(".imp-pane")).replace(/\s+/g, " ").slice(0, 200));

// apply
await page.click('button:has-text("Apply…")');
await page.waitForSelector(".imp-facts");
console.log("apply:", (await text(".imp-facts")).replace(/\s+/g, " "));
await shot("7-apply");
const force = page.locator('.imp-apply label:has-text("anyway") input');
if (await force.count()) await force.check();
await page.click('.imp-apply button.primary:has-text("Apply")');
await page.waitForSelector('.imp-apply button:has-text("Open orders_import")');
await page.click('.imp-apply button:has-text("Open orders_import")');
await page.waitForSelector(".import-view", { state: "detached" });
await page.waitForSelector('nav :text("orders_import")');
console.log("opened:", await text("header .project"));
await shot("8-opened");
await browser.close();
await server.close();
stop();
console.log("pictures in", out);

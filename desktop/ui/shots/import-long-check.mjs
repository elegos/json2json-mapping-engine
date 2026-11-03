// A long document in the headless browser, with a stand-in for the assistant: survey, batches that
// run at once, a question that shows while they go, an answer given on the run screen, and the
// delete of an import from the main page. A check, with a picture of each step.
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { chromium } from "playwright-core";
import { createServer } from "vite";
import { bridgePlugin, makeCopy, setInitial, shim, stop } from "./bridge.mjs";

const out = process.env.SHOTS_OUT ?? mkdtempSync(join(tmpdir(), "j2jme-import-long-"));
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
const context = await browser.newContext({ viewport: { width: 1500, height: 900 } });
await context.addInitScript(shim);
await context.addInitScript(() => localStorage.setItem("wizardAtStartup", "1"));
setInitial(null);
const page = await context.newPage();
page.on("pageerror", (e) => console.error("page error:", e.message));
const shot = (name) => page.screenshot({ path: join(out, `${name}.png`) });
const project = makeCopy("proj");
const docs = mkdtempSync(join(tmpdir(), "j2jme-docs-"));
const long = join(docs, "long_spec.txt");
writeFileSync(long, Array.from({ length: 100 }, (_, i) => `Requirement ${i + 1}: a rule of the mapping.`).join("\n\n") + "\n");
const pick = (path) => page.evaluate((p) => (window.__openFile = p), path);
const text = (selector) => page.textContent(selector);

await page.goto(server.resolvedUrls.local[0]);
await page.waitForSelector(".wizard");
await page.click('.wizard button:has-text("Import a document")');
await pick(project);
await page.click('.wizard button:has-text("Other project")');
await page.waitForSelector(".import-view");
if (await page.$('.modal button:has-text("Not now")')) await page.click('.modal button:has-text("Not now")');
await page.waitForSelector('.imp-document h3:has-text("Import a document")');
await pick(long);
await page.click('.imp-document button:has-text("Choose")');
await page.click('button:has-text("Start the import")');

// the batches run at once and the question shows while they do
await page.waitForSelector(".imp-run-questions .imp-question", { timeout: 60000 });
console.log("batches:", (await text(".imp-batches")).replace(/\s+/g, " "));
console.log("expected gaps:", (await text(".imp-expected")).replace(/\s+/g, " "));
console.log("live questions:", (await text(".imp-run-questions h3")).trim());
await shot("1-run-with-questions");
const cards = page.locator(".imp-run-questions .imp-question");
await cards.nth(0).locator("textarea").fill("3");
await page.click('.imp-run-questions button:has-text("Send 1 answer")');
await page.waitForFunction(() => !document.querySelector(".imp-run-questions .imp-question"));
await shot("2-answered-while-running");

// the run ends: the plan, with the rule that read the proposal
await page.waitForSelector(".imp-review, .imp-questions", { timeout: 90000 });
console.log("after the run:", (await text(".imp-summary, .imp-questions h3")).replace(/\s+/g, " ").slice(0, 220));
await shot("3-after");

// delete the import from the main page
await page.click('.imp-steps button:has-text("Document")');
await page.waitForSelector(".imp-table");
console.log("listed:", (await text(".imp-table")).replace(/\s+/g, " ").slice(0, 200));
await page.click('.imp-table button:has-text("Delete")');
await shot("4-delete-confirm");
await page.click('.modal button:has-text("Delete the import")');
await page.waitForFunction(() => !document.querySelector(".imp-table"));
console.log("deleted: no imports listed");
await browser.close();
await server.close();
stop();
console.log("pictures in", out);

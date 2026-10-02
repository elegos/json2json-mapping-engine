// Looks at a page of the guide as the tool draws it (figures and callouts included):
//   node shots/preview.mjs "<title of the page>" out.png [book: Developer|Functional user]
import { resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { chromium } from "playwright-core";
import { createServer } from "vite";
import { bridgePlugin, makeCopy, setInitial, shim, stop } from "./bridge.mjs";
import { VIEWPORT } from "./spec.mjs";

const [title, out, book] = process.argv.slice(2);
const server = await createServer({
  root: resolve(import.meta.dirname, ".."),
  configFile: false,
  plugins: [react(), bridgePlugin()],
  logLevel: "error",
  clearScreen: false,
});
await server.listen();
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 1000 }, colorScheme: "dark" });
await context.addInitScript(shim);
await context.addInitScript(() => {
  localStorage.setItem("tourOffered.functional", "1");
  localStorage.setItem("wizardAtStartup", "0");
});
setInitial(makeCopy());
const page = await context.newPage();
await page.goto(server.resolvedUrls.local[0]);
await page.waitForSelector(".ag-row");
await page.click('button[aria-label="Help"]');
await page.click('.help-menu li:text-is("Guide")');
if (book) await page.click(`.guide-toc button.book:has-text("${book}")`);
await page.click(`.guide-toc li button:text-is("${title}")`);
await page.waitForTimeout(300);
await page.screenshot({ path: out });
await browser.close();
await server.close();
stop();
void VIEWPORT;

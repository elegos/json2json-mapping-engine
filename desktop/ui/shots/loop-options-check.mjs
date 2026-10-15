// The loop options dialog: the icon beside a loop opens it, a choice is kept and shows on the icon.
// A check, with a picture.
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { chromium } from "playwright-core";
import { createServer } from "vite";
import { bridgePlugin, makeCopy, setInitial, shim, stop } from "./bridge.mjs";

const out = process.env.SHOTS_OUT ?? mkdtempSync(join(tmpdir(), "j2jme-loop-options-"));
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
setInitial(makeCopy());
const page = await context.newPage();
page.on("pageerror", (e) => console.error("page error:", e.message));
await page.goto(server.resolvedUrls.local[0]);
await page.waitForSelector(".ag-row");
const button = page.locator('.ag-cell[col-id="kind"] button.loop-options-button').first();
console.log("a loop row has the icon:", await button.count(), "| title:", await button.getAttribute("title"));
await button.click();
await page.waitForSelector(".loop-options");
await page.screenshot({ path: join(out, "1-loop-options.png") });
await page.fill('.loop-options label:has-text("Order the list by") input', "@.sku");
await page.check('.loop-options label:has-text("Descending") input');
await page.fill('.loop-options label:has-text("First number") input', "1");
await page.selectOption(".loop-options select", "omit");
await page.click('.loop-options button:has-text("Apply")');
await page.waitForSelector(".loop-options", { state: "detached" });
const after = page.locator('.ag-cell[col-id="kind"] button.loop-options-button.set').first();
console.log("icon now says:", await after.getAttribute("title"));
await after.click();
console.log("reopened with:", await page.inputValue('.loop-options label:has-text("Order the list by") input'),
  "|", await page.inputValue(".loop-options select"));
await page.click('.loop-options button:has-text("Cancel")');
await browser.close();
await server.close();
stop();
console.log("picture in", out);

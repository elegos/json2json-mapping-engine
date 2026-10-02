// Walks the start wizard's "New project" path in the headless browser: a check, not a shot.
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { chromium } from "playwright-core";
import { createServer } from "vite";
import { bridgePlugin, setInitial, shim, stop } from "./bridge.mjs";

const server = await createServer({
  root: resolve(import.meta.dirname, ".."),
  configFile: false,
  plugins: [react(), bridgePlugin()],
  logLevel: "error",
  clearScreen: false,
});
await server.listen();
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
await context.addInitScript(shim);
await context.addInitScript(() => localStorage.setItem("wizardAtStartup", "1"));
setInitial(null);
const page = await context.newPage();
page.on("pageerror", (e) => console.error("page error:", e.message));
await page.goto(server.resolvedUrls.local[0]);
await page.waitForSelector(".wizard");
await page.click('.wizard button:has-text("New project")');
const dir = join(mkdtempSync(join(tmpdir(), "j2jme-wizard-")), "demo");
await page.fill('.wizard input[spellcheck="false"]', dir);
await page.fill('.wizard label:has(span:text-is("schema *")) input', "OWNER");
await page.fill('.wizard label:has(span:text-is("error_code *")) input', "-20000");
await page.click('.wizard summary');
await page.fill('.wizard label:has(span:text-is("mapping_package_prefix")) input', "M_");
await page.click('.wizard button:has-text("Create project")');
await page.waitForSelector('.wizard h3:has-text("add mappings")');
await page.fill('.wizard label:has-text("Mapping name") input', "orders");
await page.click('.wizard button:has-text("Add mapping")');
await page.waitForSelector('.wizard-added');
await page.click('.wizard button:has-text("open the project")');
await page.waitForSelector('.wizard h3:has-text("Project ready")');
console.log(await page.textContent(".wizard p"));
await page.click('.wizard button:has-text("Open the project properties")');
await page.waitForSelector(".config h2");
console.log("properties:", await page.textContent(".config h2"), "| project:", await page.textContent("header .project"));
await browser.close();
await server.close();
stop();

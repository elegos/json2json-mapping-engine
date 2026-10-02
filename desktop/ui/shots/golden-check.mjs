// Walks the golden case editor in the headless browser: a check, not a shot.
import { readFileSync, existsSync } from "node:fs";
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
const page = await context.newPage();
page.on("pageerror", (e) => console.error("page error:", e.message));
await page.goto(server.resolvedUrls.local[0]);
await page.waitForSelector(".ag-row");
await page.click('.tab:text-is("Golden")');
await page.click('.golden-bar button:has-text("New case")');
await page.fill(".modal.prompt input", "my_case");
await page.click('.modal.prompt button:has-text("Create")');
await page.click('.golden-table button.link:text-is("my_case")');
await page.waitForSelector(".golden-editor .cm-content");
const typeInto = async (text) => {
  await page.click(".golden-editor .cm-content");
  await page.keyboard.press("Control+A");
  await page.keyboard.type(text);
};
await typeInto('{"id": "A1", "items": []}');
console.log("valid:", await page.textContent(".golden-tools span"));
await page.click('.golden-editor .tab:has-text("Expected output")');
await page.click('.golden-absent button:text-is("Add one")');
await typeInto('{"OrderId": "A1"');
console.log("broken:", await page.textContent(".golden-tools span"));
console.log("save disabled while broken:", await page.isEnabled('.golden-editor button:has-text("Save")'), "(true = enabled)");
await page.keyboard.type("}");
await page.click('.golden-editor button:text-is("Format")');
await page.click('.golden-editor button:has-text("Save")');
await page.waitForFunction(() => !document.querySelector(".golden-editor header button.primary")?.textContent?.includes("●"));
const folder = join(project, "tests/golden/orders");
console.log("input   :", JSON.stringify(readFileSync(join(folder, "my_case.input.json"), "utf8")));
console.log("expected:", JSON.stringify(readFileSync(join(folder, "my_case.expected.json"), "utf8")));
await page.click('.golden-editor button:text-is("Remove this file")');
await page.click('.golden-editor button:has-text("Save")');
await page.waitForTimeout(500);
console.log("expected removed:", !existsSync(join(folder, "my_case.expected.json")));
console.log("row:", (await page.textContent(".golden-table tr.current")).replace(/\s+/g, " "));
await browser.close();
await server.close();
stop();

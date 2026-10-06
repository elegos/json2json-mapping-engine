// The toolbar with an input run: no horizontal scroll of the window at any width, and the run
// report's buttons as tall as the others. A check, not a shot.
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
const project = makeCopy();
setInitial(project);
const free = join(project, "..", "free-input.json");
writeFileSync(free, readFileSync(join(project, "tests/golden/orders/two_lines.input.json")));
setInputFile(project, "orders", free);
const fail = (m) => {
  console.error("FAIL:", m);
  process.exitCode = 1;
};
for (const width of [1830, 1440, 1280, 1100, 900]) {
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  await context.addInitScript(shim);
  await context.addInitScript(() => {
    localStorage.setItem("wizardAtStartup", "0");
    localStorage.setItem("tourOffered.functional", "1");
  });
  const page = await context.newPage();
  await page.goto(server.resolvedUrls.local[0]);
  await page.waitForSelector(".run-report");
  const m = await page.evaluate(() => {
    const h = (sel) => document.querySelector(sel)?.getBoundingClientRect().height;
    return {
      scroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      body: document.body.scrollWidth - document.body.clientWidth,
      example: h(".schema-button"),
      report: h(".run-report > button"),
      download: h(".run-report > button:last-child"),
    };
  });
  console.log(width, JSON.stringify(m));
  if (m.scroll > 0 || m.body > 0) fail(`${width}px: the window scrolls sideways by ${m.scroll}`);
  if (Math.abs(m.report - m.example) > 1 || Math.abs(m.download - m.example) > 1) fail(`${width}px: the report's buttons are not as tall as the others`);
  await context.close();
}
await browser.close();
await server.close();
stop();

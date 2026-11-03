// Both tours, step by step: every step that frames something finds it, and shows what it says.
// A check: it lists every step with what it frames (a step that should frame something and says "card in the middle" lost its target).
import { resolve } from "node:path";
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
const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
await context.addInitScript(shim);
await context.addInitScript(() => {
  localStorage.setItem("wizardAtStartup", "0");
  localStorage.setItem("tourOffered.functional", "1");
  localStorage.setItem("tourOffered.developer", "1");
});
setInitial(makeCopy());
const page = await context.newPage();
page.on("pageerror", (e) => console.error("page error:", e.message));
await page.goto(server.resolvedUrls.local[0]);
await page.waitForSelector(".ag-row");
for (const [book, item] of [["functional", "Quick tour"], ["developer", "Developer tour"]]) {
  await page.click('[data-tour="help"]');
  await page.click(`.help-menu li:has-text("${item}")`);
  await page.waitForSelector('.tour[data-ready="true"]');
  for (let n = 1; ; n++) {
    await page.waitForSelector('.tour[data-ready="true"]');
    const title = await page.locator(".tour-card #tour-title").innerText();
    const framed = await page.locator(".tour .sr-only").count();
    const label = framed ? await page.locator(".tour .sr-only").first().innerText() : "";
    console.log(`${book} ${String(n).padStart(2)} ${title}${framed ? ` | ${label}` : " | (card in the middle)"}`);
    const last = (await page.locator(".tour-card button.primary").innerText()).trim() !== "Next";
    if (last) break;
    await page.click(".tour-card button.primary");
  }
  await page.click(".tour-card button.primary"); // the last step's button closes the tour
  await page.waitForSelector(".tour", { state: "detached" });
}
await browser.close();
await server.close();
stop();
console.log("tours walked");

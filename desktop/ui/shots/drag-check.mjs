// Dragging a rule among its siblings: the gap while dragging and the highlight after the drop.
// A check, not a shot.
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
});
setInitial(makeCopy());
const page = await context.newPage();
page.on("pageerror", (e) => console.error("page error:", e.message));
await page.goto(server.resolvedUrls.local[0]);
await page.waitForSelector(".ag-row");
const fail = (m) => {
  console.error("FAIL:", m);
  process.exitCode = 1;
};
const names = () => page.$$eval('.ag-row[row-index] .ag-cell[col-id="target"]', (c) =>
    c
      .map((x) => [Number(x.closest(".ag-row").getAttribute("row-index")), x.textContent.trim()])
      .sort((a, b) => a[0] - b[0])
      .map((x) => x[1]),
  );
console.log("before:", (await names()).slice(0, 5).join(" | "));

const handle = (i) => page.locator(`.ag-row[row-index="${i}"] [col-id="drag"] .ag-drag-handle`).first();
const from = await handle(0).boundingBox();
const to = await page.locator('.ag-row[row-index="2"]').first().boundingBox();
await page.mouse.move(from.x + 5, from.y + 5);
await page.mouse.down();
await page.mouse.move(from.x + 20, from.y + 40, { steps: 5 });
await page.mouse.move(to.x + 100, to.y + 30, { steps: 8 });
await page.waitForTimeout(300);
const shifted = await page.$$eval(".ag-row", (rows) =>
  rows.filter((r) => r.style.translate).map((r) => r.getAttribute("row-index")),
);
console.log("shifted rows while dragging:", shifted.join(","));
if (shifted.length === 0) fail("no gap opens while dragging");
await page.screenshot({ path: "/tmp/drag-during.png" });
await page.mouse.up();
await page.waitForTimeout(250);
const lit = await page.$$eval(".ag-row.just-dropped", (r) => r.length);
console.log("rows lit after the drop:", lit);
if (lit === 0) fail("nothing is highlighted after the drop");
const bg = await page.$$eval(".ag-row.just-dropped", (r) => r.map((x) => getComputedStyle(x, "::after").opacity));
console.log("background:", bg.join(" ; "));
for (const t of [100, 100, 100, 100, 100, 100]) {
  await page.waitForTimeout(t);
  const seen = await page.$$eval(".ag-row", (rows) => rows.filter((r) => r.classList.contains("just-dropped")).map((r) => `${r.getAttribute("row-id")}:${getComputedStyle(r, "::after").opacity}`));
  console.log("t+", t, seen.join(" ; ") || "none");
}
await page.screenshot({ path: "/tmp/drag-after.png" });
console.log("after:", (await names()).slice(0, 5).join(" | "));
await browser.close();
await server.close();
stop();

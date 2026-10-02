// Takes the guide's screenshots: runs the UI in a headless browser on a copy of the tutorial
// project (bridge.mjs stands in for the Tauri shell) and, for each shot of spec.mjs, writes
// src/guide/img/<name>.png and <name>.callouts.json (the callouts' boxes, found in the page and
// given in percent of the image). A figure of the guide that lists no callouts of its own uses
// that file; one that does keeps its own, so a shot taken by hand can be dropped in beside it.
//
//   node shots/run.mjs [name ...]      (from desktop/ui; all shots when none is named)
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { chromium } from "playwright-core";
import { createServer } from "vite";
import { bridgePlugin, makeCopy, setInitial, shim, stop } from "./bridge.mjs";
import { SHOTS, VIEWPORT } from "./spec.mjs";

const out = resolve(import.meta.dirname, "../src/guide/img");
mkdirSync(out, { recursive: true });
const wanted = process.argv.slice(2);
const shots = wanted.length ? SHOTS.filter((s) => wanted.includes(s.name)) : SHOTS;

const server = await createServer({
  root: resolve(import.meta.dirname, ".."),
  configFile: false,
  plugins: [react(), bridgePlugin()],
  server: { port: 0, strictPort: false },
  logLevel: "error",
  clearScreen: false,
});
await server.listen();
const url = server.resolvedUrls.local[0];
const browser = await chromium.launch();

/** The box of the elements `selector` matches, in percent of the viewport. */
async function boxes(page, selector, first, view) {
  const list = [selector].flat();
  return page.evaluate(
    ({ list, first, w, h }) => {
      // the part of the element that can be seen: what a scrolling ancestor clips is left out
      const visibleRect = (el) => {
        let { left, top, right, bottom } = el.getBoundingClientRect();
        for (let p = el.parentElement; p; p = p.parentElement) {
          const o = getComputedStyle(p);
          if (o.overflowX === "visible" && o.overflowY === "visible") continue;
          const r = p.getBoundingClientRect();
          left = Math.max(left, r.left);
          top = Math.max(top, r.top);
          right = Math.min(right, r.right);
          bottom = Math.min(bottom, r.bottom);
        }
        right = Math.min(right, w);
        bottom = Math.min(bottom, h);
        return right > left && bottom > top ? { left, top, right, bottom } : null;
      };
      const rects = list.flatMap((sel) =>
        (first ? [document.querySelector(sel)].filter(Boolean) : [...document.querySelectorAll(sel)]).map(
          (el) => visibleRect(el),
        ),
      ).filter(Boolean);
      if (!rects.length) return null;
      const left = Math.min(...rects.map((r) => r.left));
      const top = Math.min(...rects.map((r) => r.top));
      const right = Math.max(...rects.map((r) => r.right));
      const bottom = Math.max(...rects.map((r) => r.bottom));
      const pc = (v, of) => Math.round((v / of) * 1000) / 10;
      return { x: pc(left, w), y: pc(top, h), w: pc(right - left, w), h: pc(bottom - top, h) };
    },
    { list, first: !!first, w: view.width, h: view.height },
  );
}

let failed = 0;
for (const shot of shots) {
  const project = makeCopy();
  // projects the start window lists as recent: real folders, so they are not drawn as missing
  const recent = shot.start === "wizard" ? ["billing-sync", "orders-project", "customers"].map(makeCopy) : [];
  setInitial(shot.start === "wizard" ? null : project);
  const context = await browser.newContext({ viewport: shot.viewport ?? VIEWPORT, colorScheme: "dark" });
  await context.addInitScript(shim);
  await context.addInitScript((recent) => {
    localStorage.setItem("recentProjects", JSON.stringify(recent));
  }, recent);
  await context.addInitScript((wizard) => {
    // the first-time offers of the tours must not appear in a picture
    localStorage.setItem("tourOffered.functional", "1");
    localStorage.setItem("tourOffered.developer", "1");
    localStorage.setItem("wizardAtStartup", wizard ? "1" : "0");
  }, shot.start === "wizard");
  const page = await context.newPage();
  page.on("pageerror", (e) => console.error(`  [${shot.name}] page error: ${e.message}`));
  await page.goto(url);
  try {
    await page.waitForSelector(shot.ready ?? ".ag-row", { timeout: 15000 });
    // the folder is a temporary one: the picture shows a plain name
    await page.evaluate(() => {
      const el = document.querySelector("header .project");
      if (el?.textContent?.startsWith("/tmp/")) el.textContent = "~/projects/orders-project";
      for (const b of document.querySelectorAll(".wizard-recent button.link")) {
        b.textContent = "~/projects/" + b.textContent.replace(/^.*\//, "");
      }
    });
    await shot.setup?.(page);
    await page.waitForTimeout(400);
    const callouts = [];
    for (const [i, c] of (shot.callouts ?? []).entries()) {
      const box = await boxes(page, c.sel, c.first, shot.viewport ?? VIEWPORT);
      if (!box) throw new Error(`callout ${i + 1}: nothing matches ${JSON.stringify(c.sel)}`);
      callouts.push({ n: i + 1, ...box, text: c.text, ...(c.at ? { at: c.at } : {}) });
    }
    await page.screenshot({ path: join(out, `${shot.name}.png`) });
    writeFileSync(join(out, `${shot.name}.callouts.json`), JSON.stringify(callouts, null, 1) + "\n");
    console.log(`${shot.name}: ${callouts.length} callouts`);
  } catch (e) {
    failed++;
    console.error(`${shot.name}: ${e.message}`);
    await page.screenshot({ path: join(out, `${shot.name}.failed.png`) }).catch(() => {});
  }
  await context.close();
}
await browser.close();
await server.close();
stop();
process.exit(failed ? 1 : 0);

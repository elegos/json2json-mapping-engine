// The tours as pages of the guide: a picture of every step (the card and what it frames) and the
// text of the step, written to src/guide/<book>/..-tour.md and src/guide/img/tour-<book>-NN.png.
// The text is the tour's own (src/tourSteps.ts), read from the card, so the page cannot drift.
//
//   node shots/tour.mjs            (from desktop/ui)
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import react from "@vitejs/plugin-react";
import { chromium } from "playwright-core";
import { createServer } from "vite";
import { bridgePlugin, makeCopy, setInitial, shim, stop } from "./bridge.mjs";

const guide = resolve(import.meta.dirname, "../src/guide");
const out = join(guide, "img");
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
const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, colorScheme: "dark" });
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
// the folder is a temporary one: the picture shows a plain name (the header is redrawn, so: before each picture)
const plainName = () =>
  page.evaluate(() => {
    const el = document.querySelector("header .project");
    if (el?.textContent?.startsWith("/tmp/")) el.textContent = "~/projects/orders-project";
  });

const BOOKS = [
  { book: "functional", item: "Quick tour", file: "functional/14-tour.md", title: "The quick tour, step by step", lead: "The tour that **Help → Quick tour** runs, on a sample project: one picture for each step, with the part it frames." },
  { book: "developer", item: "Developer tour", file: "developer/07-tour.md", title: "The developer tour, step by step", lead: "The tour that **Help → Developer tour** runs, on a sample project: what is behind the grid, one picture for each step." },
];
for (const { book, item, file, title, lead } of BOOKS) {
  await page.click('[data-tour="help"]');
  await page.click(`.help-menu li:has-text("${item}")`);
  const parts = [`# ${title}`, "", lead, ""];
  for (let n = 1; ; n++) {
    await page.waitForSelector('.tour[data-ready="true"]');
    await page.waitForTimeout(250);
    const name = `tour-${book}-${String(n).padStart(2, "0")}.png`;
    await plainName();
    await page.screenshot({ path: join(out, name) });
    const heading = await page.locator("#tour-title").innerText();
    const paragraphs = await page.locator("#tour-text p").allInnerTexts();
    parts.push(`## ${n}. ${heading}`, "", "```figure", JSON.stringify({ src: name, alt: heading, callouts: [] }), "```", "", ...paragraphs.flatMap((t) => [t, ""]));
    const last = (await page.locator(".tour-card button.primary").innerText()).trim() !== "Next";
    if (last) break;
    await page.click(".tour-card button.primary");
  }
  await page.click(".tour-card button.primary");
  await page.waitForSelector(".tour", { state: "detached" });
  writeFileSync(join(guide, file), parts.join("\n").trimEnd() + "\n");
  console.log(`${book}: ${file}`);
}
await browser.close();
await server.close();
stop();

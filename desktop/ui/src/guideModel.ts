// The guide's pages and what is done with them: ordering, search, and the figures (a
// screenshot plus callouts kept as data, so a screenshot can be replaced without redrawing
// the boxes and arrows).
import { marked } from "marked";

export type Book = "functional" | "developer";

export const BOOKS: { id: Book; title: string; about: string }[] = [
  { id: "functional", title: "Functional user", about: "Writing and checking mapping rules" },
  { id: "developer", title: "Developer", about: "Functions, overrides, backends, build" },
];

export interface Page {
  /** `functional/the-grid`: the folder and the file name without number or extension. */
  id: string;
  book: Book;
  title: string;
  body: string;
}

/** A highlighted part of a screenshot, in percent of the image. `at` is where its number sits;
 * given, an arrow goes from there to the box. */
export interface Callout {
  n: number;
  x: number;
  y: number;
  w: number;
  h: number;
  text: string;
  at?: { x: number; y: number };
}

export interface Figure {
  src: string;
  alt: string;
  callouts: Callout[];
}

/** Pages from `{path: markdown}` (path like `./functional/01-welcome.md`), in book and file order. */
export function pagesFrom(files: Record<string, string>): Page[] {
  const pages: Page[] = [];
  for (const path of Object.keys(files).sort()) {
    const m = /^\.\/(functional|developer)\/(?:\d+-)?([^/]+)\.md$/.exec(path);
    if (!m) continue;
    const body = files[path];
    const title = /^#\s+(.+)$/m.exec(body)?.[1].trim() ?? m[2];
    pages.push({ id: `${m[1]}/${m[2]}`, book: m[1] as Book, title, body });
  }
  return pages;
}

const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** The figure a ```figure block holds, or why it cannot be read. */
export function parseFigure(text: string): Figure | string {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch (e) {
    return `figure: ${e instanceof Error ? e.message : e}`;
  }
  const f = raw as Partial<Figure>;
  if (typeof f.src !== "string" || !Array.isArray(f.callouts)) {
    return "figure: needs src and callouts";
  }
  return { src: f.src, alt: f.alt ?? "", callouts: f.callouts };
}

/** HTML of a figure: the image (or a placeholder when it is not there yet), the boxes, the
 * arrows and the numbers over it, and the legend under it. */
export function figureHtml(figure: Figure, resolve: (src: string) => string | undefined): string {
  const url = resolve(figure.src);
  const base = url
    ? `<img src="${escapeHtml(url)}" alt="${escapeHtml(figure.alt)}">`
    : `<div class="figure-pending">Screenshot pending: ${escapeHtml(figure.alt || figure.src)}</div>`;
  const boxes = figure.callouts
    .map(
      (c) =>
        `<div class="callout-box" style="left:${c.x}%;top:${c.y}%;width:${c.w}%;height:${c.h}%"></div>`,
    )
    .join("");
  const arrows = figure.callouts
    .filter((c) => c.at)
    .map((c) => {
      const from = c.at!;
      // to the nearest point of the box's edge, so the arrow does not cross what it points at
      const to = {
        x: Math.min(Math.max(from.x, c.x), c.x + c.w),
        y: Math.min(Math.max(from.y, c.y), c.y + c.h),
      };
      return `<line x1="${from.x}" y1="${from.y}" x2="${to.x}" y2="${to.y}" marker-end="url(#arrowhead)"/>`;
    })
    .join("");
  const badges = figure.callouts
    .map((c) => {
      const p = c.at ?? { x: c.x, y: c.y };
      return `<span class="callout-badge" style="left:${p.x}%;top:${p.y}%">${c.n}</span>`;
    })
    .join("");
  const legend = figure.callouts.map((c) => `<li value="${c.n}">${escapeHtml(c.text)}</li>`).join("");
  return (
    `<figure class="guide-figure"><div class="figure-stage">${base}${boxes}` +
    `<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><defs>` +
    `<marker id="arrowhead" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">` +
    `<path d="M0,0 L6,3 L0,6 z"/></marker></defs>${arrows}</svg>${badges}</div>` +
    `<ol class="figure-legend">${legend}</ol></figure>`
  );
}

/** A page's HTML. `resolve` maps an image name to its URL. Links `page:<id>` stay as they are
 * (the viewer follows them); `tour:<book>` starts a tour. */
export function renderPage(body: string, resolve: (src: string) => string | undefined): string {
  const renderer = new marked.Renderer();
  const code = renderer.code.bind(renderer);
  renderer.code = (token) => {
    if (token.lang !== "figure") return code(token);
    const figure = parseFigure(token.text);
    return typeof figure === "string"
      ? `<p class="figure-error">${escapeHtml(figure)}</p>`
      : figureHtml(figure, resolve);
  };
  return marked.parse(body, { renderer, async: false });
}

/** Pages whose title or text contain every word of `query`, title matches first. */
export function searchPages(pages: Page[], query: string): Page[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [];
  const score = (p: Page) => {
    const title = p.title.toLowerCase();
    const text = p.body.toLowerCase();
    if (!words.every((w) => title.includes(w) || text.includes(w))) return 0;
    return words.every((w) => title.includes(w)) ? 2 : 1;
  };
  return pages
    .map((p) => ({ p, s: score(p) }))
    .filter((x) => x.s > 0)
    .sort((a, b) => b.s - a.s)
    .map((x) => x.p);
}

/** The line of `page` around the first word of `query`, for the search results. */
export function snippet(page: Page, query: string): string {
  const word = query.toLowerCase().split(/\s+/).find(Boolean) ?? "";
  const text = page.body.replace(/```[\s\S]*?```/g, " ").replace(/[#*`>|]/g, " ").replace(/\s+/g, " ");
  const at = word ? text.toLowerCase().indexOf(word) : -1;
  if (at < 0) return text.slice(0, 100).trim();
  const from = Math.max(0, at - 40);
  return (from > 0 ? "…" : "") + text.slice(from, at + 80).trim() + "…";
}

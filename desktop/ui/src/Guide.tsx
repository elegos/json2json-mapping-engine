import { useEffect, useMemo, useRef, useState } from "react";
import { foundCallouts, imageUrl, PAGES } from "./guide";
import { BOOKS, type Book, type Page, renderPage, searchPages, snippet } from "./guideModel";

interface Props {
  /** The page to open on (`functional/the-grid`), or a book to open at its first page. */
  start?: string;
  onClose: () => void;
  /** `tour:<book>` links. */
  onTour?: (book: Book) => void;
  /** `explorer:open` links. */
  onExplorer?: () => void;
}

const byId = (id: string) => PAGES.find((p) => p.id === id);
const firstOf = (book: Book) => PAGES.find((p) => p.book === book);

/** The guide: two books with a table of contents, a page, search, back and forward. */
export function Guide({ start, onClose, onTour, onExplorer }: Props) {
  const first = (start && (byId(start) ?? firstOf(start as Book))) || PAGES[0];
  const [trail, setTrail] = useState<string[]>([first?.id ?? ""]);
  const [at, setAt] = useState(0);
  const [query, setQuery] = useState("");
  const pageRef = useRef<HTMLDivElement>(null);
  const page: Page | undefined = byId(trail[at]);
  const book: Book = page?.book ?? "functional";

  const go = (id: string) => {
    if (!byId(id) || id === trail[at]) return;
    setTrail([...trail.slice(0, at + 1), id]);
    setAt(at + 1);
    setQuery("");
  };

  const html = useMemo(() => (page ? renderPage(page.body, imageUrl, foundCallouts) : ""), [page]);
  const found = useMemo(() => searchPages(PAGES, query), [query]);

  useEffect(() => {
    pageRef.current?.scrollTo({ top: 0 });
  }, [page]);

  const onLink = (e: React.MouseEvent) => {
    const a = (e.target as HTMLElement).closest("a");
    const href = a?.getAttribute("href") ?? "";
    if (href.startsWith("page:")) {
      e.preventDefault();
      go(href.slice(5));
    } else if (href.startsWith("explorer:")) {
      e.preventDefault();
      onExplorer?.();
    } else if (href.startsWith("tour:")) {
      e.preventDefault();
      onTour?.(href.slice(5) as Book);
    } else if (a) {
      e.preventDefault();
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="guide"
        role="dialog"
        aria-modal="true"
        aria-label="Guide"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.key === "Escape" && onClose()}
      >
        <div className="guide-bar">
          <button disabled={at === 0} onClick={() => setAt(at - 1)} aria-label="Back" title="Back">
            ←
          </button>
          <button
            disabled={at >= trail.length - 1}
            onClick={() => setAt(at + 1)}
            aria-label="Forward"
            title="Forward"
          >
            →
          </button>
          <input
            className="guide-search"
            placeholder="Search the guide"
            value={query}
            autoFocus
            onChange={(e) => setQuery(e.target.value)}
          />
          <span className="guide-title">Guide</span>
          <button onClick={onClose}>Close</button>
        </div>
        <div className="guide-body">
          <nav className="guide-toc" aria-label="Contents">
            {query.trim() ? (
              <ul className="guide-results">
                {found.length === 0 && <li className="empty">Nothing found.</li>}
                {found.map((p) => (
                  <li key={p.id}>
                    <button onClick={() => go(p.id)}>
                      <strong>{p.title}</strong>
                      <small>
                        {BOOKS.find((b) => b.id === p.book)?.title} — {snippet(p, query)}
                      </small>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              BOOKS.map((b) => (
                <section key={b.id} className={b.id === book ? "open" : undefined}>
                  <button className="book" onClick={() => firstOf(b.id) && go(firstOf(b.id)!.id)}>
                    📖 {b.title}
                  </button>
                  <small>{b.about}</small>
                  {b.id === book && (
                    <ul>
                      {PAGES.filter((p) => p.book === b.id).map((p) => (
                        <li key={p.id}>
                          <button
                            className={p.id === page?.id ? "current" : undefined}
                            onClick={() => go(p.id)}
                          >
                            {p.title}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ))
            )}
          </nav>
          <div className="guide-page" ref={pageRef} onClick={onLink}>
            {page ? (
              <article dangerouslySetInnerHTML={{ __html: html }} />
            ) : (
              <p>No such page.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

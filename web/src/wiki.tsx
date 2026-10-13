// The Wiki (roadmap R37b): each PDF's table of contents as an outline whose levels open and
// close, and the detail pages it links to. Each entry shows its summary and the PDF pages it came
// from; a detail page has its own address, with a trail back to the levels above it.

import { useEffect, useRef, useState } from "preact/hooks";

import {
  getWikiPage,
  listPdfs,
  listWikiContents,
  type Pdf,
  pdfPageUrl,
  type WikiContents,
  type WikiDetail,
  type WikiEntry,
  wikiHref,
  wikiPageHref,
} from "./api";

interface Wiki {
  pdfs: Pdf[];
  contents: WikiContents[];
}

// Every PDF's table of contents, or with `pdf` that one's.
export function WikiPage({ pdf }: { pdf?: string }) {
  // null until loaded.
  const [wiki, setWiki] = useState<Wiki | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let stopped = false;
    const started = performance.now();
    setWiki(null);
    setFailed(false);
    Promise.all([listPdfs(), listWikiContents(pdf)])
      .then(([pdfs, contents]) => {
        console.info(
          `Wiki loaded in ${Math.round(performance.now() - started)} ms (${contents.length} tables of contents, ${pdfs.length} PDFs)`,
        );
        if (!stopped) setWiki({ pdfs, contents });
      })
      .catch((e: unknown) => {
        console.error("Could not load the wiki", e);
        if (!stopped) setFailed(true);
      });
    return () => {
      stopped = true;
    };
  }, [pdf]);

  return (
    <section className="wiki">
      <h1>Wiki</h1>
      {pdf ? (
        <p>
          <a href={wikiHref()}>All PDFs</a>
        </p>
      ) : (
        <p>
          What the PDFs in <a href="#/content">Manage Content</a> say, topic by
          topic. Open a topic to see its parts, or follow its title to a page of
          its own.
        </p>
      )}
      {failed ? (
        <p className="error">
          The wiki could not be loaded. Check that the app is still running.
        </p>
      ) : wiki === null ? (
        <p>Loading…</p>
      ) : (
        <WikiList wiki={wiki} pdf={pdf} />
      )}
    </section>
  );
}

function WikiList({ wiki, pdf }: { wiki: Wiki; pdf?: string }) {
  const built = new Set(wiki.contents.map((c) => c.pdf_id));
  const waiting = wiki.pdfs.filter(
    (p) => !built.has(p.id) && (!pdf || p.id === pdf),
  );
  if (wiki.pdfs.length === 0) {
    return (
      <p>
        There are no PDFs yet. Add one in <a href="#/content">Manage Content</a>{" "}
        and its wiki is built from it.
      </p>
    );
  }
  if (pdf && wiki.contents.length === 0 && waiting.length === 0) {
    return <p>This PDF is no longer here. It may have been removed.</p>;
  }
  return (
    <>
      {wiki.contents.map((c) => (
        <Contents key={c.pdf_id} contents={c} linked={!pdf} />
      ))}
      {waiting.map((p) => (
        <p key={p.id} className="muted">
          {p.name}: its wiki isn't ready yet.{" "}
          <a href="#/content">Manage Content</a> shows how far it has got.
        </p>
      ))}
    </>
  );
}

// A PDF's table of contents. `linked`: its name links to its own page.
function Contents({
  contents,
  linked,
}: {
  contents: WikiContents;
  linked: boolean;
}) {
  const name = linked ? (
    <a href={wikiHref(contents.pdf_id)}>{contents.pdf_name}</a>
  ) : (
    contents.pdf_name
  );
  return (
    <article className="wiki-pdf">
      <h2>{name}</h2>
      <Outline pdf={contents.pdf_id} entries={contents.entries} />
    </article>
  );
}

// A detail page, by its entry's id.
export function WikiDetailPage({ entry }: { entry: string }) {
  // null until loaded.
  const [page, setPage] = useState<WikiDetail | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let stopped = false;
    const started = performance.now();
    setPage(null);
    setMissing(false);
    getWikiPage(entry)
      .then((next) => {
        console.info(
          `Wiki page loaded in ${Math.round(performance.now() - started)} ms`,
        );
        if (stopped) return;
        setPage(next);
        // A link followed from low on the page above opens this one at its top.
        document.querySelector("main")?.scrollIntoView?.();
      })
      .catch((e: unknown) => {
        console.error("Could not load the wiki page", e);
        if (!stopped) setMissing(true);
      });
    return () => {
      stopped = true;
    };
  }, [entry]);

  if (missing) {
    return (
      <section className="wiki">
        <h1>Wiki</h1>
        <p className="error">
          This wiki page is no longer here. Its PDF may have been replaced or
          removed.
        </p>
        <p>
          <a href={wikiHref()}>Back to the wiki</a>
        </p>
      </section>
    );
  }
  if (page === null) return <p>Loading…</p>;
  return (
    <section className="wiki">
      <nav className="trail" aria-label="Where this page is">
        <a href={wikiHref()}>Wiki</a>
        <span aria-hidden="true"> › </span>
        <a href={wikiHref(page.pdf_id)}>{page.pdf_name}</a>
        {page.trail.map((t) => (
          <span key={t.id}>
            <span aria-hidden="true"> › </span>
            <a href={wikiPageHref(t.id)}>{t.title}</a>
          </span>
        ))}
      </nav>
      <h1>{page.title}</h1>
      <p>{page.summary}</p>
      <PageLinks pdf={page.pdf_id} pages={page.pages} />
      {page.entries.length > 0 && (
        <>
          <h2>In this topic</h2>
          <Outline pdf={page.pdf_id} entries={page.entries} />
        </>
      )}
    </section>
  );
}

// Entries as a nested list whose levels open and close, with buttons to open or close them all.
function Outline({ pdf, entries }: { pdf: string; entries: WikiEntry[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const opens = entries.some((e) => e.entries.length > 0);
  const openAll = (open: boolean) => {
    ref.current?.querySelectorAll("details").forEach((d) => {
      d.open = open;
    });
  };
  return (
    <div ref={ref}>
      {opens && (
        <p className="outline-buttons">
          <button
            type="button"
            className="secondary"
            onClick={() => openAll(true)}
          >
            Open all
          </button>{" "}
          <button
            type="button"
            className="secondary"
            onClick={() => openAll(false)}
          >
            Close all
          </button>
        </p>
      )}
      <Entries pdf={pdf} entries={entries} />
    </div>
  );
}

function Entries({ pdf, entries }: { pdf: string; entries: WikiEntry[] }) {
  return (
    <ul className="outline">
      {entries.map((e) => (
        <li key={e.id}>
          {e.entries.length > 0 ? (
            <details>
              <summary>
                <EntryText pdf={pdf} entry={e} />
              </summary>
              <Entries pdf={pdf} entries={e.entries} />
            </details>
          ) : (
            <div className="leaf">
              <EntryText pdf={pdf} entry={e} />
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function EntryText({ pdf, entry }: { pdf: string; entry: WikiEntry }) {
  return (
    <>
      <span className="entry-title">
        {entry.detail ? (
          <a href={wikiPageHref(entry.id)}>{entry.title}</a>
        ) : (
          entry.title
        )}
      </span>
      <span className="entry-summary">
        {entry.summary}
        {entry.detail && (
          <>
            {" "}
            <a href={wikiPageHref(entry.id)}>Read more</a>
          </>
        )}
      </span>
      <PageLinks pdf={pdf} pages={entry.pages} />
    </>
  );
}

// "PDF pages 1, 2, 3", each opening that page of the PDF in a new tab.
function PageLinks({ pdf, pages }: { pdf: string; pages: number[] }) {
  if (pages.length === 0) return null;
  return (
    <span className="entry-pages muted">
      {pages.length === 1 ? "PDF page " : "PDF pages "}
      {pages.map((n, i) => (
        <span key={n}>
          {i > 0 && ", "}
          <a
            href={pdfPageUrl(pdf, n)}
            target="_blank"
            rel="noreferrer"
            title={`Open page ${n} of the PDF`}
          >
            {n}
          </a>
        </span>
      ))}
    </span>
  );
}

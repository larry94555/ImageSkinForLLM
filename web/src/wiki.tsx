// The Wiki (roadmap R37b): each PDF's table of contents as an outline whose levels open and
// close, and the detail pages it links to. Each entry shows its summary and the PDF pages it came
// from; a detail page has its own address, with a trail back to the levels above it.
//
// The user can edit an entry's title and summary, and rebuild a PDF's wiki with the LLM, keeping
// the edits (roadmap R38). After a rebuild each edit is marked for the user to check.
//
// Every change keeps a version of the whole wiki, which the user can read and restore, and the
// wiki and its history can be saved to a file and loaded back (roadmap R38a).

import { useEffect, useRef, useState } from "preact/hooks";

import {
  AskFirst,
  getWikiPage,
  getWikiVersion,
  listPdfs,
  listWikiBuilds,
  listWikiContents,
  listWikiVersions,
  loadWikiFile,
  markWikiReviewed,
  type Pdf,
  pdfPageUrl,
  pdfUrl,
  rebuildWiki,
  restoreWikiVersion,
  saveWikiEdit,
  undoWikiEdit,
  type WikiBuild,
  type WikiChange,
  type WikiContents,
  type WikiDetail,
  type WikiEntry,
  wikiFileUrl,
  wikiHref,
  wikiPageHref,
} from "./api";
import { wikiText } from "./content";
import { useSettings } from "./settings";

// How often a rebuild's progress is checked.
export const WIKI_POLL_MS = 2000;

interface Wiki {
  pdfs: Pdf[];
  contents: WikiContents[];
}

function busy(build: WikiBuild | undefined): boolean {
  return build?.state === "waiting" || build?.state === "building";
}

// Every PDF's table of contents, or with `pdf` that one's.
export function WikiPage({ pdf }: { pdf?: string }) {
  const student = useSettings().view === "student"; // to read only (R41b)
  // null until loaded.
  const [wiki, setWiki] = useState<Wiki | null>(null);
  const [failed, setFailed] = useState(false);
  const [builds, setBuilds] = useState<Record<string, WikiBuild>>({});
  // Bumped to load the wiki again after a change, without showing "Loading…".
  const [version, setVersion] = useState(0);
  const reload = () => setVersion((v) => v + 1);

  useEffect(() => {
    setWiki(null);
  }, [pdf]);

  useEffect(() => {
    let stopped = false;
    const started = performance.now();
    setFailed(false);
    Promise.all([listPdfs(), listWikiContents(pdf), listWikiBuilds()])
      .then(([pdfs, contents, next]) => {
        console.info(
          `Wiki loaded in ${Math.round(performance.now() - started)} ms (${contents.length} tables of contents, ${pdfs.length} PDFs)`,
        );
        if (stopped) return;
        setWiki({ pdfs, contents });
        setBuilds(next);
      })
      .catch((e: unknown) => {
        console.error("Could not load the wiki", e);
        if (!stopped) setFailed(true);
      });
    return () => {
      stopped = true;
    };
  }, [pdf, version]);

  // While a PDF's wiki is being rebuilt, its progress is checked; once done, the wiki is loaded
  // again with the new pages.
  const shown = (wiki?.contents ?? []).map((c) => c.pdf_id);
  const rebuilding = shown.some((id) => busy(builds[id]));
  useEffect(() => {
    if (!rebuilding) return;
    const timer = window.setInterval(() => {
      listWikiBuilds()
        .then((next) => {
          setBuilds(next);
          if (!shown.some((id) => busy(next[id]))) reload();
        })
        .catch((e: unknown) => console.error("Could not check the wiki progress", e));
    }, WIKI_POLL_MS);
    return () => window.clearInterval(timer);
  }, [rebuilding]);

  const rebuild = async (id: string) => {
    const status = await rebuildWiki(id);
    console.info(`Rebuilding the wiki of ${id}`);
    setBuilds((b) => ({ ...b, [id]: status }));
    if (!busy(status)) reload(); // done already
  };

  return (
    <section className="wiki">
      <h1>Wiki</h1>
      {pdf ? (
        <p>
          <a href={wikiHref()}>All PDFs</a>
        </p>
      ) : student ? (
        <p>
          What the PDFs say, topic by topic. Open a topic to see its parts, or follow its title to
          a page of its own.
        </p>
      ) : (
        <p>
          What the PDFs in <a href="#/content">Manage Content</a> say, topic by topic. Open a topic
          to see its parts, or follow its title to a page of its own. You can edit any entry.
        </p>
      )}
      {failed ? (
        <p className="error">The wiki could not be loaded. Check that the app is still running.</p>
      ) : wiki === null ? (
        <p>Loading…</p>
      ) : (
        <WikiList wiki={wiki} pdf={pdf} builds={builds} onRebuild={rebuild} onChanged={reload} />
      )}
    </section>
  );
}

interface ListProps {
  wiki: Wiki;
  pdf?: string;
  builds: Record<string, WikiBuild>;
  onRebuild: (pdf: string) => Promise<void>;
  onChanged: () => void;
}

function WikiList({ wiki, pdf, builds, onRebuild, onChanged }: ListProps) {
  const student = useSettings().view === "student";
  const built = new Set(wiki.contents.map((c) => c.pdf_id));
  const waiting = wiki.pdfs.filter((p) => !built.has(p.id) && (!pdf || p.id === pdf));
  if (wiki.pdfs.length === 0) {
    if (student) return <p>There are no PDFs yet.</p>;
    return (
      <p>
        There are no PDFs yet. Add one in <a href="#/content">Manage Content</a> and its wiki is
        built from it.
      </p>
    );
  }
  if (pdf && wiki.contents.length === 0 && waiting.length === 0) {
    return <p>This PDF is no longer here. It may have been removed.</p>;
  }
  return (
    <>
      {wiki.contents.map((c) => (
        <Contents
          key={c.pdf_id}
          contents={c}
          linked={!pdf}
          build={builds[c.pdf_id]}
          onRebuild={() => onRebuild(c.pdf_id)}
          onChanged={onChanged}
        />
      ))}
      {waiting.map((p) => (
        <p key={p.id} className="muted">
          {p.name}: its wiki isn't ready yet.
          {!student && (
            <>
              {" "}
              <a href="#/content">Manage Content</a> shows how far it has got.
            </>
          )}
        </p>
      ))}
    </>
  );
}

interface ContentsProps {
  contents: WikiContents;
  linked: boolean; // its name links to its own page
  build?: WikiBuild;
  onRebuild: () => Promise<void>;
  onChanged: () => void;
}

// A PDF's table of contents, with its rebuild button and any edits a rebuild left without an
// entry.
function Contents({ contents, linked, build, onRebuild, onChanged }: ContentsProps) {
  const name = linked ? (
    <a href={wikiHref(contents.pdf_id)}>{contents.pdf_name}</a>
  ) : (
    contents.pdf_name
  );
  const student = useSettings().view === "student";
  return (
    <article className="wiki-pdf">
      <h2>{name}</h2>
      <p>
        <a href={pdfUrl(contents.pdf_id)} target="_blank" rel="noreferrer">
          Open the PDF
        </a>
      </p>
      {!student && (
        <>
          <Rebuild build={build} onRebuild={onRebuild} />
          <WikiTools contents={contents} onChanged={onChanged} />
          {contents.lost_edits.length > 0 && (
            <LostEdits edits={contents.lost_edits} onChanged={onChanged} />
          )}
        </>
      )}
      <Outline pdf={contents.pdf_id} entries={contents.entries} onChanged={onChanged} />
    </article>
  );
}

// "Rebuild the wiki", asked once more before it starts, then how far the rebuild has got.
function Rebuild({ build, onRebuild }: { build?: WikiBuild; onRebuild: () => Promise<void> }) {
  const metrics = useSettings().show_metrics;
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (busy(build)) {
    return (
      <p className="muted busy">
        {wikiText(build!, metrics)} The pages below stay as they are until it is done.
      </p>
    );
  }
  const start = () => {
    setError(null);
    onRebuild()
      .then(() => setAsking(false))
      .catch((e: unknown) => {
        console.error("Could not rebuild the wiki", e);
        setError(e instanceof Error ? e.message : "The wiki could not be rebuilt.");
      });
  };
  return (
    <div className="rebuild">
      {asking ? (
        <p className="notice">
          Build this PDF's wiki again with the LLM? It can take a while. Your edits are kept, and
          each is marked for you to check against the new wiki.{" "}
          <button type="button" onClick={start}>
            Rebuild
          </button>{" "}
          <button type="button" className="secondary" onClick={() => setAsking(false)}>
            Cancel
          </button>
        </p>
      ) : (
        <p className="outline-buttons">
          <button type="button" className="secondary" onClick={() => setAsking(true)}>
            Rebuild the wiki
          </button>
        </p>
      )}
      {build?.state === "failed" && !error && (
        <p className="error">
          The last rebuild didn't finish: {wikiText(build, metrics)} The pages below are the ones built
          before it. You can try again.
        </p>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

// What a version's change was, for the History list.
export function changeText(change: WikiChange): string {
  const entry = `\u201c${change.title ?? ""}\u201d`;
  switch (change.kind) {
    case "start":
      return "The wiki as it was before its history began";
    case "built":
      return "Built with the LLM";
    case "rebuilt":
      return "Rebuilt with the LLM";
    case "edited":
      return `You edited ${entry}`;
    case "undone":
      return `You undid your edit to ${entry}`;
    case "kept":
      return `You kept your edit to ${entry} after a rebuild`;
    case "discarded":
      return `You discarded your edit to ${entry}, which a rebuild left without an entry`;
    case "restored":
      return `You restored the version from ${when(change.restored_at ?? "")}`;
    case "loaded":
      return "You loaded it from a file";
  }
}

function when(at: string): string {
  const date = new Date(at);
  return Number.isNaN(date.getTime()) ? at : date.toLocaleString();
}

function message(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback;
}

// A change the server asked about first (the PDF was replaced since): what it said, and the
// change again with `force`.
interface Asking {
  question: string;
  confirm: string;
  go: () => Promise<void>;
}

// History, Save to a file and Load from a file, for one PDF's wiki.
function WikiTools({ contents, onChanged }: { contents: WikiContents; onChanged: () => void }) {
  const pdf = contents.pdf_id;
  const [showing, setShowing] = useState(false);
  const [asking, setAsking] = useState<Asking | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  // Runs a change, asking first when the server does.
  const change = (go: (force: boolean) => Promise<string>, confirm: string, failure: string) => {
    setError(null);
    setDone(null);
    setAsking(null);
    const run = (force: boolean) =>
      go(force).then((said) => {
        setDone(said);
        onChanged();
      });
    run(false).catch((e: unknown) => {
      if (e instanceof AskFirst) {
        setAsking({ question: e.message, confirm, go: () => run(true) });
        return;
      }
      console.error(failure, e);
      setError(message(e, failure));
    });
  };

  const restore = (id: string, at: string) =>
    change(
      async (force) => {
        await restoreWikiVersion(pdf, id, force);
        console.info(`Wiki version restored: ${id}`);
        return `The version from ${when(at)} is the wiki again. The wiki before it is kept in the history, so you can go back to it.`;
      },
      "Restore it anyway",
      "Could not restore the version",
    );

  const load = (file: File) =>
    change(
      async (force) => {
        const added = await loadWikiFile(pdf, file, force);
        console.info(`Wiki loaded from ${file.name}: ${added} versions added to the history`);
        const versions =
          added === 0
            ? "The history here already had all of its versions"
            : `Its history added ${added === 1 ? "1 version" : `${added} versions`} to this one`;
        return `Loaded ${file.name}. ${versions}, and the wiki before it is kept in the history too.`;
      },
      "Load it anyway",
      "Could not load the file",
    );

  const answer = () => {
    if (!asking) return;
    const go = asking.go;
    setAsking(null);
    go().catch((e: unknown) => {
      console.error("Could not make the change", e);
      setError(message(e, "The change could not be made."));
    });
  };

  return (
    <div className="wiki-tools">
      <p className="outline-buttons">
        <button
          type="button"
          className="secondary"
          aria-expanded={showing}
          onClick={() => setShowing((s) => !s)}
        >
          {showing ? "Hide the history" : "History"}
        </button>{" "}
        <a className="button secondary" href={wikiFileUrl(pdf)} download>
          Save to a file
        </a>{" "}
        <button type="button" className="secondary" onClick={() => picker.current?.click()}>
          Load from a file
        </button>
        <input
          ref={picker}
          type="file"
          accept=".json,application/json"
          className="sr-only"
          aria-label={`Load a saved wiki file for ${contents.pdf_name}`}
          tabIndex={-1}
          onChange={(e) => {
            const input = e.currentTarget;
            const file = input.files?.[0];
            input.value = ""; // the same file can be picked again
            if (file) load(file);
          }}
        />
      </p>
      {asking && (
        <p className="notice">
          {asking.question}{" "}
          <button type="button" onClick={answer}>
            {asking.confirm}
          </button>{" "}
          <button type="button" className="secondary" onClick={() => setAsking(null)}>
            Cancel
          </button>
        </p>
      )}
      {done && <p className="notice">{done}</p>}
      {error && <p className="error">{error}</p>}
      {showing && <History contents={contents} onRestore={restore} />}
    </div>
  );
}

// The PDF's versions, newest first, each to read or restore.
function History({
  contents,
  onRestore,
}: {
  contents: WikiContents;
  onRestore: (id: string, at: string) => void;
}) {
  const pdf = contents.pdf_id;
  const [versions, setVersions] = useState<Awaited<ReturnType<typeof listWikiVersions>> | null>(
    null,
  );
  const [failed, setFailed] = useState(false);
  const [viewing, setViewing] = useState<string | null>(null);

  // Loaded again whenever the wiki is (`contents` is new then), so a change shows at once.
  useEffect(() => {
    let stopped = false;
    const started = performance.now();
    setFailed(false);
    listWikiVersions(pdf)
      .then((found) => {
        console.info(
          `Wiki history loaded in ${Math.round(performance.now() - started)} ms (${found.length} versions)`,
        );
        if (!stopped) setVersions(found);
      })
      .catch((e: unknown) => {
        console.error("Could not load the wiki history", e);
        if (!stopped) setFailed(true);
      });
    return () => {
      stopped = true;
    };
  }, [pdf, contents]);

  if (failed) return <p className="error">The history could not be loaded. Try again.</p>;
  if (versions === null) return <p>Loading the history…</p>;
  return (
    <div className="wiki-history">
      <h3>History</h3>
      <p className="muted">
        Every change keeps a version of the whole wiki, newest first. Restoring one makes it the
        wiki again, and keeps the wiki before it here too.
      </p>
      <ol>
        {versions.map((v, i) => (
          <li key={v.id}>
            <span className="when">{when(v.at)}</span> {changeText(v.change)}
            {i === 0 && <span className="muted"> (the wiki now)</span>}{" "}
            <button
              type="button"
              className="link"
              aria-expanded={viewing === v.id}
              onClick={() => setViewing(viewing === v.id ? null : v.id)}
            >
              {viewing === v.id ? "Hide" : "View"}
            </button>
            {i > 0 && (
              <>
                {" · "}
                <button type="button" className="link" onClick={() => onRestore(v.id, v.at)}>
                  Restore
                </button>
              </>
            )}
            {viewing === v.id && (
              <VersionView
                pdf={pdf}
                id={v.id}
                onRestore={i > 0 ? () => onRestore(v.id, v.at) : undefined}
              />
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

// One version's table of contents, to read.
function VersionView({ pdf, id, onRestore }: { pdf: string; id: string; onRestore?: () => void }) {
  const [shown, setShown] = useState<Awaited<ReturnType<typeof getWikiVersion>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let stopped = false;
    getWikiVersion(pdf, id)
      .then((found) => {
        if (!stopped) setShown(found);
      })
      .catch((e: unknown) => {
        console.error("Could not load the wiki version", e);
        if (!stopped) setError(message(e, "The version could not be loaded."));
      });
    return () => {
      stopped = true;
    };
  }, [pdf, id]);
  if (error) return <p className="error">{error}</p>;
  if (shown === null) return <p>Loading…</p>;
  return (
    <div className="wiki-version">
      <Entries pdf={pdf} entries={shown.entries} />
      {shown.lost_edits.length > 0 && (
        <p className="muted">
          It also kept {shown.lost_edits.length === 1 ? "an edit" : "edits"} whose entries a rebuild
          had left out: {shown.lost_edits.map((e) => e.title).join(", ")}.
        </p>
      )}
      {onRestore && (
        <p>
          <button type="button" onClick={onRestore}>
            Restore this version
          </button>
        </p>
      )}
    </div>
  );
}

function LostEdits({
  edits,
  onChanged,
}: {
  edits: WikiContents["lost_edits"];
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const discard = (id: string) => {
    undoWikiEdit(id)
      .then(() => {
        console.info(`Wiki edit discarded: ${id}`);
        onChanged();
      })
      .catch((e: unknown) => {
        console.error("Could not discard the wiki edit", e);
        setError(e instanceof Error ? e.message : "The edit could not be discarded.");
      });
  };
  return (
    <div className="notice lost-edits">
      <p>
        The rebuilt wiki no longer has these entries you edited. Copy anything you want to keep into
        another entry, then discard them.
      </p>
      <ul>
        {edits.map((e) => (
          <li key={e.id}>
            <span className="entry-title">{e.title}</span>
            <span className="entry-summary">{e.summary}</span>
            <button type="button" className="secondary" onClick={() => discard(e.id)}>
              Discard
            </button>
          </li>
        ))}
      </ul>
      {error && <p className="error">{error}</p>}
    </div>
  );
}

// A detail page, by its entry's id.
export function WikiDetailPage({ entry }: { entry: string }) {
  // null until loaded.
  const [page, setPage] = useState<WikiDetail | null>(null);
  // Why it can't be shown: there is no such page, or it couldn't be loaded.
  const [problem, setProblem] = useState<"missing" | "failed" | null>(null);
  const [editing, setEditing] = useState(false);
  const student = useSettings().view === "student"; // to read only (R41b)
  const [version, setVersion] = useState(0);
  const reload = () => setVersion((v) => v + 1);

  useEffect(() => {
    setPage(null);
    setEditing(false);
  }, [entry]);

  useEffect(() => {
    let stopped = false;
    const started = performance.now();
    setProblem(null);
    getWikiPage(entry)
      .then((next) => {
        console.info(`Wiki page loaded in ${Math.round(performance.now() - started)} ms`);
        if (stopped) return;
        if (next === null) {
          console.info(`No wiki page ${entry}`);
          setProblem("missing");
          return;
        }
        setPage(next);
        // A link followed from low on the page above opens this one at its top.
        if (version === 0) document.querySelector("main")?.scrollIntoView?.();
      })
      .catch((e: unknown) => {
        console.error("Could not load the wiki page", e);
        if (!stopped) setProblem("failed");
      });
    return () => {
      stopped = true;
    };
  }, [entry, version]);

  if (problem) {
    return (
      <section className="wiki">
        <h1>Wiki</h1>
        <p className="error">
          {problem === "missing"
            ? "This wiki page is no longer here. Its PDF may have been replaced or removed."
            : "This wiki page could not be loaded. Check that the app is still running, then reload the page."}
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
      {editing ? (
        <EditForm
          entry={page}
          onDone={(saved) => {
            setEditing(false);
            if (saved) reload();
          }}
        />
      ) : (
        <>
          <h1>{page.title}</h1>
          <p>{page.summary}</p>
          <PageLinks pdf={page.pdf_id} pages={page.pages} />
          {!student && (
            <EditActions entry={page} onEdit={() => setEditing(true)} onChanged={reload} />
          )}
        </>
      )}
      {page.entries.length > 0 && (
        <>
          <h2>In this topic</h2>
          <Outline pdf={page.pdf_id} entries={page.entries} onChanged={reload} />
        </>
      )}
    </section>
  );
}

// Entries as a nested list whose levels open and close, with buttons to open or close them all.
// One entry at a time can be edited.
function Outline({
  pdf,
  entries,
  onChanged,
}: {
  pdf: string;
  entries: WikiEntry[];
  onChanged: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const student = useSettings().view === "student"; // to read only (R41b)
  const [editing, setEditing] = useState<string | null>(null);
  const opens = entries.some((e) => e.entries.length > 0);
  const openAll = (open: boolean) => {
    ref.current?.querySelectorAll("details").forEach((d) => {
      d.open = open;
    });
  };
  const edit: Editing = {
    id: editing,
    start: setEditing,
    done: (saved) => {
      setEditing(null);
      if (saved) onChanged();
    },
    changed: onChanged,
  };
  return (
    <div ref={ref}>
      {opens && (
        <p className="outline-buttons">
          <button type="button" className="secondary" onClick={() => openAll(true)}>
            Open all
          </button>{" "}
          <button type="button" className="secondary" onClick={() => openAll(false)}>
            Close all
          </button>
        </p>
      )}
      <Entries pdf={pdf} entries={entries} edit={student ? undefined : edit} />
    </div>
  );
}

interface Editing {
  id: string | null; // the entry being edited
  start: (id: string) => void;
  done: (saved: boolean) => void;
  changed: () => void; // an edit undone or checked
}

// Without `edit`, to read only: an earlier version, say.
function Entries({ pdf, entries, edit }: { pdf: string; entries: WikiEntry[]; edit?: Editing }) {
  return (
    <ul className="outline">
      {entries.map((e) => (
        <li key={e.id}>
          {edit && edit.id === e.id ? (
            // Not inside the <summary>, where typing a space would open or close the level.
            <div className="leaf">
              <EditForm entry={e} onDone={edit.done} />
            </div>
          ) : e.entries.length > 0 ? (
            <details>
              <summary>
                <EntryText pdf={pdf} entry={e} edit={edit} />
              </summary>
              <Entries pdf={pdf} entries={e.entries} edit={edit} />
            </details>
          ) : (
            <div className="leaf">
              <EntryText pdf={pdf} entry={e} edit={edit} />
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function EntryText({ pdf, entry, edit }: { pdf: string; entry: WikiEntry; edit?: Editing }) {
  const student = useSettings().view === "student";
  return (
    <>
      <span className="entry-title">
        {entry.detail ? <a href={wikiPageHref(entry.id)}>{entry.title}</a> : entry.title}
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
      {edit ? (
        <EditActions entry={entry} onEdit={() => edit.start(entry.id)} onChanged={edit.changed} />
      ) : (
        entry.edited && !student && <span className="entry-actions muted">Edited by you.</span>
      )}
    </>
  );
}

// Edit, and for an edited entry whether it is the user's, with undo; after a rebuild, what the
// new wiki says, to keep the edit or use the new text.
function EditActions({
  entry,
  onEdit,
  onChanged,
}: {
  entry: WikiEntry;
  onEdit: () => void;
  onChanged: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  // In a <summary>, a click would also open or close the level.
  const act = (e: Event, action: () => Promise<void> | void, failure: string) => {
    e.preventDefault();
    setError(null);
    Promise.resolve(action())
      .then(() => {
        if (action !== onEdit) onChanged();
      })
      .catch((err: unknown) => {
        console.error(failure, err);
        setError(err instanceof Error ? err.message : failure);
      });
  };
  return (
    <span className="entry-actions">
      {entry.review && entry.built && (
        <span className="notice review">
          The wiki was rebuilt after you edited this. The new wiki says:{" "}
          <strong>{entry.built.title}</strong>: {entry.built.summary}{" "}
          <button
            type="button"
            onClick={(e) => act(e, () => markWikiReviewed(entry.id), "Could not keep the edit")}
          >
            Keep my edit
          </button>{" "}
          <button
            type="button"
            className="secondary"
            onClick={(e) => act(e, () => undoWikiEdit(entry.id), "Could not use the new text")}
          >
            Use the new text
          </button>
        </span>
      )}
      {entry.edited && !entry.review && <span className="muted">Edited by you. </span>}
      <button type="button" className="link" onClick={(e) => act(e, onEdit, "Could not edit")}>
        Edit
      </button>
      {entry.edited && !entry.review && (
        <>
          {" · "}
          <button
            type="button"
            className="link"
            onClick={(e) => act(e, () => undoWikiEdit(entry.id), "Could not undo the edit")}
          >
            Undo my edit
          </button>
        </>
      )}
      {error && <span className="error"> {error}</span>}
    </span>
  );
}

// An entry's title and summary in text boxes, saved on the server. `onDone(saved)`.
function EditForm({ entry, onDone }: { entry: WikiEntry; onDone: (saved: boolean) => void }) {
  const [title, setTitle] = useState(entry.title);
  const [summary, setSummary] = useState(entry.summary);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const save = (e: Event) => {
    e.preventDefault();
    const started = performance.now();
    setSaving(true);
    setError(null);
    saveWikiEdit(entry.id, title, summary)
      .then(() => {
        console.info(`Wiki edit saved in ${Math.round(performance.now() - started)} ms`);
        onDone(true);
      })
      .catch((err: unknown) => {
        console.error("Could not save the wiki edit", err);
        setError(err instanceof Error ? err.message : "The edit could not be saved.");
        setSaving(false);
      });
  };
  return (
    <form className="wiki-edit" onSubmit={save} aria-label={`Edit ${entry.title}`}>
      <label>
        Title
        <input
          type="text"
          value={title}
          maxLength={200}
          onInput={(e) => setTitle(e.currentTarget.value)}
        />
      </label>
      <label>
        Summary
        <textarea
          rows={6}
          value={summary}
          maxLength={5000}
          onInput={(e) => setSummary(e.currentTarget.value)}
        />
      </label>
      <p className="outline-buttons">
        <button type="submit" disabled={saving || !title.trim() || !summary.trim()}>
          {saving ? "Saving…" : "Save"}
        </button>{" "}
        <button type="button" className="secondary" onClick={() => onDone(false)}>
          Cancel
        </button>
      </p>
      {error && <p className="error">{error}</p>}
    </form>
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

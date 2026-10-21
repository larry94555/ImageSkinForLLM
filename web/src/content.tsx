// The Manage Content page (roadmap R35): the PDFs the answers will come from, with add, replace
// and remove. They are kept apart from the photos and recordings (roadmap R34). Each PDF shows
// how far the server has got reading it (roadmap R36) and building its wiki pages (roadmap R37).

import { useEffect, useState } from "preact/hooks";

import {
  listPdfs,
  listReadings,
  listWikiBuilds,
  type Pdf,
  pdfUrl,
  type Reading,
  removePdf,
  sendPdf,
  type WikiBuild,
  wikiHref,
} from "./api";
import { useConfirm } from "./confirm-dialog";
import { useSettings } from "./settings";

// How often the reading and wiki progress is checked while a PDF is being read or built.
export const READING_POLL_MS = 1000;

interface Refused {
  name: string;
  reason: string;
}

export function ContentPage() {
  // null until the list has loaded.
  const [pdfs, setPdfs] = useState<Pdf[] | null>(null);
  const { ask, dialog } = useConfirm();
  const [loadFailed, setLoadFailed] = useState(false);
  // What is being sent now: the file's name, and the id of the PDF it replaces, if any.
  const [sending, setSending] = useState<{ name: string; replacing?: string } | null>(null);
  const [refused, setRefused] = useState<Refused[]>([]);
  // What was just added or replaced, said once it is sent (R41e).
  const [done, setDone] = useState<string | null>(null);
  const [readings, setReadings] = useState<Record<string, Reading>>({});
  // Until every PDF is read or has failed. A PDF with no progress yet counts as being read, so
  // a failed check is tried again.
  const reading = (pdfs ?? []).some((pdf) =>
    ["waiting", "reading", undefined].includes(readings[pdf.id]?.state),
  );
  const [wiki, setWiki] = useState<Record<string, WikiBuild>>({});
  // A PDF that has been read has its wiki pages built next.
  const building = (pdfs ?? []).some(
    (pdf) =>
      readings[pdf.id]?.state === "done" &&
      ["waiting", "building", undefined].includes(wiki[pdf.id]?.state),
  );

  // Checks the progress whenever the list changes, then every second while a PDF is read or
  // its wiki pages are built.
  useEffect(() => {
    if (pdfs === null) return;
    let stopped = false;
    const check = () => {
      listReadings()
        .then((next) => {
          if (!stopped) setReadings(next);
        })
        .catch((e: unknown) => console.error("Could not check the reading progress", e));
      listWikiBuilds()
        .then((next) => {
          if (!stopped) setWiki(next);
        })
        .catch((e: unknown) => console.error("Could not check the wiki progress", e));
    };
    check();
    const timer = reading || building ? window.setInterval(check, READING_POLL_MS) : undefined;
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [pdfs, reading, building]);

  useEffect(() => {
    listPdfs()
      .then(setPdfs)
      .catch((e: unknown) => {
        console.error("Could not list the PDFs", e);
        setLoadFailed(true);
      });
  }, []);

  // Sends one file; returns the stored PDF, or null after showing why it was refused.
  async function send(file: File, replacing?: Pdf): Promise<Pdf | null> {
    setSending({ name: file.name, replacing: replacing?.id });
    const started = performance.now();
    try {
      const pdf = await sendPdf(file, replacing?.id);
      const took = `${Math.round(performance.now() - started)} ms`;
      console.info(
        replacing
          ? `Replaced ${replacing.name} with ${pdf.name} in ${took}`
          : `Added ${pdf.name} in ${took}`,
      );
      return pdf;
    } catch (e) {
      console.error(`${replacing ? "Replacing" : "Adding"} ${file.name} refused`, e);
      setRefused((current) => [...current, { name: file.name, reason: (e as Error).message }]);
      return null;
    } finally {
      setSending(null);
    }
  }

  // One file at a time, so each refusal is shown next to the file's name.
  async function add(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    input.value = "";
    setRefused([]);
    setDone(null);
    const added: string[] = [];
    for (const file of files) {
      const pdf = await send(file);
      if (pdf) {
        added.push(pdf.name);
        setPdfs((current) => [...(current ?? []), pdf]);
      }
    }
    if (added.length) setDone(`Added ${added.join(", ")}. ${NEXT}`);
  }

  async function replace(old: Pdf, event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    setRefused([]);
    setDone(null);
    const pdf = await send(file, old);
    if (!pdf) return;
    setPdfs((current) => (current ?? []).map((p) => (p.id === pdf.id ? pdf : p)));
    setDone(`Replaced ${old.name} with ${pdf.name}. ${NEXT}`);
  }

  async function remove(pdf: Pdf) {
    const yes = await ask({
      title: `Remove ${pdf.name}?`,
      children: <p>Its wiki pages are removed too.</p>,
      keepLabel: "No, keep it",
      confirmLabel: "Yes, remove it",
    });
    if (!yes) return;
    setRefused([]);
    setDone(null);
    try {
      await removePdf(pdf.id);
      console.info(`Removed ${pdf.name}`);
      setPdfs((current) => (current ?? []).filter((p) => p.id !== pdf.id));
    } catch (e) {
      console.error(`Could not remove ${pdf.name}`, e);
      setRefused([{ name: pdf.name, reason: "Could not remove it. Please try again." }]);
    }
  }

  // Changes wait for the first list, so a late list can't hide a PDF added meanwhile.
  const ready = sending === null && (pdfs !== null || loadFailed);
  const loading = pdfs === null && !loadFailed;

  return (
    <div className="host-page">
      <h1>Manage Content</h1>
      <p className="lead">
        Add the PDFs the person&apos;s answers will come from, up to 100 MB each. Each one is read
        and turned into a <a href={wikiHref()}>wiki</a> you can check. Replace a PDF when it has a
        newer version, or remove it when it no longer applies.
      </p>
      <label className={ready ? "button" : "button busy"}>
        {sending && !sending.replacing
          ? `Uploading ${sending.name}…`
          : loading
            ? "Loading…"
            : "Add PDFs"}
        <input
          type="file"
          multiple
          accept="application/pdf,.pdf"
          disabled={!ready}
          onChange={add}
          className="file"
        />
      </label>
      {done && (
        <p className="notice" role="status">
          {done}
        </p>
      )}
      {refused.map((r) => (
        <p key={r.name} className="error">
          {r.name}: {r.reason}
        </p>
      ))}
      {loadFailed && <p className="error">Could not load the list. Reload the page to try again.</p>}
      {loading && <p className="muted busy">Loading the PDFs…</p>}
      {pdfs?.length === 0 && <p className="muted">No PDFs yet.</p>}
      <ul className="pdfs">
        {pdfs?.map((pdf) => (
          <li key={pdf.id}>
            <a className="name" href={pdfUrl(pdf.id)} target="_blank" rel="noreferrer">
              {pdf.name}
            </a>
            <span className="muted">
              {size(pdf.size)} · {pdf.replaced_at ? "replaced" : "added"}{" "}
              {day(pdf.replaced_at ?? pdf.added_at)}
            </span>
            <ReadingLine reading={readings[pdf.id]} />
            <WikiLine id={pdf.id} build={wiki[pdf.id]} />
            <span className="actions">
              <label className={sending?.replacing === pdf.id ? "replace busy" : "replace"}>
                {sending?.replacing === pdf.id ? `Uploading ${sending.name}…` : "Replace"}
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  aria-label={`Replace ${pdf.name}`}
                  disabled={!ready}
                  onChange={(e) => replace(pdf, e)}
                  className="file"
                />
              </label>
              <button type="button" className="remove" onClick={() => remove(pdf)}>
                Remove
              </button>
            </span>
          </li>
        ))}
      </ul>
      {dialog}
    </div>
  );
}

// After a PDF is sent: what happens next.
const NEXT = "It is read first, then its wiki is built. Each PDF below shows how far it has got.";

function ReadingLine({ reading }: { reading?: Reading }) {
  if (!reading) return null;
  if (reading.state === "failed") return <span className="error">{readingText(reading)}</span>;
  if (reading.state !== "done") return <span className="muted busy">{readingText(reading)}</span>;
  return <span className="muted">{readingText(reading)}</span>;
}

// "Read 3 pages: 12 paragraphs, 1 table", or how far reading has got.
export function readingText(r: Reading): string {
  if (r.state === "waiting") return "Waiting to be read…";
  if (r.state === "reading") {
    return r.pages ? `Reading page ${r.page} of ${r.pages}…` : "Reading…";
  }
  if (r.state === "failed") return r.error ?? "Could not be read.";
  const found = (["paragraph", "slide", "table"] as const)
    .filter((kind) => r.counts?.[kind])
    .map((kind) => plural(r.counts?.[kind] ?? 0, kind));
  const blank = r.pages_without_text ?? [];
  let scanned = blank.length ? ` (no text on page ${blank.join(", ")}, maybe scanned)` : "";
  if (blank.length && !found.length) scanned = ", maybe scanned";
  return `Read ${plural(r.pages, "page")}: ${found.join(", ") || "no text found"}${scanned}`;
}

function WikiLine({ id, build }: { id: string; build?: WikiBuild }) {
  const metrics = useSettings().show_metrics;
  if (!build) return null;
  if (build.state === "failed") return <span className="error">{wikiText(build, metrics)}</span>;
  if (build.state === "building" && build.stage !== "outline" && build.parts) {
    return (
      <span className="muted busy">
        {wikiText(build, metrics)}{" "}
        <progress max={build.parts} value={build.part} aria-label="Wiki parts built" />
      </span>
    );
  }
  if (build.state !== "done") return <span className="muted busy">{wikiText(build, metrics)}</span>;
  return (
    <span className="muted">
      {wikiText(build, metrics)} ·{" "}
      <a href={wikiHref(id)}>Read the wiki</a>
    </span>
  );
}

// "Wiki ready: 7 topics", or how far building them has got. While it is under way, how long it has
// taken and how long is left are always shown, counting each second (Larry's test of PR #123);
// once done, how long it took is shown only with `metrics` (R41a).
export function wikiText(b: WikiBuild, metrics = false): string {
  const time = (what = "", pending = "") => {
    const parts = [];
    if (b.elapsed_s != null) parts.push(`${duration(b.elapsed_s)} so far`);
    if (b.remaining_s != null) parts.push(`about ${duration(b.remaining_s)} left${what}`);
    else if (pending) parts.push(pending);
    return parts.length ? ` (${parts.join(", ")})` : "";
  };
  const sofar = time();
  if (b.state === "waiting") {
    if (b.error) return `Waiting for the AI to be ready to build the wiki…${sofar}`;
    if (b.ahead) {
      const now = b.building_name ? `, building “${b.building_name}” now` : "";
      return `Waiting to build the wiki: ${plural(b.ahead, "PDF")} ahead${now}…${sofar}`;
    }
    return `Waiting to build the wiki…${sofar}`;
  }
  if (b.state === "building" && b.stage === "outline") {
    const step = Math.min(b.steps + 1, b.steps_planned);
    return b.steps_planned
      ? `Arranging the wiki's topics: step ${step} of about ${b.steps_planned}…${sofar}`
      : `Arranging the wiki's topics…${sofar}`;
  }
  if (b.state === "building") {
    const part = Math.min(b.part + 1, b.parts);
    if (!b.parts) return `Building the wiki…${sofar}`;
    const done = Math.round((100 * b.part) / b.parts);
    const left = time(" before arranging its topics", "the time left shows once part 1 is done");
    return `Building the wiki: part ${part} of ${b.parts}, ${done}% done…${left}`;
  }
  if (b.state === "failed") return b.error ?? "The wiki could not be built.";
  const n = b.skipped_parts?.length ?? 0;
  const why = "the AI's answer couldn't be used";
  const skipped = n ? ` (${plural(n, "part")} of ${b.parts} skipped: ${why})` : "";
  const detail = b.detail_pages ? `, ${plural(b.detail_pages, "detail page")}` : "";
  const took = metrics && b.elapsed_s != null ? `, built in ${duration(b.elapsed_s)}` : "";
  return `Wiki ready: ${plural(b.pages ?? 0, "topic")}${detail}${took}${skipped}`;
}

// 45 -> "45 s", 252 -> "4 min 12 s", 3780 -> "1 h 3 min"
export function duration(seconds: number): string {
  const s = Math.round(seconds);
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${s % 60} s`;
  return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

// 1536 -> "2 KB", 2_500_000 -> "2.4 MB"
export function size(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// An ISO 8601 time as the day in the browser's own format, such as "12/10/2026".
function day(iso: string): string {
  return new Date(iso).toLocaleDateString();
}

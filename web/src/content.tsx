// The Manage Content page (roadmap R35): the PDFs the answers will come from, with add, replace
// and remove. They are kept apart from the photos and recordings (roadmap R34).

import { useEffect, useState } from "preact/hooks";

import { listPdfs, type Pdf, pdfUrl, removePdf, sendPdf } from "./api";

interface Refused {
  name: string;
  reason: string;
}

export function ContentPage() {
  // null until the list has loaded.
  const [pdfs, setPdfs] = useState<Pdf[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  // What is being sent now: the file's name, and the id of the PDF it replaces, if any.
  const [sending, setSending] = useState<{ name: string; replacing?: string } | null>(null);
  const [refused, setRefused] = useState<Refused[]>([]);

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
    for (const file of files) {
      const pdf = await send(file);
      if (pdf) setPdfs((current) => [...(current ?? []), pdf]);
    }
  }

  async function replace(old: Pdf, event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    setRefused([]);
    const pdf = await send(file, old);
    if (pdf) setPdfs((current) => (current ?? []).map((p) => (p.id === pdf.id ? pdf : p)));
  }

  async function remove(pdf: Pdf) {
    if (!window.confirm(`Remove ${pdf.name}?`)) return;
    setRefused([]);
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
    <>
      <h1>Manage Content</h1>
      <p className="muted">
        Add the PDFs the person&apos;s answers will come from, up to 100 MB each. Replace a PDF
        when it has a newer version, or remove it when it no longer applies.
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
    </>
  );
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

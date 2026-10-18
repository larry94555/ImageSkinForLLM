// Delete my data, on the Settings page (roadmap R31): removes the photos, recordings, prepared
// face and voice, videos and conversation, then opens setup at its start. The PDFs and the
// settings are kept.

import { useState } from "preact/hooks";

import { deleteMyData, ServerRefusal } from "./api";

export const CONFIRM_DELETE =
  "Delete the photos, recordings, prepared face and voice, videos and conversation? Setup" +
  " starts again from the beginning. This can't be undone.";

export function DeleteData() {
  const [deleting, setDeleting] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  async function remove() {
    if (!window.confirm(CONFIRM_DELETE)) {
      console.info("Delete my data cancelled");
      return;
    }
    setDeleting(true);
    setFailed(null);
    const started = performance.now();
    try {
      const deleted = await deleteMyData();
      const took = Math.round(performance.now() - started);
      console.info(`Deleted my data: ${deleted.files} file(s) (${took} ms)`);
      if (deleted.left.length === 0) {
        window.location.hash = "#/consent";
        return;
      }
      console.error(`Could not delete ${deleted.left.join(", ")}`);
      setFailed(
        `${deleted.left.length} file(s) could not be deleted, perhaps because another program` +
          " has them open. Close it and click Delete my data again.",
      );
    } catch (e) {
      console.error("Could not delete my data", e);
      setFailed(
        e instanceof ServerRefusal ? e.message : "Your data could not be deleted. Try again.",
      );
    }
    setDeleting(false);
  }

  return (
    <section className="panel" aria-labelledby="settings-delete">
      <h2 id="settings-delete">Your data</h2>
      <div className="switch">
        <button type="button" className="remove" disabled={deleting} onClick={remove}>
          Delete my data
        </button>
        <p className="muted">
          Deletes the photos, recordings, prepared face and voice, videos and conversation, then
          starts setup again. The PDFs and these settings are kept. It asks first.
        </p>
        {deleting && <p className="muted busy">Deleting…</p>}
        {failed && <p className="error">{failed}</p>}
      </div>
    </section>
  );
}

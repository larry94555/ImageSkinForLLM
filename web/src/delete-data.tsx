// Delete my data, on the Settings page (roadmap R31): removes the photos, recordings, prepared
// face and voice, videos and conversation, then opens setup at its start. The PDFs and the
// settings are kept.

import { useState } from "preact/hooks";

import { deleteMyData, ServerRefusal } from "./api";
import { ConfirmDialog } from "./confirm-dialog";
import { clearProgress } from "./progress";

// What the confirmation lists as deleted (Larry, 2026-10-18: ask "Are you sure?", say it deletes
// all the data, look like part of the app and make backing out obvious).
export const DELETED = [
  "Every photo and recording",
  "The prepared face and voice",
  "The sample video, Goodbye, Welcome back and the reply videos",
  "The whole conversation",
];

// onDeleted is told once everything is deleted, as the consent is then gone too.
export function DeleteData({ onDeleted }: { onDeleted?: () => void }) {
  const [asking, setAsking] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  function cancel() {
    console.info("Delete my data cancelled");
    setAsking(false);
  }

  async function remove() {
    setAsking(false);
    setDeleting(true);
    setFailed(null);
    const started = performance.now();
    try {
      const deleted = await deleteMyData();
      const took = Math.round(performance.now() - started);
      console.info(`Deleted my data: ${deleted.files} file(s) (${took} ms)`);
      // Any answer means the conversation was cleared, so a lesson, quiz or assessment under
      // way goes with it, and the consent is gone unless it is among what was left (review on
      // PR #109).
      clearProgress();
      if (!deleted.left.includes("consent.json")) onDeleted?.();
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
        e instanceof ServerRefusal
          ? e.message
          : "Your data could not be deleted. Try again.",
      );
    }
    setDeleting(false);
  }

  return (
    <section className="panel" aria-labelledby="settings-delete">
      <h2 id="settings-delete">Your data</h2>
      <div className="switch">
        <button
          type="button"
          className="remove"
          disabled={deleting}
          onClick={() => {
            console.info("Delete my data: asking to confirm");
            setAsking(true);
          }}
        >
          Delete my data
        </button>
        <p className="muted">
          Deletes the photos, recordings, prepared face and voice, videos and
          conversation, then starts setup again. The PDFs and these settings are
          kept. It asks first.
        </p>
        {deleting && <p className="muted busy">Deleting…</p>}
        {failed && <p className="error">{failed}</p>}
      </div>
      {asking && (
        <ConfirmDialog
          title="Are you sure you want to delete all your data?"
          keepLabel="No, keep my data"
          confirmLabel="Yes, delete everything"
          onCancel={cancel}
          onConfirm={remove}
        >
          <p>This deletes all of it:</p>
          <ul className="deleted">
            {DELETED.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p>
            Setup then starts again from the beginning. Your PDFs and settings
            are kept.
          </p>
          <p className="warning">This can't be undone.</p>
        </ConfirmDialog>
      )}
    </section>
  );
}

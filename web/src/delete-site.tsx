// Delete site, on the Settings page (roadmap R69a): its host deletes the site for good, after a
// confirmation with their password. Its subscription is cancelled at once and everything on it
// goes; their account is kept, so they can sign in and start again (R69b).

import { useState } from "preact/hooks";

import { deleteSite, ServerRefusal } from "./api";
import { ConfirmDialog } from "./confirm-dialog";

export function DeleteSite() {
  const [asking, setAsking] = useState(false);
  const [password, setPassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  async function remove() {
    setAsking(false);
    setDeleting(true);
    setFailed(null);
    try {
      await deleteSite(password);
      console.info("Site deleted");
      setDeleted(true);
    } catch (e) {
      console.error("Could not delete the site", e);
      setFailed(e instanceof ServerRefusal ? e.message : "The site could not be deleted. Try again.");
    }
    setPassword("");
    setDeleting(false);
  }

  return (
    <section className="panel" aria-labelledby="settings-delete-site">
      <h2 id="settings-delete-site">Delete site</h2>
      {deleted ? (
        <p role="status">
          Your site is deleted, with everything on it, and its address is free. Your account is
          kept, so you can sign in and start again.
        </p>
      ) : (
        <div className="switch">
          <button
            type="button"
            className="remove"
            disabled={deleting}
            onClick={() => {
              console.info("Delete site: asking to confirm");
              setAsking(true);
            }}
          >
            Delete site
          </button>
          <p className="muted">
            Deletes your site for good: its person, files and address, and cancels any
            subscription at once. Your account is kept. It asks first.
          </p>
          {deleting && <p className="muted busy">Deleting…</p>}
        </div>
      )}
      {failed && <p className="error">{failed}</p>}
      {asking && (
        <ConfirmDialog
          title="Are you sure you want to delete your site?"
          keepLabel="No, keep my site"
          confirmLabel="Yes, delete it"
          onCancel={() => {
            console.info("Delete site: kept");
            setAsking(false);
            setPassword("");
          }}
          onConfirm={remove}
        >
          <p>
            Everything on it goes and can't be brought back. Any subscription is cancelled at
            once, with no more payments.
          </p>
          <label htmlFor="delete-site-password">Your password, to confirm</label>
          <input
            id="delete-site-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onInput={(e) => setPassword((e.target as HTMLInputElement).value)}
          />
        </ConfirmDialog>
      )}
    </section>
  );
}

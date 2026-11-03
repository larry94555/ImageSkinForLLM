// Delete site, on the Settings page (roadmap R69a): never at once (Larry, 2026-11-03). After a
// confirmation with the host's password, any subscription is cancelled now and the site paused;
// its content is deleted after the admin settings' days, so a host who changes their mind can
// still come back by subscribing again. Their account is kept either way (R69b).

import { useState } from "preact/hooks";

import { deleteSite, ServerRefusal } from "./api";
import { ConfirmDialog } from "./confirm-dialog";
import { endDay } from "./subscription";

interface Props {
  days: number; // how long a paused site is kept, from the admin settings
  deletesAt: number | null; // when this site's content is deleted, once it is paused
}

export function DeleteSite({ days, deletesAt }: Props) {
  const [asking, setAsking] = useState(false);
  const [password, setPassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [when, setWhen] = useState<number | null>(deletesAt);
  const [failed, setFailed] = useState<string | null>(null);
  const kept = `${days} day${days === 1 ? "" : "s"}`;

  async function remove() {
    setAsking(false);
    setDeleting(true);
    setFailed(null);
    try {
      const at = await deleteSite(password);
      console.info("Site deletion asked: it is deleted at", at);
      setWhen(at);
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
      {when !== null ? (
        <p role="status">
          Your site is paused, and everything on it will be deleted on {endDay(when)}. Until then
          you can sign in and subscribe again to bring it back. Your account is kept either way.
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
            Cancels any subscription and pauses your site now. Its person, files and address are
            deleted {kept} later, unless you subscribe again first. Your account is kept. It asks
            first.
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
            Any subscription is cancelled now, with no more payments, and your site is paused.
            You have {kept} to change your mind by subscribing again; then everything on it is
            deleted and can't be brought back.
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

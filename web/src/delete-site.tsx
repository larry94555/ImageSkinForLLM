// Delete site, on the Settings page (roadmap R69a): never at once, and nothing paid for is taken
// away (Larry, 2026-11-03). After a confirmation with the host's password, a subscription is
// cancelled at the end of the month paid for, as Cancel subscription does: the site keeps
// working until then, and pauses. A site with no paid time left, such as a free trial, pauses
// now. Its content is deleted the admin settings' days after it pauses, so a host who changes
// their mind can still come back by subscribing again. Their account is kept either way (R69b).

import { useState } from "preact/hooks";

import { deleteSite, ServerRefusal } from "./api";
import { ConfirmDialog } from "./confirm-dialog";
import { endDay } from "./subscription";

interface Props {
  days: number; // how long a paused site is kept, from the admin settings
  subscribed: boolean; // a subscription in force, cancelled at the end of the month paid for
  endsAt: number | null; // when a cancelled subscription's service ends
  deletesAt: number | null; // when this site's content is deleted, once cancelled or paused
  onChanged?: () => void; // reads the subscription again, as a cancellation shows above too
}

// The whole days left before a paused site is deleted (R69a): the admin settings' days just
// after it paused, fewer as they pass, and never more than those days or fewer than 0.
export function daysLeft(deletesAt: number, days: number, now: number = Date.now() / 1000): number {
  return Math.min(days, Math.max(0, Math.ceil((deletesAt - now) / (24 * 60 * 60))));
}

export function DeleteSite({ days, subscribed, endsAt, deletesAt, onChanged }: Props) {
  const [asking, setAsking] = useState(false);
  const [password, setPassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [when, setWhen] = useState<number | null>(deletesAt);
  const [ends, setEnds] = useState<number | null>(subscribed ? endsAt : null);
  const [failed, setFailed] = useState<string | null>(null);
  const kept = `${days} day${days === 1 ? "" : "s"}`;

  async function remove() {
    setAsking(false);
    setDeleting(true);
    setFailed(null);
    try {
      const asked = await deleteSite(password);
      console.info("Site deletion asked: service ends at", asked.ends_at, "deleted at", asked.deletes_at);
      setEnds(asked.ends_at);
      setWhen(asked.deletes_at);
      onChanged?.();
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
      {when !== null && ends !== null ? (
        <>
          <p role="status">
            Your subscription is cancelled. You will have service until {endDay(ends)}. After
            that, your service will be paused. You will then have {kept} to renew your
            subscription before the content is deleted.
          </p>
          <p className="muted">Until then, Keep my subscription, above, undoes it.</p>
        </>
      ) : when !== null ? (
        <>
          <p role="status">
            Your site has been paused. You will have {daysLeft(when, days)} days to start it again
            before it gets deleted.
          </p>
          <p className="muted">
            It is deleted on {endDay(when)}. Subscribing again before then brings it back as it
            was. Your account is kept either way.
          </p>
        </>
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
            {subscribed
              ? `Cancels your subscription: you keep your site until the end of the month paid for, then it pauses. Its person, files and address are deleted ${kept} after that, unless you renew first.`
              : `Pauses your site now. Its person, files and address are deleted ${kept} later, unless you subscribe first.`}{" "}
            Your account is kept. It asks first.
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
          {subscribed ? (
            <p>
              Your subscription is now cancelled. You will have service until the end of the month.
              After that, your service will be paused. You will then have {kept} to renew your
              subscription before the content is deleted.
            </p>
          ) : (
            <p>
              Your site will be paused now. You will then have {kept} to subscribe before the
              content is deleted.
            </p>
          )}
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

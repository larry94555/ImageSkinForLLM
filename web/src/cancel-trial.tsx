// Cancel free trial, on the Settings page (roadmap R66): pauses the site, so visitors see that it
// is paused, while its host can still sign in. A free trial has no paid time to keep, so it
// pauses now, and its content is deleted the admin settings' days later (R69a).

import { useEffect, useState } from "preact/hooks";

import { cancelTrial, getSubscription, ServerRefusal } from "./api";
import { ConfirmDialog } from "./confirm-dialog";
import { useHost } from "./host";

export function CancelTrial() {
  const session = useHost().session;
  const [asking, setAsking] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  // The days a paused site is kept, from the admin settings (R69a).
  const [days, setDays] = useState(30);
  const shown = session?.signed_in === true && session.trial === true;

  useEffect(() => {
    if (!shown) return;
    getSubscription().then(
      (found) => found.days_before_deleting && setDays(found.days_before_deleting),
      (e: unknown) => console.error("Could not read the days before deleting", e),
    );
  }, [shown]);

  if (!shown) return null;
  const paused = cancelled || session.paused === true;

  async function cancel() {
    setAsking(false);
    setCancelling(true);
    setFailed(null);
    try {
      await cancelTrial();
      console.info("Free trial cancelled: the site is paused");
      setCancelled(true);
    } catch (e) {
      console.error("Could not cancel the free trial", e);
      setFailed(
        e instanceof ServerRefusal ? e.message : "The trial could not be cancelled. Try again.",
      );
    }
    setCancelling(false);
  }

  return (
    <section className="panel" aria-labelledby="settings-trial">
      <h2 id="settings-trial">Free trial</h2>
      {paused ? (
        <p role="status">
          Your free trial is cancelled, so your site is paused: visitors see that it is paused.
          You can still sign in. You will have {days} days to subscribe before the content is
          deleted.
        </p>
      ) : (
        <div className="switch">
          <button
            type="button"
            className="remove"
            disabled={cancelling}
            onClick={() => {
              console.info("Cancel free trial: asking to confirm");
              setAsking(true);
            }}
          >
            Cancel free trial
          </button>
          <p className="muted">
            Your site is on a free trial. Cancelling it pauses the site: visitors see that it is
            paused, and you can still sign in. You then have {days} days to subscribe before the
            content is deleted. It asks first.
          </p>
          {cancelling && <p className="muted busy">Cancelling…</p>}
        </div>
      )}
      {failed && <p className="error">{failed}</p>}
      {asking && (
        <ConfirmDialog
          title="Are you sure you want to cancel your free trial?"
          keepLabel="No, keep my trial"
          confirmLabel="Yes, cancel it"
          onCancel={() => {
            console.info("Cancel free trial: kept");
            setAsking(false);
          }}
          onConfirm={cancel}
        >
          <p>Your site is paused at once: visitors see that it is paused.</p>
          <p>
            You can still sign in to it. You will then have {days} days to subscribe before the
            content is deleted.
          </p>
        </ConfirmDialog>
      )}
    </section>
  );
}

// What a visitor sees on a paused site (R66), in place of every page but the host's sign-in.
export function PausedPage() {
  return (
    <div className="host-page">
      <h1>This site is paused</h1>
      <p className="lead">It isn't taking visitors just now.</p>
      <p>
        <a className="button" href="#/host/sign-in">
          Host sign in
        </a>
      </p>
    </div>
  );
}

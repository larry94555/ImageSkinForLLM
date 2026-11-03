// Subscribing, on the Settings page (roadmap R67): the host of a site on the main address's trial
// path subscribes on Stripe's own page, so the card never reaches this server. Stripe sends the
// browser back here, and its event, sent to the server, records the subscription.

import { useEffect, useState } from "preact/hooks";

import { getSubscription, ServerRefusal, startSubscribing, type Subscription } from "./api";
import { useHost } from "./host";

// Where the browser goes to pay; a function so tests can see it.
export const go = { to: (url: string) => window.location.assign(url) };

export function SubscriptionSection() {
  const session = useHost().session;
  const host = session?.signed_in === true;
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [starting, setStarting] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    if (!host) return;
    getSubscription().then(setSubscription, (e: unknown) =>
      console.error("Could not read the subscription", e),
    );
  }, [host]);

  if (!host || subscription === null) return null;
  if (!subscription.subscribed && !subscription.available) return null;

  async function subscribe() {
    setStarting(true);
    setFailed(null);
    try {
      const url = await startSubscribing();
      console.info("Subscribing: going to Stripe's page");
      go.to(url);
    } catch (e) {
      console.error("Could not start subscribing", e);
      setFailed(e instanceof ServerRefusal ? e.message : "Subscribing could not start. Try again.");
      setStarting(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="settings-subscription">
      <h2 id="settings-subscription">Subscription</h2>
      {subscription.subscribed ? (
        <p role="status">Subscribed: {subscription.price}.</p>
      ) : (
        <div className="switch">
          <button type="button" disabled={starting} onClick={subscribe}>
            Subscribe
          </button>
          <p className="muted">
            {subscription.price}, paid on Stripe's secure page; your card details never reach this
            site.{session?.paused ? " Subscribing brings your paused site back." : ""}
          </p>
          {starting && <p className="muted busy">Opening Stripe…</p>}
        </div>
      )}
      {failed && <p className="error">{failed}</p>}
    </section>
  );
}

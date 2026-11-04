// Subscribing, on the Settings page (roadmap R67): the host of a site on the main address's trial
// path subscribes on Stripe's own page, so the card never reaches this server. Stripe sends the
// browser back here, and its event, sent to the server, records the subscription.

import { useEffect, useState } from "preact/hooks";

import {
  checkSubdomain,
  getSubscription,
  pickSubdomain,
  resumeSubscription,
  ServerRefusal,
  setSubscriptionCancelled,
  startSubscribing,
  type SubdomainCheck,
  type Subscription,
} from "./api";
import { ConfirmDialog } from "./confirm-dialog";
import { DeleteSite } from "./delete-site";
import { useHost } from "./host";

// Where the browser goes to pay, and the page read again once the site is back; functions so
// tests can see them.
export const go = {
  to: (url: string) => window.location.assign(url),
  reload: () => window.location.reload(),
};

export function SubscriptionSection() {
  const session = useHost().session;
  const host = session?.signed_in === true;
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [starting, setStarting] = useState(false);
  const [asking, setAsking] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  // Bumped each time the subscription is read again, so the panels start from what it says.
  const [version, setVersion] = useState(0);

  function read() {
    getSubscription().then(
      (found) => {
        setSubscription(found);
        setVersion((v) => v + 1);
      },
      (e: unknown) => console.error("Could not read the subscription", e),
    );
  }

  useEffect(() => {
    if (host) read();
  }, [host]);

  if (!host || subscription === null) return null;
  // A site with its own subdomain can change it (R64), subscribed or not, as one added from
  // the command line is.
  const address = subscription.change_subdomain && subscription.subdomain && (
    <section className="panel" aria-labelledby="settings-address">
      <h2 id="settings-address">Site address</h2>
      <p role="status">
        Your site's subdomain is <strong>{subscription.subdomain}</strong>.
      </p>
      <SubdomainPicker current={subscription.subdomain} />
    </section>
  );
  // Any site but the main address's can be deleted by its host (R69a).
  const days = subscription.days_before_deleting ?? 30;
  const deletion = subscription.deletable && (
    <DeleteSite
      key={`delete-${version}`}
      onChanged={read}
      days={days}
      subscribed={subscription.subscribed}
      endsAt={subscription.ends_at ?? null}
      deletesAt={subscription.deletes_at ?? null}
    />
  );
  if (!subscription.subscribed && !subscription.available) {
    return address || deletion ? (
      <>
        {address}
        {deletion}
      </>
    ) : null;
  }

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

  // Resume subscription (R69b): one click, with the card Stripe keeps, after a confirmation that
  // says the price. Stripe's page is opened instead when it needs a card.
  async function resume() {
    setAsking(false);
    setStarting(true);
    setFailed(null);
    try {
      const answer = await resumeSubscription();
      if (answer.resumed) {
        console.info("Subscription resumed: the site is back");
        go.reload();
        return;
      }
      console.info("Resume subscription: Stripe needs a card, going to its page");
      go.to(answer.url ?? "");
    } catch (e) {
      console.error("Could not resume the subscription", e);
      setFailed(e instanceof ServerRefusal ? e.message : "Resuming didn't work. Try again.");
      setStarting(false);
    }
  }

  return (
    <>
    <section className="panel" aria-labelledby="settings-subscription">
      <h2 id="settings-subscription">Subscription</h2>
      {subscription.subscribed ? (
        <>
          <p role="status">Subscribed: {subscription.price}.</p>
          {subscription.payment_failed && (
            <p className="error" role="alert">
              Your last payment didn't go through. Stripe will try your card again over the next
              few days, and your site keeps working meanwhile.
            </p>
          )}
          {subscription.pick_subdomain && <SubdomainPicker />}
          <CancelSubscription
            key={`cancel-${version}`}
            onChanged={read}
            endsAt={subscription.ends_at ?? null}
            days={days}
          />
        </>
      ) : subscription.resumable ? (
        <div className="switch">
          <p role="status">
            {subscription.restarted
              ? "Your site is started again, empty, and paused until it is paid for. Resume your subscription to open it."
              : "Your site is paused: visitors see that it is paused. Resume your subscription to bring it back as it was."}
          </p>
          <button
            type="button"
            disabled={starting}
            onClick={() => {
              console.info("Resume subscription: asking to confirm");
              setAsking(true);
            }}
          >
            Resume subscription
          </button>
          <p className="muted">
            {subscription.price}, with the card Stripe keeps for you, so you type no card details.
          </p>
          {starting && <p className="muted busy">Asking Stripe…</p>}
          {asking && (
            <ConfirmDialog
              title="Resume your subscription?"
              keepLabel="Not now"
              confirmLabel="Yes, resume it"
              safe
              onCancel={() => {
                console.info("Resume subscription: not now");
                setAsking(false);
              }}
              onConfirm={resume}
            >
              <p>
                Your subscription, {subscription.price}, starts again now and is charged to the
                card Stripe keeps for you.{" "}
                {subscription.restarted
                  ? "Your site opens at once."
                  : "Your site comes back at once, with everything on it."}
              </p>
              <p>If Stripe needs a card, its secure page opens for you to give one.</p>
            </ConfirmDialog>
          )}
        </div>
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
    {address}
    {deletion}
    </>
  );
}

// The day a cancelled subscription ends, as the host's browser writes dates.
export function endDay(seconds: number): string {
  return new Date(seconds * 1000).toLocaleDateString(undefined, { dateStyle: "long" });
}

// Cancel, for a subscribed site (roadmap R69): the site keeps working until the end of the
// period paid for, then pauses; until then, Keep my subscription undoes it.
// Cancelling or keeping it changes what Delete site says, so `onChanged` reads it again.
function CancelSubscription({
  endsAt,
  days,
  onChanged,
}: {
  endsAt: number | null;
  days: number;
  onChanged?: () => void;
}) {
  const [ends, setEnds] = useState<number | null>(endsAt);
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  async function change(cancel: boolean) {
    setAsking(false);
    setBusy(true);
    setFailed(null);
    try {
      const when = await setSubscriptionCancelled(cancel);
      console.info(cancel ? "Subscription cancelled: it ends" : "Subscription kept", when);
      setEnds(when);
      onChanged?.();
    } catch (e) {
      console.error("Could not change the subscription", e);
      setFailed(e instanceof ServerRefusal ? e.message : "That didn't work. Try again.");
    }
    setBusy(false);
  }

  return (
    <div className="switch">
      {ends !== null ? (
        <>
          <p role="status">
            Cancelled: your site keeps working until {endDay(ends)}, then pauses. Visitors then
            see that it is paused, and you can still sign in and subscribe again. You then have{" "}
            {days} days before its content is deleted.
          </p>
          <button type="button" disabled={busy} onClick={() => change(false)}>
            Keep my subscription
          </button>
        </>
      ) : (
        <>
          <button
            type="button"
            className="remove"
            disabled={busy}
            onClick={() => {
              console.info("Cancel subscription: asking to confirm");
              setAsking(true);
            }}
          >
            Cancel subscription
          </button>
          <p className="muted">
            Your site keeps working until the end of the month paid for, then pauses. You then
            have {days} days to subscribe again before its content is deleted. It asks first.
          </p>
        </>
      )}
      {busy && <p className="muted busy">Asking Stripe…</p>}
      {failed && <p className="error">{failed}</p>}
      {asking && (
        <ConfirmDialog
          title="Are you sure you want to cancel your subscription?"
          keepLabel="No, keep it"
          confirmLabel="Yes, cancel it"
          onCancel={() => {
            console.info("Cancel subscription: kept");
            setAsking(false);
          }}
          onConfirm={() => change(true)}
        >
          <p>Your site keeps working until the end of the month paid for, then pauses.</p>
          <p>
            Until then, you can keep your subscription after all. Once it pauses, you have {days}{" "}
            days to subscribe again before its content is deleted.
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}

// How long typing pauses before the name is checked, in milliseconds.
export const CHECK_AFTER_MS = 300;

// Picking the site's subdomain once its trial is paid for (roadmap R63), or changing the one it
// has (R64, with `current`): the name is checked as it is typed, and the browser then goes to
// the site at its new address, signed in there.
function SubdomainPicker({ current }: { current?: string }) {
  const [name, setName] = useState("");
  const [check, setCheck] = useState<SubdomainCheck | null>(null);
  const [picking, setPicking] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    setCheck(null);
    if (!name.trim()) return;
    let live = true;
    const timer = setTimeout(() => {
      checkSubdomain(name).then(
        (found) => live && setCheck(found),
        (e: unknown) => console.error("Could not check the subdomain", e),
      );
    }, CHECK_AFTER_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [name]);

  async function pick(event: Event) {
    event.preventDefault();
    setPicking(true);
    setFailed(null);
    try {
      const picked = await pickSubdomain(name);
      console.info(
        `Subdomain ${current ? "changed" : "picked"}: going to the site's new address`,
        picked.address,
      );
      go.to(picked.sign_in_at ?? `${picked.address}/`);
    } catch (e) {
      console.error("Could not pick the subdomain", e);
      setFailed(e instanceof ServerRefusal ? e.message : "The address could not be set. Try again.");
      setPicking(false);
    }
  }

  const free = check !== null && check.problem === null && check.name === name.trim().toLowerCase();
  return (
    <form className="switch" onSubmit={pick} aria-label="Your site's address">
      <label htmlFor="settings-subdomain">
        {current ? "Change your site's address" : "Pick your site's address"}
      </label>
      <p className="muted">
        {current
          ? `Your site moves to the new subdomain, with everything on it. ${current} then finds no site, and anyone can take it.`
          : "Your site moves from its trial path to a subdomain of its own, with everything on it. The trial path then goes there."}
      </p>
      <input
        id="settings-subdomain"
        value={name}
        autoComplete="off"
        spellcheck={false}
        disabled={picking}
        onInput={(e) => setName((e.target as HTMLInputElement).value)}
      />
      {check !== null && (
        <p className={check.problem === null ? "muted" : "error"} role="status">
          {check.problem ?? `${check.name} is free.`}
        </p>
      )}
      <button type="submit" disabled={!free || picking}>
        {current ? "Change address" : "Use this address"}
      </button>
      {picking && <p className="muted busy">Moving your site…</p>}
      {failed && <p className="error">{failed}</p>}
    </form>
  );
}

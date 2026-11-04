// Several sites for one host: the pages (roadmap R257, items 208 and 65). The account page lists
// the host's sites with their addresses and adds one; a switcher in the top bar of every host page
// goes to another of them. Each address has its own sign-in, so going there uses a one-time link
// that signs the host in (R256).

import { useEffect, useState } from "preact/hooks";

import {
  addHostSite,
  checkSubdomain,
  getHostSites,
  getSubscription,
  type HostSite,
  openHostSite,
  ServerRefusal,
  type SubdomainCheck,
} from "./api";
import { navigation, useHost } from "./host";
import { CHECK_AFTER_MS } from "./subscription";

// The host's sites, read once they are signed in; null until the server has answered.
export function useHostSites(): HostSite[] | null {
  const { session } = useHost();
  const [sites, setSites] = useState<HostSite[] | null>(null);
  const signedIn = session?.signed_in === true;
  useEffect(() => {
    if (!signedIn) return;
    let live = true;
    getHostSites().then(
      (found) => live && setSites(found),
      (e: unknown) => console.error("Could not read the host's sites", e),
    );
    return () => {
      live = false;
    };
  }, [signedIn]);
  return signedIn ? sites : null;
}

// Where a site is, as shown: its address without the scheme.
export function shown(site: HostSite): string {
  return site.address.replace(/^https?:\/\//, "");
}

async function goToSite(site: string): Promise<void> {
  const started = performance.now();
  const link = await openHostSite(site);
  console.info(`Going to another of the host's sites (${Math.round(performance.now() - started)} ms)`);
  navigation.goTo(link);
}

// The top bar's switcher, for a host with more than one site: picking one goes there, signed in.
export function SiteSwitcher() {
  const sites = useHostSites();
  const [failed, setFailed] = useState(false);
  if (!sites || sites.length < 2) return null;
  const here = sites.find((s) => s.here);
  return (
    <span className="site-switcher">
      <select
        aria-label="Your sites"
        value={here?.site ?? ""}
        onChange={(e) => {
          const site = e.currentTarget.value;
          if (site === here?.site) return;
          setFailed(false);
          goToSite(site).catch((err: unknown) => {
            console.error("Could not open the other site", err);
            setFailed(true);
          });
        }}
      >
        {sites.map((s) => (
          <option key={s.site} value={s.site}>
            {shown(s)}
          </option>
        ))}
      </select>
      {failed && (
        <span className="error" role="alert">
          That site could not be opened. Try again.
        </span>
      )}
    </span>
  );
}

// The account page's list of the host's sites, each with its address, and Add a site.
export function YourSites() {
  const sites = useHostSites();
  const [failed, setFailed] = useState<string | null>(null);
  if (sites === null) return <p className="muted">Reading your sites…</p>;
  return (
    <section aria-labelledby="your-sites">
      <h2 id="your-sites">Your sites</h2>
      <ul className="your-sites">
        {sites.map((s) => (
          <li key={s.site}>
            <span className="site-address">{shown(s)}</span>
            {s.paused && <span className="muted"> · paused</span>}
            {s.here ? (
              <span className="muted"> · this site</span>
            ) : (
              <button
                type="button"
                className="secondary"
                onClick={() => {
                  setFailed(null);
                  goToSite(s.site).catch((err: unknown) => {
                    console.error("Could not open the other site", err);
                    setFailed(err instanceof ServerRefusal ? err.message : "That site could not be opened. Try again.");
                  });
                }}
              >
                Open
              </button>
            )}
          </li>
        ))}
      </ul>
      {failed && (
        <p className="error" role="alert">
          {failed}
        </p>
      )}
      <AddSite />
    </section>
  );
}

// Add a site: its subdomain, checked as it is typed with R63's checks, then Stripe's page to pay
// for it, as each site is its own subscription.
function AddSite() {
  const { session } = useHost();
  const [price, setPrice] = useState<string | null>(null);
  const [available, setAvailable] = useState(true);
  const [name, setName] = useState("");
  const [check, setCheck] = useState<SubdomainCheck | null>(null);
  const [adding, setAdding] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    getSubscription().then(
      (found) => {
        setPrice(found.price);
        setAvailable(found.available);
      },
      (e: unknown) => console.error("Could not read the price", e),
    );
  }, []);

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

  if (session?.acting_as_admin) {
    return <p className="muted">Only the host adds a site, as it is paid for with their card.</p>;
  }
  if (!available) {
    return <p className="muted">Adding a site needs subscribing, which isn't set up here.</p>;
  }

  async function add(event: Event) {
    event.preventDefault();
    setAdding(true);
    setFailed(null);
    try {
      const url = await addHostSite(name);
      console.info("Site added: going to Stripe to pay for it");
      navigation.goTo(url);
    } catch (e) {
      console.error("Could not add a site", e);
      setFailed(e instanceof ServerRefusal ? e.message : "The site could not be added. Try again.");
      setAdding(false);
    }
  }

  const free = check !== null && check.problem === null && check.name === name.trim().toLowerCase();
  return (
    <form className="add-site" onSubmit={add} aria-labelledby="add-a-site">
      <h2 id="add-a-site">Add a site</h2>
      <p className="muted">
        A new site of your own, with its own person, content and settings, at a subdomain you pick.
        {price ? ` It is ${price}, paid on Stripe's secure page.` : ""}
      </p>
      <label>
        The new site's address
        <input
          type="text"
          value={name}
          autoComplete="off"
          spellcheck={false}
          disabled={adding}
          onInput={(e) => setName((e.target as HTMLInputElement).value)}
        />
      </label>
      {check !== null && (
        <p className={check.problem === null ? "muted" : "error"} role="status">
          {check.problem ?? `${check.name} is free.`}
        </p>
      )}
      <button type="submit" disabled={!free || adding}>
        Add and subscribe
      </button>
      {adding && <p className="muted busy">Opening Stripe…</p>}
      {failed && (
        <p className="error" role="alert">
          {failed}
        </p>
      )}
    </form>
  );
}

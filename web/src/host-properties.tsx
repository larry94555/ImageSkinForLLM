// Host properties in Admin settings (roadmap R241, item 195): every host, by email, with a search
// box that narrows the list as it is typed to the emails containing the text anywhere in them,
// ignoring capitals. The server does the matching. R242 adds each host's own Allow and Deny.

import { useEffect, useState } from "preact/hooks";

import { useAdmin } from "./admin";
import { getAdminHosts, ServerRefusal } from "./api";

export function HostProperties() {
  const { refresh } = useAdmin();
  const [search, setSearch] = useState("");
  // null until the server has answered.
  const [hosts, setHosts] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Only the answer for what is in the box now is shown, so a slow one can't replace it.
    let active = true;
    const started = performance.now();
    getAdminHosts(search.trim()).then(
      (found) => {
        if (!active) return;
        console.info(`Host list: ${found.length} shown (${Math.round(performance.now() - started)} ms)`);
        setHosts(found);
        setError(null);
      },
      (e: unknown) => {
        if (!active) return;
        console.error("Could not read the hosts", e);
        if (e instanceof ServerRefusal && e.status === 401) return void refresh();
        setError(e instanceof ServerRefusal ? e.message : "The hosts could not be read. Try again.");
      },
    );
    return () => {
      active = false;
    };
  }, [search]);

  return (
    <section className="panel" aria-labelledby="host-properties">
      <h2 id="host-properties">Host properties</h2>
      <label className="host-search">
        <span>Search hosts by email</span>
        <input
          type="search"
          value={search}
          placeholder="Any part of the email"
          onInput={(e) => setSearch(e.currentTarget.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      {hosts === null && !error && <p className="muted">Reading the hosts…</p>}
      {hosts !== null && hosts.length === 0 && (
        <p className="muted">{search.trim() ? "No host's email contains that." : "No host has signed up yet."}</p>
      )}
      {hosts !== null && hosts.length > 0 && (
        <ul className="host-list" aria-label="Hosts">
          {hosts.map((email) => (
            <li key={email}>{email}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

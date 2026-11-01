// Host properties in Admin settings (roadmap R241, item 195): every host, by email, with a search
// box that narrows the list as it is typed to the emails containing the text anywhere in them,
// ignoring capitals. The server does the matching. R242 adds each host's own Allow and Deny.

import { useEffect, useState } from "preact/hooks";

import { useAdmin } from "./admin";
import { getAdminHosts, ServerRefusal } from "./api";

// What the server answered, and the search it answered: only the answer for what is in the box
// now is shown (Codex's review of PR #267), so while a new search is read, the last one's list or
// message isn't shown under it.
type Answer = { query: string; hosts: string[] } | { query: string; error: string };

export function HostProperties() {
  const { refresh } = useAdmin();
  const [search, setSearch] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const query = search.trim();

  useEffect(() => {
    // Only the answer for what is in the box now is kept, so a slow one can't replace it.
    let active = true;
    const started = performance.now();
    getAdminHosts(query).then(
      (found) => {
        if (!active) return;
        console.info(`Host list: ${found.length} shown (${Math.round(performance.now() - started)} ms)`);
        setAnswer({ query, hosts: found });
      },
      (e: unknown) => {
        if (!active) return;
        console.error("Could not read the hosts", e);
        if (e instanceof ServerRefusal && e.status === 401) return void refresh();
        const error = e instanceof ServerRefusal ? e.message : "The hosts could not be read. Try again.";
        setAnswer({ query, error });
      },
    );
    return () => {
      active = false;
    };
  }, [query]);

  const current = answer?.query === query ? answer : null;
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
      {current === null && <p className="muted">{query ? "Searching…" : "Reading the hosts…"}</p>}
      {current && "error" in current && <p className="error">{current.error}</p>}
      {current && "hosts" in current && current.hosts.length === 0 && (
        <p className="muted">{query ? "No host's email contains that." : "No host has signed up yet."}</p>
      )}
      {current && "hosts" in current && current.hosts.length > 0 && (
        <ul className="host-list" aria-label="Hosts">
          {current.hosts.map((email) => (
            <li key={email}>{email}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

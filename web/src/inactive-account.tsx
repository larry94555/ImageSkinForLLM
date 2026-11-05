// The administrator's test account once the administrator is signed out (roadmap R267 and R268):
// the server answers its every call with only NO_LONGER_ACTIVE. The browser then forgets the
// host's sign-in and shows only that sentence, on a page of its own with no menu or links.

import { useEffect } from "preact/hooks";

import { pathOf } from "./router";

export const NO_LONGER_ACTIVE = "This account is no longer active.";
export const INACTIVE_HASH = "#/no-longer-active";

// Set at the first NO_LONGER_ACTIVE, so the page stays: no other page's redirect replaces it.
export const inactiveAccount = { shown: false };

// Where the page goes; a function of its own so tests can see it.
export const inactiveNavigation = {
  show: () => window.location.replace(INACTIVE_HASH),
};

// Whether a response is the server's NO_LONGER_ACTIVE refusal (R267).
async function saysInactive(response: Response): Promise<boolean> {
  if (response.status !== 403) return false;
  try {
    const body = (await response.clone().json()) as { detail?: unknown };
    return body.detail === NO_LONGER_ACTIVE;
  } catch {
    return false;
  }
}

// Watches every fetch for NO_LONGER_ACTIVE (R268): the first one signs the host out in this
// browser, tells the server's log the page it was on, and shows the page that says only that.
// Every call is covered, so no page needs to check for itself.
export function watchForInactiveAccount(target: { fetch: typeof fetch } = window): void {
  const original = target.fetch.bind(target);
  target.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await original(input, init);
    if (!inactiveAccount.shown && (await saysInactive(response))) {
      inactiveAccount.shown = true;
      const page = pathOf(window.location.hash) || "/";
      console.warn(`Account no longer active, on ${page}: signing out in this browser`);
      await forget(original, page);
      inactiveNavigation.show();
    }
    return response;
  };
}

async function forget(send: typeof fetch, page: string): Promise<void> {
  try {
    const out = await send("/api/host/sign-out", { method: "POST" });
    if (!out.ok) console.error(`Host sign-in not forgotten: ${out.status}`);
    await send("/api/host/inactive-shown", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page }),
    });
  } catch (e: unknown) {
    console.error("Host sign-in not forgotten", e);
  }
}

// The whole page: one sentence, naming nothing else.
export function NoLongerActivePage() {
  useEffect(() => console.info("Inactive account shown"), []);
  return (
    <main>
      <div className="not-active">
        <p className="lead">{NO_LONGER_ACTIVE}</p>
      </div>
    </main>
  );
}

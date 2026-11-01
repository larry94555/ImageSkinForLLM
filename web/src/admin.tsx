// Signing in and out as the administrator (roadmap R150, items 121 and 123): the Settings page's
// Administrator section, the Admin link in the top bar, the admin view at #/admin, and the
// automatic sign-out. The password is set in a file on the computer (R149), never here. The
// server ends a sign-in after its minutes without activity; the page tells it of a click or key
// press in the admin view or on the Settings page, at most once a minute, and checks the
// sign-in each minute, so it shows the sign-out even when nothing is clicked.

import type { ComponentChildren } from "preact";
import { createContext } from "preact";
import { useContext, useEffect, useRef, useState } from "preact/hooks";

import {
  adminActivity,
  type AdminSession,
  getAdminChallenge,
  getAdminSession,
  isLaptopListed,
  ServerRefusal,
  signInAsAdmin,
  signOutAsAdmin,
} from "./api";
import { AdminSettingsPage } from "./admin-settings";
import { AdminGuidelinesPage } from "./admin-guidelines";
import { ResourceDashboard } from "./dashboard";
import { canProve, laptopEntry, laptopId, prove } from "./laptop-key";
import type { AdminSection } from "./router";

// Every step of setting the password, on a laptop and on the hosted site (R151).
export const GUIDE =
  "https://github.com/larry94555/ImageSkinForLLM/blob/main/docs/guides/Admin-Password-Guide.pdf";

export const CHECK_MS = 60_000;
export const ACTIVITY_MS = 60_000;

interface Shared {
  session: AdminSession | null; // null until the server has answered
  // Whether this laptop may sign in (null while asking). A laptop the host's laptops file
  // leaves out sees nothing of the administrator at all (Larry, 2026-10-30).
  listed: boolean | null;
  askListed: () => void; // asks once, from the Settings page or the admin view
  ended: string | null; // why the last sign-in ended by itself, until dismissed
  refresh: () => Promise<void>;
  signIn: (password: string) => Promise<void>;
  signOut: () => Promise<void>;
  dismiss: () => void;
}

const AdminContext = createContext<Shared>({
  session: null,
  listed: null,
  askListed: () => {},
  ended: null,
  refresh: async () => {},
  signIn: async () => {},
  signOut: async () => {},
  dismiss: () => {},
});

export function useAdmin(): Shared {
  return useContext(AdminContext);
}

function minutes(n: number): string {
  return `${n} minute${n === 1 ? "" : "s"}`;
}

function endedMessage(session: AdminSession): string {
  if (session.ended === "password changed") {
    return "Signed out as administrator because the administrator password was changed.";
  }
  // A laptop taken out of the allowed laptops file (R163): no hint of why, as with a failed
  // sign-in (R162).
  if (session.ended === "laptop removed") return "Signed out as administrator.";
  return `Signed out as administrator after ${minutes(session.timeout_minutes)} without activity.`;
}

export function AdminProvider({ children }: { children: ComponentChildren }) {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [ended, setEnded] = useState<string | null>(null);
  const [listed, setListed] = useState<boolean | null>(null);

  async function refresh() {
    try {
      const read = await getAdminSession();
      setSession(read);
      if (read.ended) {
        console.info(`Admin signed out: ${read.ended}`);
        setEnded(endedMessage(read));
      }
    } catch (e) {
      console.error("Could not read the administrator sign-in", e);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  // Whether this laptop is listed, asked once with a proof of a fresh challenge, when a page that
  // needs it opens. Not listed, its ID also goes to the browser console.
  const asked = useRef(false);
  function askListed() {
    if (asked.current) return;
    asked.current = true;
    (async () => {
      const laptop = canProve() ? await prove(await getAdminChallenge()) : undefined;
      const answer = await isLaptopListed(laptop);
      setListed(answer);
      if (!answer && canProve()) console.info(`This laptop's ID: ${await laptopId()}`);
    })().catch((err: unknown) => {
      // The server still checks the laptop at sign-in, so the sign-in is shown rather than lost.
      console.error("Could not ask whether this laptop is listed", err);
      setListed(true);
    });
  }

  // While signed in, check each minute, so a sign-out shows without a click.
  const signedIn = session?.signed_in === true;
  useEffect(() => {
    if (!signedIn) return;
    const timer = setInterval(() => void refresh(), CHECK_MS);
    return () => clearInterval(timer);
  }, [signedIn]);

  async function signIn(password: string) {
    const started = performance.now();
    // This laptop's proof (R164), where the browser can make one; without it, a site with a
    // laptops file refuses the sign-in with the same message as any other failure.
    const laptop = canProve() ? await prove(await getAdminChallenge()) : undefined;
    await signInAsAdmin(password, laptop);
    console.info(`Admin signed in (${Math.round(performance.now() - started)} ms)`);
    setEnded(null);
    await refresh();
  }

  async function signOut() {
    await signOutAsAdmin();
    console.info("Admin signed out: signed out");
    await refresh();
  }

  const shared = { session, listed, askListed, ended, refresh, signIn, signOut, dismiss: () => setEnded(null) };
  return <AdminContext.Provider value={shared}>{children}</AdminContext.Provider>;
}

// Tells the server of a click or key press while `active` (the admin view or the Settings page)
// and signed in, at most once a minute. Nothing else counts as activity: a refresh doesn't.
export function useAdminActivity(active: boolean) {
  const { session, refresh } = useAdmin();
  const last = useRef(0);
  const on = active && session?.signed_in === true;
  useEffect(() => {
    if (!on) return;
    function activity() {
      const now = Date.now();
      if (now - last.current < ACTIVITY_MS) return;
      last.current = now;
      adminActivity()
        .then(async (still) => {
          if (!still) await refresh();
        })
        .catch((e: unknown) => console.error("Could not tell the server of admin activity", e));
    }
    document.addEventListener("click", activity);
    document.addEventListener("keydown", activity);
    return () => {
      document.removeEventListener("click", activity);
      document.removeEventListener("keydown", activity);
    };
  }, [on]);
}

// The top bar's Admin link, while signed in.
export function AdminLink({ current }: { current: boolean }) {
  const { session } = useAdmin();
  if (!session?.signed_in) return null;
  return (
    <a href="#/admin" className={current ? "settings-link current" : "settings-link"}>
      Admin
    </a>
  );
}

// Why the administrator was signed out by itself, on whatever page is open.
export function AdminEndedNotice() {
  const { ended, dismiss } = useAdmin();
  if (!ended) return null;
  return (
    <p className="notice" role="status">
      {ended}{" "}
      <button type="button" className="secondary" onClick={dismiss}>
        OK
      </button>
    </p>
  );
}

// This laptop's ID (R164), to list in admin-laptops.toml on the host. Shown on every laptop, with
// no word of what it is for (Larry, 2026-10-30).
export function LaptopId() {
  const [id, setId] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [copied, setCopied] = useState(false);
  const usable = canProve();

  useEffect(() => {
    if (!usable) return;
    laptopId().then(setId, (err: unknown) => {
      console.error("Could not make this laptop's key", err);
      setFailed(true);
    });
  }, [usable]);

  async function copy() {
    if (!id) return;
    try {
      await navigator.clipboard.writeText(laptopEntry(id));
      setCopied(true);
    } catch (err) {
      console.error("Could not copy the laptop ID", err);
    }
  }

  let shown: ComponentChildren;
  if (!usable) {
    shown = (
      <p className="muted">This laptop's ID can't be shown at this address.</p>
    );
  } else if (failed) {
    shown = <p className="muted">This laptop's ID couldn't be made in this browser.</p>;
  } else {
    shown = (
      <>
        <p>
          This laptop's ID: <code>{id ?? "…"}</code>{" "}
          <button type="button" className="secondary" disabled={!id} onClick={() => void copy()}>
            {copied ? "Copied" : "Copy"}
          </button>
        </p>
      </>
    );
  }
  return (
    <div className="laptop-id">
      <h3>This laptop</h3>
      {shown}
    </div>
  );
}

// The Settings page's Administrator section, in either view.
export function AdminSection() {
  const { session, listed, askListed, signIn, signOut } = useAdmin();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const shown = Boolean(session?.signed_in || listed);

  useEffect(() => {
    if (session) askListed();
  }, [session !== null]);

  useEffect(() => {
    if (shown) console.info("Admin sign-in shown");
  }, [shown]);

  async function submit(e: Event) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(password);
      setPassword("");
    } catch (err) {
      console.error("Could not sign in as administrator", err);
      setError(
        err instanceof ServerRefusal ? err.message : "Could not sign in. Try again in a moment.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function leave() {
    setBusy(true);
    try {
      await signOut();
    } catch (err) {
      console.error("Could not sign out as administrator", err);
      setError("Could not sign out. Try again.");
    } finally {
      setBusy(false);
    }
  }

  let body: ComponentChildren = <p className="muted">Checking…</p>;
  if (session?.signed_in) {
    body = (
      <>
        <p>
          Signed in as administrator. You are signed out after {minutes(session.timeout_minutes)}{" "}
          without activity.
        </p>
        <p>
          <a className="button" href="#/admin">
            Open the admin view
          </a>{" "}
          <button type="button" className="secondary" disabled={busy} onClick={() => void leave()}>
            Sign out as administrator
          </button>
        </p>
      </>
    );
  } else if (session && !session.password_set) {
    body = (
      <p className="muted">
        Signing in as the administrator is off, as no administrator password is set on this
        computer. Whoever runs the computer sets it in the file admin.toml, as the{" "}
        <a href={GUIDE} target="_blank" rel="noreferrer">
          admin password guide
        </a>{" "}
        says.
      </p>
    );
  } else if (session) {
    body = (
      <form onSubmit={(e) => void submit(e)}>
        <label>
          Administrator password{" "}
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onInput={(e) => setPassword(e.currentTarget.value)}
          />
        </label>{" "}
        <button type="submit" disabled={busy || password === ""}>
          Sign in as administrator
        </button>
      </form>
    );
  }

  // On a laptop that isn't listed, only its ID: nothing of the administrator, so the page gives no
  // clue (Larry, 2026-10-30). Nothing while asking.
  if (!shown) {
    if (listed !== false) return null;
    return (
      <section className="panel" aria-label="This laptop">
        <LaptopId />
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="settings-admin">
      <h2 id="settings-admin">Administrator</h2>
      <p className="muted">Running the site as a whole, apart from the host and participant views.</p>
      {error && <p className="error">{error}</p>}
      {body}
      <LaptopId />
    </section>
  );
}

// The admin view: the resource dashboard (R154) at #/admin, the admin settings (R155) at
// #/admin/settings and the admin guidelines (R244) at #/admin/guidelines. Opened without a
// sign-in, it shows the sign-in instead.
export function AdminPage({ section = "resources" }: { section?: AdminSection }) {
  const { session, listed, askListed } = useAdmin();
  useEffect(() => {
    if (session) askListed();
  }, [session !== null]);
  if (!session?.signed_in) {
    // Opened on a laptop that isn't listed: the page any unknown address shows.
    if (!listed) return null;
    return (
      <div className="host-page admin-page">
        <h1>Admin</h1>
        <p className="lead">Site-wide administration, separate from the host and participant views.</p>
        <AdminSection />
      </div>
    );
  }
  const tab = (to: AdminSection, href: string, label: string) => (
    <a href={href} className={section === to ? "current" : undefined} aria-current={section === to ? "page" : undefined}>
      {label}
    </a>
  );
  return (
    <div className="host-page admin-page">
      <h1>Admin</h1>
      <p className="lead">Site-wide administration, separate from the host and participant views.</p>
      <nav className="admin-tabs" aria-label="Admin pages">
        {tab("resources", "#/admin", "Resources")}
        {tab("settings", "#/admin/settings", "Admin settings")}
        {tab("guidelines", "#/admin/guidelines", "Admin guidelines")}
      </nav>
      {section === "settings" ? (
        <AdminSettingsPage />
      ) : section === "guidelines" ? (
        <AdminGuidelinesPage />
      ) : (
        <ResourceDashboard />
      )}
    </div>
  );
}

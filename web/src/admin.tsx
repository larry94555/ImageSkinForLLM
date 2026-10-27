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
  getAdminSession,
  ServerRefusal,
  signInAsAdmin,
  signOutAsAdmin,
} from "./api";
import { AdminSettingsPage } from "./admin-settings";
import { ResourceDashboard } from "./dashboard";

// Every step of setting the password, on a laptop and on the hosted site (R151).
export const GUIDE =
  "https://github.com/larry94555/ImageSkinForLLM/blob/main/docs/guides/Admin-Password-Guide.pdf";

export const CHECK_MS = 60_000;
export const ACTIVITY_MS = 60_000;

interface Shared {
  session: AdminSession | null; // null until the server has answered
  ended: string | null; // why the last sign-in ended by itself, until dismissed
  refresh: () => Promise<void>;
  signIn: (password: string) => Promise<void>;
  signOut: () => Promise<void>;
  dismiss: () => void;
}

const AdminContext = createContext<Shared>({
  session: null,
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
  return `Signed out as administrator after ${minutes(session.timeout_minutes)} without activity.`;
}

export function AdminProvider({ children }: { children: ComponentChildren }) {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [ended, setEnded] = useState<string | null>(null);

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

  // While signed in, check each minute, so a sign-out shows without a click.
  const signedIn = session?.signed_in === true;
  useEffect(() => {
    if (!signedIn) return;
    const timer = setInterval(() => void refresh(), CHECK_MS);
    return () => clearInterval(timer);
  }, [signedIn]);

  async function signIn(password: string) {
    const started = performance.now();
    await signInAsAdmin(password);
    console.info(`Admin signed in (${Math.round(performance.now() - started)} ms)`);
    setEnded(null);
    await refresh();
  }

  async function signOut() {
    await signOutAsAdmin();
    console.info("Admin signed out: signed out");
    await refresh();
  }

  const shared = { session, ended, refresh, signIn, signOut, dismiss: () => setEnded(null) };
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

// The Settings page's Administrator section, in either view.
export function AdminSection() {
  const { session, signIn, signOut } = useAdmin();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => console.info("Admin sign-in shown"), []);

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

  return (
    <section className="panel" aria-labelledby="settings-admin">
      <h2 id="settings-admin">Administrator</h2>
      <p className="muted">Running the site as a whole, apart from the host and participant views.</p>
      {error && <p className="error">{error}</p>}
      {body}
    </section>
  );
}

// The admin view: the resource dashboard (R154) at #/admin and the admin settings (R155) at
// #/admin/settings. Opened without a sign-in, it shows the sign-in instead.
export function AdminPage({ section = "resources" }: { section?: "resources" | "settings" }) {
  const { session } = useAdmin();
  if (!session?.signed_in) {
    return (
      <div className="host-page admin-page">
        <h1>Admin</h1>
        <p className="lead">Site-wide administration, separate from the host and participant views.</p>
        <AdminSection />
      </div>
    );
  }
  const tab = (to: "resources" | "settings", href: string, label: string) => (
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
      </nav>
      {section === "settings" ? <AdminSettingsPage /> : <ResourceDashboard />}
    </div>
  );
}

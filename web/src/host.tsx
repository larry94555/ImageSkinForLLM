// Signing up, in and out as a host (roadmap R189, items 148 and 149): the top bar's Host sign up
// and Host sign in links, or the signed-in host's email and Sign out, and the two pages at
// #/host/sign-up and #/host/sign-in. The accounts are on the server (R188).

import type { ComponentChildren } from "preact";
import { createContext } from "preact";
import { useContext, useEffect, useState } from "preact/hooks";

import {
  getHostSession,
  hostPageOpened,
  type HostSession,
  ServerRefusal,
  signInAsHost,
  signOutAsHost,
  signUpAsHost,
} from "./api";

// As the server checks (R188), so a short password is said at once.
export const MIN_PASSWORD = 10;

interface Shared {
  session: HostSession | null; // null until the server has answered
  signUp: (email: string, password: string) => Promise<void>;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const HostContext = createContext<Shared>({
  session: null,
  signUp: async () => {},
  signIn: async () => {},
  signOut: async () => {},
});

export function useHost(): Shared {
  return useContext(HostContext);
}

const SIGNED_OUT: HostSession = { signed_in: false, email: null };

export function HostProvider({ children }: { children: ComponentChildren }) {
  const [session, setSession] = useState<HostSession | null>(null);

  useEffect(() => {
    getHostSession().then(setSession, (e: unknown) => {
      // Shown as signed out, so the sign-in links are there to try again.
      console.error("Could not read the host sign-in", e);
      setSession(SIGNED_OUT);
    });
  }, []);

  async function account(kind: "up" | "in", email: string, password: string) {
    const started = performance.now();
    const signedIn = await (kind === "up" ? signUpAsHost : signInAsHost)(email, password);
    console.info(`Host signed ${kind} (${Math.round(performance.now() - started)} ms)`);
    setSession(signedIn);
  }

  async function signOut() {
    await signOutAsHost();
    console.info("Host signed out");
    setSession(SIGNED_OUT);
  }

  const shared = {
    session,
    signUp: (email: string, password: string) => account("up", email, password),
    signIn: (email: string, password: string) => account("in", email, password),
    signOut,
  };
  return <HostContext.Provider value={shared}>{children}</HostContext.Provider>;
}

// The top bar's host links: Host sign up and Host sign in, or the host's email and Sign out.
// Signing out returns to the participant view's page, the chat.
export function HostLinks({ page }: { page?: string }) {
  const { session, signOut } = useHost();
  const [busy, setBusy] = useState(false);
  if (!session) return null;
  if (session.signed_in) {
    async function leave() {
      setBusy(true);
      try {
        await signOut();
        window.location.hash = "#/chat";
      } catch (e) {
        // Still signed in, so Sign out stays there to try again.
        console.error("Could not sign out as host", e);
      } finally {
        setBusy(false);
      }
    }
    return (
      <span className="host-links">
        <span className="host-email" title="Signed in as host">
          {session.email}
        </span>
        <button type="button" className="secondary" disabled={busy} onClick={() => void leave()}>
          Sign out
        </button>
      </span>
    );
  }
  const link = (to: string, href: string, label: string) => (
    <a href={href} className={page === to ? "settings-link current" : "settings-link"}>
      {label}
    </a>
  );
  return (
    <span className="host-links">
      {link("host-sign-up", "#/host/sign-up", "Host sign up")}
      {link("host-sign-in", "#/host/sign-in", "Host sign in")}
    </span>
  );
}

// The Host sign up page (kind "up") or the Host sign in page (kind "in"). Signed in, it goes to
// the home page.
export function HostAccountPage({ kind }: { kind: "up" | "in" }) {
  const { session, signUp, signIn } = useHost();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const up = kind === "up";

  useEffect(() => {
    setError(null);
    hostPageOpened(up ? "sign-up" : "sign-in").catch((e: unknown) =>
      console.error("Could not log the host page opened", e),
    );
  }, [up]);

  // A wrong field is said before asking the server; the server says the rest.
  function problem(): string | null {
    if (!up) return null;
    if (password.length < MIN_PASSWORD) {
      return `The password must be at least ${MIN_PASSWORD} characters.`;
    }
    if (password !== again) return "The two passwords are different.";
    return null;
  }

  async function submit(e: Event) {
    e.preventDefault();
    const found = problem();
    setError(found);
    if (found) return;
    setBusy(true);
    try {
      await (up ? signUp : signIn)(email, password);
      window.location.hash = "#/";
    } catch (err) {
      console.error(`Could not sign ${kind} as host`, err);
      setError(err instanceof ServerRefusal ? err.message : "That didn't work. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const title = up ? "Host sign up" : "Host sign in";
  if (session?.signed_in) {
    return (
      <div className="host-page host-account">
        <h1>{title}</h1>
        <p>
          You are signed in as host with {session.email}. <a href="#/">Go to the home page</a>
        </p>
      </div>
    );
  }
  return (
    <div className="host-page host-account">
      <h1>{title}</h1>
      <p className="lead">
        {up
          ? "Make a host account to set up the person and their content."
          : "Sign in with the email and password of your host account."}
      </p>
      <form onSubmit={(e) => void submit(e)} noValidate>
        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            value={email}
            onInput={(e) => setEmail(e.currentTarget.value)}
          />
        </label>
        <label>
          Password{up && ` (at least ${MIN_PASSWORD} characters)`}
          <input
            type="password"
            autoComplete={up ? "new-password" : "current-password"}
            value={password}
            onInput={(e) => setPassword(e.currentTarget.value)}
          />
        </label>
        {up && (
          <label>
            Password again
            <input
              type="password"
              autoComplete="new-password"
              value={again}
              onInput={(e) => setAgain(e.currentTarget.value)}
            />
          </label>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy || email.trim() === "" || password === ""}>
          {up ? "Sign up" : "Sign in"}
        </button>
      </form>
      <p className="muted">
        {up ? (
          <>
            Already a host? <a href="#/host/sign-in">Host sign in</a>
          </>
        ) : (
          <>
            New here? <a href="#/host/sign-up">Host sign up</a>
          </>
        )}
      </p>
    </div>
  );
}

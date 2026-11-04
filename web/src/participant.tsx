// A participant's account with this site's host (roadmap R46, R260): Sign up and Sign in in the top bar for anyone
// not signed in as a host, or the participant's email and Sign out, and the two pages at
// #/sign-up and #/sign-in. A signed-in participant's conversation is their account's, so it
// follows them to another browser; the server picks it by their cookie.

import type { ComponentChildren } from "preact";
import { createContext } from "preact";
import { useContext, useEffect, useState } from "preact/hooks";

import {
  getParticipantProgress,
  getParticipantSession,
  putParticipantProgress,
  ParticipantSession,
  ServerRefusal,
  signInAsParticipant,
  signOutAsParticipant,
  signUpAsParticipant,
} from "./api";
import { MIN_PASSWORD } from "./host";
import {
  clearProgress,
  type Kept,
  readProgress,
  syncProgress,
  writeProgress,
} from "./progress";

// The signed-in participant's progress (R46): what the account kept is put on this browser in
// place of whatever is here, even when it kept none, so one person's lesson left on a browser
// never shows to, or is saved for, another account (Codex's review of PR #308). Then each change
// is sent.
async function followProgress(): Promise<void> {
  const started = performance.now();
  const kept = (await getParticipantProgress()) as Kept;
  writeProgress(kept);
  syncProgress((now) => {
    putParticipantProgress(now).catch((e: unknown) =>
      console.error("Could not keep the progress for the account", e),
    );
  });
  console.info(
    `Participant progress followed (${Object.keys(kept).join(", ") || "none kept"}, ${Math.round(performance.now() - started)} ms)`,
  );
}

interface Shared {
  session: ParticipantSession | null; // null until the server has answered
  signUp: (email: string, password: string) => Promise<ParticipantSession>;
  signIn: (email: string, password: string) => Promise<ParticipantSession>;
  signOut: () => Promise<void>;
}

// Reads the page again, or opens another site's; functions of their own so tests can see them.
export const reloading = {
  reload: () => window.location.reload(),
  goTo: (url: string) => window.location.assign(url),
};

const SIGNED_OUT: ParticipantSession = { signed_in: false, email: null };

const ParticipantContext = createContext<Shared>({
  session: SIGNED_OUT,
  signUp: async () => SIGNED_OUT,
  signIn: async () => SIGNED_OUT,
  signOut: async () => {},
});

export function useParticipant(): Shared {
  return useContext(ParticipantContext);
}

export function ParticipantProvider({
  children,
}: {
  children: ComponentChildren;
}) {
  const [session, setSession] = useState<ParticipantSession | null>(null);

  useEffect(() => {
    getParticipantSession()
      .then(async (found) => {
        if (found.signed_in) {
          // Before the pages open, so the chat starts from the account's lesson.
          await followProgress().catch((e: unknown) =>
            console.error("Could not read the progress for the account", e),
          );
        }
        setSession(found);
      })
      .catch((e: unknown) => {
        // Shown as signed out, so Sign in is there to try again.
        console.error("Could not read the participant sign-in", e);
        setSession(SIGNED_OUT);
      });
    return () => syncProgress(null);
  }, []);

  async function account(kind: "up" | "in", email: string, password: string) {
    const started = performance.now();
    const signedIn = await (
      kind === "up" ? signUpAsParticipant : signInAsParticipant
    )(email, password);
    console.info(
      `Participant signed ${kind} (${Math.round(performance.now() - started)} ms)`,
    );
    if (kind === "up") {
      // A lesson begun on this browser just before signing up becomes the new account's; only
      // here, as the account was made this moment by this browser.
      const here = readProgress();
      if (Object.keys(here).length > 0) {
        await putParticipantProgress(here).catch((e: unknown) =>
          console.error("Could not keep the lesson for the new account", e),
        );
      }
    }
    setSession(signedIn);
    return signedIn;
  }

  const shared: Shared = {
    session,
    signUp: (email, password) => account("up", email, password),
    signIn: (email, password) => account("in", email, password),
    signOut: async () => {
      await signOutAsParticipant();
      console.info("Participant signed out");
      // The account's progress stays with the account, not on this browser.
      syncProgress(null);
      clearProgress();
      setSession(SIGNED_OUT);
    },
  };
  return (
    <ParticipantContext.Provider value={shared}>
      {children}
    </ParticipantContext.Provider>
  );
}

// The top bar's participant links: Sign up and Sign in, or the participant's email and Sign out.
// Signing in or out starts the chat again, as the conversation is the account's, or the browser's.
export function ParticipantLinks({ page }: { page?: string }) {
  const { session, signOut } = useParticipant();
  const [busy, setBusy] = useState(false);
  if (!session) return null;
  if (session.signed_in) {
    async function leave() {
      setBusy(true);
      try {
        await signOut();
        window.location.hash = "#/chat";
        reloading.reload();
      } catch (e) {
        console.error("Could not sign out as participant", e);
        setBusy(false);
      }
    }
    return (
      <span className="host-links participant-links">
        <span className="host-email" title="You are signed in">
          {session.email}
        </span>
        <button
          type="button"
          className="secondary"
          disabled={busy}
          onClick={() => void leave()}
        >
          Sign out
        </button>
      </span>
    );
  }
  const link = (to: string, href: string, label: string) => (
    <a
      href={href}
      className={page === to ? "settings-link current" : "settings-link"}
    >
      {label}
    </a>
  );
  return (
    <span className="host-links participant-links">
      {link("participant-sign-up", "#/sign-up", "Sign up")}
      {link("participant-sign-in", "#/sign-in", "Sign in")}
    </span>
  );
}

// Sign up and Sign in for participants (R46). Once signed in, the chat opens again with the
// account's own conversation.
export function ParticipantAccountPage({ kind }: { kind: "up" | "in" }) {
  const { session, signUp, signIn } = useParticipant();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const up = kind === "up";

  useEffect(() => {
    setError(null);
    console.info(`Participant ${up ? "sign-up" : "sign-in"} page shown`);
  }, [up]);

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
      const signedIn = await (up ? signUp : signIn)(email, password);
      if (signedIn.go_to) {
        // The host sends them to another of their sites (R261), where they are signed in too.
        console.info(`Participant sent to ${signedIn.go_to}`);
        reloading.goTo(signedIn.go_to);
        return;
      }
      // The chat is read again, as the account's conversation.
      window.location.hash = "#/chat";
      reloading.reload();
    } catch (err) {
      console.error(`Could not sign ${kind} as participant`, err);
      setError(
        err instanceof ServerRefusal
          ? err.message
          : "That didn't work. Please try again.",
      );
      setBusy(false);
    }
  }

  const title = up ? "Sign up" : "Sign in";
  if (session?.signed_in) {
    return (
      <div className="host-page host-account">
        <h1>{title}</h1>
        <p>
          You are signed in with {session.email}.{" "}
          <a href="#/chat">Go to the chat</a>
        </p>
      </div>
    );
  }
  return (
    <div className="host-page host-account">
      <h1>{title}</h1>
      <p className="lead">
        {up
          ? "Make an account, so your conversation is kept for you on any browser. It works on every site of this host."
          : "Sign in with the email and password of your account with this host."}
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
        <button
          type="submit"
          disabled={busy || email.trim() === "" || password === ""}
        >
          {title}
        </button>
      </form>
      <p className="muted">
        {up ? (
          <>
            Have an account? <a href="#/sign-in">Sign in</a>
          </>
        ) : (
          <>
            New here? <a href="#/sign-up">Sign up</a>
          </>
        )}
      </p>
    </div>
  );
}

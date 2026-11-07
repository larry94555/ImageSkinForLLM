// A participant's account with this site's host (roadmap R46, R260): the top bar's one Sign in
// link (R269) for anyone not signed in, or the participant's display name and Sign out. The
// Sign in page is in sign-in.tsx. A signed-in participant's conversation is their account's, so
// it follows them to another browser; the server picks it by their cookie.

import type { ComponentChildren } from "preact";
import { createContext } from "preact";
import { useContext, useEffect, useState } from "preact/hooks";

import {
  getParticipantProgress,
  getParticipantSession,
  putParticipantProgress,
  ParticipantSession,
  signInAsParticipant,
  signOutAsParticipant,
  signUpAsParticipant,
} from "./api";
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
  signUp: (email: string, password: string, displayName?: string) => Promise<ParticipantSession>;
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
        if (found.signed_in && found.allowed !== false) {
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

  async function account(kind: "up" | "in", email: string, password: string, name?: string) {
    const started = performance.now();
    const signedIn = await (kind === "up"
      ? signUpAsParticipant(email, password, name)
      : signInAsParticipant(email, password));
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
    signUp: (email, password, name) => account("up", email, password, name),
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

// The top bar's links for anyone not signed in as a host: the one Sign in link (R269), or the
// participant's display name and Sign out.
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
          {session.display_name || session.email}
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
  return (
    <span className="host-links participant-links">
      <a
        href="#/sign-in"
        className={page === "sign-in" ? "settings-link current" : "settings-link"}
      >
        Sign in
      </a>
    </span>
  );
}

// What a signed-in participant sees on one of the host's sites the host doesn't let them open
// (R262): one sentence, naming neither the host nor anything of the site, as the site's calls
// refuse them.
export const NOT_ACTIVE =
  "This subdomain is not yet active -- check with the host on its status.";

export function NotActivePage() {
  useEffect(() => console.info("Not active page shown"), []);
  return (
    <div className="not-active">
      <p className="lead">{NOT_ACTIVE}</p>
    </div>
  );
}

// Signing up, in and out as a host (roadmap R189, items 148 and 149): the top bar's Host sign up
// and Host sign in links, or the signed-in host's email and Sign out, and the two pages at
// #/host/sign-up and #/host/sign-in. The accounts are on the server (R188).

import type { ComponentChildren } from "preact";
import { createContext } from "preact";
import { useContext, useEffect, useRef, useState } from "preact/hooks";

import { useSettingsReload } from "./settings";

import {
  actingActivity,
  changeEmail,
  forgotPassword,
  getHostSession,
  hostPageOpened,
  type HostSession,
  sendConfirmationAgain,
  ServerRefusal,
  setNewPassword,
  signInAsHost,
  signOutAsHost,
  signUpAsHost,
  stopActing,
} from "./api";

// As the server checks (R188), so a short password is said at once.
export const MIN_PASSWORD = 10;

interface Shared {
  session: HostSession | null; // null until the server has answered
  // Acting ended by itself (R44b): the session is read again, signed out of the host's site.
  actingEnded: () => void;
  // Each resolves to true when the browser is leaving for the host's new site (R62).
  signUp: (email: string, password: string) => Promise<boolean>;
  signIn: (email: string, password: string) => Promise<boolean>;
  signOut: () => Promise<void>;
}

const HostContext = createContext<Shared>({
  session: null,
  actingEnded: () => {},
  signUp: async () => false,
  signIn: async () => false,
  signOut: async () => {},
});

export function useHost(): Shared {
  return useContext(HostContext);
}

const SIGNED_OUT: HostSession = { signed_in: false, email: null };

// Leaves this page for another address; a function of its own so tests can see where.
export const navigation = { goTo: (url: string) => window.location.assign(url) };
function goTo(url: string) {
  navigation.goTo(url);
}

export function HostProvider({ children }: { children: ComponentChildren }) {
  const [session, setSession] = useState<HostSession | null>(null);
  // The view follows who is signed in (R190), so the settings are read again after a change.
  const reload = useSettingsReload();

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
    if (signedIn.go_to) {
      // Signing up made the host a site of their own (R62): its setup is next.
      console.info(`Host's new site: ${signedIn.go_to}`);
      goTo(`${signedIn.go_to}#/setup`);
      return true;
    }
    setSession(signedIn);
    await reload();
    return false;
  }

  async function signOut() {
    await signOutAsHost();
    console.info("Host signed out");
    setSession(SIGNED_OUT);
    await reload();
  }

  const shared = {
    session,
    actingEnded: () => {
      setSession(SIGNED_OUT);
      void reload();
    },
    signUp: (email: string, password: string) => account("up", email, password),
    signIn: (email: string, password: string) => account("in", email, password),
    signOut,
  };
  return <HostContext.Provider value={shared}>{children}</HostContext.Provider>;
}

// The top bar's host links: Host sign up and Host sign in, or Resources (R193), the host's email
// and Sign out.
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
        <a
          href="#/resources"
          className={page === "resources" ? "settings-link current" : "settings-link"}
        >
          Resources
        </a>
        <a className="host-email" href="#/host/account" title="Your account">
          {session.email}
        </a>
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

// A click while acting counts as the administrator's activity, at most once a minute (R44b),
// as on the Settings page (R150).
export const ACTIVITY_MS = 60_000;

// The bar on every page while the administrator acts as this site's host (R44a, R44b): who they
// act as, and Stop acting, which goes back to the admin view at the main address. When acting
// ends by itself (the administrator signed out, or out for inactivity), it says so instead.
export function ActingBar() {
  const { session, actingEnded } = useHost();
  const [busy, setBusy] = useState(false);
  const [ended, setEnded] = useState<string | null>(null);
  // Set as Stop acting is clicked, before that click reaches the page's listener, so the click
  // isn't also sent as activity just as acting stops.
  const stopping = useRef(false);
  const acting = session?.signed_in === true && session.acting_as_admin === true;
  const email = session?.email ?? "";

  useEffect(() => {
    if (acting) console.info("Acting as host started");
  }, [acting]);

  useEffect(() => {
    if (!acting) return;
    let last = 0;
    const onClick = () => {
      if (stopping.current) return;
      const now = Date.now();
      if (now - last < ACTIVITY_MS) return;
      last = now;
      actingActivity().then(
        (still) => {
          if (still) return;
          console.info("Acting as host stopped: no longer signed in as the administrator");
          setEnded(email);
          actingEnded();
        },
        (e: unknown) => console.error("Could not note the administrator's activity", e),
      );
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [acting, email]);

  async function stop() {
    stopping.current = true;
    setBusy(true);
    try {
      const back = await stopActing();
      console.info("Acting as host stopped");
      if (back) goTo(back);
      else {
        setEnded(email);
        actingEnded();
      }
    } catch (e) {
      console.error("Could not stop acting as the host", e);
      stopping.current = false;
    } finally {
      setBusy(false);
    }
  }

  if (ended) {
    return (
      <div className="acting-bar ended" role="status">
        Stopped acting as {ended}.
      </div>
    );
  }
  if (!acting) return null;
  return (
    <div className="acting-bar" role="status">
      <span>
        Acting as <strong>{email}</strong>, as the administrator
      </span>
      <button type="button" className="secondary" disabled={busy} onClick={() => void stop()}>
        Stop acting
      </button>
    </div>
  );
}

// Where an Act as this host link that didn't work goes (R44b).
export function ActAsFailedPage() {
  useEffect(() => console.info("Act as host link failed page shown"), []);
  return (
    <div className="host-page host-account">
      <h1>Couldn't act as this host</h1>
      <p className="error" role="alert">
        That link didn't work: it was already used, is more than a minute old, was opened on
        another host's site, or the administrator has signed out. Make a new one with Act as this
        host in Admin settings.
      </p>
    </div>
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
      const leaving = await (up ? signUp : signIn)(email, password);
      if (!leaving) window.location.hash = "#/";
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
            New here? <a href="#/host/sign-up">Host sign up</a> ·{" "}
            <a href="#/host/forgot">Forgot your password?</a>
          </>
        )}
      </p>
    </div>
  );
}

// A host page opened by anyone not signed in as a host (R190): what it is, and how to sign in.
// Its calls to the server are refused too.
export function HostOnlyPage() {
  useEffect(() => console.info(`Host page refused: ${window.location.hash}`), []);
  return (
    <div className="host-page host-account">
      <h1>For the host only</h1>
      <p className="lead">This page is for the host, who sets up the person and their content.</p>
      <p>
        <a className="button" href="#/host/sign-in">
          Host sign in
        </a>{" "}
        or <a href="#/chat">go to the chat</a>
      </p>
    </div>
  );
}

// Every page of a customer's site until they confirm their email (R62b): where the link was sent,
// and Send it again. `failed` when a confirmation link didn't work.
export function ConfirmEmailPage({ email, failed = false }: { email: string; failed?: boolean }) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => console.info(`Confirm your email shown (link failed: ${failed})`), [failed]);

  async function again() {
    setBusy(true);
    setNote(null);
    setError(null);
    try {
      await sendConfirmationAgain();
      console.info("Confirmation email sent again");
      setNote(`A new link is on its way to ${email}.`);
    } catch (e) {
      console.error("Could not send the confirmation email again", e);
      setError(e instanceof ServerRefusal ? e.message : "That didn't work. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="host-page host-account">
      <h1>Confirm your email</h1>
      {failed && (
        <p className="error" role="alert">
          {LINK_FAILED}
        </p>
      )}
      <p className="lead">
        We sent a link to <strong>{email}</strong>. Open it to start setting up your site. The link
        works for 7 days.
      </p>
      {note && <p role="status">{note}</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <button type="button" disabled={busy} onClick={() => void again()}>
        Send it again
      </button>
    </div>
  );
}

const LINK_FAILED =
  "That confirmation link didn't work: it was already used, a newer one was sent, or it is" +
  " more than 7 days old.";

// Where a confirmation link that didn't work goes, for someone not signed in here (R62b).
export function ConfirmFailedPage() {
  useEffect(() => console.info("Confirmation link failed page shown"), []);
  return (
    <div className="host-page host-account">
      <h1>Confirm your email</h1>
      <p className="error" role="alert">
        {LINK_FAILED}
      </p>
      <p>
        <a className="button" href="#/host/sign-in">
          Host sign in
        </a>{" "}
        to send a new one.
      </p>
    </div>
  );
}

// Forgot password (R62a): asks for a link to set a new password, by email. The server answers
// the same whether or not the email has an account, and that answer is shown.
export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => console.info("Forgot password page shown"), []);

  async function submit(e: Event) {
    e.preventDefault();
    setBusy(true);
    setNote(null);
    setError(null);
    try {
      setNote(await forgotPassword(email));
      console.info("Password reset link asked for");
    } catch (err) {
      console.error("Could not ask for a password reset link", err);
      setError(err instanceof ServerRefusal ? err.message : "That didn't work. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="host-page host-account">
      <h1>Forgot your password?</h1>
      <p className="lead">Enter your account's email, and we'll send a link to set a new password.</p>
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
        {note && <p role="status">{note}</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy || email.trim() === ""}>
          Send the link
        </button>
      </form>
      <p className="muted">
        Remembered it? <a href="#/host/sign-in">Host sign in</a>
      </p>
    </div>
  );
}

// The page a Forgot password link opens, #/host/reset/<token> (R62a): the new password, twice.
export function ResetPasswordPage({ token }: { token: string }) {
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => console.info("Set a new password page shown"), []);

  async function submit(e: Event) {
    e.preventDefault();
    if (password.length < MIN_PASSWORD) {
      setError(`The password must be at least ${MIN_PASSWORD} characters.`);
      return;
    }
    if (password !== again) {
      setError("The two passwords are different.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await setNewPassword(token, password);
      console.info("New password set");
      setDone(true);
    } catch (err) {
      console.error("Could not set the new password", err);
      setError(err instanceof ServerRefusal ? err.message : "That didn't work. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="host-page host-account">
        <h1>Set a new password</h1>
        <p role="status">Your new password is set. Sign in with it.</p>
        <p>
          <a className="button" href="#/host/sign-in">
            Host sign in
          </a>
        </p>
      </div>
    );
  }
  return (
    <div className="host-page host-account">
      <h1>Set a new password</h1>
      <form onSubmit={(e) => void submit(e)} noValidate>
        <label>
          New password (at least {MIN_PASSWORD} characters)
          <input
            type="password"
            autoComplete="new-password"
            value={password}
            onInput={(e) => setPassword(e.currentTarget.value)}
          />
        </label>
        <label>
          New password again
          <input
            type="password"
            autoComplete="new-password"
            value={again}
            onInput={(e) => setAgain(e.currentTarget.value)}
          />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy || password === ""}>
          Set the password
        </button>
      </form>
      <p className="muted">
        Link not working? <a href="#/host/forgot">Ask for a new one</a>
      </p>
    </div>
  );
}

// The signed-in host's account (R62c): their email, and Change email, which sends a link to the
// new address; nothing changes until it is opened.
export function AccountPage() {
  const { session } = useHost();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => console.info("Account page shown"), []);
  if (!session?.signed_in) return <HostOnlyPage />;

  async function submit(e: Event) {
    e.preventDefault();
    setBusy(true);
    setSentTo(null);
    setError(null);
    try {
      setSentTo(await changeEmail(email, password));
      setPassword("");
      console.info("Email change link sent");
    } catch (err) {
      console.error("Could not ask to change the email", err);
      setError(err instanceof ServerRefusal ? err.message : "That didn't work. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="host-page host-account">
      <h1>Your account</h1>
      <p className="lead">
        You sign in with <strong>{session.email}</strong>.
      </p>
      <h2>Change email</h2>
      <form onSubmit={(e) => void submit(e)} noValidate>
        <label>
          New email
          <input
            type="email"
            autoComplete="email"
            value={email}
            onInput={(e) => setEmail(e.currentTarget.value)}
          />
        </label>
        <label>
          {/* The administrator acting as the host gives their own password (R44b). */}
          {session.acting_as_admin ? "Administrator password" : "Your password"}
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onInput={(e) => setPassword(e.currentTarget.value)}
          />
        </label>
        {sentTo && (
          <p role="status">
            We sent a link to {sentTo}. Your email changes once you open it; until then it stays{" "}
            {session.email}.
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy || email.trim() === "" || password === ""}>
          Send the link
        </button>
      </form>
    </div>
  );
}

// Where the link to confirm a new email goes (R62c): changed, or a link that didn't work.
export function EmailChangedPage({ changed }: { changed: boolean }) {
  useEffect(() => console.info(`Email change page shown (changed: ${changed})`), [changed]);
  return (
    <div className="host-page host-account">
      <h1>{changed ? "Your email is changed" : "Your email isn't changed"}</h1>
      {changed ? (
        <p role="status">Sign in with your new email from now on.</p>
      ) : (
        <p className="error" role="alert">
          That link didn't work: it was already used, a newer one was sent, it is more than a day
          old, or the new email is now another account's. Ask for a new one on your account page.
        </p>
      )}
      <p>
        <a className="button" href="#/host/account">
          Your account
        </a>
      </p>
    </div>
  );
}

// One Sign in page for everyone (roadmap R269, item 220), in place of Sign up, Sign in, Host sign
// up and Host sign in. It has the fields Host sign up had: email, display name, password and
// the password again. An email and password that match a host's account sign the host in; else
// ones that match a participant's account here sign the participant in. Otherwise, with the
// password typed twice, it makes a new account: a host's at the main address, a participant's
// on a host's site (R270), where the page says nothing of hosts. The display name is
// filled in from the email, before the @, with a number that makes it unlike every other, and
// can be changed.

import { useEffect, useRef, useState } from "preact/hooks";

import {
  hostPageOpened,
  restartSite,
  ServerRefusal,
  SiteWasDeleted,
  suggestDisplayName,
} from "./api";
import { DISPLAY_NAME_MAX, MIN_PASSWORD, navigation, useHost } from "./host";
import { reloading, useParticipant } from "./participant";

// Said when the email and password match no account and the password wasn't typed twice, so it
// may be a new account or a wrong password. It never says which.
export const NO_MATCH =
  "That email and password don't match an account. New here? Type the password again below to make one.";
const FAILED = "That didn't work. Please try again.";

// A sign-in refused for its email and password, which may then be a participant's, or new.
function wrongPassword(err: unknown): boolean {
  return err instanceof ServerRefusal && err.status === 401 && !(err instanceof SiteWasDeleted);
}

// The administrator's test sign-up (R265): an email with "-admin" at the end only signs up.
function testSignUp(email: string): boolean {
  return email.trim().toLowerCase().endsWith("-admin");
}

export function SignInPage() {
  const host = useHost();
  const participant = useParticipant();
  // On a host's site, only participants sign up, and nothing names a host (R270).
  const participantOnly = host.session?.participant_only === true;
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The host's site was deleted (R69a): Start my site again (R69c).
  const [deleted, setDeleted] = useState(false);
  // Once the person types a display name, it is theirs: the email no longer fills it in.
  const named = useRef(false);
  // The email the display name was last filled in for, so it is asked once per email.
  const suggestedFor = useRef("");
  // Counts the suggestions asked for and the emails typed, so an answer for an email since
  // changed is left out.
  const asked = useRef(0);

  useEffect(() => {
    hostPageOpened("sign-in").catch((e: unknown) =>
      console.error("Could not log the sign-in page opened", e),
    );
  }, []);

  // Fills in the display name from the email (R269), unless the person has typed one.
  async function suggest() {
    const typed = email.trim();
    if (named.current || !typed.includes("@") || typed === suggestedFor.current) return;
    suggestedFor.current = typed;
    const ask = ++asked.current;
    try {
      const name = await suggestDisplayName(typed);
      if (ask !== asked.current) {
        console.info("Display name suggestion left out: the email changed");
        return;
      }
      if (!named.current) setDisplayName(name);
    } catch (e) {
      // Left blank, the server names the account by the email before the @. Leaving the email
      // and coming back asks again.
      console.error("Could not suggest a display name", e);
      if (ask === asked.current) suggestedFor.current = "";
    }
  }

  function finish(err: unknown) {
    console.error("Could not sign in", err);
    setError(err instanceof ServerRefusal ? err.message : FAILED);
    setDeleted(err instanceof SiteWasDeleted);
    setBusy(false);
  }

  // A participant signed in or up: the chat, read again as the account's, or the site the host
  // sends them to (R261).
  function participantIn(goTo?: string) {
    if (goTo) {
      console.info(`Participant sent to ${goTo}`);
      reloading.goTo(goTo);
      return;
    }
    window.location.hash = "#/chat";
    reloading.reload();
  }

  async function signIn(): Promise<boolean> {
    try {
      if (!(await host.signIn(email, password))) window.location.hash = "#/";
      setBusy(false);
      return true;
    } catch (err) {
      if (!wrongPassword(err)) {
        finish(err);
        return true;
      }
    }
    try {
      const signedIn = await participant.signIn(email, password);
      participantIn(signedIn.go_to);
      return true;
    } catch (err) {
      if (!wrongPassword(err)) {
        finish(err);
        return true;
      }
    }
    return false;
  }

  async function signUp() {
    if (password.length < MIN_PASSWORD) {
      setError(`The password must be at least ${MIN_PASSWORD} characters.`);
      setBusy(false);
      return;
    }
    if (password !== again) {
      setError("The two passwords are different.");
      setBusy(false);
      return;
    }
    // A host's site takes participants (R270); the main address, hosts.
    const asParticipant = participantOnly;
    console.info(`New account: ${asParticipant ? "participant" : "host"}`);
    try {
      if (asParticipant) {
        const signedIn = await participant.signUp(email, password, displayName);
        participantIn(signedIn.go_to);
      } else {
        if (!(await host.signUp(email, password, displayName))) window.location.hash = "#/";
        setBusy(false);
      }
    } catch (err) {
      finish(err);
    }
  }

  async function submit(e: Event) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setDeleted(false);
    const started = performance.now();
    if (!testSignUp(email) && (await signIn())) {
      console.info(`Sign in done (${Math.round(performance.now() - started)} ms)`);
      return;
    }
    if (again === "") {
      setError(NO_MATCH);
      setBusy(false);
      return;
    }
    await signUp();
    console.info(`Sign up done (${Math.round(performance.now() - started)} ms)`);
  }

  // A new, empty site, at its old subdomain if still free, paused until Resume subscription
  // pays for it (R69c, R69b). The browser goes there, signed in.
  async function startAgain() {
    setBusy(true);
    try {
      const link = await restartSite(email, password);
      console.info("Site started again: going there");
      navigation.goTo(link);
    } catch (err) {
      console.error("Could not start the site again", err);
      setError(err instanceof ServerRefusal ? err.message : FAILED);
      setDeleted(false);
      setBusy(false);
    }
  }

  const who = host.session?.signed_in
    ? host.session.display_name || host.session.email
    : participant.session?.signed_in
      ? participant.session.display_name || participant.session.email
      : null;
  if (who) {
    return (
      <div className="host-page host-account">
        <h1>Sign in</h1>
        <p>
          You are signed in as {who}.{" "}
          <a href={host.session?.signed_in ? "#/" : "#/chat"}>Go on</a>
        </p>
      </div>
    );
  }
  return (
    <div className="host-page host-account">
      <h1>Sign in</h1>
      <p className="lead">
        Sign in with your email and password. New here? Type the password twice to make an
        account.
      </p>
      <form onSubmit={(e) => void submit(e)} noValidate>
        <label>
          Email
          <input
            type="email"
            autoComplete="email"
            value={email}
            onInput={(e) => {
              // A suggestion still on its way is for the email before this one.
              asked.current++;
              suggestedFor.current = "";
              setEmail(e.currentTarget.value);
            }}
            onBlur={() => void suggest()}
          />
        </label>
        <label>
          Display name
          <input
            type="text"
            autoComplete="nickname"
            maxLength={DISPLAY_NAME_MAX}
            value={displayName}
            onInput={(e) => {
              named.current = true;
              setDisplayName(e.currentTarget.value);
            }}
          />
          <span className="muted">
            For a new account: what others see you called. Your email is never shown to them.
          </span>
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onInput={(e) => setPassword(e.currentTarget.value)}
          />
        </label>
        <label>
          Password again (new accounts only, at least {MIN_PASSWORD} characters)
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
        {deleted && (
          <div className="switch">
            <button type="button" disabled={busy} onClick={() => void startAgain()}>
              Start my site again
            </button>
            <p className="muted">
              A new, empty site, at your old address if it is still free. It starts once you
              resume your subscription there.
            </p>
          </div>
        )}
        <button type="submit" disabled={busy || email.trim() === "" || password === ""}>
          Sign in
        </button>
      </form>
      {/* Forgot password is for hosts' accounts, which a host's site never mentions (R270). */}
      {!participantOnly && (
        <p className="muted">
          <a href="#/host/forgot">Forgot your password?</a>
        </p>
      )}
    </div>
  );
}

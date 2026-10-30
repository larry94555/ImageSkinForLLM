// The shared layout and the page for the current URL hash.

import { useEffect, useRef, useState } from "preact/hooks";

import { AdminEndedNotice, AdminLink, AdminPage, AdminProvider, useAdminActivity } from "./admin";
import { getConsent, getStartNow, type View } from "./api";
import { AvatarVoicePage } from "./avatar-voice";
import { ownAfterConsent } from "./change-setup";
import { ContentPage } from "./content";
import { GuidePage } from "./guide";
import { HomePage, setupLink } from "./home";
import { HostAccountPage, HostLinks, HostOnlyPage, HostProvider, useHost } from "./host";
import { ChatPage, ConsentPage, NotFoundPage, SetupPage } from "./pages";
import { StartNowPage } from "./start-now";
import {
  adminTarget,
  OWN_CONSENT,
  type Page,
  pageFor,
  resolve,
  setupTarget,
  useHash,
  wikiTarget,
} from "./router";
import {
  SettingsLink,
  SettingsPage,
  SettingsProvider,
  useSettings,
  useSettingsLoaded,
} from "./settings";
import { SettingsAccessProvider, useSettingsShown } from "./settings-access";
import { WikiDetailPage, WikiPage } from "./wiki";
import { WizardPage } from "./wizard";

// The top bar's pages for each view: the participant view has only the chat (Larry's test of
// PR #233). The host reaches the wiki from Manage Content, as it is built from the PDFs there
// (Larry's review of PR #123).
const NAV: { page: Page; href: string; label: string; views: View[] }[] = [
  { page: "home", href: "#/", label: "Home", views: ["host"] },
  { page: "setup", href: "#/setup", label: "Setup", views: ["host"] },
  { page: "chat", href: "#/chat", label: "Chat", views: ["host", "participant"] },
  { page: "content", href: "#/content", label: "Manage Content", views: ["host"] },
];

// The top bar link to highlight: the recording guide and Start now are part of setup, and the
// wiki's pages are part of Manage Content for the host.
function current(page: Page | undefined, view: View): Page | undefined {
  if (page === "guide" || page === "start-now" || page === "avatar-voice" || page === "wizard") {
    return "setup";
  }
  if (page === "wiki" || page === "wiki-page") return view === "host" ? "content" : undefined;
  return page;
}

export function App() {
  return (
    <SettingsProvider>
      <AdminProvider>
        <HostProvider>
          <SettingsAccessProvider>
            <Shell />
          </SettingsAccessProvider>
        </HostProvider>
      </AdminProvider>
    </SettingsProvider>
  );
}

function Shell() {
  const hash = useHash();
  const view = useSettings().view;
  const participant = view === "participant";
  const settingsLoaded = useSettingsLoaded();
  // Until the settings are read, the top bar has no links, so a participant never sees a host's
  // (review on PR #77).
  const host = settingsLoaded && !participant;
  // null until the server has answered.
  const [consented, setConsented] = useState<boolean | null>(null);

  useEffect(() => {
    getConsent()
      .then((c) => setConsented(c.agreed))
      .catch((e: unknown) => {
        console.error("Could not load consent", e);
        setConsented(false);
      });
  }, []);

  // Whether a ready-made avatar is in use, so the top bar's Setup goes where the home page's does.
  // Read again on each page change, as Start now can choose an avatar or drop it.
  const defaultPerson = useDefaultPerson(hash, host);

  // Anyone not signed in as a host has the participant view (R190), and a host page says so.
  const hostSession = useHost().session;
  const visitor = hostSession?.signed_in !== true;
  const settingsShown = useSettingsShown();
  const route =
    consented === null || !settingsLoaded || hostSession === null
      ? null
      : resolve(hash, consented, participant, visitor);
  useEffect(() => {
    if (route?.redirect && route.redirect !== window.location.hash) {
      window.location.replace(route.redirect);
    }
  }, [route?.redirect]);

  // Whether the visit is still on the page it started on, the home page (R30): a return visit
  // then goes straight to the chat.
  const landing = useRef(pageFor(window.location.hash) === "home");
  if (route && route.page !== "home") landing.current = false;

  // A click or key press in the admin view or on the Settings page keeps the administrator
  // signed in (R150).
  useAdminActivity(route?.page === "admin" || route?.page === "settings");

  const header = useHeaderHeight();
  // The page the Settings page was opened from, for Return to the app (R27). Opened by its
  // address, it returns to the first page of the view.
  const back = useRef<string | null>(null);
  if (route && route.page !== "settings" && !route.redirect) back.current = hash || "#/";

  let content = <p>Loading…</p>;
  if (route) {
    content = {
      home: <HomePage consented={consented === true} landing={landing.current} />,
      consent: (
        <ConsentPage
          onConfirmed={() => {
            setConsented(true);
            if (hash !== OWN_CONSENT) {
              window.location.hash = "#/setup";
              return;
            }
            ownAfterConsent().catch((e: unknown) => {
              console.error("Could not switch to your own photo and voice", e);
              window.location.hash = "#/setup";
            });
          }}
        />
      ),
      setup: <SetupPage change={setupTarget(hash)} />,
      wizard: <WizardPage consented={consented === true} onConsented={() => setConsented(true)} />,
      "start-now": <StartNowPage />,
      "avatar-voice": <AvatarVoicePage />,
      chat: <ChatPage />,
      content: <ContentPage />,
      guide: <GuidePage />,
      wiki: <WikiPage pdf={wikiTarget(hash).pdf} />,
      "wiki-page": <WikiDetailPage entry={wikiTarget(hash).entry ?? ""} />,
      // Only for a host or a listed laptop (R191): anyone else gets the page any unknown
      // address shows.
      settings: !settingsShown ? (
        settingsShown === null ? (
          <p>Loading…</p>
        ) : (
          <NotFoundPage />
        )
      ) : (
        <SettingsPage
          back={back.current ?? (participant ? "#/chat" : "#/")}
          // Delete my data removed the consent (R31): setup starts again there.
          onDataDeleted={() => setConsented(false)}
        />
      ),
      admin: <AdminPage section={adminTarget(hash)} />,
      "host-sign-up": <HostAccountPage kind="up" />,
      "host-sign-in": <HostAccountPage kind="in" />,
      "host-only": <HostOnlyPage />,
      "not-found": <NotFoundPage />,
    }[route.page];
  }

  return (
    <>
      <header ref={header}>
        <a className="brand" href={host ? "#/" : "#/chat"}>
          <Mark />
          ImageSkinForLLM
        </a>
        <nav>
          {NAV.filter((item) => settingsLoaded && item.views.includes(view)).map((item) => (
            <a
              key={item.page}
              href={item.page === "setup" ? setupLink(consented === true, defaultPerson) : item.href}
              className={current(route?.page, view) === item.page ? "current" : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
        <span className="header-end">
          <HostLinks page={route?.page} />
          <AdminLink current={route?.page === "admin"} />
          {settingsLoaded && settingsShown && (
            <SettingsLink current={route?.page === "settings"} />
          )}
        </span>
      </header>
      <main>
        <AdminEndedNotice />
        {content}
      </main>
      <footer>Photos and recordings stay on the computer that runs this app.</footer>
    </>
  );
}

// Whether a ready-made avatar (R24c) is in use, read from the server whenever the page changes.
// Only the host's top bar has Setup, so a participant's makes no read.
export function useDefaultPerson(hash: string, host: boolean): boolean {
  const [chosen, setChosen] = useState(false);
  useEffect(() => {
    if (!host) return;
    let active = true;
    const started = performance.now();
    getStartNow()
      .then((s) => {
        if (!active) return;
        const yes = Boolean(s.chosen);
        console.info(
          `Top bar Setup link: ${yes ? "Start now (a ready-made avatar is in use)" : "setup"} (read in ${Math.round(performance.now() - started)} ms)`,
        );
        setChosen(yes);
      })
      .catch((e: unknown) => console.error("Could not read the default person for the top bar", e));
    return () => {
      active = false;
    };
  }, [hash, host]);
  return chosen;
}

// The top bar's height as --header-h on the page (review on PR #83), so what sticks under it
// (the person on the chat page) sticks below it instead of behind it. It is measured, not fixed,
// because on a phone the tabs wrap to a second row.
export function useHeaderHeight() {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const header = ref.current;
    if (!header) return;
    const root = document.documentElement;
    const measure = () => root.style.setProperty("--header-h", `${header.offsetHeight}px`);
    measure();
    if (typeof ResizeObserver === "undefined") {
      console.warn("No ResizeObserver; the top bar's height is measured once");
      return;
    }
    const observer = new ResizeObserver(measure);
    observer.observe(header);
    return () => observer.disconnect();
  }, []);
  return ref;
}

// The app's mark (R41e2): a speech bubble with eyes, for a person who talks.
function Mark() {
  return (
    <svg className="mark" viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="mark-fill" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#6366f1" />
          <stop offset="1" stop-color="#a855f7" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#mark-fill)" />
      <path
        d="M8.5 11.5A3.5 3.5 0 0 1 12 8h8a3.5 3.5 0 0 1 3.5 3.5v5A3.5 3.5 0 0 1 20 20h-5l-4.5 3.8V19.6a3.5 3.5 0 0 1-2-3.1z"
        fill="#fff"
      />
      <circle cx="13.2" cy="14" r="1.4" fill="#5b4ee6" />
      <circle cx="18.8" cy="14" r="1.4" fill="#5b4ee6" />
    </svg>
  );
}

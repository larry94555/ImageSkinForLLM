// The shared layout and the page for the current URL hash.

import { useEffect, useState } from "preact/hooks";

import { getConsent } from "./api";
import { ContentPage } from "./content";
import { GuidePage } from "./guide";
import { HomePage } from "./home";
import { ChatPage, ConsentPage, NotFoundPage, SetupPage } from "./pages";
import { type Page, resolve, useHash, wikiTarget } from "./router";
import { SettingsMenu, SettingsProvider, useSettings, useSettingsLoaded } from "./settings";
import { WikiDetailPage, WikiPage } from "./wiki";

// The top bar's pages; the student view (R41b) has only the chat and the wiki.
const NAV: { page: Page; href: string; label: string; student?: boolean }[] = [
  { page: "home", href: "#/", label: "Home" },
  { page: "setup", href: "#/setup", label: "Setup" },
  { page: "chat", href: "#/chat", label: "Chat", student: true },
  { page: "wiki", href: "#/wiki", label: "Wiki", student: true },
  { page: "content", href: "#/content", label: "Manage Content" },
];

// The top bar link to highlight: the recording guide is part of setup, and a detail page of the
// wiki.
function current(page: Page | undefined): Page | undefined {
  if (page === "guide") return "setup";
  return page === "wiki-page" ? "wiki" : page;
}

export function App() {
  return (
    <SettingsProvider>
      <Shell />
    </SettingsProvider>
  );
}

function Shell() {
  const hash = useHash();
  const student = useSettings().view === "student";
  const settingsLoaded = useSettingsLoaded();
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

  const route = consented === null || !settingsLoaded ? null : resolve(hash, consented, student);
  useEffect(() => {
    if (route?.redirect && route.redirect !== window.location.hash) {
      window.location.replace(route.redirect);
    }
  }, [route?.redirect]);

  let content = <p>Loading…</p>;
  if (route) {
    content = {
      home: <HomePage consented={consented === true} />,
      consent: (
        <ConsentPage
          onConfirmed={() => {
            setConsented(true);
            window.location.hash = "#/setup";
          }}
        />
      ),
      setup: <SetupPage />,
      chat: <ChatPage />,
      content: <ContentPage />,
      guide: <GuidePage />,
      wiki: <WikiPage pdf={wikiTarget(hash).pdf} />,
      "wiki-page": <WikiDetailPage entry={wikiTarget(hash).entry ?? ""} />,
      "not-found": <NotFoundPage />,
    }[route.page];
  }

  return (
    <>
      <header>
        <a className="brand" href={student ? "#/chat" : "#/"}>
          ImageSkinForLLM
        </a>
        <nav>
          {NAV.filter((item) => !student || item.student).map((item) => (
            <a
              key={item.page}
              href={item.href}
              className={current(route?.page) === item.page ? "current" : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
        <SettingsMenu />
      </header>
      <main>{content}</main>
      <footer>Photos and recordings stay on the computer that runs this app.</footer>
    </>
  );
}

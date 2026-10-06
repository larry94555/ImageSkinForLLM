// The shared layout and the page for the current URL hash.

import { useEffect, useState } from "react";

import { getConsent } from "./api";
import { ConsentPage } from "./pages/ConsentPage";
import { HomePage } from "./pages/HomePage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { SetupPage } from "./pages/SetupPage";
import { type Page, resolve, useHash } from "./router";

const NAV: { page: Page; href: string; label: string }[] = [
  { page: "home", href: "#/", label: "Home" },
  { page: "setup", href: "#/setup", label: "Setup" },
];

export function App() {
  const hash = useHash();
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

  const route = consented === null ? null : resolve(hash, consented);
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
      "not-found": <NotFoundPage />,
    }[route.page];
  }

  return (
    <>
      <header>
        <a className="brand" href="#/">
          ImageSkinForLLM
        </a>
        <nav>
          {NAV.map((item) => (
            <a
              key={item.page}
              href={item.href}
              className={route?.page === item.page ? "current" : undefined}
            >
              {item.label}
            </a>
          ))}
        </nav>
      </header>
      <main>{content}</main>
      <footer>Photos and recordings stay on the computer that runs this app.</footer>
    </>
  );
}

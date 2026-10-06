// Page routing from the URL hash (#/consent). Pure, so it can be tested without a browser.

import { useEffect, useState } from "react";

export type Page = "home" | "consent" | "setup" | "not-found";

const PAGES: Record<string, Page> = {
  "/": "home",
  "/consent": "consent",
  "/setup": "setup",
};

export interface Route {
  page: Page;
  // Set when the page asked for can't be shown yet: go here instead.
  redirect?: string;
}

export function pageFor(hash: string): Page {
  const path = hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
  return PAGES[path] ?? "not-found";
}

// Setup is blocked until the user confirms consent (feature item 22).
export function resolve(hash: string, consented: boolean): Route {
  const page = pageFor(hash);
  if (page === "setup" && !consented) {
    return { page: "consent", redirect: "#/consent" };
  }
  return { page };
}

// The current URL hash, updated when it changes.
export function useHash(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const update = () => setHash(window.location.hash);
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return hash;
}

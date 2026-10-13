// Page routing from the URL hash (#/consent). Pure, so it can be tested without a browser.

import { useEffect, useState } from "preact/hooks";

export type Page =
  | "home"
  | "consent"
  | "setup"
  | "chat"
  | "content"
  | "guide"
  | "wiki"
  | "wiki-page"
  | "not-found";

const PAGES: Record<string, Page> = {
  "/": "home",
  "/consent": "consent",
  "/setup": "setup",
  "/chat": "chat",
  "/content": "content",
  "/guide": "guide",
  "/wiki": "wiki",
};

// The wiki's addresses (roadmap R37b): #/wiki/<PDF id> is one PDF's table of contents, and
// #/wiki/page/<entry id> a detail page.
const WIKI_PDF = /^\/wiki\/([^/]+)$/;
const WIKI_PAGE = /^\/wiki\/page\/([^/]+)$/;

function pathOf(hash: string): string {
  return hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
}

// Which PDF or detail page a wiki address names. A part that isn't valid percent-encoding (a
// hand-edited bookmark, say) names none, so the address is not found.
export function wikiTarget(hash: string): { pdf?: string; entry?: string } {
  const path = pathOf(hash);
  const entry = decoded(WIKI_PAGE.exec(path)?.[1]);
  if (entry) return { entry };
  const pdf = decoded(WIKI_PDF.exec(path)?.[1]);
  return pdf ? { pdf } : {};
}

function decoded(part: string | undefined): string | undefined {
  if (part === undefined) return undefined;
  try {
    return decodeURIComponent(part);
  } catch {
    return undefined;
  }
}

export interface Route {
  page: Page;
  // Set when the page asked for can't be shown yet: go here instead.
  redirect?: string;
}

export function pageFor(hash: string): Page {
  const path = pathOf(hash);
  const wiki = wikiTarget(hash);
  if (wiki.entry) return "wiki-page";
  if (wiki.pdf) return "wiki";
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

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
  | "settings"
  | "not-found";

const PAGES: Record<string, Page> = {
  "/": "home",
  "/consent": "consent",
  "/setup": "setup",
  "/chat": "chat",
  "/content": "content",
  "/guide": "guide",
  "/wiki": "wiki",
  "/settings": "settings", // in both views, so a student view can be switched back (R27)
};

// The wiki's addresses (roadmap R37b): #/wiki/<PDF id> is one PDF's table of contents, and
// #/wiki/page/<entry id> a detail page.
const WIKI_PDF = /^\/wiki\/([^/]+)$/;
const WIKI_PAGE = /^\/wiki\/page\/([^/]+)$/;
// Setup opened at what to change from Settings (roadmap R28): #/setup/photos, #/setup/sounds or
// #/setup/accent.
const SETUP_PART = /^\/setup\/(photos|sounds|accent)$/;

export type SetupPart = "photos" | "sounds" | "accent";

// Which part of setup an address opens at, if any.
export function setupTarget(hash: string): SetupPart | undefined {
  return SETUP_PART.exec(pathOf(hash))?.[1] as SetupPart | undefined;
}

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
  if (setupTarget(hash)) return "setup";
  return PAGES[path] ?? "not-found";
}

// The pages the student view hides (R41b): it has only the chat and the wiki.
const TEACHER_PAGES: Page[] = ["home", "consent", "setup", "guide", "content"];

// Setup is blocked until the user confirms consent (feature item 22). In the student view a
// teacher's page, opened by its address, shows the chat instead.
export function resolve(hash: string, consented: boolean, student = false): Route {
  const page = pageFor(hash);
  if (student && TEACHER_PAGES.includes(page)) {
    return { page: "chat", redirect: "#/chat" };
  }
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

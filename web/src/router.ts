// Page routing from the URL hash (#/consent). Pure, so it can be tested without a browser.

import { useEffect, useState } from "preact/hooks";

export type Page =
  | "home"
  | "consent"
  | "setup"
  | "start-now"
  | "avatar-voice"
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
  "/consent/own": "consent", // choosing your own image and voice over a ready-made avatar
  "/setup": "setup",
  "/start-now": "start-now",
  "/avatar-voice": "avatar-voice", // R24d: a ready-made avatar in the user's own voice
  "/chat": "chat",
  "/content": "content",
  "/guide": "guide",
  "/wiki": "wiki",
  "/settings": "settings", // in both views, so a participant view can be switched back (R27)
};

// The wiki's addresses (roadmap R37b): #/wiki/<PDF id> is one PDF's table of contents, and
// #/wiki/page/<entry id> a detail page.
const WIKI_PDF = /^\/wiki\/([^/]+)$/;
const WIKI_PAGE = /^\/wiki\/page\/([^/]+)$/;
// Setup opened at what to change from Settings (roadmap R28): #/setup/photos, #/setup/sounds or
// #/setup/accent.
const SETUP_PART = /^\/setup\/(photos|sounds|accent)$/;

// Choosing your own image and voice over a ready-made avatar shows Before you start again, even
// if it was confirmed before (Larry's test of PR #131).
export const OWN_CONSENT = "#/consent/own";

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

// The pages the participant view hides (R41b): it has only the chat and the wiki.
const HOST_PAGES: Page[] = [
  "home",
  "consent",
  "setup",
  "start-now",
  "avatar-voice",
  "guide",
  "content",
];

// Setup is blocked until the user confirms consent (feature item 22). In the participant view a
// host's page, opened by its address, shows the chat instead.
export function resolve(hash: string, consented: boolean, participant = false): Route {
  const page = pageFor(hash);
  if (participant && HOST_PAGES.includes(page)) {
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

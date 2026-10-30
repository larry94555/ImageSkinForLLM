// Page routing from the URL hash (#/consent). Pure, so it can be tested without a browser.

import { useEffect, useState } from "preact/hooks";

export type Page =
  | "home"
  | "consent"
  | "setup"
  | "wizard"
  | "start-now"
  | "avatar-voice"
  | "chat"
  | "content"
  | "guide"
  | "wiki"
  | "wiki-page"
  | "settings"
  | "admin"
  | "host-sign-up"
  | "host-sign-in"
  | "host-only"
  | "not-found";

const PAGES: Record<string, Page> = {
  "/": "home",
  "/consent": "consent",
  "/consent/own": "consent", // choosing your own image and voice over a ready-made avatar
  "/setup": "setup",
  "/setup/wizard": "wizard", // R131: setup one step at a time, with its own consent step
  "/start-now": "start-now",
  "/avatar-voice": "avatar-voice", // R24d: a ready-made avatar in the user's own voice
  "/chat": "chat",
  "/content": "content",
  "/guide": "guide",
  "/wiki": "wiki",
  "/settings": "settings", // in both views, so a participant view can be switched back (R27)
  "/admin": "admin", // the admin view (R150), apart from the host and participant views
  "/admin/settings": "admin", // its second page, the admin settings (R155)
  // Host sign up and sign in (R189), in both views, as anyone not signed in may become a host.
  "/host/sign-up": "host-sign-up",
  "/host/sign-in": "host-sign-in",
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

// Which page of the admin view an address opens (R155): the resources, or the admin settings.
export function adminTarget(hash: string): "resources" | "settings" {
  return pathOf(hash) === "/admin/settings" ? "settings" : "resources";
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

// The pages the participant view hides (R41b). The wiki has no top bar link there, but opened by
// its address it is read-only.
const HOST_PAGES: Page[] = [
  "home",
  "consent",
  "setup",
  "wizard",
  "start-now",
  "avatar-voice",
  "guide",
  "content",
];

// Setup is blocked until the user confirms consent (feature item 22). In the participant view a
// host's page, opened by its address, shows the chat instead; to anyone not signed in as a host
// (`visitor`, R190) it says it is for the host, with a link to sign in, except the home page.
export function resolve(
  hash: string,
  consented: boolean,
  participant = false,
  visitor = false,
): Route {
  const page = pageFor(hash);
  if (participant && HOST_PAGES.includes(page)) {
    if (visitor && page !== "home") return { page: "host-only" };
    return { page: "chat", redirect: "#/chat" };
  }
  if (page === "setup" && !consented) {
    return { page: "consent", redirect: "#/consent" };
  }
  return { page };
}

// A page can hold on to the address while the user confirms leaving it (leave-guard.tsx, after
// Codex's review of PR #131): it returns true to stay, and the page shown doesn't change.
type Blocker = (from: string, to: string) => boolean;
let blocker: Blocker | null = null;
export function blockLeaving(fn: Blocker | null) {
  blocker = fn;
}

// The current URL hash, updated when it changes, unless a page holds on to it.
export function useHash(): string {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const update = (e: HashChangeEvent) => {
      if (blocker?.(new URL(e.oldURL).hash, new URL(e.newURL).hash)) return;
      setHash(window.location.hash);
    };
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return hash;
}

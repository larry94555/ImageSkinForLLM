import { describe, expect, test } from "vitest";

import { pageFor, resolve, setupTarget, wikiTarget } from "./router";

describe("router", () => {
  test("hashes map to pages", () => {
    expect(pageFor("")).toBe("home");
    expect(pageFor("#/")).toBe("home");
    expect(pageFor("#/consent")).toBe("consent");
    expect(pageFor("#/consent/own")).toBe("consent"); // your own over a ready-made avatar
    expect(pageFor("#/setup/")).toBe("setup");
    expect(pageFor("#/content")).toBe("content");
    expect(pageFor("#/guide")).toBe("guide");
    expect(pageFor("#/nowhere")).toBe("not-found");
  });

  test("wiki addresses name a PDF or a detail page", () => {
    expect(pageFor("#/wiki")).toBe("wiki");
    expect(pageFor("#/wiki/a1")).toBe("wiki");
    expect(pageFor("#/wiki/page/a1-rain/")).toBe("wiki-page");
    expect(pageFor("#/wiki/a1/more")).toBe("not-found");
    expect(wikiTarget("#/wiki")).toEqual({});
    expect(wikiTarget("#/wiki/a1")).toEqual({ pdf: "a1" });
    expect(wikiTarget("#/wiki/page/a1-rain")).toEqual({ entry: "a1-rain" });
    expect(wikiTarget("#/wiki/page/a1%20b")).toEqual({ entry: "a1 b" });
  });

  test("a wiki address that isn't valid percent-encoding is not found", () => {
    for (const hash of ["#/wiki/%", "#/wiki/page/%E0%A4%A"]) {
      expect(pageFor(hash)).toBe("not-found");
      expect(wikiTarget(hash)).toEqual({});
    }
  });

  test("setup is blocked until consent is confirmed", () => {
    expect(resolve("#/setup", false)).toEqual({ page: "consent", redirect: "#/consent" });
    expect(resolve("#/setup", true)).toEqual({ page: "setup" });
  });

  test("other pages are open without consent", () => {
    expect(resolve("#/", false)).toEqual({ page: "home" });
    expect(resolve("#/consent", false)).toEqual({ page: "consent" });
    expect(resolve("#/start-now", false)).toEqual({ page: "start-now" }); // no consent (R24c)
  });
});

test("the participant view sends a host's page to the chat", () => {
  for (const hash of ["#/", "#/consent", "#/setup", "#/start-now", "#/guide", "#/content"]) {
    expect(resolve(hash, true, true)).toEqual({ page: "chat", redirect: "#/chat" });
  }
  expect(resolve("#/wiki", false, true)).toEqual({ page: "wiki" });
  expect(resolve("#/wiki/page/a1-x", true, true)).toEqual({ page: "wiki-page" });
  expect(resolve("#/chat", true, true)).toEqual({ page: "chat" });
  expect(resolve("#/content", true)).toEqual({ page: "content" }); // the host view
});

test("the Settings page is in both views (R27)", () => {
  expect(pageFor("#/settings")).toBe("settings");
  expect(resolve("#/settings", false)).toEqual({ page: "settings" });
  expect(resolve("#/settings", true, true)).toEqual({ page: "settings" }); // to switch back
  // The admin view is apart from both views (R150), so neither sends it elsewhere.
  expect(resolve("#/admin", false)).toEqual({ page: "admin" });
  expect(resolve("#/admin", true, true)).toEqual({ page: "admin" });
});

test("setup opens at what to change from Settings (R28)", () => {
  expect(pageFor("#/setup/photos")).toBe("setup");
  expect(setupTarget("#/setup/photos")).toBe("photos");
  expect(setupTarget("#/setup/sounds/")).toBe("sounds");
  expect(setupTarget("#/setup/accent")).toBe("accent");
  expect(setupTarget("#/setup")).toBeUndefined();
  expect(pageFor("#/setup/other")).toBe("not-found");
  expect(resolve("#/setup/accent", false)).toEqual({ page: "consent", redirect: "#/consent" });
  expect(resolve("#/setup/accent", true, true)).toEqual({ page: "chat", redirect: "#/chat" });
});

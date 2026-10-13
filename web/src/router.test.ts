import { describe, expect, test } from "vitest";

import { pageFor, resolve, wikiTarget } from "./router";

describe("router", () => {
  test("hashes map to pages", () => {
    expect(pageFor("")).toBe("home");
    expect(pageFor("#/")).toBe("home");
    expect(pageFor("#/consent")).toBe("consent");
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

  test("setup is blocked until consent is confirmed", () => {
    expect(resolve("#/setup", false)).toEqual({ page: "consent", redirect: "#/consent" });
    expect(resolve("#/setup", true)).toEqual({ page: "setup" });
  });

  test("other pages are open without consent", () => {
    expect(resolve("#/", false)).toEqual({ page: "home" });
    expect(resolve("#/consent", false)).toEqual({ page: "consent" });
  });
});

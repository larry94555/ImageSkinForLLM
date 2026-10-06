import { describe, expect, test } from "vitest";

import { pageFor, resolve } from "./router";

describe("router", () => {
  test("hashes map to pages", () => {
    expect(pageFor("")).toBe("home");
    expect(pageFor("#/")).toBe("home");
    expect(pageFor("#/consent")).toBe("consent");
    expect(pageFor("#/setup/")).toBe("setup");
    expect(pageFor("#/nowhere")).toBe("not-found");
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

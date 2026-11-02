import { afterEach, describe, expect, it, vi } from "vitest";

import { sendFetchesUnderSitePath, sitePath, under } from "./site-path";

const CODE = "k7q2x9mf3a8w";

afterEach(() => window.history.replaceState(null, "", "/"));

describe("a trial site's path (R61a)", () => {
  it("is found at the start of the page's path only", () => {
    expect(sitePath(`/t/${CODE}/`)).toBe(`/t/${CODE}`);
    expect(sitePath(`/t/${CODE}`)).toBe(`/t/${CODE}`);
    expect(sitePath("/")).toBe("");
    expect(sitePath("/t/short/")).toBe("");
    expect(sitePath(`/x/t/${CODE}/`)).toBe("");
    expect(sitePath(`/t/${CODE}x/`)).toBe("");
  });

  it("puts the app's addresses under it, once", () => {
    const path = `/t/${CODE}`;
    expect(under("/api/chat/idle", path)).toBe(`${path}/api/chat/idle`);
    expect(under(`${path}/api/chat/clips/1/0`, path)).toBe(
      `${path}/api/chat/clips/1/0`,
    );
    expect(under("https://example.com/x", path)).toBe("https://example.com/x");
    expect(under("//cdn.example.com/x", path)).toBe("//cdn.example.com/x");
    expect(under("/api/chat/idle", "")).toBe("/api/chat/idle");
  });

  it("sends every fetch of the app under it on a trial site's page", async () => {
    window.history.replaceState(null, "", `/t/${CODE}/#/chat`);
    const fetched = vi.fn(async () => new Response("{}"));
    const target = { fetch: fetched as unknown as typeof fetch };
    sendFetchesUnderSitePath(target);
    await target.fetch("/api/host/session");
    await target.fetch(`/t/${CODE}/api/chat/clips/1/0`);
    const url = new URL("https://example.com/a");
    await target.fetch(url);
    expect(fetched.mock.calls.map((c) => (c as unknown[])[0])).toEqual([
      `/t/${CODE}/api/host/session`,
      `/t/${CODE}/api/chat/clips/1/0`,
      url,
    ]);
  });

  it("leaves fetch as it is anywhere else", () => {
    const original = vi.fn() as unknown as typeof fetch;
    const target = { fetch: original };
    sendFetchesUnderSitePath(target);
    expect(target.fetch).toBe(original);
  });
});

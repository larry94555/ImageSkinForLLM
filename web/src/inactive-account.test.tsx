// The administrator's test account once the administrator is signed out (roadmap R268): the first
// "This account is no longer active." signs the host out in this browser and shows only that.

import { cleanup, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import {
  INACTIVE_HASH,
  inactiveAccount,
  inactiveNavigation,
  NO_LONGER_ACTIVE,
  watchForInactiveAccount,
} from "./inactive-account";

vi.unmock("./api");

const REFUSED = () => Response.json({ detail: NO_LONGER_ACTIVE }, { status: 403 });

function watched(answer: (url: string) => Response) {
  const asked: { url: string; body?: unknown }[] = [];
  const target = {
    fetch: vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      asked.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      return answer(url);
    }) as unknown as typeof fetch,
  };
  watchForInactiveAccount(target);
  return { target, asked };
}

let shown: ReturnType<typeof vi.fn<() => void>>;
beforeEach(() => {
  shown = vi.fn<() => void>();
  vi.spyOn(inactiveNavigation, "show").mockImplementation(shown);
  inactiveAccount.shown = false;
  window.location.hash = "#/setup";
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.location.hash = "";
  inactiveAccount.shown = false;
});

test("the first refusal signs out, logs the page and shows the words", async () => {
  vi.spyOn(console, "warn").mockImplementation(() => {});
  const { target, asked } = watched((url) =>
    url.startsWith("/api/host/sign-out") || url.startsWith("/api/host/inactive-shown")
      ? new Response(null, { status: 204 })
      : REFUSED(),
  );
  const first = await target.fetch("/api/host/me");
  // The caller still gets the server's answer.
  expect(first.status).toBe(403);
  expect(await first.json()).toEqual({ detail: NO_LONGER_ACTIVE });
  expect(asked.map((a) => a.url)).toEqual([
    "/api/host/me",
    "/api/host/sign-out",
    "/api/host/inactive-shown",
  ]);
  expect(asked[2].body).toEqual({ page: "/setup" });
  expect(shown).toHaveBeenCalledTimes(1);
  // Later refusals, from calls already on their way, change nothing more.
  await target.fetch("/api/settings");
  expect(asked).toHaveLength(4);
  expect(shown).toHaveBeenCalledTimes(1);
});

test("other answers pass through untouched", async () => {
  const { target, asked } = watched((url) =>
    url === "/api/other"
      ? Response.json({ detail: "Changes to this site are turned off." }, { status: 403 })
      : url === "/api/text"
        ? new Response("not json", { status: 403 })
        : Response.json({ ok: true }),
  );
  expect((await target.fetch("/api/host/session")).status).toBe(200);
  expect((await target.fetch("/api/other")).status).toBe(403);
  expect((await target.fetch("/api/text")).status).toBe(403);
  expect(asked).toHaveLength(3);
  expect(shown).not.toHaveBeenCalled();
});

test("a sign-out that fails is logged, and the words still shown", async () => {
  const errors = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
  const { target } = watched((url) =>
    url === "/api/host/sign-out"
      ? new Response("", { status: 503 })
      : url === "/api/host/inactive-shown"
        ? (() => {
            throw new TypeError("offline");
          })()
        : REFUSED(),
  );
  await target.fetch("/api/host/session");
  expect(errors).toHaveBeenCalledWith("Host sign-in not forgotten: 503");
  expect(errors).toHaveBeenCalledWith("Host sign-in not forgotten", expect.any(TypeError));
  expect(shown).toHaveBeenCalledTimes(1);
});

test("the page shows only the words: no top bar, links or site", async () => {
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json({ signed_in: false, email: null })),
  );
  window.location.hash = INACTIVE_HASH;
  const { container } = render(<App />);
  expect(await screen.findByText(NO_LONGER_ACTIVE)).toBeTruthy();
  expect(container.querySelector("header")).toBeNull();
  expect(container.querySelector("footer")).toBeNull();
  expect(container.querySelectorAll("a")).toHaveLength(0);
  expect(container.textContent).toBe(NO_LONGER_ACTIVE);
  expect(console.info).toHaveBeenCalledWith("Inactive account shown");
});

test("once shown, the words stay: no page's redirect replaces them", async () => {
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json({ signed_in: false, email: null })),
  );
  inactiveAccount.shown = true;
  // Setup, which would go to the consent page first.
  window.location.hash = "#/setup";
  const { container } = render(<App />);
  expect(await screen.findByText(NO_LONGER_ACTIVE)).toBeTruthy();
  await new Promise((done) => setTimeout(done, 50));
  expect(window.location.hash).toBe("#/setup");
  expect(container.textContent).toBe(NO_LONGER_ACTIVE);
});

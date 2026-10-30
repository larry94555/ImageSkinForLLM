import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

// The real host session and Settings calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

// Whether the browser can make a laptop key, as it can on the hosted site (R164).
const laptopKey = vi.hoisted(() => ({ can: false }));
vi.mock("./laptop-key", async (original) => ({
  ...(await original<typeof import("./laptop-key")>()),
  canProve: () => laptopKey.can,
  laptopId: async () => "LT-AAAA-BBBB-CCCC-DDDD-EEEE",
  prove: async (challenge: string) => ({ public_key: "key", challenge, signature: "signed" }),
}));

// A server as R191 makes it: Settings for a signed-in host, or for the listed laptop.
function server(opts: { host?: boolean; listed?: boolean } = {}) {
  const state = { host: opts.host === true };
  const asked: unknown[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({ view: state.host ? "host" : "participant" });
    if (url === "/api/host/session") {
      return Response.json({ signed_in: state.host, email: state.host ? "host@example.com" : null });
    }
    if (url === "/api/host/page") return new Response(null, { status: 204 });
    if (url === "/api/host/sign-in") {
      state.host = true;
      return Response.json({ signed_in: true, email: "host@example.com" });
    }
    if (url === "/api/admin/session") {
      return Response.json({ signed_in: false, password_set: true, timeout_minutes: 30, ended: null });
    }
    if (url === "/api/admin/challenge") return Response.json({ challenge: "c1" });
    if (url === "/api/admin/laptop") return Response.json({ listed: true });
    if (url === "/api/settings/access") {
      asked.push(body.laptop ?? null);
      if (state.host) return Response.json({ shown: true, as: "host" });
      const laptop = opts.listed === true && body.laptop !== undefined;
      return Response.json({ shown: laptop, as: laptop ? "laptop" : null });
    }
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, asked };
}

function topBar(): HTMLElement {
  return document.querySelector("header") as HTMLElement;
}

beforeEach(() => {
  laptopKey.can = false;
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

test("anyone not a host sees no Settings link, and its address is not found", async () => {
  const { asked } = server();
  window.location.hash = "#/settings";
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Page not found" })).toBeTruthy();
  expect(within(topBar()).queryByRole("link", { name: "Settings" })).toBeNull();
  expect(asked).toEqual([null]); // no key to prove a laptop with
  expect(console.info).toHaveBeenCalledWith("Settings hidden");
});

test("signing in as host shows Settings", async () => {
  server();
  window.location.hash = "#/host/sign-in";
  render(<App />);
  await screen.findByRole("heading", { name: "Host sign in" });
  await vi.waitFor(() => expect(console.info).toHaveBeenCalledWith("Settings hidden"));
  expect(within(topBar()).queryByRole("link", { name: "Settings" })).toBeNull();
  fireEvent.input(screen.getByLabelText(/^Email/), { target: { value: "host@example.com" } });
  fireEvent.input(screen.getByLabelText(/^Password/), { target: { value: "a long secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await within(topBar()).findByRole("link", { name: "Settings" })).toHaveProperty(
    "hash",
    "#/settings",
  );
  expect(console.info).toHaveBeenCalledWith("Settings shown, as host");
});

test("a listed laptop sees Settings with no host signed in, to sign in as administrator", async () => {
  laptopKey.can = true;
  const { asked } = server({ listed: true });
  window.location.hash = "#/settings";
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Settings" })).toBeTruthy();
  expect(within(topBar()).getByRole("link", { name: "Settings" })).toBeTruthy();
  expect(asked).toEqual([{ public_key: "key", challenge: "c1", signature: "signed" }]);
  expect(await screen.findByLabelText(/Administrator password/)).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith("Settings shown, as laptop");
});

test("a laptop that isn't listed sees no Settings, and its ID is in the console", async () => {
  laptopKey.can = true;
  server({ listed: false });
  window.location.hash = "#/chat";
  render(<App />);
  await vi.waitFor(() => expect(console.info).toHaveBeenCalledWith("Settings hidden"));
  expect(within(topBar()).queryByRole("link", { name: "Settings" })).toBeNull();
  expect(console.info).toHaveBeenCalledWith("This laptop's ID: LT-AAAA-BBBB-CCCC-DDDD-EEEE");
});

test("Settings is hidden when the server can't be asked", async () => {
  const { fetchMock } = server({ host: true });
  const answer = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
    url === "/api/settings/access" ? new Response("", { status: 500 }) : answer(url, init),
  );
  window.location.hash = "#/settings";
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Page not found" })).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith(
    "Could not ask whether Settings is shown",
    expect.anything(),
  );
});

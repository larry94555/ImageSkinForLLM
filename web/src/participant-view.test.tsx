import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { resolve } from "./router";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

// A server as R190 makes it: the settings' view is the participant view until a host signs in.
function server(signedIn = false) {
  const state = { host: signedIn, view: "host" };
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") {
      return Response.json({ view: state.host ? state.view : "participant" });
    }
    if (url === "/api/host/session") {
      return Response.json({ signed_in: state.host, email: state.host ? "host@example.com" : null });
    }
    if (url === "/api/host/page") return new Response(null, { status: 204 });
    if (url === "/api/settings/access") {
      return Response.json({ shown: state.host, as: state.host ? "host" : null });
    }
    if (url === "/api/host/sign-in") {
      const body = JSON.parse(String(init?.body)) as { email: string };
      state.host = true;
      return Response.json({ signed_in: true, email: body.email });
    }
    if (url === "/api/host/sign-out") {
      state.host = false;
      return Response.json({ signed_in: false });
    }
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, state };
}

function topBar(): HTMLElement {
  return document.querySelector("header") as HTMLElement;
}

function navLinks(): string[] {
  return within(topBar().querySelector("nav") as HTMLElement)
    .queryAllByRole("link")
    .map((a) => a.textContent ?? "");
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

test("a visitor gets the participant view: only the chat", async () => {
  server();
  window.location.hash = "#/";
  render(<App />);
  await within(topBar()).findByRole("link", { name: "Host sign in" });
  await vi.waitFor(() => expect(navLinks()).toEqual(["Chat"]));
  // The home page is the host's, so a visitor lands on the chat.
  await vi.waitFor(() => expect(window.location.hash).toBe("#/chat"));
});

test("a host page says it is for the host, with a link to sign in", async () => {
  server();
  window.location.hash = "#/content";
  render(<App />);
  expect(await screen.findByRole("heading", { name: "For the host only" })).toBeTruthy();
  const main = document.querySelector("main") as HTMLElement;
  expect(within(main).getByRole("link", { name: "Host sign in" })).toHaveProperty(
    "hash",
    "#/host/sign-in",
  );
  expect(window.location.hash).toBe("#/content");
  await vi.waitFor(() =>
    expect(console.info).toHaveBeenCalledWith("Host page refused: #/content"),
  );
});

test("signing in as host gives the host view, and signing out the participant view", async () => {
  server();
  window.location.hash = "#/host/sign-in";
  render(<App />);
  await screen.findByRole("heading", { name: "Host sign in" });
  fireEvent.input(screen.getByLabelText(/^Email/), { target: { value: "host@example.com" } });
  fireEvent.input(screen.getByLabelText(/^Password/), { target: { value: "a long secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await vi.waitFor(() =>
    expect(navLinks()).toEqual(["Home", "Setup", "Chat", "Manage Content"]),
  );

  fireEvent.click(within(topBar()).getByRole("button", { name: "Sign out" }));
  await vi.waitFor(() => expect(navLinks()).toEqual(["Chat"]));
});

test("only a signed-in host chooses the view on the Settings page", async () => {
  // Anyone else isn't shown Settings at all (R191).
  server();
  window.location.hash = "#/settings";
  render(<App />);
  await screen.findByRole("heading", { name: "Page not found" });
  cleanup();

  server(true);
  render(<App />);
  expect(await screen.findByRole("region", { name: "View" })).toBeTruthy();
});

test("a host who chose the participant view is sent to the chat, not refused", () => {
  expect(resolve("#/content", true, true, false)).toEqual({ page: "chat", redirect: "#/chat" });
  expect(resolve("#/content", true, true, true)).toEqual({ page: "host-only" });
  expect(resolve("#/", true, true, true)).toEqual({ page: "chat", redirect: "#/chat" });
});

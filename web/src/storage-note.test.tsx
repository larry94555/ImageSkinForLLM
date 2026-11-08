// The footer's note that photos and recordings stay on the computer: only a signed-in host sees
// it (Larry, 2026-11-08), with a link to Delete my data in Settings.

import { cleanup, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, onTestFinished, test, vi } from "vitest";

import { App } from "./App";
import { settingsTarget, SETTINGS_DELETE } from "./router";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

const NOTE = "Photos and recordings stay on the computer that runs this app.";

// `host` signs a host in; `view` is the view saved in the settings; `confirmed` is whether the
// host has confirmed their email.
function server({
  host = true,
  view = host ? "host" : "participant",
  confirmed = true,
}: { host?: boolean; view?: string; confirmed?: boolean } = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({ view });
      if (url === "/api/settings/access") return Response.json({ shown: host, as: host ? "host" : null });
      if (url === "/api/host/session") {
        return Response.json({ signed_in: host, email: host ? "dan@example.com" : null, confirmed });
      }
      return new Response("", { status: 404 });
    }),
  );
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

test("a signed-in host sees the note, with a link to delete them in Settings", async () => {
  server();
  window.location.hash = "#/chat";
  render(<App />);
  const link = await screen.findByRole("link", { name: "Delete them in Settings" });
  expect(link.getAttribute("href")).toBe(SETTINGS_DELETE);
  expect(link.closest("footer")?.textContent).toContain(NOTE);
});

test("someone not signed in as a host doesn't see the note", async () => {
  server({ host: false });
  window.location.hash = "#/chat";
  render(<App />);
  await screen.findByRole("link", { name: /Sign in/ });
  expect(screen.queryByText(NOTE, { exact: false })).toBeNull();
  expect(document.querySelector("footer")).toBeNull();
});

test("a host who hasn't confirmed their email doesn't see the note", async () => {
  server({ confirmed: false });
  window.location.hash = "#/chat";
  render(<App />);
  await waitFor(() => expect(console.info).toHaveBeenCalled());
  await screen.findByText(/confirm/i);
  expect(document.querySelector("footer")).toBeNull();
});

test("a host looking at the participant view doesn't see the note", async () => {
  server({ view: "participant" });
  window.location.hash = "#/chat";
  render(<App />);
  await screen.findByRole("link", { name: "Settings" });
  expect(document.querySelector("footer")).toBeNull();
});

test("the link opens Settings at Delete my data", async () => {
  server();
  const scrolled = vi.fn();
  const was = Element.prototype.scrollIntoView;
  Element.prototype.scrollIntoView = scrolled;
  onTestFinished(() => {
    Element.prototype.scrollIntoView = was;
  });
  window.location.hash = SETTINGS_DELETE;
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Settings", level: 1 })).toBeTruthy();
  expect(await screen.findByRole("button", { name: "Delete my data" })).toBeTruthy();
  await waitFor(() => expect(scrolled).toHaveBeenCalled());
  expect(scrolled.mock.contexts[0]).toBe(document.getElementById("settings-delete"));
  expect(console.info).toHaveBeenCalledWith("Settings opened at Delete my data");
});

test("in the participant view, which has no Delete my data, the address only says so in the log", async () => {
  server({ view: "participant" });
  window.location.hash = SETTINGS_DELETE;
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Settings", level: 1 })).toBeTruthy();
  await waitFor(() =>
    expect(console.warn).toHaveBeenCalledWith(
      "Settings opened at Delete my data, but it isn't on the page",
    ),
  );
});

test("only the delete address names the delete section", () => {
  expect(settingsTarget("#/settings/delete")).toBe("delete");
  expect(settingsTarget("#/settings/delete/")).toBe("delete");
  expect(settingsTarget("#/settings")).toBeUndefined();
});

// A host the administrator disabled (roadmap R44c, R44d): every host page says the site is
// read-only, and every control that would change something is turned off. The administrator
// acting as them (R44a) still changes everything.

import { cleanup, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { READ_ONLY_WORDS } from "./host";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

// Site a, signed in as ann, disabled; `acting` makes it the administrator acting as her.
function server(acting = false, disabled = true) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({ view: "host" });
    if (url === "/api/settings/access") return Response.json({ shown: true, as: "host" });
    if (url === "/api/host/session") {
      return Response.json({
        signed_in: true,
        email: "ann@example.com",
        confirmed: true,
        ...(disabled ? { disabled: true } : {}),
        ...(acting ? { acting_as_admin: true } : {}),
      });
    }
    if (url.startsWith("/api/content")) {
      return Response.json({ pdfs: [{ id: "p1", name: "lesson.pdf", size: 10, pages: 2, wiki: null }] });
    }
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
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

function changing(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>("main input, main button, main textarea, main select")];
}

test("Settings says the site is read-only and turns off every change", async () => {
  server();
  window.location.hash = "#/settings";
  render(<App />);
  await screen.findByRole("heading", { name: "Settings" });
  expect((await screen.findByText(READ_ONLY_WORDS)).className).toBe("read-only-bar");
  expect(console.info).toHaveBeenCalledWith("Site read-only: host disabled");
  const boxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
  expect(boxes.length).toBeGreaterThan(3);
  // Inside a disabled fieldset each control is turned off, and can't be clicked.
  for (const box of boxes) expect(box.matches(":disabled")).toBe(true);
  expect((screen.getByRole("link", { name: "Return to the app" }) as HTMLAnchorElement).href).toContain("#/");
});

test("the administrator acting as a disabled host has every control on", async () => {
  server(true);
  window.location.hash = "#/settings";
  render(<App />);
  await screen.findByRole("heading", { name: "Settings" });
  await screen.findByText("ann@example.com", { selector: ".acting-bar strong" });
  expect(screen.queryByText(READ_ONLY_WORDS)).toBeNull();
  for (const box of screen.getAllByRole("checkbox")) expect(box.matches(":disabled")).toBe(false);
});

test("a host who isn't disabled sees no bar", async () => {
  server(false, false);
  window.location.hash = "#/settings";
  render(<App />);
  await screen.findByRole("heading", { name: "Settings" });
  await waitFor(() => expect(screen.getAllByRole("checkbox").length).toBeGreaterThan(3));
  expect(screen.queryByText(READ_ONLY_WORDS)).toBeNull();
  for (const box of screen.getAllByRole("checkbox")) expect(box.matches(":disabled")).toBe(false);
});

test("Manage Content turns off adding and removing, and still links to the wiki", async () => {
  server();
  window.location.hash = "#/content";
  render(<App />);
  await screen.findByText(READ_ONLY_WORDS);
  await waitFor(() => expect(changing().length).toBeGreaterThan(0));
  for (const control of changing()) expect(control.matches(":disabled")).toBe(true);
  expect(document.querySelector("main a[href^='#/wiki']")).not.toBeNull();
});

test("the account page turns off Change email and the password", async () => {
  server();
  window.location.hash = "#/host/account";
  render(<App />);
  await screen.findByRole("heading", { name: "Your account" });
  await screen.findByText(READ_ONLY_WORDS);
  expect(screen.getByRole("button", { name: "Send the link" }).matches(":disabled")).toBe(true);
  expect(screen.getByLabelText(/^New email/).matches(":disabled")).toBe(true);
});

// A free trial (roadmap R66): its host cancels it from Settings, which pauses the site, and a
// visitor of a paused site sees that it is paused, with the host's sign-in still open.

import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

// A trial site; `host` signs its host in, `paused` pauses it, and `cancel` answers the cancel.
function server({
  host = true,
  paused = false,
  trial = true,
  cancel = () => Response.json({ paused: true }),
}: { host?: boolean; paused?: boolean; trial?: boolean; cancel?: () => Response } = {}) {
  const asked: string[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    asked.push(`${init?.method ?? "GET"} ${url}`);
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({ view: host ? "host" : "participant" });
    if (url === "/api/settings/access") return Response.json({ shown: host, as: host ? "host" : null });
    if (url === "/api/host/session") {
      return Response.json({
        signed_in: host,
        email: host ? "dan@example.com" : null,
        confirmed: true,
        ...(trial ? { trial: true } : {}),
        ...(paused ? { paused: true } : {}),
      });
    }
    if (url === "/api/site/cancel") return cancel();
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return asked;
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

test("the host cancels the free trial from Settings, after confirming", async () => {
  const asked = server();
  window.location.hash = "#/settings";
  render(<App />);
  const section = within(await screen.findByRole("region", { name: "Free trial" }));
  // Backing out cancels nothing.
  fireEvent.click(section.getByRole("button", { name: "Cancel free trial" }));
  fireEvent.click(await screen.findByRole("button", { name: "No, keep my trial" }));
  expect(asked).not.toContain("POST /api/site/cancel");
  fireEvent.click(section.getByRole("button", { name: "Cancel free trial" }));
  fireEvent.click(await screen.findByRole("button", { name: "Yes, cancel it" }));
  expect(await section.findByRole("status")).toHaveProperty(
    "textContent",
    expect.stringContaining("Your free trial is cancelled, so your site is paused"),
  );
  expect(asked).toContain("POST /api/site/cancel");
  expect(console.info).toHaveBeenCalledWith("Free trial cancelled: the site is paused");
});

test("a trial that can't be cancelled says why", async () => {
  server({ cancel: () => Response.json({ detail: "This trial was cancelled already." }, { status: 409 }) });
  window.location.hash = "#/settings";
  render(<App />);
  const section = within(await screen.findByRole("region", { name: "Free trial" }));
  fireEvent.click(section.getByRole("button", { name: "Cancel free trial" }));
  fireEvent.click(await screen.findByRole("button", { name: "Yes, cancel it" }));
  expect(await section.findByText("This trial was cancelled already.")).toBeTruthy();
});

test("a paused trial's host sees it is paused, and a site that isn't a trial has no section", async () => {
  server({ paused: true });
  window.location.hash = "#/settings";
  render(<App />);
  const section = within(await screen.findByRole("region", { name: "Free trial" }));
  expect(section.queryByRole("button", { name: "Cancel free trial" })).toBeNull();
  expect(section.getByRole("status").textContent).toContain("You can still sign in.");
  cleanup();
  server({ trial: false });
  render(<App />);
  await screen.findByRole("heading", { name: "Settings" });
  expect(screen.queryByRole("region", { name: "Free trial" })).toBeNull();
});

test("a visitor of a paused site sees that it is paused, and can open the host's sign-in", async () => {
  server({ host: false, paused: true });
  window.location.hash = "#/chat";
  render(<App />);
  expect(await screen.findByRole("heading", { name: "This site is paused" })).toBeTruthy();
  const page = within(document.querySelector("main") as HTMLElement);
  expect(page.getByRole("link", { name: "Host sign in" }).getAttribute("href")).toBe(
    "#/host/sign-in",
  );
  cleanup();
  window.location.hash = "#/host/sign-in";
  render(<App />);
  expect(await screen.findByLabelText(/Email/)).toBeTruthy();
  expect(screen.queryByRole("heading", { name: "This site is paused" })).toBeNull();
});

// The page for a site a participant may not use (roadmap R262): one sentence, the participant's
// own Sign out, and nothing of the host or the site.

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { NOT_ACTIVE, reloading } from "./participant";

vi.unmock("./api");

const PAT = "pat@example.com";
const REFUSED = { detail: NOT_ACTIVE };

function server(allowed: boolean, host = false): string[] {
  const asked: string[] = [];
  let signedIn = true;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      asked.push(`${init?.method ?? "GET"} ${url}`);
      if (url === "/api/participant/session") {
        return Response.json({
          signed_in: signedIn,
          email: signedIn ? PAT : null,
          ...(signedIn && !allowed ? { allowed: false } : {}),
        });
      }
      if (url === "/api/participant/sign-out") {
        signedIn = false;
        return Response.json({ signed_in: false });
      }
      // The site's other calls refuse a participant not allowed here, as the server does.
      if (!allowed && !host) return Response.json(REFUSED, { status: 403 });
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({ view: "participant" });
      if (url === "/api/settings/access")
        return Response.json({ shown: host, as: host ? "host" : null });
      if (url === "/api/host/session") {
        return Response.json({
          signed_in: host,
          email: host ? "ann@example.com" : null,
          host_name: "Dr. Smith",
          confirmed: true,
        });
      }
      if (url === "/api/participant/progress") return Response.json({});
      return new Response("", { status: 404 });
    }),
  );
  return asked;
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

test("a participant not allowed here sees only that the site is not yet active", async () => {
  const asked = server(false);
  window.location.hash = "#/chat";
  render(<App />);
  expect(await screen.findByText(NOT_ACTIVE)).toBeTruthy();
  const page = document.body.textContent ?? "";
  expect(page).not.toMatch(/Dr\. Smith|Hosted by|Chat|Sign up/);
  expect(within(document.querySelector("header")!).getByText(PAT)).toBeTruthy();
  // Their progress isn't asked for: the site would refuse it.
  expect(asked).not.toContain("GET /api/participant/progress");
  // Signing out reads the page again, as an anonymous visitor.
  const reloaded = vi.spyOn(reloading, "reload").mockImplementation(() => {});
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
  });
  await waitFor(() => expect(reloaded).toHaveBeenCalled());
});

test("a participant allowed here, or a host, gets the site as before", async () => {
  server(true);
  window.location.hash = "#/chat";
  render(<App />);
  expect(await screen.findByText("Dr. Smith")).toBeTruthy();
  expect(screen.queryByText(NOT_ACTIVE)).toBeNull();
  cleanup();
  server(false, true);
  render(<App />);
  await screen.findByText("ann@example.com");
  expect(screen.queryByText(NOT_ACTIVE)).toBeNull();
});

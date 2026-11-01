// Host properties in Admin settings: every host, narrowed by a search (roadmap R241).

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { HostProperties } from "./host-properties";

const HOSTS = ["ann@example.com", "bob@ann.net", "joanne@site.org"];

// A server that matches as the real one does: anywhere in the email, ignoring capitals.
function server(status = 200) {
  const fetchMock = vi.fn(async (url: string) => {
    const at = new URL(url, "http://x");
    if (at.pathname !== "/api/admin/hosts") return new Response("", { status: 404 });
    if (status !== 200) return Response.json({ detail: "The host accounts can't be read." }, { status });
    const q = (at.searchParams.get("q") ?? "").toLowerCase();
    return Response.json({ hosts: HOSTS.filter((h) => h.includes(q)) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function listed(): string[] {
  return screen.queryAllByRole("listitem").map((li) => li.textContent ?? "");
}

async function type(text: string) {
  await act(async () => {
    fireEvent.input(screen.getByRole("searchbox", { name: "Search hosts by email" }), {
      target: { value: text },
    });
  });
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

test("every host is listed, and the list narrows as the search is typed", async () => {
  const fetchMock = server();
  render(<HostProperties />);
  await waitFor(() => expect(listed()).toEqual(HOSTS));
  expect(fetchMock).toHaveBeenCalledWith("/api/admin/hosts");

  await type("ANN@");
  await waitFor(() => expect(listed()).toEqual(["ann@example.com"]));
  expect(fetchMock).toHaveBeenLastCalledWith("/api/admin/hosts?q=ANN%40");
  await type(".org");
  await waitFor(() => expect(listed()).toEqual(["joanne@site.org"]));
  await type("zed");
  expect(await screen.findByText("No host's email contains that.")).toBeTruthy();
  await type("");
  await waitFor(() => expect(listed()).toEqual(HOSTS));
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Host list: 3 shown \(\d+ ms\)$/));
});

test("an answer that comes late doesn't replace the one for what is typed now", async () => {
  let release: (hosts: string[]) => void = () => {};
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      url === "/api/admin/hosts"
        ? new Promise<Response>((done) => {
            release = (hosts) => done(Response.json({ hosts }));
          })
        : Promise.resolve(Response.json({ hosts: ["bob@ann.net"] })),
    ),
  );
  render(<HostProperties />);
  await type("bob");
  await waitFor(() => expect(listed()).toEqual(["bob@ann.net"]));
  await act(async () => release(HOSTS)); // the first read, for the empty box, comes last
  expect(listed()).toEqual(["bob@ann.net"]);
});

test("with no hosts yet, it says so", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ hosts: [] })));
  render(<HostProperties />);
  expect(await screen.findByText("No host has signed up yet.")).toBeTruthy();
});

test("when the hosts can't be read, it says why", async () => {
  server(503);
  render(<HostProperties />);
  expect(await screen.findByText("The host accounts can't be read.")).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith("Could not read the hosts", expect.any(Error));
});

test("a network failure says to try again", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
  render(<HostProperties />);
  expect(await screen.findByText("The hosts could not be read. Try again.")).toBeTruthy();
});

test("Admin settings shows Host properties under its form", async () => {
  const fetchMock = server();
  const base = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url: string) => {
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({});
    if (url === "/api/admin/laptop") return Response.json({ listed: true });
    if (url === "/api/admin/session") {
      return Response.json({ signed_in: true, password_set: true, timeout_minutes: 30, ended: null });
    }
    if (url === "/api/admin/settings") {
      const t = { blue_above: 60, orange_below: 30, red_below: 15 };
      return Response.json({
        timeout_minutes: 30,
        thresholds: t,
        disable_custom_image: true,
        disable_custom_voice: true,
        recommended: { timeout_minutes: 30, thresholds: t, disable_custom_image: true, disable_custom_voice: true },
      });
    }
    return base(url);
  });
  window.location.hash = "#/admin/settings";
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Host properties" })).toBeTruthy();
  await waitFor(() => expect(listed()).toEqual(HOSTS));
});

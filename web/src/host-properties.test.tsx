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

// A server whose answers are held until the test lets each one go (Codex's review of PR #267).
function heldServer() {
  const waiting = new Map<string, (r: Response) => void>();
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (url: string) =>
        new Promise<Response>((done) => {
          waiting.set(new URL(url, "http://x").searchParams.get("q") ?? "", done);
        }),
    ),
  );
  return async (q: string, response: Response) => {
    await act(async () => {
      waiting.get(q)!(response);
      await new Promise((settled) => setTimeout(settled, 0)); // its body read, then shown
    });
  };
}

test("while a new search is read, the last one's list or message isn't shown", async () => {
  const answer = heldServer();
  render(<HostProperties />);
  expect(screen.getByText("Reading the hosts…")).toBeTruthy();
  await answer("", Response.json({ hosts: HOSTS }));
  expect(listed()).toEqual(HOSTS);

  await type("zed");
  expect(listed()).toEqual([]); // not the full list under "zed"
  expect(screen.getByText("Searching…")).toBeTruthy();
  await answer("zed", Response.json({ hosts: [] }));
  expect(screen.getByText("No host's email contains that.")).toBeTruthy();

  await type(""); // cleared while the full list is read again
  expect(screen.queryByText("No host has signed up yet.")).toBeNull();
  expect(screen.queryByText("No host's email contains that.")).toBeNull();
  expect(screen.getByText("Reading the hosts…")).toBeTruthy();
  await answer("", Response.json({ hosts: HOSTS }));
  expect(listed()).toEqual(HOSTS);
});

test("a failed search's message isn't shown under the next search", async () => {
  const answer = heldServer();
  render(<HostProperties />);
  await type("ann");
  await answer("ann", Response.json({ detail: "The host accounts can't be read." }, { status: 503 }));
  expect(screen.getByText("The host accounts can't be read.")).toBeTruthy();
  await type("bob");
  expect(screen.queryByText("The host accounts can't be read.")).toBeNull();
  expect(screen.getByText("Searching…")).toBeTruthy();
  await answer("bob", Response.json({ hosts: ["bob@ann.net"] }));
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

// R242: the selected host's Allow and Deny, kept as the real server keeps them.
function choicesServer(fail: number | null = null) {
  const kept: Record<string, Record<string, string | null>> = {};
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const at = new URL(url, "http://x");
    if (at.pathname === "/api/admin/hosts") return Response.json({ hosts: HOSTS });
    if (at.pathname !== "/api/admin/hosts/properties") return new Response("", { status: 404 });
    if (fail) return Response.json({ detail: "Not now." }, { status: fail });
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, string | null>) : {};
    const email = at.searchParams.get("email") ?? String(body.email);
    const host = (kept[email] ??= { custom_image: null, custom_voice: null });
    for (const kind of ["custom_image", "custom_voice"]) if (kind in body) host[kind] = body[kind];
    return Response.json({ email, ...host, default: { custom_image: "disabled", custom_voice: "enabled" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function pressed(name: string): boolean {
  return screen.getByRole("button", { name }).getAttribute("aria-pressed") === "true";
}

async function click(name: string) {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name }));
  });
}

test("selecting a host shows their Allow and Deny, with the defaults", async () => {
  choicesServer();
  render(<HostProperties />);
  await click(await screen.findByRole("button", { name: "ann@example.com" }).then((b) => b.textContent!));
  expect(await screen.findByRole("group", { name: "Properties of ann@example.com" })).toBeTruthy();
  for (const name of ["Allow Custom Image", "Deny Custom Image", "Allow Custom Sound", "Deny Custom Sound"]) {
    expect(pressed(name)).toBe(false);
  }
  expect(screen.getByText("Default: disabled")).toBeTruthy();
  expect(screen.getByText("Default: enabled")).toBeTruthy();
  expect(pressed("ann@example.com")).toBe(true);
  await click("ann@example.com"); // selected again: closed
  expect(screen.queryByRole("group")).toBeNull();
});

test("Allow and Deny can't both be chosen, and choosing one again goes back to the default", async () => {
  const fetchMock = choicesServer();
  render(<HostProperties />);
  await click(await screen.findByRole("button", { name: "bob@ann.net" }).then((b) => b.textContent!));
  await screen.findByRole("group");
  await click("Allow Custom Image");
  await waitFor(() => expect(pressed("Allow Custom Image")).toBe(true));
  expect(fetchMock).toHaveBeenLastCalledWith("/api/admin/hosts/properties", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "bob@ann.net", custom_image: "allow" }),
  });
  await click("Deny Custom Image"); // the other is cleared
  await waitFor(() => expect(pressed("Deny Custom Image")).toBe(true));
  expect(pressed("Allow Custom Image")).toBe(false);
  await click("Deny Custom Image"); // again: back to the default
  await waitFor(() => expect(pressed("Deny Custom Image")).toBe(false));
  expect(String(fetchMock.mock.lastCall?.[1]?.body)).toBe('{"email":"bob@ann.net","custom_image":null}');
  await click("Deny Custom Sound");
  await waitFor(() => expect(pressed("Deny Custom Sound")).toBe(true));
  expect(pressed("Deny Custom Image")).toBe(false); // the image is left as it was
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Host properties changed: custom_voice deny \(\d+ ms\)$/));
});

test("when a host's properties can't be read or saved, it says why", async () => {
  choicesServer(503);
  render(<HostProperties />);
  await click(await screen.findByRole("button", { name: "ann@example.com" }).then((b) => b.textContent!));
  expect(await screen.findByText("Not now.")).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith("Could not read the host's properties", expect.any(Error));
});

test("a choice that can't be saved says so and keeps what was shown", async () => {
  const fetchMock = choicesServer();
  render(<HostProperties />);
  await click(await screen.findByRole("button", { name: "ann@example.com" }).then((b) => b.textContent!));
  await screen.findByRole("group");
  const ok = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
    init?.method === "PUT" ? Promise.reject(new TypeError("Failed to fetch")) : ok(url, init),
  );
  await click("Allow Custom Sound");
  expect(await screen.findByText("That didn't work. Try again.")).toBeTruthy();
  expect(pressed("Allow Custom Sound")).toBe(false);
});

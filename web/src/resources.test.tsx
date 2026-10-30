import { cleanup, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { size } from "./resources";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

// A server with consent given and, when `host`, a signed-in host whose disk use is `disk`.
function server(host: boolean, disk: Record<string, number> | null = null) {
  const asked: string[] = [];
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({ view: host ? "host" : "participant" });
    if (url === "/api/host/session") {
      return Response.json({ signed_in: host, email: host ? "host@example.com" : null });
    }
    if (url === "/api/settings/access") return Response.json({ shown: host, as: null });
    if (url.startsWith("/api/host/disk")) {
      asked.push(url);
      return disk ? Response.json(disk) : new Response("", { status: 500 });
    }
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { asked };
}

function topBar(): HTMLElement {
  return document.querySelector("header") as HTMLElement;
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

test("sizes are in MB below a GB, else in GB", () => {
  expect(size(0)).toBe("0.0 MB");
  expect(size(191_310)).toBe("0.2 MB");
  expect(size(25_400_000)).toBe("25.4 MB");
  expect(size(1_250_000_000)).toBe("1.25 GB");
});

test("a signed-in host opens Resources from the top bar and sees the three amounts", async () => {
  const disk = { images_and_recordings: 96_078, pdfs: 12_500_000, total: 12_596_078 };
  const { asked } = server(true, disk);
  window.location.hash = "#/resources";
  render(<App />);
  expect(await within(topBar()).findByRole("link", { name: "Resources" })).toHaveProperty(
    "hash",
    "#/resources",
  );
  const amounts = within(await screen.findByRole("region", { name: "Disk space used" }));
  const rows = amounts.getAllByRole("definition").map((d) => d.textContent);
  expect(rows).toEqual(["0.1 MB", "12.5 MB", "12.6 MB"]);
  expect(amounts.getByText("Images and voice recordings")).toBeTruthy();
  expect(asked).toEqual(["/api/host/disk?opened=true"]);
  expect(console.info).toHaveBeenCalledWith(`Resource view opened: ${JSON.stringify(disk)}`);
});

test("anyone not signed in as a host has no Resources link, and the page is for the host", async () => {
  const { asked } = server(false);
  window.location.hash = "#/resources";
  render(<App />);
  expect(await screen.findByRole("heading", { name: "For the host only" })).toBeTruthy();
  expect(within(topBar()).queryByRole("link", { name: "Resources" })).toBeNull();
  expect(asked).toEqual([]);
});

test("disk space that can't be read says so", async () => {
  server(true, null);
  window.location.hash = "#/resources";
  render(<App />);
  expect(
    await screen.findByText("The disk space used could not be read. Reload to try again."),
  ).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith(
    "Could not read the disk space used",
    expect.anything(),
  );
});

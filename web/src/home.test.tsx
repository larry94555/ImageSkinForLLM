import { cleanup, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { choices, HomePage, loadHome } from "./home";

const PHOTO_ID = "a".repeat(32);

function server(accepted: boolean, photo: string | null = PHOTO_ID, ok = true) {
  const fetchMock = vi.fn(async (url: string) => {
    if (!ok) return new Response("", { status: 503 });
    if (url === "/api/review") {
      return Response.json({ accepted, accepted_at: accepted ? "2026-10-12T08:00:00Z" : null });
    }
    if (url === "/api/uploads/photos/chosen") return Response.json({ id: photo, chosen_by: "app" });
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function hrefs(): Record<string, string | null> {
  return Object.fromEntries(
    screen.getAllByRole("listitem").map((li) => {
      const link = li.querySelector("a")!;
      return [link.querySelector(".title")!.textContent, link.getAttribute("href")];
    }),
  );
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("before setup is done, home offers only setup, at consent until it is given", async () => {
  server(false);
  render(<HomePage consented={false} />);
  expect(await screen.findByText("Welcome")).toBeTruthy();
  expect(hrefs()).toEqual({ "Start setup": "#/consent" });
  expect(screen.queryByRole("img")).toBeNull();
});

test("before setup is done, with consent given, setup opens the setup page", async () => {
  server(false);
  render(<HomePage consented />);
  await screen.findByText("Welcome");
  expect(hrefs()).toEqual({ "Start setup": "#/setup" });
});

test("once setup is done, chat and manage content stand beside setup", async () => {
  server(true);
  render(<HomePage consented />);
  expect(await screen.findByText("Welcome back")).toBeTruthy();
  expect(hrefs()).toEqual({ Chat: "#/chat", "Manage Content": "#/content", Setup: "#/setup" });
  const portrait = screen.getByRole("img", { name: "The person in the video" });
  expect(portrait.getAttribute("src")).toBe(`/api/uploads/photos/${PHOTO_ID}`);
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Home loaded in \d+ ms \(setup done\)$/));
});

test("once setup is done but no photo is chosen, there is no portrait", async () => {
  server(true, null);
  render(<HomePage consented />);
  await screen.findByText("Welcome back");
  expect(screen.queryByRole("img")).toBeNull();
});

test("if the server can't be reached, home offers setup and logs why", async () => {
  server(false, null, false);
  expect(await loadHome()).toEqual({ done: false, photo: null });
  expect(console.error).toHaveBeenCalledWith(
    "Could not load the home page's setup state",
    expect.any(Error),
  );
});

test("the choices keep the same order: chat, manage content, setup", () => {
  expect(choices(true, false).map((c) => [c.title, c.href])).toEqual([
    ["Chat", "#/chat"],
    ["Manage Content", "#/content"],
    ["Setup", "#/consent"],
  ]);
});

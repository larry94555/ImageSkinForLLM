import { cleanup, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { choices, HomePage, loadHome } from "./home";

const PHOTO_ID = "a".repeat(32);

// Like the real server, the setup reads are refused until consent is given.
function server(
  accepted: boolean,
  photo: string | null = PHOTO_ID,
  ok = true,
  consented = true,
  chosen: object | null = null,
) {
  const fetchMock = vi.fn(async (url: string) => {
    if (!ok) return new Response("", { status: 503 });
    // A default person needs no consent (R24c).
    if (url === "/api/start-now") return Response.json({ state: "idle", chosen });
    if (!consented) return new Response("", { status: 403 });
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

test("before consent, home offers setup at consent without asking for setup state", async () => {
  const fetchMock = server(false, null, true, false);
  render(<HomePage consented={false} />);
  expect(await screen.findByText("Welcome")).toBeTruthy();
  expect(hrefs()).toEqual({ "Start now": "#/start-now", "Start setup": "#/consent" });
  expect(screen.queryByRole("img")).toBeNull();
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/start-now"]);
  expect(console.error).not.toHaveBeenCalled();
});

test("before setup is done, with consent given, setup opens the setup page", async () => {
  server(false);
  render(<HomePage consented />);
  await screen.findByText("Welcome");
  expect(hrefs()).toEqual({ "Start now": "#/start-now", "Start setup": "#/setup" });
});

test("with a default person chosen, setup is done without consent (R24c)", async () => {
  const chosen = { gender: "male", accent: "British", realism: "animated", role: "Boss" };
  server(false, null, true, false, chosen);
  render(<HomePage consented={false} />);
  expect(await screen.findByText("Welcome back")).toBeTruthy();
  // Setup chooses another default person, or leads on to the user's own.
  expect(hrefs()).toEqual({ Chat: "#/chat", "Manage Content": "#/content", Setup: "#/start-now" });
  const portrait = screen.getByRole("img", { name: "The person in the video" });
  expect(portrait.getAttribute("src")).toBe("/api/start-now/picture");
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
  expect(await loadHome(true)).toEqual({ done: false, photo: null });
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

test("each choice has its own picture, hidden from screen readers (R41e2)", async () => {
  server(true);
  render(<HomePage consented />);
  await screen.findByText("Welcome back");
  const pictures = screen
    .getAllByRole("link")
    .map((a) => a.querySelector(".icon[aria-hidden='true'] path")?.getAttribute("d"));
  expect(pictures).toHaveLength(3);
  expect(new Set(pictures).size).toBe(3); // the chat, the content and setup differ
  expect(screen.getByRole("link", { name: /^Chat/ })).toBeTruthy(); // the name is still the words
});

// Roadmap R30: a return visit to the app's address goes straight to the chat once setup is
// saved; Home opened from the top bar still shows the choices.
test("a visit that starts on home goes straight to the chat once setup is done", async () => {
  server(true);
  window.location.hash = "";
  render(<HomePage consented landing />);
  await vi.waitFor(() => expect(window.location.hash).toBe("#/chat"));
  expect(console.info).toHaveBeenCalledWith("Setup is saved, so the visit starts in the chat");
  expect(screen.queryByText("Welcome back")).toBeNull();
  window.location.hash = "";
});

test("a visit that starts on home stays there while setup isn't done", async () => {
  server(false);
  window.location.hash = "";
  render(<HomePage consented landing />);
  expect(await screen.findByText("Welcome")).toBeTruthy();
  expect(window.location.hash).toBe("");
  expect(console.info).not.toHaveBeenCalledWith("Setup is saved, so the visit starts in the chat");
});

test("a late answer doesn't open the chat once the user has left home (review on PR #108)", async () => {
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  const fetchMock = server(true);
  const answer = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url: string) => {
    await held;
    return answer(url);
  });
  window.location.hash = "";
  const { unmount } = render(<HomePage consented landing />);
  unmount(); // the user clicked another page before home's setup state came back
  window.location.hash = "#/content";
  release();
  await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(window.location.hash).toBe("#/content");
  expect(console.info).not.toHaveBeenCalledWith("Setup is saved, so the visit starts in the chat");
  window.location.hash = "";
});

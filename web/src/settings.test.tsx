import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { openSettings, returnToApp } from "./settings.test.util";

// A server with consent given and the settings saved as `saved`; everything else isn't there.
function server(saved: Record<string, unknown>, saves = true) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url !== "/api/settings") return new Response("", { status: 404 });
    if (init?.method !== "PATCH") return Response.json(saved);
    if (!saves) return new Response("", { status: 500 });
    Object.assign(saved, JSON.parse(String(init.body)));
    return Response.json(saved);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function openAt(hash: string) {
  window.location.hash = hash;
  render(<App />);
  await screen.findByRole("link", { name: "Settings" });
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

test("every page has the Settings link, and it is marked on the Settings page", async () => {
  server({});
  for (const hash of ["#/", "#/setup", "#/chat", "#/wiki", "#/content", "#/guide", "#/nowhere"]) {
    await openAt(hash);
    const link = screen.getByRole("link", { name: "Settings" });
    expect(link.getAttribute("href")).toBe("#/settings");
    expect(link.className).toBe("settings-link");
    cleanup();
  }
  await openAt("#/settings");
  expect(screen.getByRole("link", { name: "Settings" }).className).toBe("settings-link current");
  expect(screen.getByRole("heading", { name: "Settings", level: 1 })).toBeTruthy();
});

test("the page groups the settings and shows each one as saved", async () => {
  server({ view: "host", quiz_me: true, general_prompts: true });
  await openAt("#/settings");
  const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
  expect(headings).toEqual([
    "View",
    "Chat",
    "Display",
    "LLM",
    "ChatGPT plan",
    "Photos and recordings",
    "Photo, voice and accent",
    "Video and conversation",
    "Your data",
  ]);
  const chat = within(screen.getByRole("region", { name: "Chat" }));
  const checked = (name: string) => (chat.getByRole("checkbox", { name }) as HTMLInputElement).checked;
  expect(checked("Answer questions outside the content")).toBe(true);
  expect(checked("Quiz me")).toBe(true);
  expect(checked("Teach me")).toBe(false);
  const display = within(screen.getByRole("region", { name: "Display" }));
  expect(display.getAllByRole("checkbox").map((b) => b.parentElement?.textContent?.trim())).toEqual(
    ["Show timing metrics", "Debug"],
  );
});

test("the question scope is changed on the Settings page (R41, R27)", async () => {
  const saved: Record<string, unknown> = { general_prompts: false };
  const fetchMock = server(saved);
  await openAt("#/settings");
  const box = screen.getByRole("checkbox", {
    name: "Answer questions outside the content",
  }) as HTMLInputElement;
  await act(async () => {
    fireEvent.click(box);
  });
  expect(saved.general_prompts).toBe(true);
  expect(box.checked).toBe(true);
  const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
  expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ general_prompts: true });
});

test("a change that can't be saved says so and leaves the box as it was", async () => {
  server({ general_prompts: false }, false);
  await openAt("#/settings");
  const box = screen.getByRole("checkbox", {
    name: "Answer questions outside the content",
  }) as HTMLInputElement;
  await act(async () => {
    fireEvent.click(box);
  });
  expect(await screen.findByText("The setting could not be changed. Try again.")).toBeTruthy();
  expect(box.checked).toBe(false);
});

test("Return to the app goes back to the page Settings was opened from", async () => {
  server({});
  await openAt("#/content");
  await openSettings();
  expect(window.location.hash).toBe("#/settings");
  await returnToApp();
  expect(window.location.hash).toBe("#/content");
});

test("opened by its address, Settings returns to the first page of the view", async () => {
  server({});
  await openAt("#/settings");
  await returnToApp();
  expect(window.location.hash).toBe("#/");
  cleanup();

  server({ view: "participant" });
  await openAt("#/settings");
  expect(screen.getByRole("link", { name: "Return to the app" }).getAttribute("href")).toBe(
    "#/chat",
  );
  // The photos and recordings are the host's, so a participant can't delete them (R31).
  expect(screen.queryByRole("button", { name: "Delete my data" })).toBeNull();
  // Nor pick the LLM or enter its key (R42).
  expect(screen.queryByRole("heading", { name: "LLM" })).toBeNull();
});

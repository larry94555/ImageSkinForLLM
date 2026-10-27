// Say it simpler: the latest reply said again in simpler terms (roadmap R157).

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { Turn } from "./api";
import { App } from "./App";
import { QUIZ_KEY } from "./progress";

const TURNS: Turn[] = [
  { role: "user", content: "Why does rain fall?" },
  { role: "assistant", content: "Condensation nucleates droplets." },
];

// A fake server with the sample accepted and the conversation `TURNS`; POST /api/chat answers
// with a simpler reply, not streamed, with nothing to say aloud.
function server() {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/review") return Response.json({ accepted: true, accepted_at: null });
    if (url === "/api/chat") {
      if (init?.method !== "POST") return Response.json({ turns: TURNS });
      return Response.json({ role: "assistant", content: "Small drops join.", turn: 3 });
    }
    if (url === "/api/settings") return Response.json({ quiz_me: true });
    if (url === "/api/chat/video") return Response.json({ video: null });
    if (url.startsWith("/api/chat/clips/")) {
      return Response.json({ detail: "No clips" }, { status: 404 });
    }
    return Response.json([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("Say it simpler asks for the latest reply in simpler terms, and shows the new one", async () => {
  const fetchMock = server();
  window.location.hash = "#/chat";
  render(<App />);
  await screen.findByText("Condensation nucleates droplets.");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Say it simpler" }));
  });
  const sent = fetchMock.mock.calls.find(([url, init]) => url === "/api/chat" && init?.method);
  expect(JSON.parse(String(sent?.[1]?.body)).prompt).toBe("Say it simpler");
  expect(console.info).toHaveBeenCalledWith("Say it simpler");
  expect(await screen.findByText("Small drops join.")).toBeTruthy();
  await waitFor(() =>
    expect(
      (screen.getByRole("button", { name: "Say it simpler" }) as HTMLButtonElement).disabled,
    ).toBe(false),
  );
});

test("Say it simpler is not offered while a quiz is going", async () => {
  server();
  const quiz = { topic: "Rain", number: 1, question: "What is rain?", part: 0 };
  localStorage.setItem(QUIZ_KEY, JSON.stringify(quiz));
  window.location.hash = "#/chat";
  render(<App />);
  await screen.findByText("Condensation nucleates droplets.");
  expect(screen.getByRole("button", { name: "Repeat" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Say it simpler" })).toBeNull();
});

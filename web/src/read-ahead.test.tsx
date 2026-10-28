// The question typed so far is read ahead by the LLM once typing pauses (roadmap R148).

import { act, cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import { READ_AHEAD_PAUSE_MS } from "./pages";
import { QUIZ_KEY } from "./progress";

// A fake server with the sample accepted and an empty conversation; a prompt sent is answered
// with nothing to say aloud.
function server() {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/review") return Response.json({ accepted: true, accepted_at: null });
    if (url === "/api/chat") {
      if (init?.method !== "POST") return Response.json({ turns: [] });
      return Response.json({ role: "assistant", content: "Two moons.", turn: 1 });
    }
    if (url === "/api/chat/ahead") return Response.json({ read: true, reason: "read" });
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

function readsAhead(fetchMock: ReturnType<typeof server>): string[] {
  return fetchMock.mock.calls
    .filter(([url]) => url === "/api/chat/ahead")
    .map(([, init]) => JSON.parse(String(init?.body)).prompt as string);
}

async function type(text: string) {
  await act(async () => {
    fireEvent.input(screen.getByPlaceholderText("Type your question here"), {
      target: { value: text },
    });
  });
}

async function pause(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "debug").mockImplementation(() => {});
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function openChat() {
  window.location.hash = "#/chat";
  render(<App />);
  await screen.findByPlaceholderText("Type your question here");
}

test("the question typed so far is read ahead once typing pauses, once", async () => {
  const fetchMock = server();
  await openChat();
  await type("How many moons");
  await pause(READ_AHEAD_PAUSE_MS / 2);
  await type("How many moons does Mars");
  await pause(READ_AHEAD_PAUSE_MS / 2);
  expect(readsAhead(fetchMock)).toEqual([]); // still typing
  await pause(READ_AHEAD_PAUSE_MS);
  expect(readsAhead(fetchMock)).toEqual(["How many moons does Mars"]);
  expect(console.debug).toHaveBeenCalledWith("Question read ahead: true");
  await type("How many moons does Mars ");
  await pause(READ_AHEAD_PAUSE_MS * 2);
  expect(readsAhead(fetchMock)).toHaveLength(1); // the same question
});

test("a question too short is not read ahead", async () => {
  const fetchMock = server();
  await openChat();
  await type("Mars moons");
  await pause(READ_AHEAD_PAUSE_MS * 2);
  expect(readsAhead(fetchMock)).toEqual([]);
});

test("an answer to a quiz is not read ahead", async () => {
  const fetchMock = server();
  localStorage.setItem(
    QUIZ_KEY,
    JSON.stringify({ topic: "Mars", number: 1, question: "How many moons?", part: 0 }),
  );
  await openChat();
  await type("It has two moons");
  await pause(READ_AHEAD_PAUSE_MS * 2);
  expect(readsAhead(fetchMock)).toEqual([]);
});

test("a read ahead that fails is only noted", async () => {
  const fetchMock = server();
  const answer = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
    url === "/api/chat/ahead"
      ? Response.json({ detail: "Not ready" }, { status: 409 })
      : answer(url, init),
  );
  await openChat();
  await type("How many moons does Mars have");
  await pause(READ_AHEAD_PAUSE_MS * 2);
  expect(readsAhead(fetchMock)).toHaveLength(1);
  expect(console.debug).toHaveBeenCalledWith(
    "Could not read the question ahead",
    expect.any(Error),
  );
  expect(screen.queryByRole("alert")).toBeNull();
});

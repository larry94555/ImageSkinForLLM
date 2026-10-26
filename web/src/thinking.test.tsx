// What thinking is doing while a prompt is answered, and how long it took (R134c).
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { Thinking, Turn } from "./api";
import { App } from "./App";
import { chatText, thinkingTook } from "./pages";

type Answer = () => Promise<Response> | Response;

// A chat server: the conversation so far, the reply to a prompt when the test sends it, what
// thinking is doing, and the settings.
function server(
  turns: Turn[],
  answer: Answer,
  thinking: () => Response = () => Response.json({ detail: "Not thinking" }, { status: 404 }),
  settings: Record<string, unknown> = {},
) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/review") return Response.json({ accepted: true, accepted_at: null });
    if (url === "/api/settings") return Response.json(settings);
    if (url === "/api/chat") return init?.method === "POST" ? answer() : Response.json({ turns });
    if (url.startsWith("/api/chat/thinking/")) return thinking();
    if (url === "/api/chat/video") return Response.json({ video: null });
    if (url.startsWith("/api/chat/clips/")) return Response.json({ detail: "No clips" }, { status: 404 });
    return Response.json([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function later(): [Answer, (r: Response) => void] {
  let send: (r: Response) => void = () => {};
  const pending = new Promise<Response>((resolve) => (send = resolve));
  return [() => pending, (r) => send(r)];
}

const ASKING: Thinking = {
  stage: "Asking the LLM",
  detail: "It reads about 3200 tokens before it writes",
  stage_s: 4.2,
  elapsed_s: 5.1,
};

async function ask(text: string) {
  window.location.hash = "#/chat";
  render(<App />);
  await screen.findByText("Ask a question to start the conversation.");
  const box = screen.getByRole("textbox", { name: "Your message" });
  fireEvent.input(box, { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText(text);
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "debug").mockImplementation(() => {});
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("while thinking, the chat shows the stage, its detail and the time so far", async () => {
  const [answer, reply] = later();
  const fetchMock = server([], answer, () => Response.json(ASKING));
  await ask("Why is the sky blue?");
  expect(screen.getByText("Thinking…")).toBeTruthy();
  expect(
    await screen.findByText(
      "Asking the LLM: It reads about 3200 tokens before it writes (4 s)",
    ),
  ).toBeTruthy();
  expect(screen.getByText("0 s so far")).toBeTruthy();
  expect(await screen.findByText("1 s so far", {}, { timeout: 2000 })).toBeTruthy();
  const sent = fetchMock.mock.calls.find(([url, init]) => url === "/api/chat" && init?.method);
  const { reply_id } = JSON.parse(sent![1]!.body as string) as { reply_id: string };
  expect(fetchMock.mock.calls.some(([url]) => url === `/api/chat/thinking/${reply_id}`)).toBe(
    true,
  );
  await act(async () => {
    reply(Response.json({ role: "assistant", content: "Light scatters.", thinking_s: 12.4 }));
  });
  expect(await screen.findByText("Took 12 seconds for thinking")).toBeTruthy();
  expect(screen.queryByText(/so far/)).toBeNull();
  expect(screen.queryByText(/Asking the LLM/)).toBeNull();
});

test("a stage just started shows no time of its own, and one without detail just its name", async () => {
  const [answer] = later();
  server([], answer, () =>
    Response.json({ stage: "Looking through the PDFs", detail: null, stage_s: 0.3, elapsed_s: 0.3 }),
  );
  await ask("What is a cell?");
  expect(await screen.findByText("Looking through the PDFs")).toBeTruthy();
});

test("with Show what thinking is doing off, only Thinking… shows and no time is said", async () => {
  const [answer, reply] = later();
  const fetchMock = server([], answer, () => Response.json(ASKING), { show_thinking: false });
  await ask("Why is the sky blue?");
  expect(screen.getByText("Thinking…")).toBeTruthy();
  await new Promise((r) => setTimeout(r, 50));
  expect(screen.queryByText(/Asking the LLM/)).toBeNull();
  expect(screen.queryByText(/so far/)).toBeNull();
  expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith("/api/chat/thinking/"))).toBe(
    false,
  );
  await act(async () => {
    reply(Response.json({ role: "assistant", content: "Light scatters.", thinking_s: 12.4 }));
  });
  await screen.findByText("Light scatters.");
  expect(screen.queryByText(/for thinking/)).toBeNull();
});

test("a reading that fails is logged once and the time keeps counting", async () => {
  const [answer] = later();
  server([], answer, () => {
    throw new TypeError("network down");
  });
  await ask("Why?");
  expect(await screen.findByText("1 s so far", {}, { timeout: 2000 })).toBeTruthy();
  await waitFor(() =>
    expect(
      vi.mocked(console.error).mock.calls.filter(([m]) => m === "Could not read what thinking is doing"),
    ).toHaveLength(1),
  );
});

test("the conversation so far shows how long each reply took to think of", async () => {
  server(
    [
      { role: "user", content: "Older" },
      { role: "assistant", content: "Kept before the time was." },
      { role: "user", content: "Hello" },
      { role: "assistant", content: "Hi!", thinking_s: 0.4 },
      { role: "user", content: "Tell me more" },
      { role: "assistant", content: "Gladly.", thinking_s: 61 },
    ],
    () => Response.json({}),
  );
  window.location.hash = "#/chat";
  render(<App />);
  expect(await screen.findByText("Took 61 seconds for thinking")).toBeTruthy();
  expect(screen.getAllByText(/for thinking/)).toHaveLength(1); // the latest exchange is shown
});

test("the time is said in plain words", () => {
  expect(thinkingTook(0.4)).toBe("Took less than a second for thinking");
  expect(thinkingTook(1.2)).toBe("Took 1 second for thinking");
  expect(thinkingTook(12.6)).toBe("Took 13 seconds for thinking");
});

test("Copy chat says how long each reply took", () => {
  const turns: Turn[] = [
    { role: "user", content: "Hello" },
    { role: "assistant", content: "Hi!", thinking_s: 3 },
  ];
  expect(chatText(turns, 1)).toBe(
    "Chat: the last 1 of 1 exchanges\n\nYou: Hello\n\nReply: Hi! (took 3 seconds for thinking)",
  );
});

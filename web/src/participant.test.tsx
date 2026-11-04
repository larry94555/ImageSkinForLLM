// Participant sign-up and login (roadmap R46): Sign up and Sign in in the top bar for anyone not
// signed in as a host, the two pages, and Teach me's progress kept for the account.

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
import { reloading } from "./participant";
import { LESSON_KEY, progressChanged, SYNC_DELAY_MS } from "./progress";

vi.unmock("./api");

const PAT = "pat@example.com";
const LESSON = { topic: "Ponds", part: 2, active: true };

interface Server {
  host: boolean;
  participant: boolean;
  kept: Record<string, unknown>;
  asked: string[];
  refuse?: string;
}

function server(state: Partial<Server> = {}): Server {
  const s: Server = {
    host: false,
    participant: false,
    kept: {},
    asked: [],
    ...state,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const body = typeof init?.body === "string" ? init.body : "";
      s.asked.push(`${method} ${url} ${body}`.trim());
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings")
        return Response.json({ view: s.host ? "host" : "participant" });
      if (url === "/api/settings/access")
        return Response.json({ shown: s.host, as: null });
      if (url === "/api/host/page") return new Response(null, { status: 204 });
      if (url === "/api/host/session") {
        return Response.json({
          signed_in: s.host,
          email: s.host ? "host@example.com" : null,
        });
      }
      if (url === "/api/participant/session") {
        return Response.json({
          signed_in: s.participant,
          email: s.participant ? PAT : null,
        });
      }
      if (
        url === "/api/participant/sign-up" ||
        url === "/api/participant/sign-in"
      ) {
        if (s.refuse)
          return Response.json({ detail: s.refuse }, { status: 409 });
        s.participant = true;
        return Response.json({ signed_in: true, email: PAT });
      }
      if (url === "/api/participant/sign-out") {
        s.participant = false;
        return Response.json({ signed_in: false });
      }
      if (url === "/api/participant/progress") {
        if (method === "PUT") {
          s.kept = JSON.parse(body) as Record<string, unknown>;
          return new Response(null, { status: 204 });
        }
        return Response.json(s.kept);
      }
      return new Response("", { status: 404 });
    }),
  );
  return s;
}

function topBar(): HTMLElement {
  return document.querySelector("header") as HTMLElement;
}

let reloaded: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
  reloaded = vi.spyOn(reloading, "reload").mockImplementation(() => {});
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
  window.location.hash = "";
  localStorage.clear();
});

test("a visitor has Sign up and Sign in; a signed-in host has neither", async () => {
  server();
  window.location.hash = "#/chat";
  render(<App />);
  const bar = within(topBar());
  expect(await bar.findByRole("link", { name: "Sign up" })).toHaveProperty(
    "hash",
    "#/sign-up",
  );
  expect(bar.getByRole("link", { name: "Sign in" })).toHaveProperty(
    "hash",
    "#/sign-in",
  );
  cleanup();
  server({ host: true });
  render(<App />);
  await within(topBar()).findByText("host@example.com");
  expect(within(topBar()).queryByRole("link", { name: "Sign up" })).toBeNull();
});

test("signing up makes the account and opens the chat again as the account's", async () => {
  const s = server();
  window.location.hash = "#/sign-up";
  render(<App />);
  await screen.findByRole("heading", { name: "Sign up" });
  fireEvent.input(screen.getByLabelText("Email"), { target: { value: PAT } });
  fireEvent.input(screen.getByLabelText(/^Password \(at least/), {
    target: { value: "a long secret" },
  });
  fireEvent.input(screen.getByLabelText("Password again"), {
    target: { value: "a long secret" },
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  });
  expect(s.asked).toContain(
    `POST /api/participant/sign-up {"email":"${PAT}","password":"a long secret"}`,
  );
  await waitFor(() => expect(reloaded).toHaveBeenCalled());
  expect(window.location.hash).toBe("#/chat");
});

test("a sign-up refused says why, and two passwords that differ are said at once", async () => {
  const s = server({
    refuse: "That email address already has an account here. Sign in instead.",
  });
  window.location.hash = "#/sign-up";
  render(<App />);
  await screen.findByRole("heading", { name: "Sign up" });
  fireEvent.input(screen.getByLabelText("Email"), { target: { value: PAT } });
  fireEvent.input(screen.getByLabelText(/^Password \(at least/), {
    target: { value: "a long secret" },
  });
  fireEvent.input(screen.getByLabelText("Password again"), {
    target: { value: "another one" },
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  });
  expect((await screen.findByRole("alert")).textContent).toBe(
    "The two passwords are different.",
  );
  expect(
    s.asked.some((a) => a.startsWith("POST /api/participant/sign-up")),
  ).toBe(false);
  fireEvent.input(screen.getByLabelText("Password again"), {
    target: { value: "a long secret" },
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  });
  await waitFor(() =>
    expect(screen.getByRole("alert").textContent).toBe(
      "That email address already has an account here. Sign in instead.",
    ),
  );
  expect(reloaded).not.toHaveBeenCalled();
});

test("signing in opens the chat again", async () => {
  const s = server();
  window.location.hash = "#/sign-in";
  render(<App />);
  await screen.findByRole("heading", { name: "Sign in" });
  fireEvent.input(screen.getByLabelText("Email"), { target: { value: PAT } });
  fireEvent.input(screen.getByLabelText("Password"), {
    target: { value: "a long secret" },
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  });
  expect(
    s.asked.some((a) => a.startsWith("POST /api/participant/sign-in")),
  ).toBe(true);
  await waitFor(() => expect(reloaded).toHaveBeenCalled());
});

test("a signed-in participant's lesson comes from their account, and changes are sent", async () => {
  const s = server({ participant: true, kept: { lesson: LESSON } });
  window.location.hash = "#/sign-in";
  render(<App />);
  // Signed in already: the page says so, and the top bar has their email and Sign out.
  expect(await screen.findByText(/You are signed in with/)).toBeTruthy();
  expect(within(topBar()).getByText(PAT)).toBeTruthy();
  expect(JSON.parse(localStorage.getItem(LESSON_KEY) ?? "null")).toEqual(
    LESSON,
  );
  vi.useFakeTimers();
  localStorage.setItem(LESSON_KEY, JSON.stringify({ ...LESSON, part: 3 }));
  progressChanged();
  progressChanged(); // one send once the changes settle
  await act(async () => {
    vi.advanceTimersByTime(SYNC_DELAY_MS);
  });
  vi.useRealTimers();
  await waitFor(() =>
    expect(s.kept).toEqual({ lesson: { ...LESSON, part: 3 } }),
  );
  expect(
    s.asked.filter((a) => a.startsWith("PUT /api/participant/progress")),
  ).toHaveLength(1);
  // Signing out leaves the lesson with the account, not on this browser.
  await act(async () => {
    fireEvent.click(within(topBar()).getByRole("button", { name: "Sign out" }));
  });
  await waitFor(() => expect(reloaded).toHaveBeenCalled());
  expect(localStorage.getItem(LESSON_KEY)).toBeNull();
  progressChanged();
  await new Promise((r) => setTimeout(r, SYNC_DELAY_MS + 50));
  expect(
    s.asked.filter((a) => a.startsWith("PUT /api/participant/progress")),
  ).toHaveLength(1);
});

test("a lesson begun before signing up becomes the account's", async () => {
  localStorage.setItem(LESSON_KEY, JSON.stringify(LESSON));
  const s = server({ participant: true });
  window.location.hash = "#/sign-in";
  render(<App />);
  await screen.findByText(/You are signed in with/);
  await waitFor(() => expect(s.kept).toEqual({ lesson: LESSON }));
  expect(JSON.parse(localStorage.getItem(LESSON_KEY) ?? "null")).toEqual(
    LESSON,
  );
});

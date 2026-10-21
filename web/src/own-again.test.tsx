// Back to your own photo and voice from a ready-made avatar (Larry's test of PR #128).

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ChangeSetup } from "./change-setup";
import { SetupPage } from "./pages";

const DONE = {
  state: "done",
  photo_id: "p1",
  percent: 100,
  steps: [],
  error: null,
  started_at: "2026-10-21T08:00:00+00:00",
  finished_at: "2026-10-21T08:20:00+00:00",
};

// A ready-made avatar in use; `ownAccepted` says whether the user's own sample is accepted too.
function server(ownAccepted: boolean, deleteOk = true) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/start-now" && init?.method === "DELETE") {
      if (!deleteOk) return Response.json({ detail: "Accept it first." }, { status: 409 });
      return Response.json({ accepted: true, accepted_at: "2026-10-21T08:30:00+00:00" });
    }
    if (url === "/api/review") {
      return Response.json({
        accepted: true,
        accepted_at: null,
        default_person: true,
        own_sample_accepted: ownAccepted,
      });
    }
    if (url === "/api/prepare") return Response.json(DONE);
    if (url === "/api/accent") return Response.json({ accent: "own", available: false });
    if (url === "/api/voice-sample") return Response.json({ recordings: 1, seconds: 30, speech: 30 });
    if (url === "/api/uploads/photos/chosen") return Response.json({ id: "p1", automatic: true });
    if (url.startsWith("/api/uploads/")) return Response.json([]);
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
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

test("with your own sample accepted, Settings switches back to it at once", async () => {
  const fetchMock = server(true);
  render(<ChangeSetup />);
  expect(await screen.findByText(/already accepted: the chat switches to it at once/)).toBeTruthy();
  const link = screen.getByRole("link", { name: "Use your own photo and voice" });
  await act(async () => {
    fireEvent.click(link);
  });
  await waitFor(() => expect(window.location.hash).toBe("#/chat"));
  expect(fetchMock).toHaveBeenCalledWith("/api/start-now", { method: "DELETE" });
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/^Switched to your own photo and voice from Settings \(\d+ ms\)$/),
  );
});

test("without your own sample accepted, Settings opens setup", async () => {
  const fetchMock = server(false);
  render(<ChangeSetup />);
  const link = await screen.findByRole("link", { name: "Use your own photo and voice" });
  await screen.findByText(/Accept their sample video at the end of setup to switch/);
  await act(async () => {
    fireEvent.click(link);
  });
  expect(window.location.hash).toBe("#/setup");
  expect(fetchMock).not.toHaveBeenCalledWith("/api/start-now", { method: "DELETE" });
});

test("a refused switch says why", async () => {
  server(true, false);
  render(<ChangeSetup />);
  await screen.findByText(/already accepted/);
  await act(async () => {
    fireEvent.click(screen.getByRole("link", { name: "Use your own photo and voice" }));
  });
  expect(await screen.findByText("Accept it first.")).toBeTruthy();
});

test("setup with an avatar in use offers Accept until your own sample is accepted", async () => {
  server(false);
  render(<SetupPage />);
  expect(await screen.findByRole("button", { name: "Accept" })).toBeTruthy();
  expect(screen.queryByText(/You accepted this sample/)).toBeNull();
});

test("setup with your own sample accepted and an avatar in use switches to it", async () => {
  const fetchMock = server(true);
  render(<SetupPage />);
  const button = await screen.findByRole("button", { name: "Use your own photo and voice in the chat" });
  expect(screen.getByText(/but the chat uses a ready-made avatar/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
  await act(async () => {
    fireEvent.click(button);
  });
  await waitFor(() => expect(window.location.hash).toBe("#/chat"));
  expect(fetchMock).toHaveBeenCalledWith("/api/start-now", { method: "DELETE" });
});

test("a refused switch in setup says why", async () => {
  server(true, false);
  render(<SetupPage />);
  const button = await screen.findByRole("button", { name: "Use your own photo and voice in the chat" });
  await act(async () => {
    fireEvent.click(button);
  });
  expect(await screen.findByText("Could not switch: Accept it first.")).toBeTruthy();
});

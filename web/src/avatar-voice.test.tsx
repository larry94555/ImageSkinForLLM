// A ready-made avatar in your own voice (roadmap R24d).

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { AvatarVoicePage } from "./avatar-voice";
import { ChangeSetup } from "./change-setup";
import { SetupPage } from "./pages";
import { pageFor, resolve } from "./router";

const DONE = {
  state: "done",
  photo_id: "avatar-animated_female_professor",
  percent: 100,
  steps: [],
  error: null,
  started_at: "2026-10-21T08:00:00+00:00",
  finished_at: "2026-10-21T08:20:00+00:00",
};

interface Server {
  avatar?: boolean; // a ready-made avatar is in use
  ownVoice?: boolean; // it is to speak in the user's voice
  accepted?: boolean; // its sample in that voice is accepted
  refuse?: string; // the own-voice change is refused with this
}

function server(s: Server) {
  const state = { ownVoice: s.ownVoice === true, accepted: s.accepted === true };
  const review = () => ({
    accepted: s.avatar !== false,
    accepted_at: null,
    default_person: s.avatar !== false,
    own_sample_accepted: false,
    own_voice: state.ownVoice,
    voice_accepted: state.ownVoice && state.accepted,
  });
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/start-now/own-voice") {
      if (s.refuse) return Response.json({ detail: s.refuse }, { status: 409 });
      state.ownVoice = init?.method === "PUT";
      return Response.json(review());
    }
    if (url === "/api/review" && init?.method === "POST") {
      state.accepted = true;
      return Response.json(review());
    }
    if (url === "/api/review") return Response.json(review());
    if (url === "/api/prepare") return Response.json(DONE);
    if (url === "/api/accent") return Response.json({ accent: "own", available: true });
    if (url === "/api/voice-sample") return Response.json({ recordings: 1, seconds: 30, speech: 30 });
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

test("the page has its own address, for the host only", () => {
  expect(pageFor("#/avatar-voice")).toBe("avatar-voice");
  expect(resolve("#/avatar-voice", false)).toEqual({ page: "avatar-voice" });
  expect(resolve("#/avatar-voice", true, true).page).toBe("chat");
});

test("consent for the person in the recordings comes first", async () => {
  const fetchMock = server({});
  render(<AvatarVoicePage />);
  const box = await screen.findByRole("checkbox");
  expect(screen.getByText(/agreed to have their voice copied/)).toBeTruthy();
  const button = screen.getByRole("button", { name: "Continue" });
  expect((button as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(box);
  await act(async () => {
    fireEvent.click(button);
  });
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/start-now/own-voice",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ agreed: true }) }),
  );
  // Then the steps, with the avatar's picture in place of the photos.
  expect(await screen.findByRole("img", { name: "The ready-made avatar" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Voice recordings" })).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Avatar to speak in your own voice \(\d+ ms\)$/));
});

test("a refused consent says why", async () => {
  server({ refuse: "Choose a ready-made avatar first." });
  render(<AvatarVoicePage />);
  fireEvent.click(await screen.findByRole("checkbox"));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  });
  expect(await screen.findByText("Choose a ready-made avatar first.")).toBeTruthy();
});

test("without an avatar it says to choose one", async () => {
  server({ avatar: false });
  render(<AvatarVoicePage />);
  expect(await screen.findByRole("link", { name: "Choose an avatar" })).toBeTruthy();
});

test("a failed load says so", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
  render(<AvatarVoicePage />);
  expect(await screen.findByText(/Could not load the page/)).toBeTruthy();
});

test("the sample is accepted without rejecting the avatar's picture", async () => {
  server({ ownVoice: true });
  render(<AvatarVoicePage />);
  const accept = await screen.findByRole("button", { name: "Accept" });
  expect(screen.queryByRole("button", { name: "Reject image" })).toBeNull();
  expect(screen.getByRole("button", { name: "Reject voice" })).toBeTruthy();
  await act(async () => {
    fireEvent.click(accept);
  });
  await waitFor(() => expect(window.location.hash).toBe("#/chat"));
});

test("rejecting the voice goes back to the recordings", async () => {
  server({ ownVoice: true });
  render(<AvatarVoicePage />);
  const target = await screen.findByRole("button", { name: "Reject voice" });
  await act(async () => {
    fireEvent.click(target);
  });
  expect(await screen.findByText(/You rejected the voice/)).toBeTruthy();
});

test("an accepted sample says so", async () => {
  server({ ownVoice: true, accepted: true });
  render(<AvatarVoicePage />);
  expect(await screen.findByText(/You accepted this sample/)).toBeTruthy();
  expect(screen.queryByText(/but the chat uses a ready-made avatar/)).toBeNull();
});

test("the avatar's ready-made voice can be used again", async () => {
  const fetchMock = server({ ownVoice: true });
  render(<AvatarVoicePage />);
  const target = await screen.findByRole("button", { name: "Use the avatar's ready-made voice" });
  await act(async () => {
    fireEvent.click(target);
  });
  await waitFor(() => expect(window.location.hash).toBe("#/chat"));
  expect(fetchMock).toHaveBeenCalledWith("/api/start-now/own-voice", { method: "DELETE" });
});

test("a refused ready-made voice says why", async () => {
  server({ ownVoice: true, refuse: "Not now." });
  render(<AvatarVoicePage />);
  const target = await screen.findByRole("button", { name: "Use the avatar's ready-made voice" });
  await act(async () => {
    fireEvent.click(target);
  });
  expect(await screen.findByText("Not now.")).toBeTruthy();
});

test("Settings offers your own voice for the avatar", async () => {
  server({});
  render(<ChangeSetup />);
  const link = await screen.findByRole("link", { name: "Use my own voice" });
  expect(link.getAttribute("href")).toBe("#/avatar-voice");
  expect(screen.getByText(/replace its voice with one made from your recordings/)).toBeTruthy();
});

test("Settings says whether the avatar speaks in your voice yet", async () => {
  server({ ownVoice: true });
  render(<ChangeSetup />);
  expect(await screen.findByRole("link", { name: "Change your voice for the avatar" })).toBeTruthy();
  expect(screen.getByText(/until you accept the sample video in your voice/)).toBeTruthy();
  cleanup();
  server({ ownVoice: true, accepted: true });
  render(<ChangeSetup />);
  expect(await screen.findByText("The avatar speaks in your voice, made from your recordings.")).toBeTruthy();
});

test("setup for your own photo first undoes the avatar's voice", async () => {
  const fetchMock = server({ ownVoice: true });
  render(<SetupPage />);
  const button = await screen.findByRole("button", { name: "Set up my own photo instead" });
  expect(screen.getByRole("link", { name: "Go to your voice for the avatar" })).toBeTruthy();
  await act(async () => {
    fireEvent.click(button);
  });
  expect(fetchMock).toHaveBeenCalledWith("/api/start-now/own-voice", { method: "DELETE" });
  expect(await screen.findByRole("heading", { name: "Photos" })).toBeTruthy();
});

test("a refused undo in setup says why", async () => {
  server({ ownVoice: true, refuse: "Not now." });
  render(<SetupPage />);
  const target = await screen.findByRole("button", { name: "Set up my own photo instead" });
  await act(async () => {
    fireEvent.click(target);
  });
  expect(await screen.findByText("Not now.")).toBeTruthy();
});

test("Settings switches back to the avatar's ready-made voice in one click", async () => {
  const fetchMock = server({ ownVoice: true, accepted: true });
  render(<ChangeSetup />);
  const button = await screen.findByRole("button", { name: "Use the avatar's ready-made voice" });
  expect(screen.getByText(/Switches back at once/)).toBeTruthy();
  await act(async () => {
    fireEvent.click(button);
  });
  expect(fetchMock).toHaveBeenCalledWith("/api/start-now/own-voice", { method: "DELETE" });
  expect(await screen.findByText("The avatar speaks in its ready-made voice again.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Use my own voice" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Use the avatar's ready-made voice" })).toBeNull();
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/^Avatar's ready-made voice used again from Settings \(\d+ ms\)$/),
  );
});

test("Settings says why the ready-made voice was refused", async () => {
  server({ ownVoice: true, refuse: "Wait until Prepare finishes, then try again." });
  render(<ChangeSetup />);
  const button = await screen.findByRole("button", { name: "Use the avatar's ready-made voice" });
  await act(async () => {
    fireEvent.click(button);
  });
  expect(await screen.findByText("Wait until Prepare finishes, then try again.")).toBeTruthy();
});

test("Settings offers the ready-made voice only once your own is chosen", async () => {
  server({});
  render(<ChangeSetup />);
  await screen.findByRole("link", { name: "Use my own voice" });
  expect(screen.queryByRole("button", { name: "Use the avatar's ready-made voice" })).toBeNull();
});

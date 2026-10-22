// A ready-made voice until recordings are added (feature item 59).

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { SetupPage } from "./pages";

// Some of the server's voices, as it labels them (R24e).
const VOICES = [
  { voice: "af_heart", label: "American woman 1" },
  { voice: "am_michael", label: "American man 1" },
  { voice: "af_heart,am_michael", label: "American nonbinary 1" },
  { voice: "bf_emma", label: "British woman 1" },
  { voice: "bf_emma,af_kore", label: "British woman, older 1" },
  { voice: "bm_george", label: "British man 1" },
  { voice: "bm_george,am_fenrir", label: "British man, younger 1" },
  { voice: "bf_emma,bm_george", label: "British nonbinary 1" },
];

// A server in setup with no recordings; `inUse` says whether the ready-made voice is used.
function server(inUse: boolean, putOk = true) {
  const state = { voice: "bf_emma" };
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/ready-voice") {
      if (init?.method === "PUT") {
        if (!putOk) return Response.json({ detail: "Not saved." }, { status: 500 });
        state.voice = JSON.parse(init.body as string).voice;
      }
      return Response.json({ voice: state.voice, in_use: inUse, voices: VOICES });
    }
    if (url === "/api/prepare") return Response.json({ state: "idle", steps: null, percent: 0 });
    if (url === "/api/accent") return Response.json({ accent: "own", available: false });
    if (url === "/api/voice-sample") return Response.json({ recordings: 0, seconds: 0, speech: 0 });
    if (url === "/api/uploads/photos/chosen") return Response.json({ id: null, automatic: true });
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
});

test("without recordings, setup says the person speaks in a ready-made voice", async () => {
  server(true);
  render(<SetupPage />);
  expect(await screen.findByRole("heading", { name: "No recordings?" })).toBeTruthy();
  const select = screen.getByRole("combobox", { name: "Ready-made voice" }) as HTMLSelectElement;
  expect(select.value).toBe("bf_emma"); // the last avatar's
  expect(screen.getByText("In use now: no recording has passed the checks.")).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith("Ready-made voice: bf_emma, in use: true");
});

test("another ready-made voice can be chosen", async () => {
  const fetchMock = server(true);
  render(<SetupPage />);
  const select = await screen.findByRole("combobox", { name: "Ready-made voice" });
  await act(async () => {
    fireEvent.change(select, { target: { value: "bm_george" } });
  });
  await waitFor(() => expect((select as HTMLSelectElement).value).toBe("bm_george"));
  const put = fetchMock.mock.calls.find(([url, init]) => url === "/api/ready-voice" && init?.method === "PUT");
  expect(JSON.parse(String(put?.[1]?.body))).toEqual({ voice: "bm_george" });
  await waitFor(() =>
    expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Ready-made voice chosen: bm_george \(\d+ ms\)$/)),
  );
});

test("with recordings, the ready-made voice is not in use", async () => {
  server(false);
  render(<SetupPage />);
  expect(await screen.findByText("Not in use: the voice is made from your recordings.")).toBeTruthy();
});

test("a voice that can't be saved says why", async () => {
  server(true, false);
  render(<SetupPage />);
  const select = await screen.findByRole("combobox", { name: "Ready-made voice" });
  await act(async () => {
    fireEvent.change(select, { target: { value: "am_michael" } });
  });
  expect(await screen.findByText("Not saved.")).toBeTruthy();
});

test("a nonbinary avatar's blended voice can be chosen too (R24b3)", async () => {
  const fetchMock = server(true);
  render(<SetupPage />);
  const select = (await screen.findByRole("combobox", { name: "Ready-made voice" })) as HTMLSelectElement;
  const labels = Array.from(select.options).map((o) => o.textContent);
  expect(labels).toContain("American nonbinary 1");
  expect(labels).toContain("British nonbinary 1");
  await act(async () => {
    fireEvent.change(select, { target: { value: "bf_emma,bm_george" } });
  });
  await waitFor(() => expect(select.value).toBe("bf_emma,bm_george"));
  const put = fetchMock.mock.calls.find(([url, init]) => url === "/api/ready-voice" && init?.method === "PUT");
  expect(JSON.parse(String(put?.[1]?.body))).toEqual({ voice: "bf_emma,bm_george" });
});

test("the voices offered are the server's, younger and older ones too (R24e)", async () => {
  server(true);
  render(<SetupPage />);
  const select = (await screen.findByRole("combobox", { name: "Ready-made voice" })) as HTMLSelectElement;
  expect(Array.from(select.options).map((o) => [o.value, o.textContent])).toEqual(
    VOICES.map(({ voice, label }) => [voice, label]),
  );
});

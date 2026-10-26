import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { FaceMovementChoice } from "./face-movement";
import { SettingsProvider } from "./settings";

// A server with the settings saved as `saved`; PATCH saves them, or fails when `saves` is false.
function server(saved: Record<string, unknown>, saves = true) {
  const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method !== "PATCH") return Response.json(saved);
    if (!saves) return new Response("", { status: 500 });
    Object.assign(saved, JSON.parse(String(init.body)));
    return Response.json(saved);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const radio = (name: string) => screen.getByRole("radio", { name }) as HTMLInputElement;

async function show() {
  render(
    <SettingsProvider>
      <FaceMovementChoice />
    </SettingsProvider>,
  );
  await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/settings")); // the settings are read
  await act(async () => {});
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

test("it shows the four strengths with the saved one picked, and saves a new one", async () => {
  const saved: Record<string, unknown> = { face_movement: "slight" };
  const fetchMock = server(saved);
  await show();
  expect(screen.getAllByRole("radio").map((r) => r.parentElement?.textContent?.trim())).toEqual([
    "Off",
    "Slight",
    "Normal",
    "More",
  ]);
  await waitFor(() => expect(radio("Slight").checked).toBe(true));
  expect(screen.getByText(/Prepare again to see it/)).toBeTruthy();
  await act(async () => {
    fireEvent.click(radio("Off"));
  });
  expect(saved.face_movement).toBe("off");
  expect(radio("Off").checked).toBe(true);
  const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
  expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ face_movement: "off" });
});

test("an unknown strength shows as Normal, and one that can't be saved goes back", async () => {
  server({ face_movement: "wild" }, false);
  await show();
  expect(radio("Normal").checked).toBe(true);
  await act(async () => {
    fireEvent.click(radio("More"));
  });
  expect(await screen.findByText("The face movement could not be changed. Try again.")).toBeTruthy();
  expect(radio("Normal").checked).toBe(true);
  expect(console.error).toHaveBeenCalled();
});

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { DetailBar } from "./detail-bar";
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

const bar = () => screen.getByRole("slider", { name: /Level of detail/ }) as HTMLInputElement;

async function show() {
  render(
    <SettingsProvider>
      <DetailBar />
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

test("the bar runs from High level to In depth and starts in the middle", async () => {
  server({});
  await show();
  expect(screen.getByText("High level")).toBeTruthy();
  expect(screen.getByText("In depth")).toBeTruthy();
  expect([bar().min, bar().max, bar().value]).toEqual(["1", "5", "3"]);
});

test("the saved level is shown, and a new one is saved at once", async () => {
  const saved: Record<string, unknown> = { detail: 2 };
  const fetchMock = server(saved);
  await show();
  await waitFor(() => expect(bar().value).toBe("2"));
  await act(async () => {
    fireEvent.change(bar(), { target: { value: "5" } });
  });
  expect(saved.detail).toBe(5);
  expect(bar().value).toBe("5");
  const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
  expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ detail: 5 });
  await waitFor(() => expect(console.info).toHaveBeenCalledWith("Level of detail set to 5"));
});

test("a level off the bar shows as the middle, and one that can't be saved goes back", async () => {
  server({ detail: 9 }, false);
  await show();
  expect(bar().value).toBe("3");
  await act(async () => {
    fireEvent.change(bar(), { target: { value: "1" } });
  });
  expect(await screen.findByText("The level of detail could not be changed. Try again.")).toBeTruthy();
  expect(bar().value).toBe("3");
  expect(console.error).toHaveBeenCalled();
});

test("moved quickly, only the last level is saved, after any save under way", async () => {
  const saved: Record<string, unknown> = { detail: 3 };
  let release: () => void = () => {};
  const bodies: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method !== "PATCH") return Response.json(saved);
      const body = JSON.parse(String(init.body));
      bodies.push(body);
      if (bodies.length === 1) await new Promise<void>((r) => (release = r)); // 4 answers late
      Object.assign(saved, body);
      return Response.json({ ...saved });
    }),
  );
  await show();
  await act(async () => {
    fireEvent.change(bar(), { target: { value: "4" } });
  });
  await act(async () => {
    fireEvent.change(bar(), { target: { value: "5" } });
  });
  expect(bar().value).toBe("5");
  await act(async () => release());
  await waitFor(() => expect(bodies).toEqual([{ detail: 4 }, { detail: 5 }]));
  await waitFor(() => expect(saved.detail).toBe(5));
  expect(bar().value).toBe("5");
});

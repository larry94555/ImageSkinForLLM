import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { Upload } from "./api";
import { YourFiles } from "./your-files";

const PHOTO = "a".repeat(32);
const OTHER_PHOTO = "b".repeat(32);
const SOUND = "c".repeat(32);
const BAD_SOUND = "d".repeat(32);

function upload(
  id: string,
  kind: "photos" | "sounds",
  name: string,
  problems: string[] | null,
): Upload {
  return {
    id,
    kind,
    name,
    format: kind === "photos" ? "jpg" : "wav",
    size: 1000,
    uploaded_at: "2026-10-17T00:00:00Z",
    seconds: kind === "sounds" ? 75 : null,
    problems,
    score: kind === "photos" && problems?.length === 0 ? 88 : null,
    speech: kind === "sounds" && problems?.length === 0 ? 70 : null,
  };
}

// A server with consent given (or not), two photos and two recordings, one of each in use.
// `checks` answers each Check again, by upload id.
function server(opts: { agreed?: boolean; checks?: Record<string, Upload | number> } = {}) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: opts.agreed ?? true });
    if (url === "/api/uploads/photos/chosen") return Response.json({ id: PHOTO, chosen_by: "app" });
    if (url === "/api/uploads/photos") {
      return Response.json([
        upload(OTHER_PHOTO, "photos", "old.jpg", []),
        upload(PHOTO, "photos", "me.jpg", []),
      ]);
    }
    if (url === "/api/uploads/sounds") {
      return Response.json([
        upload(SOUND, "sounds", "story.wav", []),
        upload(BAD_SOUND, "sounds", "noisy.wav", ["Too much noise."]),
      ]);
    }
    const id = /\/api\/uploads\/\w+\/(\w+)\/check$/.exec(url)?.[1];
    if (id && init?.method === "POST") {
      const answer = opts.checks?.[id];
      if (typeof answer === "number" || answer === undefined) {
        return Response.json({ detail: "No such file." }, { status: answer ?? 404 });
      }
      return Response.json(answer);
    }
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function show() {
  render(<YourFiles />);
  await screen.findByRole("heading", { name: "Recordings" });
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

test("shows only the photo and recordings in use, to view and play", async () => {
  server();
  await show();
  const photo = screen.getByRole("img", { name: "me.jpg" });
  expect(photo.getAttribute("src")).toBe(`/api/uploads/photos/${PHOTO}`);
  expect(photo.closest("a")?.getAttribute("href")).toBe(`/api/uploads/photos/${PHOTO}`);
  expect(screen.queryByRole("img", { name: "old.jpg" })).toBeNull();
  expect(screen.getByText("story.wav (1:15)")).toBeTruthy();
  expect(screen.queryByText(/noisy\.wav/)).toBeNull();
  const player = document.querySelector("ul.sounds audio");
  expect(player?.getAttribute("src")).toBe(`/api/uploads/sounds/${SOUND}`);
  expect(player?.hasAttribute("controls")).toBe(true);
  expect(screen.getByText("Looks good · score 88 of 100")).toBeTruthy();
  expect(screen.getByText("Looks good · 1:10 of speech")).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith("Photos and recordings in use: me.jpg, 1 recording(s)");
});

test("Check again shows the new result, even when it no longer passes", async () => {
  const fetchMock = server({
    checks: { [PHOTO]: upload(PHOTO, "photos", "me.jpg", ["Your face is too small."]) },
  });
  await show();
  const photo = screen.getByRole("img", { name: "me.jpg" }).closest("li") as HTMLElement;
  await act(async () => {
    fireEvent.click(within(photo).getByRole("button", { name: "Check again" }));
  });
  expect(await within(photo).findByText("Your face is too small.")).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith(`/api/uploads/photos/${PHOTO}/check`, { method: "POST" });
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/^Checked again: me\.jpg, 1 problem\(s\) \(\d+ ms\)$/),
  );
});

test("while one is being checked, it says so and the others wait", async () => {
  let answer: (r: Response) => void = () => {};
  server();
  const fetchMock = vi.mocked(fetch);
  const plain = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url, init) =>
    String(url).endsWith("/check") ? new Promise<Response>((r) => (answer = r)) : plain(url, init),
  );
  await show();
  const sound = screen.getByText(/story\.wav/).closest("li") as HTMLElement;
  await act(async () => {
    fireEvent.click(within(sound).getByRole("button", { name: "Check again" }));
  });
  expect(within(sound).getByText("Checking recording…")).toBeTruthy();
  for (const button of screen.getAllByRole("button", { name: "Check again" })) {
    expect((button as HTMLButtonElement).disabled).toBe(true);
  }
  await act(async () => {
    answer(Response.json(upload(SOUND, "sounds", "story.wav", [])));
  });
  expect(await within(sound).findByText("Looks good · 1:10 of speech")).toBeTruthy();
  for (const button of screen.getAllByRole("button", { name: "Check again" })) {
    expect((button as HTMLButtonElement).disabled).toBe(false);
  }
});

test("a check that fails says so and keeps the last result", async () => {
  server({ checks: { [SOUND]: 500 } });
  await show();
  const sound = screen.getByText(/story\.wav/).closest("li") as HTMLElement;
  await act(async () => {
    fireEvent.click(within(sound).getByRole("button", { name: "Check again" }));
  });
  expect(await within(sound).findByText("It could not be checked. Try again.")).toBeTruthy();
  expect(within(sound).getByText("Looks good · 1:10 of speech")).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith("Could not check story.wav again", expect.any(Error));
});

test("before consent, or with nothing in use, it points to Setup", async () => {
  const fetchMock = server({ agreed: false });
  await show();
  expect(screen.getByText(/No photo is in use yet/)).toBeTruthy();
  expect(screen.getByText(/No recording is in use yet/)).toBeTruthy();
  expect(screen.getAllByRole("link", { name: "Setup" })[0].getAttribute("href")).toBe("#/setup");
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/consent"]);
});

test("says when the list can't be loaded", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("", { status: 500 })),
  );
  render(<YourFiles />);
  expect(
    await screen.findByText("Could not load them. Reload the page to try again."),
  ).toBeTruthy();
  expect(console.error).toHaveBeenCalled();
});

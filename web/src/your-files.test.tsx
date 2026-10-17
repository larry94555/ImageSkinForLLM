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
// `checks` answers each Check again, by upload id, and the answer is saved, as the server does;
// `chosenAfter` is the photo for the video after a check (the server may pick another).
function server(
  opts: { agreed?: boolean; checks?: Record<string, Upload | number>; chosenAfter?: string } = {},
) {
  const photos = [
    upload(OTHER_PHOTO, "photos", "old.jpg", []),
    upload(PHOTO, "photos", "me.jpg", []),
  ];
  const sounds = [
    upload(SOUND, "sounds", "story.wav", []),
    upload(BAD_SOUND, "sounds", "noisy.wav", ["Too much noise."]),
  ];
  let chosen = PHOTO;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: opts.agreed ?? true });
    if (url === "/api/uploads/photos/chosen")
      return Response.json({ id: chosen, chosen_by: "app" });
    if (url === "/api/uploads/photos") return Response.json(photos);
    if (url === "/api/uploads/sounds") return Response.json(sounds);
    const id = /\/api\/uploads\/\w+\/(\w+)\/check$/.exec(url)?.[1];
    if (id && init?.method === "POST") {
      const answer = opts.checks?.[id];
      if (typeof answer === "number" || answer === undefined) {
        return Response.json({ detail: "No such file." }, { status: answer ?? 404 });
      }
      for (const list of [photos, sounds]) {
        const at = list.findIndex((u) => u.id === id);
        if (at >= 0) list[at] = answer;
      }
      chosen = opts.chosenAfter ?? chosen;
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

function itemOf(name: string): HTMLElement {
  return (screen.queryByRole("img", { name }) ?? screen.getByText(new RegExp(name))).closest(
    "li",
  ) as HTMLElement;
}

async function checkAgain(name: string) {
  await act(async () => {
    fireEvent.click(within(itemOf(name)).getByRole("button", { name: "Check again" }));
  });
}

test("Check again shows the new result, and keeps a file in use as it was", async () => {
  const checked = { ...upload(PHOTO, "photos", "me.jpg", []), score: 91 };
  const fetchMock = server({ checks: { [PHOTO]: checked } });
  await show();
  await checkAgain("me.jpg");
  expect(await within(itemOf("me.jpg")).findByText("Looks good · score 91 of 100")).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith(`/api/uploads/photos/${PHOTO}/check`, { method: "POST" });
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/^Checked again: me\.jpg, 0 problem\(s\) \(\d+ ms\)$/),
  );
  expect(screen.queryByText(/No longer/)).toBeNull();
  expect(screen.queryByRole("img", { name: "old.jpg" })).toBeNull();
});

test("a photo that no longer passes is replaced by the one now used for the video", async () => {
  server({
    checks: { [PHOTO]: upload(PHOTO, "photos", "me.jpg", ["Your face is too small."]) },
    chosenAfter: OTHER_PHOTO,
  });
  await show();
  await checkAgain("me.jpg");
  expect(await within(itemOf("me.jpg")).findByText("Your face is too small.")).toBeTruthy();
  expect(within(itemOf("me.jpg")).getByText("No longer used for the video")).toBeTruthy();
  expect(screen.getByRole("img", { name: "old.jpg" })).toBeTruthy();
  expect(within(itemOf("old.jpg")).queryByText(/No longer/)).toBeNull();
  expect(console.info).toHaveBeenCalledWith("me.jpg is no longer in use");
});

test("a photo that passes with a lower score can lose its place too", async () => {
  server({
    checks: { [PHOTO]: { ...upload(PHOTO, "photos", "me.jpg", []), score: 40 } },
    chosenAfter: OTHER_PHOTO,
  });
  await show();
  await checkAgain("me.jpg");
  expect(await within(itemOf("me.jpg")).findByText("No longer used for the video")).toBeTruthy();
  expect(within(itemOf("me.jpg")).getByText("Looks good · score 40 of 100")).toBeTruthy();
  expect(screen.getByRole("img", { name: "old.jpg" })).toBeTruthy();
});

test("a recording that no longer passes leaves the voice sample", async () => {
  server({ checks: { [SOUND]: upload(SOUND, "sounds", "story.wav", ["Too much noise."]) } });
  await show();
  await checkAgain("story.wav");
  expect(
    await within(itemOf("story.wav")).findByText("No longer in the voice sample"),
  ).toBeTruthy();
  expect(within(itemOf("story.wav")).getByText("Too much noise.")).toBeTruthy();
  expect(screen.queryByText(/No recording is in use yet/)).toBeNull();
  expect(screen.getByText(/Add, remove or choose photos and recordings in/)).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith("story.wav is no longer in use");
});

test("says so when what is in use can't be read again after a check", async () => {
  const fetchMock = server({ checks: { [SOUND]: upload(SOUND, "sounds", "story.wav", []) } });
  await show();
  const plain = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url, init) =>
    url === "/api/uploads/sounds" ? new Response("", { status: 500 }) : plain(url, init),
  );
  await checkAgain("story.wav");
  expect(
    await screen.findByText("Could not load them. Reload the page to try again."),
  ).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith(
    "Could not read the photos and recordings in use again",
    expect.any(Error),
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

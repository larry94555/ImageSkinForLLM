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

import type { PrepareStatus, Turn, Upload, VoiceSample } from "./api";
import { App } from "./App";
import {
  CANT_ANSWER,
  ClipPlayer,
  type Idle,
  Stage,
  type ClipTime,
  ClipTimes,
  clipWaits,
  countMatches,
  duration,
  latestExchange,
  loadSound,
  minutes,
  splitMatches,
} from "./pages";

const IDLE: PrepareStatus = {
  state: "idle",
  photo_id: null,
  percent: 0,
  steps: null,
  error: null,
  started_at: null,
  finished_at: null,
};

function serverWithConsent(agreed: boolean, postOk = true) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.startsWith("/api/uploads/")) return Response.json([]);
    if (url === "/api/prepare") return Response.json(IDLE);
    if (init?.method === "POST") {
      return postOk
        ? Response.json({ agreed: true, agreed_at: "2026-10-06T20:00:00+00:00" })
        : new Response("", { status: 500 });
    }
    return Response.json({ agreed, agreed_at: agreed ? "2026-10-06T20:00:00+00:00" : null });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// The server's saved settings say to show the timing metrics (R41a); every other request goes to
// the server the test set up.
function showMetrics() {
  const server = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) =>
      url === "/api/settings" ? Response.json({ show_metrics: true }) : server(url, init),
    ),
  );
}

async function openAt(hash: string) {
  window.location.hash = hash;
  render(<App />);
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("setup without consent goes to the consent page", async () => {
  serverWithConsent(false);
  await openAt("#/setup");
  expect(await screen.findByText("Before you start")).toBeTruthy();
  await waitFor(() => expect(window.location.hash).toBe("#/consent"));
  expect((screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement).disabled).toBe(
    true,
  );
});

test("ticking the box and continuing saves consent and opens setup", async () => {
  const fetchMock = serverWithConsent(false);
  await openAt("#/consent");
  fireEvent.click(await screen.findByRole("checkbox"));
  const button = screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement;
  expect(button.disabled).toBe(false);
  await act(async () => {
    fireEvent.click(button);
  });
  expect(await screen.findByText("Thank you, consent is confirmed.")).toBeTruthy();
  expect(window.location.hash).toBe("#/setup");
  expect(fetchMock).toHaveBeenCalledWith("/api/consent", expect.objectContaining({ method: "POST" }));
});

test("a failed save shows a message and lets the user try again", async () => {
  serverWithConsent(false, false);
  await openAt("#/consent");
  fireEvent.click(await screen.findByRole("checkbox"));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  });
  expect(await screen.findByText("Could not save your answer. Please try again.")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement).disabled).toBe(
    false,
  );
});

test("with consent, setup opens and the nav marks it", async () => {
  serverWithConsent(true);
  await openAt("#/setup");
  expect(await screen.findByText("Thank you, consent is confirmed.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Setup" }).className).toBe("current");
});

test("setup links to the recording guide, which keeps setup marked in the nav", async () => {
  serverWithConsent(true);
  await openAt("#/setup");
  const link = await screen.findByRole("link", { name: "recording guide" });
  expect(link.getAttribute("href")).toBe("#/guide");
  cleanup();
  await openAt("#/guide");
  expect(await screen.findByRole("heading", { name: "Before you begin" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Setup" }).className).toBe("current");
});

test("unknown pages say so", async () => {
  serverWithConsent(true);
  await openAt("#/nowhere");
  expect(await screen.findByText("Page not found")).toBeTruthy();
});

test("if the server can't be reached, setup stays blocked", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 503 })));
  await openAt("#/setup");
  expect(await screen.findByText("Before you start")).toBeTruthy();
});


// --- Upload screen (R7) ---

const PHOTO: Upload = {
  id: "a".repeat(32),
  kind: "photos",
  name: "front.jpg",
  format: "jpg",
  size: 1000,
  uploaded_at: "2026-10-07T00:00:00+00:00",
  seconds: null,
  problems: [],
  score: 90,
  speech: null,
};
const SOUND: Upload = {
  ...PHOTO,
  id: "b".repeat(32),
  kind: "sounds",
  name: "voice1.m4a",
  format: "m4a",
  seconds: 95.4,
  problems: null,
  score: null,
};

const NO_VOICE: VoiceSample = {
  recordings: 0,
  seconds: 0,
  speech: 0,
  problem: "No recording has passed the checks yet.",
};

// A fake server with consent given and these uploads stored. POSTs answer with `posted` in turn.
// The first photo is the one the app picks for the video.
function uploadServer(stored: Upload[], posted: Response[] = [], voice = NO_VOICE) {
  let choice = { id: stored.find((u) => u.kind === "photos")?.id ?? null, chosen_by: "app" };
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/uploads/photos/chosen") {
      if (init?.method === "PUT") {
        const { id } = JSON.parse(init.body as string) as { id: string };
        if (id === "f".repeat(32)) return Response.json({ detail: "No such photo." }, { status: 404 });
        choice = { id, chosen_by: "you" };
      }
      return Response.json(choice);
    }
    if (url === "/api/voice-sample") return Response.json(voice);
    if (url === "/api/prepare") return Response.json(IDLE);
    const kind = url.split("/")[3];
    if (init?.method === "POST") return posted.shift() ?? new Response("", { status: 500 });
    if (init?.method === "DELETE") return Response.json({ removed: true });
    return Response.json(stored.filter((u) => u.kind === kind));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function chooseFiles(label: string, files: File[]) {
  const input = screen.getByText(label).querySelector("input") as HTMLInputElement;
  Object.defineProperty(input, "files", { value: files, configurable: true });
  fireEvent.change(input);
}

test("setup lists stored photos and recordings so they can be viewed and played", async () => {
  uploadServer([PHOTO, SOUND]);
  await openAt("#/setup");
  const img = (await screen.findByAltText("front.jpg")) as HTMLImageElement;
  expect(img.getAttribute("src")).toBe(`/api/uploads/photos/${PHOTO.id}`);
  expect(await screen.findByText("voice1.m4a (1:35)")).toBeTruthy();
  const audio = document.querySelector("audio") as HTMLAudioElement;
  expect(audio.getAttribute("src")).toBe(`/api/uploads/sounds/${SOUND.id}`);
  expect(audio.controls).toBe(true);
});

test("each photo shows what the photo checks found", async () => {
  const small =
    "Your face is too small. Move closer to the camera, or crop the photo around your face.";
  const turned = "Your face is turned away. Look straight at the camera.";
  uploadServer([
    PHOTO,
    { ...PHOTO, id: "c".repeat(32), name: "side.jpg", problems: [small, turned] },
    SOUND,
  ]);
  await openAt("#/setup");
  expect(await screen.findByText("Looks good · score 90 of 100")).toBeTruthy();
  const side = (await screen.findByAltText("side.jpg")).closest("li") as HTMLElement;
  const shown = Array.from(side.querySelectorAll("li.error")).map((li) => li.textContent);
  expect(shown).toEqual([small, turned]);
  // Recordings aren't face-checked.
  const sound = (await screen.findByText("voice1.m4a (1:35)")).closest("li") as HTMLElement;
  expect(sound.textContent).not.toContain("Looks good");
  expect(sound.textContent).not.toContain("Use this photo");
});

// --- Best photo (R9) ---

test("the best photo is highlighted and another good photo can be chosen instead", async () => {
  const second = { ...PHOTO, id: "c".repeat(32), name: "second.jpg", score: 80 };
  const blurry = { ...PHOTO, id: "d".repeat(32), name: "blurry.jpg", problems: ["Blurry."] };
  const fetchMock = uploadServer([PHOTO, second, blurry]);
  await openAt("#/setup");
  const best = (await screen.findByAltText("front.jpg")).closest("li") as HTMLElement;
  await waitFor(() => expect(best.className).toBe("chosen"));
  expect(best.textContent).toContain("Used for the video (best score)");
  expect(best.textContent).not.toContain("Use this photo");
  const other = (await screen.findByAltText("second.jpg")).closest("li") as HTMLElement;
  // A photo that failed a check can't be chosen.
  const failed = (await screen.findByAltText("blurry.jpg")).closest("li") as HTMLElement;
  expect(failed.textContent).not.toContain("Use this photo");

  await act(async () => {
    fireEvent.click(within(other).getByRole("button", { name: "Use this photo" }));
  });
  await waitFor(() => expect(other.className).toBe("chosen"));
  expect(other.textContent).toContain("Used for the video (your choice)");
  expect(best.className).toBe("");
  expect(within(best).getByRole("button", { name: "Use this photo" })).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith("/api/uploads/photos/chosen", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: second.id }),
  });
});

test("a slow first read of the choice can't undo the user's click", async () => {
  const second = { ...PHOTO, id: "c".repeat(32), name: "second.jpg", score: 80 };
  let answerFirstRead: () => void = () => {};
  const firstRead = new Promise<void>((resolve) => {
    answerFirstRead = resolve;
  });
  let reads = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
      if (url === "/api/uploads/photos/chosen") {
        if (init?.method === "PUT") return Response.json({ id: second.id, chosen_by: "you" });
        if (++reads === 1) await firstRead; // answers with the choice from before the click
        return Response.json({ id: PHOTO.id, chosen_by: "app" });
      }
      return Response.json(url === "/api/uploads/photos" ? [PHOTO, second] : []);
    }),
  );
  await openAt("#/setup");
  const other = (await screen.findByAltText("second.jpg")).closest("li") as HTMLElement;
  await act(async () => {
    fireEvent.click(within(other).getByRole("button", { name: "Use this photo" }));
  });
  await waitFor(() => expect(other.className).toBe("chosen"));
  await act(async () => {
    answerFirstRead();
    await new Promise((resolve) => setTimeout(resolve, 10)); // let the old answer arrive
  });
  expect(reads).toBe(1);
  expect(other.className).toBe("chosen");
  expect(other.textContent).toContain("Used for the video (your choice)");
});

test("an older read of the choice answering last doesn't replace a newer one", async () => {
  const second = { ...PHOTO, id: "c".repeat(32), name: "second.jpg", score: 95 };
  let answerFirstRead: () => void = () => {};
  const firstRead = new Promise<void>((resolve) => {
    answerFirstRead = resolve;
  });
  let reads = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
      if (url === "/api/uploads/photos/chosen") {
        if (++reads === 1) {
          await firstRead; // from before the better photo arrived
          return Response.json({ id: PHOTO.id, chosen_by: "app" });
        }
        return Response.json({ id: second.id, chosen_by: "app" });
      }
      if (init?.method === "POST") return Response.json(second);
      return Response.json(url === "/api/uploads/photos" ? [PHOTO] : []);
    }),
  );
  await openAt("#/setup");
  await screen.findByAltText("front.jpg");
  await act(async () => {
    chooseFiles("Add photos", [new File(["x"], "second.jpg")]); // a better photo: read again
  });
  const newer = (await screen.findByAltText("second.jpg")).closest("li") as HTMLElement;
  await waitFor(() => expect(newer.className).toBe("chosen"));
  await act(async () => {
    answerFirstRead();
    await new Promise((resolve) => setTimeout(resolve, 10)); // let the old answer arrive
  });
  expect(reads).toBe(2);
  expect(newer.className).toBe("chosen");
});

test("a read sent while the choice is being saved can't undo it", async () => {
  const second = { ...PHOTO, id: "c".repeat(32), name: "second.jpg", score: 80 };
  const third = { ...PHOTO, id: "e".repeat(32), name: "third.jpg", score: 70 };
  let finishSave: () => void = () => {};
  const saving = new Promise<void>((resolve) => {
    finishSave = resolve;
  });
  let answerSecondRead: () => void = () => {};
  const secondRead = new Promise<void>((resolve) => {
    answerSecondRead = resolve;
  });
  let saved = { id: PHOTO.id, chosen_by: "app" };
  let reads = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
      if (url === "/api/uploads/photos/chosen") {
        if (init?.method === "PUT") {
          await saving;
          saved = { id: second.id, chosen_by: "you" };
          return Response.json(saved);
        }
        if (++reads === 2) {
          const before = saved; // read by the server before the save landed
          await secondRead;
          return Response.json(before);
        }
        return Response.json(saved);
      }
      if (init?.method === "POST") return Response.json(third);
      return Response.json(url === "/api/uploads/photos" ? [PHOTO, second] : []);
    }),
  );
  await openAt("#/setup");
  const other = (await screen.findByAltText("second.jpg")).closest("li") as HTMLElement;
  await screen.findByText("Used for the video (best score)");
  await act(async () => {
    fireEvent.click(within(other).getByRole("button", { name: "Use this photo" }));
  });
  await act(async () => {
    chooseFiles("Add photos", [new File(["x"], "third.jpg")]); // reads the choice again
  });
  await waitFor(() => expect(reads).toBe(2));
  await act(async () => {
    finishSave();
  });
  await waitFor(() => expect(other.className).toBe("chosen"));
  await act(async () => {
    answerSecondRead();
    await new Promise((resolve) => setTimeout(resolve, 10)); // let the old answer arrive
  });
  expect(other.className).toBe("chosen");
  expect(other.textContent).toContain("Used for the video (your choice)");
});

test("removing the photo being chosen falls back to the best one", async () => {
  const second = { ...PHOTO, id: "c".repeat(32), name: "second.jpg", score: 80 };
  let finishSave: () => void = () => {};
  const saving = new Promise<void>((resolve) => {
    finishSave = resolve;
  });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
      if (url === "/api/uploads/photos/chosen") {
        if (init?.method === "PUT") {
          await saving; // the server saved it before the photo was removed
          return Response.json({ id: second.id, chosen_by: "you" });
        }
        return Response.json({ id: PHOTO.id, chosen_by: "app" }); // falls back to the best
      }
      if (init?.method === "DELETE") return Response.json({ removed: true });
      return Response.json(url === "/api/uploads/photos" ? [PHOTO, second] : []);
    }),
  );
  await openAt("#/setup");
  const best = (await screen.findByAltText("front.jpg")).closest("li") as HTMLElement;
  const other = (await screen.findByAltText("second.jpg")).closest("li") as HTMLElement;
  await waitFor(() => expect(best.className).toBe("chosen"));
  await act(async () => {
    fireEvent.click(within(other).getByRole("button", { name: "Use this photo" }));
  });
  await act(async () => {
    fireEvent.click(within(other).getByRole("button", { name: "Remove" }));
  });
  await act(async () => {
    finishSave();
    await new Promise((resolve) => setTimeout(resolve, 10));
  });
  expect(screen.queryByAltText("second.jpg")).toBeNull();
  await waitFor(() => expect(best.className).toBe("chosen"));
  expect(best.textContent).toContain("Used for the video (best score)");
});

test("a refused choice says why", async () => {
  const gone = { ...PHOTO, id: "f".repeat(32), name: "gone.jpg" };
  uploadServer([PHOTO, gone]);
  await openAt("#/setup");
  const item = (await screen.findByAltText("gone.jpg")).closest("li") as HTMLElement;
  await act(async () => {
    fireEvent.click(within(item).getByRole("button", { name: "Use this photo" }));
  });
  expect(await screen.findByText("gone.jpg: No such photo.")).toBeTruthy();
});

test("the choice is asked again after a good photo is uploaded or the chosen one removed", async () => {
  const fetchMock = uploadServer([PHOTO], [Response.json({ ...PHOTO, id: "c".repeat(32) })]);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  await openAt("#/setup");
  await screen.findByText("Used for the video (best score)");
  const asked = () => fetchMock.mock.calls.filter(([url]) => url.endsWith("/chosen")).length;
  expect(asked()).toBe(1);
  await act(async () => {
    chooseFiles("Add photos", [new File(["x"], "new.jpg")]);
  });
  await waitFor(() => expect(asked()).toBe(2));
  const chosen = screen.getByText("Used for the video (best score)").closest("li") as HTMLElement;
  await act(async () => {
    fireEvent.click(within(chosen).getByRole("button", { name: "Remove" }));
  });
  await waitFor(() => expect(asked()).toBe(3));
});

test("photos uploaded before the checks are checked after the list shows", async () => {
  const turned = "Your face is turned away. Look straight at the camera.";
  const old = { ...PHOTO, id: "d".repeat(32), name: "old.jpg", problems: null };
  const next = { ...old, id: "e".repeat(32), name: "next.jpg" };
  let finishCheck: () => void = () => {};
  const checkPending = new Promise<void>((resolve) => {
    finishCheck = resolve;
  });
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url.endsWith("/check")) {
      await checkPending;
      const photo = [old, next].find((p) => url.includes(p.id));
      return Response.json({ ...photo, problems: [turned] });
    }
    return Response.json(url === "/api/uploads/photos" ? [old, next] : []);
  });
  vi.stubGlobal("fetch", fetchMock);
  await openAt("#/setup");
  expect(await screen.findByText("Checking photo…")).toBeTruthy();
  expect(screen.getByText("Waiting to check")).toBeTruthy();
  // Adding isn't held up by the check.
  const input = screen.getByText("Add photos").querySelector("input") as HTMLInputElement;
  expect(input.disabled).toBe(false);
  await act(async () => {
    finishCheck();
  });
  await waitFor(() => expect(screen.getAllByText(turned)).toHaveLength(2));
  expect(screen.queryByText("Checking photo…")).toBeNull();
  expect(screen.queryByText("Waiting to check")).toBeNull();
  expect(fetchMock).toHaveBeenCalledWith(`/api/uploads/photos/${old.id}/check`, {
    method: "POST",
  });
});

test("when the checks are off, old photos say not checked and are tried only once", async () => {
  const old = [1, 2].map((n) => ({ ...PHOTO, id: String(n).repeat(32), problems: null }));
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url.endsWith("/check")) return Response.json(old[0]);
    return Response.json(url === "/api/uploads/photos" ? old : []);
  });
  vi.stubGlobal("fetch", fetchMock);
  await openAt("#/setup");
  await waitFor(() => expect(screen.getAllByText("Not checked")).toHaveLength(2));
  const checks = fetchMock.mock.calls.filter(([url]) => url.endsWith("/check"));
  expect(checks).toHaveLength(1);
});

test("a photo that can't be checked is skipped and the next one is checked", async () => {
  const old = [1, 2].map((n) => ({ ...PHOTO, id: String(n).repeat(32), problems: null }));
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === `/api/uploads/photos/${old[0].id}/check`) return new Response("", { status: 404 });
    if (url.endsWith("/check")) return Response.json({ ...old[1], problems: [] });
    return Response.json(url === "/api/uploads/photos" ? old : []);
  });
  vi.stubGlobal("fetch", fetchMock);
  await openAt("#/setup");
  expect(await screen.findByText("Looks good · score 90 of 100")).toBeTruthy();
  expect(screen.getByText("Not checked")).toBeTruthy();
});

test("with nothing uploaded each section says so", async () => {
  uploadServer([]);
  await openAt("#/setup");
  await waitFor(() => expect(screen.getAllByText("None yet.")).toHaveLength(2));
});

test("choosing several photos uploads each and shows why one was refused", async () => {
  const fetchMock = uploadServer(
    [],
    [
      Response.json(PHOTO),
      Response.json({ detail: "This is not a JPG, PNG or HEIC photo." }, { status: 415 }),
    ],
  );
  await openAt("#/setup");
  await screen.findAllByText("None yet.");
  await act(async () => {
    chooseFiles("Add photos", [new File(["x"], "front.jpg"), new File(["y"], "notes.txt")]);
  });
  expect(await screen.findByAltText("front.jpg")).toBeTruthy();
  expect(
    await screen.findByText("notes.txt: This is not a JPG, PNG or HEIC photo."),
  ).toBeTruthy();
  const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts.map(([url]) => url)).toEqual(["/api/uploads/photos", "/api/uploads/photos"]);
  expect((posts[0][1]?.body as FormData).get("file")).toBeInstanceOf(File);
});

test("a refusal without a JSON reason still says something", async () => {
  uploadServer([], [new Response("bad gateway", { status: 502 })]);
  await openAt("#/setup");
  await screen.findAllByText("None yet.");
  await act(async () => {
    chooseFiles("Add recordings", [new File(["x"], "voice1.wav")]);
  });
  expect(await screen.findByText("voice1.wav: The server refused it (502).")).toBeTruthy();
});

test("remove asks first, then deletes the file", async () => {
  const fetchMock = uploadServer([PHOTO]);
  const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
  await openAt("#/setup");
  await screen.findByAltText("front.jpg");
  fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  expect(screen.queryByAltText("front.jpg")).toBeTruthy();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  });
  await waitFor(() => expect(screen.queryByAltText("front.jpg")).toBeNull());
  expect(confirm).toHaveBeenCalledWith("Remove front.jpg?");
  expect(fetchMock).toHaveBeenCalledWith(`/api/uploads/photos/${PHOTO.id}`, { method: "DELETE" });
});

test("a failed remove keeps the file and says so", async () => {
  uploadServer([PHOTO]);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  await openAt("#/setup");
  await screen.findByAltText("front.jpg");
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  });
  expect(await screen.findByText("front.jpg: Could not remove it. Please try again.")).toBeTruthy();
  expect(screen.getByAltText("front.jpg")).toBeTruthy();
});

test("if the list can't be loaded the page says so", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url === "/api/consent"
        ? Response.json({ agreed: true, agreed_at: null })
        : new Response("", { status: 500 }),
    ),
  );
  await openAt("#/setup");
  await waitFor(() =>
    expect(
      screen.getAllByText("Could not load the list. Reload the page to try again."),
    ).toHaveLength(2),
  );
});

test("minutes formats a recording's length", () => {
  expect(minutes(0)).toBe("0:00");
  expect(minutes(59.6)).toBe("1:00");
  expect(minutes(605)).toBe("10:05");
});

test("adding waits until the first list has loaded, so it can't hide a new upload", async () => {
  let finishList: (r: Response) => void = () => {};
  const listPending = new Promise<Response>((resolve) => {
    finishList = resolve;
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
      if (init?.method === "POST") return Response.json(PHOTO);
      return url === "/api/uploads/photos" ? listPending : Response.json([]);
    }),
  );
  await openAt("#/setup");
  const note = await screen.findByText("Loading your photos…");
  const photos = note.closest("section") as HTMLElement;
  const input = photos.querySelector("input") as HTMLInputElement;
  expect(input.disabled).toBe(true);
  expect(photos.querySelector("label")?.textContent).toBe("Loading…");
  await act(async () => {
    finishList(Response.json([]));
  });
  await waitFor(() => expect(input.disabled).toBe(false));
  expect(screen.queryByText("Loading your photos…")).toBeNull();
  await act(async () => {
    chooseFiles("Add photos", [new File(["x"], "front.jpg")]);
  });
  expect(await screen.findByAltText("front.jpg")).toBeTruthy();
});

test("if the list failed, adding still works", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
      if (init?.method === "POST") return Response.json(PHOTO);
      return new Response("", { status: 500 });
    }),
  );
  await openAt("#/setup");
  await screen.findAllByText("Could not load the list. Reload the page to try again.");
  await act(async () => {
    chooseFiles("Add photos", [new File(["x"], "front.jpg")]);
  });
  expect(await screen.findByAltText("front.jpg")).toBeTruthy();
});

// --- Sound checks and the voice sample (R10) ---

const NOISY =
  "There is too much background noise. Record in a quiet room, away from fans, open windows," +
  " music or a TV.";
const PASSED_SOUND: Upload = { ...SOUND, problems: [], speech: 70.2 };
const ONE_VOICE: VoiceSample = { recordings: 1, seconds: 95.4, speech: 70.2, problem: null };

test("each recording shows what the sound checks found, and the voice sample plays", async () => {
  const noisy = { ...SOUND, id: "c".repeat(32), name: "kitchen.m4a", problems: [NOISY] };
  uploadServer([PASSED_SOUND, noisy], [], ONE_VOICE);
  await openAt("#/setup");
  expect(await screen.findByText("Looks good · 1:10 of speech")).toBeTruthy();
  const failed = (await screen.findByText("kitchen.m4a (1:35)")).closest("li") as HTMLElement;
  expect(within(failed).getByText(NOISY).className).toBe("error");
  expect(await screen.findByText("Voice sample")).toBeTruthy();
  expect(
    screen.getByText("Made from the recording that passed the checks: 1:10 of speech."),
  ).toBeTruthy();
  expect(screen.getByText("Enough speech to make the voice.")).toBeTruthy();
  const players = Array.from(document.querySelectorAll("audio")).map((a) => a.getAttribute("src"));
  expect(players).toContain("/api/voice-sample/audio?v=0");
});

test("without enough speech the voice sample says what to add", async () => {
  const short = "The recordings that passed the checks have 20 seconds of speech.";
  uploadServer([PASSED_SOUND, { ...PASSED_SOUND, id: "c".repeat(32) }], [], {
    recordings: 2,
    seconds: 40,
    speech: 20,
    problem: short,
  });
  await openAt("#/setup");
  expect((await screen.findByText(short)).className).toBe("error");
  expect(screen.getByText(/Made from the 2 recordings that passed the checks, in order/)).toBeTruthy();
});

test("with no recording passed, there is nothing to play yet", async () => {
  uploadServer([]);
  await openAt("#/setup");
  expect((await screen.findByText(NO_VOICE.problem as string)).className).toBe("muted");
  expect(document.querySelector(".voice-sample audio")).toBeNull();
});

test("the voice sample is read again after a recording is added, checked or removed", async () => {
  const fetchMock = uploadServer(
    [SOUND],
    [Response.json(PASSED_SOUND), Response.json({ ...PASSED_SOUND, id: "c".repeat(32) })],
    ONE_VOICE,
  );
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const reads = () => fetchMock.mock.calls.filter(([url]) => url === "/api/voice-sample").length;
  await openAt("#/setup");
  // The stored recording predates the checks, so it is checked first, then the sample read.
  expect(await screen.findByText("Looks good · 1:10 of speech")).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith(`/api/uploads/sounds/${SOUND.id}/check`, {
    method: "POST",
  });
  await waitFor(() => expect(reads()).toBe(2));
  await act(async () => {
    chooseFiles("Add recordings", [new File(["x"], "voice2.m4a")]);
  });
  await waitFor(() => expect(reads()).toBe(3));
  expect(document.querySelector(".voice-sample audio")?.getAttribute("src")).toBe(
    "/api/voice-sample/audio?v=2",
  );
  await act(async () => {
    fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[0]);
  });
  await waitFor(() => expect(reads()).toBe(4));
});

test("an older read of the voice sample answering last is not shown", async () => {
  let answerFirstRead: () => void = () => {};
  const firstRead = new Promise<void>((resolve) => {
    answerFirstRead = resolve;
  });
  let reads = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
      if (url === "/api/voice-sample") {
        if (++reads === 1) {
          await firstRead; // from before the recording arrived
          return Response.json(NO_VOICE);
        }
        return Response.json(ONE_VOICE);
      }
      if (init?.method === "POST") return Response.json(PASSED_SOUND);
      return Response.json([]);
    }),
  );
  await openAt("#/setup");
  await screen.findAllByText("None yet.");
  await act(async () => {
    chooseFiles("Add recordings", [new File(["x"], "voice1.m4a")]);
  });
  expect(await screen.findByText("Enough speech to make the voice.")).toBeTruthy();
  await act(async () => {
    answerFirstRead();
    await new Promise((resolve) => setTimeout(resolve, 10)); // let the old answer arrive
  });
  expect(reads).toBe(2);
  expect(screen.getByText("Enough speech to make the voice.")).toBeTruthy();
});

// --- Prepare (R12) ---

const STEPS = [
  { key: "voice", label: "Get the voice ready", done: 1, total: 1, seconds: 4.2, left_s: null },
  { key: "models", label: "Load the face model", done: 1, total: 1, seconds: 31, left_s: null },
  { key: "shapes", label: "Render the mouth shapes", done: 10, total: 10, seconds: null, left_s: null },
  { key: "loop", label: "Render the idle video", done: 52, total: 200, seconds: null, left_s: 725 },
  { key: "align", label: "Line up the mouth", done: 0, total: 1, seconds: null, left_s: null },
];
const RUNNING: PrepareStatus = {
  ...IDLE,
  state: "running",
  photo_id: PHOTO.id,
  percent: 31,
  steps: STEPS,
  started_at: "2026-10-07T09:00:00+00:00",
};
const DONE: PrepareStatus = {
  ...RUNNING,
  state: "done",
  percent: 100,
  steps: STEPS.map((s) => ({
    ...s,
    done: s.total,
    seconds: s.key === "loop" ? 1034 : s.seconds,
    left_s: null,
  })),
  finished_at: "2026-10-07T09:20:00+00:00",
};

// A fake server with consent given, nothing uploaded, and the prepare job answering with each
// of `reads` in turn (the last one repeats); POST /api/prepare answers with `started`.
function prepareServer(reads: (PrepareStatus | Response)[], started?: Response) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/uploads/photos/chosen") return Response.json({ id: null, chosen_by: "app" });
    if (url === "/api/voice-sample") return Response.json(NO_VOICE);
    if (url === "/api/prepare") {
      if (init?.method === "POST") return started ?? Response.json(RUNNING);
      const next = reads.length > 1 ? reads.shift() : reads[0];
      return next instanceof Response ? next : Response.json(next);
    }
    return Response.json([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

test("prepare starts the job and shows each step's progress until it is ready", async () => {
  const fetchMock = prepareServer([IDLE, RUNNING, DONE]);
  showMetrics();
  await openAt("#/setup");
  fireEvent.click(await screen.findByRole("button", { name: "Prepare" }));
  expect(await screen.findByText("Preparing… 31% done")).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith("/api/prepare", { method: "POST" });
  const bar = screen.getByRole("progressbar", { name: "Preparing" }) as HTMLProgressElement;
  expect(bar.value).toBe(31);
  expect(screen.getByText("Done in 31 s")).toBeTruthy();
  expect(screen.getByText("52 of 200 · about 12 min left")).toBeTruthy();
  expect(screen.getByText("Waiting")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /Prepare/ })).toBeNull(); // no second start

  // The page asks again every second while it runs.
  expect(
    await screen.findByText("Ready. Here is the sample video:", {}, { timeout: 3000 }),
  ).toBeTruthy();
  expect(screen.getByText("Done in 17 min")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Prepare again" })).toBeTruthy();
  // The sample video plays from the server, fetched afresh each time it is prepared again.
  const video = screen.getByLabelText("Sample video") as HTMLVideoElement;
  expect(video.getAttribute("src")).toBe(
    "/api/prepare/clips/sample?v=2026-10-07T09%3A20%3A00%2B00%3A00",
  );
  expect(video.controls).toBe(true);
});

test("a job already running when the page opens is shown and followed", async () => {
  prepareServer([RUNNING]);
  await openAt("#/setup");
  expect(await screen.findByText("Preparing… 31% done")).toBeTruthy();
  expect(screen.queryByLabelText("Sample video")).toBeNull(); // not until it is done
});

test("prepare says what is missing when it can't start", async () => {
  prepareServer(
    [IDLE],
    Response.json({ detail: "Add a photo that passes the checks first." }, { status: 409 }),
  );
  await openAt("#/setup");
  fireEvent.click(await screen.findByRole("button", { name: "Prepare" }));
  expect(await screen.findByText("Add a photo that passes the checks first.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Prepare" })).toBeTruthy();
});

test("a failed job says why, marks where it stopped and can be tried again", async () => {
  const steps = STEPS.map((s) => (s.key === "loop" ? { ...s, left_s: null } : s));
  prepareServer([{ ...RUNNING, state: "failed", steps, error: "ffmpeg was not found." }]);
  await openAt("#/setup");
  expect(await screen.findByText("ffmpeg was not found.")).toBeTruthy();
  expect(screen.getByText("Stopped")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
});

test("if the prepare status can't be read the page says so", async () => {
  prepareServer([new Response("", { status: 500 })]);
  await openAt("#/setup");
  expect(
    await screen.findByText(
      "Could not read how far preparing has got. Reload the page to try again.",
    ),
  ).toBeTruthy();
});

test("duration says seconds or minutes", () => {
  expect(duration(4.2)).toBe("4 s");
  expect(duration(89)).toBe("89 s");
  expect(duration(1034)).toBe("17 min");
});

test("Prepare is asked again after the chosen photo or the recordings change", async () => {
  const other: Upload = { ...PHOTO, id: "c".repeat(32), name: "side.jpg", score: 80 };
  const sound: Upload = { ...SOUND, problems: [], speech: 40 };
  let choice = { id: PHOTO.id, chosen_by: "app" };
  let sounds = [sound];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/uploads/photos/chosen") {
      if (init?.method === "PUT") {
        const { id } = JSON.parse(init.body as string) as { id: string };
        choice = { id, chosen_by: "you" };
      }
      return Response.json(choice);
    }
    if (url === "/api/voice-sample") return Response.json(NO_VOICE);
    // The server reports the finished job only while its photo and enough speech are there.
    if (url === "/api/prepare") {
      return Response.json(choice.id === PHOTO.id && sounds.length > 0 ? DONE : IDLE);
    }
    if (url === "/api/uploads/photos") return Response.json([PHOTO, other]);
    if (url === "/api/uploads/sounds") return Response.json(sounds);
    if (init?.method === "DELETE") {
      sounds = [];
      return Response.json({ removed: true });
    }
    return Response.json([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  await openAt("#/setup");
  expect(await screen.findByText("Ready. Here is the sample video:")).toBeTruthy();

  fireEvent.click(await screen.findByRole("button", { name: "Use this photo" }));
  expect(await screen.findByRole("button", { name: "Prepare" })).toBeTruthy();
  expect(screen.queryByText("Ready. Here is the sample video:")).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "Use this photo" })); // back to the first
  expect(await screen.findByText("Ready. Here is the sample video:")).toBeTruthy();

  const recording = (await screen.findByText(/voice1\.m4a/)).closest("li") as HTMLElement;
  fireEvent.click(within(recording).getByRole("button", { name: "Remove" }));
  expect(await screen.findByRole("button", { name: "Prepare" })).toBeTruthy();
});

// --- Accent (R26) ---

// A fake server with consent given, nothing uploaded, the accent `saved`, and the prepare job
// answering with each of `reads` in turn (the last one repeats). PUT /api/accent answers with
// `put` when given, and otherwise saves the accent.
function accentServer(
  saved: { accent: string; available: boolean } | Response,
  reads: PrepareStatus[] = [IDLE],
  put?: Response,
) {
  let choice = saved;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/uploads/photos/chosen") return Response.json({ id: null, chosen_by: "app" });
    if (url === "/api/voice-sample") return Response.json(NO_VOICE);
    if (url === "/api/accent") {
      if (init?.method === "PUT") {
        if (put) return put;
        const { accent } = JSON.parse(init.body as string) as { accent: string };
        choice = { accent, available: true };
      }
      return choice instanceof Response ? choice : Response.json(choice);
    }
    if (url === "/api/prepare") return Response.json(reads.length > 1 ? reads.shift() : reads[0]);
    return Response.json([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function accentOption(name: RegExp | string) {
  return screen.getByRole("radio", { name }) as HTMLInputElement;
}

test("the accent starts as the person's own and another can be chosen", async () => {
  const fetchMock = accentServer({ accent: "own", available: true }, [DONE, RUNNING]);
  await openAt("#/setup");
  expect(await screen.findByText("Ready. Here is the sample video:")).toBeTruthy();
  await waitFor(() => expect(accentOption(/Their own accent/).checked).toBe(true));
  expect(accentOption("British").checked).toBe(false);
  expect(screen.queryByText(/needs the person's own voice installed/)).toBeNull();

  await act(async () => {
    fireEvent.click(accentOption("British"));
  });
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/accent",
    expect.objectContaining({ method: "PUT", body: JSON.stringify({ accent: "british" }) }),
  );
  await waitFor(() => expect(accentOption("British").checked).toBe(true));
  // The server makes the sample again in the new accent; the page shows it running, and the
  // accent can't change again until it has finished.
  expect(await screen.findByText("Preparing… 31% done")).toBeTruthy();
  expect(await screen.findByText("You can change the accent once Prepare has finished.")).toBeTruthy();
  expect(accentOption("American").matches(":disabled")).toBe(true);
});

test("without the person's own voice installed, the accent says it can't change yet", async () => {
  accentServer({ accent: "own", available: false });
  await openAt("#/setup");
  expect(await screen.findByText(/needs the person's own voice installed/)).toBeTruthy();
  expect(accentOption("British").matches(":disabled")).toBe(true);
  expect(accentOption("American").matches(":disabled")).toBe(true);
  expect(accentOption(/Their own accent/).matches(":disabled")).toBe(false);
});

test("an accent that can't be saved says why and keeps the old one", async () => {
  accentServer(
    { accent: "american", available: true },
    [IDLE],
    Response.json({ detail: "Input should be 'own', 'american' or 'british'" }, { status: 422 }),
  );
  await openAt("#/setup");
  await waitFor(() => expect(accentOption("American").checked).toBe(true));
  await act(async () => {
    fireEvent.click(accentOption("British"));
  });
  expect(await screen.findByText(/Could not save the accent: Input should be/)).toBeTruthy();
  expect(accentOption("American").checked).toBe(true);
});

test("if the accent can't be loaded the page says so", async () => {
  accentServer(new Response("", { status: 500 }));
  await openAt("#/setup");
  expect(
    await screen.findByText("Could not load the accent. Reload the page to try again."),
  ).toBeTruthy();
  expect(accentOption("British").matches(":disabled")).toBe(true);
});

// --- Review (R14) ---

// A fake server with a sample ready and the review saved as `accepted`; POST /api/review
// answers with `answer` when given, or saves the decision.
function reviewServer(accepted: boolean, answer?: Response) {
  let current = accepted;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/uploads/photos/chosen") return Response.json({ id: null, chosen_by: "app" });
    if (url === "/api/voice-sample") return Response.json(NO_VOICE);
    if (url === "/api/accent") return Response.json({ accent: "own", available: true });
    if (url === "/api/prepare") return Response.json(DONE);
    if (url === "/api/chat") return Response.json({ turns: [] });
    if (url === "/api/review") {
      if (init?.method === "POST") {
        if (answer) return answer;
        const { decision } = JSON.parse(init.body as string) as { decision: string };
        current = decision === "accept";
      }
      return Response.json({ accepted: current, accepted_at: current ? "2026-10-09T15:00:00" : null });
    }
    return Response.json([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

test("accepting the sample video unlocks the chat", async () => {
  const fetchMock = reviewServer(false);
  await openAt("#/setup");
  expect(await screen.findByText(/Accept it to unlock the chat/)).toBeTruthy();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
  });
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/review",
    expect.objectContaining({ method: "POST", body: JSON.stringify({ decision: "accept" }) }),
  );
  await waitFor(() => expect(window.location.hash).toBe("#/chat"));
  expect(await screen.findByText("Ask a question to start the conversation.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Chat" }).className).toBe("current");
});

test("the chat is locked until a sample is accepted", async () => {
  reviewServer(false);
  await openAt("#/chat");
  expect(await screen.findByText(/The chat is locked until you accept a sample video/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Go to setup" }).getAttribute("href")).toBe("#/setup");
});

test("if the review can't be read, the chat stays locked", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) =>
    url === "/api/consent"
      ? Response.json({ agreed: true, agreed_at: null })
      : new Response("", { status: 500 }),
  ));
  await openAt("#/chat");
  expect(await screen.findByText(/The chat is locked/)).toBeTruthy();
});

test.each([
  ["Reject image", "reject-image", "photos", /You rejected the image/],
  ["Reject voice", "reject-voice", "sounds", /You rejected the voice/],
  ["Change accent", "change-accent", "accent", /Choose another accent/],
])("%s goes back to that part of setup", async (label, decision, section, notice) => {
  const fetchMock = reviewServer(true);
  const scrolled = vi.fn();
  Element.prototype.scrollIntoView = scrolled;
  await openAt("#/setup");
  expect(await screen.findByText("You accepted this sample.")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Accept" })).toBeNull(); // already accepted
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: label }));
  });
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/review",
    expect.objectContaining({ body: JSON.stringify({ decision }) }),
  );
  const target = document.getElementById(section) as HTMLElement;
  expect(await within(target).findByText(notice)).toBeTruthy();
  await waitFor(() => expect(scrolled).toHaveBeenCalled());
  expect(scrolled.mock.contexts[0]).toBe(target);
  // No longer accepted: Accept is offered again.
  expect(await screen.findByRole("button", { name: "Accept" })).toBeTruthy();
  expect(window.location.hash).toBe("#/setup");
});

test("a choice that can't be saved says why", async () => {
  reviewServer(
    false,
    Response.json({ detail: "There is no sample video to accept yet." }, { status: 409 }),
  );
  await openAt("#/setup");
  const accept = await screen.findByRole("button", { name: "Accept" });
  await act(async () => {
    fireEvent.click(accept);
  });
  expect(
    await screen.findByText("Could not save your choice: There is no sample video to accept yet."),
  ).toBeTruthy();
  expect(window.location.hash).toBe("#/setup");
});

// --- Chat (R15) ---

// A fake server with the sample accepted, the conversation `turns`, POST /api/chat answering
// with `answer`, POST /api/chat/video with `speak` (R17; by default nothing to say aloud) and
// GET /api/chat/clips/<reply id> with `clips` (R22; by default none: the reply wasn't streamed).
type Answer = () => Response | Promise<Response>;
function chatServer(
  turns: Turn[],
  answer: Answer,
  speak: Answer = () => Response.json({ video: null }),
  clips: Answer = () => Response.json({ detail: "No clips" }, { status: 404 }),
) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/review") return Response.json({ accepted: true, accepted_at: null });
    if (url === "/api/chat") {
      return init?.method === "POST" ? answer() : Response.json({ turns });
    }
    if (url === "/api/chat/video") return speak();
    if (url.endsWith("/stop")) return Response.json({ stopped: true }); // R19
    if (url.startsWith("/api/chat/clips/")) return clips();
    return Response.json([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// A response the test sends when it chooses, and a function to send it.
function later(): [Answer, (r: Response) => void] {
  let send: (r: Response) => void = () => {};
  const pending = new Promise<Response>((resolve) => (send = resolve));
  return [() => pending, (r) => send(r)];
}

function promptBox() {
  return screen.getByRole("textbox", { name: "Your message" }) as HTMLTextAreaElement;
}

test("the chat shows the conversation so far", async () => {
  chatServer(
    [
      { role: "user", content: "My name is Larry." },
      { role: "assistant", content: "Nice to meet you, Larry!" },
    ],
    () => Response.json({}),
  );
  await openAt("#/chat");
  expect(await screen.findByText("Nice to meet you, Larry!")).toBeTruthy();
  expect(screen.getByText("My name is Larry.").className).toBe("user");
  expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
});

test("sending a prompt shows it and then the reply", async () => {
  const [answer, reply] = later();
  const fetchMock = chatServer([], answer);
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "  Hello!  " } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByText("Hello!")).toBeTruthy();
  expect(screen.getByText("Thinking…")).toBeTruthy();
  expect(promptBox().value).toBe("");
  const sent = fetchMock.mock.calls.find(([url, init]) => url === "/api/chat" && init?.method);
  const body = JSON.parse(sent![1]!.body as string) as { prompt: string; reply_id: string };
  expect(body.prompt).toBe("Hello!");
  expect(body.reply_id).toMatch(/^[0-9a-f]{32}$/);
  await act(async () => {
    reply(Response.json({ role: "assistant", content: "Hi there, how are you?" }));
  });
  expect(await screen.findByText("Hi there, how are you?")).toBeTruthy();
  expect(screen.queryByText("Thinking…")).toBeNull();
});

test("Enter sends and Shift+Enter does not", async () => {
  const fetchMock = chatServer([], () =>
    Response.json({ role: "assistant", content: "Got it." }),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Line one" } });
  fireEvent.keyDown(promptBox(), { key: "Enter", shiftKey: true });
  expect(fetchMock).not.toHaveBeenCalledWith("/api/chat", expect.anything());
  await act(async () => {
    fireEvent.keyDown(promptBox(), { key: "Enter" });
  });
  expect(await screen.findByText("Got it.")).toBeTruthy();
});

test("when the LLM fails, a short apology shows and the prompt goes back in the box", async () => {
  chatServer([], () =>
    Response.json(
      { detail: "Could not reach the LLM at http://127.0.0.1:8080/v1. Is llama-server running?" },
      { status: 502 },
    ),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Hello?" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  // R41d: no addresses or program names for the student; the details go to the console.
  expect((await screen.findByRole("alert")).textContent).toBe(CANT_ANSWER);
  expect(screen.queryByText(/llama-server|127\.0\.0\.1/)).toBeNull();
  expect(promptBox().value).toBe("Hello?");
  expect(screen.queryByText("Hello?", { selector: "li" })).toBeNull();
});

test("one status line says what is happening until the person speaks", async () => {
  const [answer, reply] = later();
  const made = clipsMade(["/api/chat/clips/x/1"], false);
  chatServer([], answer, undefined, () => Response.json(made));
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Tell me a story" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText("Thinking…");
  expect(screen.queryByText("Getting ready to say it…")).toBeNull(); // one line, not two
  await act(async () => {
    reply(Response.json({ role: "assistant", content: "Once upon a time.", streamed: true }));
  });
  await screen.findByText("Getting ready to say it…");
  expect(screen.queryByText("Thinking…")).toBeNull();
  await waitFor(() => expect(shownVideo()).not.toBeNull());
  fireEvent.playing(shownVideo());
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
});

test("a prompt the server can't use says why in its own words", async () => {
  chatServer([], () =>
    Response.json({ detail: "That message is too long. Shorten it or split it in two." }, { status: 400 }),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "A very long question" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  expect((await screen.findByRole("alert")).textContent).toBe(
    "That message is too long. Shorten it or split it in two.",
  );
});

test("when the server can't be reached at all, the same apology shows", async () => {
  chatServer([], () => {
    throw new TypeError("Failed to fetch");
  });
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Hello?" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  expect((await screen.findByRole("alert")).textContent).toBe(CANT_ANSWER);
});

// --- Video stays the focus: history closed by default (R18a) ---

test("only the latest exchange shows; the history is closed until opened", async () => {
  const info = vi.spyOn(console, "info").mockImplementation(() => {});
  chatServer(
    [
      { role: "user", content: "My name is Larry." },
      { role: "assistant", content: "Nice to meet you, Larry!" },
      { role: "user", content: "What is my name?" },
      { role: "assistant", content: "Your name is Larry." },
    ],
    () => Response.json({}),
  );
  await openAt("#/chat");
  expect(await screen.findByText("Your name is Larry.")).toBeTruthy();
  expect(screen.getByText("What is my name?")).toBeTruthy();
  expect(screen.queryByText("My name is Larry.")).toBeNull();
  expect(document.querySelector(".history-box")).toBeNull();

  const show = screen.getByRole("button", { name: "Show history" });
  expect(show.tagName).toBe("BUTTON"); // a real button: Enter and Space both toggle it
  expect(show.getAttribute("type")).toBe("button");
  expect(show.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(show);
  const box = screen.getByLabelText("Conversation history");
  const items = within(box).getAllByRole("listitem").map((li) => li.textContent);
  expect(items).toEqual([
    "YouMy name is Larry.",
    "ReplyNice to meet you, Larry!",
    "YouWhat is my name?",
    "ReplyYour name is Larry.",
  ]);
  expect(info).toHaveBeenCalledWith("Chat history shown (4 turns)");

  fireEvent.click(screen.getByRole("button", { name: "Hide history" }));
  expect(document.querySelector(".history-box")).toBeNull();
  expect(info).toHaveBeenCalledWith("Chat history hidden (4 turns)");
  info.mockRestore();
});

// --- Searching the history (R18) ---

test("a search marks every match and steps through them", async () => {
  const info = vi.spyOn(console, "info").mockImplementation(() => {});
  const scrolled: string[] = [];
  Element.prototype.scrollIntoView = function (this: Element) {
    scrolled.push(this.getAttribute("data-match") ?? "");
  };
  chatServer(
    [
      { role: "user", content: "Where is Paris?" },
      { role: "assistant", content: "Paris is in France. See https://en.wikipedia.org/wiki/Paris" },
      { role: "user", content: "Thanks!" },
      { role: "assistant", content: "You're welcome." },
    ],
    () => Response.json({}),
  );
  await openAt("#/chat");
  await screen.findByText("You're welcome.");
  fireEvent.click(screen.getByRole("button", { name: "Show history" }));
  const search = screen.getByLabelText("Search the history");
  const next = screen.getByRole("button", { name: "Next" }) as HTMLButtonElement;
  const previous = screen.getByRole("button", { name: "Previous" }) as HTMLButtonElement;
  expect(next.disabled).toBe(true);

  fireEvent.input(search, { target: { value: "paris" } });
  const box = screen.getByLabelText("Conversation history");
  const marks = () => Array.from(box.querySelectorAll("mark"));
  // The link stays in full in the history, so its "Paris" is found too.
  expect(marks().map((m) => m.textContent)).toEqual(["Paris", "Paris", "Paris"]);
  expect(screen.getByText("1 of 3")).toBeTruthy();
  expect(marks()[0].className).toBe("current");
  expect(info).toHaveBeenCalledWith(
    expect.stringMatching(/^History search found 3 matches in 4 turns \(\d+ ms\)$/),
  );

  fireEvent.click(next);
  expect(screen.getByText("2 of 3")).toBeTruthy();
  expect(marks()[1].className).toBe("current");
  fireEvent.keyDown(search, { key: "Enter" });
  expect(screen.getByText("3 of 3")).toBeTruthy();
  fireEvent.keyDown(search, { key: "Enter" }); // wraps round to the first
  expect(screen.getByText("1 of 3")).toBeTruthy();
  fireEvent.keyDown(search, { key: "Enter", shiftKey: true }); // and back to the last
  expect(screen.getByText("3 of 3")).toBeTruthy();
  fireEvent.click(previous);
  expect(screen.getByText("2 of 3")).toBeTruthy();
  expect(scrolled).toContain("2");

  fireEvent.input(search, { target: { value: "London" } });
  expect(screen.getByText("No matches")).toBeTruthy();
  expect(marks()).toEqual([]);
  expect(next.disabled).toBe(true);

  fireEvent.input(search, { target: { value: "" } });
  expect(screen.queryByText("No matches")).toBeNull();

  fireEvent.input(search, { target: { value: "Paris" } });
  fireEvent.click(screen.getByRole("button", { name: "Hide history" }));
  fireEvent.click(screen.getByRole("button", { name: "Show history" }));
  expect((screen.getByLabelText("Search the history") as HTMLInputElement).value).toBe("");
  expect(screen.getByLabelText("Conversation history").querySelector("mark")).toBeNull();
  Reflect.deleteProperty(Element.prototype, "scrollIntoView");
  info.mockRestore();
});

test("the current match stays valid when a failed prompt is taken back", async () => {
  vi.spyOn(console, "info").mockImplementation(() => {});
  const [answer, reply] = later();
  chatServer(
    [
      { role: "user", content: "Where is Paris?" },
      { role: "assistant", content: "Paris is in France." },
    ],
    answer,
  );
  await openAt("#/chat");
  await screen.findByText("Paris is in France.");
  fireEvent.click(screen.getByRole("button", { name: "Show history" }));
  fireEvent.input(screen.getByLabelText("Search the history"), { target: { value: "paris" } });
  fireEvent.input(promptBox(), { target: { value: "More about Paris?" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  // The prompt is in the history while the LLM answers, and its match is chosen.
  fireEvent.click(screen.getByRole("button", { name: "Previous" }));
  expect(screen.getByText("3 of 3")).toBeTruthy();
  await act(async () => {
    reply(Response.json({ detail: "The LLM failed." }, { status: 502 }));
  });
  expect(await screen.findByText(CANT_ANSWER)).toBeTruthy();
  expect(screen.getByText("2 of 2")).toBeTruthy();
  const box = screen.getByLabelText("Conversation history");
  expect(box.querySelector("mark.current")?.getAttribute("data-match")).toBe("1");
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  expect(screen.getByText("1 of 2")).toBeTruthy();
  vi.restoreAllMocks();
});

test("matches are found ignoring case and kept as written", () => {
  expect(splitMatches("Paris, paris and PARIS", "paris")).toEqual([
    "",
    "Paris",
    ", ",
    "paris",
    " and ",
    "PARIS",
    "",
  ]);
  expect(splitMatches("Hello", "  ")).toEqual(["Hello"]);
  expect(splitMatches("Hello", "bye")).toEqual(["Hello"]);
  expect(
    countMatches(
      [
        { role: "user", content: "aa a" },
        { role: "assistant", content: "A" },
      ],
      "a",
    ),
  ).toBe(4);
  expect(countMatches([{ role: "user", content: "aaa" }], "aa")).toBe(1); // no overlaps
});

test("an empty conversation has no history link", async () => {
  chatServer([], () => Response.json({}));
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  expect(screen.queryByRole("button", { name: "Show history" })).toBeNull();
});

test("the latest exchange starts at the last prompt", () => {
  expect(latestExchange([])).toBe(0);
  expect(latestExchange([{ role: "assistant", content: "Hi" }])).toBe(0);
  expect(
    latestExchange([
      { role: "user", content: "a" },
      { role: "assistant", content: "b" },
      { role: "user", content: "c" },
    ]),
  ).toBe(2);
});

// --- Spoken video replies (R17) ---

test("a reply that wasn't streamed is spoken in one video", async () => {
  const [speak, spoken] = later();
  const fetchMock = chatServer(
    [
      { role: "user", content: "Hi" },
      { role: "assistant", content: "Hello!" },
    ],
    () =>
      Response.json({ role: "assistant", content: "I'm well, thanks.", turn: 3, streamed: false }),
    speak,
  );
  await openAt("#/chat");
  await screen.findByText("Hello!");
  expect(document.querySelector("video.reply-video")).toBeNull();
  fireEvent.input(promptBox(), { target: { value: "How are you?" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  expect(await screen.findByText("I'm well, thanks.")).toBeTruthy();
  await waitFor(() =>
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/chat/video",
      expect.objectContaining({ method: "POST", body: expect.stringMatching(/^\{"turn":3,"reply_id":"[0-9a-f]{32}"\}$/) }),
    ),
  );
  expect(screen.getByText("Getting ready to say it…")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
  await act(async () => {
    spoken(Response.json({ video: "/api/chat/videos/3" }));
  });
  const video = await waitFor(() => {
    const found = document.querySelector("video.reply-video") as HTMLVideoElement | null;
    expect(found).not.toBeNull();
    return found!;
  });
  expect(video.getAttribute("src")).toMatch(/^\/api\/chat\/videos\/3\?t=\d+$/);
  expect(video.autoplay).toBe(true);
  expect(screen.queryByText("Getting ready to say it…")).toBeNull();
  const asked = fetchMock.mock.calls.filter(([url]) => url === "/api/chat/video");
  expect(asked).toHaveLength(1);

  // The next prompt takes the old video away: the server replaces it with the new reply's.
  const original = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url, init) =>
    url === "/api/chat" && init?.method === "POST"
      ? new Promise<Response>(() => {})
      : original(url, init),
  );
  fireEvent.input(promptBox(), { target: { value: "Good." } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  expect(screen.getByText("Thinking…")).toBeTruthy();
  expect(document.querySelector("video.reply-video")).toBeNull();
});

test("a reply's video is asked for by the server's count, not this page's", async () => {
  // Another tab added two turns since this page loaded the conversation.
  const fetchMock = chatServer([], () =>
    Response.json({ role: "assistant", content: "Hi again.", turn: 3 }),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Hello" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await screen.findByText("Hi again.");
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chat/video",
      expect.objectContaining({ body: expect.stringMatching(/^\{"turn":3,"reply_id":"[0-9a-f]{32}"\}$/) }),
    ),
  );
});

// --- Ordered playback (R22) ---

// The server's answer about a reply's clips (R22), with each clip's times on the server's clock
// (R22a): its sentence arrived `before` seconds before the answer, and it was ready 0.3 s later.
function clipsMade(urls: string[], done: boolean, error: string | null = null, before = 5) {
  const now = 1000;
  return {
    clips: urls.map((url) => ({ url, sentence_at: now - before, ready_at: now - before + 0.3 })),
    done,
    error,
    now,
  };
}

// The player showing the current clip; the other one, hidden, loads the next.
function shownVideo(): HTMLVideoElement {
  return document.querySelector("video.reply-video") as HTMLVideoElement;
}

test("a reply done with no clips is spoken in one video", async () => {
  // The server says so for a moment before it forgets a reply that wasn't streamed (R22a).
  const fetchMock = chatServer(
    [],
    () => Response.json({ role: "assistant", content: "Hi again.", turn: 1, streamed: false }),
    () => Response.json({ video: "/api/chat/videos/1" }),
    () => Response.json(clipsMade([], true)),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Hello" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await screen.findByText("Hi again.");
  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/chat/video",
      expect.objectContaining({ body: expect.stringMatching(/^\{"turn":1,"reply_id":"[0-9a-f]{32}"\}$/) }),
    ),
  );
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toMatch(/^\/api\/chat\/videos\/1/));
});

test("a reply that fails takes its clips and timing rows away", async () => {
  const [answer, reply] = later();
  // The first clip is made while the LLM writes; once the LLM fails, the server drops the clips.
  let clips: Answer = () => Response.json(clipsMade(["/api/chat/clips/x/1"], false));
  chatServer([], answer, undefined, () => clips());
  showMetrics();
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Tell me a story" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe("/api/chat/clips/x/1"));
  expect(screen.getByText("Clip 1: not spoken yet")).toBeTruthy();
  clips = () => Response.json({ detail: "No clips" }, { status: 404 });
  await act(async () => {
    reply(Response.json({ detail: "The LLM stopped." }, { status: 502 }));
  });
  await screen.findByText(CANT_ANSWER);
  await waitFor(() => expect(document.querySelector("video.reply-video")).toBeNull());
  expect(screen.queryByText(/^Clip 1:/)).toBeNull();
});

test("a streamed reply starts playing on its first clip, before the reply text", async () => {
  const [answer, reply] = later();
  let made = clipsMade([], false);
  const fetchMock = chatServer([], answer, undefined, () => Response.json(made));
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Tell me a story" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText("Thinking…");
  made = clipsMade(["/api/chat/clips/x/1"], false);
  const video = await waitFor(() => {
    const found = document.querySelector("video.reply-video") as HTMLVideoElement | null;
    expect(found?.getAttribute("src")).toBe("/api/chat/clips/x/1");
    return found!;
  });
  expect(screen.getByText("Thinking…")).toBeTruthy(); // the reply text hasn't come yet
  // Each request says how many clips the page has, so the server answers when there are more.
  const asked = fetchMock.mock.calls.map(([url]) => url).filter((u) => u.includes("/clips/"));
  expect(asked[0]).toMatch(/^\/api\/chat\/clips\/[0-9a-f]{32}\?known=0&wait=10$/);
  await act(async () => {
    reply(
      Response.json({ role: "assistant", content: "Once upon a time. The end.", streamed: true }),
    );
  });
  await screen.findByText("Once upon a time. The end.");
  fireEvent.ended(video); // the first clip ends before the second is made: wait on it
  expect(video.getAttribute("src")).toBe("/api/chat/clips/x/1");
  made = clipsMade(["/api/chat/clips/x/1", "/api/chat/clips/x/2"], true);
  await waitFor(() => expect(video.getAttribute("src")).toBe("/api/chat/clips/x/2"));
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
  fireEvent.ended(video);
  expect(video.getAttribute("src")).toBe("/api/chat/clips/x/2"); // stays on the last frame
  expect(fetchMock).not.toHaveBeenCalledWith("/api/chat/video", expect.anything());
  // Once it had one clip, every request said so, up to the answer that brought the end.
  const counts = fetchMock.mock.calls
    .map(([url]) => url)
    .filter((u) => u.includes("/clips/"))
    .map((u) => u.split("known=")[1]);
  expect(counts[0]).toBe("0&wait=10");
  expect(counts.at(-1)).toBe("1&wait=10");
});

test("a reply whose clips a newer prompt took is not spoken again as one video", async () => {
  const [answer, reply] = later();
  let clipsNow: Answer = () => Response.json(clipsMade(["/api/chat/clips/x/1"], false));
  const fetchMock = chatServer([], answer, undefined, () => clipsNow());
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Tell me a story" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  const video = await waitFor(() => {
    const found = document.querySelector("video.reply-video") as HTMLVideoElement | null;
    expect(found?.getAttribute("src")).toBe("/api/chat/clips/x/1");
    return found!;
  });
  // Another tab sends a prompt as this reply comes in, so the server drops this one's clips:
  // the reply was streamed all the same, and is not to be spoken again as one video.
  clipsNow = () => Response.json({ detail: "No clips" }, { status: 404 });
  await act(async () => {
    reply(
      Response.json({ role: "assistant", content: "Once upon a time.", turn: 3, streamed: true }),
    );
  });
  await screen.findByText("Once upon a time.");
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
  expect(fetchMock).not.toHaveBeenCalledWith("/api/chat/video", expect.anything());
  expect(video.getAttribute("src")).toBe("/api/chat/clips/x/1");
});

// Node, which the tests run in, says when a promise was rejected with nothing waiting on it.
declare const process: {
  on(event: "unhandledRejection", listener: (reason: unknown) => void): void;
  off(event: "unhandledRejection", listener: (reason: unknown) => void): void;
};

test("a clip that fails before the reply is in is reported with the reply", async () => {
  const [answer, reply] = later();
  chatServer([], answer, undefined, () =>
    Response.json(clipsMade([], true, "ffmpeg is not installed")),
  );
  const unhandled = vi.fn();
  process.on("unhandledRejection", unhandled);
  try {
    await openAt("#/chat");
    await screen.findByText("Ask a question to start the conversation.");
    fireEvent.input(promptBox(), { target: { value: "Count" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Thinking…");
    // The clips have failed; the reply is still being written.
    await act(() => new Promise((done) => setTimeout(done, 50)));
    expect(unhandled).not.toHaveBeenCalled();
    await act(async () => {
      reply(Response.json({ role: "assistant", content: "One. Two.", turn: 1, streamed: true }));
    });
    const note = await screen.findByText(/I couldn.t say this one aloud/);
    expect(note.textContent).not.toContain("ffmpeg"); // R41d: the cause goes to the console
    expect(unhandled).not.toHaveBeenCalled();
  } finally {
    process.off("unhandledRejection", unhandled);
  }
});

test("clips play in order when they arrive faster than they play", () => {
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  const { container, rerender } = render(<ClipPlayer clips={["/a"]} />);
  expect(container.querySelectorAll("video")).toHaveLength(1); // nothing to load yet
  rerender(<ClipPlayer clips={["/a", "/b", "/c"]} />);
  const videos = container.querySelectorAll("video");
  expect(videos).toHaveLength(2);
  expect(shownVideo().getAttribute("src")).toBe("/a");
  // The other player has the next clip loaded, out of sight.
  expect(videos[1].getAttribute("src")).toBe("/b");
  expect(videos[1].getAttribute("preload")).toBe("auto");
  expect(videos[1].hidden).toBe(true);
  expect(play).toHaveBeenCalledTimes(1); // the first clip is started as it arrives
  expect(shownVideo().controls).toBe(false); // no controls: the person speaks by themselves
  fireEvent.ended(shownVideo());
  expect(shownVideo()).toBe(videos[1]); // takes over, and the first loads the one after
  expect(shownVideo().getAttribute("src")).toBe("/b");
  expect(videos[0].getAttribute("src")).toBe("/c");
  expect(videos[0].hidden).toBe(true);
  expect(play).toHaveBeenCalledTimes(2);
  fireEvent.ended(shownVideo());
  expect(shownVideo()).toBe(videos[0]);
  expect(shownVideo().getAttribute("src")).toBe("/c");
  expect(container.querySelectorAll("video")).toHaveLength(1); // nothing more to load yet
  rerender(<ClipPlayer clips={["/d"]} />); // the next reply starts from its first clip
  expect(shownVideo().getAttribute("src")).toBe("/d");
});

test("a reply the browser won't play by itself gets a button to start it", async () => {
  const refused = new DOMException("needs a click first", "NotAllowedError");
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockRejectedValueOnce(refused);
  play.mockResolvedValue(undefined);
  render(<ClipPlayer clips={["/a"]} />);
  const button = await screen.findByRole("button", { name: "Play the reply" });
  fireEvent.click(button);
  await waitFor(() => expect(screen.queryByRole("button", { name: "Play the reply" })).toBeNull());
  expect(play).toHaveBeenCalledTimes(2);
});

test("a clip that arrives after the one before ended still gets the button if refused", async () => {
  const refused = new DOMException("needs a click first", "NotAllowedError");
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  const { rerender } = render(<ClipPlayer clips={["/a"]} />);
  expect(play).toHaveBeenCalledTimes(1);
  fireEvent.ended(shownVideo()); // played every clip so far: waits on the last frame
  play.mockRejectedValueOnce(refused);
  rerender(<ClipPlayer clips={["/a", "/b"]} />); // the next arrives in the same player
  expect(shownVideo().getAttribute("src")).toBe("/b");
  expect(play).toHaveBeenCalledTimes(2); // started here, not left to autoplay alone
  const button = await screen.findByRole("button", { name: "Play the reply" });
  fireEvent.click(button);
  await waitFor(() => expect(screen.queryByRole("button", { name: "Play the reply" })).toBeNull());
  expect(play).toHaveBeenCalledTimes(3);
});

test("a clip that fails to play for another reason gets no button", async () => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockRejectedValue(new Error("no source"));
  render(<ClipPlayer clips={["/a"]} />);
  await Promise.resolve();
  expect(screen.queryByRole("button", { name: "Play the reply" })).toBeNull();
});

test("the idle video shows once it plays, and goes when there is none", () => {
  const info = vi.spyOn(console, "info").mockImplementation(() => {});
  const told: Idle[] = [];
  const { rerender } = render(<Stage idle="loading" onIdle={(i) => told.push(i)} />);
  const idle = document.querySelector("video.idle-video") as HTMLVideoElement;
  expect(idle.getAttribute("src")).toBe("/api/chat/idle");
  expect(idle.className).toBe("idle-video resting"); // out of sight until it plays
  expect(idle.loop && idle.muted).toBe(true);
  expect(idle.controls).toBe(false);
  fireEvent.loadedData(idle); // a frame is not enough: it may not play yet
  expect(told).toEqual([]);
  fireEvent.playing(idle);
  expect(told).toEqual(["ready"]);
  expect(info).toHaveBeenCalledWith("Idle video ready");
  rerender(<Stage idle="ready" onIdle={(i) => told.push(i)} />);
  expect(idle.className).toBe("idle-video"); // fades in over the photo
  fireEvent.playing(idle); // played again on a loop: told once
  expect(told).toEqual(["ready"]);
  fireEvent.error(idle); // 404: an engine that makes none, or it failed
  expect(told).toEqual(["ready", "none"]);
  rerender(<Stage idle="none" onIdle={(i) => told.push(i)} />);
  expect(document.querySelector("video.idle-video")).toBeNull();
});

test("over the idle video, clips fade in and the player fades back between them", () => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  const { rerender } = render(<ClipPlayer clips={["/a", "/b"]} rest />);
  expect(shownVideo().className).toBe("reply-video resting"); // the idle video shows
  fireEvent.playing(shownVideo());
  expect(shownVideo().className).toBe("reply-video"); // fades in over it
  fireEvent.ended(shownVideo());
  // The next clip follows straight on, from where the head was: no fade.
  expect(shownVideo().getAttribute("src")).toBe("/b");
  expect(shownVideo().className).toBe("reply-video");
  fireEvent.ended(shownVideo()); // no clip yet after it: back to the idle video
  expect(shownVideo().className).toBe("reply-video resting");
  rerender(<ClipPlayer clips={["/a", "/b", "/c"]} rest />);
  fireEvent.playing(shownVideo());
  expect(shownVideo().className).toBe("reply-video");
  rerender(<ClipPlayer clips={["/d"]} rest />); // the next reply starts on the idle video
  expect(shownVideo().className).toBe("reply-video resting");
});

test("without an idle video, the player holds each clip's last frame", () => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  render(<ClipPlayer clips={["/a"]} />);
  expect(shownVideo().className).toBe("reply-video resting"); // the photo shows until it plays
  fireEvent.playing(shownVideo());
  expect(shownVideo().className).toBe("reply-video");
  fireEvent.ended(shownVideo());
  expect(shownVideo().className).toBe("reply-video");
});

// --- Clean playback (R41c) ---

test("the stage shows the photo under the videos, and goes without it if it can't load", () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  render(<Stage idle="loading" onIdle={() => {}} photo="/api/uploads/photos/p1" />);
  const still = document.querySelector(".stage img.still") as HTMLImageElement;
  expect(still.getAttribute("src")).toBe("/api/uploads/photos/p1");
  expect(still.alt).toBe(""); // only a picture behind the video
  fireEvent.error(still);
  expect(document.querySelector(".stage img.still")).toBeNull(); // no broken image
  expect(error).toHaveBeenCalledWith(expect.stringContaining("/api/uploads/photos/p1"));
});

test("a clip that can't be played is passed over quietly and the next one plays", () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  const ended = vi.fn();
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  render(<ClipPlayer clips={["/a", "/b"]} onEnded={ended} rest />);
  fireEvent.error(shownVideo()); // the first clip is broken
  expect(error).toHaveBeenCalledWith("Could not play a clip of the reply, so it was skipped: /a");
  expect(shownVideo().getAttribute("src")).toBe("/b");
  expect(shownVideo().className).toBe("reply-video resting"); // nothing broken on the screen
  expect(ended).toHaveBeenCalledWith(0, expect.any(Number)); // so Stop doesn't wait on it
  fireEvent.playing(shownVideo());
  expect(shownVideo().className).toBe("reply-video");
});

test("a clip that failed while it waited its turn is passed over when its turn comes", () => {
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  const { container, rerender } = render(<ClipPlayer clips={["/a", "/b"]} />);
  fireEvent.playing(shownVideo());
  const waiting = container.querySelectorAll("video")[1];
  fireEvent.error(waiting); // /b failed to load, out of sight
  rerender(<ClipPlayer clips={["/a", "/b", "/c"]} />);
  const seen = shownStates(container, () => fireEvent.ended(shownVideo()));
  expect(error).toHaveBeenCalledWith("Could not play a clip of the reply, so it was skipped: /b");
  expect(shownVideo().getAttribute("src")).toBe("/c");
  expect(play).toHaveBeenCalledTimes(2); // /a, then /c; never /b
  // Review on PR #78: the broken clip is never in sight, not even for a moment.
  expect(seen.filter((v) => v.src === "/b" && v.className === "reply-video")).toEqual([]);
});

// Every state the players passed through while `run` ran, from the attribute changes made to
// them in order: their src and class after each change.
function shownStates(container: Element, run: () => void): { src: string; className: string }[] {
  const now = new Map<Element, Record<string, string>>();
  for (const v of container.querySelectorAll("video"))
    now.set(v, { src: v.getAttribute("src") ?? "", class: v.getAttribute("class") ?? "" });
  const watch = new MutationObserver(() => {});
  watch.observe(container, { attributes: true, attributeOldValue: true, attributeFilter: ["src", "class"], subtree: true });
  run();
  const records = watch.takeRecords();
  watch.disconnect();
  // Each record has the value before its change; the value after is the next record's for the
  // same element and attribute, or the value now.
  const states: { src: string; className: string }[] = [];
  records.forEach((r, i) => {
    const name = r.attributeName!;
    const later = records.slice(i + 1).find((o) => o.target === r.target && o.attributeName === name);
    const el = r.target as Element;
    const state = now.get(el) ?? { src: "", class: "" };
    state[name] = later ? (later.oldValue ?? "") : (el.getAttribute(name) ?? "");
    now.set(el, state);
    states.push({ src: state.src, className: state.class });
  });
  return states;
}

test("an idle video that comes after the reply ended or was stopped takes over from it", () => {
  // Review on PR #78: the held frame stayed over the idle video once it arrived.
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  const ended = render(<ClipPlayer clips={["/a"]} />);
  fireEvent.playing(shownVideo());
  fireEvent.ended(shownVideo()); // no idle video yet: holds the last frame
  expect(shownVideo().className).toBe("reply-video");
  ended.rerender(<ClipPlayer clips={["/a"]} rest />);
  expect(shownVideo().className).toBe("reply-video resting");
  ended.unmount();

  const stopped = render(<ClipPlayer clips={["/a", "/b"]} />);
  fireEvent.playing(shownVideo());
  stopped.rerender(<ClipPlayer clips={["/a", "/b"]} stopped />);
  expect(shownVideo().className).toBe("reply-video"); // holds the frame
  stopped.rerender(<ClipPlayer clips={["/a", "/b"]} stopped rest />);
  expect(shownVideo().className).toBe("reply-video resting");
  stopped.unmount();

  const speaking = render(<ClipPlayer clips={["/a", "/b"]} />);
  fireEvent.playing(shownVideo());
  speaking.rerender(<ClipPlayer clips={["/a", "/b"]} rest />);
  expect(shownVideo().className).toBe("reply-video"); // still speaking: stays in front
});

test("without an idle video, Stop holds the clip's frame and shows no Play button", async () => {
  const refused = new DOMException("needs a click first", "NotAllowedError");
  vi.spyOn(HTMLMediaElement.prototype, "play").mockRejectedValue(refused);
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  const { rerender } = render(<ClipPlayer clips={["/a"]} />);
  await screen.findByRole("button", { name: "Play the reply" });
  fireEvent.playing(shownVideo());
  rerender(<ClipPlayer clips={["/a"]} stopped />);
  expect(pause).toHaveBeenCalled();
  expect(shownVideo().className).toBe("reply-video"); // the frame stays, no flash
  expect(screen.queryByRole("button", { name: "Play the reply" })).toBeNull();
});

test("the player says when each clip starts and ends, once each", () => {
  const started = vi.fn();
  const ended = vi.fn();
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  const { rerender } = render(<ClipPlayer clips={["/a", "/b"]} onStarted={started} onEnded={ended} />);
  fireEvent.playing(shownVideo());
  fireEvent.playing(shownVideo()); // after a stall: the same clip
  expect(started).toHaveBeenCalledTimes(1);
  expect(started).toHaveBeenLastCalledWith(0, expect.any(Number));
  fireEvent.ended(shownVideo());
  expect(ended).toHaveBeenCalledWith(0, expect.any(Number));
  fireEvent.playing(shownVideo());
  expect(started).toHaveBeenLastCalledWith(1, expect.any(Number));
  fireEvent.ended(shownVideo());
  expect(ended).toHaveBeenLastCalledWith(1, expect.any(Number));
  fireEvent.ended(shownVideo()); // played again by hand: not another sentence
  expect(ended).toHaveBeenCalledTimes(2);
  rerender(<ClipPlayer clips={["/c"]} onStarted={started} onEnded={ended} />);
  fireEvent.playing(shownVideo());
  expect(started).toHaveBeenLastCalledWith(0, expect.any(Number)); // the next reply's first
});

test("the timing readout shows each sentence against the target", () => {
  const times: ClipTime[] = [
    { text: 1000, ready: 2000, started: 2260, ended: 5000 }, // 1.26 s after its text
    { text: 1000, ready: 5100, started: 5300, ended: 8000 }, // 4.3 s, but 0.3 s after clip 1
    { text: 7000, ready: 9500, started: 10400, ended: 12000 }, // 2.4 s pause: too long
    { text: 11000, ready: 11500, started: 14100, ended: null }, // 3.1 s after; 2.1 s pause: too long
    { text: 12000, ready: 13000, started: null, ended: null },
  ];
  const { container } = render(<ClipTimes times={times} />);
  const rows = Array.from(container.querySelectorAll("li"));
  expect(rows.map((r) => r.textContent)).toEqual([
    "Clip 1: spoken 1.3 s after its text arrived",
    "Clip 2: spoken 4.3 s after its text arrived, 0.3 s after clip 1 ended",
    "Clip 3: spoken 3.4 s after its text arrived, 2.4 s after clip 2 ended",
    "Clip 4: spoken 3.1 s after its text arrived, 2.1 s after clip 3 ended",
    "Clip 5: not spoken yet",
  ]);
  // The first clip is judged by its wait after the text, the others by the pause before them.
  expect(rows.map((r) => r.className)).toEqual(["", "", "late", "late", ""]);
  expect(container.textContent).toContain("Timing (target 1 to 2 s)");
  // The average of the waits: 1.26, 0.3, 2.4 and 2.1 s.
  const average = container.querySelector(".average") as HTMLElement;
  expect(average.textContent).toBe("Average wait: 1.5 s over 4 clips of this reply");
  expect(average.className).toBe("average");
  // With the replies before it since the page was opened: (6.06 + 3 + 3) / 6 = 2.0 s.
  const since = render(<ClipTimes times={times} earlier={[3000, 3000]} />);
  expect(since.container.querySelector(".average")?.textContent).toBe(
    "Average wait: 1.5 s over 4 clips of this reply; 2.0 s over 6 clips since the page was opened",
  );
  // A reply spoken in one video (not streamed) is one line.
  const whole = render(
    <ClipTimes times={[{ text: 0, ready: 6000, started: 7200, ended: null }]} whole />,
  );
  expect(whole.container.textContent).toContain("Reply: spoken 7.2 s after its text arrived");
  const slow = whole.container.querySelectorAll(".average")[0] as HTMLElement;
  expect(slow.textContent).toBe("Average wait: 7.2 s over 1 clip of this reply");
  expect(slow.className).toBe("average late");
});

test("a clip whose text came after the one before ended waits from its text", () => {
  const times: ClipTime[] = [
    { text: 0, ready: 900, started: 1000, ended: 3000 },
    { text: 4000, ready: 5000, started: 5500, ended: null }, // 2.5 s after clip 1, 1.5 s after its text
  ];
  expect(clipWaits(times)).toEqual([1000, 1500]);
  const { container } = render(<ClipTimes times={times} />);
  expect(Array.from(container.querySelectorAll("li")).map((r) => r.className)).toEqual(["", ""]);
});

test("the chat shows how long each sentence took once it plays", async () => {
  // The first sentence's text came 5 s before the server answered; the clip plays right away.
  const made = clipsMade(["/api/chat/clips/x/1", "/api/chat/clips/x/2"], true, null, 5);
  chatServer(
    [],
    () => Response.json({ role: "assistant", content: "One. Two.", streamed: true }),
    undefined,
    () => Response.json(made),
  );
  showMetrics();
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Count" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await screen.findByText("One. Two.");
  await waitFor(() => expect(shownVideo().getAttribute("src")).toBe("/api/chat/clips/x/1"));
  expect(screen.getByText("Clip 1: not spoken yet")).toBeTruthy();
  fireEvent.playing(shownVideo());
  expect(await screen.findByText(/^Clip 1: spoken 5\.[0-2] s after its text arrived$/)).toBeTruthy();
  fireEvent.ended(shownVideo());
  fireEvent.playing(shownVideo());
  expect(
    await screen.findByText(/^Clip 2: spoken 5\.[0-2] s after its text arrived, 0\.[0-2] s after clip 1 ended$/),
  ).toBeTruthy();
});

test("when a clip fails, the clips so far stay and a plain note says so", async () => {
  chatServer(
    [],
    () => Response.json({ role: "assistant", content: "One. Two.", streamed: true }),
    undefined,
    () => Response.json(clipsMade(["/api/chat/clips/x/1"], true, "ffmpeg is not installed")),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Count" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  const note = await screen.findByText(/I couldn.t say this one aloud/);
  expect(note.textContent).toBe("I couldn't say this one aloud, so here it is as text.");
  expect(document.querySelector("video.reply-video")?.getAttribute("src")).toBe("/api/chat/clips/x/1");
});

test("when the voice or video fails, the reply stays as text with a note", async () => {
  chatServer(
    [],
    () => Response.json({ role: "assistant", content: "Hi there.", turn: 1 }),
    () => Response.json({ detail: "ffmpeg is not installed" }, { status: 502 }),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Hello" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  const note = await screen.findByText(/I couldn.t say this one aloud/);
  expect(note.textContent).not.toContain("ffmpeg");
  expect(note.closest("li")?.textContent).toContain("Hi there.");
  expect(document.querySelector("video.reply-video")).toBeNull();
  expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.input(promptBox(), { target: { value: "Again" } });
  expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(false);
});

test("if the conversation can't be loaded, the chat says so", async () => {
  chatServer([], () => Response.json({}));
  const fetchMock = vi.mocked(fetch);
  const original = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (input, init) =>
    input === "/api/chat" ? new Response("", { status: 500 }) : original(input, init),
  );
  await openAt("#/chat");
  expect(
    await screen.findByText("The conversation couldn't be loaded. Reload the page to try again."),
  ).toBeTruthy();
});

// --- Stop, volume and mute (R19) ---

test("the chat shows the idle video, with the reply's clips over it", async () => {
  const [answer, reply] = later();
  const made = clipsMade(["/api/chat/clips/x/1"], false);
  chatServer([], answer, undefined, () => Response.json(made));
  vi.spyOn(console, "info").mockImplementation(() => {});
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  const idle = document.querySelector(".stage video.idle-video") as HTMLVideoElement;
  fireEvent.playing(idle);
  await waitFor(() => expect(idle.className).toBe("idle-video")); // the person waits
  fireEvent.input(promptBox(), { target: { value: "Tell me a story" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(shownVideo()).not.toBeNull());
  fireEvent.playing(shownVideo());
  expect(shownVideo().className).toBe("reply-video"); // over the idle video
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  // Stopped: it pauses at once and fades back to the idle video, with no jump (R41c).
  expect(pause).toHaveBeenCalled();
  expect(shownVideo().className).toBe("reply-video resting");
  expect(idle.className).toBe("idle-video");
  await act(async () => {
    reply(Response.json({ role: "assistant", content: "Once upon a time.", streamed: true }));
  });
});

test("Stop ends the reply's video and its clips, and the text still comes", async () => {
  const [answer, reply] = later();
  const made = clipsMade(["/api/chat/clips/x/1"], false);
  const fetchMock = chatServer([], answer, undefined, () => Response.json(made));
  const info = vi.spyOn(console, "info").mockImplementation(() => {});
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  expect(screen.queryByRole("button", { name: "Stop" })).toBeNull(); // nothing to stop yet
  fireEvent.input(promptBox(), { target: { value: "Tell me a story" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(document.querySelector("video.reply-video")).not.toBeNull());
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  expect(pause).toHaveBeenCalled(); // the clip stops at once
  expect(shownVideo().autoplay).toBe(false); // and doesn't start again
  expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
  expect(screen.queryByText("Getting ready to say it…")).toBeNull();
  const stops = fetchMock.mock.calls.filter(([url]) => url.endsWith("/stop"));
  expect(stops).toHaveLength(1);
  const [url, init] = stops[0];
  expect(url).toMatch(/^\/api\/chat\/clips\/[0-9a-f]{32}\/stop$/);
  expect(init?.method).toBe("POST");
  expect(info).toHaveBeenCalledWith("Reply stopped (1 clips so far)");
  // The clips are no longer followed, though the server still has them to tell of.
  const asked = fetchMock.mock.calls.filter(([u]) => u.includes("known=")).length;
  await act(() => new Promise((done) => setTimeout(done, 50)));
  expect(fetchMock.mock.calls.filter(([u]) => u.includes("known=")).length).toBe(asked);
  await act(async () => {
    reply(Response.json({ role: "assistant", content: "Once upon a time.", streamed: true }));
  });
  await screen.findByText("Once upon a time.");
  fireEvent.input(promptBox(), { target: { value: "Again" } });
  await waitFor(() =>
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(false),
  ); // the next prompt can be sent
});

test("Stop frees the chat at once while a reply's one video is still being made", async () => {
  const [speak, spoken] = later();
  const fetchMock = chatServer(
    [],
    () => Response.json({ role: "assistant", content: "Hello.", turn: 1, streamed: false }),
    speak,
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Hi" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await screen.findByText("Hello.");
  // The video is asked for with the reply's id, so the server can stop making it.
  const [, init] = await waitFor(() => {
    const call = fetchMock.mock.calls.find(([url]) => url === "/api/chat/video");
    expect(call).toBeDefined();
    return call!;
  });
  const { reply_id: asked } = JSON.parse(init!.body as string) as { reply_id: string };
  vi.spyOn(console, "info").mockImplementation(() => {});
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  expect(fetchMock).toHaveBeenCalledWith(`/api/chat/clips/${asked}/stop`, { method: "POST" });
  // Not waiting for the video: the next prompt can go now.
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
  fireEvent.input(promptBox(), { target: { value: "Again" } });
  expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(false);
  await act(async () => {
    spoken(Response.json({ video: null })); // the server stopped making it
  });
  expect(document.querySelector("video.reply-video")).toBeNull();
});

test("Stop frees the chat at once while a clip request is still waiting", async () => {
  // The regression for a review finding: a request waiting for the next clip (up to 10 s on
  // the server) kept the chat waiting after Stop.
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  const [answer, reply] = later();
  chatServer([], answer, undefined, (/* the long wait */) => new Promise<Response>(() => {}));
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Count" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await act(async () => {
    reply(Response.json({ role: "assistant", content: "One. Two.", turn: 1, streamed: true }));
  });
  await screen.findByText("One. Two.");
  expect(screen.getByText("Getting ready to say it…")).toBeTruthy(); // still waiting for clips
  vi.spyOn(console, "info").mockImplementation(() => {});
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
  fireEvent.input(promptBox(), { target: { value: "Again" } });
  await waitFor(() =>
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(false),
  );
});

test("a stop the server refuses is logged", async () => {
  const [answer] = later();
  const fetchMock = chatServer([], answer);
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  const original = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url, init) =>
    url.endsWith("/stop") ? new Response("", { status: 500 }) : original(url, init),
  );
  fireEvent.input(promptBox(), { target: { value: "Hi" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  vi.spyOn(console, "info").mockImplementation(() => {});
  fireEvent.click(await screen.findByRole("button", { name: "Stop" }));
  await waitFor(() =>
    expect(console.error).toHaveBeenCalledWith("Could not stop the reply", expect.any(Error)),
  );
});

test("Stop shows until the last clip has played", async () => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  chatServer(
    [],
    () => Response.json({ role: "assistant", content: "One.", turn: 1, streamed: true }),
    undefined,
    () => Response.json(clipsMade(["/api/chat/clips/x/1"], true)),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Count" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await screen.findByText("One.");
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
  expect(screen.getByRole("button", { name: "Stop" })).toBeTruthy(); // still playing
  fireEvent.playing(shownVideo());
  fireEvent.ended(shownVideo());
  expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
});

test("mute and volume reach both players and are kept for the next visit", async () => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  chatServer(
    [],
    () => Response.json({ role: "assistant", content: "One. Two.", turn: 1, streamed: true }),
    undefined,
    () => Response.json(clipsMade(["/api/chat/clips/x/1", "/api/chat/clips/x/2"], true)),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  const volume = screen.getByRole("slider", { name: "Volume" }) as HTMLInputElement;
  expect(volume.value).toBe("100");
  fireEvent.input(volume, { target: { value: "40" } });
  fireEvent.input(promptBox(), { target: { value: "Count" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  const players = () => document.querySelectorAll(".stage video:not(.idle-video)");
  await waitFor(() => expect(players()).toHaveLength(2));
  for (const video of players() as NodeListOf<HTMLVideoElement>) {
    expect(video.volume).toBeCloseTo(0.4);
    expect(video.muted).toBe(false);
  }
  const mute = screen.getByRole("button", { name: "Mute" });
  expect(mute.getAttribute("aria-pressed")).toBe("false");
  fireEvent.click(mute);
  for (const video of players() as NodeListOf<HTMLVideoElement>) expect(video.muted).toBe(true);
  const unmute = screen.getByRole("button", { name: "Unmute" });
  expect(unmute.getAttribute("aria-pressed")).toBe("true");
  expect((screen.getByRole("slider", { name: "Volume" }) as HTMLInputElement).disabled).toBe(true);
  expect(loadSound()).toEqual({ volume: 0.4, muted: true });

  cleanup(); // the next visit starts with the same sound
  await openAt("#/chat");
  expect(await screen.findByRole("button", { name: "Unmute" })).toBeTruthy();
  expect((screen.getByRole("slider", { name: "Volume" }) as HTMLInputElement).value).toBe("40");
});

test("the sound starts at full volume when nothing usable was kept", () => {
  expect(loadSound()).toEqual({ volume: 1, muted: false });
  localStorage.setItem("imageskin.sound", "not json");
  expect(loadSound()).toEqual({ volume: 1, muted: false });
  localStorage.setItem("imageskin.sound", JSON.stringify({ volume: 7, muted: "yes" }));
  expect(loadSound()).toEqual({ volume: 1, muted: false }); // kept within 0 to 1
  localStorage.setItem("imageskin.sound", JSON.stringify({ volume: "loud" }));
  expect(loadSound()).toEqual({ volume: 1, muted: false });
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new DOMException("blocked", "SecurityError");
  });
  expect(loadSound()).toEqual({ volume: 1, muted: false });
});

test("a choice that can't be kept still changes the sound", async () => {
  chatServer([], () => Response.json({}));
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("full", "QuotaExceededError");
  });
  await openAt("#/chat");
  fireEvent.click(await screen.findByRole("button", { name: "Mute" }));
  expect(screen.getByRole("button", { name: "Unmute" })).toBeTruthy();
});

test("the player plays at full volume when given no sound", () => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  render(<ClipPlayer clips={["/a"]} />);
  expect(shownVideo().volume).toBe(1);
  expect(shownVideo().muted).toBe(false);
});

// The prepare job's server, with the settings saved as `saved`, or failing to save them.
function settingsServer(saved: { show_metrics: boolean }, saves = true) {
  const server = prepareServer([RUNNING]);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url !== "/api/settings") return server(url, init);
      if (init?.method !== "PATCH") return Response.json(saved);
      if (!saves) return new Response("", { status: 500 });
      Object.assign(saved, JSON.parse(init.body as string));
      return Response.json(saved);
    }),
  );
}

test("the timing metrics are hidden until turned on in the Settings menu", async () => {
  const saved = { show_metrics: false };
  settingsServer(saved);
  await openAt("#/setup");
  await screen.findByText("52 of 200 · about 12 min left"); // how long is left stays
  expect(screen.queryByText("Done in 31 s")).toBeNull();
  expect(screen.queryByRole("checkbox", { name: "Show timing metrics" })).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  const box = screen.getByRole("checkbox", { name: "Show timing metrics" }) as HTMLInputElement;
  expect(box.checked).toBe(false);
  await act(async () => {
    fireEvent.click(box);
  });
  expect(saved.show_metrics).toBe(true);
  expect(await screen.findByText("Done in 31 s")).toBeTruthy();
  expect(box.checked).toBe(true);

  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("checkbox", { name: "Show timing metrics" })).toBeNull();

  cleanup(); // a reload: the saved setting is read again
  await openAt("#/setup");
  expect(await screen.findByText("Done in 31 s")).toBeTruthy();
});

test("a setting that can't be saved says so and stays as it was", async () => {
  settingsServer({ show_metrics: false }, false);
  await openAt("#/setup");
  await screen.findByText("52 of 200 · about 12 min left");
  fireEvent.click(screen.getByRole("button", { name: "Settings" }));
  await act(async () => {
    fireEvent.click(screen.getByRole("checkbox", { name: "Show timing metrics" }));
  });
  expect(await screen.findByText("The setting could not be changed. Try again.")).toBeTruthy();
  expect(screen.queryByText("Done in 31 s")).toBeNull();
  const box = screen.getByRole("checkbox", { name: "Show timing metrics" }) as HTMLInputElement;
  expect(box.checked).toBe(false);
});

test("in the student view a chat that isn't set up asks for the teacher, not setup", async () => {
  serverWithConsent(true);
  const server = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/settings") return Response.json({ show_metrics: false, view: "student" });
      if (url === "/api/review") return Response.json({ accepted: false });
      return server(url, init);
    }),
  );
  await openAt("#/chat");
  expect(
    await screen.findByText("The chat isn't ready yet. Ask your teacher to finish setting it up."),
  ).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Go to setup" })).toBeNull();
});

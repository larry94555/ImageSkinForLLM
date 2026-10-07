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

import type { PrepareStatus, Upload, VoiceSample } from "./api";
import { App } from "./App";
import { duration, minutes } from "./pages";

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

async function openAt(hash: string) {
  window.location.hash = hash;
  render(<App />);
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
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

test("home starts setup at consent until it is given", async () => {
  serverWithConsent(false);
  await openAt("#/");
  const start = await screen.findByRole("link", { name: "Start setup" });
  expect(start.getAttribute("href")).toBe("#/consent");
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

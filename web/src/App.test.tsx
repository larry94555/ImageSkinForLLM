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

import type { Upload } from "./api";
import { App } from "./App";
import { minutes } from "./pages";

function serverWithConsent(agreed: boolean, postOk = true) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.startsWith("/api/uploads/")) return Response.json([]);
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

// A fake server with consent given and these uploads stored. POSTs answer with `posted` in turn.
// The first photo is the one the app picks for the video.
function uploadServer(stored: Upload[], posted: Response[] = []) {
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

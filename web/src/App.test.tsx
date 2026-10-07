import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
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
};
const SOUND: Upload = {
  ...PHOTO,
  id: "b".repeat(32),
  kind: "sounds",
  name: "voice1.m4a",
  format: "m4a",
  seconds: 95.4,
};

// A fake server with consent given and these uploads stored. POSTs answer with `posted` in turn.
function uploadServer(stored: Upload[], posted: Response[] = []) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
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
  const input = (await screen.findByText("Add photos")).querySelector("input") as HTMLInputElement;
  expect(input.disabled).toBe(true);
  await act(async () => {
    finishList(Response.json([]));
  });
  await waitFor(() => expect(input.disabled).toBe(false));
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

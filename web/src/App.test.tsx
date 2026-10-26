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
import { openSettings, returnToApp } from "./settings.test.util";
import styles from "./styles.css?raw";
import {
  CANT_ANSWER,
  ClipPlayer,
  type Idle,
  Stage,
  type ClipTime,
  ClipTimes,
  clipWaits,
  chatText,
  countMatches,
  countdown,
  duration,
  latestExchange,
  loadLesson,
  loadQuiz,
  loadAssessment,
  loadSound,
  splitMatches,
} from "./pages";
import { minutes } from "./checks";

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

test("the consent page shows Larry's short image disclaimer and checkbox", async () => {
  serverWithConsent(false);
  await openAt("#/consent");
  expect(
    await screen.findByText(
      "Only use images you have the right to use. Ideally, use your own picture.",
    ),
  ).toBeTruthy();
  expect(screen.queryByText(/Only use photos and recordings of someone/)).toBeNull();
  expect(
    screen.getByText("I have the right to use the photos and recording that will be used by the app."),
  ).toBeTruthy();
  expect(screen.queryByText(/agreed to have their face and voice/)).toBeNull();
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
  expect(await screen.findByText(/^Make the talking person in four steps/)).toBeTruthy();
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

test("the top bar's height is given to the page, and kept up to date (review on PR #83)", async () => {
  serverWithConsent(true);
  let height = 52;
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockImplementation(() => height);
  let resized = () => {};
  const disconnect = vi.fn();
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: () => void) {
        resized = callback;
      }
      observe() {}
      disconnect = disconnect;
    },
  );
  const root = document.documentElement.style;
  await openAt("#/setup");
  expect(root.getPropertyValue("--header-h")).toBe("52px");
  // On a phone the tabs wrap to a second row.
  height = 96;
  resized();
  expect(root.getPropertyValue("--header-h")).toBe("96px");
  cleanup();
  expect(disconnect).toHaveBeenCalled();
});

// The browser lays the page out, which this test runner can't, so this checks the rules that
// keep the person below the sticky top bar on the chat page (review on PR #83).
test("the chat's person sticks below the top bar, using its measured height", () => {
  const rule = (selector: string) =>
    [...styles.matchAll(new RegExp(`${selector.replace(/\./g, "\\.")} \\{([^}]*)\\}`, "g"))].map(
      (m) => m[1],
    );
  expect(rule("header")[0]).toMatch(/position: sticky;\s*top: 0;/);
  const person = rule(".chat .person");
  expect(person[0]).toMatch(/position: sticky;\s*top: var\(--header-h, 0px\);/);
  expect(person[1]).toMatch(/top: calc\(var\(--header-h, 0px\) \+ 16px\)/);
  // The stage itself no longer sticks on its own, at the top of the window, under the bar.
  expect(rule(".stage")[0]).not.toMatch(/sticky/);
});

// The text on filled buttons and the user's chat bubble against their fill, in light and dark
// mode, idle and hovered: at least 4.5:1, the WCAG AA target for normal text (review on PR #83).
test("filled buttons keep readable white text in both modes, hovered too", () => {
  const luminance = (hex: string) => {
    const [r, g, b] = [1, 3, 5].map((i) => {
      const c = parseInt(hex.slice(i, i + 2), 16) / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const contrast = (a: string, b: string) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };
  const light = styles.slice(styles.indexOf(":root {"), styles.indexOf("@media (prefers-color-scheme: dark)"));
  const dark = styles.slice(styles.indexOf("@media (prefers-color-scheme: dark)"));
  const token = (block: string, name: string) => block.match(new RegExp(`--${name}: (#[0-9a-f]{6});`))?.[1];
  const text = token(light, "on-button") ?? "";
  for (const block of [light, dark]) {
    for (const fill of ["button", "button-hover"]) {
      expect(contrast(text, token(block, fill) ?? "#ffffff")).toBeGreaterThanOrEqual(4.5);
    }
  }
  // The buttons and the bubble use those tokens, not the accent, which lightens in dark mode.
  expect(styles).toMatch(/background: var\(--button\);\s*color: var\(--on-button\);\s*font: inherit;/);
  expect(styles).toMatch(/\.button:hover, button:hover \{ background: var\(--button-hover\); \}/);
  expect(styles).toMatch(/ol\.turns li\.user \{[^}]*background: var\(--button\);[^}]*color: var\(--on-button\);/);
});

// A pressed button moves with `translate`, which adds to a `transform` instead of replacing it,
// so the centred "Play the reply" stays centred when pressed (review on PR #83).
test("pressing a button doesn't undo the centring of Play the reply", () => {
  expect(styles).toMatch(/\.button:active, button:active \{ translate: 0 1px; \}/);
  expect(styles).not.toMatch(/:active[^{]*\{[^}]*transform/);
  expect(styles).toMatch(/\.play-reply \{[^}]*transform: translate\(-50%, -50%\);/);
});

test("without ResizeObserver the top bar is measured once and that is logged", async () => {
  serverWithConsent(true);
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(60);
  vi.stubGlobal("ResizeObserver", undefined);
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  await openAt("#/setup");
  expect(document.documentElement.style.getPropertyValue("--header-h")).toBe("60px");
  expect(warn).toHaveBeenCalledWith("No ResizeObserver; the top bar's height is measured once");
});

test("with consent, setup opens and the nav marks it", async () => {
  serverWithConsent(true);
  await openAt("#/setup");
  expect(await screen.findByText(/^Make the talking person in four steps/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Setup" }).className).toBe("current");
});

test("setup offers a ready-made avatar instead of your own photo and voice", async () => {
  serverWithConsent(true);
  await openAt("#/setup");
  const link = await screen.findByRole("link", { name: "Use a ready-made avatar instead" });
  expect(link.getAttribute("href")).toBe("#/start-now");
});

// Larry's report: with a ready-made avatar in use, the home page's Setup goes to Start now, and
// the top bar's Setup went to the photo and voice setup instead. Both now go to Start now.
function serverWithAvatar() {
  const server = serverWithConsent(true);
  const chosen = { gender: "female", accent: "american", realism: "photoreal", role: "boss" };
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) =>
    url === "/api/start-now" && !init?.method
      ? Response.json({ state: "done", chosen })
      : server(url, init),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

test("with a ready-made avatar, the top bar's Setup goes where the home page's does", async () => {
  const info = vi.spyOn(console, "info").mockImplementation(() => {});
  serverWithAvatar();
  // Opened from the top bar, home shows its choices (a visit starting there goes to the chat).
  await openAt("#/chat");
  await screen.findAllByRole("link", { name: "Setup" });
  await act(async () => {
    window.location.hash = "#/";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  await screen.findByText("Choose another ready-made avatar, or use your own photo and voice.");
  const home = screen.getByText("Choose another ready-made avatar, or use your own photo and voice.").closest("a")!;
  expect(home.getAttribute("href")).toBe("#/start-now");
  const nav = within(document.querySelector("nav")!).getByRole("link", { name: "Setup" });
  await waitFor(() => expect(nav.getAttribute("href")).toBe("#/start-now"));
  expect(info).toHaveBeenCalledWith(
    expect.stringMatching(/^Top bar Setup link: Start now \(a ready-made avatar is in use\)/),
  );
});

test("without a ready-made avatar, the top bar's Setup goes to setup", async () => {
  serverWithConsent(true);
  await openAt("#/chat");
  const nav = await within(document.querySelector("nav")!).findByRole("link", { name: "Setup" });
  await act(async () => {});
  expect(nav.getAttribute("href")).toBe("#/setup");
});

test("before consent, the top bar's Setup goes to the consent page, as home's does", async () => {
  serverWithConsent(false);
  await openAt("#/");
  const nav = await within(document.querySelector("nav")!).findByRole("link", { name: "Setup" });
  expect(nav.getAttribute("href")).toBe("#/consent");
});

test("the top bar's Setup is read again on each page change", async () => {
  const fetchMock = serverWithAvatar();
  await openAt("#/chat");
  await waitFor(() =>
    expect(within(document.querySelector("nav")!).getByRole("link", { name: "Setup" }).getAttribute("href")).toBe(
      "#/start-now",
    ),
  );
  const reads = () => fetchMock.mock.calls.filter(([u, i]) => u === "/api/start-now" && !i?.method).length;
  const before = reads();
  await act(async () => {
    window.location.hash = "#/guide";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  await waitFor(() => expect(reads()).toBeGreaterThan(before));
});

test("if the avatar can't be read, the top bar's Setup still goes to setup and that is logged", async () => {
  const server = serverWithConsent(true);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) =>
      url === "/api/start-now" ? new Response("", { status: 500 }) : server(url, init),
    ),
  );
  await openAt("#/chat");
  await waitFor(() =>
    expect(console.error).toHaveBeenCalledWith(
      "Could not read the default person for the top bar",
      expect.anything(),
    ),
  );
  const nav = within(document.querySelector("nav")!).getByRole("link", { name: "Setup" });
  expect(nav.getAttribute("href")).toBe("#/setup");
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

// Clicks a Remove button, then Yes in the box that asks first.
async function removeConfirmed(button: HTMLElement) {
  await act(async () => {
    fireEvent.click(button);
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Yes, remove it" }));
  });
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
  await removeConfirmed(within(other).getByRole("button", { name: "Remove" }));
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
  await openAt("#/setup");
  await screen.findByText("Used for the video (best score)");
  const asked = () => fetchMock.mock.calls.filter(([url]) => url.endsWith("/chosen")).length;
  expect(asked()).toBe(1);
  await act(async () => {
    chooseFiles("Add photos", [new File(["x"], "new.jpg")]);
  });
  await waitFor(() => expect(asked()).toBe(2));
  const chosen = screen.getByText("Used for the video (best score)").closest("li") as HTMLElement;
  await removeConfirmed(within(chosen).getByRole("button", { name: "Remove" }));
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
    if (url.endsWith("/check")) {
      const detail = "The photo checks are off, so it could not be checked.";
      return Response.json({ detail }, { status: 503 });
    }
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
  expect(await screen.findByText("voice1.wav: That didn't work. Please try again.")).toBeTruthy();
});

test("remove asks first in the app's own box, then deletes the file", async () => {
  const fetchMock = uploadServer([PHOTO]);
  const confirm = vi.spyOn(window, "confirm");
  await openAt("#/setup");
  await screen.findByAltText("front.jpg");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  });
  expect(screen.getByRole("alertdialog", { name: "Remove front.jpg?" })).toBeTruthy();
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "No, keep it" }));
  });
  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(screen.queryByAltText("front.jpg")).toBeTruthy();
  expect(fetchMock).not.toHaveBeenCalledWith(expect.anything(), { method: "DELETE" });
  await removeConfirmed(screen.getByRole("button", { name: "Remove" }));
  await waitFor(() => expect(screen.queryByAltText("front.jpg")).toBeNull());
  expect(confirm).not.toHaveBeenCalled(); // not the browser's box
  expect(fetchMock).toHaveBeenCalledWith(`/api/uploads/photos/${PHOTO.id}`, { method: "DELETE" });
});

test("a failed remove keeps the file and says so", async () => {
  uploadServer([PHOTO]);
  await openAt("#/setup");
  await screen.findByAltText("front.jpg");
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
  await removeConfirmed(screen.getByRole("button", { name: "Remove" }));
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
  await removeConfirmed(screen.getAllByRole("button", { name: "Remove" })[0]);
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

test("the face movement is chosen on the Setup page, beside Prepare (R128a)", async () => {
  const fetchMock = prepareServer([IDLE]);
  await openAt("#/setup");
  await screen.findByRole("button", { name: "Prepare the video" });
  const choice = within(screen.getByRole("group", { name: "Face movement while speaking" }));
  expect((choice.getByRole("radio", { name: "Normal" }) as HTMLInputElement).checked).toBe(true);
  await act(async () => {
    fireEvent.click(choice.getByRole("radio", { name: "More" }));
  });
  const patch = fetchMock.mock.calls.find(([url, init]) => url === "/api/settings" && init?.method === "PATCH");
  expect(JSON.parse(String(patch?.[1]?.body))).toEqual({ face_movement: "more" });
});

test("prepare starts the job and shows each step's progress until it is ready", async () => {
  const fetchMock = prepareServer([IDLE, RUNNING, DONE]);
  showMetrics();
  await openAt("#/setup");
  fireEvent.click(await screen.findByRole("button", { name: "Prepare the video" }));
  expect(await screen.findByText("Preparing… 31% done")).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith("/api/prepare", { method: "POST" });
  const bar = screen.getByRole("progressbar", { name: "Preparing" }) as HTMLProgressElement;
  expect(bar.value).toBe(31);
  expect(screen.getByText("Done in 31 s")).toBeTruthy();
  expect(screen.getByText("52 of 200 · about 12 min 5 s left")).toBeTruthy();
  expect(screen.getByText("Waiting")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /Prepare/ })).toBeNull(); // no second start

  // The page asks again every second while it runs.
  expect(
    await screen.findByText("Done. Watch the sample video, then say whether it is right.", {}, { timeout: 3000 }),
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

test("a running step says what it is doing and about how long is left (R134b)", async () => {
  const steps = STEPS.map((s) => (s.key === "loop" ? { ...s, activity: "Frame 53 of 200" } : s));
  prepareServer([{ ...RUNNING, steps, left_s: 1500 }]);
  await openAt("#/setup");
  expect(await screen.findByText("Preparing… 31% done · about 25 min 0 s left")).toBeTruthy();
  expect(screen.getByText("Frame 53 of 200 · about 12 min 5 s left")).toBeTruthy();
  expect(screen.queryByText(/taking longer than usual/)).toBeNull();
});

test("a slow step says it is still working (R134b)", async () => {
  const steps = STEPS.map((s) =>
    s.key === "loop" ? { ...s, activity: "Frame 53 of 200", slow: true } : s,
  );
  prepareServer([{ ...RUNNING, steps }]);
  await openAt("#/setup");
  expect(
    await screen.findByText("This is taking longer than usual. It's still working."),
  ).toBeTruthy();
});

test("a job the app is no longer working on says so and can be tried again (R134b)", async () => {
  const fetchMock = prepareServer([{ ...RUNNING, stopped: true }]);
  await openAt("#/setup");
  expect(
    await screen.findByText(
      "Preparing stopped: the app is no longer working on it. Click Try again to carry on where it left off.",
    ),
  ).toBeTruthy();
  expect(screen.getByText("Stopped")).toBeTruthy();
  expect(screen.queryByText(/% done/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Preparing… 31% done")).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith("/api/prepare", { method: "POST" });
});

test("prepare says what is missing when it can't start", async () => {
  prepareServer(
    [IDLE],
    Response.json({ detail: "Add a photo that passes the checks first." }, { status: 409 }),
  );
  await openAt("#/setup");
  fireEvent.click(await screen.findByRole("button", { name: "Prepare the video" }));
  expect(await screen.findByText("Add a photo that passes the checks first.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Prepare the video" })).toBeTruthy();
});

test("a failed job says why, marks where it stopped and can be tried again", async () => {
  const steps = STEPS.map((s) => (s.key === "loop" ? { ...s, left_s: null } : s));
  prepareServer([{ ...RUNNING, state: "failed", steps, error: "The video couldn't be prepared on this computer." }]);
  await openAt("#/setup");
  expect(await screen.findByText("The video couldn't be prepared on this computer.")).toBeTruthy();
  expect(screen.getByText("Stopped")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
});

const FAILURE = {
  reference: "P-7K3F9Q",
  step: "Make the video of the person listening",
  reason: "memory",
  message: "Out of memory.",
  retry: true,
  details: "RuntimeError: out of memory reading <data folder>",
  version: "0.1.0",
};

test("a failed job shows the step, the reason and the reference for support (R134)", async () => {
  const steps = STEPS.map((s) => (s.key === "loop" ? { ...s, left_s: null } : s));
  const failed = { ...RUNNING, state: "failed" as const, steps, error: FAILURE.message };
  prepareServer([{ ...failed, failure: FAILURE, finished_at: "2026-10-25T19:30:00+00:00" }]);
  const writeText = vi.fn(async () => {});
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  await openAt("#/setup");
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain(
    "“Make the video of the person listening” failed. Out of memory.",
  );
  expect(alert.textContent).toContain(
    "Try again may help. If it keeps failing, please give support the reference P-7K3F9Q.",
  );
  expect(alert.textContent).not.toContain("log");
  expect(screen.getByText("Details")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Copy details for support" }));
  expect(await screen.findByText("Copied.")).toBeTruthy();
  const copied = (writeText.mock.calls[0] as unknown as [string])[0];
  expect(copied).toContain("Reference: P-7K3F9Q");
  expect(copied).toContain("Step: Make the video of the person listening");
  expect(copied).toContain("Time: 2026-10-25T19:30:00+00:00");
  expect(copied).toContain("App version: 0.1.0");
  expect(copied).toContain("Browser: ");
  expect(copied).toContain("Error: RuntimeError: out of memory reading <data folder>");
});

test("a failure Try again can't fix says so, and the details can be copied by hand", async () => {
  const failure = { ...FAILURE, step: null, retry: false, message: "A program is missing." };
  prepareServer([{ ...RUNNING, state: "failed", error: failure.message, failure }]);
  const writeText = vi.fn(async () => {
    throw new Error("denied");
  });
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  await openAt("#/setup");
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Preparing failed. A program is missing.");
  expect(alert.textContent).toContain("Please give support the reference P-7K3F9Q.");
  expect(alert.textContent).not.toContain("Trying again");
  expect(alert.textContent).not.toContain("keeps failing");
  fireEvent.click(screen.getByRole("button", { name: "Copy details for support" }));
  const byHand = (await screen.findByLabelText("Details for support")) as HTMLTextAreaElement;
  expect(byHand.value).toContain("Step: Before the first step");
  expect(byHand.value).toContain("Time: unknown");
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

test("the time left counts down to the second while the step and the percentage stay (review on PR #170)", async () => {
  const at = (left: number) => ({
    ...RUNNING,
    left_s: left,
    steps: STEPS.map((s) => (s.key === "loop" ? { ...s, activity: "Frame 53 of 200", left_s: left } : s)),
  });
  prepareServer([at(119), at(118), at(117)]);
  await openAt("#/setup");
  expect(await screen.findByText("Preparing… 31% done · about 1 min 59 s left")).toBeTruthy();
  expect(screen.getByText("Frame 53 of 200 · about 1 min 59 s left")).toBeTruthy();
  // The next read, a second later: the same step, activity and percentage, yet the page changed.
  expect(
    await screen.findByText("Preparing… 31% done · about 1 min 58 s left", {}, { timeout: 3000 }),
  ).toBeTruthy();
  expect(screen.getByText("Frame 53 of 200 · about 1 min 58 s left")).toBeTruthy();
});

test("countdown is to the second", () => {
  expect(countdown(42)).toBe("42 s");
  expect(countdown(60)).toBe("1 min 0 s");
  expect(countdown(725)).toBe("12 min 5 s");
  expect(countdown(3785)).toBe("1 h 3 min 5 s");
  expect(countdown(3605)).toBe("1 h 0 min 5 s");
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
  await openAt("#/setup");
  expect(await screen.findByText("Done. Watch the sample video, then say whether it is right.")).toBeTruthy();

  fireEvent.click(await screen.findByRole("button", { name: "Use this photo" }));
  expect(await screen.findByRole("button", { name: "Prepare the video" })).toBeTruthy();
  expect(screen.queryByText("Done. Watch the sample video, then say whether it is right.")).toBeNull();

  fireEvent.click(screen.getByRole("button", { name: "Use this photo" })); // back to the first
  expect(await screen.findByText("Done. Watch the sample video, then say whether it is right.")).toBeTruthy();

  const recording = (await screen.findByText(/voice1\.m4a/)).closest("li") as HTMLElement;
  await removeConfirmed(within(recording).getByRole("button", { name: "Remove" }));
  expect(await screen.findByRole("button", { name: "Prepare the video" })).toBeTruthy();
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
  expect(await screen.findByText("Done. Watch the sample video, then say whether it is right.")).toBeTruthy();
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
  expect(await screen.findByText(/needs the voice add-on/)).toBeTruthy();
  expect(document.body.textContent).not.toContain("README"); // no technical words (R41e)
  expect(accentOption("British").matches(":disabled")).toBe(true);
  expect(accentOption("American").matches(":disabled")).toBe(true);
  expect(accentOption(/Their own accent/).matches(":disabled")).toBe(false);
});

test("setup says what it is for and numbers its four steps", async () => {
  accentServer({ accent: "own", available: true });
  await openAt("#/setup");
  expect(await screen.findByText(/^Make the talking person in four steps/)).toBeTruthy();
  const steps = Array.from(document.querySelectorAll("section.panel")).map(
    (s) => `${s.querySelector(".step-of")?.textContent}: ${s.querySelector("h2")?.textContent}`,
  );
  expect(steps).toEqual([
    "Step 1 of 4: Photos",
    "Step 2 of 4: Voice recordings",
    "Step 3 of 4: Accent",
    "Step 4 of 4: Prepare the video",
  ]);
  expect(await screen.findByText("Add recordings")).toBeTruthy();
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

test("a question said with Hold to talk is shown in the box, sent, and shown as meant", async () => {
  // The browser's speech recognition (R24), heard as the test says.
  let recognition: { onresult: (e: object) => void; onend: () => void } | null = null;
  vi.stubGlobal(
    "webkitSpeechRecognition",
    class {
      onresult = (_: object) => {};
      onend = () => {};
      constructor() {
        recognition = this;
      }
      start() {}
      stop() {
        this.onend();
      }
    },
  );
  vi.spyOn(console, "info").mockImplementation(() => {});
  // The server put back a name the browser misheard (Larry's "Oiler" for "Euler").
  const fetchMock = chatServer([], () =>
    Response.json({ role: "assistant", content: "Hi!", prompt: "Who was Euler?" }),
  );
  await openAt("#/chat");
  const talk = await screen.findByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(talk);
  });
  await act(async () => {
    recognition!.onresult({ results: [[{ transcript: "Who was Oiler?" }]] });
  });
  expect(promptBox().value).toBe("Who was Oiler?");
  const now = performance.now.bind(performance);
  vi.spyOn(performance, "now").mockImplementation(() => now() + 1000); // held, not tapped
  await act(async () => {
    fireEvent.pointerUp(talk);
  });
  expect(await screen.findByText("Hi!", undefined, { timeout: 3000 })).toBeTruthy();
  expect(screen.getByText("Who was Euler?").className).toBe("user");
  expect(screen.queryByText("Who was Oiler?")).toBeNull();
  expect(promptBox().value).toBe("");
  const sent = fetchMock.mock.calls.find(([url, init]) => url === "/api/chat" && init?.method);
  expect(JSON.parse(sent![1]!.body as string)).toMatchObject({
    prompt: "Who was Oiler?",
    spoken: true,
  });
  expect(console.info).toHaveBeenCalledWith('Push-to-talk: "Who was Oiler?" taken as "Who was Euler?"');
  vi.unstubAllGlobals();
});

// --- Topic hints (R41g) ---

// The chat's server, answering the hints with `hints`, one per call and then the last again.
function hintsServer(...hints: (object | Error)[]) {
  const server = chatServer([], () =>
    Response.json({ role: "assistant", content: "Primes are counted." }),
  );
  const answers = server.getMockImplementation()!;
  let calls = 0;
  server.mockImplementation(async (url, init) => {
    if (url !== "/api/chat/hints") return answers(url, init);
    const hint = hints[Math.min(calls++, hints.length - 1)];
    if (hint instanceof Error) return Response.json({ detail: hint.message }, { status: 500 });
    return Response.json(hint);
  });
  return server;
}

const RIEMANN_HINTS = {
  line: "Questions must be about these topics: Prime Number Basics and Zeta Function Integral.",
  examples: [
    "What can you tell me about Prime Number Basics?",
    "Can you explain Zeta Function Integral?",
  ],
};

test("under the prompt box, the topics and example questions are shown", async () => {
  hintsServer(RIEMANN_HINTS);
  await openAt("#/chat");
  expect(await screen.findByText(RIEMANN_HINTS.line)).toBeTruthy();
  const examples = within(screen.getByRole("list", { name: "Example questions" }));
  expect(examples.getAllByRole("button").map((b) => b.textContent)).toEqual(
    RIEMANN_HINTS.examples,
  );
});

test("clicking an example question sends it", async () => {
  const server = hintsServer(RIEMANN_HINTS);
  const info = vi.spyOn(console, "info").mockImplementation(() => {});
  await openAt("#/chat");
  const example = await screen.findByRole("button", { name: RIEMANN_HINTS.examples[0] });
  fireEvent.input(promptBox(), { target: { value: "half typed" } });
  await act(async () => {
    fireEvent.click(example);
  });
  expect(await screen.findByText("Primes are counted.")).toBeTruthy();
  const sent = server.mock.calls.find(([url, init]) => url === "/api/chat" && init?.method);
  expect(JSON.parse(sent![1]!.body as string).prompt).toBe(RIEMANN_HINTS.examples[0]);
  expect(screen.getByText(RIEMANN_HINTS.examples[0], { selector: "li.user" })).toBeTruthy();
  expect(promptBox().value).toBe(""); // the box is cleared, as when Send is pressed
  expect(info).toHaveBeenCalledWith("Example question asked");
});

test("the example questions can't be clicked while a reply is coming", async () => {
  const [answer] = later();
  const server = hintsServer(RIEMANN_HINTS);
  const answers = server.getMockImplementation()!;
  server.mockImplementation(async (url, init) =>
    url === "/api/chat" && init?.method === "POST" ? answer() : answers(url, init),
  );
  await openAt("#/chat");
  const first = await screen.findByRole("button", { name: RIEMANN_HINTS.examples[0] });
  await act(async () => {
    fireEvent.click(first);
  });
  const other = screen.getByRole("button", { name: RIEMANN_HINTS.examples[1] });
  expect((other as HTMLButtonElement).disabled).toBe(true);
});

test("the hints are read again after each reply, so they follow the PDFs", async () => {
  const server = hintsServer({ line: null, examples: [] }, RIEMANN_HINTS);
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  expect(document.querySelector(".hints")).toBeNull(); // no PDF yet: nothing to hint
  fireEvent.input(promptBox(), { target: { value: "Hello" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  expect(await screen.findByText(RIEMANN_HINTS.line)).toBeTruthy();
  expect(server.mock.calls.filter(([url]) => url === "/api/chat/hints")).toHaveLength(2);
});

test("hints that can't be read are left out", async () => {
  hintsServer(new Error("broken"));
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  await waitFor(() =>
    expect(console.error).toHaveBeenCalledWith("Could not load the topic hints", expect.anything()),
  );
  expect(document.querySelector(".hints")).toBeNull();
});

test("hints that can't be read again are taken away, not left stale (review on PR #86)", async () => {
  hintsServer(RIEMANN_HINTS, new Error("broken"));
  await openAt("#/chat");
  expect(await screen.findByText(RIEMANN_HINTS.line)).toBeTruthy();
  fireEvent.input(promptBox(), { target: { value: "Hello" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await screen.findByText("Primes are counted.");
  await waitFor(() => expect(document.querySelector(".hints")).toBeNull());
  expect(screen.queryByRole("button", { name: RIEMANN_HINTS.examples[0] })).toBeNull();
});

test("the example questions are chips in the design's colours", () => {
  expect(styles).toMatch(/\.hints button\.example \{[^}]*background: var\(--accent-soft\)/);
  expect(styles).toMatch(/\.hints button\.example \{[^}]*color: var\(--accent-ink\)/);
  // Not boxed like the other lists' items.
  expect(styles).toMatch(/\.hints li \{[^}]*border: 0;[^}]*background: none/);
});

// --- Teach me (R41h) ---

// The chat's server, answering each prompt with the next of `replies`.
function lessonServer(...replies: object[]) {
  let n = 0;
  return chatServer([], () =>
    Response.json({
      role: "assistant",
      turn: 2 * n + 1,
      ...replies[Math.min(n++, replies.length - 1)],
    }),
  );
}

function sentBodies(server: ReturnType<typeof chatServer>) {
  return server.mock.calls
    .filter(([url, init]) => url === "/api/chat" && init?.method === "POST")
    .map(([, init]) => JSON.parse(init!.body as string) as Record<string, unknown>);
}

const ZETA = { topic: "Zeta Function", part: 0, active: true, parts: 3 };

// The server's saved settings turn Teach me on (it is off by default); every other request goes
// to the server the test set up.
function teachMeOn() {
  const server = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) =>
      url === "/api/settings" ? Response.json({ teach_me: true }) : server(url, init),
    ),
  );
}

test("Teach me asks which topic, and clicking one starts the lesson", async () => {
  const server = lessonServer(
    {
      content: "What would you like to learn about?",
      lesson: null,
      choices: [
        { label: "Zeta Function", prompt: "Teach me about Zeta Function" },
        { label: "Everything, from the start", prompt: "Teach me everything from the start" },
      ],
    },
    { content: "The zeta function adds up powers.", lesson: ZETA, choices: [] },
  );
  vi.spyOn(console, "info").mockImplementation(() => {});
  teachMeOn();
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Teach me" }));
  });
  const choices = within(await screen.findByRole("list", { name: "Choices" }));
  await waitFor(() =>
    expect((choices.getAllByRole("button")[0] as HTMLButtonElement).disabled).toBe(false),
  );
  expect(choices.getAllByRole("button").map((b) => b.textContent)).toEqual([
    "Zeta Function",
    "Everything, from the start",
  ]);
  await act(async () => {
    fireEvent.click(choices.getByRole("button", { name: "Zeta Function" }));
  });
  expect(await screen.findByText("The zeta function adds up powers.")).toBeTruthy();
  expect(screen.queryByRole("list", { name: "Choices" })).toBeNull(); // gone once one is picked
  expect(screen.getByText("Lesson: Zeta Function · part 1 of 3")).toBeTruthy();
  expect(sentBodies(server).map((b) => [b.prompt, b.lesson])).toEqual([
    ["Teach me", undefined],
    ["Teach me about Zeta Function", undefined],
  ]);
  expect(loadLesson()).toEqual(ZETA); // kept on this browser
});

test("turning Teach me off hides its choices and keeps the lesson's place", async () => {
  localStorage.setItem("imageskin.lesson", JSON.stringify({ ...ZETA, active: false }));
  lessonServer({
    content: "What would you like to learn about?",
    lesson: { ...ZETA, active: false },
    choices: [{ label: "Carry on with Zeta Function", prompt: "Teach me about Zeta Function" }],
  });
  let teachMe = true;
  const server = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url !== "/api/settings") return server(url, init);
      if (init?.method === "PATCH") teachMe = JSON.parse(String(init.body)).teach_me;
      return Response.json({ teach_me: teachMe });
    }),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Teach me" }));
  });
  expect(await screen.findByRole("list", { name: "Choices" })).toBeTruthy();
  await openSettings();
  await act(async () => {
    fireEvent.click(screen.getByRole("checkbox", { name: "Teach me" }));
  });
  expect(teachMe).toBe(false);
  await returnToApp();
  await screen.findByText("Ask a question to start the conversation.");
  expect(screen.queryByRole("list", { name: "Choices" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Teach me" })).toBeNull();
  expect(loadLesson()).toEqual({ ...ZETA, active: false }); // kept for when it is back on
});

// --- Quiz me (R41i) ---

const RAIN_QUIZ = {
  topic: "Rain",
  number: 1,
  question: "What makes rain?",
  part: 0,
  asked: ["What makes rain?"],
  right: 0,
  partly: 0,
  review: [],
  source: "3f1c",
  questions: 5,
};

function quizMeOn() {
  const server = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) =>
      url === "/api/settings" ? Response.json({ quiz_me: true }) : server(url, init),
    ),
  );
}

test("Quiz me asks which topic, then each answer is sent with the quiz", async () => {
  const second = { ...RAIN_QUIZ, number: 2, question: "Where does it fall?", right: 1 };
  const server = lessonServer(
    {
      content: "What would you like to be quizzed on?",
      quiz: null,
      choices: [{ label: "Rain", prompt: "Quiz me on Rain" }],
    },
    { content: "Question 1 of 5: What makes rain?", quiz: RAIN_QUIZ, choices: [] },
    { content: "Right! Question 2 of 5: Where does it fall?", quiz: second, choices: [] },
    { content: "OK, we'll stop the quiz here.", quiz: null, choices: [] },
  );
  const info = vi.spyOn(console, "info").mockImplementation(() => {});
  quizMeOn();
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  expect(screen.queryByRole("button", { name: "Teach me" })).toBeNull(); // only Quiz me is on
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Quiz me" }));
  });
  const choices = within(await screen.findByRole("list", { name: "Choices" }));
  const rain = choices.getByRole("button", { name: "Rain" }) as HTMLButtonElement;
  await waitFor(() => expect(rain.disabled).toBe(false));
  await act(async () => {
    fireEvent.click(rain);
  });
  expect(await screen.findByText("Quiz: Rain · question 1 of 5")).toBeTruthy();
  expect(loadQuiz()).toEqual(RAIN_QUIZ); // kept on this browser
  expect(info).toHaveBeenCalledWith("Quiz: Rain, question 1");

  const send = screen.getByRole("button", { name: "Send" }) as HTMLButtonElement;
  fireEvent.input(promptBox(), { target: { value: "Clouds" } });
  await waitFor(() => expect(send.disabled).toBe(false));
  await act(async () => {
    fireEvent.click(send);
  });
  expect(await screen.findByText("Quiz: Rain · question 2 of 5")).toBeTruthy();
  const stop = screen.getByRole("button", { name: "Stop the quiz" }) as HTMLButtonElement;
  await waitFor(() => expect(stop.disabled).toBe(false));
  await act(async () => {
    fireEvent.click(stop);
  });
  await waitFor(() => expect(screen.queryByText(/^Quiz: Rain/)).toBeNull());
  expect(loadQuiz()).toBeNull();
  const { questions: _, ...sentQuiz } = RAIN_QUIZ; // the server's count isn't sent back
  expect(sentBodies(server).map((b) => [b.prompt, b.quiz])).toEqual([
    ["Quiz me", undefined],
    ["Quiz me on Rain", undefined],
    ["Clouds", sentQuiz],
    ["Stop the quiz", { ...sentQuiz, number: 2, question: "Where does it fall?", right: 1 }],
  ]);
});

test("a quiz kept on this browser is shown after a reload, and only with Quiz me on", async () => {
  localStorage.setItem("imageskin.quiz", JSON.stringify({ ...RAIN_QUIZ, number: 3 }));
  lessonServer({ content: "Hi" });
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  expect(screen.queryByText(/^Quiz: Rain/)).toBeNull(); // Quiz me is off
  expect(screen.queryByRole("button", { name: "Quiz me" })).toBeNull();
  cleanup();
  quizMeOn();
  await openAt("#/chat");
  expect(await screen.findByText("Quiz: Rain · question 3 of 5")).toBeTruthy();
});

test("a quiz kept that can't be read is dropped", () => {
  for (const kept of ["{", JSON.stringify({ topic: "Rain" }), JSON.stringify([1])]) {
    localStorage.setItem("imageskin.quiz", kept);
    expect(loadQuiz()).toBeNull();
  }
  localStorage.setItem(
    "imageskin.quiz",
    JSON.stringify({ topic: "Rain", number: 2, question: "Q?", part: 0, asked: [1, "Q?"] }),
  );
  expect(loadQuiz()).toEqual({
    topic: "Rain",
    number: 2,
    question: "Q?",
    part: 0,
    asked: ["Q?"],
    right: 0,
    partly: 0,
    review: [],
    source: "",
    questions: undefined,
  });
});

// The server's saved settings turn both Teach me and Quiz me on, and the hints have examples.
function teachAndQuizOn(...replies: object[]) {
  const server = lessonServer(...replies);
  const answers = server.getMockImplementation()!;
  server.mockImplementation(async (url, init) => {
    if (url === "/api/settings") return Response.json({ teach_me: true, quiz_me: true });
    if (url === "/api/chat/hints") return Response.json(RIEMANN_HINTS);
    return answers(url, init);
  });
  return server;
}

test("a quiz started from a lesson's summary shows only the quiz's own controls", async () => {
  localStorage.setItem("imageskin.lesson", JSON.stringify(ZETA));
  const zetaQuiz = { ...RAIN_QUIZ, topic: "Zeta Function", question: "What is zeta?" };
  const server = teachAndQuizOn(
    {
      content: "In short, zeta.",
      lesson: ZETA,
      choices: [{ label: "Quiz me on Zeta Function", prompt: "Quiz me on Zeta Function" }],
    },
    { content: "Question 1 of 5: What is zeta?", lesson: ZETA, quiz: zetaQuiz, choices: [] },
  );
  vi.spyOn(console, "info").mockImplementation(() => {});
  await openAt("#/chat");
  expect(await screen.findByText("Lesson: Zeta Function · part 1 of 3")).toBeTruthy();
  expect(await screen.findByRole("button", { name: RIEMANN_HINTS.examples[0] })).toBeTruthy();
  const next = screen.getByRole("button", { name: "Next" }) as HTMLButtonElement;
  await waitFor(() => expect(next.disabled).toBe(false));
  await act(async () => {
    fireEvent.click(next);
  });
  const choices = within(await screen.findByRole("list", { name: "Choices" }));
  const quizMe = choices.getByRole("button", { name: "Quiz me on Zeta Function" });
  await waitFor(() => expect((quizMe as HTMLButtonElement).disabled).toBe(false));
  await act(async () => {
    fireEvent.click(quizMe);
  });
  expect(await screen.findByText("Quiz: Zeta Function · question 1 of 5")).toBeTruthy();
  // Whatever is sent now is taken as the answer, so nothing else that sends a prompt is shown.
  for (const name of ["Next", "Say it more simply", "Stop the lesson", "Teach me", "Quiz me"]) {
    expect(screen.queryByRole("button", { name })).toBeNull();
  }
  expect(screen.queryByText("Lesson: Zeta Function · part 1 of 3")).toBeNull();
  expect(screen.queryByRole("button", { name: RIEMANN_HINTS.examples[0] })).toBeNull();
  expect(screen.queryByRole("list", { name: "Choices" })).toBeNull();
  expect(screen.getByRole("button", { name: "Stop the quiz" })).toBeTruthy();
  expect(sentBodies(server).map((b) => b.prompt)).toEqual(["Next", "Quiz me on Zeta Function"]);
});

test("turning Quiz me off drops its choices, though Teach me is still on", async () => {
  const server = teachAndQuizOn({
    content: "What would you like to be quizzed on?",
    quiz: null,
    choices: [{ label: "Rain", prompt: "Quiz me on Rain" }],
  });
  const answers = server.getMockImplementation()!;
  let quizMe = true;
  server.mockImplementation(async (url, init) => {
    if (url !== "/api/settings") return answers(url, init);
    if (init?.method === "PATCH") quizMe = JSON.parse(String(init.body)).quiz_me;
    return Response.json({ teach_me: true, quiz_me: quizMe });
  });
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Quiz me" }));
  });
  expect(await screen.findByRole("list", { name: "Choices" })).toBeTruthy();
  await openSettings();
  await act(async () => {
    fireEvent.click(screen.getByRole("checkbox", { name: "Quiz me" }));
  });
  expect(quizMe).toBe(false);
  await returnToApp();
  expect(await screen.findByRole("button", { name: "Teach me" })).toBeTruthy(); // still on
  expect(screen.queryByRole("list", { name: "Choices" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Quiz me" })).toBeNull();
});

test("Next and more simply send the lesson along, and the place shown follows it", async () => {
  localStorage.setItem("imageskin.lesson", JSON.stringify(ZETA));
  const server = lessonServer(
    { content: "Part two.", lesson: { ...ZETA, part: 1 } },
    { content: "Part two, simply.", lesson: { ...ZETA, part: 1 } },
    { content: "In short, zeta.", lesson: { ...ZETA, part: 3 } },
  );
  teachMeOn();
  await openAt("#/chat");
  expect(await screen.findByText("Lesson: Zeta Function · part 1 of 3")).toBeTruthy();
  for (const label of ["Next", "Say it more simply", "Next"]) {
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: label }));
    });
    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(
        false,
      ),
    );
  }
  expect(screen.getByText("Lesson: Zeta Function · summary")).toBeTruthy();
  const sent = (prompt: string, part: number) => ({
    prompt,
    reply_id: expect.any(String),
    lesson: { topic: "Zeta Function", part, active: true }, // without the count of parts
  });
  expect(sentBodies(server)).toEqual([
    sent("Next", 0),
    sent("Say it more simply", 1),
    sent("Next", 1),
  ]);
});

test("stopping hides the lesson but keeps its place; finishing forgets it", async () => {
  localStorage.setItem("imageskin.lesson", JSON.stringify(ZETA));
  lessonServer(
    { content: "OK, we'll stop here.", lesson: { ...ZETA, active: false } },
    { content: "That's everything.", lesson: null },
  );
  teachMeOn();
  await openAt("#/chat");
  const stop = await screen.findByRole("button", { name: "Stop the lesson" });
  await act(async () => {
    fireEvent.click(stop);
  });
  await screen.findByText("OK, we'll stop here.");
  expect(screen.queryByText(/^Lesson:/)).toBeNull();
  expect(loadLesson()).toEqual({ ...ZETA, active: false });
  fireEvent.input(promptBox(), { target: { value: "Teach me about Zeta Function" } });
  await waitFor(() =>
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(
      false,
    ),
  );
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await screen.findByText("That's everything.");
  expect(loadLesson()).toBeNull();
});

test("a reply that says nothing about lessons leaves the lesson as it was", async () => {
  localStorage.setItem("imageskin.lesson", JSON.stringify(ZETA));
  chatServer([], () => Response.json({ role: "assistant", content: "Hi." }));
  teachMeOn();
  await openAt("#/chat");
  fireEvent.input(await screen.findByRole("textbox", { name: "Your message" }), {
    target: { value: "Hello" },
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await screen.findByText("Hi.");
  expect(loadLesson()).toEqual(ZETA);
});

test("a lesson saved wrongly, or storage that can't be read, means no lesson", () => {
  for (const saved of ["{", '"text"', '{"topic": 3, "part": 0}', '{"topic": "A", "part": -1}']) {
    localStorage.setItem("imageskin.lesson", saved);
    expect(loadLesson()).toBeNull();
  }
  localStorage.setItem("imageskin.lesson", '{"topic": "A", "part": 2}');
  expect(loadLesson()).toEqual({ topic: "A", part: 2, active: true, parts: undefined });
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  expect(loadLesson()).toBeNull();
});

test("a lesson that can't be kept is logged, and the chat goes on", async () => {
  lessonServer({ content: "Zeta.", lesson: ZETA });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("full");
  });
  vi.spyOn(console, "info").mockImplementation(() => {});
  teachMeOn();
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Teach me" }));
  });
  expect(await screen.findByText("Lesson: Zeta Function · part 1 of 3")).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith("Could not keep the lesson", expect.any(Error));
});

test("with Teach me off, there's no Teach me button and the saved lesson stays", async () => {
  localStorage.setItem("imageskin.lesson", JSON.stringify(ZETA));
  const server = lessonServer({ content: "Hi.", lesson: null });
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  expect(screen.queryByRole("button", { name: "Teach me" })).toBeNull();
  expect(screen.queryByText(/^Lesson:/)).toBeNull();
  fireEvent.input(promptBox(), { target: { value: "Teach me" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await screen.findByText("Hi.");
  expect(sentBodies(server)[0].lesson).toBeUndefined();
  expect(loadLesson()).toEqual(ZETA); // still there for when Teach me is turned on
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
  // R41d: no addresses or program names for the participant; the details go to the console.
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

test("the status waits for a reply's one video to start playing, not just to be made", async () => {
  // Review on PR #80: the status went as soon as the video was made, before it played.
  chatServer(
    [],
    () => Response.json({ role: "assistant", content: "Hi there.", turn: 1, streamed: false }),
    () => Response.json({ video: "/api/chat/videos/1" }),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Hello" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toMatch(/^\/api\/chat\/videos\/1/));
  await act(() => new Promise((done) => setTimeout(done, 20))); // made and handed to the player
  expect(screen.getByText("Getting ready to say it…")).toBeTruthy();
  fireEvent.playing(shownVideo());
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
});

test("the status waits for a short streamed reply's only clip to start playing", async () => {
  chatServer(
    [],
    () => Response.json({ role: "assistant", content: "Yes.", streamed: true }),
    undefined,
    () => Response.json(clipsMade(["/api/chat/clips/x/1"], true)),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Ready?" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await screen.findByText("Yes.");
  await act(() => new Promise((done) => setTimeout(done, 20))); // every clip made
  expect(screen.getByText("Getting ready to say it…")).toBeTruthy();
  fireEvent.playing(shownVideo());
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
});

test("the status stays when the first clip is broken, until a later one plays", async () => {
  // Review on PR #80: passing over a broken first clip cleared the status before anyone spoke.
  vi.spyOn(console, "error").mockImplementation(() => {});
  chatServer(
    [],
    () => Response.json({ role: "assistant", content: "One. Two.", streamed: true }),
    undefined,
    () => Response.json(clipsMade(["/api/chat/clips/x/1", "/api/chat/clips/x/2"], true)),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Count" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await screen.findByText("One. Two.");
  await waitFor(() => expect(shownVideo()?.getAttribute("src")).toBe("/api/chat/clips/x/1"));
  fireEvent.error(shownVideo()); // clip 1 can't be played: passed over
  await waitFor(() => expect(shownVideo().getAttribute("src")).toBe("/api/chat/clips/x/2"));
  expect(screen.getByText("Getting ready to say it…")).toBeTruthy(); // nobody has spoken yet
  fireEvent.playing(shownVideo());
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
});

test("the status goes when every clip is broken, as nothing will be said aloud", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  chatServer(
    [],
    () => Response.json({ role: "assistant", content: "One.", streamed: true }),
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
  await waitFor(() => expect(shownVideo()).not.toBeNull());
  await act(() => new Promise((done) => setTimeout(done, 20))); // every clip made
  fireEvent.error(shownVideo());
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
});

test("a reply with nothing to say aloud leaves no status", async () => {
  chatServer(
    [],
    () => Response.json({ role: "assistant", content: "```code```", turn: 1, streamed: false }),
    () => Response.json({ video: null }),
  );
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Code?" } });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
  });
  await screen.findByText("```code```");
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
  expect(screen.queryByText("Thinking…")).toBeNull();
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
  expect(screen.getByText("Getting ready to say it…")).toBeTruthy(); // until it plays (R41d)
  fireEvent.playing(video);
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
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
  fireEvent.playing(video);
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
  fireEvent.playing(video); // its first clip, already here, plays
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

test("the stage takes the photo's shape, so there are no empty bands around the person", () => {
  // Larry on PR #80: a wide video left white bands above and below it in a fixed-size box.
  const { rerender } = render(<Stage idle="loading" onIdle={() => {}} ratio={16 / 9} />);
  const stage = document.querySelector(".stage") as HTMLElement;
  expect(Number(stage.style.getPropertyValue("--ratio"))).toBeCloseTo(16 / 9);
  rerender(<Stage idle="loading" onIdle={() => {}} />); // no size known: a 4:3 box
  expect(stage.style.getPropertyValue("--ratio")).toBe("");
});

test("the chat draws the person's frame only once it knows the photo's shape", async () => {
  // Review on PR #80: the frame was drawn 4:3 and then took the photo's shape, changing size.
  const [photo, answerPhoto] = later();
  const server = chatServer([], () => Response.json({}));
  const answers = server.getMockImplementation()!;
  server.mockImplementation(async (url, init) =>
    url === "/api/chat/photo" ? photo() : answers(url, init),
  );
  const info = vi.spyOn(console, "info").mockImplementation(() => {});
  await openAt("#/chat");
  await act(() => new Promise((done) => setTimeout(done, 20)));
  expect(document.querySelector(".stage")).toBeNull(); // not drawn at a guessed size
  await act(async () =>
    answerPhoto(Response.json({ url: "/api/uploads/photos/p1", width: 1280, height: 720 })),
  );
  const stage = (await waitFor(() => {
    const found = document.querySelector(".stage");
    expect(found).not.toBeNull();
    return found;
  })) as HTMLElement;
  expect(Number(stage.style.getPropertyValue("--ratio"))).toBeCloseTo(16 / 9); // from the start
  expect(stage.querySelector("img.still")?.getAttribute("src")).toBe("/api/uploads/photos/p1");
  expect(info).toHaveBeenCalledWith("Chat photo 1280x720");
});

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

test("the stage plays the idle video at the photo's own address, once that is known", () => {
  const { rerender } = render(<Stage idle="loading" onIdle={() => {}} idleUrl={null} />);
  expect(document.querySelector(".stage video")).toBeNull(); // not the person before's
  rerender(<Stage idle="loading" onIdle={() => {}} idleUrl="/api/chat/idle?photo=boss" />);
  const video = document.querySelector(".stage video") as HTMLVideoElement;
  expect(video.getAttribute("src")).toBe("/api/chat/idle?photo=boss");
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

function stopButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: "Stop" }) as HTMLButtonElement;
}

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
  // Always shown, first and in red, so it is easy to find; nothing to stop yet.
  expect(stopButton().disabled).toBe(true);
  expect(stopButton().className).toBe("stop");
  expect(document.querySelector(".sound-controls button")).toBe(stopButton());
  fireEvent.input(promptBox(), { target: { value: "Tell me a story" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await waitFor(() => expect(document.querySelector("video.reply-video")).not.toBeNull());
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  expect(pause).toHaveBeenCalled(); // the clip stops at once
  expect(shownVideo().autoplay).toBe(false); // and doesn't start again
  expect(stopButton().disabled).toBe(true);
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
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(
      false,
    ),
  ); // the next prompt can be sent
});

test("Stop while it is thinking stops the thinking, and the prompt goes back in the box", async () => {
  // Larry's test of PR #129: Stop left the LLM thinking.
  const [answer, reply] = later();
  const fetchMock = chatServer([], answer);
  const info = vi.spyOn(console, "info").mockImplementation(() => {});
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  fireEvent.input(promptBox(), { target: { value: "Tell me a story" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText("Thinking…");
  expect(stopButton().disabled).toBe(false);
  fireEvent.click(stopButton());
  expect(screen.getByText("Stopping…")).toBeTruthy(); // until the server has cut the LLM off
  expect(fetchMock.mock.calls.filter(([url]) => url.endsWith("/stop"))).toHaveLength(1);
  await act(async () => {
    reply(Response.json({ detail: "Stopped." }, { status: 409 }));
  });
  await waitFor(() => expect(promptBox().value).toBe("Tell me a story"));
  expect(screen.queryByText("Stopping…")).toBeNull();
  expect(screen.queryByText(CANT_ANSWER)).toBeNull(); // nothing went wrong
  expect(screen.getByText("Ask a question to start the conversation.")).toBeTruthy();
  expect(info).toHaveBeenCalledWith("Prompt stopped while it was answered");
  expect(error).not.toHaveBeenCalledWith("Could not get a reply", expect.anything());
  expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(false);
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
    expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(
      false,
    ),
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

test("Stop can be clicked until the last clip has played", async () => {
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
  await waitFor(() => expect(shownVideo()).not.toBeNull());
  fireEvent.playing(shownVideo());
  await waitFor(() => expect(screen.queryByText("Getting ready to say it…")).toBeNull());
  expect(stopButton().disabled).toBe(false); // still playing
  fireEvent.ended(shownVideo());
  expect(stopButton().disabled).toBe(true);
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

test("the timing metrics are hidden until turned on on the Settings page", async () => {
  const saved = { show_metrics: false };
  settingsServer(saved);
  await openAt("#/setup");
  await screen.findByText("52 of 200 · about 12 min 5 s left"); // how long is left stays
  expect(screen.queryByText("Done in 31 s")).toBeNull();
  expect(screen.queryByRole("checkbox", { name: "Show timing metrics" })).toBeNull();

  await openSettings();
  const box = screen.getByRole("checkbox", { name: "Show timing metrics" }) as HTMLInputElement;
  expect(box.checked).toBe(false);
  await act(async () => {
    fireEvent.click(box);
  });
  expect(saved.show_metrics).toBe(true);
  expect(box.checked).toBe(true);
  await returnToApp();
  expect(window.location.hash).toBe("#/setup");
  expect(await screen.findByText("Done in 31 s")).toBeTruthy();
  expect(screen.queryByRole("checkbox", { name: "Show timing metrics" })).toBeNull();

  cleanup(); // a reload: the saved setting is read again
  await openAt("#/setup");
  expect(await screen.findByText("Done in 31 s")).toBeTruthy();
});

test("Teach me is off until turned on on the Settings page (Larry, 2026-10-15)", async () => {
  const saved: { show_metrics: boolean; teach_me?: boolean } = { show_metrics: false };
  settingsServer(saved);
  await openAt("#/setup");
  await screen.findByText("52 of 200 · about 12 min 5 s left");
  await openSettings();
  const box = screen.getByRole("checkbox", { name: "Teach me" }) as HTMLInputElement;
  expect(box.checked).toBe(false);
  await act(async () => {
    fireEvent.click(box);
  });
  expect(saved.teach_me).toBe(true);
  expect(box.checked).toBe(true);
});

test("Quiz me is off until turned on on the Settings page", async () => {
  const saved: { show_metrics: boolean; quiz_me?: boolean } = { show_metrics: false };
  settingsServer(saved);
  await openAt("#/setup");
  await screen.findByText("52 of 200 · about 12 min 5 s left");
  await openSettings();
  const box = screen.getByRole("checkbox", { name: "Quiz me" }) as HTMLInputElement;
  expect(box.checked).toBe(false);
  await act(async () => {
    fireEvent.click(box);
  });
  expect(saved.quiz_me).toBe(true);
  expect(box.checked).toBe(true);
});

test("Assessment is off until turned on on the Settings page", async () => {
  const saved: { show_metrics: boolean; assessment?: boolean } = { show_metrics: false };
  settingsServer(saved);
  await openAt("#/setup");
  await screen.findByText("52 of 200 · about 12 min 5 s left");
  await openSettings();
  const box = screen.getByRole("checkbox", { name: "Assessment" }) as HTMLInputElement;
  expect(box.checked).toBe(false);
  await act(async () => {
    fireEvent.click(box);
  });
  expect(saved.assessment).toBe(true);
  expect(box.checked).toBe(true);
});

test("a setting that can't be saved says so and stays as it was", async () => {
  settingsServer({ show_metrics: false }, false);
  await openAt("#/setup");
  await screen.findByText("52 of 200 · about 12 min 5 s left");
  await openSettings();
  await act(async () => {
    fireEvent.click(screen.getByRole("checkbox", { name: "Show timing metrics" }));
  });
  expect(await screen.findByText("The setting could not be changed. Try again.")).toBeTruthy();
  expect(screen.queryByText("Done in 31 s")).toBeNull();
  const box = screen.getByRole("checkbox", { name: "Show timing metrics" }) as HTMLInputElement;
  expect(box.checked).toBe(false);
});

test("in the participant view a chat that isn't set up asks for the host, not setup", async () => {
  serverWithConsent(true);
  const server = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/settings") return Response.json({ show_metrics: false, view: "participant" });
      if (url === "/api/review") return Response.json({ accepted: false });
      return server(url, init);
    }),
  );
  await openAt("#/chat");
  expect(
    await screen.findByText("The chat isn't ready yet. Ask your host to finish setting it up."),
  ).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Go to setup" })).toBeNull();
});

// --- Copy chat, with Debug on (Larry, 2026-10-15) ---

const TALK: Turn[] = [
  { role: "user", content: "Quiz me on primes" },
  { role: "assistant", content: "Question 1 of 5: Euler's approach." },
  { role: "user", content: "What's the question?" },
  { role: "assistant", content: "Not quite." },
  { role: "user", content: "Hello" },
  { role: "assistant", content: "Hi." },
];

test("the chat as text is the last N exchanges, oldest first", () => {
  expect(chatText(TALK, 2)).toBe(
    [
      "Chat: the last 2 of 3 exchanges",
      "You: What's the question?",
      "Reply: Not quite.",
      "You: Hello",
      "Reply: Hi.",
    ].join("\n\n"),
  );
  expect(chatText(TALK, 9).startsWith("Chat: the last 3 of 3 exchanges\n\nYou: Quiz me")).toBe(
    true,
  );
  // A prompt still waiting for its reply isn't an exchange yet (review on PR #89).
  expect(chatText([...TALK, { role: "user", content: "More?" }], 1)).toBe(
    "Chat: the last 1 of 3 exchanges\n\nYou: Hello\n\nReply: Hi.",
  );
});

function debugOn() {
  const server = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) =>
      url === "/api/settings" ? Response.json({ debug: true }) : server(url, init),
    ),
  );
}

test("Copy chat copies every exchange unless fewer are asked for", async () => {
  chatServer(TALK, () => Response.json({}));
  const writeText = vi.fn(async (_text: string) => {});
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  const info = vi.spyOn(console, "info").mockImplementation(() => {});
  debugOn();
  await openAt("#/chat");
  const copy = await screen.findByRole("button", { name: "Copy chat" });
  const count = screen.getByRole("spinbutton") as HTMLInputElement;
  expect(count.value).toBe("3"); // all of them
  await act(async () => {
    fireEvent.click(copy);
  });
  expect(writeText).toHaveBeenLastCalledWith(chatText(TALK, 3));
  expect(screen.getByText("Copied")).toBeTruthy();
  expect(info).toHaveBeenCalledWith(expect.stringMatching(/^Chat copied \(3 of 3 exchanges/));

  fireEvent.change(count, { target: { value: "1" } });
  expect(screen.queryByText("Copied")).toBeNull();
  await act(async () => {
    fireEvent.click(copy);
  });
  expect(writeText).toHaveBeenLastCalledWith(chatText(TALK, 1));
  fireEvent.change(count, { target: { value: "50" } });
  expect(count.value).toBe("3"); // no more than there are
});

test("where the browser won't copy, the chat is shown to copy by hand", async () => {
  chatServer(TALK, () => Response.json({}));
  const writeText = vi.fn(async () => {
    throw new Error("Not allowed");
  });
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  debugOn();
  await openAt("#/chat");
  const copy = await screen.findByRole("button", { name: "Copy chat" });
  await act(async () => {
    fireEvent.click(copy);
  });
  const box = screen.getByRole("textbox", { name: "Chat to copy" }) as HTMLTextAreaElement;
  expect(box.value).toBe(chatText(TALK, 3));
  expect(error).toHaveBeenCalledWith("Could not copy the chat", expect.any(Error));
});

test("a copy is no longer shown as done once the chat moves on", async () => {
  const [answer, reply] = later();
  chatServer(TALK, answer);
  const writeText = vi.fn(async (_text: string) => {});
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  vi.spyOn(console, "info").mockImplementation(() => {});
  debugOn();
  await openAt("#/chat");
  const copy = await screen.findByRole("button", { name: "Copy chat" });
  await act(async () => {
    fireEvent.click(copy);
  });
  expect(screen.getByText("Copied")).toBeTruthy();

  // A question asked: while it waits for its reply, it isn't copied, and the copy before it is
  // no longer the chat as it is.
  const send = screen.getByRole("button", { name: "Send" }) as HTMLButtonElement;
  fireEvent.input(promptBox(), { target: { value: "More?" } });
  await waitFor(() => expect(send.disabled).toBe(false));
  await act(async () => {
    fireEvent.click(send);
  });
  expect(screen.queryByText("Copied")).toBeNull();
  expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe("3");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Copy chat" }));
  });
  expect(writeText).toHaveBeenLastCalledWith(chatText(TALK, 3)); // not the waiting prompt
  expect(writeText.mock.calls[1][0]).not.toContain("More?");

  await act(async () => {
    reply(Response.json({ role: "assistant", content: "Lots more.", turn: 7 }));
  });
  expect(await screen.findByText("Lots more.")).toBeTruthy();
  expect(screen.queryByText("Copied")).toBeNull(); // copied before the reply came
  expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe("4");
});

test("text to copy by hand goes once the chat moves on", async () => {
  chatServer(TALK, () => Response.json({ role: "assistant", content: "Lots more.", turn: 7 }));
  const writeText = vi.fn(async () => {
    throw new Error("Not allowed");
  });
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  vi.spyOn(console, "error").mockImplementation(() => {});
  debugOn();
  await openAt("#/chat");
  const copy = await screen.findByRole("button", { name: "Copy chat" });
  await act(async () => {
    fireEvent.click(copy);
  });
  expect(screen.getByRole("textbox", { name: "Chat to copy" })).toBeTruthy();
  const send = screen.getByRole("button", { name: "Send" }) as HTMLButtonElement;
  fireEvent.input(promptBox(), { target: { value: "More?" } });
  await waitFor(() => expect(send.disabled).toBe(false));
  await act(async () => {
    fireEvent.click(send);
  });
  expect(await screen.findByText("Lots more.")).toBeTruthy();
  expect(screen.queryByRole("textbox", { name: "Chat to copy" })).toBeNull();
});

test("a copy that finishes after the chat moved on isn't shown as done", async () => {
  chatServer(TALK, () => Response.json({ role: "assistant", content: "Lots more.", turn: 7 }));
  let finish: () => void = () => {};
  const writeText = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)));
  vi.stubGlobal("navigator", { ...navigator, clipboard: { writeText } });
  vi.spyOn(console, "info").mockImplementation(() => {});
  debugOn();
  await openAt("#/chat");
  const copy = await screen.findByRole("button", { name: "Copy chat" });
  await act(async () => {
    fireEvent.click(copy);
  });
  const send = screen.getByRole("button", { name: "Send" }) as HTMLButtonElement;
  fireEvent.input(promptBox(), { target: { value: "More?" } });
  await waitFor(() => expect(send.disabled).toBe(false));
  await act(async () => {
    fireEvent.click(send);
  });
  expect(await screen.findByText("Lots more.")).toBeTruthy();
  await act(async () => {
    finish();
  });
  expect(screen.queryByText("Copied")).toBeNull();
});

test("Copy chat shows only with Debug on, and once there is something to copy", async () => {
  chatServer(TALK, () => Response.json({}));
  await openAt("#/chat");
  await screen.findByText("Hi.");
  expect(screen.queryByRole("button", { name: "Copy chat" })).toBeNull();
  cleanup();
  chatServer([], () => Response.json({}));
  debugOn();
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  expect(screen.queryByRole("button", { name: "Copy chat" })).toBeNull();
});

test("Debug is off until turned on on the Settings page", async () => {
  const saved: { show_metrics: boolean; debug?: boolean } = { show_metrics: false };
  settingsServer(saved);
  await openAt("#/setup");
  await screen.findByText("52 of 200 · about 12 min 5 s left");
  await openSettings();
  const box = screen.getByRole("checkbox", { name: "Debug" }) as HTMLInputElement;
  expect(box.checked).toBe(false);
  await act(async () => {
    fireEvent.click(box);
  });
  expect(saved.debug).toBe(true);
  expect(box.checked).toBe(true);
});

// --- Assessment (R41j) ---

const ASSESSMENT = {
  total: 15,
  number: 1,
  topic: "Rain",
  level: 0,
  part: 0,
  question: "What is one fact about Rain?",
  source: "3f1c",
  plan: "9a2e",
  answers: [],
};

test("the Assessment button asks the questions, and only its own controls show", async () => {
  const second = {
    ...ASSESSMENT,
    number: 2,
    level: 1,
    question: "How would you explain Rain?",
    answers: [{ topic: "Rain", level: 0, question: "Q?", verdict: "right", correct: "It falls." }],
  };
  const server = teachAndQuizOn(
    { content: "Let's see. Question 1 of 15: …", assessment: ASSESSMENT, choices: [] },
    { content: "Thanks. Question 2 of 15: …", assessment: second, choices: [] },
    {
      content: "OK, we'll stop the assessment here. Go over Rain again.",
      assessment: null,
      choices: [{ label: "Teach me about Rain", prompt: "Teach me about Rain" }],
    },
  );
  const answers = server.getMockImplementation()!;
  server.mockImplementation(async (url, init) =>
    url === "/api/settings"
      ? Response.json({ teach_me: true, quiz_me: true, assessment: true })
      : answers(url, init),
  );
  const info = vi.spyOn(console, "info").mockImplementation(() => {});
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  const start = screen.getByRole("button", { name: "Assessment" }) as HTMLButtonElement;
  await waitFor(() => expect(start.disabled).toBe(false));
  await act(async () => {
    fireEvent.click(start);
  });
  expect(await screen.findByText("Assessment · question 1 of 15")).toBeTruthy();
  expect(loadAssessment()).toEqual(ASSESSMENT); // kept on this browser
  expect(info).toHaveBeenCalledWith("Assessment: question 1 of 15");
  for (const name of ["Teach me", "Quiz me", "Assessment", RIEMANN_HINTS.examples[0]]) {
    expect(screen.queryByRole("button", { name })).toBeNull();
  }

  const send = screen.getByRole("button", { name: "Send" }) as HTMLButtonElement;
  fireEvent.input(promptBox(), { target: { value: "It falls" } });
  await waitFor(() => expect(send.disabled).toBe(false));
  await act(async () => {
    fireEvent.click(send);
  });
  expect(await screen.findByText("Assessment · question 2 of 15")).toBeTruthy();
  const stop = screen.getByRole("button", { name: "Stop the assessment" }) as HTMLButtonElement;
  await waitFor(() => expect(stop.disabled).toBe(false));
  await act(async () => {
    fireEvent.click(stop);
  });
  await waitFor(() => expect(screen.queryByText(/^Assessment ·/)).toBeNull());
  expect(loadAssessment()).toBeNull();
  const choices = within(await screen.findByRole("list", { name: "Choices" }));
  expect(choices.getByRole("button", { name: "Teach me about Rain" })).toBeTruthy();
  expect(sentBodies(server).map((b) => [b.prompt, b.assessment])).toEqual([
    ["Assess me", undefined],
    ["It falls", ASSESSMENT],
    ["Stop the assessment", second],
  ]);
});

test("an assessment kept on this browser shows only with Assessment on", async () => {
  localStorage.setItem("imageskin.assessment", JSON.stringify({ ...ASSESSMENT, number: 4 }));
  lessonServer({ content: "Hi" });
  await openAt("#/chat");
  await screen.findByText("Ask a question to start the conversation.");
  expect(screen.queryByText(/^Assessment ·/)).toBeNull();
  expect(screen.queryByRole("button", { name: "Assessment" })).toBeNull();
  cleanup();
  const server = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) =>
      url === "/api/settings" ? Response.json({ assessment: true }) : server(url, init),
    ),
  );
  await openAt("#/chat");
  expect(await screen.findByText("Assessment · question 4 of 15")).toBeTruthy();
});

test("an assessment kept that can't be read is dropped", () => {
  const bad = { ...ASSESSMENT, answers: 1 };
  for (const kept of ["{", JSON.stringify({ topic: "Rain" }), JSON.stringify(bad)]) {
    localStorage.setItem("imageskin.assessment", kept);
    expect(loadAssessment()).toBeNull();
  }
});

// Roadmap R30: setup and the conversation are saved, so a return visit skips setup.
function savedSetupServer() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: "2026-10-06T20:00:00+00:00" });
      if (url === "/api/review") return Response.json({ accepted: true, accepted_at: "2026-10-12T08:00:00Z" });
      if (url === "/api/uploads/photos/chosen") return Response.json({ id: null, chosen_by: "app" });
      if (url === "/api/chat") return Response.json({ turns: [{ role: "user", content: "My name is Larry." }] });
      if (url === "/api/prepare") return Response.json(IDLE);
      if (url.startsWith("/api/uploads/")) return Response.json([]);
      return Response.json({});
    }),
  );
}

test("a return visit to the app's address goes straight to the chat, with its history", async () => {
  vi.spyOn(console, "info").mockImplementation(() => {});
  savedSetupServer();
  await openAt("");
  await waitFor(() => expect(window.location.hash).toBe("#/chat"));
  expect(await screen.findByText("My name is Larry.")).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith("Setup is saved, so the visit starts in the chat");
});

test("home opened from another page still shows the choices", async () => {
  vi.spyOn(console, "info").mockImplementation(() => {});
  savedSetupServer();
  await openAt("#/content");
  await waitFor(() => expect(screen.getByRole("link", { name: "Home" })).toBeTruthy());
  await act(async () => {
    window.location.hash = "#/";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  expect(await screen.findByText("Welcome back")).toBeTruthy();
  expect(window.location.hash).toBe("#/");
});

test("after Delete my data, setup stays at consent until it is given again (R31)", async () => {
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: "2026-10-18" });
      if (url === "/api/data" && init?.method === "DELETE") {
        return Response.json({ files: 9, bytes: 90, left: [] });
      }
      if (url === "/api/settings") return Response.json({ view: "host" });
      return new Response("", { status: 404 });
    }),
  );
  await openAt("#/settings");
  await screen.findByRole("heading", { name: "Settings", level: 1 });
  await act(async () => {
    fireEvent.click(await screen.findByRole("button", { name: "Delete my data" }));
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete everything" }));
  });
  expect(await screen.findByText("Before you start")).toBeTruthy();
  expect(window.location.hash).toBe("#/consent");
  // Setup, opened from the top bar, still goes back to consent.
  await act(async () => {
    window.location.hash = "#/setup";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  await waitFor(() => expect(window.location.hash).toBe("#/consent"));
  expect(screen.getByText("Before you start")).toBeTruthy();
});

test("after a partial delete, setup stays at consent and the progress is gone (R31)", async () => {
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: "2026-10-18" });
      if (url === "/api/data" && init?.method === "DELETE") {
        return Response.json({ files: 8, bytes: 80, left: ["replies/idle/a.mp4"] });
      }
      if (url === "/api/settings") return Response.json({ view: "host" });
      return new Response("", { status: 404 });
    }),
  );
  localStorage.setItem("imageskin.quiz", JSON.stringify({ topic: "Primes" }));
  await openAt("#/settings");
  await screen.findByRole("heading", { name: "Settings", level: 1 });
  await act(async () => {
    fireEvent.click(await screen.findByRole("button", { name: "Delete my data" }));
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete everything" }));
  });
  // The retry message stays on the Settings page.
  expect(await screen.findByText(/1 file\(s\) could not be deleted/)).toBeTruthy();
  expect(loadQuiz()).toBeNull();
  await act(async () => {
    window.location.hash = "#/setup";
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  });
  await waitFor(() => expect(window.location.hash).toBe("#/consent"));
  expect(screen.getByText("Before you start")).toBeTruthy();
});

// --- Avatar Choice from the chat (Larry's test of R32a) ---

function avatarServer(readyMade: boolean, view: "host" | "participant" = "host", ownAccepted = false) {
  const chat = chatServer([], () => Response.json({}));
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/settings") return Response.json({ show_metrics: false, view });
    if (url === "/api/start-now" && init?.method === "DELETE") return Response.json({ accepted: true });
    if (url === "/api/review") {
      return Response.json({
        accepted: true,
        accepted_at: null,
        default_person: readyMade,
        own_sample_accepted: ownAccepted,
      });
    }
    return chat(url, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// Choosing your own over a ready-made avatar shows Before you start again, though consent was
// given before (Larry's test of PR #131).
async function chooseOwnFromChat() {
  await openAt("#/chat");
  const own = await screen.findByRole("link", { name: "Use your own photo and voice" });
  expect(own.getAttribute("href")).toBe("#/consent/own");
  await act(async () => {
    fireEvent.click(own);
  });
  expect(await screen.findByRole("heading", { name: "Before you start" })).toBeTruthy();
  expect(screen.getByText("Only use images you have the right to use. Ideally, use your own picture.")).toBeTruthy();
  fireEvent.click(screen.getByRole("checkbox"));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  });
}

test("from the chat, your own accepted sample is used at once after Before you start", async () => {
  const fetchMock = avatarServer(true, "host", true);
  await chooseOwnFromChat();
  await waitFor(() => expect(window.location.hash).toBe("#/chat"));
  expect(fetchMock).toHaveBeenCalledWith("/api/consent", expect.objectContaining({ method: "POST" }));
  expect(fetchMock).toHaveBeenCalledWith("/api/start-now", { method: "DELETE" });
});

test("from the chat, Before you start leads to setup when your own sample isn't accepted", async () => {
  const fetchMock = avatarServer(true, "host", false);
  await chooseOwnFromChat();
  await waitFor(() => expect(window.location.hash).toBe("#/setup"));
  expect(fetchMock).not.toHaveBeenCalledWith("/api/start-now", { method: "DELETE" });
});

test("a failed switch after Before you start opens setup", async () => {
  const fetchMock = avatarServer(true, "host", true);
  const passOn = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
    url === "/api/start-now" && init?.method === "DELETE"
      ? Response.json({ detail: "Accept it first." }, { status: 409 })
      : passOn(url, init),
  );
  await chooseOwnFromChat();
  await waitFor(() => expect(window.location.hash).toBe("#/setup"));
  expect(console.error).toHaveBeenCalledWith("Could not switch to your own photo and voice", expect.anything());
});

test("the chat links to a ready-made avatar or a new photo while the host's own is in use", async () => {
  avatarServer(false);
  const info = vi.spyOn(console, "info");
  await openAt("#/chat");
  const readyMade = await screen.findByRole("link", { name: "Use a ready-made avatar" });
  expect(readyMade.getAttribute("href")).toBe("#/start-now");
  const photo = screen.getByRole("link", { name: "Change your photo" });
  expect(photo.getAttribute("href")).toBe("#/setup/photos");
  fireEvent.click(readyMade);
  expect(info).toHaveBeenCalledWith("Choosing a ready-made avatar from the chat");
  // The click's navigation lands before the next test opens its page.
  await waitFor(() => expect(window.location.hash).toBe("#/start-now"));
});

test("the chat links to another avatar or the host's own while a ready-made one is in use", async () => {
  avatarServer(true);
  await openAt("#/chat");
  const another = await screen.findByRole("link", { name: "Choose another avatar" });
  expect(another.getAttribute("href")).toBe("#/start-now");
  const own = screen.getByRole("link", { name: "Use your own photo and voice" });
  expect(own.getAttribute("href")).toBe("#/consent/own");
});

test("the participant view's chat has no Avatar Choice links", async () => {
  avatarServer(true, "participant");
  await openAt("#/chat");
  expect(await screen.findByRole("textbox", { name: "Your message" })).toBeTruthy();
  expect(screen.queryByText("Avatar Choice:")).toBeNull();
  expect(screen.queryByRole("link", { name: "Choose another avatar" })).toBeNull();
});

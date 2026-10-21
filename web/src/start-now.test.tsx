import { cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { type Face, lineUrl, type PersonChoice, type StartNowStatus } from "./api";
import { facesOf, POLL_MS, progressText, StartNowPage } from "./start-now";

const IDLE: StartNowStatus = { state: "idle", person: null, percent: 0, error: null, chosen: null };

// A fake server: GET /api/start-now answers each of `reads` in turn, then the last again.
// In the server's order (by role, then face, then gender): Professor has two faces for a woman
// in a photo, one for a man (as R24b2 made them); Student and Boss have one each for a woman in a
// photo, and Boss one for an animated woman.
const FACES: Face[] = [
  { gender: "female", realism: "photoreal", role: "Professor", face: 1, name: "photoreal_female_professor" },
  { gender: "male", realism: "photoreal", role: "Professor", face: 1, name: "photoreal_male_professor" },
  { gender: "female", realism: "photoreal", role: "Professor", face: 2, name: "photoreal_female_professor_2" },
  { gender: "female", realism: "photoreal", role: "Student", face: 1, name: "photoreal_female_student" },
  { gender: "female", realism: "photoreal", role: "Boss", face: 1, name: "photoreal_female_boss" },
  { gender: "female", realism: "animated", role: "Boss", face: 1, name: "animated_female_boss" },
];

function server(
  reads: StartNowStatus[],
  post: Response | StartNowStatus = reads[0],
  faces: () => Promise<Response> = async () => Response.json(FACES),
) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/start-now/faces") return faces();
    if (url === "/api/start-now" && init?.method === "POST") {
      return post instanceof Response ? post : Response.json(post);
    }
    if (url === "/api/start-now") return Response.json(reads.length > 1 ? reads.shift() : reads[0]);
    if (url === "/api/prepare") return Response.json({ state: "idle", finished_at: null });
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// The choices wait for the faces, which the fake server answers at once.
async function facesShown(): Promise<void> {
  await screen.findByRole("radio", { name: /^Face 1 of/ });
}

function radio(name: string): HTMLInputElement {
  return screen.getByRole("radio", { name }) as HTMLInputElement;
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
  window.location.hash = "";
});

test("the choices start on the first of each, with no role or gender to pick", async () => {
  server([IDLE]);
  render(<StartNowPage />);
  expect(radio("American").checked).toBe(true);
  expect(radio("Photorealistic").checked).toBe(true);
  expect(await screen.findByRole("radio", { name: "Face 1 of 5" })).toBeTruthy();
  // A role would tie a role to a look (Larry's test of PR #124), and the face says enough
  // without a gender (Larry, 2026-10-21): only the faces are picked.
  expect(screen.queryByRole("combobox")).toBeNull();
  expect(screen.queryByText(/Role/)).toBeNull();
  expect(screen.queryByText("Gender")).toBeNull();
  expect(screen.queryByRole("radio", { name: "Female" })).toBeNull();
  expect(screen.queryByRole("radio", { name: "Male" })).toBeNull();
});

test("the person chosen before is where the choices start", async () => {
  const chosen = { gender: "female", accent: "British", realism: "photoreal", role: "Boss", face: 1 } as const;
  server([{ ...IDLE, chosen }]);
  render(<StartNowPage />);
  await vi.waitFor(() => expect(radio("British").checked).toBe(true));
  expect(radio("Photorealistic").checked).toBe(true);
  await vi.waitFor(() => expect(radio("Face 5 of 5").checked).toBe(true));
});

test("start downloads the person with progress, then opens the chat", async () => {
  const downloading = { ...IDLE, state: "downloading", person: "p", percent: 40 } as const;
  const ready = { ...IDLE, state: "ready", person: "p", percent: 100 } as const;
  const fetchMock = server([IDLE, downloading, ready], downloading);
  render(<StartNowPage />);
  await screen.findByRole("radio", { name: "Face 1 of 5" });
  fireEvent.click(radio("British"));
  fireEvent.click(radio("Animated"));
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  expect(await screen.findByText("Step 1 of 3: Downloading the avatar… 40%")).toBeTruthy();
  expect(screen.getByRole("progressbar")).toBeTruthy();
  expect(radio("British").closest("fieldset")!.disabled).toBe(true);
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(post[1]!.body as string)).toEqual({
    gender: "female",
    accent: "British",
    realism: "animated",
    role: "Boss", // the animated woman's only face here
    face: 1,
  });
  await vi.waitFor(() => expect(window.location.hash).toBe("#/chat"), { timeout: 4 * POLL_MS });
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Default person p ready in \d+ ms/));
});

test("a failed download says why, with Try again and the usual setup", async () => {
  const failed = { ...IDLE, state: "failed", person: "p", error: "Couldn't download." } as const;
  server([IDLE, failed], { ...IDLE, state: "downloading", person: "p" });
  render(<StartNowPage />);
  await facesShown();
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  expect((await screen.findByRole("alert")).textContent).toBe("Couldn't download.");
  expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "use your own photos and voice" }).getAttribute("href")).toBe(
    "#/consent",
  );
});

test("a refused start says why", async () => {
  server([IDLE], Response.json({ detail: "'Duke' is not one of …" }, { status: 400 }));
  render(<StartNowPage />);
  await facesShown();
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Duke");
});

test("losing the app while downloading says so", async () => {
  const downloading = { ...IDLE, state: "downloading", person: "p", percent: 5 } as const;
  const fetchMock = server([IDLE], downloading);
  render(<StartNowPage />);
  await facesShown();
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  await screen.findByText("Step 1 of 3: Downloading the avatar… 5%");
  fetchMock.mockImplementation(async () => new Response("", { status: 503 }));
  expect((await screen.findByRole("alert", {}, { timeout: 4 * POLL_MS })).textContent).toBe(
    "Could not reach the app. Try again.",
  );
});

test("a download already under way is shown on opening the page", async () => {
  server([{ ...IDLE, state: "getting-ready", person: "p", percent: 100 }]);
  render(<StartNowPage />);
  expect(await screen.findByText("Step 2 of 3: Getting the avatar's voice ready…")).toBeTruthy();
});

test("progress text", () => {
  expect(progressText({ ...IDLE, state: "downloading", percent: 12 })).toBe(
    "Step 1 of 3: Downloading the avatar… 12%",
  );
  expect(progressText({ ...IDLE, state: "unpacking", percent: 100 })).toBe(
    "Step 2 of 3: Unpacking the avatar…",
  );
  expect(progressText({ ...IDLE, state: "ready", percent: 100, chat_ready: false })).toBe(
    "Step 3 of 3: Making the avatar's video for the chat…",
  );
});

test("the chat opens only once the new avatar's video for it is made", async () => {
  const making = { ...IDLE, state: "ready", person: "boss", percent: 100, chat_ready: false } as const;
  const made = { ...making, chat_ready: true };
  server([IDLE, making, making, made], making);
  render(<StartNowPage />);
  await facesShown();
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  expect(
    await screen.findByText(/^Step 3 of 3: Making the avatar's video for the chat…/),
  ).toBeTruthy();
  expect(screen.getByRole("progressbar", { name: "Getting the avatar ready" })).toBeTruthy();
  expect(window.location.hash).toBe(""); // not yet: the chat would show the person before
  await vi.waitFor(() =>
    expect(console.info).toHaveBeenCalledWith("Avatar ready; waiting for its idle video for the chat"),
  );
  await vi.waitFor(() => expect(window.location.hash).toBe("#/chat"), { timeout: 6 * POLL_MS });
});

test("a default person says Goodbye and Welcome back in their own voice", async () => {
  const chosen = { gender: "male", accent: "British", realism: "animated", role: "Boss" } as const;
  server([{ ...IDLE, chosen }]);
  expect(await lineUrl("goodbye")).toBe(
    "/api/start-now/lines/goodbye?v=male-British-animated-Boss",
  );
  server([IDLE]);
  expect(await lineUrl("welcome-back")).toBeNull(); // the user's own, not prepared
});

test("a choice's faces are shown as pictures, and the one picked is the one started", async () => {
  const fetchMock = server([IDLE], { ...IDLE, state: "downloading", person: "p" });
  render(<StartNowPage />);
  const first = (await screen.findByRole("radio", { name: "Face 1 of 5" })) as HTMLInputElement;
  expect(first.checked).toBe(true); // the first face unless another is picked
  const img = screen.getByAltText("Face 3 of 5") as HTMLImageElement;
  expect(img.getAttribute("src")).toBe("/faces/photoreal_female_professor_2.jpg");
  fireEvent.click(screen.getByRole("radio", { name: "Face 3 of 5" }));
  expect(console.info).toHaveBeenCalledWith("Face 3 of 5 picked: photoreal_female_professor_2");
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  await vi.waitFor(() =>
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
  );
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(post[1]!.body as string).face).toBe(2);
});

test("changing the look shows its own faces, from the first; the accent keeps the face", async () => {
  server([IDLE]);
  render(<StartNowPage />);
  fireEvent.click(await screen.findByRole("radio", { name: "Face 3 of 5" }));
  fireEvent.click(radio("British"));
  expect(radio("Face 3 of 5").checked).toBe(true);
  fireEvent.click(radio("Animated"));
  expect(radio("Face 1 of 1").checked).toBe(true);
  expect(screen.queryByRole("radio", { name: "Face 3 of 5" })).toBeNull();
  fireEvent.click(radio("Photorealistic"));
  expect(radio("Face 1 of 5").checked).toBe(true);
});

test("a man's face is picked like any other, and his gender goes with it", async () => {
  const fetchMock = server([IDLE], { ...IDLE, state: "downloading", person: "p" });
  render(<StartNowPage />);
  fireEvent.click(await screen.findByRole("radio", { name: "Face 2 of 5" }));
  expect(console.info).toHaveBeenCalledWith("Face 2 of 5 picked: photoreal_male_professor");
  // Same role and face number as Face 1, so only the gender tells them apart.
  expect(radio("Face 1 of 5").checked).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  await vi.waitFor(() =>
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
  );
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(post[1]!.body as string)).toMatchObject({ gender: "male", role: "Professor", face: 1 });
});

test("the face picked before is picked again on opening the page", async () => {
  const chosen = { gender: "female", accent: "American", realism: "photoreal", role: "Professor", face: 2 } as const;
  server([{ ...IDLE, chosen }]);
  render(<StartNowPage />);
  const second = (await screen.findByRole("radio", { name: "Face 3 of 5" })) as HTMLInputElement;
  await vi.waitFor(() => expect(second.checked).toBe(true));
});

test("the faces are all the people of the look, of every gender, always in the same order", () => {
  const choice = { gender: "female", accent: "British", realism: "photoreal", role: "Professor" } as const;
  const names = (c: PersonChoice) => facesOf(FACES, c).map((f) => f.name);
  expect(names(choice)).toEqual([
    "photoreal_female_professor",
    "photoreal_male_professor",
    "photoreal_female_professor_2",
    "photoreal_female_student",
    "photoreal_female_boss",
  ]);
  expect(names({ ...choice, role: "Boss" })).toEqual(names(choice));
  expect(names({ ...choice, gender: "male" })).toEqual(names(choice));
  expect(names({ ...choice, realism: "animated" })).toEqual(["animated_female_boss"]);
});

test("any face can be picked, and that person is started", async () => {
  const fetchMock = server([IDLE], { ...IDLE, state: "downloading", person: "p" });
  render(<StartNowPage />);
  fireEvent.click(await screen.findByRole("radio", { name: "Face 5 of 5" }));
  expect(console.info).toHaveBeenCalledWith("Face 5 of 5 picked: photoreal_female_boss");
  expect(radio("Face 5 of 5").checked).toBe(true);
  expect(radio("Face 1 of 5").checked).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  await vi.waitFor(() =>
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
  );
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(post[1]!.body as string)).toMatchObject({ role: "Boss", face: 1 });
});

test("the choices wait for the faces, then a change of look picks its first face", async () => {
  // Codex's review of PR #124: changed before the faces came, the look kept the old face.
  let answer = (_: Response) => {};
  const chosen = { gender: "female", accent: "American", realism: "photoreal", role: "Professor", face: 2 } as const;
  const later = () => new Promise<Response>((r) => (answer = r));
  const fetchMock = server([{ ...IDLE, chosen }], { ...IDLE, state: "downloading", person: "p" }, later);
  render(<StartNowPage />);
  expect(await screen.findByText("Loading the faces…")).toBeTruthy();
  expect(radio("Animated").closest("fieldset")!.disabled).toBe(true);
  expect((screen.getByRole("button", { name: "Start now" }) as HTMLButtonElement).disabled).toBe(true);
  answer(Response.json(FACES));
  await facesShown();
  expect(radio("Animated").closest("fieldset")!.disabled).toBe(false);
  fireEvent.click(radio("Animated"));
  expect(radio("Face 1 of 1").checked).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  await vi.waitFor(() =>
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true),
  );
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(post[1]!.body as string)).toMatchObject({ realism: "animated", role: "Boss", face: 1 });
});

test("faces that can't be read are said, and Start stays off", async () => {
  server([IDLE], IDLE, async () => new Response("", { status: 500 }));
  render(<StartNowPage />);
  expect((await screen.findByRole("alert")).textContent).toBe(
    "Couldn't load the faces to pick from. Reload the page to try again.",
  );
  expect((screen.getByRole("button", { name: "Start now" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.queryByText("Loading the faces…")).toBeNull();
  expect(console.error).toHaveBeenCalledWith("Could not read the faces", expect.anything());
});

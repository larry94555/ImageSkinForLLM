import { cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { type Face, lineUrl, type StartNowStatus } from "./api";
import { facesOf, POLL_MS, progressText, roleLabel, StartNowPage } from "./start-now";

const IDLE: StartNowStatus = { state: "idle", person: null, percent: 0, error: null, chosen: null };

// The female photoreal Professor has two faces, listed out of order; the Boss has one.
const FACES: Face[] = [
  { gender: "female", realism: "photoreal", role: "Professor", face: 2, name: "photoreal_female_professor_2" },
  { gender: "female", realism: "photoreal", role: "Professor", face: 1, name: "photoreal_female_professor" },
  { gender: "female", realism: "photoreal", role: "Boss", face: 1, name: "photoreal_female_boss" },
  { gender: "male", realism: "photoreal", role: "Professor", face: 1, name: "photoreal_male_professor" },
];

// A fake server: GET /api/start-now answers each of `reads` in turn, then the last again.
function server(reads: StartNowStatus[], post: Response | StartNowStatus = reads[0]) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/start-now" && init?.method === "POST") {
      return post instanceof Response ? post : Response.json(post);
    }
    if (url === "/api/start-now") return Response.json(reads.length > 1 ? reads.shift() : reads[0]);
    if (url === "/api/start-now/faces") return Response.json(FACES);
    if (url === "/api/prepare") return Response.json({ state: "idle", finished_at: null });
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function radio(name: string): HTMLInputElement {
  return screen.getByRole("radio", { name }) as HTMLInputElement;
}

function roles(): string[] {
  return screen.getAllByRole("option").map((o) => o.textContent ?? "");
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

test("a role with a word for each gender shows that word", () => {
  expect(roleLabel("Parent", "female")).toBe("Mother");
  expect(roleLabel("Parent", "male")).toBe("Father");
  expect(roleLabel("Teenager", "male")).toBe("Son");
  expect(roleLabel("Teenager", "female")).toBe("Daughter");
  expect(roleLabel("Boss", "female")).toBe("Boss");
});

test("the four choices start on the first of each, and the roles follow the gender", async () => {
  server([IDLE]);
  render(<StartNowPage />);
  expect(radio("Female").checked).toBe(true);
  expect(radio("American").checked).toBe(true);
  expect(radio("Photorealistic").checked).toBe(true);
  expect(roles()).toHaveLength(9);
  expect(roles()).toContain("Mother");
  const role = screen.getByRole("combobox") as HTMLSelectElement;
  fireEvent.change(role, { target: { value: "Parent" } });
  fireEvent.click(radio("Male"));
  // Changing the gender keeps the role, so Mother becomes Father.
  expect(roles()).toContain("Father");
  expect(roles()).not.toContain("Mother");
  expect(role.value).toBe("Parent");
});

test("the person chosen before is where the choices start", async () => {
  const chosen = { gender: "male", accent: "British", realism: "animated", role: "Teenager" } as const;
  server([{ ...IDLE, chosen }]);
  render(<StartNowPage />);
  await vi.waitFor(() => expect(radio("Male").checked).toBe(true));
  expect(radio("British").checked).toBe(true);
  expect(radio("Animated").checked).toBe(true);
  expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("Teenager");
});

test("start downloads the person with progress, then opens the chat", async () => {
  const downloading = { ...IDLE, state: "downloading", person: "p", percent: 40 } as const;
  const ready = { ...IDLE, state: "ready", person: "p", percent: 100 } as const;
  const fetchMock = server([IDLE, downloading, ready], downloading);
  render(<StartNowPage />);
  fireEvent.click(radio("British"));
  fireEvent.click(radio("Animated"));
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  expect(await screen.findByText("Downloading the person… 40%")).toBeTruthy();
  expect(screen.getByRole("progressbar")).toBeTruthy();
  expect(radio("Female").closest("fieldset")!.disabled).toBe(true);
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(post[1]!.body as string)).toEqual({
    gender: "female",
    accent: "British",
    realism: "animated",
    role: "Professor",
    face: 1,
  });
  await vi.waitFor(() => expect(window.location.hash).toBe("#/chat"), { timeout: 4 * POLL_MS });
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Default person p ready in \d+ ms/));
});

test("a failed download says why, with Try again and the usual setup", async () => {
  const failed = { ...IDLE, state: "failed", person: "p", error: "Couldn't download." } as const;
  server([IDLE, failed], { ...IDLE, state: "downloading", person: "p" });
  render(<StartNowPage />);
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
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Duke");
});

test("losing the app while downloading says so", async () => {
  const downloading = { ...IDLE, state: "downloading", person: "p", percent: 5 } as const;
  const fetchMock = server([IDLE], downloading);
  render(<StartNowPage />);
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  await screen.findByText("Downloading the person… 5%");
  fetchMock.mockImplementation(async () => new Response("", { status: 503 }));
  expect((await screen.findByRole("alert", {}, { timeout: 4 * POLL_MS })).textContent).toBe(
    "Could not reach the app. Try again.",
  );
});

test("a download already under way is shown on opening the page", async () => {
  server([{ ...IDLE, state: "getting-ready", person: "p", percent: 100 }]);
  render(<StartNowPage />);
  expect(await screen.findByText("Getting the person ready…")).toBeTruthy();
});

test("progress text", () => {
  expect(progressText({ ...IDLE, state: "downloading", percent: 12 })).toBe(
    "Downloading the person… 12%",
  );
  expect(progressText({ ...IDLE, state: "unpacking", percent: 100 })).toBe(
    "Getting the person ready…",
  );
});

test("a default person says Goodbye and Welcome back in their own voice", async () => {
  const chosen = { gender: "male", accent: "British", realism: "animated", role: "Boss" } as const;
  server([{ ...IDLE, chosen }]);
  expect(await lineUrl("goodbye")).toBe(
    "/api/start-now/lines/goodbye?v=male-British-animated-Boss-1",
  );
  server([{ ...IDLE, chosen: { ...chosen, face: 2 } }]);
  expect(await lineUrl("goodbye")).toBe(
    "/api/start-now/lines/goodbye?v=male-British-animated-Boss-2",
  );
  server([IDLE]);
  expect(await lineUrl("welcome-back")).toBeNull(); // the user's own, not prepared
});

test("a choice's faces are its own, first face first", () => {
  const choice = { gender: "female", accent: "American", realism: "photoreal", role: "Professor" } as const;
  expect(facesOf(FACES, choice).map((f) => f.face)).toEqual([1, 2]);
  expect(facesOf(FACES, { ...choice, role: "Boss" }).map((f) => f.name)).toEqual(["photoreal_female_boss"]);
  expect(facesOf(FACES, { ...choice, realism: "animated" })).toEqual([]);
});

test("a choice with two faces shows both, unlabelled, and the second can be picked", async () => {
  const fetchMock = server([IDLE], { ...IDLE, state: "downloading", person: "p" });
  render(<StartNowPage />);
  expect(await screen.findByText("Pick a face")).toBeTruthy();
  const pictures = screen.getAllByRole("img", { hidden: true }) as HTMLImageElement[];
  expect(pictures.map((i) => i.getAttribute("src"))).toEqual([
    "/default-people/photoreal_female_professor.jpg",
    "/default-people/photoreal_female_professor_2.jpg",
  ]);
  expect(pictures.every((i) => i.alt === "")).toBe(true);
  expect(radio("Face 1").checked).toBe(true); // the first, if none is picked
  fireEvent.click(radio("Face 2"));
  expect(radio("Face 2").checked).toBe(true);
  expect(radio("Face 2").closest("label")!.className).toBe("picked");
  fireEvent.click(screen.getByRole("button", { name: "Start now" }));
  await vi.waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(JSON.parse(post[1]!.body as string).face).toBe(2);
});

test("changing a choice shows the new choice's faces, with the first picked", async () => {
  server([IDLE]);
  render(<StartNowPage />);
  await screen.findByText("Pick a face");
  fireEvent.click(radio("Face 2"));
  fireEvent.click(radio("British")); // only the voice changes: the face stays
  expect(radio("Face 2").checked).toBe(true);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "Boss" } });
  expect(screen.getByText("Face")).toBeTruthy();
  expect(screen.getAllByRole("radio", { name: /^Face/ })).toHaveLength(1);
  expect(radio("Face 1").checked).toBe(true);
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "Professor" } });
  expect(radio("Face 1").checked).toBe(true); // back to the first, not the one picked before
});

test("the face chosen before is picked again", async () => {
  const chosen = { gender: "female", accent: "American", realism: "photoreal", role: "Professor", face: 2 } as const;
  server([{ ...IDLE, chosen }]);
  render(<StartNowPage />);
  await screen.findByText("Pick a face");
  await vi.waitFor(() => expect(radio("Face 2").checked).toBe(true));
});

test("without the faces the choices still work", async () => {
  server([IDLE]);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      url === "/api/start-now" ? Response.json(IDLE) : new Response("", { status: 500 }),
    ),
  );
  render(<StartNowPage />);
  await vi.waitFor(() =>
    expect(console.error).toHaveBeenCalledWith("Could not read the default people's faces", expect.anything()),
  );
  expect(screen.queryByText("Pick a face")).toBeNull();
  expect(screen.getByRole("button", { name: "Start now" })).toBeTruthy();
});

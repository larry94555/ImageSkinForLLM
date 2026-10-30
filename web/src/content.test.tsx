import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { Pdf, Reading, WikiBuild } from "./api";
import { App } from "./App";
import { ContentPage, READING_POLL_MS, readingText, size, wikiText } from "./content";

const GUIDE: Pdf = {
  id: "a1",
  name: "guide.pdf",
  size: 2_500_000,
  added_at: "2026-10-12T06:00:00+00:00",
  replaced_at: null,
};

const READ: Reading = {
  state: "done",
  page: 3,
  pages: 3,
  kind: "text",
  counts: { paragraph: 12, slide: 0, table: 1 },
  pages_without_text: [],
  error: null,
};

const BUILT: WikiBuild = {
  state: "done",
  part: 2,
  parts: 2,
  pages: 7,
  skipped_parts: [],
  error: null,
  stage: "topics",
  steps: 0,
  detail_pages: 0,
  elapsed_s: null,
  steps_planned: 0,
  remaining_s: null,
};

// A fake content API holding `pdfs`. `refuse` makes adding or replacing fail with that reason.
// `readings` are the reading progress answers, in turn; the last one repeats.
function server(
  pdfs: Pdf[],
  opts: {
    refuse?: string;
    listFails?: boolean;
    readings?: Record<string, Reading>[];
    wiki?: Record<string, WikiBuild>[];
  } = {},
) {
  let next = 0;
  const readings = [...(opts.readings ?? [{}])];
  const wiki = [...(opts.wiki ?? [{}])];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/content/readings") {
      return Response.json(readings.length > 1 ? readings.shift() : readings[0]);
    }
    if (url === "/api/wiki/builds") {
      return Response.json(wiki.length > 1 ? wiki.shift() : wiki[0]);
    }
    if (url === "/api/content" && method === "GET") {
      return opts.listFails ? new Response("", { status: 500 }) : Response.json(pdfs);
    }
    if (method === "DELETE") return Response.json({ removed: true });
    if (opts.refuse) return Response.json({ detail: opts.refuse }, { status: 415 });
    const file = (init?.body as FormData).get("file") as File;
    const id = method === "PUT" ? url.split("/").pop()! : `new${++next}`;
    return Response.json({
      id,
      name: file.name,
      size: file.size,
      added_at: "2026-10-12T07:00:00+00:00",
      replaced_at: method === "PUT" ? "2026-10-12T08:00:00+00:00" : null,
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// The calls that change something.
function changes(fetchMock: ReturnType<typeof server>) {
  return fetchMock.mock.calls.filter(([, init]) => init?.method);
}

function pdfFile(name: string) {
  return new File(["%PDF-1.7 test"], name, { type: "application/pdf" });
}

async function choose(input: HTMLElement, ...files: File[]) {
  await act(async () => {
    fireEvent.change(input, { target: { files } });
  });
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
});

// Clicks a Remove button, then Yes in the box that asks first.
async function removeConfirmed(button: HTMLElement) {
  await act(async () => {
    fireEvent.click(button);
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Yes, remove it" }));
  });
}

test("the nav's Manage Content link opens the page", async () => {
  server([GUIDE]);
  window.location.hash = "#/content";
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Manage Content" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Manage Content" }).className).toBe("current");
  expect(await screen.findByRole("link", { name: "guide.pdf" })).toBeTruthy();
});

test("lists the PDFs with their size, linking to each", async () => {
  server([GUIDE]);
  render(<ContentPage />);
  const link = await screen.findByRole("link", { name: "guide.pdf" });
  expect(link.getAttribute("href")).toBe("/api/content/a1");
  expect(screen.getByText(/2\.4 MB · added/)).toBeTruthy();
});

test("says when there are no PDFs", async () => {
  server([]);
  render(<ContentPage />);
  expect(await screen.findByText("No PDFs yet.")).toBeTruthy();
});

test("says when the list can't be loaded", async () => {
  server([], { listFails: true });
  render(<ContentPage />);
  expect(await screen.findByText(/Could not load the list/)).toBeTruthy();
});

test("adds several PDFs, one at a time", async () => {
  const fetchMock = server([]);
  render(<ContentPage />);
  await screen.findByText("No PDFs yet.");
  await choose(screen.getByLabelText("Add PDFs"), pdfFile("one.pdf"), pdfFile("two.pdf"));
  expect(await screen.findByRole("link", { name: "one.pdf" })).toBeTruthy();
  expect(await screen.findByRole("link", { name: "two.pdf" })).toBeTruthy();
  const posts = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(2);
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Added one\.pdf in \d/));
  // A done message says what happens next (R41e).
  expect(screen.getByRole("status").textContent).toBe(
    "Added one.pdf, two.pdf. It is read first, then its wiki is built. Each PDF below shows how far it has got.",
  );
});

test("a refused PDF shows why next to its name", async () => {
  server([], { refuse: "That file is not a PDF." });
  render(<ContentPage />);
  await screen.findByText("No PDFs yet.");
  await choose(screen.getByLabelText("Add PDFs"), pdfFile("notes.txt"));
  expect(await screen.findByText("notes.txt: That file is not a PDF.")).toBeTruthy();
  expect(screen.getByText("No PDFs yet.")).toBeTruthy();
  expect(screen.queryByRole("status")).toBeNull(); // nothing was added
});

test("replacing a PDF keeps its place and shows it was replaced", async () => {
  const fetchMock = server([GUIDE]);
  render(<ContentPage />);
  await screen.findByRole("link", { name: "guide.pdf" });
  await choose(screen.getByLabelText("Replace guide.pdf"), pdfFile("guide-v2.pdf"));
  const link = await screen.findByRole("link", { name: "guide-v2.pdf" });
  expect(screen.queryByRole("link", { name: "guide.pdf" })).toBeNull();
  expect(link.getAttribute("href")).toBe("/api/content/a1");
  expect(screen.getByText(/· replaced/)).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledWith("/api/content/a1", expect.objectContaining({ method: "PUT" }));
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/^Replaced guide\.pdf with guide-v2\.pdf in \d/),
  );
  expect(screen.getByRole("status").textContent).toMatch(/^Replaced guide\.pdf with guide-v2\.pdf\. It is read first/);
});

test("a refused replacement keeps the old PDF", async () => {
  server([GUIDE], { refuse: "That file is not a PDF." });
  render(<ContentPage />);
  await screen.findByRole("link", { name: "guide.pdf" });
  await choose(screen.getByLabelText("Replace guide.pdf"), pdfFile("bad.pdf"));
  expect(screen.getByRole("link", { name: "guide.pdf" })).toBeTruthy();
  expect(await screen.findByText("bad.pdf: That file is not a PDF.")).toBeTruthy();
  expect(screen.queryByRole("status")).toBeNull();
});

test("choosing no file to replace with changes nothing", async () => {
  const fetchMock = server([GUIDE]);
  render(<ContentPage />);
  await screen.findByRole("link", { name: "guide.pdf" });
  await choose(screen.getByLabelText("Replace guide.pdf"));
  expect(changes(fetchMock)).toHaveLength(0);
});

test("removes a PDF after asking in the app's own box", async () => {
  const fetchMock = server([GUIDE, { ...GUIDE, id: "b2", name: "other.pdf" }]);
  const confirm = vi.spyOn(window, "confirm");
  render(<ContentPage />);
  const item = (await screen.findByRole("link", { name: "guide.pdf" })).closest("li")!;
  await act(async () => {
    fireEvent.click(within(item).getByRole("button", { name: "Remove" }));
  });
  const dialog = screen.getByRole("alertdialog", { name: "Remove guide.pdf?" });
  expect(dialog.textContent).toContain("Its wiki pages are removed too.");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "No, keep it" }));
  });
  expect(screen.queryByRole("alertdialog")).toBeNull();
  expect(changes(fetchMock)).toHaveLength(0);
  await removeConfirmed(within(item).getByRole("button", { name: "Remove" }));
  expect(confirm).not.toHaveBeenCalled(); // not the browser's box
  expect(fetchMock).toHaveBeenCalledWith("/api/content/a1", { method: "DELETE" });
  await waitFor(() => expect(screen.queryByRole("link", { name: "guide.pdf" })).toBeNull());
  expect(screen.getByRole("link", { name: "other.pdf" })).toBeTruthy();
});

test("a failed removal says so and keeps the PDF", async () => {
  server([GUIDE]);
  vi.mocked(fetch).mockImplementation(async (_url, init) =>
    init?.method === "DELETE" ? new Response("", { status: 500 }) : Response.json([GUIDE]),
  );
  render(<ContentPage />);
  await screen.findByRole("link", { name: "guide.pdf" });
  await removeConfirmed(screen.getByRole("button", { name: "Remove" }));
  expect(await screen.findByText("guide.pdf: Could not remove it. Please try again.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "guide.pdf" })).toBeTruthy();
});

test("sizes read as KB or MB", () => {
  expect(size(10)).toBe("1 KB");
  expect(size(1536)).toBe("2 KB");
  expect(size(2_500_000)).toBe("2.4 MB");
});

// Waits for `text` under fake timers that move only when the test moves them: each check moves
// the clock 50 ms, so no extra progress check fires while waiting (the real clock moving the fake
// one on a slow runner skipped a step of the wiki's progress).
async function seen(text: string | RegExp) {
  await vi.waitFor(() => screen.getByText(text));
}

test("shows how far each PDF has got being read, checking again until it is done", async () => {
  vi.useFakeTimers();
  const reading: Reading = { ...READ, state: "reading", page: 1, kind: null, counts: null };
  const fetchMock = server([GUIDE], {
    readings: [{ a1: { ...reading, state: "waiting", pages: 0 } }, { a1: reading }, { a1: READ }],
    wiki: [{ a1: BUILT }],
  });
  render(<ContentPage />);
  await seen("Waiting to be read…");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(READING_POLL_MS);
  });
  await seen("Reading page 1 of 3…");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(READING_POLL_MS);
  });
  await seen(/Read 3 pages: 12 paragraphs, 1 table/);
  // What was read is raw data, so the page doesn't link to it (R41e).
  expect(screen.queryByRole("link", { name: "What was read" })).toBeNull();

  // Done: no more checks.
  const checks = fetchMock.mock.calls.length;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(READING_POLL_MS * 3);
  });
  expect(fetchMock.mock.calls.length).toBe(checks);
  vi.useRealTimers();
});

test("a PDF that could not be read shows why", async () => {
  server([GUIDE], {
    readings: [{ a1: { ...READ, state: "failed", error: "This PDF could not be read." } }],
  });
  render(<ContentPage />);
  const error = await screen.findByText("This PDF could not be read.");
  expect(error.className).toBe("error");
});

test("a failed progress check is tried again", async () => {
  vi.useFakeTimers();
  server([GUIDE]);
  let checks = 0;
  vi.mocked(fetch).mockImplementation(async (url) => {
    if (url !== "/api/content/readings") return Response.json([GUIDE]);
    return ++checks === 1 ? new Response("", { status: 500 }) : Response.json({ a1: READ });
  });
  render(<ContentPage />);
  await vi.waitFor(() => screen.getByRole("link", { name: "guide.pdf" }));
  await vi.waitFor(() => expect(checks).toBe(1));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(READING_POLL_MS);
  });
  await seen(/Read 3 pages/);
  vi.useRealTimers();
});

test("a failed progress check is logged", async () => {
  server([GUIDE]);
  vi.mocked(fetch).mockImplementation(async (url) =>
    url === "/api/content/readings" ? new Response("", { status: 500 }) : Response.json([GUIDE]),
  );
  render(<ContentPage />);
  await screen.findByRole("link", { name: "guide.pdf" });
  await waitFor(() =>
    expect(console.error).toHaveBeenCalledWith(
      "Could not check the reading progress",
      expect.any(Error),
    ),
  );
});

test("reading progress reads as a sentence", () => {
  expect(readingText({ ...READ, state: "reading", pages: 0 })).toBe("Reading…");
  expect(readingText({ ...READ, state: "failed" })).toBe("Could not be read.");
  expect(
    readingText({
      ...READ,
      pages: 1,
      counts: { paragraph: 0, slide: 1, table: 0 },
      pages_without_text: [2, 3],
    }),
  ).toBe("Read 1 page: 1 slide (no text on page 2, 3, maybe scanned)");
  expect(readingText({ ...READ, counts: { paragraph: 0, slide: 0, table: 0 } })).toBe(
    "Read 3 pages: no text found",
  );
  expect(
    readingText({ ...READ, counts: { paragraph: 0, slide: 0, table: 0 }, pages_without_text: [1] }),
  ).toBe("Read 3 pages: no text found, maybe scanned");
});

test("shows the wiki pages being built once a PDF is read, checking until they are", async () => {
  vi.useFakeTimers();
  const building: WikiBuild = { ...BUILT, state: "building", part: 0, pages: null };
  const fetchMock = server([GUIDE], {
    readings: [{ a1: READ }],
    // Building is answered twice: once when the PDF is read, and again by the check made at once
    // when the page sees the wiki being built. Then one answer per check.
    wiki: [{}, { a1: building }, { a1: building }, { a1: { ...building, part: 1 } }, { a1: BUILT }],
  });
  render(<ContentPage />);
  await seen(/Read 3 pages/);
  await seen(/Building the wiki: part 1 of 2, 0% done…/);
  for (const text of ["part 2 of 2, 50% done", "Wiki ready: 7 topics"]) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(READING_POLL_MS);
    });
    await seen(new RegExp(text));
  }
  const link = screen.getByRole("link", { name: "Read the wiki" });
  expect(link.getAttribute("href")).toBe("#/wiki/a1"); // the readable wiki, not its JSON

  // Done: no more checks.
  const checks = fetchMock.mock.calls.length;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(READING_POLL_MS * 3);
  });
  expect(fetchMock.mock.calls.length).toBe(checks);
  vi.useRealTimers();
});

test("wiki pages that could not be built show why", async () => {
  server([GUIDE], {
    readings: [{ a1: READ }],
    wiki: [{ a1: { ...BUILT, state: "failed", error: "The LLM gave no usable answer." } }],
  });
  render(<ContentPage />);
  const error = await screen.findByText("The LLM gave no usable answer.");
  expect(error.className).toBe("error");
});

test("a failed wiki progress check is logged", async () => {
  server([GUIDE]);
  vi.mocked(fetch).mockImplementation(async (url) =>
    url === "/api/wiki/builds" ? new Response("", { status: 500 }) : Response.json([GUIDE]),
  );
  render(<ContentPage />);
  await screen.findByRole("link", { name: "guide.pdf" });
  await waitFor(() =>
    expect(console.error).toHaveBeenCalledWith(
      "Could not check the wiki progress",
      expect.any(Error),
    ),
  );
});

test("wiki progress reads as a sentence", () => {
  const waiting: WikiBuild = { ...BUILT, state: "waiting", parts: 0, pages: null };
  expect(wikiText(waiting)).toBe("Waiting to build the wiki…");
  expect(wikiText({ ...waiting, ahead: 1, building_name: "notes.pdf" })).toBe(
    "Waiting to build the wiki: 1 PDF ahead, building “notes.pdf” now…",
  );
  expect(wikiText({ ...waiting, ahead: 2, building_name: null })).toBe(
    "Waiting to build the wiki: 2 PDFs ahead…",
  );
  expect(wikiText({ ...waiting, ahead: 1, stopping: true })).toBe(
    "Waiting to build the wiki: stopping the removed PDF's build…",
  );
  expect(wikiText({ ...waiting, ahead: 3, stopping: true })).toBe(
    "Waiting to build the wiki: stopping the removed PDF's build, then 2 PDFs ahead…",
  );
  expect(wikiText({ ...waiting, error: "Could not reach the LLM" })).toBe(
    "Waiting for the AI to be ready to build the wiki…",
  );
  expect(wikiText({ ...waiting, state: "building" })).toBe("Building the wiki…");
  expect(wikiText({ ...BUILT, state: "failed" })).toBe("The wiki could not be built.");
  expect(wikiText({ ...BUILT, pages: 1, parts: 5, skipped_parts: [2, 4] })).toBe(
    "Wiki ready: 1 topic (2 parts of 5 skipped: the AI's answer couldn't be used)",
  );
  const outline: WikiBuild = { ...BUILT, state: "building", stage: "outline", pages: null };
  expect(wikiText(outline)).toBe("Arranging the wiki's topics…");
  expect(wikiText({ ...outline, steps: 3, steps_planned: 9 })).toBe(
    "Arranging the wiki's topics: step 4 of about 9…",
  );
  expect(wikiText({ ...BUILT, detail_pages: 1 })).toBe("Wiki ready: 7 topics, 1 detail page");
  expect(wikiText({ ...outline, steps: 2, steps_planned: 2, elapsed_s: 252.4 }, true)).toBe(
    "Arranging the wiki's topics: step 2 of about 2… (4 min 12 s so far)",
  );
  expect(
    wikiText({ ...outline, steps: 2, steps_planned: 5, elapsed_s: 252.4, remaining_s: 90 }, true),
  ).toBe("Arranging the wiki's topics: step 3 of about 5… (4 min 12 s so far, about 1 min 30 s left)");
  expect(wikiText({ ...BUILT, state: "building", part: 1, elapsed_s: 40, remaining_s: 40 }, true)).toBe(
    "Building the wiki: part 2 of 2, 50% done… (40 s so far, about 40 s left before arranging its topics)",
  );
  expect(wikiText({ ...BUILT, state: "building", part: 0, elapsed_s: 5 }, true)).toBe(
    "Building the wiki: part 1 of 2, 0% done… (5 s so far, the time left shows once part 1 is done)",
  );
  expect(wikiText({ ...waiting, error: "down", elapsed_s: 61 }, true)).toBe(
    "Waiting for the AI to be ready to build the wiki… (1 min 1 s so far)",
  );
  expect(wikiText({ ...BUILT, elapsed_s: 3780 }, true)).toBe("Wiki ready: 7 topics, built in 1 h 3 min");
});

test("without the timing metrics, wiki progress still says how long so far and how long is left", () => {
  // Larry's test of PR #123: "Building the wiki…" alone showed nothing moving.
  const building: WikiBuild = { ...BUILT, state: "building", part: 1, elapsed_s: 40 };
  expect(wikiText({ ...building, remaining_s: 40 })).toBe(
    "Building the wiki: part 2 of 2, 50% done… (40 s so far, about 40 s left before arranging its topics)",
  );
  expect(wikiText({ ...building, remaining_s: 39 })).toContain("about 39 s left"); // counting down
  expect(wikiText({ ...BUILT, elapsed_s: 3780 })).toBe("Wiki ready: 7 topics"); // done: metrics only
});

test("a wiki being built shows a bar of the parts built", async () => {
  const building: WikiBuild = { ...BUILT, state: "building", part: 1, pages: null };
  server([GUIDE], { readings: [{ a1: READ }], wiki: [{ a1: building }] });
  render(<ContentPage />);
  const bar = (await screen.findByRole("progressbar", { name: "Wiki parts built" })) as HTMLProgressElement;
  expect(bar.value).toBe(1);
  expect(bar.max).toBe(2);
});

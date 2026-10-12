import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { Pdf, Reading } from "./api";
import { App } from "./App";
import { ContentPage, READING_POLL_MS, readingText, size } from "./content";

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

// A fake content API holding `pdfs`. `refuse` makes adding or replacing fail with that reason.
// `readings` are the reading progress answers, in turn; the last one repeats.
function server(
  pdfs: Pdf[],
  opts: { refuse?: string; listFails?: boolean; readings?: Record<string, Reading>[] } = {},
) {
  let next = 0;
  const readings = [...(opts.readings ?? [{}])];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/content/readings") {
      return Response.json(readings.length > 1 ? readings.shift() : readings[0]);
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
});

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
});

test("a refused PDF shows why next to its name", async () => {
  server([], { refuse: "That file is not a PDF." });
  render(<ContentPage />);
  await screen.findByText("No PDFs yet.");
  await choose(screen.getByLabelText("Add PDFs"), pdfFile("notes.txt"));
  expect(await screen.findByText("notes.txt: That file is not a PDF.")).toBeTruthy();
  expect(screen.getByText("No PDFs yet.")).toBeTruthy();
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
});

test("a refused replacement keeps the old PDF", async () => {
  server([GUIDE], { refuse: "That file is not a PDF." });
  render(<ContentPage />);
  await screen.findByRole("link", { name: "guide.pdf" });
  await choose(screen.getByLabelText("Replace guide.pdf"), pdfFile("bad.pdf"));
  expect(screen.getByRole("link", { name: "guide.pdf" })).toBeTruthy();
  expect(await screen.findByText("bad.pdf: That file is not a PDF.")).toBeTruthy();
});

test("choosing no file to replace with changes nothing", async () => {
  const fetchMock = server([GUIDE]);
  render(<ContentPage />);
  await screen.findByRole("link", { name: "guide.pdf" });
  await choose(screen.getByLabelText("Replace guide.pdf"));
  expect(changes(fetchMock)).toHaveLength(0);
});

test("removes a PDF after asking", async () => {
  const fetchMock = server([GUIDE, { ...GUIDE, id: "b2", name: "other.pdf" }]);
  const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
  render(<ContentPage />);
  const item = (await screen.findByRole("link", { name: "guide.pdf" })).closest("li")!;
  fireEvent.click(within(item).getByRole("button", { name: "Remove" }));
  expect(changes(fetchMock)).toHaveLength(0);
  await act(async () => {
    fireEvent.click(within(item).getByRole("button", { name: "Remove" }));
  });
  expect(confirm).toHaveBeenCalledWith("Remove guide.pdf?");
  expect(fetchMock).toHaveBeenCalledWith("/api/content/a1", { method: "DELETE" });
  await waitFor(() => expect(screen.queryByRole("link", { name: "guide.pdf" })).toBeNull());
  expect(screen.getByRole("link", { name: "other.pdf" })).toBeTruthy();
});

test("a failed removal says so and keeps the PDF", async () => {
  server([GUIDE]);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.mocked(fetch).mockImplementation(async (_url, init) =>
    init?.method === "DELETE" ? new Response("", { status: 500 }) : Response.json([GUIDE]),
  );
  render(<ContentPage />);
  await screen.findByRole("link", { name: "guide.pdf" });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  });
  expect(await screen.findByText("guide.pdf: Could not remove it. Please try again.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "guide.pdf" })).toBeTruthy();
});

test("sizes read as KB or MB", () => {
  expect(size(10)).toBe("1 KB");
  expect(size(1536)).toBe("2 KB");
  expect(size(2_500_000)).toBe("2.4 MB");
});

test("shows how far each PDF has got being read, checking again until it is done", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const reading: Reading = { ...READ, state: "reading", page: 1, kind: null, counts: null };
  const fetchMock = server([GUIDE], {
    readings: [{ a1: { ...reading, state: "waiting", pages: 0 } }, { a1: reading }, { a1: READ }],
  });
  render(<ContentPage />);
  expect(await screen.findByText("Waiting to be read…")).toBeTruthy();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(READING_POLL_MS);
  });
  expect(await screen.findByText("Reading page 1 of 3…")).toBeTruthy();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(READING_POLL_MS);
  });
  expect(await screen.findByText(/Read 3 pages: 12 paragraphs, 1 table/)).toBeTruthy();
  const link = screen.getByRole("link", { name: "What was read" });
  expect(link.getAttribute("href")).toBe("/api/content/a1/reading");

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
  vi.useFakeTimers({ shouldAdvanceTime: true });
  server([GUIDE]);
  let checks = 0;
  vi.mocked(fetch).mockImplementation(async (url) => {
    if (url !== "/api/content/readings") return Response.json([GUIDE]);
    return ++checks === 1 ? new Response("", { status: 500 }) : Response.json({ a1: READ });
  });
  render(<ContentPage />);
  await screen.findByRole("link", { name: "guide.pdf" });
  await waitFor(() => expect(checks).toBe(1));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(READING_POLL_MS);
  });
  expect(await screen.findByText(/Read 3 pages/)).toBeTruthy();
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

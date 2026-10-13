import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { afterEach, expect, test, vi } from "vitest";

import type { Pdf, WikiContents, WikiVersion } from "./api";
import { changeText, WikiPage } from "./wiki";

const GUIDE: Pdf = {
  id: "a1",
  name: "guide.pdf",
  size: 2_500_000,
  added_at: "2026-10-12T06:00:00+00:00",
  replaced_at: null,
};

function contents(title: string, edited = false): WikiContents {
  return {
    pdf_id: "a1",
    pdf_name: "guide.pdf",
    lost_edits: [],
    entries: [
      {
        id: "a1-rain",
        title,
        summary: "Rain falls from clouds.",
        pages: [1],
        detail: false,
        edited,
        review: false,
        entries: [],
      },
    ],
  };
}

const VERSIONS: WikiVersion[] = [
  { id: "v3", at: "2026-10-13T09:00:00+00:00", change: { kind: "rebuilt" } },
  { id: "v2", at: "2026-10-13T08:00:00+00:00", change: { kind: "edited", title: "My rain" } },
  { id: "v1", at: "2026-10-13T07:00:00+00:00", change: { kind: "built" } },
];

// A fake wiki API with a history. `refuse` answers every change with that status: 412 until
// it is sent again with force.
function server(opts: { refuse?: number; history?: number; added?: number } = {}) {
  let wiki = contents("Rain");
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/content") return Response.json([GUIDE]);
    if (url === "/api/wiki/builds") return Response.json({});
    if (url.startsWith("/api/wiki/contents")) return Response.json([wiki]);
    if (url === "/api/content/a1/wiki/history") {
      if (opts.history) return new Response("", { status: opts.history });
      return Response.json(VERSIONS);
    }
    if (url === "/api/content/a1/wiki/history/v2") {
      return Response.json({ ...contents("My rain", true), ...VERSIONS[1] });
    }
    if (method === "POST" && opts.refuse && !(opts.refuse === 412 && url.includes("force=true"))) {
      const status = opts.refuse;
      const detail =
        status === 412 ? "This wiki was built from an earlier copy of the PDF." : "No.";
      return Response.json({ detail }, { status });
    }
    if (url.startsWith("/api/content/a1/wiki/history/v2/restore")) {
      wiki = contents("My rain", true);
      return Response.json({ restored: true });
    }
    if (url.startsWith("/api/content/a1/wiki/file") && method === "POST") {
      wiki = contents("From a file", true);
      return Response.json({ versions_added: opts.added ?? 2 });
    }
    return Response.json({ detail: "Not found" }, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function posted(fetchMock: ReturnType<typeof server>): string[] {
  return fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").map(([url]) => url);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function openHistory() {
  render(<WikiPage pdf="a1" />);
  fireEvent.click(await screen.findByRole("button", { name: "History" }));
  return (await screen.findByRole("heading", { name: "History" })).closest("div")!;
}

test("the history lists every version newest first, to read and restore", async () => {
  const fetchMock = server();
  const history = await openHistory();
  const items = within(history).getAllByRole("listitem");
  expect(items.map((i) => i.textContent)).toEqual([
    expect.stringContaining("Rebuilt with the LLM (the wiki now)"),
    expect.stringContaining("You edited “My rain”"),
    expect.stringContaining("Built with the LLM"),
  ]);
  expect(within(items[0]).queryByRole("button", { name: "Restore" })).toBeNull(); // it is now

  // Read the version before the rebuild: its outline, without Edit.
  fireEvent.click(within(items[1]).getByRole("button", { name: "View" }));
  expect(await within(items[1]).findByText("My rain")).toBeTruthy();
  expect(within(items[1]).getByText("Edited by you.")).toBeTruthy();
  expect(within(items[1]).queryByRole("button", { name: "Edit" })).toBeNull();

  fireEvent.click(within(items[1]).getByRole("button", { name: "Restore this version" }));
  expect(await screen.findByText(/is the wiki again/)).toBeTruthy();
  expect(posted(fetchMock)).toEqual(["/api/content/a1/wiki/history/v2/restore"]);
  // The wiki is loaded again, and the history with it.
  await waitFor(() => expect(screen.getAllByText("My rain").length).toBeGreaterThan(1));
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.filter(([url]) => url === "/api/content/a1/wiki/history").length,
    ).toBe(2),
  );

  fireEvent.click(screen.getByRole("button", { name: "Hide the history" }));
  expect(screen.queryByRole("heading", { name: "History" })).toBeNull();
});

test("restoring a version of a replaced PDF asks first", async () => {
  const fetchMock = server({ refuse: 412 });
  const history = await openHistory();
  const [, edited] = within(history).getAllByRole("listitem");
  fireEvent.click(within(edited).getByRole("button", { name: "Restore" }));
  expect(await screen.findByText(/earlier copy of the PDF/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByText(/earlier copy of the PDF/)).toBeNull();

  fireEvent.click(within(edited).getByRole("button", { name: "Restore" }));
  fireEvent.click(await screen.findByRole("button", { name: "Restore it anyway" }));
  expect(await screen.findByText(/is the wiki again/)).toBeTruthy();
  expect(posted(fetchMock)).toEqual([
    "/api/content/a1/wiki/history/v2/restore",
    "/api/content/a1/wiki/history/v2/restore",
    "/api/content/a1/wiki/history/v2/restore?force=true",
  ]);
});

test("a history that can't be loaded says so", async () => {
  server({ history: 500 });
  render(<WikiPage pdf="a1" />);
  fireEvent.click(await screen.findByRole("button", { name: "History" }));
  expect(await screen.findByText("The history could not be loaded. Try again.")).toBeTruthy();
});

test("the wiki is saved to a file with its history", async () => {
  server();
  render(<WikiPage pdf="a1" />);
  const save = await screen.findByRole("link", { name: "Save to a file" });
  expect(save.getAttribute("href")).toBe("/api/content/a1/wiki/file");
  expect(save.hasAttribute("download")).toBe(true);
});

function pick(name = "guide-wiki.json") {
  const input = screen.getByLabelText("Load a saved wiki file for guide.pdf") as HTMLInputElement;
  const file = new File(["{}"], name, { type: "application/json" });
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  fireEvent.change(input);
  return file;
}

test("a wiki file is loaded back, asking first when the PDF was replaced", async () => {
  const fetchMock = server({ refuse: 412 });
  render(<WikiPage pdf="a1" />);
  await screen.findByText("Rain");
  const click = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {});
  fireEvent.click(screen.getByRole("button", { name: "Load from a file" }));
  expect(click).toHaveBeenCalled(); // the file picker opens

  const file = pick();
  fireEvent.click(await screen.findByRole("button", { name: "Load it anyway" }));
  expect(
    await screen.findByText(/Loaded guide-wiki.json. Its history added 2 versions/),
  ).toBeTruthy();
  expect(await screen.findByText("From a file")).toBeTruthy();
  expect(posted(fetchMock)).toEqual([
    "/api/content/a1/wiki/file",
    "/api/content/a1/wiki/file?force=true",
  ]);
  const sent = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")?.[1]?.body;
  expect(sent instanceof FormData && sent.get("file")).toBe(file);
});

test.each([
  [0, "The history here already had all of its versions"],
  [1, "Its history added 1 version to this one"],
])("loading a file whose history adds %i versions says so", async (added, said) => {
  server({ added });
  render(<WikiPage pdf="a1" />);
  await screen.findByText("Rain");
  pick();
  expect(await screen.findByText(new RegExp(said))).toBeTruthy();
});

test("a file that isn't a wiki file is refused with the reason", async () => {
  server({ refuse: 422 });
  render(<WikiPage pdf="a1" />);
  await screen.findByText("Rain");
  pick("notes.txt");
  expect(await screen.findByText("No.")).toBeTruthy();
});

test("a change asked about first that then fails says why", async () => {
  let calls = 0;
  server();
  const fetchMock = vi.mocked(fetch);
  const answer = fetchMock.getMockImplementation()!;
  fetchMock.mockImplementation(async (url, init) => {
    if (init?.method === "POST") {
      calls += 1;
      const status = calls === 1 ? 412 : 409;
      return Response.json({ detail: `Refused ${status}.` }, { status });
    }
    return answer(url, init);
  });
  render(<WikiPage pdf="a1" />);
  await screen.findByText("Rain");
  pick();
  fireEvent.click(await screen.findByRole("button", { name: "Load it anyway" }));
  expect(await screen.findByText("Refused 409.")).toBeTruthy();
});

test("each kind of change is described", () => {
  const at = "2026-10-13T07:00:00+00:00";
  expect(changeText({ kind: "start" })).toBe("The wiki as it was before its history began");
  expect(changeText({ kind: "undone", title: "Rain" })).toBe("You undid your edit to “Rain”");
  expect(changeText({ kind: "kept", title: "Rain" })).toContain("after a rebuild");
  expect(changeText({ kind: "discarded", title: "Hail" })).toContain("without an entry");
  expect(changeText({ kind: "restored", restored_at: at })).toBe(
    `You restored the version from ${new Date(at).toLocaleString()}`,
  );
  expect(changeText({ kind: "restored", restored_at: "soon" })).toContain("from soon");
  expect(changeText({ kind: "loaded" })).toBe("You loaded it from a file");
});

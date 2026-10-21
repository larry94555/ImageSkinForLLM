import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { afterEach, expect, test, vi } from "vitest";

import { useContext } from "preact/hooks";

import type { Pdf, UiSettings, WikiBuild, WikiContents, WikiDetail } from "./api";
import { App } from "./App";
import { openSettings, returnToApp } from "./settings.test.util";
import { SettingsContext, SettingsProvider, useSettings } from "./settings";
import { WIKI_POLL_MS, WikiDetailPage, WikiPage } from "./wiki";

const GUIDE: Pdf = {
  id: "a1",
  name: "guide.pdf",
  size: 2_500_000,
  added_at: "2026-10-12T06:00:00+00:00",
  replaced_at: null,
};
const NOTES: Pdf = { ...GUIDE, id: "b2", name: "notes.pdf" };

const BUILT: WikiBuild = {
  state: "done",
  part: 1,
  parts: 1,
  pages: 2,
  skipped_parts: [],
  error: null,
  stage: "topics",
  steps: 0,
  steps_planned: 0,
  detail_pages: 1,
  elapsed_s: 30,
  remaining_s: null,
};

const CONTENTS: WikiContents = {
  pdf_id: "a1",
  pdf_name: "guide.pdf",
  lost_edits: [],
  entries: [
    {
      id: "a1-weather",
      title: "Weather",
      summary: "How the weather changes.",
      pages: [1, 2],
      detail: false,
      edited: false,
      review: false,
      entries: [
        {
          id: "a1-rain",
          title: "Rain",
          summary: "Rain falls from clouds.",
          pages: [1],
          detail: true,
          edited: false,
          review: false,
          entries: [
            {
              id: "a1-drops",
              title: "Drops",
              summary: "Drops grow until they fall.",
              pages: [1],
              detail: false,
              edited: false,
              review: false,
              entries: [],
            },
          ],
        },
        {
          id: "a1-snow",
          title: "Snow",
          summary: "Snow is frozen.",
          pages: [2],
          detail: false,
          edited: false,
          review: false,
          entries: [],
        },
      ],
    },
  ],
};

const DROPS: WikiDetail = {
  pdf_id: "a1",
  pdf_name: "guide.pdf",
  id: "a1-drops",
  title: "Drops",
  summary: "Drops grow until they fall.",
  pages: [1, 3],
  detail: true,
  edited: false,
  review: false,
  trail: [{ id: "a1-rain", title: "Rain" }],
  entries: [
    {
      id: "a1-size",
      title: "Size",
      summary: "Drops are small.",
      pages: [3],
      detail: false,
      edited: false,
      review: false,
      entries: [
        {
          id: "a1-tiny",
          title: "Tiny",
          summary: "Very small.",
          pages: [3],
          detail: false,
          edited: false,
          review: false,
          entries: [],
        },
      ],
    },
  ],
};

// A fake wiki API: the PDFs, their tables of contents and detail pages by id. `builds` are the
// wiki progress answers, in turn; the last one repeats. `refuse` makes the edits fail with that.
function server(
  pdfs: Pdf[],
  contents: WikiContents[],
  pages: Record<string, WikiDetail> = {},
  opts: { builds?: Record<string, WikiBuild>[]; refuse?: string } = {},
) {
  const builds = [...(opts.builds ?? [{}])];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/content") return Response.json(pdfs);
    if (url === "/api/wiki/builds") {
      return Response.json(builds.length > 1 ? builds.shift() : builds[0]);
    }
    if (url.startsWith("/api/wiki/contents")) {
      const pdf = new URL(url, "http://x").searchParams.get("pdf");
      return Response.json(contents.filter((c) => !pdf || c.pdf_id === pdf));
    }
    if (method !== "GET") {
      if (opts.refuse) return Response.json({ detail: opts.refuse }, { status: 422 });
      if (url.endsWith("/wiki/rebuild")) return Response.json({ ...BUILT, state: "waiting" });
      if (method === "PUT") return Response.json(JSON.parse(String(init?.body)));
      return Response.json({ ok: true });
    }
    const page = pages[decodeURIComponent(url.replace("/api/wiki/", ""))];
    if (page) return Response.json(page);
    return Response.json({ detail: "No such wiki page." }, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// The calls that changed something: method and address, and what was sent.
function changes(fetchMock: ReturnType<typeof server>): [string, string, unknown][] {
  return fetchMock.mock.calls
    .filter(([, init]) => init?.method && init.method !== "GET")
    .map(([url, init]) => [init!.method!, url, init?.body ? JSON.parse(String(init.body)) : null]);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.location.hash = "";
});

test("lists each PDF's table of contents, with summaries, links and PDF pages", async () => {
  server([GUIDE, NOTES], [CONTENTS]);
  render(<WikiPage />);
  const pdf = (await screen.findByRole("heading", { name: "guide.pdf" })).closest("article")!;
  expect(within(pdf).getByRole("link", { name: "guide.pdf" }).getAttribute("href")).toBe(
    "#/wiki/a1",
  );
  expect(within(pdf).getByText("How the weather changes.")).toBeTruthy();
  // Rain has a page of its own; Snow is said in full here.
  expect(within(pdf).getByRole("link", { name: "Rain" }).getAttribute("href")).toBe(
    "#/wiki/page/a1-rain",
  );
  expect(within(pdf).getByRole("link", { name: "Read more" }).getAttribute("href")).toBe(
    "#/wiki/page/a1-rain",
  );
  expect(within(pdf).queryByRole("link", { name: "Snow" })).toBeNull();
  expect(within(pdf).getByText("Drops grow until they fall.")).toBeTruthy(); // every level
  const page2 = within(pdf).getAllByRole("link", { name: "2" })[0];
  expect(page2.getAttribute("href")).toBe("/api/content/a1#page=2");
  expect(page2.getAttribute("target")).toBe("_blank");
  // A PDF not built yet says so.
  expect(screen.getByText(/notes\.pdf: its wiki isn't ready yet/)).toBeTruthy();
});

test("levels open and close, one at a time or all together", async () => {
  server([GUIDE], [CONTENTS]);
  render(<WikiPage pdf="a1" />);
  await screen.findByText("How the weather changes.");
  expect(screen.getByRole("link", { name: "All PDFs" }).getAttribute("href")).toBe("#/wiki");
  const details = [...document.querySelectorAll("details")];
  expect(details.map((d) => d.open)).toEqual([false, false]); // Weather, and Rain inside it
  fireEvent.click(screen.getByRole("button", { name: "Open all" }));
  expect(details.map((d) => d.open)).toEqual([true, true]);
  fireEvent.click(screen.getByRole("button", { name: "Close all" }));
  expect(details.map((d) => d.open)).toEqual([false, false]);
  details[0].open = true; // as clicking it does
  expect(screen.getByText("Snow is frozen.")).toBeTruthy();
});

test("a detail page has a trail back up, its PDF pages and its own parts", async () => {
  server([GUIDE], [CONTENTS], { "a1-drops": DROPS });
  render(<WikiDetailPage entry="a1-drops" />);
  expect(await screen.findByRole("heading", { name: "Drops", level: 1 })).toBeTruthy();
  const trail = within(screen.getByRole("navigation", { name: "Where this page is" }));
  expect(trail.getAllByRole("link").map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
    ["Manage Content", "#/content"],
    ["Wiki", "#/wiki"],
    ["guide.pdf", "#/wiki/a1"],
    ["Rain", "#/wiki/page/a1-rain"],
  ]);
  expect(screen.getByText("Drops grow until they fall.")).toBeTruthy();
  expect(screen.getAllByRole("link", { name: "3" })[0].getAttribute("href")).toBe(
    "/api/content/a1#page=3",
  );
  expect(screen.getByText("Very small.")).toBeTruthy(); // inside a closed level
});

test("a missing detail page says so and leads back", async () => {
  server([GUIDE], [CONTENTS]);
  render(<WikiDetailPage entry="a1-gone" />);
  expect(await screen.findByText(/no longer here/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "Back to the wiki" }).getAttribute("href")).toBe(
    "#/wiki",
  );
  expect(screen.queryByText(/could not be loaded/)).toBeNull();
});

test("a detail page that can't be loaded says so, not that it was removed", async () => {
  const errors = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("", { status: 500 })),
  );
  const { unmount } = render(<WikiDetailPage entry="a1-drops" />);
  expect(await screen.findByText(/could not be loaded/)).toBeTruthy();
  expect(screen.queryByText(/no longer here/)).toBeNull();
  unmount();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))),
  );
  render(<WikiDetailPage entry="a1-drops" />);
  expect(await screen.findByText(/could not be loaded/)).toBeTruthy();
  expect(errors).toHaveBeenCalledTimes(2);
});

test("with no PDFs, or a removed one, the wiki says what to do", async () => {
  server([], []);
  const { unmount } = render(<WikiPage />);
  expect(await screen.findByText(/There are no PDFs yet/)).toBeTruthy();
  unmount();
  server([GUIDE], []);
  render(<WikiPage pdf="zz" />);
  expect(await screen.findByText(/This PDF is no longer here/)).toBeTruthy();
});

test("the wiki says when it can't be loaded", async () => {
  const errors = vi.spyOn(console, "error").mockImplementation(() => {});
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("", { status: 500 })),
  );
  render(<WikiPage />);
  expect(await screen.findByText("The wiki couldn't be loaded. Reload the page to try again.")).toBeTruthy();
  expect(errors).toHaveBeenCalled();
});

test("for the host the wiki is part of Manage Content, with no top bar link of its own", async () => {
  // Larry's review of PR #123: the wiki is built from the PDFs, so it is reached from there.
  server([GUIDE], [CONTENTS], { "a1-drops": DROPS });
  window.location.hash = "#/wiki";
  render(<App />);
  const nav = within(screen.getByRole("navigation", { name: "" }));
  await screen.findByText("How the weather changes.");
  expect(nav.queryByRole("link", { name: "Wiki" })).toBeNull();
  expect(nav.getByRole("link", { name: "Manage Content" }).className).toBe("current");
  const trail = within(screen.getByRole("navigation", { name: "Where this page is" }));
  expect(trail.getByRole("link", { name: "Manage Content" }).getAttribute("href")).toBe("#/content");
  window.location.hash = "#/wiki/page/a1-drops";
  window.dispatchEvent(new HashChangeEvent("hashchange"));
  expect(await screen.findByRole("heading", { name: "Drops", level: 1 })).toBeTruthy();
  await waitFor(() =>
    expect(nav.getByRole("link", { name: "Manage Content" }).className).toBe("current"),
  );
  const detail = within(screen.getByRole("navigation", { name: "Where this page is" }));
  expect(detail.getAllByRole("link").map((a) => a.textContent).slice(0, 2)).toEqual([
    "Manage Content",
    "Wiki",
  ]);
});

test("an entry's title and summary are edited and saved", async () => {
  const fetchMock = server([GUIDE], [CONTENTS]);
  render(<WikiPage pdf="a1" />);
  await screen.findByText("How the weather changes.");
  const edits = screen.getAllByRole("button", { name: "Edit" });
  fireEvent.click(edits[edits.length - 1]); // Snow's
  const form = screen.getByRole("form", { name: "Edit Snow" });
  const title = within(form).getByLabelText("Title") as HTMLInputElement;
  expect(title.value).toBe("Snow");
  fireEvent.input(title, { target: { value: "Snow and ice" } });
  fireEvent.input(within(form).getByLabelText("Summary"), { target: { value: "Frozen rain." } });
  fireEvent.click(within(form).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(screen.queryByRole("form")).toBeNull());
  expect(changes(fetchMock)).toEqual([
    ["PUT", "/api/wiki/a1-snow", { title: "Snow and ice", summary: "Frozen rain." }],
  ]);
  // Loaded again, with the saved text.
  await waitFor(() =>
    expect(
      fetchMock.mock.calls.filter(([url]) => String(url).startsWith("/api/wiki/contents")).length,
    ).toBe(2),
  );
});

test("an edit can be cancelled, and a refused one says why", async () => {
  const errors = vi.spyOn(console, "error").mockImplementation(() => {});
  const fetchMock = server(
    [GUIDE],
    [CONTENTS],
    {},
    { refuse: "A wiki entry needs a title and a summary." },
  );
  render(<WikiPage pdf="a1" />);
  await screen.findByText("How the weather changes.");
  fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("form")).toBeNull();
  expect(changes(fetchMock)).toEqual([]);

  fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
  const form = screen.getByRole("form", { name: "Edit Weather" });
  const summary = within(form).getByLabelText("Summary");
  fireEvent.input(summary, { target: { value: " " } });
  expect((within(form).getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(
    true,
  );
  fireEvent.input(summary, { target: { value: "Weather." } });
  fireEvent.submit(form);
  expect(await screen.findByText("A wiki entry needs a title and a summary.")).toBeTruthy();
  expect(screen.getByRole("form")).toBeTruthy(); // kept, to fix
  expect(errors).toHaveBeenCalled();
});

test("an edited entry says so and can be undone", async () => {
  const edited: WikiContents = {
    ...CONTENTS,
    entries: [{ ...CONTENTS.entries[0], title: "My weather", edited: true }],
  };
  const fetchMock = server([GUIDE], [edited]);
  render(<WikiPage pdf="a1" />);
  expect(await screen.findByText("My weather")).toBeTruthy();
  expect(screen.getByText(/Edited by you/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Undo my edit" }));
  await waitFor(() =>
    expect(changes(fetchMock)).toEqual([["DELETE", "/api/wiki/a1-weather/edit", null]]),
  );
});

test("after a rebuild an edit shows the new text, to keep the edit or use the new text", async () => {
  const flagged: WikiContents = {
    ...CONTENTS,
    entries: [
      {
        ...CONTENTS.entries[0],
        title: "My weather",
        edited: true,
        review: true,
        built: { title: "Weather", summary: "The new summary." },
      },
    ],
  };
  const fetchMock = server([GUIDE], [flagged]);
  render(<WikiPage pdf="a1" />);
  expect(await screen.findByText(/The wiki was rebuilt after you edited this/)).toBeTruthy();
  expect(screen.getByText(/The new summary\./)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Keep my edit" }));
  fireEvent.click(screen.getByRole("button", { name: "Use the new text" }));
  await waitFor(() =>
    expect(changes(fetchMock)).toEqual([
      ["POST", "/api/wiki/a1-weather/reviewed", null],
      ["DELETE", "/api/wiki/a1-weather/edit", null],
    ]),
  );
});

test("edits a rebuild left without an entry are listed until discarded", async () => {
  const left: WikiContents = {
    ...CONTENTS,
    lost_edits: [{ id: "a1-hail", title: "Hail", summary: "What I wrote about hail." }],
  };
  const fetchMock = server([GUIDE], [left]);
  render(<WikiPage pdf="a1" />);
  expect(await screen.findByText("What I wrote about hail.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Discard" }));
  await waitFor(() =>
    expect(changes(fetchMock)).toEqual([["DELETE", "/api/wiki/a1-hail/edit", null]]),
  );
});

test("rebuilding asks first, shows the progress, then loads the new wiki", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const building: WikiBuild = { ...BUILT, state: "building", part: 0, pages: null, elapsed_s: 5 };
  const fetchMock = server(
    [GUIDE],
    [CONTENTS],
    {},
    { builds: [{ a1: BUILT }, { a1: building }, { a1: BUILT }] },
  );
  render(<WikiPage pdf="a1" />);
  await screen.findByText("How the weather changes.");
  // The PDF's buttons are in one row (R41e).
  const row = document.querySelector(".pdf-tools") as HTMLElement;
  expect(within(row).getAllByRole("button").map((b) => b.textContent)).toEqual([
    "Rebuild the wiki",
    "History",
    "Load from a file",
  ]);
  expect(within(row).getAllByRole("link").map((a) => a.textContent)).toEqual([
    "Open the PDF",
    "Save to a file",
  ]);
  fireEvent.click(screen.getByRole("button", { name: "Rebuild the wiki" }));
  const asking = screen.getByText(/Your edits are kept/);
  expect(asking.textContent).toMatch(/^Build this PDF's wiki again\? The AI reads the PDF again/);
  expect(asking.textContent).not.toMatch(/LLM/); // no technical words (R41e)
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(changes(fetchMock)).toEqual([]);

  fireEvent.click(screen.getByRole("button", { name: "Rebuild the wiki" }));
  fireEvent.click(screen.getByRole("button", { name: "Rebuild" }));
  expect(await screen.findByText(/Waiting to build the wiki/)).toBeTruthy();
  expect(changes(fetchMock)).toEqual([["POST", "/api/content/a1/wiki/rebuild", null]]);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(WIKI_POLL_MS);
  });
  expect(await screen.findByText(/Building the wiki/)).toBeTruthy();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(WIKI_POLL_MS);
  });
  expect(await screen.findByRole("button", { name: "Rebuild the wiki" })).toBeTruthy();
  const loads = fetchMock.mock.calls.filter(([url]) =>
    String(url).startsWith("/api/wiki/contents"),
  );
  expect(loads.length).toBe(2); // the new wiki
  vi.useRealTimers();
});

test("a refused rebuild says why", async () => {
  const errors = vi.spyOn(console, "error").mockImplementation(() => {});
  server([GUIDE], [CONTENTS], {}, { refuse: "The PDF hasn't been read yet." });
  render(<WikiPage pdf="a1" />);
  await screen.findByText("How the weather changes.");
  fireEvent.click(screen.getByRole("button", { name: "Rebuild the wiki" }));
  fireEvent.click(screen.getByRole("button", { name: "Rebuild" }));
  expect(await screen.findByText("The PDF hasn't been read yet.")).toBeTruthy();
  expect(errors).toHaveBeenCalled();
});

test("a detail page's own title and summary are edited there", async () => {
  const fetchMock = server([GUIDE], [CONTENTS], { "a1-drops": DROPS });
  render(<WikiDetailPage entry="a1-drops" />);
  await screen.findByRole("heading", { name: "Drops", level: 1 });
  fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
  const form = screen.getByRole("form", { name: "Edit Drops" });
  fireEvent.input(within(form).getByLabelText("Title"), { target: { value: "Raindrops" } });
  fireEvent.click(within(form).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(screen.queryByRole("form")).toBeNull());
  expect(changes(fetchMock)[0]).toEqual([
    "PUT",
    "/api/wiki/a1-drops",
    { title: "Raindrops", summary: "Drops grow until they fall." },
  ]);
  fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByRole("heading", { name: "Drops", level: 1 })).toBeTruthy();
});

test("a failed undo says why", async () => {
  const errors = vi.spyOn(console, "error").mockImplementation(() => {});
  const edited: WikiContents = {
    ...CONTENTS,
    entries: [{ ...CONTENTS.entries[0], edited: true }],
    lost_edits: [{ id: "a1-hail", title: "Hail", summary: "Hail." }],
  };
  server([GUIDE], [edited], {}, { refuse: "The edit could not be saved. Try again." });
  render(<WikiPage pdf="a1" />);
  await screen.findByText("How the weather changes.");
  fireEvent.click(screen.getByRole("button", { name: "Undo my edit" }));
  fireEvent.click(screen.getByRole("button", { name: "Discard" }));
  await waitFor(() => expect(screen.getAllByText(/The edit could not be saved/).length).toBe(2));
  expect(errors).toHaveBeenCalled();
});

test("a rebuild that fails later says so, and can be tried again", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const building: WikiBuild = { ...BUILT, state: "building", part: 0, pages: null };
  const failed: WikiBuild = {
    ...BUILT,
    state: "failed",
    error: "The LLM refused the prompt (400)",
  };
  const fetchMock = server(
    [GUIDE],
    [CONTENTS],
    {},
    {
      builds: [{ a1: BUILT }, { a1: building }, { a1: failed }],
    },
  );
  render(<WikiPage pdf="a1" />);
  await screen.findByText("How the weather changes.");
  fireEvent.click(screen.getByRole("button", { name: "Rebuild the wiki" }));
  fireEvent.click(screen.getByRole("button", { name: "Rebuild" }));
  expect(await screen.findByText(/Waiting to build the wiki/)).toBeTruthy();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(WIKI_POLL_MS);
  });
  expect(await screen.findByText(/Building the wiki/)).toBeTruthy();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(WIKI_POLL_MS);
  });
  expect(
    await screen.findByText(/The last rebuild didn't finish: The LLM refused the prompt/),
  ).toBeTruthy();
  expect(screen.getByText("How the weather changes.")).toBeTruthy(); // the pages built before
  fireEvent.click(screen.getByRole("button", { name: "Rebuild the wiki" }));
  fireEvent.click(screen.getByRole("button", { name: "Rebuild" }));
  await waitFor(() => expect(changes(fetchMock).length).toBe(2)); // tried again
  vi.useRealTimers();
});

// The wiki server above, with the settings saved as `saved` (R41b); PATCH changes them.
function withSettings(saved: { show_metrics: boolean; view: string }) {
  const wiki = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url !== "/api/settings") return wiki(url, init);
      if (init?.method === "PATCH") Object.assign(saved, JSON.parse(String(init.body)));
      return Response.json(saved);
    }),
  );
}

const PARTICIPANT = { show_metrics: false, view: "participant" };

test("the participant view has only the chat and a read-only wiki with its PDFs", async () => {
  const edited: WikiContents = {
    ...CONTENTS,
    entries: [{ ...CONTENTS.entries[0], edited: true }],
    lost_edits: [{ id: "a1-old", title: "Old", summary: "Gone." }],
  };
  server([GUIDE, NOTES], [edited], { "a1-drops": DROPS });
  withSettings({ ...PARTICIPANT });
  window.location.hash = "#/wiki";
  render(<App />);
  const pdf = (await screen.findByRole("heading", { name: "guide.pdf" })).closest("article")!;
  const nav = within(screen.getByRole("navigation", { name: "" }));
  expect(nav.getAllByRole("link").map((a) => a.textContent)).toEqual(["Chat", "Wiki"]);
  expect(screen.getByRole("link", { name: "ImageSkinForLLM" }).getAttribute("href")).toBe("#/chat");

  const open = within(pdf).getByRole("link", { name: "Open the PDF" });
  expect(open.getAttribute("href")).toBe("/api/content/a1");
  expect(open.getAttribute("target")).toBe("_blank");
  expect(within(pdf).getByText("How the weather changes.")).toBeTruthy();
  for (const name of ["Rebuild the wiki", "History", "Load from a file", "Edit"]) {
    expect(screen.queryByRole("button", { name })).toBeNull();
  }
  expect(screen.queryByRole("link", { name: "Save to a file" })).toBeNull();
  expect(screen.queryByText(/Edited by you/)).toBeNull();
  expect(screen.queryByText("Old")).toBeNull(); // edits a rebuild left without an entry
  expect(screen.getByText(/notes\.pdf: its wiki isn't ready yet\.$/)).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Manage Content" })).toBeNull();
  expect(screen.queryByText(/You can edit any entry/)).toBeNull();

  window.location.hash = "#/wiki/page/a1-drops";
  window.dispatchEvent(new HashChangeEvent("hashchange"));
  expect(await screen.findByRole("heading", { name: "Drops", level: 1 })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
});

test("in the participant view a host's page shows the chat instead", async () => {
  server([], []);
  withSettings({ ...PARTICIPANT });
  for (const hash of ["#/", "#/setup", "#/content", "#/guide", "#/consent"]) {
    window.location.hash = hash;
    render(<App />);
    await waitFor(() => expect(window.location.hash).toBe("#/chat"));
    cleanup();
  }
  window.location.hash = "#/wiki";
  render(<App />);
  expect(await screen.findByText("There are no PDFs yet.")).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Manage Content" })).toBeNull();
});

test("switching the view on the Settings page shows or hides the host's options", async () => {
  server([GUIDE], [CONTENTS]);
  const saved = { show_metrics: false, view: "host" };
  withSettings(saved);
  window.location.hash = "#/wiki";
  render(<App />);
  await screen.findByText("How the weather changes.");
  expect(screen.getAllByRole("button", { name: "Edit" }).length).toBeGreaterThan(0);
  // The top bar, the trail and the text.
  expect(screen.getAllByRole("link", { name: "Manage Content" }).length).toBe(3);

  await openSettings();
  expect((screen.getByRole("radio", { name: /Host/ }) as HTMLInputElement).checked).toBe(true);
  // Teacher and Student were renamed; for now the old words follow in parentheses (2026-10-19).
  expect(screen.getByText("Host (Teacher)")).toBeTruthy();
  expect(screen.getByText("Participant (Student)")).toBeTruthy();
  await act(async () => {
    fireEvent.click(screen.getByRole("radio", { name: /Participant/ }));
  });
  expect(saved.view).toBe("participant");
  await waitFor(() => expect(screen.queryByRole("link", { name: "Manage Content" })).toBeNull());
  await returnToApp();
  expect(window.location.hash).toBe("#/wiki"); // back where it was opened from
  await screen.findByText("How the weather changes.");
  expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();

  await openSettings(); // still there in the participant view, to switch back
  await act(async () => {
    fireEvent.click(screen.getByRole("radio", { name: /Host/ }));
  });
  expect(saved.view).toBe("host");
  await returnToApp();
  expect((await screen.findAllByRole("button", { name: "Edit" })).length).toBeGreaterThan(0);
  expect(screen.getByRole("button", { name: "Rebuild the wiki" })).toBeTruthy();
});

test("a view that can't be saved says so and stays as it was", async () => {
  server([GUIDE], [CONTENTS]);
  const wiki = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url !== "/api/settings") return wiki(url, init);
      if (init?.method === "PATCH") return new Response("", { status: 500 });
      return Response.json({ show_metrics: false, view: "host" });
    }),
  );
  window.location.hash = "#/wiki";
  render(<App />);
  await screen.findByText("How the weather changes.");
  await openSettings();
  await act(async () => {
    fireEvent.click(screen.getByRole("radio", { name: /Participant/ }));
  });
  expect(await screen.findByText("The setting could not be changed. Try again.")).toBeTruthy();
  expect((screen.getByRole("radio", { name: /Host/ }) as HTMLInputElement).checked).toBe(true);
  await returnToApp();
  expect((await screen.findAllByRole("button", { name: "Edit" })).length).toBeGreaterThan(0);
});

test("while the settings load, the top bar shows no host's links", async () => {
  // Review on PR #77: the top bar showed the host's links until a Participant view was read.
  server([GUIDE], [CONTENTS]);
  const wiki = globalThis.fetch;
  let answer: (r: Response) => void = () => {};
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) =>
      url === "/api/settings" ? new Promise<Response>((r) => (answer = r)) : wiki(url, init),
    ),
  );
  window.location.hash = "#/wiki";
  render(<App />);
  const nav = within(screen.getByRole("navigation", { name: "" }));
  await act(async () => {}); // consent is read; the settings are not yet
  expect(nav.queryAllByRole("link")).toEqual([]);
  expect(screen.getByRole("link", { name: "ImageSkinForLLM" }).getAttribute("href")).toBe("#/chat");
  expect(screen.queryByText("How the weather changes.")).toBeNull();
  expect(screen.queryByRole("link", { name: "Settings" })).toBeNull();

  await act(async () => answer(Response.json(PARTICIPANT)));
  await screen.findByText("How the weather changes.");
  expect(nav.getAllByRole("link").map((a) => a.textContent)).toEqual(["Chat", "Wiki"]);
  expect(screen.getByRole("link", { name: "Settings" }).getAttribute("href")).toBe("#/settings");
});

test("a change saved before the first read finishes is not undone by it", async () => {
  // Review on PR #77: a slow first read could put the Host view back after Participant was saved.
  let answer: (r: Response) => void = () => {};
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === "PATCH"
        ? Response.json(PARTICIPANT)
        : new Promise<Response>((r) => (answer = r)),
    ),
  );
  let change: (c: Partial<UiSettings>) => Promise<void> = async () => {};
  function Shows() {
    const settings = useSettings();
    change = useContext(SettingsContext).change;
    return <p>{settings.view}</p>;
  }
  render(
    <SettingsProvider>
      <Shows />
    </SettingsProvider>,
  );
  await act(() => change({ view: "participant" }));
  expect(screen.getByText("participant")).toBeTruthy();
  await act(async () => {
    answer(Response.json({ show_metrics: false, view: "host" }));
    await new Promise((r) => setTimeout(r, 20)); // time for the read to be applied, if it were
  });
  expect(screen.getByText("participant")).toBeTruthy();
});

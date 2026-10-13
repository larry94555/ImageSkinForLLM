import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { afterEach, expect, test, vi } from "vitest";

import type { Pdf, WikiContents, WikiDetail } from "./api";
import { App } from "./App";
import { WikiDetailPage, WikiPage } from "./wiki";

const GUIDE: Pdf = {
  id: "a1",
  name: "guide.pdf",
  size: 2_500_000,
  added_at: "2026-10-12T06:00:00+00:00",
  replaced_at: null,
};
const NOTES: Pdf = { ...GUIDE, id: "b2", name: "notes.pdf" };

const CONTENTS: WikiContents = {
  pdf_id: "a1",
  pdf_name: "guide.pdf",
  entries: [
    {
      id: "a1-weather",
      title: "Weather",
      summary: "How the weather changes.",
      pages: [1, 2],
      detail: false,
      entries: [
        {
          id: "a1-rain",
          title: "Rain",
          summary: "Rain falls from clouds.",
          pages: [1],
          detail: true,
          entries: [
            {
              id: "a1-drops",
              title: "Drops",
              summary: "Drops grow until they fall.",
              pages: [1],
              detail: false,
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
  trail: [{ id: "a1-rain", title: "Rain" }],
  entries: [
    {
      id: "a1-size",
      title: "Size",
      summary: "Drops are small.",
      pages: [3],
      detail: false,
      entries: [
        {
          id: "a1-tiny",
          title: "Tiny",
          summary: "Very small.",
          pages: [3],
          detail: false,
          entries: [],
        },
      ],
    },
  ],
};

// A fake wiki API: the PDFs, their tables of contents and detail pages by id.
function server(pdfs: Pdf[], contents: WikiContents[], pages: Record<string, WikiDetail> = {}) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url === "/api/consent") return Response.json({ agreed: true, agreed_at: null });
    if (url === "/api/content") return Response.json(pdfs);
    if (url.startsWith("/api/wiki/contents")) {
      const pdf = new URL(url, "http://x").searchParams.get("pdf");
      return Response.json(contents.filter((c) => !pdf || c.pdf_id === pdf));
    }
    const page = pages[decodeURIComponent(url.replace("/api/wiki/", ""))];
    if (page) return Response.json(page);
    return Response.json({ detail: "No such wiki page." }, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
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
  expect(await screen.findByText(/could not be loaded/)).toBeTruthy();
  expect(errors).toHaveBeenCalled();
});

test("the top bar links to the wiki, and a detail page's link opens it", async () => {
  server([GUIDE], [CONTENTS], { "a1-drops": DROPS });
  window.location.hash = "#/wiki";
  render(<App />);
  const nav = within(screen.getByRole("navigation", { name: "" }));
  await screen.findByText("How the weather changes.");
  expect(nav.getByRole("link", { name: "Wiki" }).className).toBe("current");
  window.location.hash = "#/wiki/page/a1-drops";
  window.dispatchEvent(new HashChangeEvent("hashchange"));
  expect(await screen.findByRole("heading", { name: "Drops", level: 1 })).toBeTruthy();
  await waitFor(() => expect(nav.getByRole("link", { name: "Wiki" }).className).toBe("current"));
});

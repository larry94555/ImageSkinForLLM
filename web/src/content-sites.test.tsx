// A host's PDFs on several of their sites (roadmap R258a): Manage Content shows, for a host with
// more than one site, which of them use each PDF, gives it to another or takes it off, and asks
// whether Remove takes a shared PDF off this site only or deletes it from every site.

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

import { App } from "./App";

vi.unmock("./api");

const ANN = { site: "ann", address: "https://ann.me0.ai", here: true };
const TWO = { site: "ann-two", address: "https://ann-two.me0.ai", here: false };
const GUIDE = {
  id: "a1",
  name: "guide.pdf",
  size: 1000,
  added_at: "2026-11-04T06:00:00+00:00",
  replaced_at: null,
};

interface Answers {
  sites?: object[];
  uses?: Record<string, string[]>;
  refuse?: string;
  hold?: Promise<void>;
}

function server(answers: Answers = {}) {
  const asked: string[] = [];
  let uses = { a1: ["ann"], ...answers.uses };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      asked.push(
        `${method} ${url} ${init?.body && typeof init.body === "string" ? init.body : ""}`.trim(),
      );
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") return Response.json({});
      if (url === "/api/host/page") return new Response(null, { status: 204 });
      if (url === "/api/host/session") {
        return Response.json({
          signed_in: true,
          email: "ann@example.com",
          confirmed: true,
        });
      }
      if (url === "/api/host/sites")
        return Response.json({ sites: answers.sites ?? [ANN, TWO] });
      if (url === "/api/content" && method === "GET")
        return Response.json([GUIDE]);
      if (url === "/api/content/sites") return Response.json(uses);
      if (url === "/api/content/readings" || url === "/api/wiki/builds")
        return Response.json({});
      const change = /^\/api\/content\/a1\/sites\/(.+)$/.exec(url);
      if (change) {
        if (answers.refuse)
          return Response.json({ detail: answers.refuse }, { status: 500 });
        await answers.hold; // a slow answer, while more boxes are clicked
        const others = uses.a1.filter((s) => s !== change[1]);
        uses = { a1: method === "PUT" ? [...others, change[1]] : others };
        return Response.json({ sites: uses.a1 });
      }
      if (method === "DELETE") return Response.json({ removed: true });
      return new Response("", { status: 404 });
    }),
  );
  return asked;
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

async function content() {
  window.location.hash = "#/content";
  render(<App />);
  await screen.findByText("guide.pdf");
}

// The box Remove opens to ask first.
async function askedToRemove(): Promise<HTMLElement> {
  await act(async () => {});
  const title = await screen.findByText("Remove guide.pdf?");
  return (title.closest("dialog") ?? title.parentElement) as HTMLElement;
}

function site(name: string | RegExp): HTMLInputElement {
  const used = screen.getByRole("group", { name: "Used on" });
  return within(used).getByRole("checkbox", {
    name: new RegExp(name),
  }) as HTMLInputElement;
}

test("each PDF shows the host's sites that use it, and is given to another or taken off", async () => {
  const asked = server();
  await content();
  await waitFor(() => expect(site("ann-two.me0.ai").checked).toBe(false));
  expect(site(/^ann\.me0\.ai.*this site/).checked).toBe(true);
  expect(site(/^ann\.me0\.ai.*this site/).disabled).toBe(true);
  await act(async () => {
    fireEvent.click(site("ann-two.me0.ai"));
  });
  await waitFor(() => expect(site("ann-two.me0.ai").checked).toBe(true));
  expect(asked).toContain("PUT /api/content/a1/sites/ann-two");
  await act(async () => {
    fireEvent.click(site("ann-two.me0.ai"));
  });
  await waitFor(() => expect(site("ann-two.me0.ai").checked).toBe(false));
  expect(asked).toContain("DELETE /api/content/a1/sites/ann-two");
});

test("a change refused says why", async () => {
  server({ refuse: "The PDF's sites could not be saved just now. Try again." });
  await content();
  await waitFor(() => site("ann-two.me0.ai"));
  await act(async () => {
    fireEvent.click(site("ann-two.me0.ai"));
  });
  expect(
    await screen.findByText(
      "guide.pdf: The PDF's sites could not be saved just now. Try again.",
    ),
  ).toBeTruthy();
  expect(site("ann-two.me0.ai").checked).toBe(false);
});

test("Remove asks whether a shared PDF leaves this site only or every site", async () => {
  const asked = server({ uses: { a1: ["ann", "ann-two"] } });
  await content();
  await waitFor(() => expect(site("ann-two.me0.ai").checked).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  const dialog = await askedToRemove();
  expect(dialog.textContent).toContain("It is also on ann-two.me0.ai.");
  await act(async () => {
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Remove from this site" }),
    );
  });
  await waitFor(() => expect(screen.queryByText("guide.pdf")).toBeNull());
  expect(asked).toContain("DELETE /api/content/a1");
  expect(asked.some((a) => a.includes("everywhere"))).toBe(false);
});

test("Delete everywhere deletes a shared PDF from every site", async () => {
  const asked = server({ uses: { a1: ["ann", "ann-two"] } });
  await content();
  await waitFor(() => expect(site("ann-two.me0.ai").checked).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  const dialog = await askedToRemove();
  await act(async () => {
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Delete everywhere" }),
    );
  });
  await waitFor(() => expect(screen.queryByText("guide.pdf")).toBeNull());
  expect(asked).toContain("DELETE /api/content/a1/everywhere");
});

test("a host with one site, or a PDF on this site only, is asked as before", async () => {
  const asked = server({ sites: [ANN] });
  await content();
  await act(async () => {});
  expect(screen.queryByRole("group", { name: "Used on" })).toBeNull();
  expect(asked.some((a) => a.includes("/api/content/sites"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Remove" }));
  const dialog = await askedToRemove();
  expect(dialog.textContent).toContain("Its wiki pages are removed too.");
  await act(async () => {
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Yes, remove it" }),
    );
  });
  expect(asked).toContain("DELETE /api/content/a1");
});

test("a box clicked while a change is saved waits, so no change undoes another", async () => {
  // Codex's review of PR #306: two sites ticked quickly are both kept.
  const THREE = {
    site: "ann-three",
    address: "https://ann-three.me0.ai",
    here: false,
  };
  let release = () => {};
  const asked = server({
    sites: [ANN, TWO, THREE],
    hold: new Promise<void>((resolve) => {
      release = resolve;
    }),
  });
  await content();
  await waitFor(() => site("ann-two.me0.ai"));
  await act(async () => {
    fireEvent.click(site("ann-two.me0.ai"));
  });
  // While ann-two's change is saved, the PDF's boxes wait.
  expect(site("ann-three.me0.ai").disabled).toBe(true);
  await act(async () => {
    fireEvent.click(site("ann-three.me0.ai"));
  });
  expect(asked.filter((a) => a.startsWith("PUT"))).toEqual([
    "PUT /api/content/a1/sites/ann-two",
  ]);
  await act(async () => {
    release();
  });
  await waitFor(() => expect(site("ann-three.me0.ai").disabled).toBe(false));
  await act(async () => {
    fireEvent.click(site("ann-three.me0.ai"));
  });
  await waitFor(() => expect(site("ann-three.me0.ai").checked).toBe(true));
  expect(site("ann-two.me0.ai").checked).toBe(true);
  expect(asked.filter((a) => a.startsWith("PUT"))).toEqual([
    "PUT /api/content/a1/sites/ann-two",
    "PUT /api/content/a1/sites/ann-three",
  ]);
});

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { AdminGuidelines, AdminGuidelinesEdit } from "./api";

const FEATURES = [
  { key: "questions", label: "Answering questions", section: "Guidelines", changes: "How answers are written." },
  { key: "topics", label: "Topics", section: "Guidelines", changes: "How a topic is talked about." },
  { key: "assessment questions", label: "Assessment questions", section: "Assessment", changes: "How questions are asked." },
];
const BLANK = { name: "", speaks_as: "", purpose: "", audience: "", helps_with: "" };

// A server with an administrator signed in, keeping the admin guidelines as the real one does.
function server(kept: Partial<AdminGuidelinesEdit> = {}) {
  const state = {
    signedIn: true,
    edit: { identity: { ...BLANK }, goals: [] as string[], guidelines: {} as Record<string, string>, ...kept },
    refuse: null as number | null,
    readFails: false,
    // Each part's changes and the one in use, kept as the real history keeps them (R253).
    history: {} as Record<string, { current: number; changes: { number: number; made_by: string; value: unknown }[] }>,
  };
  const valueOf = (edit: AdminGuidelinesEdit, part: string): unknown =>
    part === "identity" ? edit.identity : part === "goals" ? edit.goals : (edit.guidelines[part] ?? "");
  const parts = () => ["identity", "goals", ...FEATURES.map((f) => f.key)];
  const labelOf = (part: string) =>
    part === "identity" ? "Identity" : part === "goals" ? "Goals" : FEATURES.find((f) => f.key === part)!.label;
  const shown = (): AdminGuidelines => ({
    ...state.edit,
    guidelines: Object.fromEntries(FEATURES.map((f) => [f.key, state.edit.guidelines[f.key] ?? ""])),
    features: FEATURES.map((f) => ({ ...f, text: state.edit.guidelines[f.key] ?? "" })),
  });
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/consent") return Response.json({ agreed: true });
    if (url === "/api/settings") return Response.json({});
    if (url === "/api/admin/laptop") return Response.json({ listed: true });
    if (url === "/api/admin/session") {
      return Response.json({ signed_in: state.signedIn, password_set: true, timeout_minutes: 30, ended: null });
    }
    if (url === "/api/admin/guidelines") {
      if (state.readFails && !init?.method) return Response.json({ detail: "no" }, { status: 500 });
      if (init?.method === "PUT") {
        if (state.refuse) {
          if (state.refuse === 401) state.signedIn = false;
          return Response.json({ detail: "There can be at most 10 goals." }, { status: state.refuse });
        }
        const body = JSON.parse(String(init.body)) as AdminGuidelinesEdit;
        const before = state.edit;
        state.edit = {
          identity: body.identity,
          goals: body.goals.map((g) => g.trim()).filter(Boolean),
          guidelines: Object.fromEntries(Object.entries(body.guidelines).filter(([, v]) => v.trim())),
        };
        for (const part of parts()) {
          const [was, now] = [valueOf(before, part), valueOf(state.edit, part)];
          if (JSON.stringify(was) === JSON.stringify(now)) continue;
          const h = (state.history[part] ??= { current: 1, changes: [{ number: 1, made_by: "shipped", value: was }] });
          const number = h.changes.length + 1;
          h.changes.push({ number, made_by: "saved", value: now });
          h.current = number;
        }
      }
      return Response.json(shown());
    }
    if (url.startsWith("/api/admin/guidelines/history")) {
      const compare = /history\/([^/]+)\/(\d+)\/compare$/.exec(url);
      if (compare) {
        const part = decodeURIComponent(compare[1]);
        const h = state.history[part];
        const earlier = h.changes.find((c) => c.number === Number(compare[2]))!;
        const now = h.changes.find((c) => c.number === h.current)!;
        return Response.json({
          part,
          earlier: earlier.number,
          current: h.current,
          runs: [
            { kind: "removed", text: String(earlier.value) },
            { kind: "added", text: String(now.value) },
          ],
        });
      }
      const restore = /history\/([^/]+)\/(\d+)\/restore$/.exec(url);
      if (restore) {
        const part = decodeURIComponent(restore[1]);
        const h = state.history[part];
        const change = h.changes.find((c) => c.number === Number(restore[2]))!;
        h.current = change.number;
        if (part === "identity") state.edit.identity = change.value as typeof BLANK;
        else if (part === "goals") state.edit.goals = change.value as string[];
        else state.edit.guidelines = { ...state.edit.guidelines, [part]: change.value as string };
        return Response.json(shown());
      }
      return Response.json({
        parts: parts()
          .filter((p) => state.history[p])
          .map((p) => ({
            part: p,
            label: labelOf(p),
            current: state.history[p].current,
            changes: [...state.history[p].changes]
              .reverse()
              .map((c) => ({ ...c, made_at: "2026-11-01T01:00:00+00:00" })),
          })),
      });
    }
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  const puts = () =>
    fetchMock.mock.calls
      .filter(([u, init]) => u === "/api/admin/guidelines" && init?.method === "PUT")
      .map(([, init]) => JSON.parse(String(init?.body)) as AdminGuidelinesEdit);
  return { state, puts };
}

async function openPage() {
  window.location.hash = "#/admin/guidelines";
  render(<App />);
  await screen.findByRole("heading", { name: "Goals" });
}

async function type(target: HTMLElement, value: string) {
  await act(async () => {
    fireEvent.input(target, { target: { value } });
  });
}

// A click, and the save it starts, through to what it gives back.
async function click(button: HTMLElement) {
  await act(async () => {
    fireEvent.click(button);
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

const goals = () => screen.getByRole("textbox", { name: "Goals" }) as HTMLTextAreaElement;
const feature = (label: string) => screen.getByRole("form", { name: label });

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("a third tab mirrors the Customization page, saying these come first", async () => {
  server({ goals: ["Be accurate."], guidelines: { topics: "Be brief." } });
  await openPage();
  const tab = screen.getByRole("link", { name: "Admin guidelines" });
  expect(tab.getAttribute("href")).toBe("#/admin/guidelines");
  expect(tab.getAttribute("aria-current")).toBe("page");
  expect(screen.getByText(/These come first, over every host's/)).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Identity" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Guidelines" })).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Assessment" })).toBeTruthy();
  expect(goals().value).toBe("Be accurate.");
  expect((within(feature("Topics")).getByRole("textbox") as HTMLTextAreaElement).value).toBe("Be brief.");
  expect(within(feature("Answering questions")).getByText(/none/)).toBeTruthy();
  expect(within(feature("Answering questions")).getByRole("button", { name: "Clear" })).toHaveProperty("disabled", true);
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Admin guidelines shown \(\d+ ms\)$/));
});

test("each part saves alone, leaving another part's unsaved text as typed", async () => {
  const { puts } = server();
  await openPage();
  await type(within(feature("Topics")).getByRole("textbox"), "Not saved yet.");
  await type(goals(), "Be accurate.\n\nCite the page.");
  await click(screen.getByRole("button", { name: "Save the goals" }));
  expect(puts()).toEqual([{ identity: BLANK, goals: ["Be accurate.", "", "Cite the page."], guidelines: { questions: "", topics: "", "assessment questions": "" } }]);
  expect((await screen.findByRole("status")).textContent).toContain("followed first from the next prompt");
  expect(goals().value).toBe("Be accurate.\nCite the page.");
  expect((within(feature("Topics")).getByRole("textbox") as HTMLTextAreaElement).value).toBe("Not saved yet.");
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Admin guidelines saved: goals \(\d+ ms\)$/));

  // A feature's save keeps the goals saved before it.
  await type(within(feature("Answering questions")).getByRole("textbox"), "Always answer in at least three sentences.");
  await click(within(feature("Answering questions")).getByRole("button", { name: "Save" }));
  expect(puts()[1].goals).toEqual(["Be accurate.", "Cite the page."]);
  expect(puts()[1].guidelines.questions).toBe("Always answer in at least three sentences.");
  expect(puts()[1].guidelines.topics).toBe(""); // typed, not saved

  // The identity, then cleared.
  await type(screen.getByRole("textbox", { name: "Name" }), "Tutor");
  await click(screen.getByRole("button", { name: "Save the identity" }));
  expect(puts()[2].identity.name).toBe("Tutor");
  await click(screen.getByRole("button", { name: "Clear the identity" }));
  expect(puts()[3].identity).toEqual(BLANK);
  expect((screen.getByRole("textbox", { name: "Name" }) as HTMLInputElement).value).toBe("");
  expect(screen.getByRole("button", { name: "Clear the identity" })).toHaveProperty("disabled", true);
});

test("Clear empties a part, so the host's are followed alone", async () => {
  const { puts } = server({ goals: ["Be accurate."], guidelines: { topics: "Be brief." } });
  await openPage();
  await click(within(feature("Topics")).getByRole("button", { name: "Clear" }));
  expect(puts()[0].guidelines.topics).toBe("");
  expect(puts()[0].goals).toEqual(["Be accurate."]);
  expect((await within(feature("Topics")).findByRole("status")).textContent).toContain("host's are followed alone");
  expect(within(feature("Topics")).getByText(/none/)).toBeTruthy();
  await click(screen.getByRole("button", { name: "Clear the goals" }));
  expect(puts()[1].goals).toEqual([]);
  expect(goals().value).toBe("");
});

test("a refused save says why, and a signed-out one shows the sign-in", async () => {
  const { state } = server();
  await openPage();
  state.refuse = 400;
  await type(goals(), "One.");
  await click(screen.getByRole("button", { name: "Save the goals" }));
  expect((await screen.findByRole("alert")).textContent).toBe("There can be at most 10 goals.");
  expect(goals().value).toBe("One."); // kept as typed
  state.refuse = 401;
  await click(screen.getByRole("button", { name: "Save the goals" }));
  expect(await screen.findByRole("heading", { name: "Administrator" })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Admin guidelines" })).toBeNull();
});

test("a page that can't be read says so", async () => {
  const { state } = server();
  state.readFails = true;
  window.location.hash = "#/admin/guidelines";
  render(<App />);
  expect(await screen.findByText(/could not be read/)).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith("Could not read the admin guidelines", expect.anything());
});

test("two saves at once go one after another, so neither undoes the other", async () => {
  const { puts } = server();
  await openPage();
  // Hold the first save's answer until both have been asked for (Codex's review on PR #261).
  const real = globalThis.fetch;
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  let first = true;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/admin/guidelines" && init?.method === "PUT" && first) {
        first = false;
        const answer = real(url, init);
        await held;
        return answer;
      }
      return real(url, init);
    }),
  );
  await type(goals(), "Be accurate.");
  await click(screen.getByRole("button", { name: "Save the goals" }));
  await type(within(feature("Topics")).getByRole("textbox"), "Be brief.");
  await click(within(feature("Topics")).getByRole("button", { name: "Save" }));
  expect(puts()).toHaveLength(1); // the second waits for the first
  await act(async () => {
    release();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(puts()).toHaveLength(2);
  expect(puts()[1].goals).toEqual(["Be accurate."]); // the first's goals kept
  expect(puts()[1].guidelines.topics).toBe("Be brief.");
  expect(goals().value).toBe("Be accurate.");
  expect((within(feature("Topics")).getByRole("textbox") as HTMLTextAreaElement).value).toBe("Be brief.");
});

test("the History goes back on one part only, adds no change, and hides after a save", async () => {
  const { state } = server();
  await openPage();
  await type(within(feature("Topics")).getByRole("textbox"), "Be brief.");
  await click(within(feature("Topics")).getByRole("button", { name: "Save" }));
  await type(within(feature("Topics")).getByRole("textbox"), "Be briefer.");
  await click(within(feature("Topics")).getByRole("button", { name: "Save" }));
  await type(goals(), "Be accurate.");
  await click(screen.getByRole("button", { name: "Save the goals" }));
  await type(within(feature("Answering questions")).getByRole("textbox"), "Typed, not saved.");

  await click(screen.getByRole("button", { name: "History" }));
  const topics = await screen.findByRole("group", { name: "Topics" });
  const items = within(topics).getAllByRole("listitem");
  expect(items.map((li) => li.textContent)).toEqual([
    expect.stringMatching(/^Change 3 \(in use\) · Saved.*Be briefer\./),
    expect.stringMatching(/^Change 2 · Saved.*Be brief\./),
    expect.stringMatching(/^Change 1 · Empty at first.*Empty\./),
  ]);
  // Compare (R254): the change in use beside an earlier one, as on the Customization page.
  await click(within(topics).getByRole("button", { name: "Compare Topics change 2 with the change in use" }));
  const compared = await within(topics).findByRole("region", { name: "Topics compared" });
  expect(compared.textContent).toContain("Change 2 beside change 3 (in use)");
  expect(compared.querySelector("del")?.textContent).toBe("Be brief.");
  expect(compared.querySelector("ins")?.textContent).toBe("Be briefer.");
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Admin guidelines compared: Topics, change 2 with 3/));
  await click(within(compared).getByRole("button", { name: "Hide the comparison" }));
  expect(within(topics).queryByRole("region", { name: "Topics compared" })).toBeNull();
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Admin guidelines history shown: 2 parts/));

  // Text typed in the goals and not saved survives going back on Topics (Codex's review on
  // PR #262).
  await type(goals(), "Be accurate.\nNot saved yet.");
  await click(within(topics).getByRole("button", { name: "Go back to Topics change 2" }));
  expect((within(feature("Topics")).getByRole("textbox") as HTMLTextAreaElement).value).toBe("Be brief.");
  expect(goals().value).toBe("Be accurate.\nNot saved yet."); // only Topics changed
  expect(state.edit.goals).toEqual(["Be accurate."]);
  expect((within(feature("Answering questions")).getByRole("textbox") as HTMLTextAreaElement).value).toBe(
    "Typed, not saved.",
  );
  expect(state.history.topics.changes).toHaveLength(3); // no change added
  expect(within(screen.getByRole("group", { name: "Topics" })).getAllByRole("listitem")[1].textContent).toContain(
    "Change 2 (in use)",
  );
  expect(console.info).toHaveBeenCalledWith("Admin guidelines restored: Topics, change 2");

  // Edit goes to the part's editor, and the History stays open.
  const scrolled = vi.fn();
  Element.prototype.scrollIntoView = scrolled;
  await click(within(screen.getByRole("group", { name: "Goals" })).getByRole("button", { name: "Edit" }));
  expect(scrolled.mock.contexts[0]).toBe(document.getElementById("admin-guidelines-goals"));
  expect(screen.getByRole("group", { name: "Goals" })).toBeTruthy();
  Reflect.deleteProperty(Element.prototype, "scrollIntoView");

  // A save hides it, so it opens again up to date.
  await type(goals(), "Be accurate.\nCite the page.");
  await click(screen.getByRole("button", { name: "Save the goals" }));
  expect(screen.queryByRole("group", { name: "Goals" })).toBeNull();
  expect(screen.getByRole("button", { name: "History" }).getAttribute("aria-expanded")).toBe("false");
});

test("a go-back after a save still waiting goes after it", async () => {
  const { state, puts } = server({ goals: ["One."] });
  state.history.goals = {
    current: 2,
    changes: [
      { number: 1, made_by: "shipped", value: [] },
      { number: 2, made_by: "saved", value: ["One."] },
    ],
  };
  await openPage();
  await click(screen.getByRole("button", { name: "History" }));
  await screen.findByRole("group", { name: "Goals" });
  const real = globalThis.fetch;
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  const asked: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      asked.push(`${init?.method ?? "GET"} ${url}`);
      if (init?.method === "PUT") await held;
      return real(url, init);
    }),
  );
  await type(within(feature("Topics")).getByRole("textbox"), "Be brief.");
  await act(async () => {
    fireEvent.click(within(feature("Topics")).getByRole("button", { name: "Save" }));
  });
  await click(screen.getByRole("button", { name: "Go back to Goals change 1" }));
  expect(asked.filter((a) => !a.startsWith("GET"))).toEqual(["PUT /api/admin/guidelines"]); // waiting
  await act(async () => {
    release();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(asked.filter((a) => !a.startsWith("GET"))).toEqual([
    "PUT /api/admin/guidelines",
    "POST /api/admin/guidelines/history/goals/1/restore",
  ]);
  expect(puts()).toHaveLength(1);
  expect(state.edit.guidelines.topics).toBe("Be brief.");
  expect(state.edit.goals).toEqual([]);
});

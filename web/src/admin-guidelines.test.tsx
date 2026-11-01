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
  };
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
        state.edit = {
          identity: body.identity,
          goals: body.goals.map((g) => g.trim()).filter(Boolean),
          guidelines: Object.fromEntries(Object.entries(body.guidelines).filter(([, v]) => v.trim())),
        };
      }
      return Response.json(shown());
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

import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";
import type { Customization, CustomizationChange, PartHistory } from "./api";
import { preview } from "./customization";

// The real host session calls, not test-setup.ts's signed-in host.
vi.unmock("./api");

const MAYA = {
  identity: {
    name: "Maya",
    speaks_as: "the person seen in the video",
    purpose: "to teach astronomy",
    audience: "",
    helps_with: "the planets",
  },
  goals: ["Make every answer exam-ready."],
  guidelines: {},
  features: [] as object[],
  shipped: false,
};

const QUESTIONS = {
  key: "questions",
  label: "Answering questions",
  changes: "How every answer is written.",
  stays: "Which questions are declined stays as the code decides.",
  shipped: "Answer from the content.",
  text: "Answer from the content.",
  edited: false,
  section: "Guidelines",
};

type Put = { url: string; body: unknown };

// Each part's history, as the server's History gives it (R95), newest change first.
let histories: PartHistory[] = [];
function change(number: number, made_by: CustomizationChange["made_by"], value: CustomizationChange["value"]) {
  return { number, made_at: "2026-10-31T21:30:00+00:00", made_by, value };
}
const TOPICS_HISTORY = {
  part: "questions",
  label: "Answering questions",
  current: 2,
  changes: [change(2, "saved", "Start with the main idea."), change(1, "shipped", null)],
};
const GOALS_HISTORY = {
  part: "goals",
  label: "Goals",
  current: 3,
  changes: [
    change(3, "saved", ["Make every answer exam-ready."]),
    change(2, "generated", ["Love the night sky."]),
    change(1, "shipped", ["Understand it."]),
  ],
};

// A save's answer held back until `resolve` is called.
type Held = { promise: Promise<void>; resolve: () => void };
function hold(): Held {
  let resolve = () => {};
  const promise = new Promise<void>((done) => (resolve = done));
  return { promise, resolve };
}

// A server with consent given and, when `host`, a signed-in host; `customization` null fails.
function server(
  host: boolean,
  customization: typeof MAYA | null = MAYA,
  refuse: string | null = null,
  // When given, each save is answered only once it resolves.
  held: Held | null = null,
) {
  const asked: string[] = [];
  const puts: Put[] = [];
  // What the server gives back after a save: the customization with the change.
  function saved(url: string, body: Record<string, unknown>) {
    const now = customization ?? MAYA;
    if (url.endsWith("/identity")) return { ...now, identity: body };
    if (url.endsWith("/draft")) {
      const drafted = body as { identity: Customization["identity"]; goals: string[] };
      const features = now.features.map((f) => ({ ...(f as object), text: "Drafted.", edited: true }));
      return { ...now, identity: drafted.identity, goals: drafted.goals, features };
    }
    if (url.endsWith("/goals")) {
      const goals = (body.goals as string[]).map((g) => g.trim()).filter(Boolean);
      return { ...now, goals };
    }
    const text = body.text as string | null;
    const feature = { ...QUESTIONS, text: text ?? QUESTIONS.shipped, edited: text !== null };
    return { ...now, features: [feature] };
  }
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/consent") return Response.json({ agreed: true });
      if (url === "/api/settings") {
        return Response.json({ view: host ? "host" : "participant", general_prompts: false });
      }
      if (url === "/api/host/session") {
        return Response.json({ signed_in: host, email: host ? "host@example.com" : null });
      }
      if (url === "/api/settings/access") return Response.json({ shown: true, as: null });
      if (url.startsWith("/api/customization/") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        puts.push({ url, body });
        await held?.promise;
        if (refuse) return Response.json({ detail: refuse }, { status: 400 });
        return Response.json(saved(url, body));
      }
      if (url === "/api/customization/draft" && init?.method === "POST") {
        asked.push(url);
        if (refuse) return Response.json({ detail: refuse }, { status: 502 });
        const now = customization ?? MAYA;
        const identity = { ...now.identity, name: "Ada", purpose: "to teach the stars" };
        const features = (now.features as { key: string }[]).map((f) => ({
          ...f,
          text: "Drafted.",
          edited: true,
        }));
        const draft = { ...now, identity, goals: ["Love the night sky."], features };
        return Response.json({ draft, drafted: features.map((f) => f.key), based_on: "abc123" });
      }
      if (url.startsWith("/api/customization/history")) {
        asked.push(url);
        const compare = /^\/api\/customization\/history\/([^/]+)\/(\d+)\/compare$/.exec(url);
        if (compare) {
          if (refuse) return Response.json({ detail: refuse }, { status: 404 });
          const part = decodeURIComponent(compare[1]);
          const current = histories.find((h) => h.part === part)?.current ?? 0;
          const runs = [
            { kind: "same", text: "Make every answer " },
            { kind: "removed", text: "clear" },
            { kind: "added", text: "exam-ready" },
            { kind: "same", text: "." },
          ];
          return Response.json({ part, earlier: Number(compare[2]), current, runs });
        }
        const restore = /^\/api\/customization\/history\/([^/]+)\/(\d+)\/restore$/.exec(url);
        if (restore && init?.method === "POST") {
          if (refuse) return Response.json({ detail: refuse }, { status: 404 });
          const part = decodeURIComponent(restore[1]);
          const back = Number(restore[2]);
          histories = histories.map((h) => (h.part === part ? { ...h, current: back } : h));
          const goals = part === "goals" ? ["Love the night sky."] : MAYA.goals;
          return Response.json({ ...MAYA, goals });
        }
        return Response.json({ parts: histories });
      }
      if (url === "/api/customization/draft/discard") {
        asked.push(url);
        return Response.json({ discarded: true });
      }
      if (url.startsWith("/api/customization")) {
        asked.push(url);
        return customization ? Response.json(customization) : new Response("", { status: 500 });
      }
      return new Response("", { status: 404 });
    }),
  );
  return { asked, puts };
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
});

afterEach(() => {
  histories = [];
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = "";
});

test("a signed-in host finds Customization at the bottom of Settings' Chat section", async () => {
  server(true);
  window.location.hash = "#/settings";
  render(<App />);
  const chat = (await screen.findByRole("heading", { name: "Chat" })).closest("section");
  const link = await within(chat as HTMLElement).findByRole("link", { name: "Customization" });
  expect(link).toHaveProperty("hash", "#/customization");
  const parts = Array.from((chat as HTMLElement).querySelectorAll(".switch"));
  expect(parts[parts.length - 1].contains(link)).toBe(true);
});

test("anyone not signed in as a host has no Customization link in Settings", async () => {
  server(false);
  window.location.hash = "#/settings";
  render(<App />);
  await screen.findByRole("heading", { name: "Chat" });
  expect(screen.queryByRole("link", { name: "Customization" })).toBeNull();
});

async function opened() {
  window.location.hash = "#/customization";
  render(<App />);
  return await screen.findByRole("region", { name: "Identity" });
}

test("a host edits and saves the identity", async () => {
  const { asked, puts } = server(true);
  const identity = within(await opened());
  expect(asked).toEqual(["/api/customization?opened=true"]);
  expect(console.info).toHaveBeenCalledWith("Customization page opened: shipped=false");
  // Only that the administrator's come first, never what they are (R244).
  expect(screen.getByText("The administrator's requirements, if any, come before yours.")).toBeTruthy();
  const name = identity.getByRole("textbox", { name: /^Name/ }) as HTMLInputElement;
  expect(name.value).toBe("Maya");
  fireEvent.input(name, { target: { value: "Ada" } });
  fireEvent.click(identity.getByRole("button", { name: "Save the identity" }));
  expect(await identity.findByText("Saved. It is used from the next prompt.")).toBeTruthy();
  expect(puts).toEqual([
    { url: "/api/customization/identity", body: { ...MAYA.identity, name: "Ada" } },
  ]);
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Customization saved: identity/));
});

test("a host saves the goals, one on each line", async () => {
  const { puts } = server(true);
  await opened();
  const goals = within(screen.getByRole("region", { name: "Goals" }));
  const box = goals.getByRole("textbox") as HTMLTextAreaElement;
  expect(box.value).toBe("Make every answer exam-ready.");
  fireEvent.input(box, { target: { value: "Be kind.\n\nBe brief." } });
  fireEvent.click(goals.getByRole("button", { name: "Save the goals" }));
  expect(await goals.findByText("Saved. It is used from the next prompt.")).toBeTruthy();
  expect(puts[0]).toEqual({
    url: "/api/customization/goals",
    body: { goals: ["Be kind.", "", "Be brief."] },
  });
  expect(box.value).toBe("Be kind.\nBe brief.");
});

test("a refused save says why, and typing again clears it", async () => {
  server(true, MAYA, "The purpose is too long: at most 500 characters.");
  const identity = within(await opened());
  fireEvent.click(identity.getByRole("button", { name: "Save the identity" }));
  expect(
    await identity.findByText("The purpose is too long: at most 500 characters."),
  ).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith(
    "Could not save the customization: identity",
    expect.anything(),
  );
  fireEvent.input(identity.getByRole("textbox", { name: /^Purpose/ }), {
    target: { value: "short" },
  });
  expect(identity.queryByText(/too long/)).toBeNull();
});

test("a save that fails without a reason says to try again", async () => {
  server(true);
  await opened();
  const goals = within(screen.getByRole("region", { name: "Goals" }));
  vi.mocked(fetch).mockImplementationOnce(async () => {
    throw new TypeError("offline");
  });
  fireEvent.click(goals.getByRole("button", { name: "Save the goals" }));
  expect(await goals.findByText("Could not save. Try again.")).toBeTruthy();
});

test("with no feature's guidelines yet, the Guidelines section says so", async () => {
  server(true);
  await opened();
  const guidelines = within(screen.getByRole("region", { name: "Guidelines" }));
  expect(guidelines.getByText("No feature has guidelines to edit yet.")).toBeTruthy();
});

test("Assessment and Level of detail have their own sections", async () => {
  const assessment = { ...QUESTIONS, key: "assessment judging", label: "Assessment: judging", section: "Assessment" };
  const lowest = { ...QUESTIONS, key: "detail lowest", label: "Lowest detail", section: "Level of detail" };
  const general = { ...QUESTIONS, key: "detail general", label: "General guidelines", section: "Level of detail" };
  server(true, { ...MAYA, features: [QUESTIONS, assessment, lowest, general] });
  await opened();
  const headings = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
  expect(headings).toEqual([
    "Generate again",
    "History",
    "Identity",
    "Goals",
    "Guidelines",
    "Assessment",
    "Level of detail",
  ]);
  const detail = within(screen.getByRole("region", { name: "Level of detail" }));
  const forms = detail.getAllByRole("form").map((f) => f.getAttribute("aria-label"));
  expect(forms).toEqual(["Lowest detail", "General guidelines"]);
  const guidelines = within(screen.getByRole("region", { name: "Guidelines" }));
  expect(guidelines.getAllByRole("form")).toHaveLength(1);
  expect(within(screen.getByRole("region", { name: "Assessment" })).getByRole("form")).toBeTruthy();
});

test("a feature's guidelines are edited, saved and set back to how they shipped", async () => {
  const { puts } = server(true, { ...MAYA, features: [QUESTIONS] });
  await opened();
  const form = within(screen.getByRole("form", { name: "Answering questions" }));
  expect(form.getByText(/as shipped/)).toBeTruthy();
  expect(
    form.getByText(
      "How every answer is written. Which questions are declined stays as the code decides.",
    ),
  ).toBeTruthy();
  const setBack = form.getByRole("button", { name: "Set back to how it shipped" });
  expect(setBack).toHaveProperty("disabled", true);
  const box = form.getByRole("textbox") as HTMLTextAreaElement;
  fireEvent.input(box, { target: { value: "End with a question." } });
  fireEvent.click(form.getByRole("button", { name: "Save" }));
  expect(await form.findByText("Saved. It is used from the next prompt.")).toBeTruthy();
  expect(form.queryByText(/as shipped/)).toBeNull();
  expect(setBack).toHaveProperty("disabled", false);
  fireEvent.click(setBack);
  await vi.waitFor(() => expect(box.value).toBe("Answer from the content."));
  expect(puts).toEqual([
    { url: "/api/customization/guidelines/questions", body: { text: "End with a question." } },
    { url: "/api/customization/guidelines/questions", body: { text: null } },
  ]);
});

test("the Customization page is for the host only", async () => {
  const { asked } = server(false);
  window.location.hash = "#/customization";
  render(<App />);
  expect(await screen.findByRole("heading", { name: "For the host only" })).toBeTruthy();
  expect(asked).toEqual([]);
});

test("a customization that can't be read says so", async () => {
  server(true, null);
  window.location.hash = "#/customization";
  render(<App />);
  expect(
    await screen.findByText("The customization could not be read. Reload to try again."),
  ).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith(
    "Could not read the customization",
    expect.anything(),
  );
});

test.each([
  ["Identity", /^Name/, "Save the identity"],
  ["Goals", "Goals", "Save the goals"],
  ["Answering questions", null, "Save"],
] as const)(
  "the %s editor is read-only while its save is in flight, so nothing typed is lost",
  async (part, box, button) => {
    const held = hold();
    server(true, { ...MAYA, features: [QUESTIONS] }, null, held);
    await opened();
    const area = within(
      part === "Answering questions"
        ? screen.getByRole("form", { name: part })
        : screen.getByRole("region", { name: part }),
    );
    const editor = (box ? area.getByRole("textbox", { name: box }) : area.getByRole("textbox")) as
      | HTMLInputElement
      | HTMLTextAreaElement;
    fireEvent.click(area.getByRole("button", { name: button }));
    await vi.waitFor(() => expect(editor.readOnly).toBe(true));
    held.resolve();
    expect(await area.findByText("Saved. It is used from the next prompt.")).toBeTruthy();
    expect(editor.readOnly).toBe(false);
  },
);

test("Generate again shows a draft beside the current text, and Discard keeps it as it was", async () => {
  const { asked, puts } = server(true, { ...MAYA, features: [QUESTIONS] });
  await opened();
  const generate = within(screen.getByRole("region", { name: "Generate again" }));
  fireEvent.click(generate.getByRole("button", { name: "Generate again" }));
  const table = within(await generate.findByRole("table"));
  const name = table.getByRole("rowheader", { name: "Name" }).closest("tr") as HTMLElement;
  expect(within(name).getByText("Maya")).toBeTruthy();
  expect(within(name).getByText("Ada")).toBeTruthy();
  const questions = table.getByRole("rowheader", { name: "Answering questions" }).closest("tr");
  expect(within(questions as HTMLElement).getByText("Drafted.")).toBeTruthy();
  fireEvent.click(generate.getByRole("button", { name: "Discard" }));
  expect(generate.queryByRole("table")).toBeNull();
  await vi.waitFor(() => expect(asked).toContain("/api/customization/draft/discard"));
  expect(puts).toEqual([]);
  const identity = within(screen.getByRole("region", { name: "Identity" }));
  expect((identity.getByRole("textbox", { name: /^Name/ }) as HTMLInputElement).value).toBe("Maya");
});

test("a saved draft fills the editors", async () => {
  const { puts } = server(true, { ...MAYA, features: [QUESTIONS] });
  await opened();
  const generate = within(screen.getByRole("region", { name: "Generate again" }));
  fireEvent.click(generate.getByRole("button", { name: "Generate again" }));
  fireEvent.click(await generate.findByRole("button", { name: "Save the draft" }));
  // The editors start again from what was saved.
  await vi.waitFor(() => {
    const identity = within(screen.getByRole("region", { name: "Identity" }));
    expect((identity.getByRole("textbox", { name: /^Name/ }) as HTMLInputElement).value).toBe("Ada");
  });
  const form = within(screen.getByRole("form", { name: "Answering questions" }));
  expect((form.getByRole("textbox") as HTMLTextAreaElement).value).toBe("Drafted.");
  expect(generate.queryByRole("table")).toBeNull();
  expect(puts).toEqual([
    {
      url: "/api/customization/draft",
      body: {
        identity: { ...MAYA.identity, name: "Ada", purpose: "to teach the stars" },
        goals: ["Love the night sky."],
        guidelines: { questions: "Drafted." },
        based_on: "abc123",
      },
    },
  ]);
});

test("a draft that can't be made says so", async () => {
  server(true, MAYA, "A draft could not be made: no reply within 120 s. Try again.");
  await opened();
  const generate = within(screen.getByRole("region", { name: "Generate again" }));
  fireEvent.click(generate.getByRole("button", { name: "Generate again" }));
  expect(
    await generate.findByText("A draft could not be made: no reply within 120 s. Try again."),
  ).toBeTruthy();
  expect(generate.getByRole("button", { name: "Generate again" })).toHaveProperty("disabled", false);
});

test("guidelines the LLM drafted say so", async () => {
  const drafted = { ...QUESTIONS, text: "Drafted.", edited: true, generated: true };
  server(true, { ...MAYA, features: [drafted] });
  await opened();
  const form = within(screen.getByRole("form", { name: "Answering questions" }));
  expect(form.getByText(/drafted by the LLM/)).toBeTruthy();
  expect(form.queryByText(/as shipped/)).toBeNull();
});

test("a draft older than a save says so, and stays to be discarded", async () => {
  const { puts } = server(true, { ...MAYA, features: [QUESTIONS] });
  await opened();
  const generate = within(screen.getByRole("region", { name: "Generate again" }));
  fireEvent.click(generate.getByRole("button", { name: "Generate again" }));
  await generate.findByRole("table");
  const refused = "Something was saved since this draft was made. Generate again to redraft.";
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      puts.push({ url, body: JSON.parse(String(init?.body ?? "null")) });
      return Response.json({ detail: refused }, { status: 409 });
    }),
  );
  fireEvent.click(generate.getByRole("button", { name: "Save the draft" }));
  expect(await generate.findByText(refused)).toBeTruthy();
  expect(generate.getByRole("table")).toBeTruthy();
  expect(generate.getByRole("button", { name: "Discard" })).toBeTruthy();
});

test("History lists each part's changes, newest first, with the one in use", async () => {
  histories = [GOALS_HISTORY, TOPICS_HISTORY];
  const { asked } = server(true, { ...MAYA, features: [QUESTIONS] });
  await opened();
  const history = within(screen.getByRole("region", { name: "History" }));
  expect(history.queryByRole("group")).toBeNull(); // shown only when asked for
  fireEvent.click(history.getByRole("button", { name: "History" }));
  const goals = within(await history.findByRole("group", { name: "Goals" }));
  const items = goals.getAllByRole("listitem").map((li) => li.textContent);
  expect(items[0]).toMatch(/^Change 3 \(in use\) · Saved · .*Make every answer exam-ready\.Edit$/);
  expect(items[1]).toMatch(/^Change 2 · Drafted by the LLM · .*Love the night sky\.CompareGo back$/);
  expect(items[2]).toMatch(/^Change 1 · As shipped · /);
  const questions = within(history.getByRole("group", { name: "Answering questions" }));
  expect(questions.getByText("As shipped.")).toBeTruthy();
  expect(asked).toContain("/api/customization/history?opened=true");
  expect(history.getAllByRole("button", { name: /^Go back to/ })).toHaveLength(3);
  expect(history.getAllByRole("button", { name: "Edit" })).toHaveLength(2);
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Customization history shown: 2 parts/));
  fireEvent.click(history.getByRole("button", { name: "Hide the history" }));
  expect(history.queryByRole("group")).toBeNull();
});

test("Go back changes only that part, adds no change, and fills its editor", async () => {
  histories = [GOALS_HISTORY, TOPICS_HISTORY];
  const { asked } = server(true);
  await opened();
  const history = within(screen.getByRole("region", { name: "History" }));
  fireEvent.click(history.getByRole("button", { name: "History" }));
  fireEvent.click(await history.findByRole("button", { name: "Go back to Goals change 2" }));
  await vi.waitFor(() => {
    const goals = within(screen.getByRole("region", { name: "Goals" }));
    expect((goals.getByRole("textbox") as HTMLTextAreaElement).value).toBe("Love the night sky.");
  });
  expect(asked).toContain("/api/customization/history/goals/2/restore");
  const goals = within(history.getByRole("group", { name: "Goals" }));
  await vi.waitFor(() => expect(goals.getAllByRole("listitem")[1].textContent).toMatch(/^Change 2 \(in use\)/));
  expect(goals.getAllByRole("listitem")).toHaveLength(3);
  expect(history.getByText("Saved. It is used from the next prompt.")).toBeTruthy();
  expect(console.info).toHaveBeenCalledWith("Customization restored: Goals, change 2");
});

test("Edit on the change in use goes to that part's editor", async () => {
  histories = [GOALS_HISTORY, TOPICS_HISTORY];
  server(true, { ...MAYA, features: [QUESTIONS] });
  await opened();
  const scrolled = vi.fn();
  const form = screen.getByRole("form", { name: "Answering questions" });
  form.scrollIntoView = scrolled;
  document.getElementById("customization-goals")!.scrollIntoView = scrolled;
  const history = within(screen.getByRole("region", { name: "History" }));
  fireEvent.click(history.getByRole("button", { name: "History" }));
  const questions = within(await history.findByRole("group", { name: "Answering questions" }));
  fireEvent.click(questions.getByRole("button", { name: "Edit" }));
  expect(scrolled).toHaveBeenCalledTimes(1);
  // Edit leaves the History open; only a save hides it.
  const goals = within(history.getByRole("group", { name: "Goals" }));
  fireEvent.click(goals.getByRole("button", { name: "Edit" }));
  expect(scrolled).toHaveBeenCalledTimes(2);
});

test("with nothing changed yet, History says so", async () => {
  server(true);
  await opened();
  const history = within(screen.getByRole("region", { name: "History" }));
  fireEvent.click(history.getByRole("button", { name: "History" }));
  expect(await history.findByText(/Nothing has been changed yet/)).toBeTruthy();
});

test("a history that can't be read, or a change that can't be gone back to, says so", async () => {
  histories = [GOALS_HISTORY];
  server(true, MAYA, "There is no such change.");
  await opened();
  const history = within(screen.getByRole("region", { name: "History" }));
  fireEvent.click(history.getByRole("button", { name: "History" }));
  fireEvent.click(await history.findByRole("button", { name: "Go back to Goals change 1" }));
  expect(await history.findByText("There is no such change.")).toBeTruthy();
  vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
  fireEvent.click(history.getByRole("button", { name: "Hide the history" }));
  fireEvent.click(history.getByRole("button", { name: "History" }));
  expect(await history.findByText("The history could not be read. Try again.")).toBeTruthy();
});

test.each([
  [null, "As shipped."],
  ["Use short words.", "Use short words."],
  [["One.", "Two."], "One. Two."],
  [[], "No goals."],
  [{ name: "Maya", speaks_as: "x", purpose: "to teach", audience: "", helps_with: "stars" }, "Maya · to teach · stars"],
])("a change's value is shown in a line", (value, said) => {
  expect(preview(change(1, "saved", value))).toBe(said);
});

test("a save anywhere else on the page hides the History, so it opens again up to date", async () => {
  histories = [GOALS_HISTORY];
  const { asked } = server(true);
  await opened();
  const history = within(screen.getByRole("region", { name: "History" }));
  fireEvent.click(history.getByRole("button", { name: "History" }));
  // Going back keeps it open, up to date.
  fireEvent.click(await history.findByRole("button", { name: "Go back to Goals change 2" }));
  await vi.waitFor(() => expect(asked).toContain("/api/customization/history/goals/2/restore"));
  expect(await history.findByRole("group", { name: "Goals" })).toBeTruthy();
  await history.findByText("Saved. It is used from the next prompt.");
  const identity = within(screen.getByRole("region", { name: "Identity" }));
  fireEvent.click(identity.getByRole("button", { name: "Save the identity" }));
  await vi.waitFor(() => expect(history.queryByRole("group")).toBeNull());
  expect(history.getByRole("button", { name: "History" })).toHaveProperty("ariaExpanded", "false");
  expect(console.info).toHaveBeenCalledWith("Customization history hidden after a save");
  fireEvent.click(history.getByRole("button", { name: "History" }));
  expect(await history.findByRole("group", { name: "Goals" })).toBeTruthy();
});

test("Compare shows the change in use beside an earlier one, with the changes marked", async () => {
  histories = [GOALS_HISTORY, TOPICS_HISTORY];
  const { asked } = server(true);
  await opened();
  const history = within(screen.getByRole("region", { name: "History" }));
  fireEvent.click(history.getByRole("button", { name: "History" }));
  // Only the changes not in use can be compared with it.
  expect(await history.findAllByRole("button", { name: /^Compare / })).toHaveLength(3);
  fireEvent.click(history.getByRole("button", { name: "Compare Goals change 2 with the change in use" }));
  const shown = within(await history.findByRole("region", { name: "Goals compared" }));
  expect(asked).toContain("/api/customization/history/goals/2/compare");
  expect(shown.getByText("Change 2 beside change 3 (in use)")).toBeTruthy();
  expect(shown.getByText("exam-ready").tagName).toBe("INS");
  expect(shown.getByText("clear").tagName).toBe("DEL");
  expect(shown.getByText("Make every answer").tagName).toBe("SPAN");
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Customization compared: Goals, change 2 with 3/));
  // Shown under its own part only.
  const questions = within(history.getByRole("group", { name: "Answering questions" }));
  expect(questions.queryByRole("region")).toBeNull();
  fireEvent.click(shown.getByRole("button", { name: "Hide the comparison" }));
  expect(history.queryByRole("region", { name: "Goals compared" })).toBeNull();
});

test("a comparison that can't be made says so under its part", async () => {
  histories = [GOALS_HISTORY];
  server(true, MAYA, "There is no such change.");
  await opened();
  const history = within(screen.getByRole("region", { name: "History" }));
  fireEvent.click(history.getByRole("button", { name: "History" }));
  fireEvent.click(await history.findByRole("button", { name: "Compare Goals change 1 with the change in use" }));
  const goals = within(history.getByRole("group", { name: "Goals" }));
  expect(await goals.findByText("There is no such change.")).toBeTruthy();
  vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
  fireEvent.click(goals.getByRole("button", { name: "Compare Goals change 2 with the change in use" }));
  expect(await goals.findByText("They could not be compared. Try again.")).toBeTruthy();
});

test("an answer to an earlier Compare, or one asked before Go back, is ignored when it comes late", async () => {
  // Codex's review on PR #259.
  histories = [GOALS_HISTORY];
  server(true);
  const real = globalThis.fetch;
  const held = new Map<string, Held>();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/compare")) {
        const h = hold();
        held.set(url, h);
        await h.promise;
      }
      return real(url, init);
    }),
  );
  await opened();
  const history = within(screen.getByRole("region", { name: "History" }));
  fireEvent.click(history.getByRole("button", { name: "History" }));
  fireEvent.click(await history.findByRole("button", { name: "Compare Goals change 1 with the change in use" }));
  fireEvent.click(history.getByRole("button", { name: "Compare Goals change 2 with the change in use" }));
  await vi.waitFor(() => expect(held.size).toBe(2));
  held.get("/api/customization/history/goals/2/compare")!.resolve();
  expect(await history.findByText("Change 2 beside change 3 (in use)")).toBeTruthy();
  held.get("/api/customization/history/goals/1/compare")!.resolve();
  await vi.waitFor(() =>
    expect(console.info).toHaveBeenCalledWith(
      "Customization comparison dropped: Goals, change 1, as another was asked for",
    ),
  );
  expect(history.getByText("Change 2 beside change 3 (in use)")).toBeTruthy();
  expect(history.queryByText("Change 1 beside change 3 (in use)")).toBeNull();
  // Asked, then Go back before it answers: it never shows.
  held.clear();
  fireEvent.click(history.getByRole("button", { name: "Compare Goals change 1 with the change in use" }));
  await vi.waitFor(() => expect(held.size).toBe(1));
  fireEvent.click(history.getByRole("button", { name: "Go back to Goals change 2" }));
  await history.findByText("Saved. It is used from the next prompt.");
  held.get("/api/customization/history/goals/1/compare")!.resolve();
  await vi.waitFor(() =>
    expect(console.info).toHaveBeenCalledWith(
      "Customization comparison dropped: Goals, change 1, as another was asked for",
    ),
  );
  await new Promise((r) => setTimeout(r, 20));
  expect(history.queryByRole("region", { name: "Goals compared" })).toBeNull();
});

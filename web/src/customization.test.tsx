import { cleanup, fireEvent, render, screen, within } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { App } from "./App";

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
};

type Put = { url: string; body: unknown };

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

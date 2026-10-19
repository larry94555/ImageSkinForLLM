import { cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { LlmProvider, LlmSetting } from "./api";
import { LlmSettingSection, modelsNote } from "./llm-setting";

function provider(id: string, label: string, extra: Partial<LlmProvider> = {}): LlmProvider {
  const fields = { keys_at: `${id}.example`, model: "", default_model: `${id}-model` };
  return { id, label, ...fields, has_key: false, lists_freely: false, ...extra };
}

const LOCAL: LlmSetting = {
  provider: "local",
  providers: [
    provider("local", "Local (llama.cpp)", { keys_at: "", default_model: "" }),
    provider("claude", "Claude", { has_key: true, model: "claude-sonnet-5-5" }),
    provider("grok", "Grok"),
  ],
};

// A fake server: GET /api/llm answers `read`; PUT answers `put` and is recorded. The models
// are listed as `models` answers.
function server(
  read: LlmSetting | Response,
  put: LlmSetting | Response = read,
  models: () => Response = () => Response.json({ models: ["claude-opus-5-5", "claude-sonnet-5-5"] }),
) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === "/api/llm/models") return models();
    if (url !== "/api/llm") return new Response("", { status: 404 });
    const answer = init?.method === "PUT" ? put : read;
    return answer instanceof Response ? answer : Response.json(answer);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function sent(fetchMock: ReturnType<typeof server>): unknown {
  const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
  return JSON.parse(call[1]!.body as string);
}

function radio(name: RegExp): HTMLInputElement {
  return screen.getByRole("radio", { name }) as HTMLInputElement;
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

test("the LLM answering now is picked, with which providers have a key", async () => {
  server(LOCAL);
  render(<LlmSettingSection />);
  await screen.findByText("Answering now:");
  expect(screen.getByText("Answering now:").textContent).toContain("Local (llama.cpp)");
  expect(radio(/Local/).checked).toBe(true);
  expect(screen.getByText("· key saved")).toBeTruthy();
  expect(screen.getByText("· needs a key")).toBeTruthy();
  expect(screen.queryByLabelText("API key")).toBeNull(); // the local model needs none
});

test("a provider is picked with its key, which is sent once and cleared", async () => {
  const grok = { ...LOCAL, provider: "grok" };
  grok.providers = LOCAL.providers.map((p) => (p.id === "grok" ? { ...p, has_key: true } : p));
  const fetchMock = server(LOCAL, grok);
  render(<LlmSettingSection />);
  fireEvent.click(await screen.findByRole("radio", { name: /Grok/ }));
  const key = screen.getByLabelText("API key") as HTMLInputElement;
  expect(key.type).toBe("password");
  expect(key.placeholder).toBe("From grok.example");
  // No model is offered until a key works.
  expect(screen.queryByLabelText("Model")).toBeNull();
  expect(screen.getByText("Enter your key to choose one of Grok's models.")).toBeTruthy();
  fireEvent.input(key, { target: { value: " xai-1 " } });
  fireEvent.click(screen.getByRole("button", { name: "Use this LLM" }));
  expect(await screen.findByText("Saved. Grok answers from the next prompt.")).toBeTruthy();
  expect(sent(fetchMock)).toEqual({ provider: "grok", api_key: "xai-1", model: "" });
  // The key just saved was checked, so its models are offered now.
  expect(((await screen.findByLabelText("Model")) as HTMLInputElement).placeholder).toBe("grok-model");
  expect(screen.getByText(/^The key works\./)).toBeTruthy();
  expect(screen.getByText("Answering now:").textContent).toContain("Grok");
  expect((screen.getByLabelText("API key") as HTMLInputElement).value).toBe("");
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^LLM changed to grok \(\d+ ms\)$/));
});

test("a provider with a saved key keeps it, and shows its saved model", async () => {
  const fetchMock = server(LOCAL, { ...LOCAL, provider: "claude" });
  render(<LlmSettingSection />);
  fireEvent.click(await screen.findByRole("radio", { name: /Claude/ }));
  expect((screen.getByLabelText("API key") as HTMLInputElement).placeholder).toContain("Saved");
  expect(((await screen.findByLabelText("Model")) as HTMLInputElement).value).toBe("claude-sonnet-5-5");
  fireEvent.click(screen.getByRole("button", { name: "Use this LLM" }));
  await screen.findByText(/Claude answers from the next prompt/);
  expect(sent(fetchMock)).toEqual({ provider: "claude", model: "claude-sonnet-5-5" });
});

test("going back to the local model sends no key or model", async () => {
  const fetchMock = server({ ...LOCAL, provider: "claude" }, LOCAL);
  render(<LlmSettingSection />);
  fireEvent.click(await screen.findByRole("radio", { name: /Local/ }));
  fireEvent.click(screen.getByRole("button", { name: "Use this LLM" }));
  await screen.findByText(/Local \(llama.cpp\) answers from the next prompt/);
  expect(sent(fetchMock)).toEqual({ provider: "local" });
});

test("a refused change says why", async () => {
  server(LOCAL, Response.json({ detail: "Enter your Grok API key." }, { status: 400 }));
  render(<LlmSettingSection />);
  fireEvent.click(await screen.findByRole("radio", { name: /Grok/ }));
  fireEvent.click(screen.getByRole("button", { name: "Use this LLM" }));
  expect((await screen.findByRole("alert")).textContent).toBe("Enter your Grok API key.");
  expect(screen.getByText("Answering now:").textContent).toContain("Local");
  fireEvent.input(screen.getByLabelText("API key"), { target: { value: "xai-2" } });
  expect(screen.queryByRole("alert")).toBeNull(); // gone once another key is typed
});

test("a change that can't reach the app says so", async () => {
  server(LOCAL);
  render(<LlmSettingSection />);
  await screen.findByRole("radio", { name: /Grok/ });
  vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("offline"))));
  fireEvent.click(screen.getByRole("button", { name: "Use this LLM" }));
  expect((await screen.findByRole("alert")).textContent).toBe("The LLM could not be changed. Try again.");
});

test("a setting that can't be read says so", async () => {
  server(new Response("", { status: 500 }));
  render(<LlmSettingSection />);
  expect((await screen.findByRole("alert")).textContent).toContain("could not be read");
  expect(screen.queryByRole("button", { name: "Use this LLM" })).toBeNull();
});

test("a provider with a saved key offers the models it lists", async () => {
  const fetchMock = server(LOCAL);
  render(<LlmSettingSection />);
  fireEvent.click(await screen.findByRole("radio", { name: /Claude/ }));
  expect(await screen.findByText(/^The key works\. 2 models available: pick one or type a name\./)).toBeTruthy();
  const options = [...document.querySelectorAll("#llm-models option")].map((o) => o.getAttribute("value"));
  expect(options).toEqual(["claude-opus-5-5", "claude-sonnet-5-5"]);
  expect(screen.getByLabelText("Model").getAttribute("list")).toBe("llm-models");
  const asked = fetchMock.mock.calls.find(([url]) => url === "/api/llm/models")!;
  expect(JSON.parse(asked[1]!.body as string)).toEqual({ provider: "claude" });
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Listed 2 models for claude \(\d+ ms\)$/));
});

test("a key just entered is used to list the models, and a missing default is pointed out", async () => {
  const fetchMock = server(LOCAL, LOCAL, () => Response.json({ models: ["grok-5"] }));
  render(<LlmSettingSection />);
  fireEvent.click(await screen.findByRole("radio", { name: /Grok/ }));
  expect(screen.getByText("Enter your key to choose one of Grok's models.")).toBeTruthy();
  const key = screen.getByLabelText("API key");
  fireEvent.input(key, { target: { value: " xai-1 " } });
  fireEvent.blur(key);
  expect(await screen.findByText(/grok-model isn't in Grok's list for this key/)).toBeTruthy();
  const asked = fetchMock.mock.calls.find(([url]) => url === "/api/llm/models")!;
  expect(JSON.parse(asked[1]!.body as string)).toEqual({ provider: "grok", api_key: "xai-1" });
});

test("models that can't be listed still let a name be typed", async () => {
  server(LOCAL, LOCAL, () => Response.json({ detail: "Claude's models couldn't be listed." }, { status: 502 }));
  render(<LlmSettingSection />);
  fireEvent.click(await screen.findByRole("radio", { name: /Claude/ }));
  expect(
    await screen.findByText("Claude's models couldn't be listed. You can still type a model's name."),
  ).toBeTruthy();
  expect(screen.getByLabelText("Model")).toBeTruthy();
  expect(document.querySelector("#llm-models")).toBeNull();
});

test("a refused key offers no model", async () => {
  server(LOCAL, LOCAL, () => Response.json({ detail: "Grok refused the API key." }, { status: 400 }));
  render(<LlmSettingSection />);
  fireEvent.click(await screen.findByRole("radio", { name: /Grok/ }));
  const key = screen.getByLabelText("API key");
  fireEvent.input(key, { target: { value: "xai-bad" } });
  fireEvent.blur(key);
  expect(await screen.findByText("Grok refused the API key.")).toBeTruthy();
  expect(screen.queryByLabelText("Model")).toBeNull();
});

test("a provider that lists its models for anyone shows them before a key", async () => {
  const open = {
    ...LOCAL,
    providers: [...LOCAL.providers, provider("openrouter", "OpenRouter", { lists_freely: true })],
  };
  const fetchMock = server(open, open, () => Response.json({ models: ["a/one", "b/two"] }));
  render(<LlmSettingSection />);
  fireEvent.click(await screen.findByRole("radio", { name: /OpenRouter/ }));
  expect(screen.getByLabelText("Model")).toBeTruthy();
  expect(await screen.findByText(/^2 models available: pick one or type a name\./)).toBeTruthy();
  const asked = fetchMock.mock.calls.find(([url]) => url === "/api/llm/models")!;
  expect(JSON.parse(asked[1]!.body as string)).toEqual({ provider: "openrouter" });
  const key = screen.getByLabelText("API key");
  fireEvent.input(key, { target: { value: "sk-or-1" } });
  fireEvent.blur(key);
  expect(await screen.findByText(/^The key works\. 2 models available/)).toBeTruthy();
});

test("a late list for a provider no longer picked is dropped", async () => {
  let answer: (r: Response) => void = () => {};
  server(LOCAL, LOCAL, () => new Promise<Response>((r) => (answer = r)) as unknown as Response);
  render(<LlmSettingSection />);
  fireEvent.click(await screen.findByRole("radio", { name: /Claude/ }));
  expect(screen.getByText("Looking up Claude's models…")).toBeTruthy();
  fireEvent.click(screen.getByRole("radio", { name: /Grok/ }));
  answer(Response.json({ models: ["claude-x"] }));
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.getByText("Enter your key to choose one of Grok's models.")).toBeTruthy();
});

test("a late list for a key since replaced is dropped", async () => {
  const answers: ((r: Response) => void)[] = [];
  server(LOCAL, LOCAL, () => new Promise<Response>((r) => answers.push(r)) as unknown as Response);
  render(<LlmSettingSection />);
  fireEvent.click(await screen.findByRole("radio", { name: /Grok/ }));
  const key = screen.getByLabelText("API key");
  fireEvent.input(key, { target: { value: "xai-a" } });
  fireEvent.blur(key);
  fireEvent.input(key, { target: { value: "xai-b" } });
  fireEvent.blur(key);
  await new Promise((r) => setTimeout(r, 20));
  expect(answers).toHaveLength(2);
  // Key B's refusal comes first, then key A's late list: B's refusal stands.
  answers[1](Response.json({ detail: "Grok refused the API key." }, { status: 400 }));
  expect(await screen.findByText("Grok refused the API key.")).toBeTruthy();
  answers[0](Response.json({ models: ["grok-a"] }));
  await new Promise((r) => setTimeout(r, 20));
  expect(screen.getByText("Grok refused the API key.")).toBeTruthy();
  expect(screen.queryByLabelText("Model")).toBeNull();
});

test("the note under the Model box", () => {
  const grok = provider("grok", "Grok");
  expect(modelsNote({ state: "listed", ids: ["grok-model"], checked: true }, "grok-model", grok)).toBe(
    "The key works. 1 model available: pick one or type a name. Leave the model blank for grok-model.",
  );
  expect(modelsNote({ state: "listed", ids: ["grok-model"], checked: false }, "grok-model", grok)).toBe(
    "1 model available: pick one or type a name. Leave the model blank for grok-model.",
  );
  expect(modelsNote({ state: "failed", error: "No.", unreachable: true }, "x", grok)).toBe(
    "No. You can still type a model's name.",
  );
  expect(modelsNote({ state: "failed", error: "Refused.", unreachable: false }, "x", grok)).toBe("Refused.");
});

// The ChatGPT plan (R43a): a ChatGPT sign-in in place of a key.

const PLAN = provider("chatgpt", "ChatGPT plan", { keys_at: "", default_model: "", signs_in: true });

test("the ChatGPT plan asks for a sign-in, not a key", async () => {
  const fetchMock = server({ ...LOCAL, providers: [...LOCAL.providers, PLAN] });
  render(<LlmSettingSection />);
  expect(await screen.findByText("· needs a ChatGPT sign-in")).toBeTruthy();
  fireEvent.click(screen.getByRole("radio", { name: /ChatGPT plan/ }));
  expect(screen.queryByLabelText("API key")).toBeNull();
  expect(screen.queryByLabelText("Model")).toBeNull();
  expect(screen.getByText("Sign in with ChatGPT under ChatGPT plan below to choose one of your plan's models.")).toBeTruthy();
  expect(fetchMock.mock.calls.some(([url]) => url === "/api/llm/models")).toBe(false);
});

test("signed in, the ChatGPT plan offers its own models and is chosen with no key", async () => {
  const signed = { ...LOCAL, providers: [...LOCAL.providers, { ...PLAN, has_key: true }] };
  const now = { ...signed, provider: "chatgpt" };
  now.providers = signed.providers.map((p) => (p.id === "chatgpt" ? { ...p, model: "gpt-a" } : p));
  const fetchMock = server(signed, now, () => Response.json({ models: ["gpt-a", "gpt-b"] }));
  render(<LlmSettingSection />);
  expect(await screen.findByText("· signed in")).toBeTruthy();
  fireEvent.click(screen.getByRole("radio", { name: /ChatGPT plan/ }));
  expect(
    await screen.findByText(
      "Signed in. 2 models available: pick one or type a name. Leave the model blank for the first in your plan's list.",
    ),
  ).toBeTruthy();
  const model = screen.getByLabelText("Model") as HTMLInputElement;
  expect(model.placeholder).toBe("First in your plan's list");
  fireEvent.click(screen.getByRole("button", { name: "Use this LLM" }));
  expect(await screen.findByText("Saved. ChatGPT plan answers from the next prompt.")).toBeTruthy();
  // A blank model is saved as the first in the plan's list, which the box then shows.
  expect(sent(fetchMock)).toEqual({ provider: "chatgpt", model: "" });
  expect(model.value).toBe("gpt-a");
});

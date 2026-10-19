import { cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { LlmProvider, LlmSetting } from "./api";
import { LlmSettingSection } from "./llm-setting";

function provider(id: string, label: string, extra: Partial<LlmProvider> = {}): LlmProvider {
  return { id, label, keys_at: `${id}.example`, model: "", default_model: `${id}-model`, has_key: false, ...extra };
}

const LOCAL: LlmSetting = {
  provider: "local",
  providers: [
    provider("local", "Local (llama.cpp)", { keys_at: "", default_model: "" }),
    provider("claude", "Claude", { has_key: true, model: "claude-sonnet-5-5" }),
    provider("grok", "Grok"),
  ],
};

// A fake server: GET /api/llm answers `read`; PUT answers `put` and is recorded.
function server(read: LlmSetting | Response, put: LlmSetting | Response = read) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
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
  expect((screen.getByLabelText("Model") as HTMLInputElement).placeholder).toBe("grok-model");
  fireEvent.input(key, { target: { value: " xai-1 " } });
  fireEvent.click(screen.getByRole("button", { name: "Use this LLM" }));
  expect(await screen.findByText("Saved. Grok answers from the next prompt.")).toBeTruthy();
  expect(sent(fetchMock)).toEqual({ provider: "grok", api_key: "xai-1", model: "" });
  expect(screen.getByText("Answering now:").textContent).toContain("Grok");
  expect((screen.getByLabelText("API key") as HTMLInputElement).value).toBe("");
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^LLM changed to grok \(\d+ ms\)$/));
});

test("a provider with a saved key keeps it, and shows its saved model", async () => {
  const fetchMock = server(LOCAL, { ...LOCAL, provider: "claude" });
  render(<LlmSettingSection />);
  fireEvent.click(await screen.findByRole("radio", { name: /Claude/ }));
  expect((screen.getByLabelText("API key") as HTMLInputElement).placeholder).toContain("Saved");
  expect((screen.getByLabelText("Model") as HTMLInputElement).value).toBe("claude-sonnet-5-5");
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

import { act, cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { heard, type Recognition, TAIL_MS, TalkButton, talkProblem } from "./talk";

// The browser's speech recognition, driven by the test: `say` gives what was heard so far,
// `fail` an error, and stop() ends it as the browser does.
class FakeRecognition implements Recognition {
  static made: FakeRecognition[] = [];
  lang = "";
  continuous = false;
  interimResults = false;
  onresult: Recognition["onresult"] = null;
  onerror: Recognition["onerror"] = null;
  onend: Recognition["onend"] = null;
  started = false;
  constructor() {
    FakeRecognition.made.push(this);
  }
  start() {
    this.started = true;
  }
  stop() {
    this.onend?.();
  }
  say(...parts: string[]) {
    this.onresult?.({ results: parts.map((transcript) => [{ transcript }]) });
  }
  fail(error: string) {
    this.onerror?.({ error });
  }
}

function talk(disabled = false) {
  const calls = {
    hearing: [] as string[],
    heard: [] as string[],
    problems: [] as (string | null)[],
  };
  render(
    <TalkButton
      disabled={disabled}
      onHearing={(t) => calls.hearing.push(t)}
      onHeard={(t) => calls.heard.push(t)}
      onProblem={(p) => calls.problems.push(p)}
    />,
  );
  return calls;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  FakeRecognition.made = [];
  vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("with no speech recognition in the browser, there is no button", () => {
  vi.stubGlobal("webkitSpeechRecognition", undefined);
  talk();
  expect(screen.queryByRole("button")).toBeNull();
});

test("holding the button listens, and letting go sends what was heard", async () => {
  const calls = talk();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(button);
  });
  const r = FakeRecognition.made[0]!;
  expect([r.started, r.continuous, r.interimResults]).toEqual([true, true, true]);
  expect(button.textContent).toBe("Listening… let go to send");
  expect(button.getAttribute("aria-pressed")).toBe("true");
  expect(console.info).toHaveBeenCalledWith("Push-to-talk: listening");
  await act(async () => {
    r.say("What is a ");
    r.say("What is a", " prime number?");
  });
  expect(calls.hearing).toEqual(["What is a", "What is a prime number?"]);
  await act(async () => {
    fireEvent.pointerUp(button);
    fireEvent.pointerLeave(button); // let go and moved off: stopped once
    r.say("What is a", " prime number", " exactly?"); // said as the button came up
  });
  expect(calls.heard).toEqual([]); // still listening for the last word
  await act(async () => {
    vi.advanceTimersByTime(TAIL_MS);
  });
  expect(calls.heard).toEqual(["What is a prime number exactly?"]);
  expect(button.textContent).toBe("Hold to talk");
  expect(console.info).toHaveBeenCalledWith(
    expect.stringMatching(/^Push-to-talk: heard 6 words in \d+ ms$/),
  );
});

test("the space bar works like holding the button", async () => {
  const calls = talk();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.keyDown(button, { key: " " });
    fireEvent.keyDown(button, { key: " ", repeat: true }); // held: not started again
  });
  expect(FakeRecognition.made).toHaveLength(1);
  await act(async () => {
    FakeRecognition.made[0]!.say("Hello");
    fireEvent.keyUp(button, { key: " " });
    vi.advanceTimersByTime(TAIL_MS);
  });
  expect(calls.heard).toEqual(["Hello"]);
});

test("nothing heard sends nothing and says so", async () => {
  const calls = talk();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(button);
    fireEvent.pointerUp(button);
    vi.advanceTimersByTime(TAIL_MS);
  });
  expect(calls.heard).toEqual([]);
  expect(calls.problems).toEqual([null, talkProblem("no-speech")]);
});

test("a microphone the browser may not use is explained", async () => {
  const calls = talk();
  await act(async () => {
    fireEvent.pointerDown(screen.getByRole("button", { name: "Hold to talk" }));
  });
  await act(async () => {
    FakeRecognition.made[0]!.fail("not-allowed");
    FakeRecognition.made[0]!.stop();
  });
  expect(calls.problems).toEqual([null, talkProblem("not-allowed")]); // said once
  expect(calls.heard).toEqual([]);
  expect(console.error).toHaveBeenCalledWith("Push-to-talk failed", "not-allowed");
});

test("recognition that can't start says so", async () => {
  class Broken extends FakeRecognition {
    override start() {
      throw new Error("already started");
    }
  }
  vi.stubGlobal("webkitSpeechRecognition", Broken);
  const calls = talk();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(button);
  });
  expect(calls.problems.at(-1)).toBe(talkProblem("start"));
  expect(button.textContent).toBe("Hold to talk");
});

test("while a reply is coming, the button can't start listening", async () => {
  talk(true);
  const button = screen.getByRole("button", { name: "Hold to talk" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  fireEvent.keyDown(button, { key: "Enter" });
  expect(FakeRecognition.made).toHaveLength(0);
});

test("each recognition error gets plain words, and a deliberate stop none", () => {
  expect(talkProblem("aborted")).toBeNull();
  for (const e of ["no-speech", "not-allowed", "service-not-allowed", "audio-capture", "x"]) {
    expect(talkProblem(e)).toMatch(/\.$/);
  }
  expect(heard([[{ transcript: " a  b " }], [{ transcript: "c" }]])).toBe("a b c");
});

test("recognition that fails or ends on its own while held sends nothing", async () => {
  const calls = talk();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(button);
  });
  await act(async () => {
    FakeRecognition.made[0]!.say("What is a");
    FakeRecognition.made[0]!.stop(); // ended by the browser, the button still held
  });
  expect(calls.heard).toEqual([]);
  expect(calls.hearing).toEqual(["What is a"]); // left in the prompt box
  expect(console.info).toHaveBeenCalledWith("Push-to-talk: ended without sending");
  expect(button.textContent).toBe("Hold to talk");
  await act(async () => {
    fireEvent.pointerDown(button);
  });
  await act(async () => {
    FakeRecognition.made[1]!.say("What is a");
    FakeRecognition.made[1]!.fail("network");
    fireEvent.pointerUp(button); // let go after the error: still not sent
    vi.advanceTimersByTime(TAIL_MS);
  });
  expect(calls.heard).toEqual([]);
  expect(calls.problems.at(-1)).toBe(talkProblem("network"));
});

test("recognition that ends on its own after the button is let go sends once", async () => {
  const calls = talk();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(button);
  });
  const r = FakeRecognition.made[0]!;
  const stopped = vi.spyOn(r, "stop");
  await act(async () => {
    r.say("What is a prime?");
    fireEvent.pointerUp(button);
    r.onend?.(); // ended by the browser before the tail is up
  });
  expect(calls.heard).toEqual(["What is a prime?"]);
  await act(async () => {
    vi.advanceTimersByTime(TAIL_MS);
  });
  expect(calls.heard).toEqual(["What is a prime?"]); // not sent again
  expect(stopped).not.toHaveBeenCalled();
});

test("leaving the page while listening stops listening", async () => {
  const calls = talk();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(button);
    fireEvent.pointerUp(button);
  });
  const r = FakeRecognition.made[0]!;
  const stopped = vi.spyOn(r, "stop");
  r.say("What is a"); // heard before the page was left: not sent
  cleanup();
  expect(calls.heard).toEqual([]);
  expect(stopped).toHaveBeenCalledTimes(1);
  vi.advanceTimersByTime(TAIL_MS); // the pending stop was cleared
  expect(stopped).toHaveBeenCalledTimes(1);
});

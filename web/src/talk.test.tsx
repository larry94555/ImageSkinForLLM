import { act, cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import {
  heard,
  leastSure,
  type Recognition,
  SURE,
  TAIL_MS,
  TalkButton,
  talkProblem,
  TAP_MS,
} from "./talk";

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
  // As `say`, with how sure the browser is of each phrase.
  sayWith(...parts: [string, number][]) {
    this.onresult?.({
      results: parts.map(([transcript, confidence]) => [{ transcript, confidence }]),
    });
  }
  fail(error: string) {
    this.onerror?.({ error });
  }
}

function talk(disabled = false) {
  const calls = {
    hearing: [] as string[],
    heard: [] as string[],
    unsure: [] as string[],
    edited: [] as string[],
    problems: [] as (string | null)[],
  };
  render(
    <TalkButton
      disabled={disabled}
      onHearing={(t) => calls.hearing.push(t)}
      onHeard={(t) => calls.heard.push(t)}
      onUnsure={(t) => calls.unsure.push(t)}
      onEdit={(t) => calls.edited.push(t)}
      onProblem={(p) => calls.problems.push(p)}
    />,
  );
  return calls;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "performance"] });
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
  expect(button.textContent).toBe("Let go to send or…");
  expect(button.getAttribute("aria-pressed")).toBe("true");
  expect(console.info).toHaveBeenCalledWith("Push-to-talk: listening");
  await act(async () => {
    r.say("What is a ");
    r.say("What is a", " prime number?");
  });
  expect(calls.hearing).toEqual(["What is a", "What is a prime number?"]);
  await act(async () => {
    vi.advanceTimersByTime(TAP_MS); // held, not tapped
    fireEvent.pointerUp(button);
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
    vi.advanceTimersByTime(TAP_MS);
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
    vi.advanceTimersByTime(TAP_MS);
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
    vi.advanceTimersByTime(TAP_MS);
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
    vi.advanceTimersByTime(TAP_MS);
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
    vi.advanceTimersByTime(TAP_MS);
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

test("a quick click or tap keeps listening until the button is clicked again", async () => {
  const calls = talk();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(button);
    vi.advanceTimersByTime(80); // a touchpad tap
    fireEvent.pointerUp(button);
  });
  const r = FakeRecognition.made[0]!;
  expect(button.textContent).toBe("Click to send or…");
  expect(console.info).toHaveBeenCalledWith(
    "Push-to-talk: let go after 80 ms; listening until clicked again",
  );
  await act(async () => {
    vi.advanceTimersByTime(TAIL_MS * 3);
    r.say("What is a prime?");
  });
  expect(calls.heard).toEqual([]);
  expect(calls.problems).toEqual([null]); // no "didn't hear anything"
  await act(async () => {
    fireEvent.pointerDown(button); // clicked again: sent
    fireEvent.pointerUp(button);
  });
  expect(FakeRecognition.made).toHaveLength(1); // not started again
  await act(async () => {
    vi.advanceTimersByTime(TAIL_MS);
  });
  expect(calls.heard).toEqual(["What is a prime?"]);
  expect(button.textContent).toBe("Hold to talk");
});

test("the pointer is kept while held, so moving off the button doesn't end listening", async () => {
  talk();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  const captured = vi.fn();
  button.setPointerCapture = captured;
  await act(async () => {
    fireEvent.pointerDown(button, { pointerId: 7 });
    fireEvent.pointerLeave(button);
    vi.advanceTimersByTime(TAIL_MS * 2);
  });
  expect(captured).toHaveBeenCalledWith(7);
  expect(button.textContent).toBe("Let go to send or…");
});

test("a pointer the browser cancels stops listening, rather than keeping it on as a tap", async () => {
  const calls = talk();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(button);
    vi.advanceTimersByTime(80);
    FakeRecognition.made[0]!.say("What is");
    fireEvent.pointerCancel(button);
  });
  expect(button.textContent).not.toBe("Click to send or…");
  await act(async () => {
    vi.advanceTimersByTime(TAIL_MS);
  });
  expect(button.textContent).toBe("Hold to talk");
  expect(calls.heard).toEqual(["What is"]);
});

// --- Words perhaps misheard (R179) ---

test("leastSure is the lowest confidence given, leaving out phrases given none", () => {
  const phrases = (...c: (number | undefined)[]) =>
    c.map((confidence) => [{ transcript: "a", confidence }]);
  expect(leastSure(phrases(0.95, 0.6))).toBe(0.6);
  expect(leastSure(phrases(0.9, 0))).toBe(0.9);
  expect(leastSure(phrases(undefined, 0))).toBeNull();
  expect(leastSure([])).toBeNull();
});

// Holds the button, hears `parts` with their confidence, and lets go.
async function holdAndSay(...parts: [string, number][]) {
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(button);
  });
  await act(async () => {
    FakeRecognition.made[0]!.sayWith(...parts);
    vi.advanceTimersByTime(TAP_MS);
    fireEvent.pointerUp(button);
    vi.advanceTimersByTime(TAIL_MS);
  });
}

test("a phrase the browser isn't sure of is left to check, not sent", async () => {
  const calls = talk();
  await holdAndSay(["Who is", 0.93], [" Joe Budden?", 0.62]); // Larry's "Jill Biden"
  expect(calls.heard).toEqual([]);
  expect(calls.unsure).toEqual(["Who is Joe Budden?"]);
  expect(calls.hearing.at(-1)).toBe("Who is Joe Budden?"); // in the box, to fix
  expect(console.info).toHaveBeenCalledWith(
    "Push-to-talk: not sure of the words (confidence 0.62), left to check",
  );
});

test("speech heard clearly is sent at once", async () => {
  const calls = talk();
  await holdAndSay(["What is a prime number?", SURE]);
  expect(calls.heard).toEqual(["What is a prime number?"]);
  expect(calls.unsure).toEqual([]);
  expect(console.info).toHaveBeenCalledWith("Push-to-talk: sent (confidence 0.80)");
});

test("with no confidence from the browser, what was heard is sent as before", async () => {
  const calls = talk();
  await holdAndSay(["What is a prime number?", 0]);
  expect(calls.heard).toEqual(["What is a prime number?"]);
  expect(console.info).toHaveBeenCalledWith("Push-to-talk: sent (confidence not given)");
});

// --- Edit while listening (R179) ---

test("Edit shows only while listening, and after a tap stops it without sending", async () => {
  const calls = talk();
  expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(button);
    fireEvent.pointerUp(button); // a tap: listening until clicked again
  });
  expect(button.textContent).toBe("Click to send or…");
  await act(async () => {
    FakeRecognition.made[0]!.say("Who is Joe Budden?");
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  });
  expect(calls.heard).toEqual([]);
  expect(calls.edited).toEqual(["Who is Joe Budden?"]);
  expect(button.textContent).toBe("Hold to talk");
  expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
  expect(console.info).toHaveBeenCalledWith(
    "Push-to-talk: Edit chosen; left in the box to change",
  );
});

test("a held button let go over Edit edits instead of sending", async () => {
  const calls = talk();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(button);
  });
  const link = screen.getByRole("button", { name: "Edit" });
  link.getBoundingClientRect = () => new DOMRect(10, 20, 40, 24);
  await act(async () => {
    FakeRecognition.made[0]!.say("Who is Bill Biden?");
    vi.advanceTimersByTime(TAP_MS);
    fireEvent.pointerUp(button, { clientX: 30, clientY: 30 }); // slid onto Edit
    vi.advanceTimersByTime(TAIL_MS);
  });
  expect(calls.heard).toEqual([]);
  expect(calls.edited).toEqual(["Who is Bill Biden?"]);
});

test("let go off Edit, it sends; Edit with nothing heard does nothing", async () => {
  const calls = talk();
  const button = screen.getByRole("button", { name: "Hold to talk" });
  await act(async () => {
    fireEvent.pointerDown(button);
  });
  screen.getByRole("button", { name: "Edit" }).getBoundingClientRect = () =>
    new DOMRect(10, 20, 40, 24);
  await act(async () => {
    FakeRecognition.made[0]!.say("Hello");
    vi.advanceTimersByTime(TAP_MS);
    fireEvent.pointerUp(button, { clientX: 300, clientY: 30 });
    vi.advanceTimersByTime(TAIL_MS);
  });
  expect(calls.heard).toEqual(["Hello"]);
  await act(async () => {
    fireEvent.pointerDown(button);
    fireEvent.pointerUp(button);
  });
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  });
  expect(calls.edited).toEqual([]);
});

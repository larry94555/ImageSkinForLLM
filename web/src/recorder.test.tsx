import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { clock, extension, MAX_S, MICROPHONE, reasonOf, recordingType, VoiceRecorder, WHY_NOT } from "./recorder";

const SOUND = { id: "s1", kind: "sounds", name: "voice-1.webm", format: "webm", size: 9, uploaded_at: "", seconds: 84, score: null, speech: 80 };

// The server: what each recording upload answers, and the microphone reports it was sent.
function server(upload: Response | (() => Response), deleteFails = false) {
  const reports: unknown[] = [];
  const uploads: File[] = [];
  const deleted: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/wizard/recording") {
        reports.push(JSON.parse(init!.body as string));
        return Response.json({ logged: true });
      }
      if (url === "/api/uploads/sounds" && init?.method === "POST") {
        uploads.push((init.body as FormData).get("file") as File);
        return typeof upload === "function" ? upload() : upload.clone();
      }
      if (url.startsWith("/api/uploads/sounds/") && init?.method === "DELETE") {
        if (deleteFails) return Response.json({ detail: "busy" }, { status: 500 });
        deleted.push(url);
        return Response.json({});
      }
      return new Response("", { status: 404 });
    }),
  );
  return { reports, uploads, deleted };
}

// A MediaRecorder that hands over one chunk of its type when stopped.
class FakeRecorder {
  static made: FakeRecorder[] = [];
  static isTypeSupported = vi.fn((t: string) => t === "audio/webm;codecs=opus");
  state = "inactive";
  mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(_stream: MediaStream, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? "";
    FakeRecorder.made.push(this);
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["opus"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

// A microphone whose tracks can be checked for being stopped; `answer` is "ok" or an error's name.
function microphone(answer = "ok") {
  const stop = vi.fn();
  const getUserMedia = vi.fn(async () => {
    if (answer !== "ok") throw Object.assign(new Error(answer), { name: answer });
    const track = { stop, label: "Microphone Array" };
    return { getTracks: () => [track], getAudioTracks: () => [track] } as unknown as MediaStream;
  });
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  return { getUserMedia, stop };
}

function recorder(props: { onAdded?: () => void; onChanging?: (busy: boolean) => void } = {}) {
  return render(<VoiceRecorder onAdded={props.onAdded ?? (() => {})} onChanging={props.onChanging ?? (() => {})} />);
}

async function recordAndStop() {
  fireEvent.click(await screen.findByRole("button", { name: "Start recording" }));
  fireEvent.click(await screen.findByRole("button", { name: "Stop" }));
}

beforeEach(() => {
  FakeRecorder.made = [];
  Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
  URL.createObjectURL = vi.fn(() => "blob:voice");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Reflect.deleteProperty(navigator, "mediaDevices");
});

test("a refused or missing microphone means what it says", () => {
  expect(reasonOf({ name: "NotAllowedError" })).toBe("refused");
  expect(reasonOf({ name: "SecurityError" })).toBe("refused");
  expect(reasonOf({ name: "NotFoundError" })).toBe("no-microphone");
  expect(reasonOf({ name: "NotSupportedError" })).toBe("unsupported");
  expect(reasonOf({ name: "NotReadableError" })).toBe("failed");
  expect(reasonOf(null)).toBe("failed");
});

test("the recording's type is one the server reads, with a matching file ending", () => {
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  expect(recordingType()).toBe("audio/webm;codecs=opus");
  FakeRecorder.isTypeSupported.mockImplementationOnce(() => false).mockImplementationOnce(() => false).mockImplementationOnce((t) => t === "audio/mp4");
  expect(recordingType()).toBe("audio/mp4");
  expect(extension("audio/mp4")).toBe("m4a");
  expect(extension("audio/ogg;codecs=opus")).toBe("ogg");
  expect(extension("audio/webm;codecs=opus")).toBe("webm");
  expect(clock(65.7)).toBe("1:05");
  expect(clock(0)).toBe("0:00");
});

test("without a way to record, the step says so, logs why and never asks", async () => {
  const { reports } = server(Response.json(SOUND));
  recorder();
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  expect(await screen.findByText(WHY_NOT.unsupported, { exact: false })).toBeTruthy();
  await waitFor(() => expect(reports).toEqual([{ made: false, reason: "unsupported" }]));
  expect(screen.queryByRole("button", { name: "Try the microphone again" })).toBeNull();
});

test("a page that isn't secure can't ask for the microphone", async () => {
  microphone();
  Object.defineProperty(window, "isSecureContext", { value: false, configurable: true });
  server(Response.json(SOUND));
  recorder();
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  expect(await screen.findByText(WHY_NOT.insecure, { exact: false })).toBeTruthy();
});

test("the microphone is asked for only when the first recording starts, with the voice as it is", async () => {
  const { getUserMedia } = microphone();
  server(Response.json(SOUND));
  recorder();
  expect(screen.getByText("Recording 1 of 3: Voice 1")).toBeTruthy();
  expect(screen.getByText(/Hi, thanks for stopping by/)).toBeTruthy();
  expect(getUserMedia).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  expect(await screen.findByRole("button", { name: "Stop" })).toBeTruthy();
  expect(getUserMedia).toHaveBeenCalledWith({ audio: MICROPHONE, video: false });
  expect(MICROPHONE).toEqual({ echoCancellation: false, noiseSuppression: false, autoGainControl: false });
  expect(screen.getByText("0:00")).toBeTruthy();
});

test("a recording is played back, uploaded, logged and kept, then the next one is offered", async () => {
  const { stop } = microphone();
  const { reports, uploads } = server(Response.json({ ...SOUND, problems: [] }));
  const onAdded = vi.fn();
  const changing: boolean[] = [];
  recorder({ onAdded, onChanging: (b) => changing.push(b) });
  await recordAndStop();
  expect(await screen.findByText(/^Kept\./)).toBeTruthy();
  expect(screen.getByLabelText("The recording you made").getAttribute("src")).toBe("blob:voice");
  expect(stop).toHaveBeenCalled(); // the microphone is off once stopped
  expect(uploads[0].name).toMatch(/^voice-1-.*\.webm$/);
  expect(uploads[0].type).toBe("audio/webm;codecs=opus");
  expect(reports).toEqual([{ made: true, seconds: expect.any(Number), format: "audio/webm;codecs=opus" }]);
  expect(onAdded).toHaveBeenCalledTimes(1);
  expect(changing).toEqual([true, false]);
  fireEvent.click(screen.getByRole("button", { name: "Next recording: Voice 2" }));
  expect(screen.getByText("Recording 2 of 3: Voice 2")).toBeTruthy();
  expect(screen.getByText(/Could you call me back around four thirty/)).toBeTruthy();
  expect(screen.queryByLabelText("The recording you made")).toBeNull();
});

test("the last recording says that's all three", async () => {
  microphone();
  const { uploads } = server(Response.json({ ...SOUND, problems: [] }));
  recorder();
  for (const n of [2, 3]) {
    await recordAndStop();
    fireEvent.click(await screen.findByRole("button", { name: `Next recording: Voice ${n}` }));
  }
  expect(screen.getByText(/What did you do last weekend/)).toBeTruthy();
  await recordAndStop();
  expect(await screen.findByText(/That's all three: click Next/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: /Next recording/ })).toBeNull();
  expect(uploads.map((f) => f.name.slice(0, 7))).toEqual(["voice-1", "voice-2", "voice-3"]);
});

test("a recording that fails its checks says why, is not kept, and can be recorded again", async () => {
  microphone();
  const { deleted } = server(Response.json({ ...SOUND, problems: ["There is too much background noise."] }));
  const onAdded = vi.fn();
  recorder({ onAdded });
  await recordAndStop();
  expect(await screen.findByText("There is too much background noise.")).toBeTruthy();
  expect(screen.getByText("Not kept. Record again to try again.")).toBeTruthy();
  await waitFor(() => expect(deleted).toEqual(["/api/uploads/sounds/s1"]));
  expect(onAdded).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: /Next recording/ })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Record again" }));
  expect(await screen.findByRole("button", { name: "Stop" })).toBeTruthy();
  expect(screen.getByText("Recording 1 of 3: Voice 1")).toBeTruthy();
});

test("a failed recording that can't be removed says it is still in the list", async () => {
  microphone();
  server(Response.json({ ...SOUND, problems: ["There is too much background noise."] }), true);
  const onAdded = vi.fn();
  recorder({ onAdded });
  await recordAndStop();
  expect(await screen.findByText(/This recording could not be removed\. It is still in Your recordings/)).toBeTruthy();
  expect(screen.queryByText("Not kept. Record again to try again.")).toBeNull();
  expect(onAdded).toHaveBeenCalled();
  expect(console.error).toHaveBeenCalledWith("Could not remove the recording that failed its checks", expect.any(Error));
});

test("a recording the server refuses shows the reason", async () => {
  microphone();
  server(() => Response.json({ detail: "The recording could not be read." }, { status: 400 }));
  const changing: boolean[] = [];
  recorder({ onChanging: (b) => changing.push(b) });
  await recordAndStop();
  expect(await screen.findByText("The recording could not be read.")).toBeTruthy();
  expect(changing).toEqual([true, false]);
});

test("a refused microphone says why, offers files, logs it and can be tried again", async () => {
  const { getUserMedia } = microphone("NotAllowedError");
  const { reports } = server(Response.json(SOUND));
  recorder();
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  expect(await screen.findByText(WHY_NOT.refused, { exact: false })).toBeTruthy();
  await waitFor(() => expect(reports).toEqual([{ made: false, reason: "refused" }]));
  fireEvent.click(screen.getByRole("button", { name: "Try the microphone again" }));
  await waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(2));
});

test("a recorder the browser can't make for the microphone counts as unsupported", async () => {
  const { stop } = microphone();
  vi.stubGlobal(
    "MediaRecorder",
    Object.assign(
      function () {
        throw new Error("no recorder");
      },
      { isTypeSupported: () => false },
    ),
  );
  server(Response.json(SOUND));
  recorder();
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  expect(await screen.findByText(WHY_NOT.unsupported, { exact: false })).toBeTruthy();
  expect(stop).toHaveBeenCalled();
});

test("leaving the step while recording turns the microphone off and keeps nothing", async () => {
  const { stop } = microphone();
  const { uploads, reports } = server(Response.json(SOUND));
  const { unmount } = recorder();
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  await screen.findByRole("button", { name: "Stop" });
  unmount();
  expect(stop).toHaveBeenCalled();
  await act(async () => {});
  expect(uploads).toEqual([]);
  expect(reports).toEqual([]);
});

test("a microphone allowed after the step was left is turned off at once", async () => {
  let allow = (_: MediaStream) => {};
  const stop = vi.fn();
  const getUserMedia = vi.fn(() => new Promise<MediaStream>((r) => (allow = r)));
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia }, configurable: true });
  vi.stubGlobal("MediaRecorder", FakeRecorder);
  server(Response.json(SOUND));
  const { unmount } = recorder();
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  await waitFor(() => expect(getUserMedia).toHaveBeenCalled());
  unmount();
  await act(async () => allow({ getTracks: () => [{ stop }] } as unknown as MediaStream));
  expect(stop).toHaveBeenCalled();
  expect(FakeRecorder.made).toEqual([]);
});

test("the timer counts, and a recording stops itself at the 10-minute limit", async () => {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "setTimeout", "clearTimeout", "performance"] });
  microphone();
  server(Response.json({ ...SOUND, problems: [] }));
  recorder();
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(65_000);
  });
  expect(screen.getByText("1:05")).toBeTruthy();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(MAX_S * 1000);
  });
  expect(FakeRecorder.made[0].state).toBe("inactive");
  expect(console.info).toHaveBeenCalledWith("Recording stopped at the 10-minute limit");
});

test("the level meter shows how loud the voice is", async () => {
  const frames: FrameRequestCallback[] = [];
  vi.stubGlobal("requestAnimationFrame", (f: FrameRequestCallback) => frames.push(f));
  vi.stubGlobal("cancelAnimationFrame", () => {});
  const close = vi.fn(async () => {});
  vi.stubGlobal(
    "AudioContext",
    class {
      close = close;
      createAnalyser() {
        return { fftSize: 4, connect() {}, getFloatTimeDomainData: (a: Float32Array) => a.set([0.1, -0.42, 0.2, 0]) };
      }
      createMediaStreamSource() {
        return { connect() {} };
      }
    },
  );
  microphone();
  server(Response.json({ ...SOUND, problems: [] }));
  recorder();
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  await screen.findByRole("button", { name: "Stop" });
  const bar = screen.getByLabelText("Sound level").firstElementChild as HTMLElement;
  expect(bar.style.width).toBe("42%");
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  await screen.findByText(/^Kept\./);
  expect(close).toHaveBeenCalled();
});

test("any recording can be chosen first, and the ones kept are ticked", async () => {
  microphone();
  const { uploads } = server(Response.json({ ...SOUND, problems: [] }));
  recorder();
  fireEvent.click(screen.getByRole("button", { name: "Voice 3" }));
  expect(screen.getByText("Recording 3 of 3: Voice 3")).toBeTruthy();
  expect(screen.getByText(/What did you do last weekend/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  await screen.findByRole("button", { name: "Stop" });
  expect((screen.getByRole("button", { name: "Voice 1" }) as HTMLButtonElement).disabled).toBe(true); // not while recording
  fireEvent.click(screen.getByRole("button", { name: "Stop" }));
  await screen.findByText(/^Kept\./);
  expect(uploads[0].name).toMatch(/^voice-3-/);
  expect(screen.getByRole("button", { name: "Voice 3 kept" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Voice 2" }));
  expect(screen.getByText("Recording 2 of 3: Voice 2")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Voice 2" }).getAttribute("aria-pressed")).toBe("true");
  expect(screen.queryByLabelText("The recording you made")).toBeNull();
});

test("a recorder that won't start turns the microphone off and can be tried again", async () => {
  const { stop, getUserMedia } = microphone();
  const start = vi.spyOn(FakeRecorder.prototype, "start").mockImplementationOnce(() => {
    throw Object.assign(new Error("can't start"), { name: "NotSupportedError" });
  });
  const { reports } = server(Response.json(SOUND));
  const changing: boolean[] = [];
  recorder({ onChanging: (b) => changing.push(b) });
  fireEvent.click(screen.getByRole("button", { name: "Start recording" }));
  expect(await screen.findByText(WHY_NOT.failed, { exact: false })).toBeTruthy();
  expect(stop).toHaveBeenCalled();
  expect(screen.queryByText("Asking for the microphone…")).toBeNull();
  expect(changing).toEqual([]);
  await waitFor(() => expect(reports).toEqual([{ made: false, reason: "failed" }]));
  fireEvent.click(screen.getByRole("button", { name: "Try the microphone again" }));
  expect(await screen.findByRole("button", { name: "Stop" })).toBeTruthy();
  expect(getUserMedia).toHaveBeenCalledTimes(2);
  expect(start).toHaveBeenCalledTimes(2);
});

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { betterCamera, CameraPhoto, cameraBlocked, grabFrame, NO_PICTURE, reasonOf, WHY_NOT } from "./camera";

const PHOTO = { id: "p1", kind: "photos", name: "camera.jpg", format: "jpg", size: 9, uploaded_at: "", seconds: null, score: 81, speech: null };

// The server: what each photo upload answers, and the camera reports it was sent.
function server(upload: Response | (() => Response), deleteFails = false) {
  const reports: unknown[] = [];
  const uploads: File[] = [];
  const deleted: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/wizard/camera") {
        reports.push(JSON.parse(init!.body as string));
        return Response.json({ logged: true });
      }
      if (url === "/api/uploads/photos" && init?.method === "POST") {
        uploads.push((init.body as FormData).get("file") as File);
        return typeof upload === "function" ? upload() : upload.clone();
      }
      if (url.startsWith("/api/uploads/photos/") && init?.method === "DELETE") {
        if (deleteFails) return Response.json({ detail: "busy" }, { status: 500 });
        deleted.push(url);
        return Response.json({});
      }
      return new Response("", { status: 404 });
    }),
  );
  return { reports, uploads, deleted };
}

// A camera whose stream's tracks can be checked for being stopped.
// Two cameras by default: the laptop's own, opened first, and a virtual one.
const CAMERAS = [
  { kind: "videoinput", deviceId: "laptop", label: "Integrated Camera" },
  { kind: "videoinput", deviceId: "obs", label: "OBS Virtual Camera" },
  { kind: "audioinput", deviceId: "mic", label: "Microphone" },
];

function camera(answer: "ok" | string = "ok", devices = CAMERAS) {
  const stop = vi.fn();
  const applyConstraints = vi.fn(async () => {});
  const getUserMedia = vi.fn(async (asked: MediaStreamConstraints) => {
    if (answer !== "ok") throw Object.assign(new Error(answer), { name: answer });
    const video = asked.video as { deviceId?: { ideal?: string; exact?: string } } | true;
    const id = video === true ? devices[0].deviceId : (video.deviceId?.exact ?? video.deviceId?.ideal ?? "");
    const label = devices.find((d) => d.deviceId === id)?.label ?? "";
    const track = { stop, label, getSettings: () => ({ deviceId: id }), applyConstraints };
    return { getTracks: () => [track], getVideoTracks: () => [track] } as unknown as MediaStream;
  });
  const enumerateDevices = vi.fn(async () => devices);
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia, enumerateDevices },
    configurable: true,
  });
  return { getUserMedia, stop, applyConstraints };
}

const grab = vi.fn(async () => ({ blob: new Blob(["jpeg"], { type: "image/jpeg" }), width: 1280, height: 720 }));

beforeEach(() => {
  localStorage.clear();
  Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  URL.createObjectURL = vi.fn(() => "blob:shot");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {});
  grab.mockClear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Reflect.deleteProperty(navigator, "mediaDevices");
});

async function takePhoto() {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  fireEvent.click(await screen.findByRole("button", { name: "Take photo" }));
  expect(screen.getByText("3")).toBeTruthy();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(screen.getByText("2")).toBeTruthy();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
}

test("a refused camera, or a missing one, means what it says", () => {
  expect(reasonOf({ name: "NotAllowedError" })).toBe("refused");
  expect(reasonOf({ name: "SecurityError" })).toBe("refused");
  expect(reasonOf({ name: "NotFoundError" })).toBe("no-camera");
  expect(reasonOf({ name: "NotSupportedError" })).toBe("unsupported");
  expect(reasonOf({ name: "NotReadableError" })).toBe("failed");
  expect(reasonOf(null)).toBe("failed");
});

test("a page that isn't secure can't ask for the camera", () => {
  Object.defineProperty(window, "isSecureContext", { value: false, configurable: true });
  expect(cameraBlocked()).toBe("insecure");
});

test("without a camera API, the step says so, logs why and never asks", async () => {
  const { reports } = server(Response.json(PHOTO));
  const onAdded = vi.fn();
  render(<CameraPhoto onAdded={onAdded} onChanging={() => {}} grab={grab} />);
  expect(await screen.findByText(WHY_NOT.unsupported, { exact: false })).toBeTruthy();
  await waitFor(() => expect(reports).toEqual([{ taken: false, reason: "unsupported" }]));
  expect(screen.queryByRole("button", { name: "Try the camera again" })).toBeNull();
});

test("a refused camera says why, offers a file, and can be tried again", async () => {
  const { getUserMedia } = camera("NotAllowedError");
  const { reports } = server(Response.json(PHOTO));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  expect(await screen.findByText(/Add a photo you already have below instead/)).toBeTruthy();
  expect(screen.getByText(WHY_NOT.refused, { exact: false })).toBeTruthy();
  await waitFor(() => expect(reports).toEqual([{ taken: false, reason: "refused" }]));
  fireEvent.click(screen.getByRole("button", { name: "Try the camera again" }));
  await waitFor(() => expect(getUserMedia).toHaveBeenCalledTimes(2));
});

test("a photo taken after the countdown is uploaded, checked, kept, and turns the camera off", async () => {
  const { stop } = camera();
  const { reports, uploads } = server(Response.json({ ...PHOTO, problems: [] }));
  const onAdded = vi.fn();
  const changing: boolean[] = [];
  render(<CameraPhoto onAdded={onAdded} onChanging={(b) => changing.push(b)} grab={grab} />);
  expect(await screen.findByLabelText("The camera's live picture")).toBeTruthy();
  await takePhoto();
  expect(await screen.findByText("Kept. Click Next, or Retake to try again.")).toBeTruthy();
  expect(screen.getByText(/Looks good/)).toBeTruthy();
  expect(screen.getByRole("img", { name: "The photo you took" }).getAttribute("src")).toBe("blob:shot");
  expect(stop).toHaveBeenCalled();
  expect(reports).toEqual([{ taken: true, width: 1280, height: 720, camera: "Integrated Camera" }]);
  expect(uploads[0].name).toMatch(/^camera-.*\.jpg$/);
  expect(onAdded).toHaveBeenCalledTimes(1);
  expect(changing).toEqual([true, false]);
});

test("Retake turns the camera back on", async () => {
  const { getUserMedia } = camera();
  server(Response.json({ ...PHOTO, problems: [] }));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  await takePhoto();
  fireEvent.click(await screen.findByRole("button", { name: "Retake" }));
  expect(await screen.findByRole("button", { name: "Take photo" })).toBeTruthy();
  expect(getUserMedia).toHaveBeenCalledTimes(2);
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:shot");
});

test("a photo that fails its checks shows why, isn't kept, and offers Retake", async () => {
  camera();
  const { deleted } = server(Response.json({ ...PHOTO, problems: ["The photo is too dark."] }));
  const onAdded = vi.fn();
  render(<CameraPhoto onAdded={onAdded} onChanging={() => {}} grab={grab} />);
  await takePhoto();
  expect(await screen.findByText("The photo is too dark.")).toBeTruthy();
  expect(screen.getByText("Not kept. Retake to try again.")).toBeTruthy();
  expect(screen.queryByText(/^Kept\./)).toBeNull();
  expect(screen.getByRole("button", { name: "Retake" })).toBeTruthy();
  await waitFor(() => expect(deleted).toEqual(["/api/uploads/photos/p1"]));
  expect(onAdded).not.toHaveBeenCalled(); // never in the list
});

test("a failed photo that can't be removed is shown in the list, to remove there", async () => {
  camera();
  server(Response.json({ ...PHOTO, problems: ["The photo is too dark."] }), true);
  const onAdded = vi.fn();
  render(<CameraPhoto onAdded={onAdded} onChanging={() => {}} grab={grab} />);
  await takePhoto();
  await waitFor(() => expect(onAdded).toHaveBeenCalled());
  expect(console.error).toHaveBeenCalledWith("Could not remove the camera photo that failed its checks", expect.any(Error));
  expect(await screen.findByText(/This photo could not be removed\. It is still in Your photos/)).toBeTruthy();
  expect(screen.queryByText("Not kept. Retake to try again.")).toBeNull();
});

test("a photo the server refuses shows the reason", async () => {
  camera();
  server(() => Response.json({ detail: "The file is not a photo." }, { status: 400 }));
  const changing: boolean[] = [];
  render(<CameraPhoto onAdded={() => {}} onChanging={(b) => changing.push(b)} grab={grab} />);
  await takePhoto();
  expect(await screen.findByText("The file is not a photo.")).toBeTruthy();
  expect(changing).toEqual([true, false]);
});

test("a picture that can't be grabbed goes back to the live picture", async () => {
  camera();
  server(Response.json(PHOTO));
  const failing = vi.fn(async () => {
    throw new Error("no frame");
  });
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={failing} />);
  await takePhoto();
  expect(await screen.findByRole("button", { name: "Take photo" })).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith("Could not take the picture", expect.any(Error));
  expect(screen.getByText("no frame")).toBeTruthy();
});

test("leaving the step turns the camera off", async () => {
  const { stop } = camera();
  server(Response.json(PHOTO));
  const { unmount } = render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  await screen.findByRole("button", { name: "Take photo" });
  unmount();
  expect(stop).toHaveBeenCalled();
});

test("a camera allowed after the step was left is turned off at once", async () => {
  let allow = (_: MediaStream) => {};
  const stop = vi.fn();
  const getUserMedia = vi.fn(() => new Promise<MediaStream>((r) => (allow = r)));
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia, enumerateDevices: async () => [] },
    configurable: true,
  });
  server(Response.json(PHOTO));
  const { unmount } = render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  await waitFor(() => expect(getUserMedia).toHaveBeenCalled());
  unmount();
  await act(async () => allow({ getTracks: () => [{ stop }] } as unknown as MediaStream));
  expect(stop).toHaveBeenCalled();
});

test("a camera that opens after a newer one was asked for is turned off, and the newer one stays", async () => {
  const devices = [
    { kind: "videoinput", deviceId: "laptop", label: "Integrated Camera" },
    { kind: "videoinput", deviceId: "usb", label: "HD Webcam" },
    { kind: "videoinput", deviceId: "dock", label: "Dock Camera" },
  ];
  const { getUserMedia } = camera("ok", devices);
  const works = getUserMedia.getMockImplementation()!;
  server(Response.json(PHOTO));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  const select = (await screen.findByRole("combobox")) as HTMLSelectElement;
  // Each camera asked for from here waits to be answered; each answered stream has its own stop.
  const pending: { asked: MediaStreamConstraints; answer: (m: MediaStream) => void }[] = [];
  getUserMedia.mockImplementation((asked: MediaStreamConstraints) => new Promise((answer) => pending.push({ asked, answer })));
  const stops: (() => void)[] = [];
  async function answer(i: number) {
    const media = await works(pending[i].asked);
    const track = media.getVideoTracks()[0] as unknown as { stop: () => void };
    stops[i] = vi.fn<() => void>();
    track.stop = stops[i];
    await act(async () => pending[i].answer(media));
  }
  // Two picks, the second landing while the first camera is still opening.
  fireEvent.change(select, { target: { value: "usb" } });
  await waitFor(() => expect(pending).toHaveLength(1));
  fireEvent.change(select, { target: { value: "dock" } });
  await waitFor(() => expect(pending).toHaveLength(2));
  await answer(1); // the newer opens first
  await answer(0); // then the older one
  expect(stops[0]).toHaveBeenCalled();
  expect(stops[1]).not.toHaveBeenCalled();
  await waitFor(() => expect(select.value).toBe("dock"));
  expect(screen.getByRole("button", { name: "Take photo" })).toBeTruthy();
});

test("grabbing needs a canvas the browser can draw on", async () => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  const video = document.createElement("video");
  Object.defineProperty(video, "videoWidth", { value: 640 });
  Object.defineProperty(video, "videoHeight", { value: 480 });
  await expect(grabFrame(video)).rejects.toThrow("The picture could not be taken.");
});

test("a grabbed picture is a JPEG at the video's size", async () => {
  const drawImage = vi.fn();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage } as never);
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(function (this: HTMLCanvasElement, done, type) {
    expect(type).toBe("image/jpeg");
    done(new Blob(["x"]));
  });
  const video = document.createElement("video");
  Object.defineProperty(video, "videoWidth", { value: 1920 });
  Object.defineProperty(video, "videoHeight", { value: 1080 });
  const grabbed = await grabFrame(video);
  expect([grabbed.width, grabbed.height]).toEqual([1920, 1080]);
  expect(drawImage).toHaveBeenCalledWith(video, 0, 0, 1920, 1080);
});

test("before the camera is allowed, the browser's default opens, with no size asked for, then raised", async () => {
  const { getUserMedia, applyConstraints } = camera("ok", [{ kind: "videoinput", deviceId: "", label: "" }]);
  server(Response.json(PHOTO));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  await screen.findByRole("button", { name: "Take photo" });
  expect(getUserMedia).toHaveBeenCalledWith({ video: true, audio: false });
  expect(applyConstraints).toHaveBeenCalledWith({ width: { ideal: 1920 }, height: { ideal: 1080 } });
});

test("once allowed, a real camera is opened by its id, not a virtual one listed first (Larry's LG laptop)", async () => {
  const { getUserMedia } = camera("ok", [
    { kind: "videoinput", deviceId: "mmx", label: "Mirametrix Virtual Camera" },
    { kind: "videoinput", deviceId: "lge", label: "LGE Camera (30c9:0084)" },
  ]);
  server(Response.json(PHOTO));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  await screen.findByRole("button", { name: "Take photo" });
  expect(getUserMedia).toHaveBeenCalledTimes(1);
  expect(getUserMedia).toHaveBeenCalledWith({ video: { deviceId: { exact: "lge" } }, audio: false });
});

test("a camera that won't start gives way to the next one", async () => {
  const devices = [
    { kind: "videoinput", deviceId: "lge", label: "LGE Camera" },
    { kind: "videoinput", deviceId: "usb", label: "USB Webcam" },
  ];
  const { getUserMedia } = camera("ok", devices);
  const works = getUserMedia.getMockImplementation()!;
  getUserMedia.mockImplementation(async (asked: MediaStreamConstraints) => {
    if (JSON.stringify(asked).includes('"lge"')) throw Object.assign(new Error("Timeout starting video source"), { name: "AbortError" });
    return works(asked);
  });
  vi.spyOn(console, "warn").mockImplementation(() => {});
  server(Response.json(PHOTO));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  expect(await screen.findByRole("button", { name: "Take photo" })).toBeTruthy();
  expect(getUserMedia).toHaveBeenLastCalledWith({ video: { deviceId: { exact: "usb" } }, audio: false });
});

test("when no camera starts, the step says why", async () => {
  const { getUserMedia } = camera("AbortError");
  vi.spyOn(console, "warn").mockImplementation(() => {});
  server(Response.json(PHOTO));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  expect(await screen.findByText(WHY_NOT.failed, { exact: false })).toBeTruthy();
  expect(getUserMedia).toHaveBeenCalledTimes(2); // the first, then the other one
});

test("with two cameras, another can be chosen, and a real one chosen is opened first next time", async () => {
  const devices = [
    { kind: "videoinput", deviceId: "laptop", label: "Integrated Camera" },
    { kind: "videoinput", deviceId: "usb", label: "HD Webcam" },
  ];
  const { getUserMedia } = camera("ok", devices);
  server(Response.json(PHOTO));
  const { unmount } = render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  const select = (await screen.findByRole("combobox")) as HTMLSelectElement;
  expect([...select.options].map((o) => o.textContent)).toEqual(["Integrated Camera", "HD Webcam"]);
  expect(select.value).toBe("laptop");
  fireEvent.change(select, { target: { value: "usb" } });
  await waitFor(() => expect(getUserMedia).toHaveBeenLastCalledWith({ video: { deviceId: { exact: "usb" } }, audio: false }));
  unmount();
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  await screen.findByRole("button", { name: "Take photo" });
  expect(getUserMedia).toHaveBeenLastCalledWith({ video: { deviceId: { exact: "usb" } }, audio: false });
});

test("a virtual camera chosen last time isn't reopened when a real one is there", async () => {
  localStorage.setItem("imageskin.camera", "obs");
  const { getUserMedia } = camera();
  server(Response.json(PHOTO));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  await screen.findByRole("button", { name: "Take photo" });
  expect(getUserMedia).toHaveBeenCalledWith({ video: { deviceId: { exact: "laptop" } }, audio: false });
});

test("with one camera, there is nothing to choose", async () => {
  camera("ok", CAMERAS.slice(0, 1));
  server(Response.json(PHOTO));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  await screen.findByRole("button", { name: "Take photo" });
  await waitFor(() => expect(console.info).toHaveBeenCalledWith("Cameras: Integrated Camera"));
  expect(screen.queryByRole("combobox")).toBeNull();
});

test("a camera that keeps its own size is still used", async () => {
  const { applyConstraints } = camera();
  applyConstraints.mockRejectedValue(new Error("OverconstrainedError"));
  vi.spyOn(console, "warn").mockImplementation(() => {});
  server(Response.json(PHOTO));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  expect(await screen.findByRole("button", { name: "Take photo" })).toBeTruthy();
});

test("a camera sending no picture says so, instead of failing silently", async () => {
  await expect(grabFrame(document.createElement("video"))).rejects.toThrow(NO_PICTURE);
});

test("an infrared or virtual camera gives way to one that can take the photo", () => {
  const cams = (...labels: string[]) => labels.map((label, i) => ({ id: String(i), label }));
  expect(betterCamera(cams("Integrated IR Camera", "Integrated Camera"), "0")?.label).toBe("Integrated Camera");
  expect(betterCamera(cams("OBS Virtual Camera", "HD Webcam"), "0")?.label).toBe("HD Webcam");
  expect(betterCamera(cams("Integrated Camera", "OBS Virtual Camera"), "0")).toBeNull();
  expect(betterCamera(cams("Integrated IR Camera"), "0")).toBeNull(); // nothing better
  expect(betterCamera(cams("Integrated IR Camera", "Integrated Camera"), null)).toBeNull();
});

test("opened on the infrared camera by default, it switches to the laptop's own, without remembering it", async () => {
  // Before the camera is allowed no names can be read, so the browser's first opens.
  const devices = [
    { kind: "videoinput", deviceId: "ir", label: "Integrated IR Camera" },
    { kind: "videoinput", deviceId: "rgb", label: "Integrated Camera" },
  ];
  const { getUserMedia } = camera("ok", devices);
  const enumerate = navigator.mediaDevices.enumerateDevices as ReturnType<typeof vi.fn>;
  enumerate.mockResolvedValueOnce([]); // not allowed yet
  server(Response.json(PHOTO));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  await waitFor(() => expect(getUserMedia).toHaveBeenLastCalledWith({ video: { deviceId: { exact: "rgb" } }, audio: false }));
  expect(getUserMedia).toHaveBeenNthCalledWith(1, { video: true, audio: false });
  await waitFor(() => expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("rgb"));
  expect(localStorage.getItem("imageskin.camera")).toBeNull();
});

test("a camera picked in the list is kept, even an infrared one", async () => {
  const { getUserMedia } = camera("ok", [
    { kind: "videoinput", deviceId: "rgb", label: "Integrated Camera" },
    { kind: "videoinput", deviceId: "ir", label: "Integrated IR Camera" },
  ]);
  server(Response.json(PHOTO));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  fireEvent.change(await screen.findByRole("combobox"), { target: { value: "ir" } });
  await waitFor(() => expect(getUserMedia).toHaveBeenLastCalledWith({ video: { deviceId: { exact: "ir" } }, audio: false }));
  await screen.findByRole("button", { name: "Take photo" });
  expect(getUserMedia).toHaveBeenCalledTimes(2); // no switch back
});

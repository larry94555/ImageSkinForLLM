import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CameraPhoto, cameraBlocked, grabFrame, NO_PICTURE, reasonOf, WHY_NOT } from "./camera";

const PHOTO = { id: "p1", kind: "photos", name: "camera.jpg", format: "jpg", size: 9, uploaded_at: "", seconds: null, score: 81, speech: null };

// The server: what each photo upload answers, and the camera reports it was sent.
function server(upload: Response | (() => Response)) {
  const reports: unknown[] = [];
  const uploads: File[] = [];
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
      return new Response("", { status: 404 });
    }),
  );
  return { reports, uploads };
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
    const video = asked.video as { deviceId?: { ideal: string } } | true;
    const id = video === true ? "laptop" : (video.deviceId?.ideal ?? "laptop");
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

test("a photo that fails its checks shows why, with Retake", async () => {
  camera();
  server(Response.json({ ...PHOTO, problems: ["The photo is too dark."] }));
  const onAdded = vi.fn();
  render(<CameraPhoto onAdded={onAdded} onChanging={() => {}} grab={grab} />);
  await takePhoto();
  expect(await screen.findByText("The photo is too dark.")).toBeTruthy();
  expect(screen.queryByText(/Kept\./)).toBeNull();
  expect(screen.getByRole("button", { name: "Retake" })).toBeTruthy();
  expect(onAdded).toHaveBeenCalled(); // stored, so the list shows it with its problem
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
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: () => new Promise<MediaStream>((r) => (allow = r)) },
    configurable: true,
  });
  server(Response.json(PHOTO));
  const { unmount } = render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  unmount();
  await act(async () => allow({ getTracks: () => [{ stop }] } as unknown as MediaStream));
  expect(stop).toHaveBeenCalled();
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

test("the browser's default camera opens, with no size asked for, then is raised to full size", async () => {
  const { getUserMedia, applyConstraints } = camera();
  server(Response.json(PHOTO));
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  await screen.findByRole("button", { name: "Take photo" });
  expect(getUserMedia).toHaveBeenCalledWith({ video: true, audio: false });
  expect(applyConstraints).toHaveBeenCalledWith({ width: { ideal: 1920 }, height: { ideal: 1080 } });
});

test("with two cameras, another can be chosen, and is opened first next time", async () => {
  const { getUserMedia } = camera();
  server(Response.json(PHOTO));
  const { unmount } = render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  const select = (await screen.findByRole("combobox")) as HTMLSelectElement;
  expect([...select.options].map((o) => o.textContent)).toEqual(["Integrated Camera", "OBS Virtual Camera"]);
  expect(select.value).toBe("laptop");
  fireEvent.change(select, { target: { value: "obs" } });
  await waitFor(() => expect(getUserMedia).toHaveBeenLastCalledWith({ video: { deviceId: { ideal: "obs" } }, audio: false }));
  unmount();
  render(<CameraPhoto onAdded={() => {}} onChanging={() => {}} grab={grab} />);
  await screen.findByRole("button", { name: "Take photo" });
  expect(getUserMedia).toHaveBeenLastCalledWith({ video: { deviceId: { ideal: "obs" } }, audio: false });
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

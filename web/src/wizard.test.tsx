import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { nextStep, WizardPage } from "./wizard";

const PHOTO_ID = "a".repeat(32);
const FINISHED = "2026-10-29T20:00:00Z";

// A server for the wizard: the step reached, the photo chosen (or none), the prepare job's state
// and the review. `saved` collects each step the wizard saves.
function server(opts: {
  step?: string;
  photo?: string | null;
  prepare?: string;
  stepFails?: boolean;
  consentFails?: boolean;
  saveGate?: Promise<void>; // step saves wait for it
  chosenGate?: Promise<void>; // reads of the chosen photo after the first wait for it
}) {
  let chosenReads = 0;
  let photo = opts.photo ?? null;
  const saved: string[] = [];
  const reviews: string[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url === "/api/wizard" && method === "GET") {
      if (opts.stepFails) return new Response("", { status: 500 });
      return Response.json({ step: opts.step ?? "start" });
    }
    if (url === "/api/wizard" && method === "PUT") {
      if (opts.stepFails) return Response.json({ detail: "The step could not be saved." }, { status: 500 });
      const { step } = JSON.parse(init!.body as string) as { step: string };
      saved.push(step);
      await opts.saveGate;
      return Response.json({ step });
    }
    if (url === "/api/consent") {
      if (opts.consentFails) return new Response("", { status: 500 });
      return Response.json({ agreed: true, agreed_at: FINISHED });
    }
    if (url === "/api/uploads/photos" && method === "POST") {
      return Response.json({ detail: "The photo is too blurry." }, { status: 400 });
    }
    if (url === "/api/uploads/photos") {
      return Response.json(photo ? [{ id: photo, kind: "photos", name: "me.jpg", format: "jpg", size: 1, uploaded_at: FINISHED, seconds: null, problems: [], score: 90 }] : []);
    }
    if (url === "/api/uploads/sounds") return Response.json([]);
    if (url === `/api/uploads/photos/${PHOTO_ID}` && method === "DELETE") {
      photo = null;
      return Response.json({});
    }
    if (url === "/api/uploads/photos/chosen") {
      if (chosenReads++ > 0) await opts.chosenGate;
      return Response.json({ id: photo, chosen_by: "app" });
    }
    if (url === "/api/voice-sample") {
      return Response.json({ recordings: 0, speech: 0, problem: "No recordings yet." });
    }
    if (url === "/api/accent") return Response.json({ accent: "own", available: true });
    if (url === "/api/prepare") {
      return Response.json({
        state: opts.prepare ?? "idle",
        photo_id: PHOTO_ID,
        percent: 100,
        steps: null,
        error: null,
        finished_at: FINISHED,
      });
    }
    if (url === "/api/review" && method === "POST") {
      reviews.push((JSON.parse(init!.body as string) as { decision: string }).decision);
      return Response.json({ accepted: false, accepted_at: null });
    }
    if (url === "/api/review") return Response.json({ accepted: false, accepted_at: null });
    return new Response("", { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, saved, reviews };
}

function next() {
  return screen.getByRole("button", { name: "Next" }) as HTMLButtonElement;
}

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  vi.spyOn(console, "info").mockImplementation(() => {});
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("next and back stay within the steps", () => {
  expect(nextStep("start", 1)).toBe("photo");
  expect(nextStep("photo", -1)).toBe("start");
  expect(nextStep("start", -1)).toBe("start");
  expect(nextStep("review", 1)).toBe("review");
});

test("the first step asks for consent, and Next waits for it", async () => {
  const { saved } = server({});
  const onConsented = vi.fn();
  const { rerender } = render(<WizardPage consented={false} onConsented={onConsented} />);
  expect(await screen.findByText("You will need:")).toBeTruthy();
  expect(screen.getByText("Step 1 of 6")).toBeTruthy();
  expect(next().disabled).toBe(true);
  expect((screen.getByRole("button", { name: "Back" }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("checkbox"));
  await waitFor(() => expect(onConsented).toHaveBeenCalled());
  rerender(<WizardPage consented onConsented={onConsented} />);
  await waitFor(() => expect(next().disabled).toBe(false));
  fireEvent.click(next());
  expect(await screen.findByText("Add a photo file")).toBeTruthy();
  expect(saved).toEqual(["photo"]);
  expect(console.info).toHaveBeenCalledWith(expect.stringMatching(/^Wizard step: photo \(\d+ s on start\)$/));
});

test("consent that can't be saved says so and leaves the box unticked", async () => {
  server({ consentFails: true });
  const onConsented = vi.fn();
  render(<WizardPage consented={false} onConsented={onConsented} />);
  await screen.findByText("You will need:");
  fireEvent.click(screen.getByRole("checkbox"));
  expect(await screen.findByText("Could not save your answer. Please try again.")).toBeTruthy();
  expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(false);
  expect(onConsented).not.toHaveBeenCalled();
});

test("before consent, a saved step is not opened", async () => {
  server({ step: "accent" });
  render(<WizardPage consented={false} onConsented={() => {}} />);
  expect(await screen.findByText("You will need:")).toBeTruthy();
});

test("the photo step, without a camera, says why and waits for a photo that passed its checks", async () => {
  server({ step: "photo", photo: null });
  render(<WizardPage consented onConsented={() => {}} />);
  expect(await screen.findByText("Add a photo file")).toBeTruthy();
  expect(await screen.findByText("The camera can't be used.")).toBeTruthy();
  expect(next().disabled).toBe(true);
});

test("with a photo chosen, the photo step's Next is ready", async () => {
  server({ step: "photo", photo: PHOTO_ID });
  render(<WizardPage consented onConsented={() => {}} />);
  await waitFor(() => expect(next().disabled).toBe(false));
});

test("the voice step offers the recorder, with the script to read, and is optional", async () => {
  const { saved } = server({ step: "voice" });
  render(<WizardPage consented onConsented={() => {}} />);
  expect(await screen.findByText("Recording 1 of 3: Voice 1")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Start recording" })).toBeTruthy();
  expect(await screen.findByText("Add a recording file")).toBeTruthy();
  await waitFor(() => expect(next().disabled).toBe(false));
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByText("Add a photo file")).toBeTruthy();
  expect(saved).toEqual(["photo"]);
});

test("the accent step opens at its choices, unnumbered", async () => {
  server({ step: "accent" });
  render(<WizardPage consented onConsented={() => {}} />);
  expect(await screen.findByText("Speak with")).toBeTruthy();
  expect(screen.queryByText("Step 3 of 4")).toBeNull();
  await waitFor(() => expect(next().disabled).toBe(false));
});

test("Next on Prepare waits until the video is prepared", async () => {
  server({ step: "prepare", prepare: "idle" });
  render(<WizardPage consented onConsented={() => {}} />);
  expect(await screen.findByRole("button", { name: "Prepare Video" })).toBeTruthy();
  expect(next().disabled).toBe(true);
});

test("once prepared, Next opens the sample video on a step of its own", async () => {
  const { saved } = server({ step: "prepare", prepare: "done" });
  render(<WizardPage consented onConsented={() => {}} />);
  expect(await screen.findByText("Done. Click Next to watch the sample video.")).toBeTruthy();
  expect(screen.queryByLabelText("Sample video")).toBeNull();
  await waitFor(() => expect(next().disabled).toBe(false));
  fireEvent.click(next());
  expect(await screen.findByLabelText("Sample video")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Next" })).toBeNull(); // the last step
  expect(saved).toEqual(["review"]);
});

test("rejecting the voice in the review goes back to the voice step", async () => {
  const { saved, reviews } = server({ step: "review", prepare: "done" });
  render(<WizardPage consented onConsented={() => {}} />);
  fireEvent.click(await screen.findByRole("button", { name: "Reject voice" }));
  expect(await screen.findByText(/You rejected the voice/)).toBeTruthy();
  expect(reviews).toEqual(["reject-voice"]);
  expect(saved).toEqual(["voice"]);
});

test("a review with no sample video says to go back and prepare it", async () => {
  server({ step: "review", prepare: "idle" });
  render(<WizardPage consented onConsented={() => {}} />);
  expect(await screen.findByText("The sample video isn't ready. Go Back to prepare it.")).toBeTruthy();
});

test("a step that can't be read or saved still lets the wizard go on", async () => {
  server({ stepFails: true });
  render(<WizardPage consented onConsented={() => {}} />);
  expect(await screen.findByText("You will need:")).toBeTruthy();
  await waitFor(() => expect(next().disabled).toBe(false));
  fireEvent.click(next());
  expect(await screen.findByText("Add a photo file")).toBeTruthy();
  expect(console.error).toHaveBeenCalledWith("Could not save the wizard's step (photo)", expect.any(Error));
});

test("removing the chosen photo turns Next off at once, before the choice is read again", async () => {
  let release = () => {};
  const chosenGate = new Promise<void>((r) => (release = r));
  server({ step: "photo", photo: PHOTO_ID, chosenGate });
  render(<WizardPage consented onConsented={() => {}} />);
  await waitFor(() => expect(next().disabled).toBe(false));
  fireEvent.click(await screen.findByRole("button", { name: "Remove" }));
  fireEvent.click(await screen.findByRole("button", { name: "Yes, remove it" }));
  await waitFor(() => expect(next().disabled).toBe(true));
  release();
  await screen.findByText("None yet.");
  expect(next().disabled).toBe(true);
});

test("a double click on Next moves one step, saved once, with Back and Next off meanwhile", async () => {
  let release = () => {};
  const saveGate = new Promise<void>((r) => (release = r));
  const { saved } = server({ step: "voice", saveGate });
  render(<WizardPage consented onConsented={() => {}} />);
  await waitFor(() => expect(next().disabled).toBe(false));
  fireEvent.click(next());
  fireEvent.click(next());
  await waitFor(() => expect(next().disabled).toBe(true));
  expect((screen.getByRole("button", { name: "Back" }) as HTMLButtonElement).disabled).toBe(true);
  release();
  expect(await screen.findByText("Speak with", { exact: true })).toBeTruthy();
  expect(saved).toEqual(["accent"]);
});

test("a photo refused on upload leaves Next on for the photo already chosen", async () => {
  server({ step: "photo", photo: PHOTO_ID });
  render(<WizardPage consented onConsented={() => {}} />);
  await waitFor(() => expect(next().disabled).toBe(false));
  const input = document.querySelector("input[type=file]") as HTMLInputElement;
  const file = new File(["x"], "blurry.jpg", { type: "image/jpeg" });
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  fireEvent.change(input);
  expect(await screen.findByText("blurry.jpg: The photo is too blurry.")).toBeTruthy();
  await waitFor(() => expect(next().disabled).toBe(false));
});

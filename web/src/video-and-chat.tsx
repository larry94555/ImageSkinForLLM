// Run the video test again and Clear conversation, on the Settings page (roadmap R27b).

import { useState } from "preact/hooks";

import { clearChat, runVideoTestAgain, ServerRefusal } from "./api";
import { useConfirm } from "./confirm-dialog";

export const CONFIRM_CLEAR = "Clear the whole conversation?";

// What went wrong, in the server's words when it gave a reason.
function reason(e: unknown, fallback: string): string {
  return e instanceof ServerRefusal ? e.message : fallback;
}

export function VideoAndChat() {
  const [running, setRunning] = useState(false);
  const [video, setVideo] = useState<string | null>(null); // the sample just made, to play
  const [testFailed, setTestFailed] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);
  const [cleared, setCleared] = useState(false);
  const [clearFailed, setClearFailed] = useState<string | null>(null);
  const { ask, dialog } = useConfirm();

  async function runAgain() {
    setRunning(true);
    setVideo(null);
    setTestFailed(null);
    const started = performance.now();
    try {
      const url = await runVideoTestAgain();
      console.info(
        `Video test run again (${Math.round(performance.now() - started)} ms)`,
      );
      setVideo(`${url}?made=${Date.now()}`); // a new address, so the browser doesn't play the old
    } catch (e) {
      console.error("Could not run the video test again", e);
      setTestFailed(reason(e, "The video could not be made. Try again."));
    }
    setRunning(false);
  }

  async function clear() {
    const yes = await ask({
      title: CONFIRM_CLEAR,
      children: <p className="warning">This can't be undone.</p>,
      keepLabel: "No, keep it",
      confirmLabel: "Yes, clear it",
    });
    if (!yes) {
      console.info("Clear conversation cancelled");
      return;
    }
    setClearing(true);
    setCleared(false);
    setClearFailed(null);
    const started = performance.now();
    try {
      const turns = await clearChat();
      const took = Math.round(performance.now() - started);
      console.info(`Conversation cleared: ${turns} turn(s) (${took} ms)`);
      setCleared(true);
    } catch (e) {
      console.error("Could not clear the conversation", e);
      setClearFailed(
        reason(e, "The conversation could not be cleared. Try again."),
      );
    }
    setClearing(false);
  }

  return (
    <section className="panel" aria-labelledby="settings-video-chat">
      <h2 id="settings-video-chat">Video and conversation</h2>
      <div className="switch">
        <button
          type="button"
          className="use"
          disabled={running}
          onClick={runAgain}
        >
          Run the video test again
        </button>
        <p className="muted">
          Makes the sample video again from the photo and voice, and plays it.
        </p>
        {running && (
          <p className="muted busy">
            Making the sample video. This can take a few minutes…
          </p>
        )}
        {testFailed && <p className="error">{testFailed}</p>}
        {video && (
          <div className="sample-video">
            <video
              src={video}
              controls
              autoPlay
              playsInline
              aria-label="Sample video"
            />
          </div>
        )}
      </div>
      <div className="switch">
        <button
          type="button"
          className="use"
          disabled={clearing}
          onClick={clear}
        >
          Clear conversation
        </button>
        <p className="muted">
          Removes every question and answer from the chat. It asks first.
        </p>
        {cleared && <p className="muted">The conversation was cleared.</p>}
        {clearFailed && <p className="error">{clearFailed}</p>}
      </div>
      {dialog}
    </section>
  );
}

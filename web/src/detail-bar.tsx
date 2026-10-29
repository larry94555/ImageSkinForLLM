// The Level of detail bar on the chat screen (roadmap R180): from High level, brief answers with
// only the main points, to In depth, longer and more complete ones. It is saved like the other
// settings, and the server asks the next answer at it, with no restart.

import { useContext, useRef, useState } from "preact/hooks";

import { DETAIL_LEVELS } from "./api";
import { SettingsContext } from "./settings";

export function DetailBar() {
  const { settings, change } = useContext(SettingsContext);
  const [failed, setFailed] = useState(false);
  // Shown at once, and put back if the server doesn't save it.
  const [picked, setPicked] = useState<number | null>(null);
  const shown = picked ?? settings.detail;
  // Saved one at a time, and only the last level picked (review on PR #221): moved quickly,
  // a save that answered late put the bar, and the next answer, back on an earlier level.
  const latest = useRef<number | null>(null);
  const saving = useRef<Promise<void>>(Promise.resolve());

  function choose(detail: number) {
    setFailed(false);
    setPicked(detail);
    latest.current = detail;
    saving.current = saving.current.then(async () => {
      if (latest.current !== detail) return; // a later level was picked meanwhile
      try {
        await change({ detail });
        console.info(`Level of detail set to ${detail}`);
      } catch (e) {
        console.error(`Could not set the level of detail to ${detail}`, e);
        setFailed(true);
      }
      if (latest.current === detail) setPicked(null);
    });
  }

  return (
    <div className="detail-bar">
      <label>
        <span>Level of detail</span>
        <span className="detail-poles">
          <span className="muted">High level</span>
          <input
            type="range"
            min={1}
            max={DETAIL_LEVELS}
            step={1}
            value={shown}
            aria-valuetext={`${shown} of ${DETAIL_LEVELS}`}
            onChange={(e) => choose(Number(e.currentTarget.value))}
          />
          <span className="muted">In depth</span>
        </span>
      </label>
      {failed && <p className="error">The level of detail could not be changed. Try again.</p>}
    </div>
  );
}

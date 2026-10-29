// The Level of detail bar on the chat screen (roadmap R180): from High level, brief answers with
// only the main points, to In depth, longer and more complete ones. It is saved like the other
// settings, and the server asks the next answer at it, with no restart.

import { useContext, useState } from "preact/hooks";

import { DETAIL_LEVELS } from "./api";
import { SettingsContext } from "./settings";

export function DetailBar() {
  const { settings, change } = useContext(SettingsContext);
  const [failed, setFailed] = useState(false);
  // Shown at once, and put back if the server doesn't save it.
  const [picked, setPicked] = useState<number | null>(null);
  const shown = picked ?? settings.detail;

  async function choose(detail: number) {
    setFailed(false);
    setPicked(detail);
    try {
      await change({ detail });
      console.info(`Level of detail set to ${detail}`);
    } catch (e) {
      console.error(`Could not set the level of detail to ${detail}`, e);
      setFailed(true);
    }
    setPicked(null);
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
            onChange={(e) => void choose(Number(e.currentTarget.value))}
          />
          <span className="muted">In depth</span>
        </span>
      </label>
      {failed && <p className="error">The level of detail could not be changed. Try again.</p>}
    </div>
  );
}

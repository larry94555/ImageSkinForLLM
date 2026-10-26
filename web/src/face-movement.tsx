// How much the cheeks and the face around the mouth move with it while the person speaks
// (roadmap R128a). It is on the Setup page beside Prepare, since the sample video and the
// prepared clips are made with it, so a change shows after preparing again (Larry, 2026-10-26).

import { useContext, useState } from "preact/hooks";

import type { FaceMovement } from "./api";
import { SettingsContext } from "./settings";

// Weakest first.
const CHOICES: [FaceMovement, string][] = [
  ["off", "Off"],
  ["slight", "Slight"],
  ["normal", "Normal"],
];

// `onChanged` once a new one is saved: a finished prepare made with another is no longer current
// (review on PR #174), so the page reads the prepare job again. While `disabled` (preparing),
// it can't be changed: the clips are being made with the one chosen when it started.
export function FaceMovementChoice(props: {
  onChanged?: () => void;
  disabled?: boolean;
}) {
  const { settings, change } = useContext(SettingsContext);
  const [failed, setFailed] = useState(false);
  // Shown at once, and put back if the server doesn't save it.
  const [picked, setPicked] = useState<FaceMovement | null>(null);
  const shown = picked ?? settings.face_movement;

  async function choose(face_movement: FaceMovement) {
    setFailed(false);
    setPicked(face_movement);
    try {
      await change({ face_movement });
      props.onChanged?.();
    } catch (e) {
      console.error(
        `Could not change the face movement to ${face_movement}`,
        e,
      );
      setFailed(true);
    }
    setPicked(null);
  }

  return (
    <fieldset className="face-movement">
      <legend>Face movement while speaking</legend>
      <p className="muted">
        How much the cheeks and the face around the mouth move with it. Off
        moves only the lips and jaw. After changing it, Prepare again to see it.
      </p>
      {CHOICES.map(([value, label]) => (
        <label key={value} className="choice">
          <input
            type="radio"
            name="face_movement"
            value={value}
            checked={shown === value}
            disabled={props.disabled}
            onChange={() => void choose(value)}
          />{" "}
          <span>{label}</span>
        </label>
      ))}
      {failed && (
        <p className="error">
          The face movement could not be changed. Try again.
        </p>
      )}
    </fieldset>
  );
}

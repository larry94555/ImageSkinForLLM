// A setting changed while a prepare is stopped part-way (roadmap R159) means preparing over
// again instead of resuming, so the change is confirmed first (Larry, 2026-10-26).

import { createContext } from "preact";
import { useContext, useRef, useState } from "preact/hooks";

import { discardPrepare } from "./api";
import { useConfirm } from "./confirm-dialog";

interface Guard {
  // Whether a change needs confirming now: a prepare is stopped part-way.
  needed: () => boolean;
  // Asks, under `title`, whether to change the setting; true to go ahead (always, when not
  // needed). Once confirmed, the stopped prepare is dropped.
  confirm: (title?: string) => Promise<boolean>;
}

export const SettingGuard = createContext<Guard>({
  needed: () => false,
  confirm: async () => true,
});

export function useSettingGuard() {
  return useContext(SettingGuard);
}

export const RESTART_WARNING = "Changing a setting will require restarting the preparation over again.";

// For a page with Prepare on it: `guard` goes in SettingGuard, `onStopped` to PrepareSection,
// and `dialog` somewhere on the page. `onDiscarded` once a stopped prepare was dropped, so the
// page reads the prepare job again. If the stopped prepare can't be dropped, the setting is
// not changed and `dialog` says so: Resume Preparation would otherwise carry on with the old
// setting (Codex's review of PR #191).
export function usePrepareStopGuard(onDiscarded: () => void) {
  const stopped = useRef(false);
  const { ask, dialog } = useConfirm();
  const [failed, setFailed] = useState<string | null>(null);

  async function confirm(title = "Change this setting?") {
    if (!stopped.current) return true;
    setFailed(null);
    const yes = await ask({
      title,
      children: <p>{RESTART_WARNING}</p>,
      keepLabel: "Cancel change",
      confirmLabel: "Confirm change",
    });
    if (!yes) return false;
    const started = performance.now();
    try {
      await discardPrepare();
      console.info(`Stopped prepare dropped for a setting change (${Math.round(performance.now() - started)} ms)`);
    } catch (e) {
      console.error("Could not drop the stopped prepare; the setting is left as it was", e);
      setFailed(
        `The setting was not changed: the stopped preparation could not be cleared (${(e as Error).message}). Try again.`,
      );
      return false;
    }
    stopped.current = false;
    onDiscarded();
    return true;
  }

  const guard: Guard = { needed: () => stopped.current, confirm };
  const shown = (
    <>
      {failed && (
        <p className="error" role="alert">
          {failed}
        </p>
      )}
      {dialog}
    </>
  );
  return { guard, onStopped: (now: boolean) => (stopped.current = now), dialog: shown };
}

// The app's own confirmation box, used instead of the browser's confirm() (Larry, 2026-10-20:
// the browser's box looks unprofessional). First made for Delete my data (roadmap R31).

import type { ComponentChildren } from "preact";
import { useEffect, useId, useRef, useState } from "preact/hooks";

interface Props {
  title: string;
  children?: ComponentChildren;
  keepLabel: string; // backs out
  confirmLabel: string; // goes ahead
  otherLabel?: string; // a third choice between the two, such as Stop after this part (R159)
  onCancel: () => void;
  onConfirm: () => void;
  onOther?: () => void;
}

// What Tab can reach inside the box.
const FOCUSABLE = "button, a[href], input, select, textarea, [tabindex]:not([tabindex='-1'])";

// The box over a dimmed page. The back-out button has the focus, so Enter backs out; Escape and
// a click outside the box back out too. Like the browser's confirm(), nothing behind it can be
// used while it is open: Tab and Shift+Tab go round its own buttons, and focus that lands
// behind it is brought back. It then gives the focus back to what had it, such as the Remove
// button (a review on PR #121).
export function ConfirmDialog(props: Props) {
  const { onCancel } = props;
  const keep = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const id = useId();
  // The latest onCancel, so a page that re-renders (Manage Content checks its PDFs every second)
  // doesn't take the focus back to the button each time.
  const cancel = useRef(onCancel);
  cancel.current = onCancel;

  useEffect(() => {
    const opener = document.activeElement;
    keep.current?.focus();
    const inside = (el: EventTarget | null) => el instanceof Node && !!box.current?.contains(el);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        cancel.current();
        return;
      }
      if (e.key !== "Tab" || !box.current) return;
      const items = Array.from(box.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      const first = items[0];
      const last = items[items.length - 1];
      const at = document.activeElement;
      if (!inside(at) || at === (e.shiftKey ? first : last)) {
        e.preventDefault();
        (e.shiftKey ? last : first).focus();
      }
    };
    const onFocus = (e: FocusEvent) => {
      if (!inside(e.target)) keep.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("focusin", onFocus);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("focusin", onFocus);
      // Unless it went with the answer, as a removed PDF's Remove button does.
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);

  return (
    <div className="confirm-backdrop" onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div
        className="confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        ref={box}
        aria-labelledby={`${id}-title`}
        aria-describedby={props.children ? `${id}-about` : undefined}
      >
        <h2 id={`${id}-title`}>{props.title}</h2>
        {props.children && <div id={`${id}-about`}>{props.children}</div>}
        <div className="confirm-buttons">
          <button type="button" className="secondary" ref={keep} onClick={onCancel}>
            {props.keepLabel}
          </button>
          {props.otherLabel && (
            <button type="button" className="secondary" onClick={props.onOther}>
              {props.otherLabel}
            </button>
          )}
          <button type="button" className="danger" onClick={props.onConfirm}>
            {props.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export type Question = Omit<Props, "onCancel" | "onConfirm" | "onOther">;
export type Answer = "cancel" | "other" | "confirm";

// For a click handler that asks first: `if (!(await ask({...}))) return;`, or `choose` for a
// question with a third choice (`otherLabel`). Render `dialog` somewhere in the component; it is
// null until something is asked.
export function useConfirm() {
  const [asking, setAsking] = useState<{
    question: Question;
    answer: (answer: Answer) => void;
  } | null>(null);

  function choose(question: Question): Promise<Answer> {
    return new Promise((resolve) => {
      setAsking({
        question,
        answer: (answer) => {
          const said = { cancel: "cancelled", other: question.otherLabel, confirm: "confirmed" };
          console.info(`${question.title} ${said[answer]}`);
          setAsking(null);
          resolve(answer);
        },
      });
    });
  }

  async function ask(question: Question): Promise<boolean> {
    return (await choose(question)) === "confirm";
  }

  const dialog = asking && (
    <ConfirmDialog
      {...asking.question}
      onCancel={() => asking.answer("cancel")}
      onConfirm={() => asking.answer("confirm")}
      onOther={() => asking.answer("other")}
    />
  );
  return { ask, choose, dialog };
}

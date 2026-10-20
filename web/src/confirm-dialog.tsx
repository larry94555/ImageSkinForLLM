// The app's own confirmation box, used instead of the browser's confirm() (Larry, 2026-10-20:
// the browser's box looks unprofessional). First made for Delete my data (roadmap R31).

import type { ComponentChildren } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";

interface Props {
  title: string;
  children?: ComponentChildren;
  keepLabel: string; // backs out
  confirmLabel: string; // goes ahead
  onCancel: () => void;
  onConfirm: () => void;
}

// The box over a dimmed page. The back-out button has the focus, so Enter backs out; Escape and
// a click outside the box back out too.
export function ConfirmDialog(props: Props) {
  const { onCancel } = props;
  const keep = useRef<HTMLButtonElement>(null);
  // The latest onCancel, so a page that re-renders (Manage Content checks its PDFs every second)
  // doesn't take the focus back to the button each time.
  const cancel = useRef(onCancel);
  cancel.current = onCancel;

  useEffect(() => {
    keep.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") cancel.current();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div
      className="confirm-backdrop"
      onClick={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div
        className="confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby={props.children ? "confirm-about" : undefined}
      >
        <h2 id="confirm-title">{props.title}</h2>
        {props.children && <div id="confirm-about">{props.children}</div>}
        <div className="confirm-buttons">
          <button
            type="button"
            className="secondary"
            ref={keep}
            onClick={onCancel}
          >
            {props.keepLabel}
          </button>
          <button type="button" className="danger" onClick={props.onConfirm}>
            {props.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export type Question = Omit<Props, "onCancel" | "onConfirm">;

// For a click handler that asks first: `if (!(await ask({...}))) return;`. Render `dialog`
// somewhere in the component; it is null until something is asked.
export function useConfirm() {
  const [asking, setAsking] = useState<{
    question: Question;
    answer: (yes: boolean) => void;
  } | null>(null);

  function ask(question: Question): Promise<boolean> {
    return new Promise((resolve) => {
      setAsking({
        question,
        answer: (yes) => {
          console.info(`${question.title} ${yes ? "confirmed" : "cancelled"}`);
          setAsking(null);
          resolve(yes);
        },
      });
    });
  }

  const dialog = asking && (
    <ConfirmDialog
      {...asking.question}
      onCancel={() => asking.answer(false)}
      onConfirm={() => asking.answer(true)}
    />
  );
  return { ask, dialog };
}

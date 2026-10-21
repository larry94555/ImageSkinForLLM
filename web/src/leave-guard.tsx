// Leaving setup with a sample video neither accepted nor rejected (Larry's test of PR #131): a
// change takes effect only once its sample is accepted, so the app asks first. Proceed leaves
// with nothing changed; Cancel stays, to accept or reject the sample.

import { useEffect, useRef } from "preact/hooks";

import { useConfirm } from "./confirm-dialog";
import { pageFor } from "./router";

export const LEAVE_TITLE = "Your change isn't accepted yet";
export const LEAVE_PROCEED = "Proceed without the change";
export const LEAVE_CANCEL = "Cancel";

// While `pending`, a click on a link to another page asks first, and closing or reloading the
// tab gets the browser's own warning. `unchanged` says what stays as it is, such as "The avatar
// keeps its current voice." Render the returned dialog in the page.
export function useLeaveGuard(pending: boolean, unchanged: string) {
  const { ask, dialog } = useConfirm();
  const now = useRef({ pending, unchanged });
  now.current = { pending, unchanged };

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (!now.current.pending || !(e.target instanceof Element)) return;
      const href = e.target.closest("a[href^='#/']")?.getAttribute("href");
      if (!href || pageFor(href) === pageFor(window.location.hash)) return;
      e.preventDefault();
      e.stopPropagation();
      console.info(`Leaving setup for ${href} with the sample neither accepted nor rejected`);
      void ask({
        title: LEAVE_TITLE,
        keepLabel: LEAVE_CANCEL,
        confirmLabel: LEAVE_PROCEED,
        children: (
          <>
            <p>
              Your change takes effect only once you accept its sample video. If you proceed,
              nothing changes. {now.current.unchanged}
            </p>
            <p className="muted">Choose Cancel to stay and accept or reject the sample video.</p>
          </>
        ),
      }).then((proceed) => {
        if (proceed) window.location.hash = href;
      });
    };
    const onUnload = (e: BeforeUnloadEvent) => {
      if (now.current.pending) e.preventDefault(); // the browser asks whether to leave
    };
    // Captured first, so the link's own handler doesn't run unless the user proceeds.
    document.addEventListener("click", onClick, true);
    window.addEventListener("beforeunload", onUnload);
    return () => {
      document.removeEventListener("click", onClick, true);
      window.removeEventListener("beforeunload", onUnload);
    };
  }, []);

  return dialog;
}

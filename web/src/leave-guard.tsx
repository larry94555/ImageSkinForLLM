// Leaving setup with a sample video neither accepted nor rejected (Larry's test of PR #131): a
// change takes effect only once its sample is accepted, so the app asks first. Proceed leaves
// with nothing changed; Cancel stays, to accept or reject the sample.

import { useEffect, useRef } from "preact/hooks";

import { useConfirm } from "./confirm-dialog";
import { blockLeaving, pageFor } from "./router";

export const LEAVE_TITLE = "Your change isn't accepted yet";
export const LEAVE_PROCEED = "Proceed without the change";
export const LEAVE_CANCEL = "Cancel";

// An address the page itself goes to once the sample is decided, such as the chat after Accept,
// let through once without asking (Larry's test of PR #191). The page's own state still says the
// sample is waiting until it has drawn again, which comes after the address changes.
let decided: string | null = null;

export function goWithoutAsking(href: string) {
  decided = href;
  // After the router has seen this change, so it never lets a later one through.
  window.addEventListener("hashchange", () => (decided = null), { once: true });
  window.location.hash = href;
}

// While `pending`, a click on a link to another page, or the browser's Back or Forward, asks
// first, and closing or reloading the tab gets the browser's own warning. `unchanged` says what
// stays as it is, such as "The avatar keeps its current voice." Render the returned dialog in the
// page.
export function useLeaveGuard(pending: boolean, unchanged: string) {
  const { ask, dialog } = useConfirm();
  const now = useRef({ pending, unchanged });
  now.current = { pending, unchanged };
  // The address the user chose to proceed to, let through once without asking again.
  const allowed = useRef<string | null>(null);

  useEffect(() => {
    const confirmLeave = (href: string) => {
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
        if (!proceed) return;
        allowed.current = href;
        window.location.hash = href;
      });
    };
    const leaving = (from: string, to: string) => {
      if (decided === to) {
        decided = null;
        return false;
      }
      return now.current.pending && pageFor(to) !== pageFor(from) && allowed.current !== to;
    };
    const onClick = (e: MouseEvent) => {
      if (!(e.target instanceof Element)) return;
      const href = e.target.closest("a[href^='#/']")?.getAttribute("href");
      if (!href || !leaving(window.location.hash, href)) return;
      e.preventDefault();
      e.stopPropagation();
      confirmLeave(href);
    };
    // Back and Forward change the address without a click (Codex's review of PR #131): the
    // router asks here first, and the page's address is put back while the user decides, as a
    // new entry, so Back still works after Cancel. pushState makes no hashchange of its own.
    blockLeaving((from, to) => {
      if (!leaving(from, to)) {
        if (allowed.current === to) allowed.current = null;
        return false;
      }
      history.pushState(history.state, "", from);
      confirmLeave(to);
      return true;
    });
    const onUnload = (e: BeforeUnloadEvent) => {
      if (now.current.pending) e.preventDefault(); // the browser asks whether to leave
    };
    // Captured first, so the link's own handler doesn't run unless the user proceeds.
    document.addEventListener("click", onClick, true);
    window.addEventListener("beforeunload", onUnload);
    return () => {
      document.removeEventListener("click", onClick, true);
      blockLeaving(null);
      window.removeEventListener("beforeunload", onUnload);
    };
  }, []);

  return dialog;
}

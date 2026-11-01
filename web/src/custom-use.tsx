// Hiding a host's own photo and voice where the administrator turned them off (roadmap R240b).
// Admin settings' Disable custom image and Disable custom voice (R239) say what a host may use,
// and the server refuses the rest (R240); here the browser stops offering it. It asks the server
// again on each page, so a change in Admin settings shows on the host's next page.

import { createContext } from "preact";
import { useContext, useEffect, useState } from "preact/hooks";

import { type CustomUse, getCustomUse } from "./api";

// Until the server has said, and for anyone not signed in as a host, nothing is hidden: the
// participant view offers none of it, and the server refuses what isn't allowed anyway.
export const ALLOWED: CustomUse = { image: true, voice: true };

const CustomUseContext = createContext<CustomUse>(ALLOWED);
export const CustomUseProvider = CustomUseContext.Provider;

// What the host may use, for the page being shown.
export function useCustomUse(): CustomUse {
  return useContext(CustomUseContext);
}

// What the host may use, and the page (`hash`) it was read for.
export interface CustomUseRead {
  use: CustomUse | null; // null until the first answer, so no page shows what it should hide
  // Whether `use` was read for the page shown now. Until it is, the page is opened anyway, and
  // only the newly read answer sends it elsewhere: an answer from before an Admin settings change
  // mustn't send the host away from a page they may now use.
  fresh: boolean;
}

// Read again on each page change (`hash`) while signed in as a host. A page change keeps the last
// answer, for what the page offers, until the next one.
export function useCustomUseOf(hash: string, signedIn: boolean | undefined): CustomUseRead {
  const [read, setRead] = useState<{ use: CustomUse; hash: string } | null>(null);
  useEffect(() => {
    if (signedIn === undefined) return; // the sign-in isn't known yet
    if (!signedIn) {
      setRead({ use: ALLOWED, hash });
      return;
    }
    let active = true;
    getCustomUse().then(
      (got) => {
        if (!active) return;
        setRead((was) => {
          if (!was || was.use.image !== got.image || was.use.voice !== got.voice) {
            console.info(`Own photo allowed: ${got.image}, own voice allowed: ${got.voice}`);
          }
          return { use: got, hash };
        });
      },
      (e: unknown) => {
        // Shown as allowed: the server still refuses what isn't (R240).
        console.error("Could not read whether your own photo and voice may be used", e);
        if (active) setRead((was) => ({ use: was?.use ?? ALLOWED, hash }));
      },
    );
    return () => {
      active = false;
    };
  }, [hash, signedIn]);
  return { use: read?.use ?? null, fresh: read?.hash === hash };
}

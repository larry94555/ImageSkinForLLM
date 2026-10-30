// Settings only for a signed-in host, or on a laptop listed in the admin laptops file (roadmap
// R191), so the administrator can still open Settings and sign in there. Asked again whenever the
// host signs in or out.

import type { ComponentChildren } from "preact";
import { createContext } from "preact";
import { useContext, useEffect, useState } from "preact/hooks";

import { getAdminChallenge, getSettingsAccess } from "./api";
import { useHost } from "./host";
import { canProve, laptopId, prove } from "./laptop-key";

// null until the server has answered.
const AccessContext = createContext<boolean | null>(null);

export function useSettingsShown(): boolean | null {
  return useContext(AccessContext);
}

export function SettingsAccessProvider({ children }: { children: ComponentChildren }) {
  const session = useHost().session;
  const [shown, setShown] = useState<boolean | null>(null);
  const host = session?.signed_in;

  useEffect(() => {
    if (host === undefined) return;
    let current = true;
    (async () => {
      // A host needs no proof; any other browser proves its laptop where it can (R164), in case
      // it is listed.
      const laptop = !host && canProve() ? await prove(await getAdminChallenge()) : undefined;
      const access = await getSettingsAccess(laptop);
      // Hidden, the page can't show this laptop's ID, so the console has it, to list in
      // admin-laptops.toml on the host.
      if (!access.shown && laptop) console.info(`This laptop's ID: ${await laptopId()}`);
      return access;
    })().then(
      (access) => {
        if (!current) return;
        console.info(access.shown ? `Settings shown, as ${access.as}` : "Settings hidden");
        setShown(access.shown === true);
      },
      (e: unknown) => {
        // Hidden: the server refuses the Settings calls anyway.
        console.error("Could not ask whether Settings is shown", e);
        if (current) setShown(false);
      },
    );
    return () => {
      current = false;
    };
  }, [host]);

  return <AccessContext.Provider value={shown}>{children}</AccessContext.Provider>;
}

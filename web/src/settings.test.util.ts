// Steps the tests share for the Settings page (R27).

import { act, fireEvent, screen, waitFor } from "@testing-library/preact";
import { expect } from "vitest";

// Opens the Settings page from the top bar.
export async function openSettings() {
  await act(async () => {
    fireEvent.click(screen.getByRole("link", { name: "Settings" }));
  });
  await screen.findByRole("heading", { name: "Settings", level: 1 });
}

// Goes back to the page the Settings page was opened from.
export async function returnToApp() {
  await act(async () => {
    fireEvent.click(screen.getByRole("link", { name: "Return to the app" }));
  });
  await waitFor(() => expect(screen.queryByRole("heading", { name: "Settings" })).toBeNull());
}

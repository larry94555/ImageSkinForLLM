// The browser app: draws the page for the current URL hash inside the shared layout.

import { confirmConsent, getConsent } from "./api.js";
import { type Page, resolve } from "./router.js";

const main = document.getElementById("page") as HTMLElement;

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<HTMLElementTagNameMap[K]> = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

function link(href: string, text: string, className = "button"): HTMLAnchorElement {
  return el("a", { href, className }, text);
}

function homePage(consented: boolean): Node[] {
  return [
    el("h1", {}, "Welcome"),
    el(
      "p",
      {},
      "Set up a talking video of a person from a few photos and voice recordings. " +
        "The person then speaks the chatbot's replies.",
    ),
    link(consented ? "#/setup" : "#/consent", "Start setup"),
  ];
}

function consentPage(): Node[] {
  const box = el("input", { type: "checkbox", id: "consent-box" });
  const button = el("button", { type: "submit", disabled: true }, "Continue");
  const error = el("p", { className: "error", hidden: true });
  box.addEventListener("change", () => {
    button.disabled = !box.checked;
  });
  const form = el(
    "form",
    {},
    el(
      "label",
      { className: "check" },
      box,
      " The person in the photos and recordings I will upload agreed to have their face " +
        "and voice copied by this app.",
    ),
    button,
    error,
  );
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    button.disabled = true;
    try {
      await confirmConsent();
      location.hash = "#/setup";
    } catch (e) {
      console.error("Could not save consent", e);
      error.textContent = "Could not save your answer. Please try again.";
      error.hidden = false;
      button.disabled = false;
    }
  });
  return [
    el("h1", {}, "Before you start"),
    el(
      "p",
      {},
      "Only use photos and recordings of someone who has agreed to this, " +
        "or of yourself.",
    ),
    form,
  ];
}

function setupPage(): Node[] {
  return [
    el("h1", {}, "Setup"),
    el("p", { className: "done" }, "Thank you, consent is confirmed."),
    el("p", {}, "Uploading photos and recordings comes in the next version."),
  ];
}

function notFoundPage(): Node[] {
  return [el("h1", {}, "Page not found"), link("#/", "Go to the start page")];
}

function draw(page: Page, consented: boolean): void {
  const pages: Record<Page, () => Node[]> = {
    home: () => homePage(consented),
    consent: consentPage,
    setup: setupPage,
    "not-found": notFoundPage,
  };
  main.replaceChildren(...pages[page]());
  document.querySelectorAll<HTMLAnchorElement>("nav a").forEach((a) => {
    a.classList.toggle("current", a.dataset.page === page);
  });
}

async function render(): Promise<void> {
  let consented = false;
  try {
    consented = (await getConsent()).agreed;
  } catch (e) {
    console.error("Could not load consent", e);
  }
  const route = resolve(location.hash, consented);
  if (route.redirect && route.redirect !== location.hash) {
    location.replace(route.redirect); // fires hashchange, which renders again
    return;
  }
  draw(route.page, consented);
}

window.addEventListener("hashchange", () => void render());
void render();

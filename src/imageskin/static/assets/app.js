// Generated from web/src/*.tsx by `npm run build` in web/. Do not edit; edit web/src.
import { a as S, i as R, n as d, r as h, t as u } from "./preact.js";
//#region src/api.ts
async function json(response) {
	if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
	return await response.json();
}
async function getConsent() {
	return json(await fetch("/api/consent"));
}
async function confirmConsent() {
	return json(await fetch("/api/consent", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ agreed: true })
	}));
}
//#endregion
//#region src/pages.tsx
function HomePage({ consented }) {
	return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("h1", { children: "Welcome" }),
		/* @__PURE__ */ u("p", { children: "Set up a talking video of a person from a few photos and voice recordings. The person then speaks the chatbot's replies." }),
		/* @__PURE__ */ u("a", {
			className: "button",
			href: consented ? "#/setup" : "#/consent",
			children: "Start setup"
		})
	] });
}
function ConsentPage({ onConfirmed }) {
	const [checked, setChecked] = d(false);
	const [saving, setSaving] = d(false);
	const [error, setError] = d(false);
	async function submit(event) {
		event.preventDefault();
		setSaving(true);
		setError(false);
		try {
			await confirmConsent();
			onConfirmed();
		} catch (e) {
			console.error("Could not save consent", e);
			setError(true);
			setSaving(false);
		}
	}
	return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("h1", { children: "Before you start" }),
		/* @__PURE__ */ u("p", { children: "Only use photos and recordings of someone who has agreed to this, or of yourself." }),
		/* @__PURE__ */ u("form", {
			onSubmit: submit,
			children: [
				/* @__PURE__ */ u("label", {
					className: "check",
					children: [
						/* @__PURE__ */ u("input", {
							type: "checkbox",
							checked,
							onChange: (e) => setChecked(e.currentTarget.checked)
						}),
						" ",
						"The person in the photos and recordings I will upload agreed to have their face and voice copied by this app."
					]
				}),
				/* @__PURE__ */ u("button", {
					type: "submit",
					disabled: !checked || saving,
					children: "Continue"
				}),
				error && /* @__PURE__ */ u("p", {
					className: "error",
					children: "Could not save your answer. Please try again."
				})
			]
		})
	] });
}
function SetupPage() {
	return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("h1", { children: "Setup" }),
		/* @__PURE__ */ u("p", {
			className: "done",
			children: "Thank you, consent is confirmed."
		}),
		/* @__PURE__ */ u("p", { children: "Uploading photos and recordings comes in the next version." })
	] });
}
function NotFoundPage() {
	return /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("h1", { children: "Page not found" }), /* @__PURE__ */ u("a", {
		className: "button",
		href: "#/",
		children: "Go to the start page"
	})] });
}
//#endregion
//#region src/router.ts
var PAGES = {
	"/": "home",
	"/consent": "consent",
	"/setup": "setup"
};
function pageFor(hash) {
	return PAGES[hash.replace(/^#/, "").replace(/\/+$/, "") || "/"] ?? "not-found";
}
function resolve(hash, consented) {
	const page = pageFor(hash);
	if (page === "setup" && !consented) return {
		page: "consent",
		redirect: "#/consent"
	};
	return { page };
}
function useHash() {
	const [hash, setHash] = d(window.location.hash);
	h(() => {
		const update = () => setHash(window.location.hash);
		window.addEventListener("hashchange", update);
		return () => window.removeEventListener("hashchange", update);
	}, []);
	return hash;
}
//#endregion
//#region src/App.tsx
var NAV = [{
	page: "home",
	href: "#/",
	label: "Home"
}, {
	page: "setup",
	href: "#/setup",
	label: "Setup"
}];
function App() {
	const hash = useHash();
	const [consented, setConsented] = d(null);
	h(() => {
		getConsent().then((c) => setConsented(c.agreed)).catch((e) => {
			console.error("Could not load consent", e);
			setConsented(false);
		});
	}, []);
	const route = consented === null ? null : resolve(hash, consented);
	h(() => {
		if (route?.redirect && route.redirect !== window.location.hash) window.location.replace(route.redirect);
	}, [route?.redirect]);
	let content = /* @__PURE__ */ u("p", { children: "Loading…" });
	if (route) content = {
		home: /* @__PURE__ */ u(HomePage, { consented: consented === true }),
		consent: /* @__PURE__ */ u(ConsentPage, { onConfirmed: () => {
			setConsented(true);
			window.location.hash = "#/setup";
		} }),
		setup: /* @__PURE__ */ u(SetupPage, {}),
		"not-found": /* @__PURE__ */ u(NotFoundPage, {})
	}[route.page];
	return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("header", { children: [/* @__PURE__ */ u("a", {
			className: "brand",
			href: "#/",
			children: "ImageSkinForLLM"
		}), /* @__PURE__ */ u("nav", { children: NAV.map((item) => /* @__PURE__ */ u("a", {
			href: item.href,
			className: route?.page === item.page ? "current" : void 0,
			children: item.label
		}, item.page)) })] }),
		/* @__PURE__ */ u("main", { children: content }),
		/* @__PURE__ */ u("footer", { children: "Photos and recordings stay on the computer that runs this app." })
	] });
}
//#endregion
//#region src/main.tsx
R(/* @__PURE__ */ u(App, {}), document.getElementById("root"));
//#endregion

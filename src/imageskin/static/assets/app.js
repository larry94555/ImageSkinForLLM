// Generated from web/src/*.tsx by `npm run build` in web/. Do not edit; edit web/src.
import { n as require_client, r as require_react, t as require_jsx_runtime } from "./react.js";
//#region src/api.ts
var import_react = require_react();
var import_client = require_client();
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
//#region src/pages/ConsentPage.tsx
var import_jsx_runtime = require_jsx_runtime();
function ConsentPage({ onConfirmed }) {
	const [checked, setChecked] = (0, import_react.useState)(false);
	const [saving, setSaving] = (0, import_react.useState)(false);
	const [error, setError] = (0, import_react.useState)(false);
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
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", { children: "Before you start" }),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { children: "Only use photos and recordings of someone who has agreed to this, or of yourself." }),
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("form", {
			onSubmit: submit,
			children: [
				/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("label", {
					className: "check",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("input", {
							type: "checkbox",
							checked,
							onChange: (e) => setChecked(e.target.checked)
						}),
						" ",
						"The person in the photos and recordings I will upload agreed to have their face and voice copied by this app."
					]
				}),
				/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
					type: "submit",
					disabled: !checked || saving,
					children: "Continue"
				}),
				error && /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
					className: "error",
					children: "Could not save your answer. Please try again."
				})
			]
		})
	] });
}
//#endregion
//#region src/pages/HomePage.tsx
function HomePage({ consented }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", { children: "Welcome" }),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { children: "Set up a talking video of a person from a few photos and voice recordings. The person then speaks the chatbot's replies." }),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
			className: "button",
			href: consented ? "#/setup" : "#/consent",
			children: "Start setup"
		})
	] });
}
//#endregion
//#region src/pages/NotFoundPage.tsx
function NotFoundPage() {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", { children: "Page not found" }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
		className: "button",
		href: "#/",
		children: "Go to the start page"
	})] });
}
//#endregion
//#region src/pages/SetupPage.tsx
function SetupPage() {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", { children: "Setup" }),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
			className: "done",
			children: "Thank you, consent is confirmed."
		}),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { children: "Uploading photos and recordings comes in the next version." })
	] });
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
	const [hash, setHash] = (0, import_react.useState)(window.location.hash);
	(0, import_react.useEffect)(() => {
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
	const [consented, setConsented] = (0, import_react.useState)(null);
	(0, import_react.useEffect)(() => {
		getConsent().then((c) => setConsented(c.agreed)).catch((e) => {
			console.error("Could not load consent", e);
			setConsented(false);
		});
	}, []);
	const route = consented === null ? null : resolve(hash, consented);
	(0, import_react.useEffect)(() => {
		if (route?.redirect && route.redirect !== window.location.hash) window.location.replace(route.redirect);
	}, [route?.redirect]);
	let content = /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", { children: "Loading…" });
	if (route) content = {
		home: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(HomePage, { consented: consented === true }),
		consent: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ConsentPage, { onConfirmed: () => {
			setConsented(true);
			window.location.hash = "#/setup";
		} }),
		setup: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(SetupPage, {}),
		"not-found": /* @__PURE__ */ (0, import_jsx_runtime.jsx)(NotFoundPage, {})
	}[route.page];
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [
		/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("header", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
			className: "brand",
			href: "#/",
			children: "ImageSkinForLLM"
		}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("nav", { children: NAV.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
			href: item.href,
			className: route?.page === item.page ? "current" : void 0,
			children: item.label
		}, item.page)) })] }),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("main", { children: content }),
		/* @__PURE__ */ (0, import_jsx_runtime.jsx)("footer", { children: "Photos and recordings stay on the computer that runs this app." })
	] });
}
//#endregion
//#region src/main.tsx
(0, import_client.createRoot)(document.getElementById("root")).render(/* @__PURE__ */ (0, import_jsx_runtime.jsx)(import_react.StrictMode, { children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(App, {}) }));
//#endregion

// Generated from web/src/*.tsx by `npm run build` in web/. Do not edit; edit web/src.
import { a as h, c as S, i as d, l as X, n as A, o as x, r as _, s as R, t as u } from "./preact.js";
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
var ServerRefusal = class extends Error {
	status;
	constructor(message, status) {
		super(message);
		this.status = status;
	}
};
async function refusal(response) {
	try {
		const body = await response.json();
		if (typeof body.detail === "string") return body.detail;
	} catch {}
	console.error(`Refused with ${response.status} and no reason`);
	return "That didn't work. Please try again.";
}
function uploadUrl(kind, id) {
	return `/api/uploads/${kind}/${id}`;
}
async function listUploads(kind) {
	return json(await fetch(`/api/uploads/${kind}`));
}
async function uploadFile(kind, file) {
	const form = new FormData();
	form.append("file", file);
	const response = await fetch(`/api/uploads/${kind}`, {
		method: "POST",
		body: form
	});
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function checkUpload(kind, id) {
	const response = await fetch(`${uploadUrl(kind, id)}/check`, { method: "POST" });
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function getVoiceSample() {
	return json(await fetch("/api/voice-sample"));
}
async function getPhotoChoice() {
	return json(await fetch("/api/uploads/photos/chosen"));
}
async function choosePhoto(id) {
	const response = await fetch("/api/uploads/photos/chosen", {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ id })
	});
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function removeUpload(kind, id) {
	const response = await fetch(uploadUrl(kind, id), { method: "DELETE" });
	if (!response.ok) throw new Error(await refusal(response));
}
async function getAccent() {
	return json(await fetch("/api/accent"));
}
async function chooseAccent(accent) {
	const response = await fetch("/api/accent", {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ accent })
	});
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
function clipUrl(name, status) {
	return `/api/prepare/clips/${name}?v=${encodeURIComponent(status.finished_at ?? "")}`;
}
async function getPrepare() {
	return json(await fetch("/api/prepare"));
}
async function startPrepare() {
	const response = await fetch("/api/prepare", { method: "POST" });
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function getReview() {
	return json(await fetch("/api/review"));
}
async function review(decision) {
	const response = await fetch("/api/review", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ decision })
	});
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function getChat() {
	return (await json(await fetch("/api/chat"))).turns;
}
async function sendPrompt(prompt, replyId, lesson) {
	const body = { prompt };
	if (replyId) body.reply_id = replyId;
	if (lesson) body.lesson = {
		topic: lesson.topic,
		part: lesson.part,
		active: lesson.active
	};
	const response = await fetch("/api/chat", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body)
	});
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function speakReply(turn, replyId) {
	const response = await fetch("/api/chat/video", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(replyId ? {
			turn,
			reply_id: replyId
		} : { turn })
	});
	if (!response.ok) throw new Error(await refusal(response));
	return (await response.json()).video;
}
async function getClips(replyId, known) {
	const query = known === void 0 ? "" : `?known=${known}&wait=10`;
	const response = await fetch(`/api/chat/clips/${replyId}${query}`);
	if (response.status === 404) return null;
	return json(response);
}
async function stopReply(replyId) {
	return (await json(await fetch(`/api/chat/clips/${replyId}/stop`, { method: "POST" }))).stopped;
}
async function getChatPhoto() {
	return json(await fetch("/api/chat/photo"));
}
async function getChatHints() {
	const hints = await json(await fetch("/api/chat/hints"));
	return {
		line: typeof hints?.line === "string" ? hints.line : null,
		examples: Array.isArray(hints?.examples) ? hints.examples : []
	};
}
function pdfUrl(id) {
	return `/api/content/${id}`;
}
async function listPdfs() {
	return json(await fetch("/api/content"));
}
async function sendPdf(file, id) {
	const form = new FormData();
	form.append("file", file);
	const response = await fetch(id ? pdfUrl(id) : "/api/content", {
		method: id ? "PUT" : "POST",
		body: form
	});
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function removePdf(id) {
	const response = await fetch(pdfUrl(id), { method: "DELETE" });
	if (!response.ok) throw new Error(await refusal(response));
}
async function listReadings() {
	return json(await fetch("/api/content/readings"));
}
async function listWikiContents(pdf) {
	const query = pdf ? `?pdf=${encodeURIComponent(pdf)}` : "";
	return json(await fetch(`/api/wiki/contents${query}`));
}
async function getWikiPage(id) {
	const response = await fetch(`/api/wiki/${encodeURIComponent(id)}`);
	if (response.status === 404) return null;
	return json(response);
}
async function saveWikiEdit(id, title, summary) {
	const response = await fetch(`/api/wiki/${encodeURIComponent(id)}`, {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			title,
			summary
		})
	});
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function undoWikiEdit(id) {
	const response = await fetch(`/api/wiki/${encodeURIComponent(id)}/edit`, { method: "DELETE" });
	if (!response.ok) throw new Error(await refusal(response));
}
async function markWikiReviewed(id) {
	const response = await fetch(`/api/wiki/${encodeURIComponent(id)}/reviewed`, { method: "POST" });
	if (!response.ok) throw new Error(await refusal(response));
}
async function rebuildWiki(pdf) {
	const response = await fetch(`/api/content/${pdf}/wiki/rebuild`, { method: "POST" });
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
var AskFirst = class extends Error {};
async function refused(response) {
	const message = await refusal(response);
	throw response.status === 412 ? new AskFirst(message) : new Error(message);
}
async function listWikiVersions(pdf) {
	const response = await fetch(`/api/content/${pdf}/wiki/history`);
	if (!response.ok) return refused(response);
	return await response.json();
}
async function getWikiVersion(pdf, id) {
	const response = await fetch(`/api/content/${pdf}/wiki/history/${encodeURIComponent(id)}`);
	if (!response.ok) return refused(response);
	return await response.json();
}
async function restoreWikiVersion(pdf, id, force = false) {
	const response = await fetch(`/api/content/${pdf}/wiki/history/${encodeURIComponent(id)}/restore${force ? "?force=true" : ""}`, { method: "POST" });
	if (!response.ok) await refused(response);
}
function wikiFileUrl(pdf) {
	return `/api/content/${pdf}/wiki/file`;
}
async function loadWikiFile(pdf, file, force = false) {
	const body = new FormData();
	body.append("file", file);
	const response = await fetch(`/api/content/${pdf}/wiki/file${force ? "?force=true" : ""}`, {
		method: "POST",
		body
	});
	if (!response.ok) return refused(response);
	return (await response.json()).versions_added;
}
function wikiHref(pdf) {
	return pdf ? `#/wiki/${pdf}` : "#/wiki";
}
function wikiPageHref(id) {
	return `#/wiki/page/${id}`;
}
function pdfPageUrl(id, page) {
	return `${pdfUrl(id)}#page=${page}`;
}
async function listWikiBuilds() {
	return json(await fetch("/api/wiki/builds"));
}
var DEFAULT_SETTINGS = {
	show_metrics: false,
	view: "teacher",
	teach_me: false,
	debug: false
};
function settings(data) {
	return {
		show_metrics: data.show_metrics === true,
		view: data.view === "student" ? "student" : "teacher",
		teach_me: data.teach_me === true,
		debug: data.debug === true
	};
}
async function getSettings() {
	return settings(await json(await fetch("/api/settings")));
}
async function changeSettings(changes) {
	return settings(await json(await fetch("/api/settings", {
		method: "PATCH",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(changes)
	})));
}
//#endregion
//#region src/settings.tsx
var SettingsContext = X({
	settings: DEFAULT_SETTINGS,
	loaded: true,
	change: async () => {}
});
function useSettings() {
	return x(SettingsContext).settings;
}
function useSettingsLoaded() {
	return x(SettingsContext).loaded;
}
function SettingsProvider({ children }) {
	const [settings, setSettings] = d(DEFAULT_SETTINGS);
	const [loaded, setLoaded] = d(false);
	const changed = A(false);
	h(() => {
		getSettings().then((read) => changed.current || setSettings(read)).catch((e) => console.error("Could not load the settings", e)).finally(() => setLoaded(true));
	}, []);
	async function change(changes) {
		const started = performance.now();
		const saved = await changeSettings(changes);
		changed.current = true;
		setSettings(saved);
		const took = Math.round(performance.now() - started);
		console.info(`Settings changed: ${JSON.stringify(changes)} (${took} ms)`);
	}
	return /* @__PURE__ */ u(SettingsContext.Provider, {
		value: {
			settings,
			loaded,
			change
		},
		children
	});
}
var VIEWS = [[
	"teacher",
	"Teacher",
	"every page and option"
], [
	"student",
	"Student",
	"the chat and a read-only wiki"
]];
function SettingsMenu() {
	const { settings, loaded, change } = x(SettingsContext);
	const [open, setOpen] = d(false);
	const [failed, setFailed] = d(false);
	const menu = A(null);
	h(() => {
		if (!open) return;
		const close = (e) => e.key === "Escape" && setOpen(false);
		window.addEventListener("keydown", close);
		return () => window.removeEventListener("keydown", close);
	}, [open]);
	async function save(changes, undo) {
		setFailed(false);
		try {
			await change(changes);
		} catch (e) {
			console.error(`Could not change the settings ${JSON.stringify(changes)}`, e);
			setFailed(true);
			undo();
		}
	}
	function chooseView(view) {
		const was = settings.view;
		save({ view }, () => {
			const box = menu.current?.querySelector(`input[value="${was}"]`);
			if (box) box.checked = true;
		});
	}
	return /* @__PURE__ */ u("div", {
		className: "settings",
		children: [/* @__PURE__ */ u("button", {
			type: "button",
			className: "link",
			"aria-expanded": open,
			"aria-controls": "settings-menu",
			disabled: !loaded,
			onClick: () => setOpen(!open),
			children: [/* @__PURE__ */ u("svg", {
				viewBox: "0 0 24 24",
				"aria-hidden": "true",
				fill: "none",
				stroke: "currentColor",
				"stroke-width": "2",
				"stroke-linecap": "round",
				children: [
					/* @__PURE__ */ u("path", { d: "M4 7h10M18 7h2M4 17h4M12 17h8" }),
					/* @__PURE__ */ u("circle", {
						cx: "16",
						cy: "7",
						r: "2"
					}),
					/* @__PURE__ */ u("circle", {
						cx: "10",
						cy: "17",
						r: "2"
					})
				]
			}), "Settings"]
		}), open && /* @__PURE__ */ u("div", {
			id: "settings-menu",
			ref: menu,
			className: "settings-menu",
			role: "group",
			"aria-label": "Settings",
			children: [
				/* @__PURE__ */ u("fieldset", { children: [/* @__PURE__ */ u("legend", { children: "View" }), VIEWS.map(([view, label, about]) => /* @__PURE__ */ u("label", {
					className: "choice",
					children: [
						/* @__PURE__ */ u("input", {
							type: "radio",
							name: "view",
							value: view,
							checked: settings.view === view,
							onChange: () => chooseView(view)
						}),
						" ",
						/* @__PURE__ */ u("span", { children: [label, /* @__PURE__ */ u("span", {
							className: "muted",
							children: [" · ", about]
						})] })
					]
				}, view))] }),
				/* @__PURE__ */ u("label", { children: [
					/* @__PURE__ */ u("input", {
						type: "checkbox",
						checked: settings.show_metrics,
						onChange: (e) => {
							const box = e.currentTarget;
							save({ show_metrics: box.checked }, () => box.checked = !box.checked);
						}
					}),
					" ",
					"Show timing metrics"
				] }),
				/* @__PURE__ */ u("p", {
					className: "muted",
					children: "How long replies and other steps take, under the video and on the pages."
				}),
				/* @__PURE__ */ u("label", { children: [
					/* @__PURE__ */ u("input", {
						type: "checkbox",
						checked: settings.teach_me,
						onChange: (e) => {
							const box = e.currentTarget;
							save({ teach_me: box.checked }, () => box.checked = !box.checked);
						}
					}),
					" ",
					"Teach me"
				] }),
				/* @__PURE__ */ u("p", {
					className: "muted",
					children: "A Teach me button in the chat that teaches the content a part at a time."
				}),
				/* @__PURE__ */ u("label", { children: [
					/* @__PURE__ */ u("input", {
						type: "checkbox",
						checked: settings.debug,
						onChange: (e) => {
							const box = e.currentTarget;
							save({ debug: box.checked }, () => box.checked = !box.checked);
						}
					}),
					" ",
					"Debug"
				] }),
				/* @__PURE__ */ u("p", {
					className: "muted",
					children: "Copy chat under the conversation, to paste the latest exchanges somewhere else."
				}),
				failed && /* @__PURE__ */ u("p", {
					className: "error",
					children: "The setting could not be changed. Try again."
				})
			]
		})]
	});
}
//#endregion
//#region src/content.tsx
var READING_POLL_MS = 1e3;
function ContentPage() {
	const [pdfs, setPdfs] = d(null);
	const [loadFailed, setLoadFailed] = d(false);
	const [sending, setSending] = d(null);
	const [refused, setRefused] = d([]);
	const [done, setDone] = d(null);
	const [readings, setReadings] = d({});
	const reading = (pdfs ?? []).some((pdf) => [
		"waiting",
		"reading",
		void 0
	].includes(readings[pdf.id]?.state));
	const [wiki, setWiki] = d({});
	const building = (pdfs ?? []).some((pdf) => readings[pdf.id]?.state === "done" && [
		"waiting",
		"building",
		void 0
	].includes(wiki[pdf.id]?.state));
	h(() => {
		if (pdfs === null) return;
		let stopped = false;
		const check = () => {
			listReadings().then((next) => {
				if (!stopped) setReadings(next);
			}).catch((e) => console.error("Could not check the reading progress", e));
			listWikiBuilds().then((next) => {
				if (!stopped) setWiki(next);
			}).catch((e) => console.error("Could not check the wiki progress", e));
		};
		check();
		const timer = reading || building ? window.setInterval(check, READING_POLL_MS) : void 0;
		return () => {
			stopped = true;
			window.clearInterval(timer);
		};
	}, [
		pdfs,
		reading,
		building
	]);
	h(() => {
		listPdfs().then(setPdfs).catch((e) => {
			console.error("Could not list the PDFs", e);
			setLoadFailed(true);
		});
	}, []);
	async function send(file, replacing) {
		setSending({
			name: file.name,
			replacing: replacing?.id
		});
		const started = performance.now();
		try {
			const pdf = await sendPdf(file, replacing?.id);
			const took = `${Math.round(performance.now() - started)} ms`;
			console.info(replacing ? `Replaced ${replacing.name} with ${pdf.name} in ${took}` : `Added ${pdf.name} in ${took}`);
			return pdf;
		} catch (e) {
			console.error(`${replacing ? "Replacing" : "Adding"} ${file.name} refused`, e);
			setRefused((current) => [...current, {
				name: file.name,
				reason: e.message
			}]);
			return null;
		} finally {
			setSending(null);
		}
	}
	async function add(event) {
		const input = event.currentTarget;
		const files = Array.from(input.files ?? []);
		input.value = "";
		setRefused([]);
		setDone(null);
		const added = [];
		for (const file of files) {
			const pdf = await send(file);
			if (pdf) {
				added.push(pdf.name);
				setPdfs((current) => [...current ?? [], pdf]);
			}
		}
		if (added.length) setDone(`Added ${added.join(", ")}. ${NEXT}`);
	}
	async function replace(old, event) {
		const input = event.currentTarget;
		const file = input.files?.[0];
		input.value = "";
		if (!file) return;
		setRefused([]);
		setDone(null);
		const pdf = await send(file, old);
		if (!pdf) return;
		setPdfs((current) => (current ?? []).map((p) => p.id === pdf.id ? pdf : p));
		setDone(`Replaced ${old.name} with ${pdf.name}. ${NEXT}`);
	}
	async function remove(pdf) {
		if (!window.confirm(`Remove ${pdf.name}? Its wiki is removed too.`)) return;
		setRefused([]);
		setDone(null);
		try {
			await removePdf(pdf.id);
			console.info(`Removed ${pdf.name}`);
			setPdfs((current) => (current ?? []).filter((p) => p.id !== pdf.id));
		} catch (e) {
			console.error(`Could not remove ${pdf.name}`, e);
			setRefused([{
				name: pdf.name,
				reason: "Could not remove it. Please try again."
			}]);
		}
	}
	const ready = sending === null && (pdfs !== null || loadFailed);
	const loading = pdfs === null && !loadFailed;
	return /* @__PURE__ */ u("div", {
		className: "teacher-page",
		children: [
			/* @__PURE__ */ u("h1", { children: "Manage Content" }),
			/* @__PURE__ */ u("p", {
				className: "lead",
				children: [
					"Add the PDFs the person's answers will come from, up to 100 MB each. Each one is read and turned into a ",
					/* @__PURE__ */ u("a", {
						href: wikiHref(),
						children: "wiki"
					}),
					" you can check. Replace a PDF when it has a newer version, or remove it when it no longer applies."
				]
			}),
			/* @__PURE__ */ u("label", {
				className: ready ? "button" : "button busy",
				children: [sending && !sending.replacing ? `Uploading ${sending.name}…` : loading ? "Loading…" : "Add PDFs", /* @__PURE__ */ u("input", {
					type: "file",
					multiple: true,
					accept: "application/pdf,.pdf",
					disabled: !ready,
					onChange: add,
					className: "file"
				})]
			}),
			done && /* @__PURE__ */ u("p", {
				className: "notice",
				role: "status",
				children: done
			}),
			refused.map((r) => /* @__PURE__ */ u("p", {
				className: "error",
				children: [
					r.name,
					": ",
					r.reason
				]
			}, r.name)),
			loadFailed && /* @__PURE__ */ u("p", {
				className: "error",
				children: "Could not load the list. Reload the page to try again."
			}),
			loading && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Loading the PDFs…"
			}),
			pdfs?.length === 0 && /* @__PURE__ */ u("p", {
				className: "muted",
				children: "No PDFs yet."
			}),
			/* @__PURE__ */ u("ul", {
				className: "pdfs",
				children: pdfs?.map((pdf) => /* @__PURE__ */ u("li", { children: [
					/* @__PURE__ */ u("a", {
						className: "name",
						href: pdfUrl(pdf.id),
						target: "_blank",
						rel: "noreferrer",
						children: pdf.name
					}),
					/* @__PURE__ */ u("span", {
						className: "muted",
						children: [
							size(pdf.size),
							" · ",
							pdf.replaced_at ? "replaced" : "added",
							" ",
							day(pdf.replaced_at ?? pdf.added_at)
						]
					}),
					/* @__PURE__ */ u(ReadingLine, { reading: readings[pdf.id] }),
					/* @__PURE__ */ u(WikiLine, {
						id: pdf.id,
						build: wiki[pdf.id]
					}),
					/* @__PURE__ */ u("span", {
						className: "actions",
						children: [/* @__PURE__ */ u("label", {
							className: sending?.replacing === pdf.id ? "replace busy" : "replace",
							children: [sending?.replacing === pdf.id ? `Uploading ${sending.name}…` : "Replace", /* @__PURE__ */ u("input", {
								type: "file",
								accept: "application/pdf,.pdf",
								"aria-label": `Replace ${pdf.name}`,
								disabled: !ready,
								onChange: (e) => replace(pdf, e),
								className: "file"
							})]
						}), /* @__PURE__ */ u("button", {
							type: "button",
							className: "remove",
							onClick: () => remove(pdf),
							children: "Remove"
						})]
					})
				] }, pdf.id))
			})
		]
	});
}
var NEXT = "It is read first, then its wiki is built. Each PDF below shows how far it has got.";
function ReadingLine({ reading }) {
	if (!reading) return null;
	if (reading.state === "failed") return /* @__PURE__ */ u("span", {
		className: "error",
		children: readingText(reading)
	});
	if (reading.state !== "done") return /* @__PURE__ */ u("span", {
		className: "muted busy",
		children: readingText(reading)
	});
	return /* @__PURE__ */ u("span", {
		className: "muted",
		children: readingText(reading)
	});
}
function readingText(r) {
	if (r.state === "waiting") return "Waiting to be read…";
	if (r.state === "reading") return r.pages ? `Reading page ${r.page} of ${r.pages}…` : "Reading…";
	if (r.state === "failed") return r.error ?? "Could not be read.";
	const found = [
		"paragraph",
		"slide",
		"table"
	].filter((kind) => r.counts?.[kind]).map((kind) => plural(r.counts?.[kind] ?? 0, kind));
	const blank = r.pages_without_text ?? [];
	let scanned = blank.length ? ` (no text on page ${blank.join(", ")}, maybe scanned)` : "";
	if (blank.length && !found.length) scanned = ", maybe scanned";
	return `Read ${plural(r.pages, "page")}: ${found.join(", ") || "no text found"}${scanned}`;
}
function WikiLine({ id, build }) {
	const metrics = useSettings().show_metrics;
	if (!build) return null;
	if (build.state === "failed") return /* @__PURE__ */ u("span", {
		className: "error",
		children: wikiText(build, metrics)
	});
	if (build.state !== "done") return /* @__PURE__ */ u("span", {
		className: "muted busy",
		children: wikiText(build, metrics)
	});
	return /* @__PURE__ */ u("span", {
		className: "muted",
		children: [
			wikiText(build, metrics),
			" ·",
			" ",
			/* @__PURE__ */ u("a", {
				href: wikiHref(id),
				children: "Read the wiki"
			})
		]
	});
}
function wikiText(b, metrics = false) {
	const time = (what = "") => {
		const parts = [];
		if (metrics && b.elapsed_s != null) parts.push(`${duration$1(b.elapsed_s)} so far`);
		if (b.remaining_s != null) parts.push(`about ${duration$1(b.remaining_s)} left${what}`);
		return parts.length ? ` (${parts.join(", ")})` : "";
	};
	const sofar = time();
	if (b.state === "waiting") {
		if (b.error) return `Waiting for the AI to be ready to build the wiki…${sofar}`;
		return `Waiting to build the wiki…${sofar}`;
	}
	if (b.state === "building" && b.stage === "outline") {
		const step = Math.min(b.steps + 1, b.steps_planned);
		return b.steps_planned ? `Arranging the wiki's topics: step ${step} of about ${b.steps_planned}…${sofar}` : `Arranging the wiki's topics…${sofar}`;
	}
	if (b.state === "building") {
		const part = Math.min(b.part + 1, b.parts);
		return b.parts ? `Building the wiki: part ${part} of ${b.parts}…${time(" before arranging its topics")}` : `Building the wiki…${sofar}`;
	}
	if (b.state === "failed") return b.error ?? "The wiki could not be built.";
	const n = b.skipped_parts?.length ?? 0;
	const skipped = n ? ` (${plural(n, "part")} of ${b.parts} skipped: the AI's answer couldn't be used)` : "";
	const detail = b.detail_pages ? `, ${plural(b.detail_pages, "detail page")}` : "";
	const took = metrics && b.elapsed_s != null ? `, built in ${duration$1(b.elapsed_s)}` : "";
	return `Wiki ready: ${plural(b.pages ?? 0, "topic")}${detail}${took}${skipped}`;
}
function duration$1(seconds) {
	const s = Math.round(seconds);
	if (s < 60) return `${s} s`;
	if (s < 3600) return `${Math.floor(s / 60)} min ${s % 60} s`;
	return `${Math.floor(s / 3600)} h ${Math.floor(s % 3600 / 60)} min`;
}
function plural(n, word) {
	return `${n} ${word}${n === 1 ? "" : "s"}`;
}
function size(bytes) {
	if (bytes < 1048576) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
	return `${(bytes / 1048576).toFixed(1)} MB`;
}
function day(iso) {
	return new Date(iso).toLocaleDateString();
}
//#endregion
//#region src/guide.tsx
var LAPTOPS = [
	{
		id: "win10",
		label: "Windows 10",
		photo: "Camera app",
		voice: "Voice Recorder app"
	},
	{
		id: "win11",
		label: "Windows 11",
		photo: "Camera app",
		voice: "Sound Recorder app"
	},
	{
		id: "mac",
		label: "Mac",
		photo: "Photo Booth app",
		voice: "Voice Memos app"
	}
];
var STORAGE_KEY = "imageskin.guide";
function loadGuide() {
	try {
		const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
		const step = typeof saved?.step === "number" ? saved.step : 0;
		const laptop = LAPTOPS.some((l) => l.id === saved?.laptop) ? saved?.laptop : null;
		return {
			step: Math.min(Math.max(0, Math.floor(step)), STEPS.length - 1),
			laptop
		};
	} catch {
		return {
			step: 0,
			laptop: null
		};
	}
}
function saveGuide(state) {
	try {
		localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
	} catch (e) {
		console.error("Could not save the guide's place", e);
	}
}
function For({ laptop, only, children }) {
	return laptop === null || only.includes(laptop) ? /* @__PURE__ */ u(S, { children }) : null;
}
function Script({ first, lines }) {
	return /* @__PURE__ */ u("ol", {
		className: "script",
		start: first,
		children: lines.map((line) => /* @__PURE__ */ u("li", { children: line }, line))
	});
}
function Before({ name, minutes, children }) {
	return /* @__PURE__ */ u("p", {
		className: "notice",
		children: [
			children ?? /* @__PURE__ */ u(S, { children: "Press Record. Read each line, then pause about 1 second (one breath) before the next line." }),
			" ",
			"At the end: press Stop, listen to check it, and name it ",
			/* @__PURE__ */ u("b", { children: name }),
			". This whole recording takes about ",
			minutes,
			"."
		]
	});
}
function Questions({ items }) {
	return /* @__PURE__ */ u("ul", {
		className: "bullets",
		children: items.map((q) => /* @__PURE__ */ u("li", { children: q }, q))
	});
}
var STEPS = [
	{
		title: "Before you begin",
		body: (laptop, pick) => /* @__PURE__ */ u(S, { children: [
			/* @__PURE__ */ u("p", { children: "This guide helps you make, on your own laptop:" }),
			/* @__PURE__ */ u("ul", {
				className: "bullets",
				children: [/* @__PURE__ */ u("li", { children: "Five photos of your face (picture files, usually ending in .jpg)." }), /* @__PURE__ */ u("li", { children: "Three to seven recordings of your voice (sound files, usually ending in .m4a or .wav). The first three, about 4 minutes, are enough today; all seven take about 15 minutes." })]
			}),
			/* @__PURE__ */ u("p", { children: "The photo becomes the face, and the recordings teach the app to speak in a voice that sounds like you. Your recordings are not played back as they are; they are only used as a sample." }),
			/* @__PURE__ */ u("h2", { children: "What you need" }),
			/* @__PURE__ */ u("ul", {
				className: "bullets",
				children: [
					/* @__PURE__ */ u("li", { children: "A laptop with a built-in camera and microphone (almost all laptops have both)." }),
					/* @__PURE__ */ u("li", { children: "A quiet room and about 40 minutes (you can take a break between recordings)." }),
					/* @__PURE__ */ u("li", { children: "A window or lamp in front of you for light." }),
					/* @__PURE__ */ u("li", { children: "This guide open next to the recording app, or on a second screen, so you can read the script while recording." })
				]
			}),
			/* @__PURE__ */ u("p", { children: "No accounts, downloads or technical skills are needed. Everything uses apps that already come with your laptop." }),
			/* @__PURE__ */ u("h2", { children: "Which laptop do you have?" }),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "The guide then shows only the steps for your laptop."
			}),
			/* @__PURE__ */ u("fieldset", {
				className: "laptops",
				children: [/* @__PURE__ */ u("legend", {
					className: "sr-only",
					children: "Your laptop"
				}), LAPTOPS.map((l) => /* @__PURE__ */ u("label", {
					className: laptop === l.id ? "picked" : void 0,
					children: [
						/* @__PURE__ */ u("input", {
							type: "radio",
							name: "laptop",
							checked: laptop === l.id,
							onChange: () => pick(l.id)
						}),
						/* @__PURE__ */ u("span", {
							className: "title",
							children: l.label
						}),
						/* @__PURE__ */ u("span", {
							className: "muted",
							children: [
								"Photo: ",
								l.photo,
								". Voice: ",
								l.voice,
								"."
							]
						})
					]
				}, l.id))]
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: [
					"Not sure which Windows you have? Press the Windows key, type ",
					/* @__PURE__ */ u("b", { children: "winver" }),
					" and press Enter. A small window shows \"Windows 10\" or \"Windows 11\". Click OK to close it."
				]
			}),
			/* @__PURE__ */ u("p", {
				className: "notice",
				children: "Your permission matters. Only use photos and voice recordings of yourself, or of someone who is happy for them to be used to make a talking video that looks and sounds like them."
			})
		] })
	},
	{
		title: "Get ready",
		body: () => /* @__PURE__ */ u(S, { children: [
			/* @__PURE__ */ u("h2", { children: "For the photo" }),
			/* @__PURE__ */ u("ul", {
				className: "bullets",
				children: [
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Light in front of you." }), " Sit facing a window (daytime is best) or a lamp. Do not sit with a bright window behind you, or your face will be dark."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Plain background." }), " A plain wall behind you is ideal."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Clean the camera lens." }), " Gently wipe the small lens above your screen with a soft cloth. Smudges make the photo blurry."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Raise the laptop." }), " Put it on a few books so the camera is at about the height of your eyes, not looking up at your chin."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Clear your face." }), " Take off sunglasses, hats and masks, and move hair away from your eyes. Ordinary glasses are fine, but tilt them slightly if they reflect light."] })
				]
			}),
			/* @__PURE__ */ u("h2", { children: "For the voice recording" }),
			/* @__PURE__ */ u("ul", {
				className: "bullets",
				children: [
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Quiet room." }), " Turn off the TV, music, fans, heaters and air conditioning. Close the windows and door. Silence your phone."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Soft room is better." }), " A bedroom with curtains, a bed and carpet sounds much better than a kitchen or bathroom, which echo."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Sit close." }), " Sit about an arm's length from the laptop or a little closer, and stay at the same distance the whole time."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Have water nearby." }), " A sip between sections keeps your voice clear."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Plug in the laptop" }), " so it does not go to sleep or run out of battery while you record."] })
				]
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "Using a headset or plug-in microphone? That is fine and often sounds better. Plug it in before you open the recording app. Keep it a hand's width from your mouth, a little to the side so your breath does not hit it."
			}),
			/* @__PURE__ */ u("h2", { children: "\"Allow\" messages" }),
			/* @__PURE__ */ u("p", { children: [
				"The first time you open a camera or recording app, your laptop may ask whether the app can use the camera or microphone. Always click ",
				/* @__PURE__ */ u("b", { children: "Allow" }),
				" or ",
				/* @__PURE__ */ u("b", { children: "OK" }),
				". If you clicked \"Don't allow\" by mistake, see the last step of this guide."
			] })
		] })
	},
	{
		title: "Take 5 photos",
		body: () => /* @__PURE__ */ u(S, { children: [
			/* @__PURE__ */ u("p", { children: "Take these 5 photos, in this order, without moving the laptop or changing the light between them. The app picks the best one as your face; the others are backups." }),
			/* @__PURE__ */ u("table", {
				className: "guide-table",
				children: [/* @__PURE__ */ u("thead", { children: /* @__PURE__ */ u("tr", { children: [
					/* @__PURE__ */ u("th", { children: "Photo" }),
					/* @__PURE__ */ u("th", { children: "Your head" }),
					/* @__PURE__ */ u("th", { children: "Your face" })
				] }) }), /* @__PURE__ */ u("tbody", { children: [
					/* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("td", { children: "1" }),
						/* @__PURE__ */ u("td", { children: "Straight at the camera" }),
						/* @__PURE__ */ u("td", { children: "Relaxed and neutral, mouth closed. This is the most important photo." })
					] }),
					/* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("td", { children: "2" }),
						/* @__PURE__ */ u("td", { children: "Straight at the camera" }),
						/* @__PURE__ */ u("td", { children: "Relaxed, lips slightly apart (as if about to say \"uh\"). No teeth showing, or only a little." })
					] }),
					/* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("td", { children: "3" }),
						/* @__PURE__ */ u("td", { children: "Straight at the camera" }),
						/* @__PURE__ */ u("td", { children: "A gentle, closed-mouth smile, the way you smile when greeting someone." })
					] }),
					/* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("td", { children: "4" }),
						/* @__PURE__ */ u("td", { children: "Turned slightly to your left (about the angle of glancing at a clock on the wall). Eyes still on the lens." }),
						/* @__PURE__ */ u("td", { children: "Relaxed, mouth closed." })
					] }),
					/* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("td", { children: "5" }),
						/* @__PURE__ */ u("td", { children: "Turned slightly to your right, the same small amount. Eyes still on the lens." }),
						/* @__PURE__ */ u("td", { children: "Relaxed, mouth closed." })
					] })
				] })]
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "If a photo comes out blurry, with eyes closed, or badly lit, simply take that one again."
			}),
			/* @__PURE__ */ u("h2", { children: "What matters most" }),
			/* @__PURE__ */ u("ol", {
				className: "tips",
				children: [
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Your face fills a good part of the picture." }), " Head and shoulders only. Leave about a hand's width of space above your head and some space on each side, because the face moves slightly in the video."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Eyes on the lens, not the screen." }), " Look at the small camera dot above the screen. Keep your eyes open and relaxed, not wide."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Mouth closed or only slightly open." }), " The app makes the mouth movements itself. A big smile or open mouth \"freezes\" your teeth into every word."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Soft, even light on both sides of your face." }), " Avoid one side in shadow, shiny spots on your forehead, or a bright window behind you."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Sharp, not blurry." }), " Hold still for the moment the photo is taken. Clean the lens first."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Nothing covering your face." }), " No hands near your face, hair out of your eyes, no hat, sunglasses or mask. Normal glasses are fine without glare."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Camera at eye level." }), " Sit up straight with your shoulders relaxed and level."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Plain, tidy background." }), " Avoid busy shelves, mirrors, posters, or other people behind you."] }),
					/* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("b", { children: "Look like yourself on a normal day." }), " Solid colours look better than busy patterns. This is how the video version of you will look."] })
				]
			})
		] })
	},
	{
		title: "How to take the photos",
		body: (laptop) => /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u(For, {
			laptop,
			only: ["win10", "win11"],
			children: [
				/* @__PURE__ */ u("h2", { children: "Windows 10 and Windows 11: the Camera app" }),
				/* @__PURE__ */ u("ol", {
					className: "tips",
					children: [
						/* @__PURE__ */ u("li", { children: "Click the Start button, or press the Windows key on your keyboard." }),
						/* @__PURE__ */ u("li", { children: [
							"Type ",
							/* @__PURE__ */ u("b", { children: "Camera" }),
							". When the Camera app appears in the list, click it."
						] }),
						/* @__PURE__ */ u("li", { children: [
							"If asked \"Let Camera access your camera?\" or similar, click ",
							/* @__PURE__ */ u("b", { children: "Yes" }),
							" or ",
							/* @__PURE__ */ u("b", { children: "Allow" }),
							". Your face now appears on the screen."
						] }),
						/* @__PURE__ */ u("li", { children: "Make sure the app is in photo mode, not video. If the round button on the right shows a video camera, click the small camera icon next to it." }),
						/* @__PURE__ */ u("li", { children: "Sit back so your head and shoulders fit in the picture. Look at the small camera lens above the screen." }),
						/* @__PURE__ */ u("li", { children: [
							"Click the round ",
							/* @__PURE__ */ u("b", { children: "Take photo" }),
							" button. You hear a shutter sound, and a small preview appears in a corner."
						] }),
						/* @__PURE__ */ u("li", { children: "Take the rest of the 5 photos from the previous step, one after another." }),
						/* @__PURE__ */ u("li", { children: "To look at them, click the small preview in the corner. Close the Camera app when you are done." })
					]
				}),
				/* @__PURE__ */ u("p", {
					className: "muted",
					children: [
						"The photos are saved in your ",
						/* @__PURE__ */ u("b", { children: "Pictures" }),
						" folder, inside ",
						/* @__PURE__ */ u("b", { children: "Camera Roll" }),
						". For a sharper photo, click the gear icon (Settings) and choose the largest size under Photo quality."
					]
				})
			]
		}), /* @__PURE__ */ u(For, {
			laptop,
			only: ["mac"],
			children: [/* @__PURE__ */ u("h2", { children: "Mac: the Photo Booth app" }), /* @__PURE__ */ u("ol", {
				className: "tips",
				children: [
					/* @__PURE__ */ u("li", { children: [
						"Press ",
						/* @__PURE__ */ u("b", { children: "Command + Space" }),
						" together. A search bar appears."
					] }),
					/* @__PURE__ */ u("li", { children: [
						"Type ",
						/* @__PURE__ */ u("b", { children: "Photo Booth" }),
						" and press Return. Your face appears and a small green light turns on next to the camera."
					] }),
					/* @__PURE__ */ u("li", { children: "In the bottom left corner, click the left of the three small buttons (a single square), so the app takes one photo, not four." }),
					/* @__PURE__ */ u("li", { children: "If you see an Effects button, make sure no effect is chosen (\"Normal\")." }),
					/* @__PURE__ */ u("li", { children: "Sit back so your head and shoulders fit in the picture. Look at the camera lens above the screen." }),
					/* @__PURE__ */ u("li", { children: "Click the red camera button. Photo Booth counts down 3, 2, 1, the screen flashes white, and the photo is taken." }),
					/* @__PURE__ */ u("li", { children: "Take the rest of the 5 photos from the previous step. They appear as small pictures along the bottom." }),
					/* @__PURE__ */ u("li", { children: [
						"Save each photo to the Desktop: click it, then choose ",
						/* @__PURE__ */ u("b", { children: "File > Export" }),
						", choose Desktop, name it (such as Photo 1) and click Save. Or drag each small picture onto your Desktop."
					] })
				]
			})]
		})] })
	},
	{
		title: "Record your voice",
		body: () => /* @__PURE__ */ u(S, { children: [
			/* @__PURE__ */ u("p", { children: "The guide has 7 recordings, one for each of the next steps; the first 3 are the ones needed today. Record a section, stop, listen to check it, and only then move on. If a section goes wrong, just record that section again; you never have to start over." }),
			/* @__PURE__ */ u("table", {
				className: "guide-table",
				children: [/* @__PURE__ */ u("thead", { children: /* @__PURE__ */ u("tr", { children: [
					/* @__PURE__ */ u("th", { children: "Recording" }),
					/* @__PURE__ */ u("th", { children: "What you say" }),
					/* @__PURE__ */ u("th", { children: "About" })
				] }) }), /* @__PURE__ */ u("tbody", { children: [
					/* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("td", { children: "Voice 1" }),
						/* @__PURE__ */ u("td", { children: "Read script lines 1 to 10" }),
						/* @__PURE__ */ u("td", { children: "1½ minutes" })
					] }),
					/* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("td", { children: "Voice 2" }),
						/* @__PURE__ */ u("td", { children: "Read script lines 11 to 19" }),
						/* @__PURE__ */ u("td", { children: "1½ minutes" })
					] }),
					/* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("td", { children: "Voice 3" }),
						/* @__PURE__ */ u("td", { children: "Answer 2 or 3 questions in your own words" }),
						/* @__PURE__ */ u("td", { children: "1 minute" })
					] }),
					/* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("td", { children: "Voice 4" }),
						/* @__PURE__ */ u("td", { children: "Read a short story" }),
						/* @__PURE__ */ u("td", { children: "3 minutes" })
					] }),
					/* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("td", { children: "Voice 5" }),
						/* @__PURE__ */ u("td", { children: "Read script lines 20 to 39" }),
						/* @__PURE__ */ u("td", { children: "3 minutes" })
					] }),
					/* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("td", { children: "Voice 6" }),
						/* @__PURE__ */ u("td", { children: "Read a short explanation" }),
						/* @__PURE__ */ u("td", { children: "3 minutes" })
					] }),
					/* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("td", { children: "Voice 7" }),
						/* @__PURE__ */ u("td", { children: "Answer 4 or 5 questions in your own words" }),
						/* @__PURE__ */ u("td", { children: "2 minutes" })
					] })
				] })]
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "The times are the length of each whole recording, from Record to Stop. You can take breaks between recordings, as long as you use the same room, microphone and distance."
			}),
			/* @__PURE__ */ u("p", {
				className: "notice",
				children: "Recordings 1 to 3 (about 4 minutes) are enough for the voice today. Recordings 4 to 7 do not change today's voice: they are kept so a closer, trained copy of your voice can be made later without recording again. If you are short on time, stop after Recording 3."
			}),
			/* @__PURE__ */ u("h2", { children: "How to speak" }),
			/* @__PURE__ */ u("ul", {
				className: "bullets",
				children: [
					/* @__PURE__ */ u("li", { children: "Use your normal, relaxed voice, the way you talk to a friend." }),
					/* @__PURE__ */ u("li", { children: "Speak at a natural, everyday pace. Pause about 1 second (one breath) after each line." }),
					/* @__PURE__ */ u("li", { children: "Small slip? Don't stop. Pause for a second, then say that line again and carry on." }),
					/* @__PURE__ */ u("li", { children: "Lots of slips, or a noise (cough, phone, dog)? Stop, delete that recording, and record that section again." }),
					/* @__PURE__ */ u("li", { children: "Only your voice should be on the recording. Ask others in the house to stay quiet." })
				]
			}),
			/* @__PURE__ */ u("h2", { children: "First, a 10-second test" }),
			/* @__PURE__ */ u("p", { children: "Record yourself saying \"Hello, this is a test\" and play it back. If it sounds muffled, quiet or echoey, move closer to the laptop or try a different room." })
		] })
	},
	{
		title: "How to make each recording",
		body: (laptop) => /* @__PURE__ */ u(S, { children: [
			/* @__PURE__ */ u("p", { children: "You repeat these \"record, stop, check, rename\" steps seven times, once for each recording." }),
			/* @__PURE__ */ u(For, {
				laptop,
				only: ["win10"],
				children: [
					/* @__PURE__ */ u("h2", { children: "Windows 10: the Voice Recorder app" }),
					/* @__PURE__ */ u("ol", {
						className: "tips",
						children: [
							/* @__PURE__ */ u("li", { children: [
								"Press the Windows key, type ",
								/* @__PURE__ */ u("b", { children: "Voice Recorder" }),
								", and click the app."
							] }),
							/* @__PURE__ */ u("li", { children: [
								"If asked to allow the microphone, click ",
								/* @__PURE__ */ u("b", { children: "Yes" }),
								" or ",
								/* @__PURE__ */ u("b", { children: "Allow" }),
								"."
							] }),
							/* @__PURE__ */ u("li", { children: "Click the big round blue microphone button to start recording. A timer starts counting." }),
							/* @__PURE__ */ u("li", { children: [
								"Read that step's page only. At the end, click the round ",
								/* @__PURE__ */ u("b", { children: "Stop" }),
								" button. The recording appears in the list on the left."
							] }),
							/* @__PURE__ */ u("li", { children: "Click the recording and press Play. Listen to a few seconds at the start and the end." }),
							/* @__PURE__ */ u("li", { children: [
								"Rename it: right-click the recording, choose ",
								/* @__PURE__ */ u("b", { children: "Rename" }),
								", type Voice 1 (then Voice 2 and so on) and press Enter."
							] }),
							/* @__PURE__ */ u("li", { children: "Not happy with it? Right-click it, choose Delete, and record that section again." })
						]
					}),
					/* @__PURE__ */ u("p", {
						className: "muted",
						children: [
							"The recordings are saved in ",
							/* @__PURE__ */ u("b", { children: "Documents" }),
							", inside ",
							/* @__PURE__ */ u("b", { children: "Sound recordings" }),
							", as .m4a files. Can't find Voice Recorder? Get \"Windows Voice Recorder\" free from the Microsoft Store."
						]
					})
				]
			}),
			/* @__PURE__ */ u(For, {
				laptop,
				only: ["win11"],
				children: [
					/* @__PURE__ */ u("h2", { children: "Windows 11: the Sound Recorder app" }),
					/* @__PURE__ */ u("ol", {
						className: "tips",
						children: [
							/* @__PURE__ */ u("li", { children: [
								"Press the Windows key, type ",
								/* @__PURE__ */ u("b", { children: "Sound Recorder" }),
								", and click the app."
							] }),
							/* @__PURE__ */ u("li", { children: [
								"If asked to allow the microphone, click ",
								/* @__PURE__ */ u("b", { children: "Yes" }),
								" or ",
								/* @__PURE__ */ u("b", { children: "Allow" }),
								"."
							] }),
							/* @__PURE__ */ u("li", { children: [
								"One time only: click the three dots (···) at the top right, choose Settings, set Recording format to ",
								/* @__PURE__ */ u("b", { children: "WAV" }),
								" (if shown) and Audio quality to ",
								/* @__PURE__ */ u("b", { children: "High" }),
								". Click the back arrow."
							] }),
							/* @__PURE__ */ u("li", { children: "If you use a headset or plug-in mic, pick it from the microphone list at the bottom left." }),
							/* @__PURE__ */ u("li", { children: [
								"Click the big round red ",
								/* @__PURE__ */ u("b", { children: "Record" }),
								" button. A timer starts counting."
							] }),
							/* @__PURE__ */ u("li", { children: [
								"Read that step's page only. At the end, click the square ",
								/* @__PURE__ */ u("b", { children: "Stop" }),
								" button."
							] }),
							/* @__PURE__ */ u("li", { children: "Click the recording and press Play. Listen to a few seconds at the start and the end." }),
							/* @__PURE__ */ u("li", { children: [
								"Rename it: right-click it, choose ",
								/* @__PURE__ */ u("b", { children: "Rename" }),
								", type Voice 1 (then Voice 2 and so on) and press Enter."
							] }),
							/* @__PURE__ */ u("li", { children: "Not happy with it? Right-click it, choose Delete, and record that section again." })
						]
					}),
					/* @__PURE__ */ u("p", {
						className: "muted",
						children: [
							"The recordings are saved in ",
							/* @__PURE__ */ u("b", { children: "Documents" }),
							", inside ",
							/* @__PURE__ */ u("b", { children: "Sound recordings" }),
							", as .wav or .m4a files. Either is fine."
						]
					})
				]
			}),
			/* @__PURE__ */ u(For, {
				laptop,
				only: ["mac"],
				children: [
					/* @__PURE__ */ u("h2", { children: "Mac: the Voice Memos app" }),
					/* @__PURE__ */ u("ol", {
						className: "tips",
						children: [
							/* @__PURE__ */ u("li", { children: [
								"Press ",
								/* @__PURE__ */ u("b", { children: "Command + Space" }),
								", type ",
								/* @__PURE__ */ u("b", { children: "Voice Memos" }),
								", and press Return."
							] }),
							/* @__PURE__ */ u("li", { children: [
								"If asked to allow the microphone, click ",
								/* @__PURE__ */ u("b", { children: "OK" }),
								" or ",
								/* @__PURE__ */ u("b", { children: "Allow" }),
								"."
							] }),
							/* @__PURE__ */ u("li", { children: [
								"One time only: choose ",
								/* @__PURE__ */ u("b", { children: "Voice Memos > Settings" }),
								" (Preferences on older Macs) and set Audio Quality to ",
								/* @__PURE__ */ u("b", { children: "Lossless" }),
								"."
							] }),
							/* @__PURE__ */ u("li", { children: [
								"Click the big round red ",
								/* @__PURE__ */ u("b", { children: "Record" }),
								" button at the bottom left."
							] }),
							/* @__PURE__ */ u("li", { children: [
								"Read that step's page only. At the end, click ",
								/* @__PURE__ */ u("b", { children: "Done" }),
								"."
							] }),
							/* @__PURE__ */ u("li", { children: "Click the recording and press Play. Listen to a few seconds at the start and the end." }),
							/* @__PURE__ */ u("li", { children: "Rename it: double-click its name, type Voice 1 (then Voice 2 and so on) and press Return." }),
							/* @__PURE__ */ u("li", { children: "Not happy with it? Click it, press Delete, and record that section again." }),
							/* @__PURE__ */ u("li", { children: "Drag the recording from the list onto your Desktop. A file ending in .m4a appears there." })
						]
					}),
					/* @__PURE__ */ u("p", {
						className: "muted",
						children: "Do not click the magic-wand Enhance Recording button, and do not add effects."
					})
				]
			}),
			/* @__PURE__ */ u("p", {
				className: "notice",
				children: "Leave \"clean-up\" features off. Noise reduction, voice clarity, voice focus or \"enhance\" options make the voice worse for this. The plain, natural sound gives the best result."
			})
		] })
	},
	{
		title: "Recording 1 of 7",
		body: () => /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u(Before, {
			name: "Voice 1",
			minutes: "1½ minutes"
		}), /* @__PURE__ */ u(Script, {
			first: 1,
			lines: [
				"Hi, thanks for stopping by. It's good to see you.",
				"I wasn't sure what to expect today, but honestly, I'm glad you asked.",
				"Let me think about that for a second. Okay, here's what I'd do.",
				"First, take a deep breath. Second, write down the three things that matter most. Third, pick one and start there.",
				"Really? You found it in the garage, behind the old bicycle? That's amazing!",
				"No, no, that's not what I meant at all. I meant the other one, the blue one.",
				"The weather this weekend should be cool and breezy, with a chance of rain on Sunday afternoon.",
				"My favourite meal is still my grandmother's soup, with fresh bread and a little too much butter.",
				"She sells seashells by the seashore, and the shells she sells are surely seashells.",
				"The quick brown fox jumps over the lazy dog, and the dog doesn't seem to mind."
			]
		})] })
	},
	{
		title: "Recording 2 of 7",
		body: () => /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u(Before, {
			name: "Voice 2",
			minutes: "1½ minutes"
		}), /* @__PURE__ */ u(Script, {
			first: 11,
			lines: [
				"Could you call me back around four thirty? My number is five five five, two nine one, eight three zero seven.",
				"It cost about twelve dollars and fifty cents, which felt fair for what it was.",
				"Hmm, I'm not totally sure. I think it was in two thousand nineteen, but don't quote me on that.",
				"Wow. That is genuinely the best news I've heard all week.",
				"I'm sorry to hear that. That sounds really hard, and it makes sense that you're tired.",
				"Here's a fun fact: an octopus has three hearts and blue blood.",
				"Would you like the short version, or the long version with all the details?",
				"Measure twice, cut once. My father used to say that, and he was usually right.",
				"Thanks for listening. Take care of yourself, and let's talk again soon."
			]
		})] })
	},
	{
		title: "Recording 3 of 7",
		body: () => /* @__PURE__ */ u(S, { children: [
			/* @__PURE__ */ u(Before, {
				name: "Voice 3",
				minutes: "1 minute",
				children: "Choose two or three of the questions below. Press Record and answer them out loud in your own words, as if chatting with a friend, for about 20 to 30 seconds each. Pause for a second between questions."
			}),
			/* @__PURE__ */ u(Questions, { items: [
				"What did you do last weekend?",
				"Describe a place you love and why.",
				"Explain how to make something you cook often.",
				"What's something you've changed your mind about?"
			] }),
			/* @__PURE__ */ u("p", {
				className: "notice",
				children: [
					"Short on time? You can stop here: Recordings 1 to 3 are enough for today's voice. Use",
					" ",
					/* @__PURE__ */ u("b", { children: "Go to step" }),
					" below to jump to ",
					/* @__PURE__ */ u("b", { children: "Check your recordings" }),
					"."
				]
			})
		] })
	},
	{
		title: "Recording 4 of 7",
		body: () => /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u(Before, {
			name: "Voice 4",
			minutes: "3 minutes",
			children: "Press Record. Read the story at a relaxed, natural pace, as if reading to a friend. Pause about 1 second between paragraphs. If you stumble, pause and reread that sentence."
		}), /* @__PURE__ */ u("div", {
			className: "story",
			children: [
				/* @__PURE__ */ u("p", { children: "Every Saturday morning, my neighbour Ruth walks her old dog, Biscuit, down to the bakery on the corner. Biscuit is twelve years old, mostly grey around the nose, and moves at exactly one speed: slow. Ruth says that suits her just fine." }),
				/* @__PURE__ */ u("p", { children: "Last spring, the bakery changed owners. The new baker, a quiet young man named Theo, didn't know about Biscuit. On his first Saturday, he looked up from the counter to find a dog sitting politely by the door, staring at the shelf of day-old rolls." }),
				/* @__PURE__ */ u("p", { children: "\"Is he waiting for someone?\" Theo asked. Ruth laughed. \"He's waiting for you. The last owner gave him the end of a loaf every week. I think he expects the tradition to continue.\"" }),
				/* @__PURE__ */ u("p", { children: "Theo thought about it for a moment, then broke off a small piece of crust and crouched down. Biscuit took it gently, wagged his tail twice, and walked straight back out the door. Ruth apologised and hurried after him." }),
				/* @__PURE__ */ u("p", { children: "The next Saturday, Theo had a paper bag ready, with \"Biscuit\" written on it in thick black marker. The Saturday after that, he added a second bag for Ruth: two warm cinnamon buns and a note that said, \"For the person holding the leash.\"" }),
				/* @__PURE__ */ u("p", { children: "By summer, half the street knew the story. Children waved at Biscuit through the window. A man from the hardware store brought a water bowl for the doorstep. Somebody even painted a small sign, shaped like a bone, that read: \"Dogs welcome. Especially Biscuit.\"" }),
				/* @__PURE__ */ u("p", { children: "I asked Ruth once why she thought the whole thing had caught on. She shrugged and said, \"People like a routine they can count on. And everybody likes being expected.\" Then she checked her watch, because it was almost nine o'clock, and Biscuit was already standing by the door." })
			]
		})] })
	},
	{
		title: "Recording 5 of 7",
		body: () => /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u(Before, {
			name: "Voice 5",
			minutes: "3 minutes"
		}), /* @__PURE__ */ u(Script, {
			first: 20,
			lines: [
				"Good morning! Did you sleep well, or were the neighbours noisy again?",
				"That's a fair question, and I don't have a perfect answer, but I'll do my best.",
				"Wait, say that again? I think I missed the most important part.",
				"The train leaves at seven fifteen from platform nine, so we should be there by seven.",
				"Honestly, I loved the first half of the film, but the ending felt rushed.",
				"If you add a pinch of salt to the water, the pasta tastes much better.",
				"Oh no, I left my umbrella on the bus. Typical!",
				"Let's keep it simple: one page, three ideas, and a clear next step.",
				"She was born on the fourth of July, nineteen eighty-six, in a small town by the river.",
				"Are you sure? Because yesterday you told me the opposite.",
				"Thank you so much. That was incredibly kind, and I won't forget it.",
				"The library opens at ten, closes at six, and is shut on Mondays.",
				"Please don't worry about it. These things happen to everyone.",
				"Which would you rather have: a quiet cabin in the woods, or a flat in the middle of the city?",
				"Turn left at the lights, go past the petrol station, and it's the third house on the right.",
				"I can't believe it's already October. Where did the year go?",
				"Bright yellow jackets, thick woollen gloves, and very wet boots.",
				"The answer is forty-two, but nobody remembers what the question was.",
				"Hmm. Let me check my notes, and I'll get back to you this afternoon.",
				"That's everything for now. Thanks again, and have a lovely evening."
			]
		})] })
	},
	{
		title: "Recording 6 of 7",
		body: () => /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u(Before, {
			name: "Voice 6",
			minutes: "3 minutes",
			children: "Press Record. Read it as if you were explaining it to a curious friend. Pause about 1 second between paragraphs."
		}), /* @__PURE__ */ u("div", {
			className: "story",
			children: [
				/* @__PURE__ */ u("p", { children: "Have you ever wondered why the sky is blue during the day, but red and orange at sunset? The answer has to do with sunlight, and with the air itself." }),
				/* @__PURE__ */ u("p", { children: "Sunlight looks white, but it is really a mixture of every colour of the rainbow. Each colour travels as a wave, and the waves have different lengths. Red light has long, lazy waves. Blue and violet light have short, quick ones." }),
				/* @__PURE__ */ u("p", { children: "When sunlight enters the air, it bumps into tiny gas molecules, mostly nitrogen and oxygen. These molecules are far too small to see, but they scatter short waves much more strongly than long ones. So blue light bounces around the sky in every direction, and wherever you look, some of it reaches your eyes. That is why the whole sky seems to glow blue." }),
				/* @__PURE__ */ u("p", { children: "You might ask: if violet waves are even shorter, why isn't the sky violet? There are two reasons. First, the sun gives off less violet light than blue. Second, our eyes are simply more sensitive to blue. Put those together, and blue wins." }),
				/* @__PURE__ */ u("p", { children: "Now think about sunset. When the sun is low, its light has to travel through much more air before it reaches you, sometimes forty times as much as at midday. Along that long path, most of the blue light is scattered away to the sides. What is left is the light that scatters least: the yellows, oranges and deep reds." }),
				/* @__PURE__ */ u("p", { children: "Dust, smoke and tiny water droplets can make sunsets even more dramatic, because they add their own scattering and colour. After a large volcanic eruption, people around the world have seen unusually vivid sunsets for months." }),
				/* @__PURE__ */ u("p", { children: "So the next time you watch the sky change colour in the evening, remember: you are watching sunlight take the long way home." })
			]
		})] })
	},
	{
		title: "Recording 7 of 7",
		body: () => /* @__PURE__ */ u(S, { children: [
			/* @__PURE__ */ u(Before, {
				name: "Voice 7",
				minutes: "2 minutes",
				children: "Choose four or five of the questions below, different from the ones in Recording 3. Press Record and answer them out loud in your own words, for about 20 to 30 seconds each. Pause for a second between questions."
			}),
			/* @__PURE__ */ u(Questions, { items: [
				"What was your first job, and what did you learn from it?",
				"Describe your ideal day off, from morning to night.",
				"Tell a short story about a time something went wrong but turned out fine.",
				"What's a book, film or song you'd recommend, and why?",
				"Explain how to get from your home to a shop or café you like.",
				"If you could learn any skill instantly, what would it be?",
				"What's the best piece of advice anyone has given you?"
			] }),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "Optional: is English not your first language? Make one more recording of about 1 minute talking about anything in your first language, and name it Voice 8. It helps capture the sound of your voice."
			})
		] })
	},
	{
		title: "Check your recordings",
		body: () => /* @__PURE__ */ u("ul", {
			className: "checklist",
			children: [
				/* @__PURE__ */ u("li", { children: "You have at least Voice 1, Voice 2 and Voice 3. These are all today's voice needs. Voice 4 to Voice 7 (and Voice 8) are extra, if you made them." }),
				/* @__PURE__ */ u("li", { children: "Voice 1 and Voice 2 are each about 1 to 2 minutes long; Voice 3 is about 1 minute. If you made them, Voice 4, 5 and 6 are each about 3 minutes and Voice 7 is about 2 minutes." }),
				/* @__PURE__ */ u("li", { children: "When you play them back, your voice is clear and easy to hear." }),
				/* @__PURE__ */ u("li", { children: "There is no music, TV, other voices or loud background hum." }),
				/* @__PURE__ */ u("li", { children: "If one of them went wrong, delete just that one and record that section again." })
			]
		})
	},
	{
		title: "Add your files to the app",
		body: (laptop) => /* @__PURE__ */ u(S, { children: [
			/* @__PURE__ */ u("p", { children: "Find your 5 photos and your recordings (Voice 1 to Voice 3, plus any extra ones you made), then add them on the Setup page." }),
			/* @__PURE__ */ u(For, {
				laptop,
				only: ["win10", "win11"],
				children: [/* @__PURE__ */ u("h2", { children: "Windows" }), /* @__PURE__ */ u("ul", {
					className: "bullets",
					children: [
						/* @__PURE__ */ u("li", { children: [
							"Photos: in the file picker, open ",
							/* @__PURE__ */ u("b", { children: "Pictures" }),
							", then ",
							/* @__PURE__ */ u("b", { children: "Camera Roll" }),
							". Your 5 photos are the newest ones."
						] }),
						/* @__PURE__ */ u("li", { children: [
							"Recordings: open ",
							/* @__PURE__ */ u("b", { children: "Documents" }),
							", then ",
							/* @__PURE__ */ u("b", { children: "Sound recordings" }),
							". You should see Voice 1, Voice 2 and Voice 3, and any extra ones you made."
						] }),
						/* @__PURE__ */ u("li", { children: [
							"Can't find them? Pictures and Documents may be inside a OneDrive folder. Type ",
							/* @__PURE__ */ u("b", { children: "Camera Roll" }),
							" or ",
							/* @__PURE__ */ u("b", { children: "Sound recordings" }),
							" in the search box at the top right."
						] })
					]
				})]
			}),
			/* @__PURE__ */ u(For, {
				laptop,
				only: ["mac"],
				children: [/* @__PURE__ */ u("h2", { children: "Mac" }), /* @__PURE__ */ u("p", { children: "Your photos and recordings are on your Desktop (you put them there in the earlier steps)." })]
			}),
			/* @__PURE__ */ u("ol", {
				className: "tips",
				children: [
					/* @__PURE__ */ u("li", { children: [
						"On the Setup page, click ",
						/* @__PURE__ */ u("b", { children: "Add photos" }),
						" and choose all 5 photos at once."
					] }),
					/* @__PURE__ */ u("li", { children: [
						"Click ",
						/* @__PURE__ */ u("b", { children: "Add recordings" }),
						" and choose all your recordings at once: Voice 1 to Voice 3, plus Voice 4 to Voice 8 if you made them."
					] }),
					/* @__PURE__ */ u("li", { children: "Each file is checked as it arrives. If one needs fixing, the page says what to change; take or record that one again and add it." })
				]
			}),
			/* @__PURE__ */ u("a", {
				className: "button",
				href: "#/setup",
				children: "Go to setup"
			})
		] })
	},
	{
		title: "If something goes wrong",
		body: () => /* @__PURE__ */ u("table", {
			className: "guide-table",
			children: [/* @__PURE__ */ u("thead", { children: /* @__PURE__ */ u("tr", { children: [/* @__PURE__ */ u("th", { children: "Problem" }), /* @__PURE__ */ u("th", { children: "What to try" })] }) }), /* @__PURE__ */ u("tbody", { children: [
				/* @__PURE__ */ u("tr", { children: [/* @__PURE__ */ u("td", { children: "The camera shows a black screen or \"We can't find your camera\"" }), /* @__PURE__ */ u("td", { children: "Some laptops have a sliding cover over the camera, or a camera on/off key. Slide the cover open or press the key. Close any other app that might use the camera (Zoom, Teams, Skype, FaceTime) and try again." })] }),
				/* @__PURE__ */ u("tr", { children: [/* @__PURE__ */ u("td", { children: "Windows: I clicked \"No\" when asked about the camera or microphone" }), /* @__PURE__ */ u("td", { children: [
					"Press the Windows key, type ",
					/* @__PURE__ */ u("b", { children: "Camera privacy settings" }),
					" (or ",
					/* @__PURE__ */ u("b", { children: "Microphone privacy settings" }),
					") and open it. Turn on access, and make sure Camera, Voice Recorder or Sound Recorder is switched on."
				] })] }),
				/* @__PURE__ */ u("tr", { children: [/* @__PURE__ */ u("td", { children: "Mac: I clicked \"Don't Allow\"" }), /* @__PURE__ */ u("td", { children: "Apple menu > System Settings > Privacy & Security. Click Camera or Microphone and switch on Photo Booth or Voice Memos." })] }),
				/* @__PURE__ */ u("tr", { children: [/* @__PURE__ */ u("td", { children: "The photo is dark or has strong shadows" }), /* @__PURE__ */ u("td", { children: "Face a window or put a lamp behind the laptop, shining toward your face. Turn off bright lights behind you." })] }),
				/* @__PURE__ */ u("tr", { children: [/* @__PURE__ */ u("td", { children: "The photo is blurry" }), /* @__PURE__ */ u("td", { children: "Wipe the camera lens, sit still, and make sure the room is bright." })] }),
				/* @__PURE__ */ u("tr", { children: [/* @__PURE__ */ u("td", { children: "The recording timer doesn't move, or playback is silent" }), /* @__PURE__ */ u("td", { children: "Check that the microphone is allowed (see above). Plug a headset in before opening the app. On Windows 11 Sound Recorder, check the microphone chosen at the bottom left." })] }),
				/* @__PURE__ */ u("tr", { children: [/* @__PURE__ */ u("td", { children: "The recording sounds echoey or noisy" }), /* @__PURE__ */ u("td", { children: "Move to a smaller room with soft furniture, curtains or carpet. A walk-in closet works very well. Turn off fans and air conditioning." })] }),
				/* @__PURE__ */ u("tr", { children: [/* @__PURE__ */ u("td", { children: "I can't find Voice Recorder or Sound Recorder (Windows)" }), /* @__PURE__ */ u("td", { children: "Open the Microsoft Store, search for \"Sound Recorder\" or \"Windows Voice Recorder\", and click Get. It is free." })] }),
				/* @__PURE__ */ u("tr", { children: [/* @__PURE__ */ u("td", { children: "I can't find my files" }), /* @__PURE__ */ u("td", { children: "Windows: in File Explorer, type the file name, Camera Roll or Sound recordings in the search box at the top right. Mac: press Command + Space and type the file name." })] })
			] })]
		})
	}
];
function GuidePage() {
	const [state, setState] = d(loadGuide);
	const { step, laptop } = state;
	h(() => {
		saveGuide(state);
	}, [state]);
	function go(to) {
		setState({
			...state,
			step: to
		});
		console.info(`Guide step ${to + 1} of ${STEPS.length}: ${STEPS[to].title}`);
		window.scrollTo?.({ top: 0 });
	}
	function pick(l) {
		setState({
			...state,
			laptop: l
		});
		console.info(`Guide laptop: ${l}`);
	}
	const current = STEPS[step];
	const last = step === STEPS.length - 1;
	return /* @__PURE__ */ u("section", {
		className: "guide",
		children: [
			/* @__PURE__ */ u("div", {
				className: "guide-top",
				children: [/* @__PURE__ */ u("a", {
					className: "return",
					href: "#/setup",
					children: "← Return to Setup page"
				}), /* @__PURE__ */ u("p", {
					className: "muted step-count",
					children: [
						"Recording guide · Step ",
						step + 1,
						" of ",
						STEPS.length
					]
				})]
			}),
			/* @__PURE__ */ u("progress", {
				value: step + 1,
				max: STEPS.length,
				"aria-label": "Guide progress"
			}),
			/* @__PURE__ */ u("h1", { children: current.title }),
			current.body(laptop, pick),
			/* @__PURE__ */ u("div", {
				className: "guide-nav",
				children: [/* @__PURE__ */ u("button", {
					type: "button",
					className: "secondary",
					disabled: step === 0,
					onClick: () => go(step - 1),
					children: "Back"
				}), !last && /* @__PURE__ */ u("button", {
					type: "button",
					onClick: () => go(step + 1),
					children: ["Next: ", STEPS[step + 1].title]
				})]
			}),
			/* @__PURE__ */ u("label", {
				className: "jump",
				children: [
					"Go to step",
					" ",
					/* @__PURE__ */ u("select", {
						value: step,
						onChange: (e) => go(Number(e.currentTarget.value)),
						children: STEPS.map((s, i) => /* @__PURE__ */ u("option", {
							value: i,
							children: [
								i + 1,
								". ",
								s.title
							]
						}, s.title))
					})
				]
			}),
			/* @__PURE__ */ u("p", {
				className: "guide-bottom",
				children: /* @__PURE__ */ u("a", {
					className: "return",
					href: "#/setup",
					children: "← Return to Setup page"
				})
			})
		]
	});
}
//#endregion
//#region src/home.tsx
async function loadHome(consented) {
	if (!consented) {
		console.info("Home loaded (setup not started: no consent yet)");
		return {
			done: false,
			photo: null
		};
	}
	const started = performance.now();
	try {
		const [review, choice] = await Promise.all([getReview(), getPhotoChoice()]);
		const state = {
			done: review.accepted,
			photo: review.accepted && choice.id ? uploadUrl("photos", choice.id) : null
		};
		console.info(`Home loaded in ${Math.round(performance.now() - started)} ms (setup ${state.done ? "done" : "not done"})`);
		return state;
	} catch (e) {
		console.error("Could not load the home page's setup state", e);
		return {
			done: false,
			photo: null
		};
	}
}
function choices(done, consented) {
	const setupHref = consented ? "#/setup" : "#/consent";
	if (!done) return [{
		href: setupHref,
		title: "Start setup",
		text: "Add photos and voice recordings, then review a sample video of the person speaking."
	}];
	return [
		{
			href: "#/chat",
			title: "Chat",
			text: "Ask a question. The person answers in their own voice and face."
		},
		{
			href: "#/content",
			title: "Manage Content",
			text: "Add, replace or remove the PDFs that answers come from."
		},
		{
			href: setupHref,
			title: "Setup",
			text: "Change the photos, the voice recordings or the accent."
		}
	];
}
function HomePage({ consented }) {
	const [state, setState] = d(null);
	h(() => {
		loadHome(consented).then(setState);
	}, [consented]);
	if (state === null) return /* @__PURE__ */ u("p", {
		className: "muted busy",
		children: "Loading…"
	});
	return /* @__PURE__ */ u("section", {
		className: "home",
		children: [/* @__PURE__ */ u("div", {
			className: "hero",
			children: [state.photo && /* @__PURE__ */ u("img", {
				className: "portrait",
				src: state.photo,
				alt: "The person in the video"
			}), /* @__PURE__ */ u("div", { children: [/* @__PURE__ */ u("h1", { children: state.done ? "Welcome back" : "Welcome" }), /* @__PURE__ */ u("p", {
				className: "muted",
				children: state.done ? "Setup is done. Pick up where you left off." : "Make a talking video of a person from a few photos and voice recordings. The person then speaks the chatbot's replies."
			})] })]
		}), /* @__PURE__ */ u("ul", {
			className: state.done ? "choices three" : "choices",
			children: choices(state.done, consented).map((c) => /* @__PURE__ */ u("li", { children: /* @__PURE__ */ u("a", {
				href: c.href,
				children: [
					/* @__PURE__ */ u(ChoiceIcon, { href: c.href }),
					/* @__PURE__ */ u("span", {
						className: "title",
						children: c.title
					}),
					/* @__PURE__ */ u("span", {
						className: "text",
						children: c.text
					})
				]
			}) }, c.title))
		})]
	});
}
var ICONS = {
	"#/chat": "M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v6a2.5 2.5 0 0 1-2.5 2.5H11l-4 3.5V15h0.5A2.5 2.5 0 0 1 5 12.5z",
	"#/content": "M7 3.5h6.5L18 8v12.5H7zM13.5 3.5V8H18M9.5 12h6M9.5 15.5h6",
	setup: "M4 7h10M18 7h2M4 17h4M12 17h8M16 5v4M10 15v4"
};
function ChoiceIcon({ href }) {
	return /* @__PURE__ */ u("span", {
		className: "icon",
		"aria-hidden": "true",
		children: /* @__PURE__ */ u("svg", {
			viewBox: "0 0 24 24",
			fill: "none",
			stroke: "currentColor",
			"stroke-width": "1.8",
			"stroke-linejoin": "round",
			"stroke-linecap": "round",
			children: /* @__PURE__ */ u("path", { d: ICONS[href] ?? ICONS.setup })
		})
	});
}
//#endregion
//#region src/pages.tsx
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
var BACK_NOTICE = {
	photos: "You rejected the image. Add new photos and remove the ones you don't want, then Prepare again.",
	sounds: "You rejected the voice. Add new recordings and remove the ones you don't want, then Prepare again.",
	accent: "Choose another accent. The sample video is then made again."
};
function SetupPage() {
	const [changes, setChanges] = d(0);
	const changed = () => setChanges((n) => n + 1);
	const [preparing, setPreparing] = d(false);
	const [back, setBack] = d(null);
	function goBack(to) {
		setBack(to);
		window.setTimeout(() => document.getElementById(to)?.scrollIntoView?.({ behavior: "smooth" }));
	}
	const notice = (to) => back === to ? BACK_NOTICE[to] : null;
	return /* @__PURE__ */ u("div", {
		className: "teacher-page",
		children: [
			/* @__PURE__ */ u("h1", { children: "Setup" }),
			/* @__PURE__ */ u("p", {
				className: "lead",
				children: "Make the talking person in four steps: add photos, add voice recordings, choose an accent, then prepare a sample video and check it."
			}),
			/* @__PURE__ */ u("p", {
				className: "notice",
				children: [
					"New to this? The ",
					/* @__PURE__ */ u("a", {
						href: "#/guide",
						children: "recording guide"
					}),
					" walks you step by step through taking the photos and making the voice recordings on a Windows or Mac laptop."
				]
			}),
			/* @__PURE__ */ u(UploadSection, {
				kind: "photos",
				step: 1,
				title: "Photos",
				button: "Add photos",
				hint: "Add the five photos from the recording guide (JPG, PNG or HEIC). At least one is needed; the app will pick the best.",
				accept: "image/jpeg,image/png,image/heic,.heic",
				notice: notice("photos"),
				onChange: changed
			}),
			/* @__PURE__ */ u(UploadSection, {
				kind: "sounds",
				step: 2,
				title: "Voice recordings",
				button: "Add recordings",
				hint: "Add the voice recordings from the recording guide (WAV, M4A or MP3, up to 10 minutes each).",
				accept: "audio/*,.m4a,.wav,.mp3",
				notice: notice("sounds"),
				onChange: changed
			}),
			/* @__PURE__ */ u(AccentSection, {
				onChange: changed,
				preparing,
				notice: notice("accent")
			}),
			/* @__PURE__ */ u(PrepareSection, {
				changes,
				onRunning: setPreparing,
				onBack: goBack
			})
		]
	});
}
function StepOf({ n }) {
	return /* @__PURE__ */ u("p", {
		className: "step-of",
		children: [
			"Step ",
			n,
			" of 4"
		]
	});
}
function UploadSection(props) {
	const { kind } = props;
	const [items, setItems] = d(null);
	const [loadFailed, setLoadFailed] = d(false);
	const [sending, setSending] = d(null);
	const [refused, setRefused] = d([]);
	const [toCheck, setToCheck] = d([]);
	const [soundChanges, setSoundChanges] = d(0);
	const [choice, setChoice] = d(null);
	const [choosing, setChoosing] = d(null);
	const choiceRequests = A(0);
	async function refreshChoice() {
		if (kind !== "photos") return;
		const request = ++choiceRequests.current;
		try {
			const current = await getPhotoChoice();
			if (request === choiceRequests.current) setChoice(current);
		} catch (e) {
			console.error("Could not get the chosen photo", e);
		}
	}
	async function choose(item) {
		if (choosing !== null) return;
		const sent = ++choiceRequests.current;
		setChoosing(item.id);
		setRefused([]);
		try {
			const chosen = await choosePhoto(item.id);
			const readWhileSaving = choiceRequests.current > sent;
			++choiceRequests.current;
			setChoice(chosen);
			props.onChange();
			if (readWhileSaving) refreshChoice();
		} catch (e) {
			console.error(`Could not choose ${item.name}`, e);
			setRefused([{
				name: item.name,
				reason: e.message
			}]);
		}
		setChoosing(null);
	}
	h(() => {
		listUploads(kind).then((list) => {
			setItems(list);
			checkOld(list);
			refreshChoice();
		}).catch((e) => {
			console.error(`Could not list ${kind}`, e);
			setLoadFailed(true);
		});
	}, [kind]);
	function uploadsChanged() {
		if (kind === "sounds") setSoundChanges((n) => n + 1);
		props.onChange();
	}
	async function checkOld(list) {
		const unchecked = list.filter((u) => u.problems === null);
		setToCheck(unchecked.map((u) => u.id));
		for (const upload of unchecked) {
			try {
				const checked = await checkUpload(kind, upload.id);
				setItems((current) => (current ?? []).map((i) => i.id === checked.id ? checked : i));
				if (checked.problems === null) break;
				if (checked.problems.length === 0) {
					await refreshChoice();
					uploadsChanged();
				}
			} catch (e) {
				console.error(`Could not check ${upload.name}`, e);
			}
			setToCheck((ids) => ids.slice(1));
		}
		setToCheck([]);
	}
	async function add(event) {
		const input = event.currentTarget;
		const files = Array.from(input.files ?? []);
		input.value = "";
		setRefused([]);
		for (const file of files) {
			setSending(file.name);
			try {
				const upload = await uploadFile(kind, file);
				setItems((current) => [...current ?? [], upload]);
				if (upload.problems?.length === 0) {
					await refreshChoice();
					uploadsChanged();
				}
			} catch (e) {
				console.error(`Upload of ${file.name} refused`, e);
				setRefused((current) => [...current, {
					name: file.name,
					reason: e.message
				}]);
			}
		}
		setSending(null);
	}
	async function remove(item) {
		if (!window.confirm(`Remove ${item.name}?`)) return;
		try {
			await removeUpload(kind, item.id);
			setItems((current) => (current ?? []).filter((i) => i.id !== item.id));
			await refreshChoice();
			uploadsChanged();
		} catch (e) {
			console.error(`Could not remove ${item.name}`, e);
			setRefused([{
				name: item.name,
				reason: "Could not remove it. Please try again."
			}]);
		}
	}
	const ready = sending === null && (items !== null || loadFailed);
	const loading = items === null && !loadFailed;
	return /* @__PURE__ */ u("section", {
		id: kind,
		className: "panel",
		children: [
			/* @__PURE__ */ u(StepOf, { n: props.step }),
			/* @__PURE__ */ u("h2", { children: props.title }),
			props.notice && /* @__PURE__ */ u("p", {
				className: "notice",
				children: props.notice
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: props.hint
			}),
			/* @__PURE__ */ u("label", {
				className: ready ? "button" : "button busy",
				children: [sending ? `Uploading and checking ${sending}…` : loading ? "Loading…" : props.button, /* @__PURE__ */ u("input", {
					type: "file",
					multiple: true,
					accept: props.accept,
					disabled: !ready,
					onChange: add,
					className: "file"
				})]
			}),
			refused.map((r) => /* @__PURE__ */ u("p", {
				className: "error",
				children: [
					r.name,
					": ",
					r.reason
				]
			}, r.name)),
			loadFailed && /* @__PURE__ */ u("p", {
				className: "error",
				children: "Could not load the list. Reload the page to try again."
			}),
			loading && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: [
					"Loading your ",
					props.title.toLowerCase(),
					"…"
				]
			}),
			items?.length === 0 && /* @__PURE__ */ u("p", {
				className: "muted",
				children: "None yet."
			}),
			/* @__PURE__ */ u("ul", {
				className: kind,
				children: items?.map((item) => /* @__PURE__ */ u("li", {
					className: item.id === choice?.id ? "chosen" : void 0,
					children: [
						kind === "photos" ? /* @__PURE__ */ u("a", {
							href: uploadUrl(kind, item.id),
							target: "_blank",
							rel: "noreferrer",
							children: /* @__PURE__ */ u("img", {
								src: uploadUrl(kind, item.id),
								alt: item.name
							})
						}) : /* @__PURE__ */ u("audio", {
							controls: true,
							preload: "none",
							src: uploadUrl(kind, item.id)
						}),
						/* @__PURE__ */ u("span", {
							className: "name",
							children: [item.name, item.seconds !== null && ` (${minutes(item.seconds)})`]
						}),
						/* @__PURE__ */ u(Checks, {
							item,
							queue: toCheck.indexOf(item.id)
						}),
						kind === "photos" && item.id === choice?.id && /* @__PURE__ */ u("span", {
							className: "chosen-note",
							children: ["Used for the video", choice.chosen_by === "app" ? " (best score)" : " (your choice)"]
						}),
						kind === "photos" && item.problems?.length === 0 && item.id !== choice?.id && /* @__PURE__ */ u("button", {
							type: "button",
							className: choosing === item.id ? "use busy" : "use",
							onClick: () => choose(item),
							children: choosing === item.id ? "Saving…" : "Use this photo"
						}),
						/* @__PURE__ */ u("button", {
							type: "button",
							className: "remove",
							onClick: () => remove(item),
							children: "Remove"
						})
					]
				}, item.id))
			}),
			kind === "sounds" && /* @__PURE__ */ u(VoiceSampleView, { changes: soundChanges })
		]
	});
}
function Checks({ item, queue }) {
	const { problems, score, speech } = item;
	const what = item.kind === "photos" ? "photo" : "recording";
	if (queue === 0) return /* @__PURE__ */ u("span", {
		className: "muted check busy",
		children: [
			"Checking ",
			what,
			"…"
		]
	});
	if (queue > 0) return /* @__PURE__ */ u("span", {
		className: "muted check",
		children: "Waiting to check"
	});
	if (problems == null) return /* @__PURE__ */ u("span", {
		className: "muted check",
		children: "Not checked"
	});
	if (problems.length === 0) return /* @__PURE__ */ u("span", {
		className: "done check",
		children: [
			"Looks good",
			score !== null && ` · score ${score} of 100`,
			speech !== null && ` · ${minutes(speech)} of speech`
		]
	});
	return /* @__PURE__ */ u("ul", {
		className: "problems",
		children: problems.map((p) => /* @__PURE__ */ u("li", {
			className: "error",
			children: p
		}, p))
	});
}
function VoiceSampleView({ changes }) {
	const [sample, setSample] = d(null);
	h(() => {
		let newest = true;
		getVoiceSample().then((s) => {
			if (newest) setSample(s);
		}).catch((e) => console.error("Could not get the voice sample", e));
		return () => {
			newest = false;
		};
	}, [changes]);
	if (sample === null) return null;
	return /* @__PURE__ */ u("div", {
		className: "voice-sample",
		children: [
			/* @__PURE__ */ u("h3", { children: "Voice sample" }),
			sample.recordings > 0 && /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("audio", {
				controls: true,
				preload: "none",
				src: `/api/voice-sample/audio?v=${changes}`
			}), /* @__PURE__ */ u("p", {
				className: "name",
				children: [
					sample.recordings === 1 ? "Made from the recording that passed the checks" : `Made from the ${sample.recordings} recordings that passed the checks, in order`,
					": ",
					minutes(sample.speech),
					" of speech."
				]
			})] }),
			sample.problem === null ? /* @__PURE__ */ u("p", {
				className: "done",
				children: "Enough speech to make the voice."
			}) : /* @__PURE__ */ u("p", {
				className: sample.recordings > 0 ? "error" : "muted",
				children: sample.problem
			})
		]
	});
}
var ACCENTS = [
	{
		accent: "own",
		label: "Their own accent, as in the recordings"
	},
	{
		accent: "american",
		label: "American"
	},
	{
		accent: "british",
		label: "British"
	}
];
function AccentSection(props) {
	const { onChange, preparing } = props;
	const [choice, setChoice] = d(null);
	const [saving, setSaving] = d(null);
	const [failed, setFailed] = d(null);
	h(() => {
		getAccent().then(setChoice).catch((e) => {
			console.error("Could not get the accent", e);
			setFailed("Could not load the accent. Reload the page to try again.");
		});
	}, []);
	async function choose(accent) {
		setSaving(accent);
		setFailed(null);
		try {
			setChoice(await chooseAccent(accent));
			onChange();
		} catch (e) {
			console.error(`Could not choose the ${accent} accent`, e);
			setFailed(`Could not save the accent: ${e.message}`);
		}
		setSaving(null);
	}
	return /* @__PURE__ */ u("section", {
		className: "accent panel",
		id: "accent",
		children: [
			/* @__PURE__ */ u(StepOf, { n: 3 }),
			/* @__PURE__ */ u("h2", { children: "Accent" }),
			props.notice && /* @__PURE__ */ u("p", {
				className: "notice",
				children: props.notice
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "The person's voice can keep their own accent or speak with another one. Changing it makes the sample video again."
			}),
			/* @__PURE__ */ u("fieldset", {
				disabled: choice === null || saving !== null || preparing,
				children: [/* @__PURE__ */ u("legend", { children: "Speak with" }), ACCENTS.map(({ accent, label }) => /* @__PURE__ */ u("label", {
					className: saving === accent ? "busy" : void 0,
					children: [
						/* @__PURE__ */ u("input", {
							type: "radio",
							name: "accent",
							value: accent,
							checked: (saving ?? choice?.accent) === accent,
							disabled: accent !== "own" && choice?.available === false,
							onChange: () => void choose(accent)
						}),
						" ",
						label
					]
				}, accent))]
			}),
			preparing && /* @__PURE__ */ u("p", {
				className: "muted",
				children: "You can change the accent once Prepare has finished."
			}),
			choice?.available === false && /* @__PURE__ */ u("p", {
				className: "muted",
				children: "Another accent needs the voice add-on, which isn't installed on this computer yet. Until then a ready-made voice speaks, with its own accent."
			}),
			failed && /* @__PURE__ */ u("p", {
				className: "error",
				children: failed
			})
		]
	});
}
var PREPARE_POLL_MS = 1e3;
function PrepareSection(props) {
	const { changes, onRunning } = props;
	const [status, setStatus] = d(null);
	const [loadFailed, setLoadFailed] = d(false);
	const [starting, setStarting] = d(false);
	const [refused, setRefused] = d(null);
	const requests = A(0);
	async function read() {
		const request = ++requests.current;
		try {
			const current = await getPrepare();
			if (request === requests.current) setStatus(current);
			setLoadFailed(false);
		} catch (e) {
			console.error("Could not read the prepare job", e);
			setLoadFailed(true);
		}
	}
	async function start() {
		const request = ++requests.current;
		setStarting(true);
		setRefused(null);
		try {
			const started = await startPrepare();
			if (request === requests.current) setStatus(started);
		} catch (e) {
			console.error("Could not start preparing", e);
			setRefused(e.message);
		}
		setStarting(false);
	}
	h(() => {
		read();
	}, [changes]);
	const running = status?.state === "running";
	h(() => onRunning(running), [running]);
	h(() => {
		if (!running) return;
		const timer = window.setInterval(() => void read(), PREPARE_POLL_MS);
		return () => window.clearInterval(timer);
	}, [running]);
	return /* @__PURE__ */ u("section", {
		className: "prepare panel",
		children: [
			/* @__PURE__ */ u(StepOf, { n: 4 }),
			/* @__PURE__ */ u("h2", { children: "Prepare the video" }),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "Gets the voice and the face ready for the video, then makes a short sample video of the person talking. The first time takes 20 minutes or more. You can leave this page meanwhile; if the app is stopped, it carries on where it left off when the app starts again."
			}),
			status === null && !loadFailed && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Loading…"
			}),
			loadFailed && /* @__PURE__ */ u("p", {
				className: "error",
				children: "Could not read how far preparing has got. Reload the page to try again."
			}),
			status !== null && !running && /* @__PURE__ */ u("button", {
				type: "button",
				className: starting ? "busy" : void 0,
				onClick: start,
				disabled: starting,
				children: starting ? "Starting…" : {
					idle: "Prepare the video",
					running: "Preparing…",
					done: "Prepare again",
					failed: "Try again"
				}[status.state]
			}),
			refused && /* @__PURE__ */ u("p", {
				className: "error",
				children: refused
			}),
			running && /* @__PURE__ */ u("p", {
				className: "busy",
				children: [
					"Preparing… ",
					status.percent,
					"% done"
				]
			}),
			status?.steps && status.state !== "idle" && /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("progress", {
				max: 100,
				value: status.percent,
				"aria-label": "Preparing",
				children: [status.percent, "%"]
			}), /* @__PURE__ */ u("ol", {
				className: "steps",
				children: status.steps.map((step, i) => /* @__PURE__ */ u("li", { children: [
					/* @__PURE__ */ u("span", { children: step.label }),
					" ",
					/* @__PURE__ */ u(StepState, {
						step,
						status,
						index: i
					})
				] }, step.key))
			})] }),
			status?.state === "done" && /* @__PURE__ */ u("div", {
				className: "sample-video",
				children: [
					/* @__PURE__ */ u("p", {
						className: "done",
						children: "Done. Watch the sample video, then say whether it is right."
					}),
					/* @__PURE__ */ u("video", {
						controls: true,
						preload: "metadata",
						src: clipUrl("sample", status),
						"aria-label": "Sample video"
					}),
					/* @__PURE__ */ u(ReviewChoices, {
						sample: status.finished_at,
						onBack: props.onBack
					})
				]
			}),
			status?.state === "failed" && /* @__PURE__ */ u("p", {
				className: "error",
				children: status.error
			})
		]
	});
}
var REJECTS = [
	{
		decision: "reject-image",
		label: "Reject image",
		back: "photos"
	},
	{
		decision: "reject-voice",
		label: "Reject voice",
		back: "sounds"
	},
	{
		decision: "change-accent",
		label: "Change accent",
		back: "accent"
	}
];
function ReviewChoices(props) {
	const [current, setCurrent] = d(null);
	const [saving, setSaving] = d(null);
	const [failed, setFailed] = d(null);
	h(() => {
		getReview().then(setCurrent).catch((e) => console.error("Could not get the review", e));
	}, [props.sample]);
	async function decide(decision, back) {
		setSaving(decision);
		setFailed(null);
		try {
			setCurrent(await review(decision));
			if (back) props.onBack(back);
			else window.location.hash = "#/chat";
		} catch (e) {
			console.error(`Could not save the review (${decision})`, e);
			setFailed(`Could not save your choice: ${e.message}`);
		}
		setSaving(null);
	}
	return /* @__PURE__ */ u("div", {
		className: "review",
		children: [
			/* @__PURE__ */ u("h3", { children: "Is this right?" }),
			current?.accepted ? /* @__PURE__ */ u("p", {
				className: "done",
				children: ["You accepted this sample. ", /* @__PURE__ */ u("a", {
					href: "#/chat",
					children: "Go to the chat"
				})]
			}) : /* @__PURE__ */ u("p", {
				className: "muted",
				children: "Accept it to unlock the chat, or go back and change what is wrong."
			}),
			/* @__PURE__ */ u("div", {
				className: "choices",
				children: [!current?.accepted && /* @__PURE__ */ u("button", {
					type: "button",
					className: saving === "accept" ? "busy" : void 0,
					disabled: saving !== null,
					onClick: () => void decide("accept"),
					children: "Accept"
				}), REJECTS.map(({ decision, label, back }) => /* @__PURE__ */ u("button", {
					type: "button",
					className: saving === decision ? "secondary busy" : "secondary",
					disabled: saving !== null,
					onClick: () => void decide(decision, back),
					children: label
				}, decision))]
			}),
			failed && /* @__PURE__ */ u("p", {
				className: "error",
				children: failed
			})
		]
	});
}
function ChatPage() {
	const student = useSettings().view === "student";
	const [accepted, setAccepted] = d(null);
	h(() => {
		getReview().then((r) => setAccepted(r.accepted)).catch((e) => {
			console.error("Could not get the review", e);
			setAccepted(false);
		});
	}, []);
	if (accepted === null) return /* @__PURE__ */ u("p", {
		className: "muted busy",
		children: "Loading…"
	});
	if (!accepted) {
		if (student) return /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("h1", { children: "Chat" }), /* @__PURE__ */ u("p", { children: "The chat isn't ready yet. Ask your teacher to finish setting it up." })] });
		return /* @__PURE__ */ u(S, { children: [
			/* @__PURE__ */ u("h1", { children: "Chat" }),
			/* @__PURE__ */ u("p", { children: "The chat is locked until you accept a sample video at the end of setup." }),
			/* @__PURE__ */ u("a", {
				className: "button",
				href: "#/setup",
				children: "Go to setup"
			})
		] });
	}
	return /* @__PURE__ */ u("div", {
		className: "chat-page",
		children: [/* @__PURE__ */ u("h1", {
			className: "sr-only",
			children: "Chat"
		}), /* @__PURE__ */ u(Chat, {})]
	});
}
var CANT_ANSWER = "Sorry, I couldn't answer that just now. Please try again in a moment.";
function newReplyId() {
	return Array.from(crypto.getRandomValues(/* @__PURE__ */ new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}
function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}
var SOUND_KEY = "imageskin.sound";
var LESSON_KEY = "imageskin.lesson";
function loadLesson() {
	try {
		const saved = JSON.parse(localStorage.getItem(LESSON_KEY) ?? "null");
		if (typeof saved?.topic !== "string" || !Number.isInteger(saved.part) || saved.part < 0) return null;
		const parts = Number.isInteger(saved.parts) ? saved.parts : void 0;
		return {
			topic: saved.topic,
			part: saved.part,
			active: saved.active !== false,
			parts
		};
	} catch {
		return null;
	}
}
function saveLesson(lesson) {
	try {
		if (lesson) localStorage.setItem(LESSON_KEY, JSON.stringify(lesson));
		else localStorage.removeItem(LESSON_KEY);
	} catch (e) {
		console.error("Could not keep the lesson", e);
	}
}
function loadSound() {
	try {
		const saved = JSON.parse(localStorage.getItem(SOUND_KEY) ?? "null");
		const volume = Number(saved?.volume);
		return {
			volume: Number.isFinite(volume) ? Math.min(Math.max(volume, 0), 1) : 1,
			muted: saved?.muted === true
		};
	} catch {
		return {
			volume: 1,
			muted: false
		};
	}
}
function saveSound(sound) {
	try {
		localStorage.setItem(SOUND_KEY, JSON.stringify(sound));
	} catch {}
}
function Chat() {
	const metrics = useSettings().show_metrics;
	const { teach_me: teachMe, debug } = useSettings();
	const [turns, setTurns] = d(null);
	const [prompt, setPrompt] = d("");
	const [sending, setSending] = d(false);
	const [speaking, setSpeaking] = d(false);
	const [clips, setClips] = d([]);
	const [times, setTimes] = d([]);
	const [earlier, setEarlier] = d([]);
	const [whole, setWhole] = d(false);
	const [unspoken, setUnspoken] = d(null);
	const [failed, setFailed] = d(null);
	const gone = A(false);
	const replying = A(null);
	const stopped = A(null);
	const wakeOnStop = A(() => {});
	const [halted, setHalted] = d(false);
	const [sound, setSound] = d(loadSound);
	const [idle, setIdle] = d("loading");
	const [photo, setPhoto] = d();
	const [waiting, setWaiting] = d(false);
	const [hints, setHints] = d({
		line: null,
		examples: []
	});
	const [lesson, setLesson] = d(loadLesson);
	const [choices, setChoices] = d([]);
	const clipTotal = A(0);
	const allMade = A(false);
	const clipsEnded = A(0);
	h(() => () => {
		gone.current = true;
	}, []);
	h(() => {
		getChatPhoto().then(({ url, width, height }) => {
			setPhoto({
				url: url ?? null,
				ratio: width && height ? width / height : null
			});
			if (url && width && height) console.info(`Chat photo ${width}x${height}`);
		}).catch((e) => {
			console.error("Could not find the photo for the chat", e);
			setPhoto({
				url: null,
				ratio: null
			});
		});
	}, []);
	h(() => {
		if (sending) return;
		getChatHints().then(setHints).catch((e) => {
			console.error("Could not load the topic hints", e);
			setHints({
				line: null,
				examples: []
			});
		});
	}, [sending]);
	h(() => {
		getChat().then(setTurns).catch((e) => {
			console.error("Could not load the conversation", e);
			setTurns([]);
			setFailed("The conversation couldn't be loaded. Reload the page to try again.");
		});
	}, []);
	async function followClips(replyId, replied) {
		let known = 0;
		while (!gone.current && stopped.current !== replyId) {
			const answered = replied();
			const got = await getClips(replyId, known);
			if (stopped.current === replyId) return known;
			if (got === null) {
				if (answered) return known;
				await sleep(300);
				continue;
			}
			const offset = performance.now() - got.now * 1e3;
			const made = got.clips.slice(known).map((c) => ({
				text: c.sentence_at * 1e3 + offset,
				ready: c.ready_at * 1e3 + offset,
				started: null,
				ended: null
			}));
			if (made.length) setTimes((t) => [...t, ...made]);
			setClips(got.clips.map((c) => c.url));
			clipTotal.current = got.clips.length;
			if (got.error !== null) throw new Error(got.error);
			if (got.done) return got.clips.length;
			if (got.clips.length === known) await sleep(300);
			known = got.clips.length;
		}
		return known;
	}
	function started(clip, at) {
		setWaiting(false);
		setTimes((t) => t.map((c, i) => i === clip && c.started === null ? {
			...c,
			started: at
		} : c));
	}
	function ended(clip, at) {
		clipsEnded.current = Math.max(clipsEnded.current, clip + 1);
		if (allMade.current && clipsEnded.current >= clipTotal.current) setWaiting(false);
		setTimes((t) => t.map((c, i) => i === clip && c.ended === null ? {
			...c,
			ended: at
		} : c));
	}
	async function send(asked) {
		const text = (asked ?? prompt).trim();
		if (!text || sending || speaking) return;
		const shownAt = (turns ?? []).length + 1;
		const replyId = newReplyId();
		let replied = false;
		replying.current = replyId;
		const stopping = new Promise((resolve) => {
			wakeOnStop.current = () => resolve("stopped");
		});
		setHalted(false);
		setSending(true);
		setSpeaking(true);
		setWaiting(true);
		clipTotal.current = 0;
		allMade.current = false;
		clipsEnded.current = 0;
		setFailed(null);
		setUnspoken(null);
		setClips([]);
		setEarlier((e) => [...e, ...clipWaits(times)]);
		setTimes([]);
		setWhole(false);
		setTurns((t) => [...t ?? [], {
			role: "user",
			content: text
		}]);
		setPrompt("");
		setChoices([]);
		let clipCount = 0;
		const following = followClips(replyId, () => replied).then((n) => {
			clipCount = n;
			allMade.current = true;
			return null;
		}, (e) => e instanceof Error ? e : new Error(String(e)));
		let reply;
		let repliedAt = 0;
		try {
			reply = await sendPrompt(text, replyId, teachMe ? lesson : null);
			repliedAt = performance.now();
			if (teachMe && reply.lesson !== void 0) {
				const next = reply.lesson;
				setLesson(next);
				saveLesson(next);
				if (next) console.info(`Lesson: ${next.topic}, part ${next.part + 1}`);
			}
			setChoices(reply.choices ?? []);
			const { role, content } = reply;
			setTurns((t) => [...t ?? [], {
				role,
				content
			}]);
		} catch (e) {
			console.error("Could not get a reply", e);
			setTurns((t) => (t ?? []).slice(0, -1));
			setPrompt(text);
			setFailed(e instanceof ServerRefusal && e.status === 400 ? e.message : CANT_ANSWER);
			replied = true;
			await Promise.race([following, stopping]);
			setClips([]);
			setTimes([]);
			setWhole(false);
			setSpeaking(false);
			setWaiting(false);
			return;
		} finally {
			replied = true;
			setSending(false);
		}
		try {
			const clipsFailed = await Promise.race([following, stopping]);
			if (gone.current || clipsFailed === "stopped") return;
			if (clipsFailed !== null) throw clipsFailed;
			if (reply.streamed && clipsEnded.current >= clipCount) setWaiting(false);
			if (!reply.streamed) {
				const url = await Promise.race([speakReply(reply.turn, replyId), stopping]);
				if (url === "stopped") return;
				setClips(url ? [`${url}?t=${Date.now()}`] : []);
				clipTotal.current = url ? 1 : 0;
				if (!url) setWaiting(false);
				if (url) {
					setWhole(true);
					setTimes([{
						text: repliedAt,
						ready: performance.now(),
						started: null,
						ended: null
					}]);
				}
			}
		} catch (e) {
			console.error("Could not speak the reply", e);
			setUnspoken({ turn: shownAt });
			setWaiting(false);
		} finally {
			setSpeaking(false);
		}
	}
	function stop() {
		const replyId = replying.current;
		if (replyId === null) return;
		stopped.current = replyId;
		wakeOnStop.current();
		setHalted(true);
		setWaiting(false);
		setTimes([]);
		setWhole(false);
		console.info(`Reply stopped (${clips.length} clips so far)`);
		stopReply(replyId).catch((e) => console.error("Could not stop the reply", e));
	}
	function changeSound(change) {
		const next = {
			...sound,
			...change
		};
		setSound(next);
		saveSound(next);
	}
	const stoppable = !halted && (speaking || times.some((t) => t.ended === null));
	const stage = /* @__PURE__ */ u(Stage, {
		idle,
		onIdle: setIdle,
		photo: photo?.url,
		ratio: photo?.ratio,
		children: clips.length > 0 && /* @__PURE__ */ u(ClipPlayer, {
			clips,
			onStarted: started,
			onEnded: ended,
			sound,
			rest: idle === "ready",
			stopped: halted
		})
	});
	if (photo === void 0) return /* @__PURE__ */ u("p", {
		className: "muted busy",
		children: "Loading…"
	});
	if (turns === null) return /* @__PURE__ */ u("div", {
		className: "chat",
		children: [/* @__PURE__ */ u("div", {
			className: "person",
			children: stage
		}), /* @__PURE__ */ u("div", {
			className: "talk",
			children: /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Loading…"
			})
		})]
	});
	const status = sending ? "Thinking…" : waiting ? "Getting ready to say it…" : null;
	return /* @__PURE__ */ u("div", {
		className: "chat",
		children: [/* @__PURE__ */ u("div", {
			className: "person",
			children: [
				stage,
				/* @__PURE__ */ u(SoundControls, {
					sound,
					onChange: changeSound,
					onStop: stoppable ? stop : void 0
				}),
				metrics && times.length > 0 && /* @__PURE__ */ u(ClipTimes, {
					times,
					whole,
					earlier
				})
			]
		}), /* @__PURE__ */ u("div", {
			className: "talk",
			children: [
				turns.length === 0 && /* @__PURE__ */ u("p", {
					className: "muted hint",
					children: "Ask a question to start the conversation."
				}),
				/* @__PURE__ */ u(TurnList, {
					turns,
					from: latestExchange(turns),
					unspoken
				}),
				/* @__PURE__ */ u("p", {
					className: "status muted",
					"aria-live": "polite",
					children: status && /* @__PURE__ */ u("span", {
						className: "busy",
						children: status
					})
				}),
				failed && /* @__PURE__ */ u("p", {
					className: "error",
					role: "alert",
					children: failed
				}),
				/* @__PURE__ */ u("form", {
					onSubmit: (e) => {
						e.preventDefault();
						send();
					},
					children: [/* @__PURE__ */ u("label", {
						className: "prompt",
						children: [/* @__PURE__ */ u("span", { children: "Your message" }), /* @__PURE__ */ u("textarea", {
							rows: 2,
							placeholder: "Type your question here",
							value: prompt,
							onInput: (e) => setPrompt(e.currentTarget.value),
							onKeyDown: (e) => {
								if (e.key === "Enter" && !e.shiftKey) {
									e.preventDefault();
									send();
								}
							}
						})]
					}), /* @__PURE__ */ u("div", {
						className: "send-buttons",
						children: [/* @__PURE__ */ u("button", {
							type: "submit",
							disabled: sending || speaking || !prompt.trim(),
							children: "Send"
						}), teachMe && /* @__PURE__ */ u("button", {
							type: "button",
							className: "secondary",
							disabled: sending || speaking,
							onClick: () => void send(TEACH_ME),
							children: "Teach me"
						})]
					})]
				}),
				teachMe && /* @__PURE__ */ u(Choices, {
					choices,
					disabled: sending || speaking,
					onAsk: (q) => void send(q)
				}),
				teachMe && lesson?.active && /* @__PURE__ */ u(LessonControls, {
					lesson,
					disabled: sending || speaking,
					onAsk: (q) => void send(q)
				}),
				/* @__PURE__ */ u(Hints, {
					hints,
					disabled: sending || speaking,
					onAsk: (q) => void send(q)
				}),
				turns.length > 0 && /* @__PURE__ */ u(History$1, {
					turns,
					unspoken
				}),
				debug && /* @__PURE__ */ u(CopyChat, { turns })
			]
		})]
	});
}
var TEACH_ME = "Teach me";
function Choices(props) {
	if (props.choices.length === 0) return null;
	return /* @__PURE__ */ u("ul", {
		className: "choices-row",
		"aria-label": "Choices",
		children: props.choices.map((choice) => /* @__PURE__ */ u("li", { children: /* @__PURE__ */ u("button", {
			type: "button",
			className: "example",
			disabled: props.disabled,
			onClick: () => props.onAsk(choice.prompt),
			children: choice.label
		}) }, choice.prompt))
	});
}
function LessonControls(props) {
	const { topic, part, parts } = props.lesson;
	const where = parts === void 0 ? "" : part >= parts ? " · summary" : ` · part ${part + 1} of ${parts}`;
	return /* @__PURE__ */ u("div", {
		className: "lesson",
		children: [/* @__PURE__ */ u("p", {
			className: "muted",
			children: [
				"Lesson: ",
				topic,
				where
			]
		}), /* @__PURE__ */ u("div", {
			className: "lesson-buttons",
			children: [
				"Next",
				"Say it more simply",
				"Stop the lesson"
			].map((label) => /* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				disabled: props.disabled,
				onClick: () => props.onAsk(label),
				children: label
			}, label))
		})]
	});
}
function Hints(props) {
	const { line, examples } = props.hints;
	if (!line && examples.length === 0) return null;
	return /* @__PURE__ */ u("div", {
		className: "hints",
		children: [line && /* @__PURE__ */ u("p", {
			className: "muted",
			children: line
		}), examples.length > 0 && /* @__PURE__ */ u("ul", {
			"aria-label": "Example questions",
			children: examples.map((question) => /* @__PURE__ */ u("li", { children: /* @__PURE__ */ u("button", {
				type: "button",
				className: "example",
				disabled: props.disabled,
				onClick: () => {
					console.info("Example question asked");
					props.onAsk(question);
				},
				children: question
			}) }, question))
		})]
	});
}
function latestExchange(turns) {
	for (let i = turns.length - 1; i >= 0; i--) if (turns[i].role === "user") return i;
	return Math.max(turns.length - 1, 0);
}
function TurnList(props) {
	const { turns, from = 0, unspoken, search } = props;
	let counted = 0;
	return /* @__PURE__ */ u("ol", {
		className: "turns",
		children: turns.slice(from).map((turn, k) => {
			const i = from + k;
			const first = counted;
			const parts = search ? splitMatches(turn.content, search.query) : [turn.content];
			counted += (parts.length - 1) / 2;
			return /* @__PURE__ */ u("li", {
				className: turn.role,
				children: [
					/* @__PURE__ */ u("span", {
						className: "who",
						children: turn.role === "user" ? "You" : "Reply"
					}),
					search ? /* @__PURE__ */ u("span", { children: parts.map((part, p) => {
						if (p % 2 === 0) return part;
						const n = first + (p - 1) / 2;
						const current = n === search.current ? "current" : void 0;
						return /* @__PURE__ */ u("mark", {
							"data-match": n,
							className: current,
							children: part
						}, p);
					}) }) : turn.content,
					unspoken?.turn === i && /* @__PURE__ */ u("span", {
						className: "note",
						children: "I couldn't say this one aloud, so here it is as text."
					})
				]
			}, i);
		})
	});
}
function splitMatches(text, query) {
	const q = query.trim().toLowerCase();
	if (!q) return [text];
	const lower = text.toLowerCase();
	const parts = [];
	let at = 0;
	for (let found = lower.indexOf(q); found >= 0; found = lower.indexOf(q, at)) {
		parts.push(text.slice(at, found), text.slice(found, found + q.length));
		at = found + q.length;
	}
	parts.push(text.slice(at));
	return parts;
}
function countMatches(turns, query) {
	return turns.reduce((n, turn) => n + (splitMatches(turn.content, query).length - 1) / 2, 0);
}
function chatText(turns, count) {
	const exchanges = [];
	for (const turn of turns) if (turn.role === "user" || exchanges.length === 0) exchanges.push([turn]);
	else exchanges[exchanges.length - 1].push(turn);
	const kept = exchanges.slice(Math.max(exchanges.length - count, 0));
	return [`Chat: the last ${kept.length} of ${exchanges.length} exchanges`, ...kept.flat().map((t) => `${t.role === "user" ? "You" : "Reply"}: ${t.content}`)].join("\n\n");
}
function CopyChat(props) {
	const all = props.turns.filter((t) => t.role === "user").length;
	const [count, setCount] = d(null);
	const [copied, setCopied] = d(false);
	const [byHand, setByHand] = d(null);
	if (all === 0) return null;
	const shown = Math.min(count ?? all, all);
	async function copy() {
		const text = chatText(props.turns, shown);
		try {
			await navigator.clipboard.writeText(text);
			console.info(`Chat copied (${shown} of ${all} exchanges, ${text.length} characters)`);
			setCopied(true);
			setByHand(null);
		} catch (e) {
			console.error("Could not copy the chat", e);
			setCopied(false);
			setByHand(text);
		}
	}
	return /* @__PURE__ */ u("div", {
		className: "copy-chat",
		children: [
			/* @__PURE__ */ u("label", { children: [
				"Copy the last",
				" ",
				/* @__PURE__ */ u("input", {
					type: "number",
					min: 1,
					max: all,
					value: shown,
					onChange: (e) => {
						const n = Math.round(Number(e.currentTarget.value));
						setCount(Number.isFinite(n) ? Math.min(Math.max(n, 1), all) : null);
						setCopied(false);
						setByHand(null);
					}
				}),
				" ",
				"of ",
				all,
				" exchanges"
			] }),
			/* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				onClick: () => void copy(),
				children: "Copy chat"
			}),
			copied && /* @__PURE__ */ u("span", {
				className: "muted",
				children: "Copied"
			}),
			byHand !== null && /* @__PURE__ */ u("textarea", {
				readOnly: true,
				"aria-label": "Chat to copy",
				value: byHand,
				onFocus: (e) => e.currentTarget.select()
			})
		]
	});
}
function History$1(props) {
	const { turns, unspoken } = props;
	const [open, setOpen] = d(false);
	const [query, setQuery] = d("");
	const [current, setCurrent] = d(0);
	const box = A(null);
	const total = query.trim() ? countMatches(turns, query) : 0;
	const active = Math.min(current, Math.max(total - 1, 0));
	h(() => {
		if (open && box.current) box.current.scrollTop = box.current.scrollHeight;
	}, [open, turns]);
	h(() => {
		if (total === 0) return;
		(box.current?.querySelector(`mark[data-match="${active}"]`))?.scrollIntoView?.({ block: "nearest" });
	}, [
		open,
		query,
		active,
		total
	]);
	function toggle() {
		console.info(`Chat history ${open ? "hidden" : "shown"} (${turns.length} turns)`);
		if (open) search("");
		setOpen(!open);
	}
	function search(text) {
		const began = performance.now();
		const found = text.trim() ? countMatches(turns, text) : 0;
		setQuery(text);
		setCurrent(0);
		if (text.trim()) {
			const ms = Math.round(performance.now() - began);
			console.info(`History search found ${found} matches in ${turns.length} turns (${ms} ms)`);
		}
	}
	function step(by) {
		if (total > 0) setCurrent((active + by + total) % total);
	}
	return /* @__PURE__ */ u("section", {
		className: "history",
		children: [/* @__PURE__ */ u("button", {
			type: "button",
			className: "link",
			"aria-expanded": open,
			onClick: toggle,
			children: open ? "Hide history" : "Show history"
		}), open && /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("div", {
			className: "history-search",
			role: "search",
			children: [
				/* @__PURE__ */ u("input", {
					type: "search",
					"aria-label": "Search the history",
					placeholder: "Search the history",
					value: query,
					onInput: (e) => search(e.currentTarget.value),
					onKeyDown: (e) => {
						if (e.key === "Enter") {
							e.preventDefault();
							step(e.shiftKey ? -1 : 1);
						}
					}
				}),
				/* @__PURE__ */ u("button", {
					type: "button",
					disabled: total < 2,
					onClick: () => step(-1),
					children: "Previous"
				}),
				/* @__PURE__ */ u("button", {
					type: "button",
					disabled: total < 2,
					onClick: () => step(1),
					children: "Next"
				}),
				query.trim() && /* @__PURE__ */ u("span", {
					className: "muted",
					"aria-live": "polite",
					children: total === 0 ? "No matches" : `${active + 1} of ${total}`
				})
			]
		}), /* @__PURE__ */ u("div", {
			ref: box,
			className: "history-box",
			tabIndex: 0,
			"aria-label": "Conversation history",
			children: /* @__PURE__ */ u(TurnList, {
				turns,
				unspoken,
				search: {
					query,
					current: active
				}
			})
		})] })]
	});
}
function Stage(props) {
	const { idle, onIdle, photo, ratio } = props;
	const [still, setStill] = d(true);
	return /* @__PURE__ */ u("div", {
		className: "stage",
		style: ratio ? { "--ratio": String(ratio) } : void 0,
		children: [
			photo && still && /* @__PURE__ */ u("img", {
				className: "still",
				src: photo,
				alt: "",
				onError: () => {
					console.error(`Could not show the photo under the video: ${photo}`);
					setStill(false);
				}
			}),
			idle !== "none" && /* @__PURE__ */ u("video", {
				className: idle === "ready" ? "idle-video" : "idle-video resting",
				src: "/api/chat/idle",
				autoPlay: true,
				loop: true,
				muted: true,
				playsInline: true,
				disablePictureInPicture: true,
				onPlaying: () => {
					if (idle === "ready") return;
					console.info("Idle video ready");
					onIdle("ready");
				},
				onError: () => {
					console.info("No idle video: the chat holds each reply's last frame");
					onIdle("none");
				}
			}),
			props.children
		]
	});
}
function ClipPlayer(props) {
	const { clips, onStarted, onEnded, sound, rest, stopped } = props;
	const [on, setOn] = d(false);
	const [playing, setPlaying] = d(0);
	const [active, setActive] = d(0);
	const players = [A(null), A(null)];
	const [refused, setRefused] = d(false);
	const begun = A(/* @__PURE__ */ new Set());
	const broken = A(/* @__PURE__ */ new Set());
	const first = clips[0];
	function play(player) {
		if (stopped) return;
		try {
			player?.play()?.then(() => setRefused(false)).catch((e) => {
				if (e instanceof DOMException && e.name === "NotAllowedError") setRefused(true);
			});
		} catch {}
	}
	_(() => {
		setPlaying(0);
		setActive(0);
		setOn(false);
		begun.current = /* @__PURE__ */ new Set();
		play(players[0].current);
	}, [first]);
	_(() => {
		for (const player of players) {
			if (!player.current) continue;
			player.current.volume = sound?.volume ?? 1;
			player.current.muted = sound?.muted ?? false;
		}
	});
	const current = Math.min(playing, clips.length - 1);
	const shown = clips[current];
	const next = clips[current + 1];
	h(() => {
		if (shown === first) return;
		if (broken.current.has(shown)) skip(shown);
		else play(players[active].current);
	}, [active, shown]);
	h(() => {
		if (!stopped) return;
		for (const player of players) try {
			player.current?.pause();
		} catch {}
		if (rest) setOn(false);
		setRefused(false);
	}, [stopped]);
	h(() => {
		if (rest && (stopped || playing >= clips.length)) setOn(false);
	}, [rest]);
	function begins(at) {
		setOn(true);
		if (playing < clips.length && !begun.current.has(playing)) {
			begun.current.add(playing);
			onStarted?.(playing, at);
		}
	}
	function ends(at) {
		if (playing >= clips.length) return;
		onEnded?.(playing, at);
		if (next !== void 0) {
			if (broken.current.has(next)) setOn(false);
			setActive((a) => 1 - a);
		} else if (rest) setOn(false);
		setPlaying(playing + 1);
	}
	function skip(url) {
		console.error(`Could not play a clip of the reply, so it was skipped: ${url}`);
		setOn(false);
		ends(performance.now());
	}
	return /* @__PURE__ */ u(S, { children: [[0, 1].map((n) => n === active ? /* @__PURE__ */ u("video", {
		ref: players[n],
		className: on ? "reply-video" : "reply-video resting",
		src: shown,
		autoPlay: !stopped,
		playsInline: true,
		disablePictureInPicture: true,
		onPlaying: () => begins(performance.now()),
		onEnded: () => ends(performance.now()),
		onError: () => skip(shown)
	}, n) : next !== void 0 && /* @__PURE__ */ u("video", {
		ref: players[n],
		src: next,
		preload: "auto",
		playsInline: true,
		hidden: true,
		onError: () => broken.current.add(next)
	}, n)), refused && !stopped && /* @__PURE__ */ u("button", {
		type: "button",
		className: "play-reply",
		onClick: () => play(players[active].current),
		children: "Play the reply"
	})] });
}
function SoundControls(props) {
	const { sound, onChange, onStop } = props;
	return /* @__PURE__ */ u("div", {
		className: "sound-controls",
		children: [
			/* @__PURE__ */ u("button", {
				type: "button",
				className: "stop",
				onClick: onStop,
				disabled: onStop === void 0,
				children: [/* @__PURE__ */ u("span", {
					className: "stop-icon",
					"aria-hidden": "true"
				}), "Stop"]
			}),
			/* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				"aria-pressed": sound.muted,
				onClick: () => onChange({ muted: !sound.muted }),
				children: sound.muted ? "Unmute" : "Mute"
			}),
			/* @__PURE__ */ u("label", { children: [/* @__PURE__ */ u("span", { children: "Volume" }), /* @__PURE__ */ u("input", {
				type: "range",
				min: 0,
				max: 100,
				value: Math.round(sound.volume * 100),
				disabled: sound.muted,
				onInput: (e) => onChange({ volume: Number(e.currentTarget.value) / 100 })
			})] })
		]
	});
}
function seconds(ms) {
	return `${(ms / 1e3).toFixed(1)} s`;
}
function clipWaits(times) {
	return times.flatMap((_, i) => {
		const wait = clipWait(times, i);
		return wait === null ? [] : [wait];
	});
}
function clipWait(times, i) {
	const t = times[i];
	if (t.started === null) return null;
	const before = times[i - 1]?.ended ?? null;
	return Math.max(0, t.started - Math.max(t.text, before ?? t.text));
}
function average(waits) {
	return waits.reduce((a, b) => a + b, 0) / waits.length;
}
function ClipTimes(props) {
	const { times, whole, earlier = [] } = props;
	const limit = 2e3;
	const waits = clipWaits(times);
	const all = [...earlier, ...waits];
	return /* @__PURE__ */ u("div", {
		className: "timing",
		children: [
			/* @__PURE__ */ u("span", { children: "Timing (target 1 to 2 s)" }),
			/* @__PURE__ */ u("ol", { children: times.map((t, i) => {
				const name = whole ? "Reply" : `Clip ${i + 1}`;
				if (t.started === null) return /* @__PURE__ */ u("li", { children: [name, ": not spoken yet"] }, i);
				const after = t.started - t.text;
				const before = times[i - 1];
				const pause = before?.ended === null || before === void 0 ? null : Math.max(0, t.started - before.ended);
				const late = (clipWait(times, i) ?? 0) > limit;
				return /* @__PURE__ */ u("li", {
					className: late ? "late" : void 0,
					children: [
						name,
						": spoken ",
						seconds(after),
						" after its text arrived",
						pause !== null && `, ${seconds(pause)} after clip ${i} ended`
					]
				}, i);
			}) }),
			waits.length > 0 && /* @__PURE__ */ u("p", {
				className: average(waits) > limit ? "average late" : "average",
				children: [
					"Average wait: ",
					seconds(average(waits)),
					" over ",
					waits.length,
					" ",
					waits.length === 1 ? "clip" : "clips",
					" of this reply",
					earlier.length > 0 && `; ${seconds(average(all))} over ${all.length} clips since the page was opened`
				]
			})
		]
	});
}
function StepState(props) {
	const { step, status } = props;
	const metrics = useSettings().show_metrics;
	if (step.done >= step.total) {
		const took = metrics && step.seconds !== null ? ` in ${duration(step.seconds)}` : "";
		return /* @__PURE__ */ u("span", {
			className: "done",
			children: ["Done", took]
		});
	}
	if (!(status.steps?.findIndex((s) => s.done < s.total) === props.index)) return /* @__PURE__ */ u("span", {
		className: "muted",
		children: "Waiting"
	});
	if (status.state === "failed") return /* @__PURE__ */ u("span", {
		className: "error",
		children: "Stopped"
	});
	return /* @__PURE__ */ u("span", {
		className: "busy",
		children: [step.total > 1 ? `${step.done} of ${step.total}` : "Working…", step.left_s !== null && ` · about ${duration(step.left_s)} left`]
	});
}
function duration(seconds) {
	return seconds < 90 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`;
}
function minutes(seconds) {
	const whole = Math.round(seconds);
	return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
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
	"/setup": "setup",
	"/chat": "chat",
	"/content": "content",
	"/guide": "guide",
	"/wiki": "wiki"
};
var WIKI_PDF = /^\/wiki\/([^/]+)$/;
var WIKI_PAGE = /^\/wiki\/page\/([^/]+)$/;
function pathOf(hash) {
	return hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
}
function wikiTarget(hash) {
	const path = pathOf(hash);
	const entry = decoded(WIKI_PAGE.exec(path)?.[1]);
	if (entry) return { entry };
	const pdf = decoded(WIKI_PDF.exec(path)?.[1]);
	return pdf ? { pdf } : {};
}
function decoded(part) {
	if (part === void 0) return void 0;
	try {
		return decodeURIComponent(part);
	} catch {
		return;
	}
}
function pageFor(hash) {
	const path = pathOf(hash);
	const wiki = wikiTarget(hash);
	if (wiki.entry) return "wiki-page";
	if (wiki.pdf) return "wiki";
	return PAGES[path] ?? "not-found";
}
var TEACHER_PAGES = [
	"home",
	"consent",
	"setup",
	"guide",
	"content"
];
function resolve(hash, consented, student = false) {
	const page = pageFor(hash);
	if (student && TEACHER_PAGES.includes(page)) return {
		page: "chat",
		redirect: "#/chat"
	};
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
//#region src/wiki.tsx
var WIKI_POLL_MS = 2e3;
function busy(build) {
	return build?.state === "waiting" || build?.state === "building";
}
function WikiPage({ pdf }) {
	const student = useSettings().view === "student";
	const [wiki, setWiki] = d(null);
	const [failed, setFailed] = d(false);
	const [builds, setBuilds] = d({});
	const [version, setVersion] = d(0);
	const reload = () => setVersion((v) => v + 1);
	h(() => {
		setWiki(null);
	}, [pdf]);
	h(() => {
		let stopped = false;
		const started = performance.now();
		setFailed(false);
		Promise.all([
			listPdfs(),
			listWikiContents(pdf),
			listWikiBuilds()
		]).then(([pdfs, contents, next]) => {
			console.info(`Wiki loaded in ${Math.round(performance.now() - started)} ms (${contents.length} tables of contents, ${pdfs.length} PDFs)`);
			if (stopped) return;
			setWiki({
				pdfs,
				contents
			});
			setBuilds(next);
		}).catch((e) => {
			console.error("Could not load the wiki", e);
			if (!stopped) setFailed(true);
		});
		return () => {
			stopped = true;
		};
	}, [pdf, version]);
	const shown = (wiki?.contents ?? []).map((c) => c.pdf_id);
	const rebuilding = shown.some((id) => busy(builds[id]));
	h(() => {
		if (!rebuilding) return;
		const timer = window.setInterval(() => {
			listWikiBuilds().then((next) => {
				setBuilds(next);
				if (!shown.some((id) => busy(next[id]))) reload();
			}).catch((e) => console.error("Could not check the wiki progress", e));
		}, WIKI_POLL_MS);
		return () => window.clearInterval(timer);
	}, [rebuilding]);
	const rebuild = async (id) => {
		const status = await rebuildWiki(id);
		console.info(`Rebuilding the wiki of ${id}`);
		setBuilds((b) => ({
			...b,
			[id]: status
		}));
		if (!busy(status)) reload();
	};
	return /* @__PURE__ */ u("section", {
		className: "wiki",
		children: [
			/* @__PURE__ */ u("h1", { children: "Wiki" }),
			pdf ? /* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("a", {
				href: wikiHref(),
				children: "All PDFs"
			}) }) : student ? /* @__PURE__ */ u("p", {
				className: "lead",
				children: "What the PDFs say, topic by topic. Open a topic to see its parts, or follow its title to a page of its own."
			}) : /* @__PURE__ */ u("p", {
				className: "lead",
				children: [
					"What the PDFs in ",
					/* @__PURE__ */ u("a", {
						href: "#/content",
						children: "Manage Content"
					}),
					" say, topic by topic. Open a topic to see its parts, or follow its title to a page of its own. You can edit any entry."
				]
			}),
			failed ? /* @__PURE__ */ u("p", {
				className: "error",
				children: "The wiki couldn't be loaded. Reload the page to try again."
			}) : wiki === null ? /* @__PURE__ */ u("p", { children: "Loading…" }) : /* @__PURE__ */ u(WikiList, {
				wiki,
				pdf,
				builds,
				onRebuild: rebuild,
				onChanged: reload
			})
		]
	});
}
function WikiList({ wiki, pdf, builds, onRebuild, onChanged }) {
	const student = useSettings().view === "student";
	const built = new Set(wiki.contents.map((c) => c.pdf_id));
	const waiting = wiki.pdfs.filter((p) => !built.has(p.id) && (!pdf || p.id === pdf));
	if (wiki.pdfs.length === 0) {
		if (student) return /* @__PURE__ */ u("p", { children: "There are no PDFs yet." });
		return /* @__PURE__ */ u("p", { children: [
			"There are no PDFs yet. Add one in ",
			/* @__PURE__ */ u("a", {
				href: "#/content",
				children: "Manage Content"
			}),
			" and its wiki is built from it."
		] });
	}
	if (pdf && wiki.contents.length === 0 && waiting.length === 0) return /* @__PURE__ */ u("p", { children: "This PDF is no longer here. It may have been removed." });
	return /* @__PURE__ */ u(S, { children: [wiki.contents.map((c) => /* @__PURE__ */ u(Contents, {
		contents: c,
		linked: !pdf,
		build: builds[c.pdf_id],
		onRebuild: () => onRebuild(c.pdf_id),
		onChanged
	}, c.pdf_id)), waiting.map((p) => /* @__PURE__ */ u("p", {
		className: "muted",
		children: [
			p.name,
			": its wiki isn't ready yet.",
			!student && /* @__PURE__ */ u(S, { children: [
				" ",
				/* @__PURE__ */ u("a", {
					href: "#/content",
					children: "Manage Content"
				}),
				" shows how far it has got."
			] })
		]
	}, p.id))] });
}
function Contents({ contents, linked, build, onRebuild, onChanged }) {
	const name = linked ? /* @__PURE__ */ u("a", {
		href: wikiHref(contents.pdf_id),
		children: contents.pdf_name
	}) : contents.pdf_name;
	const student = useSettings().view === "student";
	return /* @__PURE__ */ u("article", {
		className: "wiki-pdf panel",
		children: [
			/* @__PURE__ */ u("h2", { children: name }),
			/* @__PURE__ */ u("div", {
				className: "pdf-tools",
				children: [/* @__PURE__ */ u("a", {
					className: "button secondary",
					href: pdfUrl(contents.pdf_id),
					target: "_blank",
					rel: "noreferrer",
					children: "Open the PDF"
				}), !student && /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u(Rebuild, {
					build,
					onRebuild
				}), /* @__PURE__ */ u(WikiTools, {
					contents,
					onChanged
				})] })]
			}),
			!student && contents.lost_edits.length > 0 && /* @__PURE__ */ u(LostEdits, {
				edits: contents.lost_edits,
				onChanged
			}),
			/* @__PURE__ */ u(Outline, {
				pdf: contents.pdf_id,
				entries: contents.entries,
				onChanged
			})
		]
	});
}
function Rebuild({ build, onRebuild }) {
	const metrics = useSettings().show_metrics;
	const [asking, setAsking] = d(false);
	const [error, setError] = d(null);
	if (busy(build)) return /* @__PURE__ */ u("p", {
		className: "muted busy",
		children: [wikiText(build, metrics), " The pages below stay as they are until it is done."]
	});
	const start = () => {
		setError(null);
		onRebuild().then(() => setAsking(false)).catch((e) => {
			console.error("Could not rebuild the wiki", e);
			setError(e instanceof Error ? e.message : "The wiki could not be rebuilt.");
		});
	};
	return /* @__PURE__ */ u("div", {
		className: "rebuild",
		children: [
			asking ? /* @__PURE__ */ u("p", {
				className: "notice",
				children: [
					"Build this PDF's wiki again? The AI reads the PDF again, which can take a while. Your edits are kept, and each is marked for you to check against the new wiki.",
					" ",
					/* @__PURE__ */ u("button", {
						type: "button",
						onClick: start,
						children: "Rebuild"
					}),
					" ",
					/* @__PURE__ */ u("button", {
						type: "button",
						className: "secondary",
						onClick: () => setAsking(false),
						children: "Cancel"
					})
				]
			}) : /* @__PURE__ */ u("p", {
				className: "outline-buttons",
				children: /* @__PURE__ */ u("button", {
					type: "button",
					className: "secondary",
					onClick: () => setAsking(true),
					children: "Rebuild the wiki"
				})
			}),
			build?.state === "failed" && !error && /* @__PURE__ */ u("p", {
				className: "error",
				children: [
					"The last rebuild didn't finish: ",
					wikiText(build, metrics),
					" The pages below are the ones built before it. You can try again."
				]
			}),
			error && /* @__PURE__ */ u("p", {
				className: "error",
				children: error
			})
		]
	});
}
function changeText(change) {
	const entry = `\u201c${change.title ?? ""}\u201d`;
	switch (change.kind) {
		case "start": return "The wiki as it was before its history began";
		case "built": return "Built by the AI";
		case "rebuilt": return "Rebuilt by the AI";
		case "edited": return `You edited ${entry}`;
		case "undone": return `You undid your edit to ${entry}`;
		case "kept": return `You kept your edit to ${entry} after a rebuild`;
		case "discarded": return `You discarded your edit to ${entry}, which a rebuild left without an entry`;
		case "restored": return `You restored the version from ${when(change.restored_at ?? "")}`;
		case "loaded": return "You loaded it from a file";
	}
}
function when(at) {
	const date = new Date(at);
	return Number.isNaN(date.getTime()) ? at : date.toLocaleString();
}
function message(e, fallback) {
	return e instanceof Error ? e.message : fallback;
}
function WikiTools({ contents, onChanged }) {
	const pdf = contents.pdf_id;
	const [showing, setShowing] = d(false);
	const [asking, setAsking] = d(null);
	const [done, setDone] = d(null);
	const [error, setError] = d(null);
	const picker = A(null);
	const change = (go, confirm, failure) => {
		setError(null);
		setDone(null);
		setAsking(null);
		const run = (force) => go(force).then((said) => {
			setDone(said);
			onChanged();
		});
		run(false).catch((e) => {
			if (e instanceof AskFirst) {
				setAsking({
					question: e.message,
					confirm,
					go: () => run(true)
				});
				return;
			}
			console.error(failure, e);
			setError(message(e, failure));
		});
	};
	const restore = (id, at) => change(async (force) => {
		await restoreWikiVersion(pdf, id, force);
		console.info(`Wiki version restored: ${id}`);
		return `The version from ${when(at)} is the wiki again. The wiki before it is kept in the history, so you can go back to it.`;
	}, "Restore it anyway", "Could not restore the version");
	const load = (file) => change(async (force) => {
		const added = await loadWikiFile(pdf, file, force);
		console.info(`Wiki loaded from ${file.name}: ${added} versions added to the history`);
		const versions = added === 0 ? "The history here already had all of its versions" : `Its history added ${added === 1 ? "1 version" : `${added} versions`} to this one`;
		return `Loaded ${file.name}. ${versions}, and the wiki before it is kept in the history too.`;
	}, "Load it anyway", "Could not load the file");
	const answer = () => {
		if (!asking) return;
		const go = asking.go;
		setAsking(null);
		go().catch((e) => {
			console.error("Could not make the change", e);
			setError(message(e, "The change could not be made."));
		});
	};
	return /* @__PURE__ */ u("div", {
		className: "wiki-tools",
		children: [
			/* @__PURE__ */ u("p", {
				className: "outline-buttons",
				children: [
					/* @__PURE__ */ u("button", {
						type: "button",
						className: "secondary",
						"aria-expanded": showing,
						onClick: () => setShowing((s) => !s),
						children: showing ? "Hide the history" : "History"
					}),
					" ",
					/* @__PURE__ */ u("a", {
						className: "button secondary",
						href: wikiFileUrl(pdf),
						download: true,
						children: "Save to a file"
					}),
					" ",
					/* @__PURE__ */ u("button", {
						type: "button",
						className: "secondary",
						onClick: () => picker.current?.click(),
						children: "Load from a file"
					}),
					/* @__PURE__ */ u("input", {
						ref: picker,
						type: "file",
						accept: ".json,application/json",
						className: "sr-only",
						"aria-label": `Load a saved wiki file for ${contents.pdf_name}`,
						tabIndex: -1,
						onChange: (e) => {
							const input = e.currentTarget;
							const file = input.files?.[0];
							input.value = "";
							if (file) load(file);
						}
					})
				]
			}),
			asking && /* @__PURE__ */ u("p", {
				className: "notice",
				children: [
					asking.question,
					" ",
					/* @__PURE__ */ u("button", {
						type: "button",
						onClick: answer,
						children: asking.confirm
					}),
					" ",
					/* @__PURE__ */ u("button", {
						type: "button",
						className: "secondary",
						onClick: () => setAsking(null),
						children: "Cancel"
					})
				]
			}),
			done && /* @__PURE__ */ u("p", {
				className: "notice",
				children: done
			}),
			error && /* @__PURE__ */ u("p", {
				className: "error",
				children: error
			}),
			showing && /* @__PURE__ */ u(History, {
				contents,
				onRestore: restore
			})
		]
	});
}
function History({ contents, onRestore }) {
	const pdf = contents.pdf_id;
	const [versions, setVersions] = d(null);
	const [failed, setFailed] = d(false);
	const [viewing, setViewing] = d(null);
	h(() => {
		let stopped = false;
		const started = performance.now();
		setFailed(false);
		listWikiVersions(pdf).then((found) => {
			console.info(`Wiki history loaded in ${Math.round(performance.now() - started)} ms (${found.length} versions)`);
			if (!stopped) setVersions(found);
		}).catch((e) => {
			console.error("Could not load the wiki history", e);
			if (!stopped) setFailed(true);
		});
		return () => {
			stopped = true;
		};
	}, [pdf, contents]);
	if (failed) return /* @__PURE__ */ u("p", {
		className: "error",
		children: "The history could not be loaded. Try again."
	});
	if (versions === null) return /* @__PURE__ */ u("p", { children: "Loading the history…" });
	return /* @__PURE__ */ u("div", {
		className: "wiki-history",
		children: [
			/* @__PURE__ */ u("h3", { children: "History" }),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "Every change keeps a version of the whole wiki, newest first. Restoring one makes it the wiki again, and keeps the wiki before it here too."
			}),
			/* @__PURE__ */ u("ol", { children: versions.map((v, i) => /* @__PURE__ */ u("li", { children: [
				/* @__PURE__ */ u("span", {
					className: "when",
					children: when(v.at)
				}),
				" ",
				changeText(v.change),
				i === 0 && /* @__PURE__ */ u("span", {
					className: "muted",
					children: " (the wiki now)"
				}),
				" ",
				/* @__PURE__ */ u("button", {
					type: "button",
					className: "link",
					"aria-expanded": viewing === v.id,
					onClick: () => setViewing(viewing === v.id ? null : v.id),
					children: viewing === v.id ? "Hide" : "View"
				}),
				i > 0 && /* @__PURE__ */ u(S, { children: [" · ", /* @__PURE__ */ u("button", {
					type: "button",
					className: "link",
					onClick: () => onRestore(v.id, v.at),
					children: "Restore"
				})] }),
				viewing === v.id && /* @__PURE__ */ u(VersionView, {
					pdf,
					id: v.id,
					onRestore: i > 0 ? () => onRestore(v.id, v.at) : void 0
				})
			] }, v.id)) })
		]
	});
}
function VersionView({ pdf, id, onRestore }) {
	const [shown, setShown] = d(null);
	const [error, setError] = d(null);
	h(() => {
		let stopped = false;
		getWikiVersion(pdf, id).then((found) => {
			if (!stopped) setShown(found);
		}).catch((e) => {
			console.error("Could not load the wiki version", e);
			if (!stopped) setError(message(e, "The version could not be loaded."));
		});
		return () => {
			stopped = true;
		};
	}, [pdf, id]);
	if (error) return /* @__PURE__ */ u("p", {
		className: "error",
		children: error
	});
	if (shown === null) return /* @__PURE__ */ u("p", { children: "Loading…" });
	return /* @__PURE__ */ u("div", {
		className: "wiki-version",
		children: [
			/* @__PURE__ */ u(Entries, {
				pdf,
				entries: shown.entries
			}),
			shown.lost_edits.length > 0 && /* @__PURE__ */ u("p", {
				className: "muted",
				children: [
					"It also kept ",
					shown.lost_edits.length === 1 ? "an edit" : "edits",
					" whose entries a rebuild had left out: ",
					shown.lost_edits.map((e) => e.title).join(", "),
					"."
				]
			}),
			onRestore && /* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("button", {
				type: "button",
				onClick: onRestore,
				children: "Restore this version"
			}) })
		]
	});
}
function LostEdits({ edits, onChanged }) {
	const [error, setError] = d(null);
	const discard = (id) => {
		undoWikiEdit(id).then(() => {
			console.info(`Wiki edit discarded: ${id}`);
			onChanged();
		}).catch((e) => {
			console.error("Could not discard the wiki edit", e);
			setError(e instanceof Error ? e.message : "The edit could not be discarded.");
		});
	};
	return /* @__PURE__ */ u("div", {
		className: "notice lost-edits",
		children: [
			/* @__PURE__ */ u("p", { children: "The rebuilt wiki no longer has these entries you edited. Copy anything you want to keep into another entry, then discard them." }),
			/* @__PURE__ */ u("ul", { children: edits.map((e) => /* @__PURE__ */ u("li", { children: [
				/* @__PURE__ */ u("span", {
					className: "entry-title",
					children: e.title
				}),
				/* @__PURE__ */ u("span", {
					className: "entry-summary",
					children: e.summary
				}),
				/* @__PURE__ */ u("button", {
					type: "button",
					className: "secondary",
					onClick: () => discard(e.id),
					children: "Discard"
				})
			] }, e.id)) }),
			error && /* @__PURE__ */ u("p", {
				className: "error",
				children: error
			})
		]
	});
}
function WikiDetailPage({ entry }) {
	const [page, setPage] = d(null);
	const [problem, setProblem] = d(null);
	const [editing, setEditing] = d(false);
	const student = useSettings().view === "student";
	const [version, setVersion] = d(0);
	const reload = () => setVersion((v) => v + 1);
	h(() => {
		setPage(null);
		setEditing(false);
	}, [entry]);
	h(() => {
		let stopped = false;
		const started = performance.now();
		setProblem(null);
		getWikiPage(entry).then((next) => {
			console.info(`Wiki page loaded in ${Math.round(performance.now() - started)} ms`);
			if (stopped) return;
			if (next === null) {
				console.info(`No wiki page ${entry}`);
				setProblem("missing");
				return;
			}
			setPage(next);
			if (version === 0) document.querySelector("main")?.scrollIntoView?.();
		}).catch((e) => {
			console.error("Could not load the wiki page", e);
			if (!stopped) setProblem("failed");
		});
		return () => {
			stopped = true;
		};
	}, [entry, version]);
	if (problem) return /* @__PURE__ */ u("section", {
		className: "wiki",
		children: [
			/* @__PURE__ */ u("h1", { children: "Wiki" }),
			/* @__PURE__ */ u("p", {
				className: "error",
				children: problem === "missing" ? "This wiki page is no longer here. Its PDF may have been replaced or removed." : "This wiki page could not be loaded. Check that the app is still running, then reload the page."
			}),
			/* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("a", {
				href: wikiHref(),
				children: "Back to the wiki"
			}) })
		]
	});
	if (page === null) return /* @__PURE__ */ u("p", { children: "Loading…" });
	return /* @__PURE__ */ u("section", {
		className: "wiki",
		children: [
			/* @__PURE__ */ u("nav", {
				className: "trail",
				"aria-label": "Where this page is",
				children: [
					/* @__PURE__ */ u("a", {
						href: wikiHref(),
						children: "Wiki"
					}),
					/* @__PURE__ */ u("span", {
						"aria-hidden": "true",
						children: " › "
					}),
					/* @__PURE__ */ u("a", {
						href: wikiHref(page.pdf_id),
						children: page.pdf_name
					}),
					page.trail.map((t) => /* @__PURE__ */ u("span", { children: [/* @__PURE__ */ u("span", {
						"aria-hidden": "true",
						children: " › "
					}), /* @__PURE__ */ u("a", {
						href: wikiPageHref(t.id),
						children: t.title
					})] }, t.id))
				]
			}),
			editing ? /* @__PURE__ */ u(EditForm, {
				entry: page,
				onDone: (saved) => {
					setEditing(false);
					if (saved) reload();
				}
			}) : /* @__PURE__ */ u(S, { children: [
				/* @__PURE__ */ u("h1", { children: page.title }),
				/* @__PURE__ */ u("p", { children: page.summary }),
				/* @__PURE__ */ u(PageLinks, {
					pdf: page.pdf_id,
					pages: page.pages
				}),
				!student && /* @__PURE__ */ u(EditActions, {
					entry: page,
					onEdit: () => setEditing(true),
					onChanged: reload
				})
			] }),
			page.entries.length > 0 && /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("h2", { children: "In this topic" }), /* @__PURE__ */ u(Outline, {
				pdf: page.pdf_id,
				entries: page.entries,
				onChanged: reload
			})] })
		]
	});
}
function Outline({ pdf, entries, onChanged }) {
	const ref = A(null);
	const student = useSettings().view === "student";
	const [editing, setEditing] = d(null);
	const opens = entries.some((e) => e.entries.length > 0);
	const openAll = (open) => {
		ref.current?.querySelectorAll("details").forEach((d) => {
			d.open = open;
		});
	};
	return /* @__PURE__ */ u("div", {
		ref,
		children: [opens && /* @__PURE__ */ u("p", {
			className: "outline-buttons",
			children: [
				/* @__PURE__ */ u("button", {
					type: "button",
					className: "secondary",
					onClick: () => openAll(true),
					children: "Open all"
				}),
				" ",
				/* @__PURE__ */ u("button", {
					type: "button",
					className: "secondary",
					onClick: () => openAll(false),
					children: "Close all"
				})
			]
		}), /* @__PURE__ */ u(Entries, {
			pdf,
			entries,
			edit: student ? void 0 : {
				id: editing,
				start: setEditing,
				done: (saved) => {
					setEditing(null);
					if (saved) onChanged();
				},
				changed: onChanged
			}
		})]
	});
}
function Entries({ pdf, entries, edit }) {
	return /* @__PURE__ */ u("ul", {
		className: "outline",
		children: entries.map((e) => /* @__PURE__ */ u("li", { children: edit && edit.id === e.id ? /* @__PURE__ */ u("div", {
			className: "leaf",
			children: /* @__PURE__ */ u(EditForm, {
				entry: e,
				onDone: edit.done
			})
		}) : e.entries.length > 0 ? /* @__PURE__ */ u("details", { children: [/* @__PURE__ */ u("summary", { children: /* @__PURE__ */ u(EntryText, {
			pdf,
			entry: e,
			edit
		}) }), /* @__PURE__ */ u(Entries, {
			pdf,
			entries: e.entries,
			edit
		})] }) : /* @__PURE__ */ u("div", {
			className: "leaf",
			children: /* @__PURE__ */ u(EntryText, {
				pdf,
				entry: e,
				edit
			})
		}) }, e.id))
	});
}
function EntryText({ pdf, entry, edit }) {
	const student = useSettings().view === "student";
	return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("span", {
			className: "entry-title",
			children: entry.detail ? /* @__PURE__ */ u("a", {
				href: wikiPageHref(entry.id),
				children: entry.title
			}) : entry.title
		}),
		/* @__PURE__ */ u("span", {
			className: "entry-summary",
			children: [entry.summary, entry.detail && /* @__PURE__ */ u(S, { children: [" ", /* @__PURE__ */ u("a", {
				href: wikiPageHref(entry.id),
				children: "Read more"
			})] })]
		}),
		/* @__PURE__ */ u(PageLinks, {
			pdf,
			pages: entry.pages
		}),
		edit ? /* @__PURE__ */ u(EditActions, {
			entry,
			onEdit: () => edit.start(entry.id),
			onChanged: edit.changed
		}) : entry.edited && !student && /* @__PURE__ */ u("span", {
			className: "entry-actions muted",
			children: "Edited by you."
		})
	] });
}
function EditActions({ entry, onEdit, onChanged }) {
	const [error, setError] = d(null);
	const act = (e, action, failure) => {
		e.preventDefault();
		setError(null);
		Promise.resolve(action()).then(() => {
			if (action !== onEdit) onChanged();
		}).catch((err) => {
			console.error(failure, err);
			setError(err instanceof Error ? err.message : failure);
		});
	};
	return /* @__PURE__ */ u("span", {
		className: "entry-actions",
		children: [
			entry.review && entry.built && /* @__PURE__ */ u("span", {
				className: "notice review",
				children: [
					"The wiki was rebuilt after you edited this. The new wiki says:",
					" ",
					/* @__PURE__ */ u("strong", { children: entry.built.title }),
					": ",
					entry.built.summary,
					" ",
					/* @__PURE__ */ u("button", {
						type: "button",
						onClick: (e) => act(e, () => markWikiReviewed(entry.id), "Could not keep the edit"),
						children: "Keep my edit"
					}),
					" ",
					/* @__PURE__ */ u("button", {
						type: "button",
						className: "secondary",
						onClick: (e) => act(e, () => undoWikiEdit(entry.id), "Could not use the new text"),
						children: "Use the new text"
					})
				]
			}),
			entry.edited && !entry.review && /* @__PURE__ */ u("span", {
				className: "muted",
				children: "Edited by you. "
			}),
			/* @__PURE__ */ u("button", {
				type: "button",
				className: "link",
				onClick: (e) => act(e, onEdit, "Could not edit"),
				children: "Edit"
			}),
			entry.edited && !entry.review && /* @__PURE__ */ u(S, { children: [" · ", /* @__PURE__ */ u("button", {
				type: "button",
				className: "link",
				onClick: (e) => act(e, () => undoWikiEdit(entry.id), "Could not undo the edit"),
				children: "Undo my edit"
			})] }),
			error && /* @__PURE__ */ u("span", {
				className: "error",
				children: [" ", error]
			})
		]
	});
}
function EditForm({ entry, onDone }) {
	const [title, setTitle] = d(entry.title);
	const [summary, setSummary] = d(entry.summary);
	const [saving, setSaving] = d(false);
	const [error, setError] = d(null);
	const save = (e) => {
		e.preventDefault();
		const started = performance.now();
		setSaving(true);
		setError(null);
		saveWikiEdit(entry.id, title, summary).then(() => {
			console.info(`Wiki edit saved in ${Math.round(performance.now() - started)} ms`);
			onDone(true);
		}).catch((err) => {
			console.error("Could not save the wiki edit", err);
			setError(err instanceof Error ? err.message : "The edit could not be saved.");
			setSaving(false);
		});
	};
	return /* @__PURE__ */ u("form", {
		className: "wiki-edit",
		onSubmit: save,
		"aria-label": `Edit ${entry.title}`,
		children: [
			/* @__PURE__ */ u("label", { children: ["Title", /* @__PURE__ */ u("input", {
				type: "text",
				value: title,
				maxLength: 200,
				onInput: (e) => setTitle(e.currentTarget.value)
			})] }),
			/* @__PURE__ */ u("label", { children: ["Summary", /* @__PURE__ */ u("textarea", {
				rows: 6,
				value: summary,
				maxLength: 5e3,
				onInput: (e) => setSummary(e.currentTarget.value)
			})] }),
			/* @__PURE__ */ u("p", {
				className: "outline-buttons",
				children: [
					/* @__PURE__ */ u("button", {
						type: "submit",
						disabled: saving || !title.trim() || !summary.trim(),
						children: saving ? "Saving…" : "Save"
					}),
					" ",
					/* @__PURE__ */ u("button", {
						type: "button",
						className: "secondary",
						onClick: () => onDone(false),
						children: "Cancel"
					})
				]
			}),
			error && /* @__PURE__ */ u("p", {
				className: "error",
				children: error
			})
		]
	});
}
function PageLinks({ pdf, pages }) {
	if (pages.length === 0) return null;
	return /* @__PURE__ */ u("span", {
		className: "entry-pages muted",
		children: [pages.length === 1 ? "PDF page " : "PDF pages ", pages.map((n, i) => /* @__PURE__ */ u("span", { children: [i > 0 && ", ", /* @__PURE__ */ u("a", {
			href: pdfPageUrl(pdf, n),
			target: "_blank",
			rel: "noreferrer",
			title: `Open page ${n} of the PDF`,
			children: n
		})] }, n))]
	});
}
//#endregion
//#region src/App.tsx
var NAV = [
	{
		page: "home",
		href: "#/",
		label: "Home"
	},
	{
		page: "setup",
		href: "#/setup",
		label: "Setup"
	},
	{
		page: "chat",
		href: "#/chat",
		label: "Chat",
		student: true
	},
	{
		page: "wiki",
		href: "#/wiki",
		label: "Wiki",
		student: true
	},
	{
		page: "content",
		href: "#/content",
		label: "Manage Content"
	}
];
function current(page) {
	if (page === "guide") return "setup";
	return page === "wiki-page" ? "wiki" : page;
}
function App() {
	return /* @__PURE__ */ u(SettingsProvider, { children: /* @__PURE__ */ u(Shell, {}) });
}
function Shell() {
	const hash = useHash();
	const student = useSettings().view === "student";
	const settingsLoaded = useSettingsLoaded();
	const teacher = settingsLoaded && !student;
	const [consented, setConsented] = d(null);
	h(() => {
		getConsent().then((c) => setConsented(c.agreed)).catch((e) => {
			console.error("Could not load consent", e);
			setConsented(false);
		});
	}, []);
	const route = consented === null || !settingsLoaded ? null : resolve(hash, consented, student);
	h(() => {
		if (route?.redirect && route.redirect !== window.location.hash) window.location.replace(route.redirect);
	}, [route?.redirect]);
	const header = useHeaderHeight();
	let content = /* @__PURE__ */ u("p", { children: "Loading…" });
	if (route) content = {
		home: /* @__PURE__ */ u(HomePage, { consented: consented === true }),
		consent: /* @__PURE__ */ u(ConsentPage, { onConfirmed: () => {
			setConsented(true);
			window.location.hash = "#/setup";
		} }),
		setup: /* @__PURE__ */ u(SetupPage, {}),
		chat: /* @__PURE__ */ u(ChatPage, {}),
		content: /* @__PURE__ */ u(ContentPage, {}),
		guide: /* @__PURE__ */ u(GuidePage, {}),
		wiki: /* @__PURE__ */ u(WikiPage, { pdf: wikiTarget(hash).pdf }),
		"wiki-page": /* @__PURE__ */ u(WikiDetailPage, { entry: wikiTarget(hash).entry ?? "" }),
		"not-found": /* @__PURE__ */ u(NotFoundPage, {})
	}[route.page];
	return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("header", {
			ref: header,
			children: [
				/* @__PURE__ */ u("a", {
					className: "brand",
					href: teacher ? "#/" : "#/chat",
					children: [/* @__PURE__ */ u(Mark, {}), "ImageSkinForLLM"]
				}),
				/* @__PURE__ */ u("nav", { children: NAV.filter((item) => settingsLoaded && (teacher || item.student)).map((item) => /* @__PURE__ */ u("a", {
					href: item.href,
					className: current(route?.page) === item.page ? "current" : void 0,
					children: item.label
				}, item.page)) }),
				/* @__PURE__ */ u(SettingsMenu, {})
			]
		}),
		/* @__PURE__ */ u("main", { children: content }),
		/* @__PURE__ */ u("footer", { children: "Photos and recordings stay on the computer that runs this app." })
	] });
}
function useHeaderHeight() {
	const ref = A(null);
	h(() => {
		const header = ref.current;
		if (!header) return;
		const root = document.documentElement;
		const measure = () => root.style.setProperty("--header-h", `${header.offsetHeight}px`);
		measure();
		if (typeof ResizeObserver === "undefined") {
			console.warn("No ResizeObserver; the top bar's height is measured once");
			return;
		}
		const observer = new ResizeObserver(measure);
		observer.observe(header);
		return () => observer.disconnect();
	}, []);
	return ref;
}
function Mark() {
	return /* @__PURE__ */ u("svg", {
		className: "mark",
		viewBox: "0 0 32 32",
		"aria-hidden": "true",
		children: [
			/* @__PURE__ */ u("defs", { children: /* @__PURE__ */ u("linearGradient", {
				id: "mark-fill",
				x1: "0",
				y1: "0",
				x2: "1",
				y2: "1",
				children: [/* @__PURE__ */ u("stop", {
					offset: "0",
					"stop-color": "#6366f1"
				}), /* @__PURE__ */ u("stop", {
					offset: "1",
					"stop-color": "#a855f7"
				})]
			}) }),
			/* @__PURE__ */ u("rect", {
				width: "32",
				height: "32",
				rx: "9",
				fill: "url(#mark-fill)"
			}),
			/* @__PURE__ */ u("path", {
				d: "M8.5 11.5A3.5 3.5 0 0 1 12 8h8a3.5 3.5 0 0 1 3.5 3.5v5A3.5 3.5 0 0 1 20 20h-5l-4.5 3.8V19.6a3.5 3.5 0 0 1-2-3.1z",
				fill: "#fff"
			}),
			/* @__PURE__ */ u("circle", {
				cx: "13.2",
				cy: "14",
				r: "1.4",
				fill: "#5b4ee6"
			}),
			/* @__PURE__ */ u("circle", {
				cx: "18.8",
				cy: "14",
				r: "1.4",
				fill: "#5b4ee6"
			})
		]
	});
}
//#endregion
//#region src/main.tsx
R(/* @__PURE__ */ u(App, {}), document.getElementById("root"));
//#endregion

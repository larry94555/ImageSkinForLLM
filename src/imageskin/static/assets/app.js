// Generated from web/src/*.tsx by `npm run build` in web/. Do not edit; edit web/src.
import { a as h, i as d, n as A, o as R, r as _, s as S, t as u } from "./preact.js";
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
async function refusal(response) {
	try {
		const body = await response.json();
		if (typeof body.detail === "string") return body.detail;
	} catch {}
	return `The server refused it (${response.status}).`;
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
async function sendPrompt(prompt, replyId) {
	const response = await fetch("/api/chat", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(replyId ? {
			prompt,
			reply_id: replyId
		} : { prompt })
	});
	if (!response.ok) throw new Error(await refusal(response));
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
function readingUrl(id) {
	return `/api/content/${id}/reading`;
}
async function listReadings() {
	return json(await fetch("/api/content/readings"));
}
//#endregion
//#region src/content.tsx
var READING_POLL_MS = 1e3;
function ContentPage() {
	const [pdfs, setPdfs] = d(null);
	const [loadFailed, setLoadFailed] = d(false);
	const [sending, setSending] = d(null);
	const [refused, setRefused] = d([]);
	const [readings, setReadings] = d({});
	const reading = (pdfs ?? []).some((pdf) => [
		"waiting",
		"reading",
		void 0
	].includes(readings[pdf.id]?.state));
	h(() => {
		if (pdfs === null) return;
		let stopped = false;
		const check = () => listReadings().then((next) => {
			if (!stopped) setReadings(next);
		}).catch((e) => console.error("Could not check the reading progress", e));
		check();
		const timer = reading ? window.setInterval(check, READING_POLL_MS) : void 0;
		return () => {
			stopped = true;
			window.clearInterval(timer);
		};
	}, [pdfs, reading]);
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
		for (const file of files) {
			const pdf = await send(file);
			if (pdf) setPdfs((current) => [...current ?? [], pdf]);
		}
	}
	async function replace(old, event) {
		const input = event.currentTarget;
		const file = input.files?.[0];
		input.value = "";
		if (!file) return;
		setRefused([]);
		const pdf = await send(file, old);
		if (pdf) setPdfs((current) => (current ?? []).map((p) => p.id === pdf.id ? pdf : p));
	}
	async function remove(pdf) {
		if (!window.confirm(`Remove ${pdf.name}?`)) return;
		setRefused([]);
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
	return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("h1", { children: "Manage Content" }),
		/* @__PURE__ */ u("p", {
			className: "muted",
			children: "Add the PDFs the person's answers will come from, up to 100 MB each. Replace a PDF when it has a newer version, or remove it when it no longer applies."
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
				/* @__PURE__ */ u(ReadingLine, {
					id: pdf.id,
					reading: readings[pdf.id]
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
	] });
}
function ReadingLine({ id, reading }) {
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
		children: [
			readingText(reading),
			" ·",
			" ",
			/* @__PURE__ */ u("a", {
				href: readingUrl(id),
				target: "_blank",
				rel: "noreferrer",
				children: "What was read"
			})
		]
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
				children: [/* @__PURE__ */ u("li", { children: "Five photos of your face (picture files, usually ending in .jpg)." }), /* @__PURE__ */ u("li", { children: "Seven recordings of your voice, about 15 minutes of talking in total (sound files, usually ending in .m4a or .wav)." })]
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
			/* @__PURE__ */ u("p", { children: "You will make 7 recordings, one for each of the next steps. Record a section, stop, listen to check it, and only then move on. If a section goes wrong, just record that section again; you never have to start over." }),
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
		body: () => /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u(Before, {
			name: "Voice 3",
			minutes: "1 minute",
			children: "Choose two or three of the questions below. Press Record and answer them out loud in your own words, as if chatting with a friend, for about 20 to 30 seconds each. Pause for a second between questions."
		}), /* @__PURE__ */ u(Questions, { items: [
			"What did you do last weekend?",
			"Describe a place you love and why.",
			"Explain how to make something you cook often.",
			"What's something you've changed your mind about?"
		] })] })
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
				/* @__PURE__ */ u("li", { children: "You have 7 recordings named Voice 1 to Voice 7 (plus Voice 8 if you made the optional one)." }),
				/* @__PURE__ */ u("li", { children: "Voice 1 and Voice 2 are each about 1 to 2 minutes long; Voice 3 is about 1 minute; Voice 4, 5 and 6 are each about 3 minutes; Voice 7 is about 2 minutes." }),
				/* @__PURE__ */ u("li", { children: "When you play them back, your voice is clear and easy to hear." }),
				/* @__PURE__ */ u("li", { children: "There is no music, TV, other voices or loud background hum." }),
				/* @__PURE__ */ u("li", { children: "If one of them went wrong, delete just that one and record that section again." })
			]
		})
	},
	{
		title: "Add your files to the app",
		body: (laptop) => /* @__PURE__ */ u(S, { children: [
			/* @__PURE__ */ u("p", { children: "Find your 5 photos and 7 recordings, then add them on the Setup page." }),
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
							". You should see Voice 1 to Voice 7."
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
				children: [/* @__PURE__ */ u("h2", { children: "Mac" }), /* @__PURE__ */ u("p", { children: "All 12 files are on your Desktop (you put them there in the earlier steps)." })]
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
						" and choose all 7 recordings at once."
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
				children: [/* @__PURE__ */ u("span", {
					className: "title",
					children: c.title
				}), /* @__PURE__ */ u("span", {
					className: "text",
					children: c.text
				})]
			}) }, c.title))
		})]
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
	return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("h1", { children: "Setup" }),
		/* @__PURE__ */ u("p", {
			className: "done",
			children: "Thank you, consent is confirmed."
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
			title: "Photos",
			hint: "Add the five photos from the recording guide (JPG, PNG or HEIC). At least one is needed; the app will pick the best.",
			accept: "image/jpeg,image/png,image/heic,.heic",
			notice: notice("photos"),
			onChange: changed
		}),
		/* @__PURE__ */ u(UploadSection, {
			kind: "sounds",
			title: "Recordings",
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
	] });
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
		children: [
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
				children: [sending ? `Uploading and checking ${sending}…` : loading ? "Loading…" : `Add ${props.title.toLowerCase()}`, /* @__PURE__ */ u("input", {
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
		className: "accent",
		id: "accent",
		children: [
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
				children: "Another accent needs the person's own voice installed (see \"Your own voice\" in the README). Until then a ready-made voice speaks, with its own accent."
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
		className: "prepare",
		children: [
			/* @__PURE__ */ u("h2", { children: "Prepare" }),
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
					idle: "Prepare",
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
						children: "Ready. Here is the sample video:"
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
	if (!accepted) return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("h1", { children: "Chat" }),
		/* @__PURE__ */ u("p", { children: "The chat is locked until you accept a sample video at the end of setup." }),
		/* @__PURE__ */ u("a", {
			className: "button",
			href: "#/setup",
			children: "Go to setup"
		})
	] });
	return /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("h1", { children: "Chat" }), /* @__PURE__ */ u(Chat, {})] });
}
function newReplyId() {
	return Array.from(crypto.getRandomValues(/* @__PURE__ */ new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}
function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}
var SOUND_KEY = "imageskin.sound";
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
	h(() => () => {
		gone.current = true;
	}, []);
	h(() => {
		getChat().then(setTurns).catch((e) => {
			console.error("Could not load the conversation", e);
			setTurns([]);
			setFailed("Could not load the conversation. Reload the page to try again.");
		});
	}, []);
	async function followClips(replyId, replied) {
		let known = 0;
		while (!gone.current && stopped.current !== replyId) {
			const answered = replied();
			const got = await getClips(replyId, known);
			if (stopped.current === replyId) return;
			if (got === null) {
				if (answered) return;
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
			if (got.error !== null) throw new Error(got.error);
			if (got.done) return;
			if (got.clips.length === known) await sleep(300);
			known = got.clips.length;
		}
	}
	function started(clip, at) {
		setTimes((t) => t.map((c, i) => i === clip && c.started === null ? {
			...c,
			started: at
		} : c));
	}
	function ended(clip, at) {
		setTimes((t) => t.map((c, i) => i === clip && c.ended === null ? {
			...c,
			ended: at
		} : c));
	}
	async function send() {
		const text = prompt.trim();
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
		const following = followClips(replyId, () => replied).then(() => null, (e) => e instanceof Error ? e : new Error(String(e)));
		let reply;
		let repliedAt = 0;
		try {
			reply = await sendPrompt(text, replyId);
			repliedAt = performance.now();
			const { role, content } = reply;
			setTurns((t) => [...t ?? [], {
				role,
				content
			}]);
		} catch (e) {
			console.error("Could not get a reply", e);
			setTurns((t) => (t ?? []).slice(0, -1));
			setPrompt(text);
			setFailed(e instanceof Error ? e.message : String(e));
			replied = true;
			await Promise.race([following, stopping]);
			setClips([]);
			setTimes([]);
			setWhole(false);
			setSpeaking(false);
			return;
		} finally {
			replied = true;
			setSending(false);
		}
		try {
			const clipsFailed = await Promise.race([following, stopping]);
			if (gone.current || clipsFailed === "stopped") return;
			if (clipsFailed !== null) throw clipsFailed;
			if (!reply.streamed) {
				const url = await Promise.race([speakReply(reply.turn, replyId), stopping]);
				if (url === "stopped") return;
				setClips(url ? [`${url}?t=${Date.now()}`] : []);
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
			setUnspoken({
				turn: shownAt,
				why: e instanceof Error ? e.message : String(e)
			});
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
		setClips([]);
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
	if (turns === null) return /* @__PURE__ */ u("p", {
		className: "muted busy",
		children: "Loading…"
	});
	return /* @__PURE__ */ u("div", {
		className: "chat",
		children: [
			/* @__PURE__ */ u(Stage, {
				idle,
				onIdle: setIdle,
				children: clips.length > 0 && /* @__PURE__ */ u(ClipPlayer, {
					clips,
					onStarted: started,
					onEnded: ended,
					sound,
					rest: idle === "ready"
				})
			}),
			/* @__PURE__ */ u(SoundControls, {
				sound,
				onChange: changeSound,
				onStop: stoppable ? stop : void 0
			}),
			times.length > 0 && /* @__PURE__ */ u(ClipTimes, {
				times,
				whole,
				earlier
			}),
			turns.length === 0 && /* @__PURE__ */ u("p", {
				className: "muted",
				children: "Say hello to start the conversation."
			}),
			/* @__PURE__ */ u(TurnList, {
				turns,
				from: latestExchange(turns),
				unspoken
			}),
			sending && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Thinking…"
			}),
			speaking && !halted && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Getting ready to say it…"
			}),
			failed && /* @__PURE__ */ u("p", {
				className: "error",
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
						rows: 3,
						value: prompt,
						onInput: (e) => setPrompt(e.currentTarget.value),
						onKeyDown: (e) => {
							if (e.key === "Enter" && !e.shiftKey) {
								e.preventDefault();
								send();
							}
						}
					})]
				}), /* @__PURE__ */ u("button", {
					type: "submit",
					disabled: sending || speaking || !prompt.trim(),
					children: "Send"
				})]
			}),
			turns.length > 0 && /* @__PURE__ */ u(History, {
				turns,
				unspoken
			})
		]
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
						children: ["I couldn't say this one aloud, so here it is as text. ", unspoken.why]
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
function History(props) {
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
	const { idle, onIdle } = props;
	return /* @__PURE__ */ u("div", {
		className: "stage",
		children: [idle !== "none" && /* @__PURE__ */ u("video", {
			className: "idle-video",
			src: "/api/chat/idle",
			hidden: idle !== "ready",
			autoPlay: true,
			loop: true,
			muted: true,
			playsInline: true,
			disablePictureInPicture: true,
			onLoadedData: () => {
				if (idle === "ready") return;
				console.info("Idle video ready");
				onIdle("ready");
			},
			onError: () => {
				console.info("No idle video: the chat holds each reply's last frame");
				onIdle("none");
			}
		}), props.children]
	});
}
function ClipPlayer(props) {
	const { clips, onStarted, onEnded, sound, rest } = props;
	const [on, setOn] = d(false);
	const [playing, setPlaying] = d(0);
	const [active, setActive] = d(0);
	const players = [A(null), A(null)];
	const [refused, setRefused] = d(false);
	const begun = A(/* @__PURE__ */ new Set());
	const first = clips[0];
	function play(player) {
		try {
			player?.play()?.then(() => setRefused(false)).catch((e) => {
				if (e instanceof DOMException && e.name === "NotAllowedError") setRefused(true);
			});
		} catch {}
	}
	h(() => {
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
		play(players[active].current);
	}, [active, shown]);
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
		if (next !== void 0) setActive((a) => 1 - a);
		else setOn(false);
		setPlaying(playing + 1);
	}
	return /* @__PURE__ */ u(S, { children: [[0, 1].map((n) => n === active ? /* @__PURE__ */ u("video", {
		ref: players[n],
		className: rest ? on ? "reply-video over" : "reply-video over resting" : "reply-video",
		src: shown,
		autoPlay: true,
		playsInline: true,
		disablePictureInPicture: true,
		onPlaying: () => begins(performance.now()),
		onEnded: () => ends(performance.now())
	}, n) : next !== void 0 && /* @__PURE__ */ u("video", {
		ref: players[n],
		src: next,
		preload: "auto",
		playsInline: true,
		hidden: true
	}, n)), refused && /* @__PURE__ */ u("button", {
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
			onStop && /* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				onClick: onStop,
				children: "Stop"
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
	if (step.done >= step.total) {
		const took = step.seconds !== null ? ` in ${duration(step.seconds)}` : "";
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
	"/guide": "guide"
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
		label: "Chat"
	},
	{
		page: "content",
		href: "#/content",
		label: "Manage Content"
	}
];
function current(page) {
	return page === "guide" ? "setup" : page;
}
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
		chat: /* @__PURE__ */ u(ChatPage, {}),
		content: /* @__PURE__ */ u(ContentPage, {}),
		guide: /* @__PURE__ */ u(GuidePage, {}),
		"not-found": /* @__PURE__ */ u(NotFoundPage, {})
	}[route.page];
	return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("header", { children: [/* @__PURE__ */ u("a", {
			className: "brand",
			href: "#/",
			children: "ImageSkinForLLM"
		}), /* @__PURE__ */ u("nav", { children: NAV.map((item) => /* @__PURE__ */ u("a", {
			href: item.href,
			className: current(route?.page) === item.page ? "current" : void 0,
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

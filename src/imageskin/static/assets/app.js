// Generated from web/src/*.tsx by `npm run build` in web/. Do not edit; edit web/src.
import { a as R, i as h, n as A, o as S, r as d, t as u } from "./preact.js";
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
async function speakReply(turn) {
	const response = await fetch("/api/chat/video", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ turn })
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
function Chat() {
	const [turns, setTurns] = d(null);
	const [prompt, setPrompt] = d("");
	const [sending, setSending] = d(false);
	const [speaking, setSpeaking] = d(false);
	const [clips, setClips] = d([]);
	const [times, setTimes] = d([]);
	const [whole, setWhole] = d(false);
	const [unspoken, setUnspoken] = d(null);
	const [failed, setFailed] = d(null);
	const end = A(null);
	const gone = A(false);
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
	h(() => end.current?.scrollIntoView?.({ block: "end" }), [
		turns,
		sending,
		speaking
	]);
	async function followClips(replyId, replied) {
		let known = 0;
		while (!gone.current) {
			const answered = replied();
			const got = await getClips(replyId, known);
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
		setSending(true);
		setSpeaking(true);
		setFailed(null);
		setUnspoken(null);
		setClips([]);
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
			await following;
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
			const clipsFailed = await following;
			if (gone.current) return;
			if (clipsFailed !== null) throw clipsFailed;
			if (!reply.streamed) {
				const url = await speakReply(reply.turn);
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
	if (turns === null) return /* @__PURE__ */ u("p", {
		className: "muted busy",
		children: "Loading…"
	});
	return /* @__PURE__ */ u("div", {
		className: "chat",
		children: [
			clips.length > 0 && /* @__PURE__ */ u(ClipPlayer, {
				clips,
				onStarted: started,
				onEnded: ended
			}),
			times.length > 0 && /* @__PURE__ */ u(ClipTimes, {
				times,
				whole
			}),
			turns.length === 0 && /* @__PURE__ */ u("p", {
				className: "muted",
				children: "Say hello to start the conversation."
			}),
			/* @__PURE__ */ u("ol", {
				className: "turns",
				children: turns.map((turn, i) => /* @__PURE__ */ u("li", {
					className: turn.role,
					children: [
						/* @__PURE__ */ u("span", {
							className: "who",
							children: turn.role === "user" ? "You" : "Reply"
						}),
						turn.content,
						unspoken?.turn === i && /* @__PURE__ */ u("span", {
							className: "note",
							children: ["I couldn't say this one aloud, so here it is as text. ", unspoken.why]
						})
					]
				}, i))
			}),
			sending && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Thinking…"
			}),
			speaking && /* @__PURE__ */ u("p", {
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
			/* @__PURE__ */ u("div", { ref: end })
		]
	});
}
function ClipPlayer(props) {
	const { clips, onStarted, onEnded } = props;
	const [playing, setPlaying] = d(0);
	const [active, setActive] = d(0);
	const players = [A(null), A(null)];
	const begun = A(/* @__PURE__ */ new Set());
	const first = clips[0];
	h(() => {
		setPlaying(0);
		setActive(0);
		begun.current = /* @__PURE__ */ new Set();
	}, [first]);
	h(() => {
		const player = players[active].current;
		if (active === 0 && playing === 0) return;
		try {
			player?.play()?.catch(() => void 0);
		} catch {}
	}, [active]);
	const current = Math.min(playing, clips.length - 1);
	const next = clips[current + 1];
	function begins(at) {
		if (playing < clips.length && !begun.current.has(playing)) {
			begun.current.add(playing);
			onStarted?.(playing, at);
		}
	}
	function ends(at) {
		if (playing >= clips.length) return;
		onEnded?.(playing, at);
		if (next !== void 0) setActive((a) => 1 - a);
		setPlaying(playing + 1);
	}
	return /* @__PURE__ */ u(S, { children: [0, 1].map((n) => n === active ? /* @__PURE__ */ u("video", {
		ref: players[n],
		className: "reply-video",
		src: clips[current],
		autoPlay: true,
		controls: true,
		playsInline: true,
		onPlaying: () => begins(performance.now()),
		onEnded: () => ends(performance.now())
	}, n) : next !== void 0 && /* @__PURE__ */ u("video", {
		ref: players[n],
		src: next,
		preload: "auto",
		playsInline: true,
		hidden: true
	}, n)) });
}
function seconds(ms) {
	return `${(ms / 1e3).toFixed(1)} s`;
}
function ClipTimes(props) {
	const { times, whole } = props;
	const limit = 2e3;
	return /* @__PURE__ */ u("div", {
		className: "timing",
		children: [/* @__PURE__ */ u("span", { children: "Timing (target 1 to 2 s)" }), /* @__PURE__ */ u("ol", { children: times.map((t, i) => {
			const name = whole ? "Reply" : `Clip ${i + 1}`;
			if (t.started === null) return /* @__PURE__ */ u("li", { children: [name, ": not spoken yet"] }, i);
			const after = t.started - t.text;
			const before = times[i - 1];
			const pause = before?.ended === null || before === void 0 ? null : Math.max(0, t.started - before.ended);
			return /* @__PURE__ */ u("li", {
				className: (pause === null ? after : pause) > limit ? "late" : void 0,
				children: [
					name,
					": spoken ",
					seconds(after),
					" after its text arrived",
					pause !== null && `, ${seconds(pause)} after clip ${i} ended`
				]
			}, i);
		}) })]
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
	"/chat": "chat"
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
	}
];
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

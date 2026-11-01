// Generated from web/src/*.tsx by `npm run build` in web/. Do not edit; edit web/src.
import { a as g, c as R, i as d, l as S, n as A, o as h, r as _, s as x, t as u, u as X } from "./preact.js";
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
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function runVideoTestAgain() {
	const response = await fetch("/api/prepare/clips/sample/again", { method: "POST" });
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return (await response.json()).video;
}
async function clearChat() {
	const response = await fetch("/api/chat", { method: "DELETE" });
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return (await response.json()).cleared;
}
async function deleteMyData() {
	const response = await fetch("/api/data", { method: "DELETE" });
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
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
async function lineUrl(name) {
	const start = await getStartNow();
	if (start.chosen) {
		const { gender, accent, realism, role } = start.chosen;
		return `/api/start-now/lines/${name}?v=${encodeURIComponent([
			gender,
			accent,
			realism,
			role
		].join("-"))}`;
	}
	const status = await getPrepare();
	return status.state === "done" ? clipUrl(name, status) : null;
}
async function getFaces() {
	return json(await fetch("/api/start-now/faces"));
}
function faceUrl(name) {
	return `/faces/${name}.jpg`;
}
async function getStartNow() {
	return json(await fetch("/api/start-now"));
}
async function startNow(choice) {
	const response = await fetch("/api/start-now", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(choice)
	});
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
var DEFAULT_PICTURE = "/api/start-now/picture";
async function getReadyVoice() {
	return json(await fetch("/api/ready-voice"));
}
async function chooseReadyVoice(voice) {
	const response = await fetch("/api/ready-voice", {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ voice })
	});
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function startPrepare() {
	const response = await fetch("/api/prepare", { method: "POST" });
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function cancelPrepare(now) {
	const response = await fetch("/api/prepare/cancel", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ now })
	});
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function discardPrepare() {
	const response = await fetch("/api/prepare/discard", { method: "POST" });
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function useAvatarOwnVoice() {
	const response = await fetch("/api/start-now/own-voice", {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ agreed: true })
	});
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function useAvatarReadyVoice() {
	const response = await fetch("/api/start-now/own-voice", { method: "DELETE" });
	if (!response.ok) throw new Error(await refusal(response));
	return await response.json();
}
async function useOwnPerson() {
	const response = await fetch("/api/start-now", { method: "DELETE" });
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
async function sendPrompt(prompt, replyId, lesson, quiz, assessment, spoken) {
	const body = { prompt };
	if (spoken) body.spoken = true;
	if (replyId) body.reply_id = replyId;
	if (lesson) body.lesson = {
		topic: lesson.topic,
		part: lesson.part,
		active: lesson.active
	};
	if (quiz) {
		const { questions: _, ...kept } = quiz;
		body.quiz = kept;
	}
	if (assessment) body.assessment = assessment;
	const response = await fetch("/api/chat", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body)
	});
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function readAhead(prompt) {
	const response = await fetch("/api/chat/ahead", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ prompt })
	});
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return (await response.json()).read;
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
async function repeatReply(replyId) {
	return json(await fetch("/api/chat/repeat", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ reply_id: replyId })
	}));
}
async function getChatPhoto() {
	return json(await fetch("/api/chat/photo"));
}
async function getChatReady() {
	const body = await json(await fetch("/api/chat/ready"));
	const left = body?.left_s;
	return {
		ready: body?.ready !== false,
		leftS: typeof left === "number" && left > 0 ? left : null,
		warming: body?.warming === true
	};
}
async function getChatHints() {
	const hints = await json(await fetch("/api/chat/hints"));
	return {
		line: typeof hints?.line === "string" ? hints.line : null,
		examples: Array.isArray(hints?.examples) ? hints.examples : []
	};
}
var IDLE_VIDEO_URL = "/api/chat/idle";
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
var FACE_MOVEMENTS = [
	"off",
	"slight",
	"normal"
];
var DEFAULT_SETTINGS = {
	show_metrics: false,
	view: "host",
	teach_me: false,
	quiz_me: false,
	assessment: false,
	debug: false,
	general_prompts: false,
	face_movement: "normal",
	detail: 3
};
function settings(data) {
	return {
		show_metrics: data.show_metrics === true,
		view: data.view === "participant" ? "participant" : "host",
		teach_me: data.teach_me === true,
		quiz_me: data.quiz_me === true,
		assessment: data.assessment === true,
		debug: data.debug === true,
		general_prompts: data.general_prompts === true,
		face_movement: FACE_MOVEMENTS.includes(data.face_movement) ? data.face_movement : "normal",
		detail: Number.isInteger(data.detail) && data.detail >= 1 && data.detail <= 5 ? data.detail : 3
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
async function getLlm() {
	return json(await fetch("/api/llm"));
}
async function chooseLlm(choice) {
	const response = await fetch("/api/llm", {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(choice)
	});
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function listModels(provider, apiKey) {
	const response = await fetch("/api/llm/models", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(apiKey ? {
			provider,
			api_key: apiKey
		} : { provider })
	});
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	const listed = await response.json();
	return {
		ids: listed.models,
		names: listed.names ?? {}
	};
}
var CHATGPT_ACCOUNT_CHANGED = "chatgpt-account-changed";
async function getChatGpt() {
	return json(await fetch("/api/chatgpt"));
}
async function useChatGptAccount(account) {
	return json(await fetch("/api/chatgpt/use", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ account })
	}));
}
async function signOutChatGpt() {
	return json(await fetch("/api/chatgpt/sign-out", { method: "POST" }));
}
async function getAdminSession() {
	return json(await fetch("/api/admin/session"));
}
async function getAdminChallenge() {
	return (await json(await fetch("/api/admin/challenge"))).challenge;
}
async function isLaptopListed(laptop) {
	return (await json(await fetch("/api/admin/laptop", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(laptop ? { laptop } : {})
	}))).listed;
}
async function getSettingsAccess(laptop) {
	return json(await fetch("/api/settings/access", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(laptop ? { laptop } : {})
	}));
}
async function signInAsAdmin(password, laptop) {
	const response = await fetch("/api/admin/sign-in", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(laptop ? {
			password,
			laptop
		} : { password })
	});
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
}
async function signOutAsAdmin() {
	await json(await fetch("/api/admin/sign-out", { method: "POST" }));
}
async function adminActivity() {
	return (await fetch("/api/admin/activity", { method: "POST" })).ok;
}
async function getResources() {
	const response = await fetch("/api/admin/resources");
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function getAdminSettings() {
	const response = await fetch("/api/admin/settings");
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function getAdminHosts(q = "") {
	const response = await fetch(q ? `/api/admin/hosts?q=${encodeURIComponent(q)}` : "/api/admin/hosts");
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return (await response.json()).hosts;
}
async function getHostChoices(email) {
	const response = await fetch(`/api/admin/hosts/properties?email=${encodeURIComponent(email)}`);
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function saveHostChoice(email, kind, choice) {
	const response = await fetch("/api/admin/hosts/properties", {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			email,
			[kind]: choice
		})
	});
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function saveAdminSettings(changes) {
	const response = await fetch("/api/admin/settings", {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(changes)
	});
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
var WIZARD_STEPS = [
	"start",
	"photo",
	"voice",
	"accent",
	"prepare",
	"review"
];
async function getWizardStep() {
	return (await json(await fetch("/api/wizard"))).step;
}
async function saveWizardStep(step) {
	const response = await fetch("/api/wizard", {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ step })
	});
	if (!response.ok) throw new Error(await refusal(response));
	return (await response.json()).step;
}
async function reportCamera(report) {
	const response = await fetch("/api/wizard/camera", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(report)
	});
	if (!response.ok) throw new Error(await refusal(response));
}
async function reportRecording(report) {
	const response = await fetch("/api/wizard/recording", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(report)
	});
	if (!response.ok) throw new Error(await refusal(response));
}
async function getHostSession() {
	return json(await fetch("/api/host/session"));
}
async function getCustomUse() {
	const me = await json(await fetch("/api/host/me"));
	return {
		image: me.custom_image,
		voice: me.custom_voice
	};
}
async function hostAccount(route, email, password) {
	const response = await fetch(`/api/host/${route}`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({
			email,
			password
		})
	});
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
function signUpAsHost(email, password) {
	return hostAccount("sign-up", email, password);
}
function signInAsHost(email, password) {
	return hostAccount("sign-in", email, password);
}
async function signOutAsHost() {
	const response = await fetch("/api/host/sign-out", { method: "POST" });
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
}
async function hostPageOpened(page) {
	const response = await fetch("/api/host/page", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ page })
	});
	if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
}
async function getHostDisk(opened = false) {
	return json(await fetch(opened ? "/api/host/disk?opened=true" : "/api/host/disk"));
}
async function putCustomization(path, body) {
	const response = await fetch(`/api/customization/${path}`, {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(body)
	});
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
function saveIdentity(identity) {
	return putCustomization("identity", identity);
}
function saveGoals(goals) {
	return putCustomization("goals", { goals });
}
function saveGuidelines(feature, text) {
	return putCustomization(`guidelines/${encodeURIComponent(feature)}`, { text });
}
async function generateDraft() {
	const response = await fetch("/api/customization/draft", { method: "POST" });
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
function saveDraft({ draft, drafted, based_on }) {
	const guidelines = Object.fromEntries(draft.features.filter((f) => drafted.includes(f.key)).map((f) => [f.key, f.text]));
	return putCustomization("draft", {
		identity: draft.identity,
		goals: draft.goals,
		guidelines,
		based_on
	});
}
async function discardDraft() {
	await fetch("/api/customization/draft/discard", { method: "POST" });
}
async function getCustomizationHistory(opened = false) {
	return (await json(await fetch(opened ? "/api/customization/history?opened=true" : "/api/customization/history"))).parts;
}
async function compareCustomizationChange(part, number) {
	const response = await fetch(`/api/customization/history/${encodeURIComponent(part)}/${number}/compare`);
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function restoreCustomizationChange(part, number) {
	const response = await fetch(`/api/customization/history/${encodeURIComponent(part)}/${number}/restore`, { method: "POST" });
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function getCustomization(opened = false) {
	return json(await fetch(opened ? "/api/customization?opened=true" : "/api/customization"));
}
async function getAdminGuidelines() {
	const response = await fetch("/api/admin/guidelines");
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function saveAdminGuidelines(edit) {
	const response = await fetch("/api/admin/guidelines", {
		method: "PUT",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(edit)
	});
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function getAdminGuidelinesHistory(opened = false) {
	const response = await fetch(opened ? "/api/admin/guidelines/history?opened=true" : "/api/admin/guidelines/history");
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return (await response.json()).parts;
}
async function restoreAdminGuidelinesChange(part, number) {
	const response = await fetch(`/api/admin/guidelines/history/${encodeURIComponent(part)}/${number}/restore`, { method: "POST" });
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
async function compareAdminGuidelinesChange(part, number) {
	const response = await fetch(`/api/admin/guidelines/history/${encodeURIComponent(part)}/${number}/compare`);
	if (!response.ok) throw new ServerRefusal(await refusal(response), response.status);
	return await response.json();
}
//#endregion
//#region src/dashboard.tsx
var REFRESH_MS = 1e4;
var TITLES = {
	cpu: "CPU",
	memory: "Memory",
	disk: "Disk",
	network: "Network this month"
};
var MEANINGS = [
	[
		"blue",
		"More than enough",
		"The site could take on more work, or reserve less."
	],
	[
		"green",
		"Enough",
		"No action needed."
	],
	[
		"orange",
		"Getting close",
		"Act now, before it runs out."
	],
	[
		"red",
		"Running out",
		"Act at once: the site may slow down or fail."
	]
];
var NAMES = {
	blue: "Blue",
	green: "Green",
	orange: "Orange",
	red: "Red",
	unknown: "Unknown"
};
var GB$1 = 1e3 ** 3;
var GIB = 1024 ** 3;
function amount(resource, value) {
	if (value === null || value === void 0) return "unknown";
	if (resource.unit === "cores") return `${value.toFixed(value >= 10 ? 0 : 2)} cores`;
	const binary = resource.name === "memory";
	const gb = value / (binary ? GIB : GB$1);
	if (gb >= 1e3) return `${(gb / 1e3).toFixed(2)} TB`;
	if (gb >= 10) return `${gb.toFixed(0)} GB`;
	if (gb >= 1) return `${gb.toFixed(1)} GB`;
	const mb = value / (binary ? 1024 ** 2 : 1e3 ** 2);
	if (mb >= 1) return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB`;
	return `${Math.round(value / (binary ? 1024 : 1e3))} KB`;
}
function rangeOf(colour, t) {
	return {
		blue: `more than ${t.blue_above}% left`,
		green: `${t.orange_below}% to ${t.blue_above}% left`,
		orange: `${t.red_below}% to ${t.orange_below}% left`,
		red: `less than ${t.red_below}% left`,
		unknown: ""
	}[colour];
}
function basisLine(resource) {
	const limit = amount(resource, resource.free_tier);
	if (resource.name === "disk") return `This disk's own size. Oracle's free tier allows ${limit} of disks in all.`;
	if (resource.name === "network") return `Oracle's free tier allows ${limit} out each month.`;
	if (resource.basis === "machine") return `This machine's own, less than the free tier's ${limit}.`;
	return `Oracle's free tier limit.`;
}
function detailLines(resource) {
	const d = resource.details;
	const bytes = (v) => amount({
		...resource,
		unit: "bytes"
	}, v);
	if (resource.name === "cpu" && d.load_15 !== void 0) return [`Load over 1, 5 and 15 minutes: ${d.load_1}, ${d.load_5}, ${d.load_15}`];
	if (resource.name === "memory" && typeof d.app_cap === "number") return [`The app: ${bytes(d.app_used)} of its ${bytes(d.app_cap)} cap`];
	if (resource.name === "disk" && typeof d.llm_location === "string") return [`The LLM model: ${d.llm_location}`];
	if (resource.name === "network" && d.month !== void 0) {
		const lines = [`Received: ${bytes(d.received)} (inbound is free)`, `Now: ${bytes(d.sent_per_s)}/s out, ${bytes(d.received_per_s)}/s in`];
		if (typeof d.projected_sent === "number") lines.push(`At this pace, about ${bytes(d.projected_sent)} out by the month's end`);
		return lines;
	}
	return [];
}
function usedTenths(resource) {
	const d = resource.details;
	if (resource.name !== "disk" || typeof d.llm_bytes !== "number") return null;
	return {
		used: Math.round((d.llm_bytes + Number(d.other_bytes)) / GB$1 * 10),
		model: Math.round(d.llm_bytes / GB$1 * 10)
	};
}
function usedBy(resource) {
	const split = usedTenths(resource);
	if (split === null) return [];
	return [[`LLM model ${resource.details.llm_model}`, tenths(split.model)], ["Other", tenths(split.used - split.model)]];
}
function tenths(n) {
	return `${(n / 10).toFixed(1)} GB`;
}
function usedShown(resource) {
	const split = usedTenths(resource);
	return split === null ? amount(resource, resource.used) : tenths(split.used);
}
function Card({ resource, thresholds }) {
	const known = resource.colour !== "unknown";
	const usedShare = known && resource.available ? 100 * (resource.used ?? 0) / resource.available : 0;
	const name = TITLES[resource.name];
	return /* @__PURE__ */ u("section", {
		className: `panel resource ${resource.colour}`,
		"aria-labelledby": `resource-${resource.name}`,
		children: [
			/* @__PURE__ */ u("h2", {
				id: `resource-${resource.name}`,
				children: name
			}),
			/* @__PURE__ */ u("p", {
				className: "remaining",
				children: [
					/* @__PURE__ */ u("span", {
						className: "big",
						children: amount(resource, resource.remaining)
					}),
					" remaining",
					known && /* @__PURE__ */ u("span", {
						className: "muted",
						children: [
							" · ",
							resource.percent_remaining,
							"%"
						]
					})
				]
			}),
			/* @__PURE__ */ u("p", {
				className: `colour-name ${resource.colour}`,
				children: [NAMES[resource.colour], known ? ` · ${rangeOf(resource.colour, thresholds)}` : " · couldn't be read"]
			}),
			/* @__PURE__ */ u("div", {
				className: "bar",
				role: "meter",
				"aria-label": `${name} used`,
				"aria-valuemin": 0,
				"aria-valuemax": 100,
				"aria-valuenow": Math.round(usedShare),
				children: /* @__PURE__ */ u("span", { style: { width: `${Math.min(usedShare, 100)}%` } })
			}),
			/* @__PURE__ */ u("dl", { children: [
				/* @__PURE__ */ u("dt", { children: "Available" }),
				/* @__PURE__ */ u("dd", { children: amount(resource, resource.available) }),
				/* @__PURE__ */ u("dt", { children: "Used" }),
				/* @__PURE__ */ u("dd", { children: usedShown(resource) }),
				usedBy(resource).map(([label, value]) => /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("dt", {
					className: "part",
					children: label
				}), /* @__PURE__ */ u("dd", {
					className: "part",
					children: value
				})] }, label)),
				/* @__PURE__ */ u("dt", { children: "Remaining" }),
				/* @__PURE__ */ u("dd", { children: amount(resource, resource.remaining) })
			] }),
			/* @__PURE__ */ u("p", {
				className: "muted small",
				children: basisLine(resource)
			}),
			detailLines(resource).map((line) => /* @__PURE__ */ u("p", {
				className: "muted small",
				children: line
			}, line))
		]
	});
}
function ResourceDashboard() {
	const { refresh } = useAdmin();
	const [reading, setReading] = d(null);
	const [failed, setFailed] = d(false);
	const colours = A(null);
	h(() => {
		let active = true;
		async function read() {
			const started = performance.now();
			try {
				const read = await getResources();
				if (!active) return;
				setReading(read);
				setFailed(false);
				logColours(read, Math.round(performance.now() - started));
			} catch (e) {
				if (!active) return;
				if (e instanceof ServerRefusal && e.status === 401) {
					await refresh();
					return;
				}
				console.error("Could not read the resources", e);
				setFailed(true);
			}
		}
		function logColours(read, took) {
			const now = Object.fromEntries(read.resources.map((r) => [r.name, r.colour]));
			const before = colours.current;
			colours.current = now;
			if (!before) {
				console.info(`Resources shown: ${JSON.stringify(now)} (${took} ms)`);
				return;
			}
			for (const [name, colour] of Object.entries(now)) if (before[name] !== colour) console.info(`Resource colour changed: ${name} ${before[name]} to ${colour}`);
		}
		read();
		const timer = setInterval(() => void read(), REFRESH_MS);
		return () => {
			active = false;
			clearInterval(timer);
		};
	}, []);
	return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("h2", {
			className: "section-title",
			children: "Resources"
		}),
		failed && /* @__PURE__ */ u("p", {
			className: "error",
			children: "The resources could not be read. Trying again…"
		}),
		!reading && !failed && /* @__PURE__ */ u("p", {
			className: "muted",
			children: "Reading the resources…"
		}),
		reading && /* @__PURE__ */ u(S, { children: [
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: [
					"Read at ",
					new Date(reading.read_at).toLocaleTimeString(),
					", every 10 seconds while this page is open."
				]
			}),
			/* @__PURE__ */ u("div", {
				className: "resources",
				children: reading.resources.map((resource) => /* @__PURE__ */ u(Card, {
					resource,
					thresholds: reading.thresholds
				}, resource.name))
			}),
			/* @__PURE__ */ u("section", {
				className: "panel",
				"aria-labelledby": "resource-colours",
				children: [/* @__PURE__ */ u("h2", {
					id: "resource-colours",
					children: "What the colours mean"
				}), MEANINGS.map(([colour, meaning, todo]) => /* @__PURE__ */ u("p", {
					className: "colour-key",
					children: [
						/* @__PURE__ */ u("span", {
							className: `colour-name ${colour}`,
							children: NAMES[colour]
						}),
						" ",
						/* @__PURE__ */ u("span", {
							className: "muted",
							children: [
								"(",
								rangeOf(colour, reading.thresholds),
								")"
							]
						}),
						": ",
						meaning,
						".",
						" ",
						todo
					]
				}, colour))]
			})
		] })
	] });
}
//#endregion
//#region src/host-properties.tsx
function HostProperties() {
	const { refresh } = useAdmin();
	const [search, setSearch] = d("");
	const [answer, setAnswer] = d(null);
	const [selected, setSelected] = d(null);
	const query = search.trim();
	h(() => {
		let active = true;
		const started = performance.now();
		getAdminHosts(query).then((found) => {
			if (!active) return;
			console.info(`Host list: ${found.length} shown (${Math.round(performance.now() - started)} ms)`);
			setAnswer({
				query,
				hosts: found
			});
		}, (e) => {
			if (!active) return;
			console.error("Could not read the hosts", e);
			if (e instanceof ServerRefusal && e.status === 401) return void refresh();
			const error = e instanceof ServerRefusal ? e.message : "The hosts could not be read. Try again.";
			setAnswer({
				query,
				error
			});
		});
		return () => {
			active = false;
		};
	}, [query]);
	const current = answer?.query === query ? answer : null;
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": "host-properties",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "host-properties",
				children: "Host properties"
			}),
			/* @__PURE__ */ u("label", {
				className: "host-search",
				children: [/* @__PURE__ */ u("span", { children: "Search hosts by email" }), /* @__PURE__ */ u("input", {
					type: "search",
					value: search,
					placeholder: "Any part of the email",
					onInput: (e) => setSearch(e.currentTarget.value)
				})]
			}),
			current === null && /* @__PURE__ */ u("p", {
				className: "muted",
				children: query ? "Searching…" : "Reading the hosts…"
			}),
			current && "error" in current && /* @__PURE__ */ u("p", {
				className: "error",
				children: current.error
			}),
			current && "hosts" in current && current.hosts.length === 0 && /* @__PURE__ */ u("p", {
				className: "muted",
				children: query ? "No host's email contains that." : "No host has signed up yet."
			}),
			current && "hosts" in current && current.hosts.length > 0 && /* @__PURE__ */ u("ul", {
				className: "host-list",
				"aria-label": "Hosts",
				children: current.hosts.map((email) => /* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("button", {
					type: "button",
					className: email === selected ? "host-pick picked" : "host-pick",
					"aria-pressed": email === selected,
					onClick: () => {
						console.info("Host selected in Host properties");
						setSelected(email === selected ? null : email);
					},
					children: email
				}), email === selected && /* @__PURE__ */ u(HostChoicesPanel, { email }, email)] }, email))
			})
		]
	});
}
var KINDS = [{
	kind: "custom_image",
	label: "Custom Image"
}, {
	kind: "custom_voice",
	label: "Custom Sound"
}];
function HostChoicesPanel({ email }) {
	const { refresh } = useAdmin();
	const [choices, setChoices] = d(null);
	const [busy, setBusy] = d(false);
	const [error, setError] = d(null);
	function failed(e, what) {
		console.error(what, e);
		if (e instanceof ServerRefusal && e.status === 401) return void refresh();
		setError(e instanceof ServerRefusal ? e.message : "That didn't work. Try again.");
	}
	h(() => {
		getHostChoices(email).then(setChoices, (e) => failed(e, "Could not read the host's properties"));
	}, [email]);
	async function choose(kind, choice) {
		if (!choices) return;
		const next = choices[kind] === choice ? null : choice;
		setBusy(true);
		setError(null);
		const started = performance.now();
		try {
			setChoices(await saveHostChoice(email, kind, next));
			console.info(`Host properties changed: ${kind} ${next ?? "default"} (${Math.round(performance.now() - started)} ms)`);
		} catch (e) {
			failed(e, "Could not change the host's properties");
		} finally {
			setBusy(false);
		}
	}
	if (!choices) return error ? /* @__PURE__ */ u("p", {
		className: "error",
		children: error
	}) : /* @__PURE__ */ u("p", {
		className: "muted",
		children: [
			"Reading ",
			email,
			"…"
		]
	});
	return /* @__PURE__ */ u("div", {
		className: "host-choices",
		"aria-label": `Properties of ${email}`,
		role: "group",
		children: [KINDS.map(({ kind, label }) => /* @__PURE__ */ u("div", {
			className: "host-choice",
			children: [["allow", "deny"].map((choice) => /* @__PURE__ */ u("button", {
				type: "button",
				className: choices[kind] === choice ? "choice chosen" : "choice",
				"aria-pressed": choices[kind] === choice,
				disabled: busy,
				onClick: () => void choose(kind, choice),
				children: [
					choice === "allow" ? "Allow" : "Deny",
					" ",
					label
				]
			}, choice)), /* @__PURE__ */ u("span", {
				className: "muted",
				children: ["Default: ", choices.default[kind]]
			})]
		}, kind)), error && /* @__PURE__ */ u("p", {
			className: "error",
			children: error
		})]
	});
}
//#endregion
//#region src/admin-settings.tsx
function fieldsOf(settings) {
	const t = settings.thresholds;
	return {
		minutes: String(settings.timeout_minutes),
		blue: String(t.blue_above),
		orange: String(t.orange_below),
		red: String(t.red_below),
		noImage: settings.disable_custom_image,
		noVoice: settings.disable_custom_voice
	};
}
function AdminSettingsPage() {
	const { refresh } = useAdmin();
	const [settings, setSettings] = d(null);
	const [fields, setFields] = d(null);
	const [error, setError] = d(null);
	const [saved, setSaved] = d(false);
	const [busy, setBusy] = d(false);
	h(() => {
		getAdminSettings().then((read) => {
			console.info("Admin settings shown");
			setSettings(read);
			setFields(fieldsOf(read));
		}).catch(async (e) => {
			console.error("Could not read the admin settings", e);
			if (e instanceof ServerRefusal && e.status === 401) return refresh();
			setError("The admin settings could not be read. Reload the page to try again.");
		});
	}, []);
	async function save(changes) {
		setBusy(true);
		setError(null);
		setSaved(false);
		const started = performance.now();
		try {
			const read = await saveAdminSettings({
				timeout_minutes: Number(changes.minutes),
				thresholds: {
					blue_above: Number(changes.blue),
					orange_below: Number(changes.orange),
					red_below: Number(changes.red)
				},
				disable_custom_image: changes.noImage,
				disable_custom_voice: changes.noVoice
			});
			console.info(`Admin settings saved (${Math.round(performance.now() - started)} ms)`);
			setSettings(read);
			setFields(fieldsOf(read));
			setSaved(true);
			await refresh();
		} catch (e) {
			console.error("Could not save the admin settings", e);
			if (e instanceof ServerRefusal && e.status === 401) {
				await refresh();
				return;
			}
			setError(e instanceof ServerRefusal ? e.message : "Could not save. Try again.");
		} finally {
			setBusy(false);
		}
	}
	if (!settings || !fields) return error ? /* @__PURE__ */ u("p", {
		className: "error",
		children: error
	}) : /* @__PURE__ */ u("p", {
		className: "muted",
		children: "Reading the admin settings…"
	});
	const input = (name, label, min, max) => /* @__PURE__ */ u("label", {
		className: "admin-number",
		children: [/* @__PURE__ */ u("span", { children: label }), /* @__PURE__ */ u("input", {
			type: "number",
			min,
			max,
			step: name === "minutes" ? 1 : "any",
			value: fields[name],
			onInput: (e) => {
				setSaved(false);
				setFields({
					...fields,
					[name]: e.currentTarget.value
				});
			}
		})]
	});
	const recommended = settings.recommended.thresholds;
	const checkbox = (name, label) => /* @__PURE__ */ u("label", {
		className: "check",
		children: [
			/* @__PURE__ */ u("input", {
				type: "checkbox",
				checked: fields[name],
				onChange: (e) => {
					setSaved(false);
					setFields({
						...fields,
						[name]: e.currentTarget.checked
					});
				}
			}),
			" ",
			label
		]
	});
	return /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("form", {
		onSubmit: (e) => {
			e.preventDefault();
			save(fields);
		},
		children: [
			error && /* @__PURE__ */ u("p", {
				className: "error",
				children: error
			}),
			saved && /* @__PURE__ */ u("p", {
				className: "notice",
				role: "status",
				children: "Saved. The dashboard, the sign-out and the hosts use them now."
			}),
			/* @__PURE__ */ u("section", {
				className: "panel",
				"aria-labelledby": "admin-sign-out",
				children: [
					/* @__PURE__ */ u("h2", {
						id: "admin-sign-out",
						children: "Automatic sign-out"
					}),
					/* @__PURE__ */ u("p", {
						className: "muted",
						children: [
							"The administrator is signed out after this many minutes without a click or key press in the admin view or on the Settings page. Recommended: ",
							settings.recommended.timeout_minutes,
							"."
						]
					}),
					input("minutes", "Minutes without activity (5 to 240)", 5, 240)
				]
			}),
			/* @__PURE__ */ u("section", {
				className: "panel",
				"aria-labelledby": "admin-thresholds",
				children: [
					/* @__PURE__ */ u("h2", {
						id: "admin-thresholds",
						children: "Colours on the dashboard"
					}),
					/* @__PURE__ */ u("p", {
						className: "muted",
						children: [
							"As the percentage of a resource remaining, for every resource. Green is between orange and blue. Recommended: blue above ",
							recommended.blue_above,
							"%, orange below",
							" ",
							recommended.orange_below,
							"%, red below ",
							recommended.red_below,
							"%."
						]
					}),
					input("blue", "Blue: more than this % remaining", 1, 99),
					input("orange", "Orange: less than this % remaining", 1, 99),
					input("red", "Red: less than this % remaining", 1, 99),
					MEANINGS.map(([colour, meaning, todo]) => /* @__PURE__ */ u("p", {
						className: "colour-key",
						children: [
							/* @__PURE__ */ u("span", {
								className: `colour-name ${colour}`,
								children: colour[0].toUpperCase() + colour.slice(1)
							}),
							":",
							" ",
							meaning,
							". ",
							todo
						]
					}, colour)),
					/* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("button", {
						type: "button",
						className: "secondary",
						disabled: busy,
						onClick: () => void save({
							...fields,
							blue: String(recommended.blue_above),
							orange: String(recommended.orange_below),
							red: String(recommended.red_below)
						}),
						children: "Use the recommended thresholds"
					}) })
				]
			}),
			/* @__PURE__ */ u("section", {
				className: "panel",
				"aria-labelledby": "admin-hosts",
				children: [
					/* @__PURE__ */ u("h2", {
						id: "admin-hosts",
						children: "Hosts"
					}),
					/* @__PURE__ */ u("p", {
						className: "muted",
						children: "Checked, hosts use a default person and a ready-made voice, and can't add their own photo or record their own voice. Both are checked to begin with."
					}),
					/* @__PURE__ */ u("p", { children: checkbox("noImage", "Disable custom image") }),
					/* @__PURE__ */ u("p", { children: checkbox("noVoice", "Disable custom voice") })
				]
			}),
			/* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("button", {
				type: "submit",
				disabled: busy,
				children: "Save"
			}) })
		]
	}), /* @__PURE__ */ u(HostProperties, {})] });
}
//#endregion
//#region src/custom-use.tsx
var ALLOWED = {
	image: true,
	voice: true
};
var CustomUseContext = X(ALLOWED);
var CustomUseProvider = CustomUseContext.Provider;
function useCustomUse() {
	return x(CustomUseContext);
}
function useCustomUseOf(hash, signedIn) {
	const [read, setRead] = d(null);
	h(() => {
		if (signedIn === void 0) return;
		if (!signedIn) {
			setRead({
				use: ALLOWED,
				hash
			});
			return;
		}
		let active = true;
		getCustomUse().then((got) => {
			if (!active) return;
			setRead((was) => {
				if (!was || was.use.image !== got.image || was.use.voice !== got.voice) console.info(`Own photo allowed: ${got.image}, own voice allowed: ${got.voice}`);
				return {
					use: got,
					hash
				};
			});
		}, (e) => {
			console.error("Could not read whether your own photo and voice may be used", e);
			if (active) setRead((was) => ({
				use: was?.use ?? ALLOWED,
				hash
			}));
		});
		return () => {
			active = false;
		};
	}, [hash, signedIn]);
	return {
		use: read?.use ?? null,
		fresh: read?.hash === hash
	};
}
//#endregion
//#region src/router.ts
var PAGES = {
	"/": "home",
	"/consent": "consent",
	"/consent/own": "consent",
	"/setup": "setup",
	"/setup/wizard": "wizard",
	"/start-now": "start-now",
	"/avatar-voice": "avatar-voice",
	"/chat": "chat",
	"/content": "content",
	"/guide": "guide",
	"/wiki": "wiki",
	"/settings": "settings",
	"/admin": "admin",
	"/admin/settings": "admin",
	"/admin/guidelines": "admin",
	"/host/sign-up": "host-sign-up",
	"/host/sign-in": "host-sign-in",
	"/resources": "resources",
	"/customization": "customization"
};
var WIKI_PDF = /^\/wiki\/([^/]+)$/;
var WIKI_PAGE = /^\/wiki\/page\/([^/]+)$/;
var SETUP_PART = /^\/setup\/(photos|sounds|accent)$/;
var OWN_CONSENT = "#/consent/own";
function setupTarget(hash) {
	return SETUP_PART.exec(pathOf(hash))?.[1];
}
function pathOf(hash) {
	return hash.replace(/^#/, "").replace(/\/+$/, "") || "/";
}
function adminTarget(hash) {
	const path = pathOf(hash);
	if (path === "/admin/settings") return "settings";
	return path === "/admin/guidelines" ? "guidelines" : "resources";
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
	if (setupTarget(hash)) return "setup";
	return PAGES[path] ?? "not-found";
}
var HOST_PAGES = [
	"home",
	"consent",
	"setup",
	"wizard",
	"start-now",
	"avatar-voice",
	"guide",
	"content"
];
function resolve(hash, consented, participant = false, visitor = false, use = {
	image: true,
	voice: true
}) {
	const page = pageFor(hash);
	if (visitor && (page === "wiki" || page === "wiki-page")) return { page: "host-only" };
	if (participant && HOST_PAGES.includes(page)) {
		if (visitor && page !== "home") return { page: "host-only" };
		return {
			page: "chat",
			redirect: "#/chat"
		};
	}
	const ownPerson = page === "setup" || page === "wizard" || hash === "#/consent/own";
	if (!participant && (!use.image && ownPerson || !use.voice && page === "avatar-voice")) return {
		page: "start-now",
		redirect: "#/start-now"
	};
	if (!participant && !use.voice && page === "wizard") {
		const setup = resolve("#/setup", consented, participant, visitor, use);
		return {
			page: setup.page,
			redirect: setup.redirect ?? "#/setup"
		};
	}
	if (page === "setup" && !consented) return {
		page: "consent",
		redirect: "#/consent"
	};
	return { page };
}
var blocker = null;
function blockLeaving(fn) {
	blocker = fn;
}
function useHash() {
	const [hash, setHash] = d(window.location.hash);
	h(() => {
		const update = (e) => {
			if (blocker?.(new URL(e.oldURL).hash, new URL(e.newURL).hash)) return;
			setHash(window.location.hash);
		};
		window.addEventListener("hashchange", update);
		return () => window.removeEventListener("hashchange", update);
	}, []);
	return hash;
}
//#endregion
//#region src/change-setup.tsx
var CHANGES = [
	{
		part: "photos",
		label: "Change photos",
		about: "Add, remove or choose the photo the video is made from."
	},
	{
		part: "sounds",
		label: "Change recordings",
		about: "Add or remove the recordings the voice is made from."
	},
	{
		part: "accent",
		label: "Change accent",
		about: "Keep the person's own accent or choose another one."
	}
];
async function switchToOwn(ownAccepted, from) {
	if (!ownAccepted) {
		window.location.hash = "#/setup";
		return;
	}
	const started = performance.now();
	await useOwnPerson();
	console.info(`Switched to your own photo and voice from ${from} (${Math.round(performance.now() - started)} ms)`);
	window.location.hash = "#/chat";
}
async function ownAfterConsent() {
	const review = await getReview();
	await switchToOwn(review.default_person === true && review.own_sample_accepted === true, "Before you start");
}
function InUseMark({ shown }) {
	return shown ? /* @__PURE__ */ u("span", {
		className: "in-use",
		children: "In use"
	}) : null;
}
function ChangeSetup() {
	const use = useCustomUse();
	const changes = CHANGES.filter(({ part }) => use.voice || part === "photos");
	const [accepted, setAccepted] = d(null);
	const [inUse, setInUse] = d(null);
	const [ownAccepted, setOwnAccepted] = d(false);
	const [readyVoiceBusy, setReadyVoiceBusy] = d(false);
	const [readyVoiceDone, setReadyVoiceDone] = d(false);
	const [readyVoiceFailed, setReadyVoiceFailed] = d(null);
	const [avatarVoice, setAvatarVoice] = d({
		chosen: false,
		accepted: false
	});
	h(() => {
		const started = performance.now();
		getReview().then((r) => {
			const avatar = r.default_person ? "ready-made" : "own";
			setAccepted(r.accepted);
			setInUse(avatar);
			setOwnAccepted(r.own_sample_accepted === true);
			setAvatarVoice({
				chosen: r.own_voice === true,
				accepted: r.voice_accepted === true
			});
			const took = Math.round(performance.now() - started);
			console.info(`Sample accepted: ${r.accepted}, avatar in use: ${avatar} (${took} ms)`);
		}).catch((e) => console.error("Could not get the review", e));
	}, []);
	async function readyVoice() {
		const started = performance.now();
		setReadyVoiceBusy(true);
		setReadyVoiceFailed(null);
		try {
			await useAvatarReadyVoice();
			setAvatarVoice({
				chosen: false,
				accepted: false
			});
			setReadyVoiceDone(true);
			console.info(`Avatar's default voice used again from Settings (${Math.round(performance.now() - started)} ms)`);
		} catch (e) {
			console.error("Could not use the avatar's ready-made voice again", e);
			setReadyVoiceFailed(e.message);
		}
		setReadyVoiceBusy(false);
	}
	const defaultVoice = inUse === "ready-made" && !avatarVoice.accepted;
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": "settings-change",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "settings-change",
				children: "Avatar Choice"
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: use.image ? "The person in the video: your own photo and voice, or a ready-made avatar." : "The person in the video: a ready-made avatar. Using your own photo is turned off for this site."
			}),
			/* @__PURE__ */ u("div", {
				className: "avatar-options",
				children: [
					use.image && /* @__PURE__ */ u("div", {
						className: inUse === "own" ? "avatar-option chosen" : "avatar-option",
						children: [/* @__PURE__ */ u("h3", { children: ["Your own photo and voice ", /* @__PURE__ */ u(InUseMark, { shown: inUse === "own" })] }), inUse === "ready-made" ? /* @__PURE__ */ u("div", {
							className: "switch",
							children: [/* @__PURE__ */ u("a", {
								className: "button secondary",
								href: "#/consent/own",
								onClick: () => console.info("Switching to your own photo and voice from Settings"),
								children: "Use your own photo and voice"
							}), /* @__PURE__ */ u("p", {
								className: "muted",
								children: ownAccepted ? "Your sample video is already accepted: the chat switches to it at once." : "Your photos and recordings are kept. Accept their sample video at the end of setup to switch."
							})]
						}) : /* @__PURE__ */ u(S, { children: [
							/* @__PURE__ */ u("p", {
								className: "muted",
								children: "Changing any of them makes the sample video again, and the chat stays locked until you accept the new one at the end of setup."
							}),
							accepted === true && /* @__PURE__ */ u("p", {
								className: "muted",
								children: "The chat is open with the sample you accepted."
							}),
							accepted === false && /* @__PURE__ */ u("p", {
								className: "notice",
								children: [
									"The chat is locked until you accept a sample video in ",
									/* @__PURE__ */ u("a", {
										href: "#/setup",
										children: "Setup"
									}),
									"."
								]
							}),
							changes.map(({ part, label, about }) => /* @__PURE__ */ u("div", {
								className: "switch",
								children: [/* @__PURE__ */ u("a", {
									className: "button secondary",
									href: `#/setup/${part}`,
									onClick: () => console.info(`Changing the ${part} from Settings`),
									children: label
								}), /* @__PURE__ */ u("p", {
									className: "muted",
									children: about
								})]
							}, part))
						] })]
					}),
					/* @__PURE__ */ u("div", {
						className: inUse === "ready-made" ? "avatar-option chosen" : "avatar-option",
						children: [
							/* @__PURE__ */ u("h3", { children: ["Ready-made avatar ", /* @__PURE__ */ u(InUseMark, { shown: inUse === "ready-made" })] }),
							/* @__PURE__ */ u("p", {
								className: "muted",
								children: "A made-up person in a ready-made voice, chosen by face, accent and look. Your own photos and recordings are kept."
							}),
							/* @__PURE__ */ u("div", {
								className: "switch",
								children: /* @__PURE__ */ u("a", {
									className: "button secondary",
									href: "#/start-now",
									onClick: () => console.info("Choosing a ready-made avatar from Settings"),
									children: inUse === "ready-made" ? "Choose another avatar" : "Use a ready-made avatar"
								})
							}),
							inUse === "ready-made" && use.voice && /* @__PURE__ */ u("div", {
								className: "switch",
								children: [/* @__PURE__ */ u("a", {
									className: "button secondary",
									href: "#/avatar-voice",
									onClick: () => console.info("Giving the avatar your own voice from Settings"),
									children: avatarVoice.chosen ? "Change your voice for the avatar" : "Use my own voice"
								}), /* @__PURE__ */ u("p", {
									className: "muted",
									children: avatarVoice.accepted ? "The avatar speaks in your voice, made from your recordings." : avatarVoice.chosen ? "The avatar speaks in its ready-made voice until you accept the sample video in your voice." : "Keep the avatar's picture and replace its voice with one made from your recordings."
								})]
							})
						]
					}),
					/* @__PURE__ */ u("div", {
						className: defaultVoice ? "avatar-option chosen" : "avatar-option",
						children: [
							/* @__PURE__ */ u("h3", { children: ["Default voice for the avatar ", /* @__PURE__ */ u(InUseMark, { shown: defaultVoice })] }),
							/* @__PURE__ */ u("p", {
								className: "muted",
								children: "The ready-made avatar speaks in its own ready-made voice. There is nothing to accept, and your recordings are kept."
							}),
							inUse === "ready-made" && avatarVoice.chosen && /* @__PURE__ */ u("div", {
								className: "switch",
								children: [/* @__PURE__ */ u("button", {
									type: "button",
									className: readyVoiceBusy ? "secondary busy" : "secondary",
									disabled: readyVoiceBusy,
									onClick: () => void readyVoice(),
									children: "Use the Default Voice for the Avatar"
								}), /* @__PURE__ */ u("p", {
									className: "muted",
									children: "Switches back at once."
								})]
							}),
							inUse === "own" && /* @__PURE__ */ u("div", {
								className: "switch",
								children: [/* @__PURE__ */ u("a", {
									className: "button secondary",
									href: "#/start-now",
									onClick: () => console.info("Choosing an avatar in its default voice from Settings"),
									children: "Use the Default Voice for the Avatar"
								}), /* @__PURE__ */ u("p", {
									className: "muted",
									children: "Choose an avatar: it starts in its default voice."
								})]
							}),
							readyVoiceDone && /* @__PURE__ */ u("p", {
								className: "done",
								children: "The avatar speaks in its default voice again."
							}),
							readyVoiceFailed && /* @__PURE__ */ u("p", {
								className: "error",
								children: readyVoiceFailed
							})
						]
					})
				]
			})
		]
	});
}
//#endregion
//#region src/chatgpt-plan.tsx
function ChatGptPlanSection() {
	const [status, setStatus] = d(null);
	const [busy, setBusy] = d(false);
	const [error, setError] = d(null);
	const [unconfirmed, setUnconfirmed] = d(false);
	h(() => {
		getChatGpt().then((read) => {
			setStatus(read);
			console.info(`ChatGPT sign-in: ${read.connected ? "connected" : "not connected"}`);
		}).catch((e) => {
			console.error("Could not read the ChatGPT sign-in", e);
			setError("The ChatGPT sign-in could not be read. Reload the page to try again.");
		});
	}, []);
	async function disconnect() {
		setBusy(true);
		setError(null);
		setUnconfirmed(false);
		const started = performance.now();
		try {
			const now = await signOutChatGpt();
			setStatus(now);
			window.dispatchEvent(new Event(CHATGPT_ACCOUNT_CHANGED));
			setUnconfirmed(now.revoked === false);
			const confirmed = now.revoked === false ? ", not confirmed by ChatGPT" : "";
			console.info(`Disconnected ChatGPT (${Math.round(performance.now() - started)} ms${confirmed})`);
		} catch (e) {
			console.error("Could not disconnect ChatGPT", e);
			setError("ChatGPT could not be disconnected. Try again.");
		}
		setBusy(false);
	}
	async function switchTo(account) {
		setBusy(true);
		setError(null);
		setUnconfirmed(false);
		try {
			const now = await useChatGptAccount(account);
			setStatus(now);
			window.dispatchEvent(new Event(CHATGPT_ACCOUNT_CHANGED));
			console.info(`Switched ChatGPT account (${now.connected ? "connected" : "not connected"})`);
		} catch (e) {
			console.error("Could not switch the ChatGPT account", e);
			setError("The ChatGPT account could not be switched. Reload the page to try again.");
		}
		setBusy(false);
	}
	const others = status?.accounts ?? [];
	return /* @__PURE__ */ u("section", {
		className: "panel chatgpt-plan",
		"aria-labelledby": "settings-chatgpt",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "settings-chatgpt",
				children: "ChatGPT plan"
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "Sign in with your ChatGPT account to use your ChatGPT Plus or Pro plan instead of an API key, while the app runs on your own computer."
			}),
			status && !status.connected && /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("a", {
				className: "button",
				href: "/api/chatgpt/sign-in",
				children: "Continue with ChatGPT"
			}) }), status.registered_email && /* @__PURE__ */ u("p", {
				className: "muted",
				children: [
					"Signs in again as ",
					status.label || status.registered_email,
					".",
					" ",
					/* @__PURE__ */ u("a", {
						href: "/api/chatgpt/sign-in?another=true",
						children: "Use another ChatGPT account"
					})
				]
			})] }),
			status?.connected && /* @__PURE__ */ u(S, { children: [
				/* @__PURE__ */ u("p", { children: [
					"Connected as",
					" ",
					/* @__PURE__ */ u("strong", { children: status.label || status.email || status.name || "your ChatGPT account" })
				] }),
				!status.plan_usage && /* @__PURE__ */ u("p", { children: [
					/* @__PURE__ */ u("span", {
						className: "error",
						children: "Using your plan wasn't allowed when you signed in."
					}),
					" ",
					/* @__PURE__ */ u("a", {
						href: "/api/chatgpt/sign-in?consent=true",
						children: "Allow use of my plan"
					})
				] }),
				/* @__PURE__ */ u("button", {
					type: "button",
					disabled: busy,
					onClick: () => void disconnect(),
					children: busy ? "Disconnecting…" : "Disconnect"
				})
			] }),
			others.length > 0 && /* @__PURE__ */ u("p", {
				className: "muted",
				children: [
					status?.connected ? "Other accounts:" : "Or sign in as",
					" ",
					others.map((a, i) => /* @__PURE__ */ u("span", { children: [i > 0 && ", ", a.connected ? /* @__PURE__ */ u("button", {
						type: "button",
						className: "link",
						disabled: busy,
						onClick: () => void switchTo(a.id),
						children: ["Switch to ", a.label || a.email || "an earlier account"]
					}) : /* @__PURE__ */ u("a", {
						href: `/api/chatgpt/sign-in?account=${encodeURIComponent(a.id)}`,
						children: a.label || a.email || "an earlier account"
					})] }, a.id))
				]
			}),
			unconfirmed && /* @__PURE__ */ u("p", {
				className: "error",
				role: "alert",
				children: "Disconnected here, but ChatGPT didn't confirm it ended the sign-in. To be sure, remove ImageSkinForLLM from the connected apps in your ChatGPT settings."
			}),
			error && /* @__PURE__ */ u("p", {
				className: "error",
				role: "alert",
				children: error
			})
		]
	});
}
//#endregion
//#region src/confirm-dialog.tsx
var FOCUSABLE = "button, a[href], input, select, textarea, [tabindex]:not([tabindex='-1'])";
function ConfirmDialog(props) {
	const { onCancel } = props;
	const keep = A(null);
	const box = A(null);
	const id = g();
	const cancel = A(onCancel);
	cancel.current = onCancel;
	h(() => {
		const opener = document.activeElement;
		keep.current?.focus();
		const inside = (el) => el instanceof Node && !!box.current?.contains(el);
		const onKey = (e) => {
			if (e.key === "Escape") {
				cancel.current();
				return;
			}
			if (e.key !== "Tab" || !box.current) return;
			const items = Array.from(box.current.querySelectorAll(FOCUSABLE));
			const first = items[0];
			const last = items[items.length - 1];
			const at = document.activeElement;
			if (!inside(at) || at === (e.shiftKey ? first : last)) {
				e.preventDefault();
				(e.shiftKey ? last : first).focus();
			}
		};
		const onFocus = (e) => {
			if (!inside(e.target)) keep.current?.focus();
		};
		document.addEventListener("keydown", onKey);
		document.addEventListener("focusin", onFocus);
		return () => {
			document.removeEventListener("keydown", onKey);
			document.removeEventListener("focusin", onFocus);
			if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
		};
	}, []);
	return /* @__PURE__ */ u("div", {
		className: "confirm-backdrop",
		onClick: (e) => e.target === e.currentTarget && onCancel(),
		children: /* @__PURE__ */ u("div", {
			className: "confirm-dialog",
			role: "alertdialog",
			"aria-modal": "true",
			ref: box,
			"aria-labelledby": `${id}-title`,
			"aria-describedby": props.children ? `${id}-about` : void 0,
			children: [
				/* @__PURE__ */ u("h2", {
					id: `${id}-title`,
					children: props.title
				}),
				props.children && /* @__PURE__ */ u("div", {
					id: `${id}-about`,
					children: props.children
				}),
				/* @__PURE__ */ u("div", {
					className: "confirm-buttons",
					children: [
						/* @__PURE__ */ u("button", {
							type: "button",
							className: "secondary",
							ref: keep,
							onClick: onCancel,
							children: props.keepLabel
						}),
						props.otherLabel && /* @__PURE__ */ u("button", {
							type: "button",
							className: "secondary",
							onClick: props.onOther,
							children: props.otherLabel
						}),
						/* @__PURE__ */ u("button", {
							type: "button",
							className: "danger",
							onClick: props.onConfirm,
							children: props.confirmLabel
						})
					]
				})
			]
		})
	});
}
function useConfirm() {
	const [asking, setAsking] = d(null);
	function choose(question) {
		return new Promise((resolve) => {
			setAsking({
				question,
				answer: (answer) => {
					const said = {
						cancel: "cancelled",
						other: question.otherLabel,
						confirm: "confirmed"
					};
					console.info(`${question.title} ${said[answer]}`);
					setAsking(null);
					resolve(answer);
				}
			});
		});
	}
	async function ask(question) {
		return await choose(question) === "confirm";
	}
	return {
		ask,
		choose,
		dialog: asking && /* @__PURE__ */ u(ConfirmDialog, {
			...asking.question,
			onCancel: () => asking.answer("cancel"),
			onConfirm: () => asking.answer("confirm"),
			onOther: () => asking.answer("other")
		})
	};
}
//#endregion
//#region src/progress.ts
var LESSON_KEY = "imageskin.lesson";
var QUIZ_KEY = "imageskin.quiz";
var ASSESSMENT_KEY = "imageskin.assessment";
function clearProgress() {
	for (const key of [
		LESSON_KEY,
		QUIZ_KEY,
		ASSESSMENT_KEY
	]) try {
		localStorage.removeItem(key);
	} catch (e) {
		console.error(`Could not clear ${key}`, e);
	}
}
//#endregion
//#region src/delete-data.tsx
var DELETED = [
	"Every photo and recording",
	"The prepared face and voice",
	"The sample video, Goodbye, Welcome back and the reply videos",
	"The whole conversation",
	"Every PDF, with its wiki, edits, saved versions and lessons"
];
function DeleteData({ onDeleted }) {
	const [asking, setAsking] = d(false);
	const [deleting, setDeleting] = d(false);
	const [failed, setFailed] = d(null);
	function cancel() {
		console.info("Delete my data cancelled");
		setAsking(false);
	}
	async function remove() {
		setAsking(false);
		setDeleting(true);
		setFailed(null);
		const started = performance.now();
		try {
			const deleted = await deleteMyData();
			const took = Math.round(performance.now() - started);
			console.info(`Deleted my data: ${deleted.files} file(s) (${took} ms)`);
			clearProgress();
			if (!deleted.left.includes("consent.json")) onDeleted?.();
			if (deleted.left.length === 0) {
				window.location.hash = "#/consent";
				return;
			}
			console.error(`Could not delete ${deleted.left.join(", ")}`);
			setFailed(`${deleted.left.length} file(s) could not be deleted, perhaps because another program has them open. Close it and click Delete my data again.`);
		} catch (e) {
			console.error("Could not delete my data", e);
			setFailed(e instanceof ServerRefusal ? e.message : "Your data could not be deleted. Try again.");
		}
		setDeleting(false);
	}
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": "settings-delete",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "settings-delete",
				children: "Your data"
			}),
			/* @__PURE__ */ u("div", {
				className: "switch",
				children: [
					/* @__PURE__ */ u("button", {
						type: "button",
						className: "remove",
						disabled: deleting,
						onClick: () => {
							console.info("Delete my data: asking to confirm");
							setAsking(true);
						},
						children: "Delete my data"
					}),
					/* @__PURE__ */ u("p", {
						className: "muted",
						children: "Deletes the photos, recordings, prepared face and voice, videos, conversation and PDFs with their wiki, then starts setup again. These settings are kept. It asks first."
					}),
					deleting && /* @__PURE__ */ u("p", {
						className: "muted busy",
						children: "Deleting…"
					}),
					failed && /* @__PURE__ */ u("p", {
						className: "error",
						children: failed
					})
				]
			}),
			asking && /* @__PURE__ */ u(ConfirmDialog, {
				title: "Are you sure you want to delete all your data?",
				keepLabel: "No, keep my data",
				confirmLabel: "Yes, delete everything",
				onCancel: cancel,
				onConfirm: remove,
				children: [
					/* @__PURE__ */ u("p", { children: "This deletes all of it:" }),
					/* @__PURE__ */ u("ul", {
						className: "deleted",
						children: DELETED.map((item) => /* @__PURE__ */ u("li", { children: item }, item))
					}),
					/* @__PURE__ */ u("p", { children: "Setup then starts again from the beginning. Your settings are kept." }),
					/* @__PURE__ */ u("p", {
						className: "warning",
						children: "This can't be undone."
					})
				]
			})
		]
	});
}
//#endregion
//#region src/llm-setting.tsx
function LlmSettingSection() {
	const [setting, setSetting] = d(null);
	const [picked, setPicked] = d("local");
	const [key, setKey] = d("");
	const [model, setModel] = d("");
	const [saving, setSaving] = d(false);
	const [error, setError] = d(null);
	const [saved, setSaved] = d(false);
	const [models, setModels] = d(null);
	const asking = A(0);
	const pickedNow = A("local");
	h(() => {
		function accountChanged() {
			getLlm().then((read) => {
				console.info("ChatGPT account changed; LLM setting read again");
				setSetting(read);
				if (pickedNow.current === "chatgpt") pick("chatgpt", read);
			}).catch((e) => console.error("Could not read the LLM setting again", e));
		}
		window.addEventListener(CHATGPT_ACCOUNT_CHANGED, accountChanged);
		return () => window.removeEventListener(CHATGPT_ACCOUNT_CHANGED, accountChanged);
	}, []);
	h(() => {
		getLlm().then((read) => {
			if (!Array.isArray(read.providers)) throw new Error("The LLM setting has no providers");
			setSetting(read);
			pick(read.provider, read);
		}).catch((e) => {
			console.error("Could not read the LLM setting", e);
			setError("The LLM setting could not be read. Reload the page to try again.");
		});
	}, []);
	function pick(id, from = setting) {
		const provider = from?.providers.find((p) => p.id === id);
		pickedNow.current = id;
		setPicked(id);
		setKey("");
		setModel(provider?.model ?? "");
		setSaved(false);
		setError(null);
		setModels(null);
		asking.current += 1;
		if (provider?.has_key || provider?.lists_freely) lookUp(id, void 0, provider.has_key);
	}
	async function lookUp(id, typedKey, savedKey = false) {
		const asked = asking.current += 1;
		setModels({ state: "loading" });
		const started = performance.now();
		try {
			const { ids, names } = await listModels(id, typedKey);
			if (asking.current !== asked) return;
			console.info(`Listed ${ids.length} models for ${id} (${Math.round(performance.now() - started)} ms)`);
			setModels({
				state: "listed",
				ids,
				names,
				checked: Boolean(typedKey) || savedKey
			});
		} catch (e) {
			if (asking.current !== asked) return;
			console.error(`Could not list the models for ${id}`, e);
			const refused = e instanceof ServerRefusal && e.status < 500;
			const error = e instanceof ServerRefusal ? e.message : "The models couldn't be listed.";
			setModels({
				state: "failed",
				error,
				unreachable: !refused
			});
		}
	}
	async function use() {
		setSaving(true);
		setError(null);
		setSaved(false);
		const started = performance.now();
		try {
			const local = picked === "local";
			const typed = key.trim();
			const now = await chooseLlm({
				provider: picked,
				...typed && !local ? { api_key: typed } : {},
				...local ? {} : { model }
			});
			console.info(`LLM changed to ${picked} (${Math.round(performance.now() - started)} ms)`);
			setSetting(now);
			setKey("");
			setModel(now.providers.find((p) => p.id === picked)?.model ?? model);
			setSaved(true);
			if (!local && (typed || models?.state !== "listed")) lookUp(picked, void 0, true);
		} catch (e) {
			console.error(`Could not change the LLM to ${picked}`, e);
			setError(e instanceof ServerRefusal ? e.message : "The LLM could not be changed. Try again.");
		}
		setSaving(false);
	}
	const current = setting?.providers.find((p) => p.id === setting.provider);
	const chosen = setting?.providers.find((p) => p.id === picked);
	const showModel = chosen?.lists_freely || models?.state === "listed" || models?.state === "failed" && models.unreachable;
	return /* @__PURE__ */ u("section", {
		className: "panel llm-setting",
		"aria-labelledby": "settings-llm",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "settings-llm",
				children: "LLM"
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "Who writes the replies. A provider other than the local model needs your own API key, which is kept on the app's server and never shown again. The ChatGPT plan needs a ChatGPT sign-in instead, under ChatGPT plan below."
			}),
			current && /* @__PURE__ */ u("p", {
				className: "current-llm",
				children: ["Answering now: ", /* @__PURE__ */ u("strong", { children: current.label })]
			}),
			setting && /* @__PURE__ */ u("form", {
				onSubmit: (e) => {
					e.preventDefault();
					use();
				},
				children: [
					/* @__PURE__ */ u("fieldset", {
						disabled: saving,
						children: [/* @__PURE__ */ u("legend", {
							className: "sr-only",
							children: "LLM"
						}), setting.providers.map((p) => /* @__PURE__ */ u("label", {
							className: "choice",
							children: [
								/* @__PURE__ */ u("input", {
									type: "radio",
									name: "llm",
									value: p.id,
									checked: picked === p.id,
									onChange: () => pick(p.id)
								}),
								" ",
								/* @__PURE__ */ u("span", { children: [p.label, p.id !== "local" && /* @__PURE__ */ u("span", {
									className: "muted",
									children: [" · ", keyState(p)]
								})] })
							]
						}, p.id))]
					}),
					chosen && chosen.id !== "local" && /* @__PURE__ */ u("div", {
						className: "llm-fields",
						children: [
							!chosen.signs_in && /* @__PURE__ */ u("label", { children: ["API key", /* @__PURE__ */ u("input", {
								type: "password",
								autoComplete: "off",
								value: key,
								placeholder: chosen.has_key ? "Saved. Paste a new key to replace it." : `From ${chosen.keys_at}`,
								onInput: (e) => {
									setKey(e.target.value);
									setError(null);
								},
								onBlur: () => key.trim() && void lookUp(chosen.id, key.trim()),
								disabled: saving
							})] }),
							showModel && /* @__PURE__ */ u("label", { children: ["Model", /* @__PURE__ */ u("input", {
								type: "text",
								list: "llm-models",
								value: model,
								placeholder: chosen.default_model || "First in your plan's list",
								onInput: (e) => setModel(e.target.value),
								disabled: saving
							})] }),
							models?.state === "listed" && /* @__PURE__ */ u("datalist", {
								id: "llm-models",
								children: models.ids.map((id) => /* @__PURE__ */ u("option", {
									value: id,
									label: models.names[id]
								}, id))
							}),
							/* @__PURE__ */ u("p", {
								className: "muted",
								children: modelsNote(models, model || chosen.default_model, chosen)
							})
						]
					}),
					/* @__PURE__ */ u("button", {
						type: "submit",
						className: "use",
						disabled: saving,
						children: saving ? "Saving…" : "Use this LLM"
					})
				]
			}),
			saved && current && /* @__PURE__ */ u("p", {
				className: "muted",
				children: [
					"Saved. ",
					current.label,
					" answers from the next prompt."
				]
			}),
			error && /* @__PURE__ */ u("p", {
				className: "error",
				role: "alert",
				children: error
			})
		]
	});
}
function keyState(provider) {
	if (provider.signs_in) return provider.has_key ? "signed in" : "needs a ChatGPT sign-in";
	return provider.has_key ? "key saved" : "needs a key";
}
function modelsNote(models, model, provider) {
	const blank = provider.default_model ? `Leave the model blank for ${provider.default_model}.` : "Leave the model blank for the first in your plan's list.";
	if (models === null && provider.signs_in) return "Sign in with ChatGPT under ChatGPT plan below to choose one of your plan's models.";
	if (models === null) return `Enter your key to choose one of ${provider.label}'s models.`;
	if (models.state === "loading") return `Looking up ${provider.label}'s models…`;
	if (models.state === "failed") return models.unreachable ? `${models.error} You can still type a model's name.` : models.error;
	const n = models.ids.length;
	const available = `${n} model${n === 1 ? "" : "s"} available: pick one or type a name.`;
	const works = provider.signs_in ? "Signed in." : "The key works.";
	const listed = models.checked ? `${works} ${available}` : available;
	if (!model) return `${listed} ${blank}`;
	if (!models.ids.includes(model)) return `${listed} ${model} isn't in ${provider.label}'s list for this key.`;
	return `${listed} ${blank}`;
}
function reason(e, fallback) {
	return e instanceof ServerRefusal ? e.message : fallback;
}
function VideoAndChat() {
	const [running, setRunning] = d(false);
	const [video, setVideo] = d(null);
	const [testFailed, setTestFailed] = d(null);
	const [clearing, setClearing] = d(false);
	const [cleared, setCleared] = d(false);
	const [clearFailed, setClearFailed] = d(null);
	const { ask, dialog } = useConfirm();
	async function runAgain() {
		setRunning(true);
		setVideo(null);
		setTestFailed(null);
		const started = performance.now();
		try {
			const url = await runVideoTestAgain();
			console.info(`Video test run again (${Math.round(performance.now() - started)} ms)`);
			setVideo(`${url}?made=${Date.now()}`);
		} catch (e) {
			console.error("Could not run the video test again", e);
			setTestFailed(reason(e, "The video could not be made. Try again."));
		}
		setRunning(false);
	}
	async function clear() {
		if (!await ask({
			title: "Clear the whole conversation?",
			children: /* @__PURE__ */ u("p", {
				className: "warning",
				children: "This can't be undone."
			}),
			keepLabel: "No, keep it",
			confirmLabel: "Yes, clear it"
		})) {
			console.info("Clear conversation cancelled");
			return;
		}
		setClearing(true);
		setCleared(false);
		setClearFailed(null);
		const started = performance.now();
		try {
			const turns = await clearChat();
			const took = Math.round(performance.now() - started);
			console.info(`Conversation cleared: ${turns} turn(s) (${took} ms)`);
			setCleared(true);
		} catch (e) {
			console.error("Could not clear the conversation", e);
			setClearFailed(reason(e, "The conversation could not be cleared. Try again."));
		}
		setClearing(false);
	}
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": "settings-video-chat",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "settings-video-chat",
				children: "Video and conversation"
			}),
			/* @__PURE__ */ u("div", {
				className: "switch",
				children: [
					/* @__PURE__ */ u("button", {
						type: "button",
						className: "use",
						disabled: running,
						onClick: runAgain,
						children: "Run the video test again"
					}),
					/* @__PURE__ */ u("p", {
						className: "muted",
						children: "Makes the sample video again from the photo and voice, and plays it."
					}),
					running && /* @__PURE__ */ u("p", {
						className: "muted busy",
						children: "Making the sample video. This can take a few minutes…"
					}),
					testFailed && /* @__PURE__ */ u("p", {
						className: "error",
						children: testFailed
					}),
					video && /* @__PURE__ */ u("div", {
						className: "sample-video",
						children: /* @__PURE__ */ u("video", {
							src: video,
							controls: true,
							autoPlay: true,
							playsInline: true,
							"aria-label": "Sample video"
						})
					})
				]
			}),
			/* @__PURE__ */ u("div", {
				className: "switch",
				children: [
					/* @__PURE__ */ u("button", {
						type: "button",
						className: "use",
						disabled: clearing,
						onClick: clear,
						children: "Clear conversation"
					}),
					/* @__PURE__ */ u("p", {
						className: "muted",
						children: "Removes every question and answer from the chat. It asks first."
					}),
					cleared && /* @__PURE__ */ u("p", {
						className: "muted",
						children: "The conversation was cleared."
					}),
					clearFailed && /* @__PURE__ */ u("p", {
						className: "error",
						children: clearFailed
					})
				]
			}),
			dialog
		]
	});
}
//#endregion
//#region src/checks.tsx
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
			speech !== null && ` · ${minutes$1(speech)} of speech`
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
function minutes$1(seconds) {
	const whole = Math.round(seconds);
	return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
//#endregion
//#region src/your-files.tsx
async function readInUse() {
	if (!(await getConsent()).agreed) return {
		photo: null,
		sounds: []
	};
	const [photos, choice, sounds] = await Promise.all([
		listUploads("photos"),
		getPhotoChoice(),
		listUploads("sounds")
	]);
	return {
		photo: photos.find((p) => p.id === choice.id) ?? null,
		sounds: sounds.filter((s) => s.problems?.length === 0)
	};
}
function isInUse(inUse, id) {
	return inUse.photo?.id === id || inUse.sounds.some((s) => s.id === id);
}
function YourFiles() {
	const [inUse, setInUse] = d(null);
	const [dropped, setDropped] = d([]);
	const [loadFailed, setLoadFailed] = d(false);
	const [checking, setChecking] = d(null);
	const [failed, setFailed] = d(null);
	h(() => {
		readInUse().then((read) => {
			setInUse(read);
			const photo = read.photo?.name ?? "no photo";
			console.info(`Photos and recordings in use: ${photo}, ${read.sounds.length} recording(s)`);
		}).catch((e) => {
			console.error("Could not load the photos and recordings in use", e);
			setLoadFailed(true);
		});
	}, []);
	async function checkAgain(item) {
		if (checking !== null) return;
		setChecking(item.id);
		setFailed(null);
		const started = performance.now();
		let checked = null;
		try {
			checked = await checkUpload(item.kind, item.id);
			const took = Math.round(performance.now() - started);
			const found = checked.problems === null ? "not checked" : `${checked.problems.length} problem(s)`;
			console.info(`Checked again: ${item.name}, ${found} (${took} ms)`);
		} catch (e) {
			console.error(`Could not check ${item.name} again`, e);
			const off = e instanceof ServerRefusal && e.status === 503;
			setFailed({
				id: item.id,
				reason: off ? e.message : "It could not be checked. Try again."
			});
		}
		if (checked) await refresh(checked);
		setChecking(null);
	}
	async function refresh(checked) {
		try {
			const read = await readInUse();
			const out = !isInUse(read, checked.id);
			if (out) console.info(`${checked.name} is no longer in use`);
			setInUse(read);
			setDropped((was) => [...was.filter((u) => u.id !== checked.id && !isInUse(read, u.id)), ...out ? [checked] : []]);
		} catch (e) {
			console.error("Could not read the photos and recordings in use again", e);
			setLoadFailed(true);
		}
	}
	function actions(item) {
		return /* @__PURE__ */ u(S, { children: [
			/* @__PURE__ */ u(Checks, {
				item,
				queue: checking === item.id ? 0 : -1
			}),
			/* @__PURE__ */ u("button", {
				type: "button",
				className: "use",
				disabled: checking !== null,
				onClick: () => checkAgain(item),
				children: "Check again"
			}),
			failed?.id === item.id && /* @__PURE__ */ u("p", {
				className: "error",
				children: failed.reason
			})
		] });
	}
	const photos = inUse ? [...inUse.photo ? [inUse.photo] : [], ...dropped.filter((u) => u.kind === "photos")] : [];
	const sounds = inUse ? [...inUse.sounds, ...dropped.filter((u) => u.kind === "sounds")] : [];
	const isDropped = (item) => dropped.some((u) => u.id === item.id);
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": "settings-files",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "settings-files",
				children: "Photos and recordings"
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "The photo the video is made from, and the recordings the voice is made from."
			}),
			loadFailed && /* @__PURE__ */ u("p", {
				className: "error",
				children: "Could not load them. Reload the page to try again."
			}),
			inUse === null && !loadFailed && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Loading…"
			}),
			inUse && /* @__PURE__ */ u(S, { children: [
				/* @__PURE__ */ u("h3", { children: "Photo" }),
				photos.length > 0 ? /* @__PURE__ */ u("ul", {
					className: "photos",
					children: photos.map((item) => /* @__PURE__ */ u("li", { children: [
						/* @__PURE__ */ u("a", {
							href: uploadUrl("photos", item.id),
							target: "_blank",
							rel: "noreferrer",
							children: /* @__PURE__ */ u("img", {
								src: uploadUrl("photos", item.id),
								alt: item.name
							})
						}),
						/* @__PURE__ */ u("span", {
							className: "name",
							children: item.name
						}),
						isDropped(item) && /* @__PURE__ */ u("span", {
							className: "muted check",
							children: "No longer used for the video"
						}),
						actions(item)
					] }, item.id))
				}) : /* @__PURE__ */ u("p", {
					className: "muted",
					children: [
						"No photo is in use yet. Add one in ",
						/* @__PURE__ */ u("a", {
							href: "#/setup",
							children: "Setup"
						}),
						"."
					]
				}),
				/* @__PURE__ */ u("h3", { children: "Recordings" }),
				sounds.length > 0 ? /* @__PURE__ */ u("ul", {
					className: "sounds",
					children: sounds.map((item) => /* @__PURE__ */ u("li", { children: [
						/* @__PURE__ */ u("audio", {
							controls: true,
							preload: "none",
							src: uploadUrl("sounds", item.id)
						}),
						/* @__PURE__ */ u("span", {
							className: "name",
							children: [item.name, item.seconds !== null && ` (${minutes$1(item.seconds)})`]
						}),
						isDropped(item) && /* @__PURE__ */ u("span", {
							className: "muted check",
							children: "No longer in the voice sample"
						}),
						actions(item)
					] }, item.id))
				}) : /* @__PURE__ */ u("p", {
					className: "muted",
					children: [
						"No recording is in use yet. Add them in ",
						/* @__PURE__ */ u("a", {
							href: "#/setup",
							children: "Setup"
						}),
						"."
					]
				}),
				dropped.length > 0 && /* @__PURE__ */ u("p", {
					className: "muted",
					children: [
						"Add, remove or choose photos and recordings in ",
						/* @__PURE__ */ u("a", {
							href: "#/setup",
							children: "Setup"
						}),
						"."
					]
				})
			] })
		]
	});
}
//#endregion
//#region src/settings.tsx
var SettingsContext = X({
	settings: DEFAULT_SETTINGS,
	loaded: true,
	change: async () => {},
	reload: async () => {}
});
function useSettings() {
	return x(SettingsContext).settings;
}
function useSettingsLoaded() {
	return x(SettingsContext).loaded;
}
function useSettingsReload() {
	return x(SettingsContext).reload;
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
	async function reload() {
		try {
			const read = await getSettings();
			setSettings(read);
			console.info(`Settings read again: the ${read.view} view`);
		} catch (e) {
			console.error("Could not read the settings again", e);
		}
	}
	return /* @__PURE__ */ u(SettingsContext.Provider, {
		value: {
			settings,
			loaded,
			change,
			reload
		},
		children
	});
}
var VIEWS = [[
	"host",
	"Host (Teacher)",
	"every page and option"
], [
	"participant",
	"Participant (Student)",
	"the chat and a read-only wiki"
]];
var SWITCHES = [{
	group: "Chat",
	about: "What the person in the video answers, and the buttons under the prompt box.",
	items: [
		[
			"general_prompts",
			"Answer questions outside the content",
			"Off: a question the PDFs don't cover gets a short, polite reply instead of an answer."
		],
		[
			"teach_me",
			"Teach me",
			"A Teach me button that teaches the content a part at a time."
		],
		[
			"quiz_me",
			"Quiz me",
			"A Quiz me button that asks five questions on a topic and judges each answer."
		],
		[
			"assessment",
			"Assessment",
			"An Assessment button that asks questions across all the content, then says how broad and deep your knowledge is."
		]
	]
}, {
	group: "Display",
	about: "What else is shown on the pages.",
	items: [[
		"show_metrics",
		"Show timing metrics",
		"How long replies and other steps take, under the video and on the pages."
	], [
		"debug",
		"Debug",
		"Copy chat under the conversation, to paste the latest exchanges somewhere else."
	]]
}];
var ICON = /* @__PURE__ */ u("svg", {
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
});
function SettingsLink({ current }) {
	return /* @__PURE__ */ u("a", {
		href: "#/settings",
		className: current ? "settings-link current" : "settings-link",
		children: [ICON, "Settings"]
	});
}
function SettingsPage({ back, onDataDeleted }) {
	const { settings, change } = x(SettingsContext);
	const [failed, setFailed] = d(false);
	const page = A(null);
	h(() => console.info(`Settings page opened, returning to ${back}`), [back]);
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
	const host = useHost().session?.signed_in === true;
	function chooseView(view) {
		const was = settings.view;
		save({ view }, () => {
			const box = page.current?.querySelector(`input[value="${was}"]`);
			if (box) box.checked = true;
		});
	}
	return /* @__PURE__ */ u("div", {
		className: "host-page settings-page",
		ref: page,
		children: [
			/* @__PURE__ */ u("h1", { children: "Settings" }),
			/* @__PURE__ */ u("p", {
				className: "lead",
				children: "Changes are saved at once and kept after a restart."
			}),
			failed && /* @__PURE__ */ u("p", {
				className: "error",
				children: "The setting could not be changed. Try again."
			}),
			host && /* @__PURE__ */ u("section", {
				className: "panel",
				"aria-labelledby": "settings-view",
				children: [
					/* @__PURE__ */ u("h2", {
						id: "settings-view",
						children: "View"
					}),
					/* @__PURE__ */ u("p", {
						className: "muted",
						children: "Who the app is set out for."
					}),
					/* @__PURE__ */ u("fieldset", { children: [/* @__PURE__ */ u("legend", {
						className: "sr-only",
						children: "View"
					}), VIEWS.map(([view, label, about]) => /* @__PURE__ */ u("label", {
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
					}, view))] })
				]
			}),
			SWITCHES.map(({ group, about, items }) => /* @__PURE__ */ u("section", {
				className: "panel",
				"aria-labelledby": `settings-${group}`,
				children: [
					/* @__PURE__ */ u("h2", {
						id: `settings-${group}`,
						children: group
					}),
					/* @__PURE__ */ u("p", {
						className: "muted",
						children: about
					}),
					items.map(([name, label, help]) => /* @__PURE__ */ u("div", {
						className: "switch",
						children: [/* @__PURE__ */ u("label", { children: [
							/* @__PURE__ */ u("input", {
								type: "checkbox",
								checked: settings[name],
								onChange: (e) => {
									const box = e.currentTarget;
									save({ [name]: box.checked }, () => box.checked = !box.checked);
								}
							}),
							" ",
							label
						] }), /* @__PURE__ */ u("p", {
							className: "muted",
							children: help
						})]
					}, name)),
					group === "Chat" && host && /* @__PURE__ */ u("div", {
						className: "switch",
						children: [/* @__PURE__ */ u("a", {
							href: "#/customization",
							children: "Customization"
						}), /* @__PURE__ */ u("p", {
							className: "muted",
							children: "Who the person in the video is and their goals, given to the LLM with every prompt."
						})]
					})
				]
			}, group)),
			settings.view === "host" && /* @__PURE__ */ u(LlmSettingSection, {}),
			settings.view === "host" && /* @__PURE__ */ u(ChatGptPlanSection, {}),
			/* @__PURE__ */ u(YourFiles, {}),
			settings.view === "host" && /* @__PURE__ */ u(ChangeSetup, {}),
			/* @__PURE__ */ u(VideoAndChat, {}),
			settings.view === "host" && /* @__PURE__ */ u(DeleteData, { onDeleted: onDataDeleted }),
			/* @__PURE__ */ u(AdminSection, {}),
			/* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("a", {
				className: "button",
				href: back,
				children: "Return to the app"
			}) })
		]
	});
}
var HostContext = X({
	session: null,
	signUp: async () => {},
	signIn: async () => {},
	signOut: async () => {}
});
function useHost() {
	return x(HostContext);
}
var SIGNED_OUT = {
	signed_in: false,
	email: null
};
function HostProvider({ children }) {
	const [session, setSession] = d(null);
	const reload = useSettingsReload();
	h(() => {
		getHostSession().then(setSession, (e) => {
			console.error("Could not read the host sign-in", e);
			setSession(SIGNED_OUT);
		});
	}, []);
	async function account(kind, email, password) {
		const started = performance.now();
		const signedIn = await (kind === "up" ? signUpAsHost : signInAsHost)(email, password);
		console.info(`Host signed ${kind} (${Math.round(performance.now() - started)} ms)`);
		setSession(signedIn);
		await reload();
	}
	async function signOut() {
		await signOutAsHost();
		console.info("Host signed out");
		setSession(SIGNED_OUT);
		await reload();
	}
	const shared = {
		session,
		signUp: (email, password) => account("up", email, password),
		signIn: (email, password) => account("in", email, password),
		signOut
	};
	return /* @__PURE__ */ u(HostContext.Provider, {
		value: shared,
		children
	});
}
function HostLinks({ page }) {
	const { session, signOut } = useHost();
	const [busy, setBusy] = d(false);
	if (!session) return null;
	if (session.signed_in) {
		async function leave() {
			setBusy(true);
			try {
				await signOut();
				window.location.hash = "#/chat";
			} catch (e) {
				console.error("Could not sign out as host", e);
			} finally {
				setBusy(false);
			}
		}
		return /* @__PURE__ */ u("span", {
			className: "host-links",
			children: [
				/* @__PURE__ */ u("a", {
					href: "#/resources",
					className: page === "resources" ? "settings-link current" : "settings-link",
					children: "Resources"
				}),
				/* @__PURE__ */ u("span", {
					className: "host-email",
					title: "Signed in as host",
					children: session.email
				}),
				/* @__PURE__ */ u("button", {
					type: "button",
					className: "secondary",
					disabled: busy,
					onClick: () => void leave(),
					children: "Sign out"
				})
			]
		});
	}
	const link = (to, href, label) => /* @__PURE__ */ u("a", {
		href,
		className: page === to ? "settings-link current" : "settings-link",
		children: label
	});
	return /* @__PURE__ */ u("span", {
		className: "host-links",
		children: [link("host-sign-up", "#/host/sign-up", "Host sign up"), link("host-sign-in", "#/host/sign-in", "Host sign in")]
	});
}
function HostAccountPage({ kind }) {
	const { session, signUp, signIn } = useHost();
	const [email, setEmail] = d("");
	const [password, setPassword] = d("");
	const [again, setAgain] = d("");
	const [busy, setBusy] = d(false);
	const [error, setError] = d(null);
	const up = kind === "up";
	h(() => {
		setError(null);
		hostPageOpened(up ? "sign-up" : "sign-in").catch((e) => console.error("Could not log the host page opened", e));
	}, [up]);
	function problem() {
		if (!up) return null;
		if (password.length < 10) return `The password must be at least 10 characters.`;
		if (password !== again) return "The two passwords are different.";
		return null;
	}
	async function submit(e) {
		e.preventDefault();
		const found = problem();
		setError(found);
		if (found) return;
		setBusy(true);
		try {
			await (up ? signUp : signIn)(email, password);
			window.location.hash = "#/";
		} catch (err) {
			console.error(`Could not sign ${kind} as host`, err);
			setError(err instanceof ServerRefusal ? err.message : "That didn't work. Please try again.");
		} finally {
			setBusy(false);
		}
	}
	const title = up ? "Host sign up" : "Host sign in";
	if (session?.signed_in) return /* @__PURE__ */ u("div", {
		className: "host-page host-account",
		children: [/* @__PURE__ */ u("h1", { children: title }), /* @__PURE__ */ u("p", { children: [
			"You are signed in as host with ",
			session.email,
			". ",
			/* @__PURE__ */ u("a", {
				href: "#/",
				children: "Go to the home page"
			})
		] })]
	});
	return /* @__PURE__ */ u("div", {
		className: "host-page host-account",
		children: [
			/* @__PURE__ */ u("h1", { children: title }),
			/* @__PURE__ */ u("p", {
				className: "lead",
				children: up ? "Make a host account to set up the person and their content." : "Sign in with the email and password of your host account."
			}),
			/* @__PURE__ */ u("form", {
				onSubmit: (e) => void submit(e),
				noValidate: true,
				children: [
					/* @__PURE__ */ u("label", { children: ["Email", /* @__PURE__ */ u("input", {
						type: "email",
						autoComplete: "email",
						value: email,
						onInput: (e) => setEmail(e.currentTarget.value)
					})] }),
					/* @__PURE__ */ u("label", { children: [
						"Password",
						up && ` (at least 10 characters)`,
						/* @__PURE__ */ u("input", {
							type: "password",
							autoComplete: up ? "new-password" : "current-password",
							value: password,
							onInput: (e) => setPassword(e.currentTarget.value)
						})
					] }),
					up && /* @__PURE__ */ u("label", { children: ["Password again", /* @__PURE__ */ u("input", {
						type: "password",
						autoComplete: "new-password",
						value: again,
						onInput: (e) => setAgain(e.currentTarget.value)
					})] }),
					error && /* @__PURE__ */ u("p", {
						className: "error",
						role: "alert",
						children: error
					}),
					/* @__PURE__ */ u("button", {
						type: "submit",
						disabled: busy || email.trim() === "" || password === "",
						children: up ? "Sign up" : "Sign in"
					})
				]
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: up ? /* @__PURE__ */ u(S, { children: ["Already a host? ", /* @__PURE__ */ u("a", {
					href: "#/host/sign-in",
					children: "Host sign in"
				})] }) : /* @__PURE__ */ u(S, { children: ["New here? ", /* @__PURE__ */ u("a", {
					href: "#/host/sign-up",
					children: "Host sign up"
				})] })
			})
		]
	});
}
function HostOnlyPage() {
	h(() => console.info(`Host page refused: ${window.location.hash}`), []);
	return /* @__PURE__ */ u("div", {
		className: "host-page host-account",
		children: [
			/* @__PURE__ */ u("h1", { children: "For the host only" }),
			/* @__PURE__ */ u("p", {
				className: "lead",
				children: "This page is for the host, who sets up the person and their content."
			}),
			/* @__PURE__ */ u("p", { children: [
				/* @__PURE__ */ u("a", {
					className: "button",
					href: "#/host/sign-in",
					children: "Host sign in"
				}),
				" ",
				"or ",
				/* @__PURE__ */ u("a", {
					href: "#/chat",
					children: "go to the chat"
				})
			] })
		]
	});
}
//#endregion
//#region src/customization.tsx
var IDENTITY$1 = [
	[
		"name",
		"Name",
		"Said first to \"Who are you?\": I'm …"
	],
	[
		"speaks_as",
		"Speaks as",
		"Told to the LLM only."
	],
	[
		"purpose",
		"Purpose",
		"My purpose is …"
	],
	[
		"audience",
		"Who it is for",
		"I'm here for …"
	],
	[
		"helps_with",
		"What it can help with",
		"I can help with …"
	]
];
var SAVED$1 = "Saved. It is used from the next prompt.";
var SAVED_EVENT = "customization-saved";
function useSave(announce = true, name = "Customization") {
	const [busy, setBusy] = d(false);
	const [said, setSaid] = d(null);
	async function run(part, save) {
		setBusy(true);
		setSaid(null);
		const started = performance.now();
		try {
			const saved = await save();
			console.info(`${name} saved: ${part} (${Math.round(performance.now() - started)} ms)`);
			setSaid({
				ok: true,
				text: SAVED$1
			});
			if (announce) window.dispatchEvent(new Event(SAVED_EVENT));
			return saved;
		} catch (e) {
			console.error(`Could not save the ${name.toLowerCase()}: ${part}`, e);
			setSaid({
				ok: false,
				text: e instanceof ServerRefusal ? e.message : "Could not save. Try again."
			});
			return null;
		} finally {
			setBusy(false);
		}
	}
	return {
		busy,
		run,
		status: said && /* @__PURE__ */ u("p", {
			className: said.ok ? "notice" : "error",
			role: "status",
			children: said.text
		}),
		changed: () => setSaid(null)
	};
}
function IdentitySection$1({ identity }) {
	const [fields, setFields] = d(identity);
	const { busy, run, status, changed } = useSave();
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": "customization-identity",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "customization-identity",
				children: "Identity"
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "Who the person in the video is. \"Who are you?\" is answered from it."
			}),
			/* @__PURE__ */ u("form", {
				className: "customization-edit",
				onSubmit: (e) => {
					e.preventDefault();
					run("identity", () => saveIdentity(fields)).then((saved) => {
						if (saved) setFields(saved.identity);
					});
				},
				children: [
					IDENTITY$1.map(([key, label, about]) => /* @__PURE__ */ u("label", { children: [/* @__PURE__ */ u("span", { children: [label, /* @__PURE__ */ u("span", {
						className: "muted",
						children: [" · ", about]
					})] }), /* @__PURE__ */ u("input", {
						value: fields[key],
						readOnly: busy,
						onInput: (e) => {
							changed();
							setFields({
								...fields,
								[key]: e.currentTarget.value
							});
						}
					})] }, key)),
					status,
					/* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("button", {
						type: "submit",
						disabled: busy,
						children: "Save the identity"
					}) })
				]
			})
		]
	});
}
function GoalsSection$1({ goals }) {
	const [text, setText] = d(goals.join("\n"));
	const { busy, run, status, changed } = useSave();
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": "customization-goals",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "customization-goals",
				children: "Goals"
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "What every reply aims for, one goal on each line."
			}),
			/* @__PURE__ */ u("form", {
				className: "customization-edit",
				onSubmit: (e) => {
					e.preventDefault();
					run("goals", () => saveGoals(text.split("\n"))).then((saved) => {
						if (saved) setText(saved.goals.join("\n"));
					});
				},
				children: [
					/* @__PURE__ */ u("label", { children: [/* @__PURE__ */ u("span", {
						className: "sr-only",
						children: "Goals"
					}), /* @__PURE__ */ u("textarea", {
						rows: 4,
						value: text,
						readOnly: busy,
						onInput: (e) => {
							changed();
							setText(e.currentTarget.value);
						}
					})] }),
					status,
					/* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("button", {
						type: "submit",
						disabled: busy,
						children: "Save the goals"
					}) })
				]
			})
		]
	});
}
function FeatureGuidelines$1({ feature }) {
	const [shown, setShown] = d(feature);
	const [text, setText] = d(feature.text);
	const { busy, run, status, changed } = useSave();
	function save(value) {
		run(`guidelines ${shown.key}`, () => saveGuidelines(shown.key, value)).then((saved) => {
			const now = saved?.features.find((f) => f.key === shown.key);
			if (now) {
				setShown(now);
				setText(now.text);
			}
		});
	}
	return /* @__PURE__ */ u("form", {
		className: "customization-edit guideline",
		"aria-label": shown.label,
		onSubmit: (e) => {
			e.preventDefault();
			save(text);
		},
		children: [
			/* @__PURE__ */ u("label", { children: [/* @__PURE__ */ u("span", { children: [
				shown.label,
				!shown.edited && /* @__PURE__ */ u("span", {
					className: "muted",
					children: " · as shipped"
				}),
				shown.generated && /* @__PURE__ */ u("span", {
					className: "muted",
					children: " · drafted by the LLM"
				})
			] }), /* @__PURE__ */ u("textarea", {
				rows: 4,
				value: text,
				readOnly: busy,
				onInput: (e) => {
					changed();
					setText(e.currentTarget.value);
				}
			})] }),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: [
					shown.changes,
					" ",
					shown.stays
				]
			}),
			status,
			/* @__PURE__ */ u("p", { children: [
				/* @__PURE__ */ u("button", {
					type: "submit",
					disabled: busy,
					children: "Save"
				}),
				" ",
				/* @__PURE__ */ u("button", {
					type: "button",
					className: "secondary",
					disabled: busy || !shown.edited,
					onClick: () => save(null),
					children: "Set back to how it shipped"
				})
			] })
		]
	});
}
var SECTION_ABOUT = {
	Guidelines: "How each feature writes what it says.",
	Assessment: "How the assessment writes its questions and judges the answers.",
	"Level of detail": "What the Level of detail bar on the chat screen asks of each reply, from High level to In depth."
};
function sections$1(features) {
	const grouped = /* @__PURE__ */ new Map();
	for (const feature of features) {
		const section = feature.section || "Guidelines";
		grouped.set(section, [...grouped.get(section) ?? [], feature]);
	}
	return [...grouped.entries()];
}
function GuidelineSection({ name, features }) {
	const id = `customization-${name.toLowerCase().replace(/[^a-z]+/g, "-")}`;
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": id,
		children: [
			/* @__PURE__ */ u("h2", {
				id,
				children: name
			}),
			SECTION_ABOUT[name] && /* @__PURE__ */ u("p", {
				className: "muted",
				children: SECTION_ABOUT[name]
			}),
			features.length ? features.map((feature) => /* @__PURE__ */ u(FeatureGuidelines$1, { feature }, feature.key)) : /* @__PURE__ */ u("p", {
				className: "muted",
				children: "No feature has guidelines to edit yet."
			})
		]
	});
}
var DRAFTED_IDENTITY = [
	["name", "Name"],
	["purpose", "Purpose"],
	["audience", "Who it is for"],
	["helps_with", "What it can help with"]
];
function draftRows(now, { draft, drafted }) {
	const textOf = (c, key) => c.features.find((f) => f.key === key)?.text ?? "";
	return [
		...DRAFTED_IDENTITY.map(([key, label]) => [
			label,
			now.identity[key],
			draft.identity[key]
		]),
		[
			"Goals",
			now.goals.join("\n"),
			draft.goals.join("\n")
		],
		...draft.features.filter((f) => drafted.includes(f.key)).map((f) => [
			f.label,
			textOf(now, f.key),
			f.text
		])
	];
}
function GenerateSection({ now, onSaved }) {
	const [draft, setDraft] = d(null);
	const [writing, setWriting] = d(false);
	const [error, setError] = d(null);
	const { busy, run, status, changed } = useSave();
	async function generate() {
		setWriting(true);
		setError(null);
		changed();
		const started = performance.now();
		try {
			setDraft(await generateDraft());
			console.info(`Customization draft made (${Math.round(performance.now() - started)} ms)`);
		} catch (e) {
			console.error("Could not make a customization draft", e);
			setError(e instanceof ServerRefusal ? e.message : "A draft could not be made. Try again.");
		} finally {
			setWriting(false);
		}
	}
	function discard() {
		setDraft(null);
		discardDraft().catch((e) => console.error("Could not discard the draft", e));
	}
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": "customization-generate",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "customization-generate",
				children: "Generate again"
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "The LLM drafts the identity, the goals and every feature's guidelines you haven't changed, from the person and the content. Guidelines you changed are left alone. Only Save keeps the draft."
			}),
			!draft && /* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("button", {
				type: "button",
				disabled: writing,
				onClick: () => void generate(),
				children: "Generate again"
			}) }),
			writing && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Writing a draft. This can take up to two minutes…"
			}),
			error && /* @__PURE__ */ u("p", {
				className: "error",
				children: error
			}),
			draft && /* @__PURE__ */ u("div", {
				className: "customization-draft",
				children: [
					/* @__PURE__ */ u("table", { children: [/* @__PURE__ */ u("thead", { children: /* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("th", {
							scope: "col",
							children: "Part"
						}),
						/* @__PURE__ */ u("th", {
							scope: "col",
							children: "Now"
						}),
						/* @__PURE__ */ u("th", {
							scope: "col",
							children: "Draft"
						})
					] }) }), /* @__PURE__ */ u("tbody", { children: draftRows(now, draft).map(([label, current, drafted]) => /* @__PURE__ */ u("tr", { children: [
						/* @__PURE__ */ u("th", {
							scope: "row",
							children: label
						}),
						/* @__PURE__ */ u("td", {
							className: "muted",
							children: current
						}),
						/* @__PURE__ */ u("td", { children: drafted })
					] }, label)) })] }),
					status,
					/* @__PURE__ */ u("p", { children: [
						/* @__PURE__ */ u("button", {
							type: "button",
							disabled: busy,
							onClick: () => void run("draft", () => saveDraft(draft)).then((saved) => {
								if (saved) {
									setDraft(null);
									onSaved(saved);
								}
							}),
							children: "Save the draft"
						}),
						" ",
						/* @__PURE__ */ u("button", {
							type: "button",
							className: "secondary",
							disabled: busy,
							onClick: discard,
							children: "Discard"
						})
					] })
				]
			})
		]
	});
}
var MADE_BY = {
	shipped: "As shipped",
	generated: "Drafted by the LLM",
	saved: "Saved"
};
function preview(change) {
	const { value } = change;
	if (value === null) return "As shipped.";
	if (typeof value === "string") return value || "Empty.";
	if (Array.isArray(value)) return value.join(" ") || "No goals.";
	return [
		"name",
		"purpose",
		"audience",
		"helps_with"
	].map((k) => value[k]).filter(Boolean).join(" · ") || "Empty.";
}
function when$1(at) {
	const date = new Date(at);
	return Number.isNaN(date.getTime()) ? at : date.toLocaleString();
}
function editorOf(prefix, part, label) {
	if (part === "identity" || part === "goals") return document.getElementById(`${prefix}-${part}`) ?? void 0;
	return Array.from(document.querySelectorAll("form")).find((f) => f.getAttribute("aria-label") === label);
}
function Comparison({ h, shown, onHide }) {
	return /* @__PURE__ */ u("div", {
		className: "customization-compare",
		role: "region",
		"aria-label": `${h.label} compared`,
		children: [
			/* @__PURE__ */ u("p", { children: [/* @__PURE__ */ u("strong", { children: [
				"Change ",
				shown.earlier,
				" beside change ",
				shown.current,
				" (in use)"
			] }), /* @__PURE__ */ u("span", {
				className: "muted",
				children: " · added text is marked, removed text is struck through"
			})] }),
			/* @__PURE__ */ u("p", {
				className: "compare-text",
				children: shown.runs.map((r, i) => r.kind === "added" ? /* @__PURE__ */ u("ins", { children: r.text }, i) : r.kind === "removed" ? /* @__PURE__ */ u("del", { children: r.text }, i) : /* @__PURE__ */ u("span", { children: r.text }, i))
			}),
			/* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				onClick: onHide,
				children: "Hide the comparison"
			}) })
		]
	});
}
var CUSTOMIZATION_HISTORY = {
	name: "Customization",
	idPrefix: "customization",
	madeBy: MADE_BY,
	load: getCustomizationHistory,
	restore: restoreCustomizationChange,
	compare: compareCustomizationChange
};
function HistorySection({ source, onRestored }) {
	const [histories, setHistories] = d(null);
	const [open, setOpen] = d(false);
	const [error, setError] = d(null);
	const [comparison, setComparison] = d(null);
	const asked = A(0);
	function dropComparison() {
		asked.current += 1;
		setComparison(null);
		setCompareError(null);
	}
	const [compareError, setCompareError] = d(null);
	const { busy, run, status, changed } = useSave(false, source.name);
	h(() => {
		function hide() {
			setOpen((was) => {
				if (was) console.info(`${source.name} history hidden after a save`);
				return false;
			});
		}
		window.addEventListener(SAVED_EVENT, hide);
		return () => window.removeEventListener(SAVED_EVENT, hide);
	}, []);
	async function load(opened) {
		setError(null);
		const started = performance.now();
		try {
			const got = await source.load(opened);
			setHistories(got);
			console.info(`${source.name} history shown: ${got.length} parts (${Math.round(performance.now() - started)} ms)`);
		} catch (e) {
			console.error(`Could not read the ${source.name.toLowerCase()} history`, e);
			setError("The history could not be read. Try again.");
		}
	}
	function toggle() {
		changed();
		dropComparison();
		if (open) {
			setOpen(false);
			return;
		}
		setOpen(true);
		load(true);
	}
	async function compare(h, number) {
		if (!source.compare) return;
		dropComparison();
		const mine = asked.current;
		const started = performance.now();
		try {
			const got = await source.compare(h.part, number);
			if (mine !== asked.current) {
				console.info(`${source.name} comparison dropped: ${h.label}, change ${number}, as another was asked for`);
				return;
			}
			setComparison(got);
			console.info(`${source.name} compared: ${h.label}, change ${number} with ${h.current} (${Math.round(performance.now() - started)} ms)`);
		} catch (e) {
			if (mine !== asked.current) return;
			console.error("Could not compare the changes", e);
			setCompareError({
				part: h.part,
				text: e instanceof ServerRefusal ? e.message : "They could not be compared. Try again."
			});
		}
	}
	async function goBack(h, number) {
		dropComparison();
		const saved = await run(`${h.label} back to change ${number}`, () => source.restore(h.part, number));
		if (saved) {
			console.info(`${source.name} restored: ${h.label}, change ${number}`);
			onRestored(saved, h.part);
			await load(false);
		}
	}
	function edit(h) {
		editorOf(source.idPrefix, h.part, h.label)?.scrollIntoView({ behavior: "smooth" });
	}
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": "customization-history",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "customization-history",
				children: "History"
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "Each part keeps its own changes. Go back makes an earlier change the one in use for that part only, and adds no change; editing it after adds one."
			}),
			/* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				"aria-expanded": open,
				onClick: toggle,
				children: open ? "Hide the history" : "History"
			}) }),
			open && error && /* @__PURE__ */ u("p", {
				className: "error",
				children: error
			}),
			open && !error && histories === null && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Loading…"
			}),
			open && histories?.length === 0 && /* @__PURE__ */ u("p", {
				className: "muted",
				children: "Nothing has been changed yet. Each change from now on is kept here."
			}),
			open && histories?.map((h) => /* @__PURE__ */ u("div", {
				className: "customization-history",
				role: "group",
				"aria-label": h.label,
				children: [
					/* @__PURE__ */ u("h3", { children: h.label }),
					/* @__PURE__ */ u("ol", {
						reversed: true,
						children: h.changes.map((c) => /* @__PURE__ */ u("li", { children: [/* @__PURE__ */ u("span", { children: [
							/* @__PURE__ */ u("strong", { children: ["Change ", c.number] }),
							c.number === h.current && " (in use)",
							" · ",
							source.madeBy[c.made_by],
							/* @__PURE__ */ u("span", {
								className: "muted",
								children: [" · ", when$1(c.made_at)]
							}),
							/* @__PURE__ */ u("span", {
								className: "change-preview",
								children: preview(c)
							})
						] }), c.number === h.current ? /* @__PURE__ */ u("button", {
							type: "button",
							className: "secondary",
							onClick: () => edit(h),
							children: "Edit"
						}) : /* @__PURE__ */ u("span", {
							className: "change-actions",
							children: [source.compare && /* @__PURE__ */ u("button", {
								type: "button",
								className: "secondary",
								"aria-label": `Compare ${h.label} change ${c.number} with the change in use`,
								onClick: () => void compare(h, c.number),
								children: "Compare"
							}), /* @__PURE__ */ u("button", {
								type: "button",
								disabled: busy,
								"aria-label": `Go back to ${h.label} change ${c.number}`,
								onClick: () => void goBack(h, c.number),
								children: "Go back"
							})]
						})] }, c.number))
					}),
					comparison?.part === h.part && /* @__PURE__ */ u(Comparison, {
						h,
						shown: comparison,
						onHide: dropComparison
					}),
					compareError?.part === h.part && /* @__PURE__ */ u("p", {
						className: "error",
						children: compareError.text
					})
				]
			}, h.part)),
			open && status
		]
	});
}
function CustomizationPage() {
	const session = useHost().session;
	const host = session?.signed_in === true;
	const [read, setRead] = d(null);
	const [saves, setSaves] = d(0);
	const [failed, setFailed] = d(false);
	h(() => {
		if (!host) return;
		getCustomization(true).then((got) => {
			setRead(got);
			console.info(`Customization page opened: shipped=${got.shipped}`);
		}, (e) => {
			console.error("Could not read the customization", e);
			setFailed(true);
		});
	}, [host]);
	if (session === null) return /* @__PURE__ */ u("p", { children: "Loading…" });
	if (!host) return /* @__PURE__ */ u(HostOnlyPage, {});
	return /* @__PURE__ */ u("div", {
		className: "host-page customization-page",
		children: [
			/* @__PURE__ */ u("h1", { children: "Customization" }),
			/* @__PURE__ */ u("p", {
				className: "lead",
				children: "Who the person in the video is, what they aim for, and how each feature answers, given to the LLM with every prompt."
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "The administrator's requirements, if any, come before yours."
			}),
			failed && /* @__PURE__ */ u("p", {
				className: "error",
				children: "The customization could not be read. Reload to try again."
			}),
			!failed && read === null && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Loading…"
			}),
			read && /* @__PURE__ */ u(S, { children: [
				/* @__PURE__ */ u(GenerateSection, {
					now: read,
					onSaved: (saved) => {
						setRead({
							...saved,
							shipped: false
						});
						setSaves((n) => n + 1);
					}
				}),
				/* @__PURE__ */ u(HistorySection, {
					source: CUSTOMIZATION_HISTORY,
					onRestored: (saved) => {
						setRead({
							...saved,
							shipped: false
						});
						setSaves((n) => n + 1);
					}
				}),
				/* @__PURE__ */ u(IdentitySection$1, { identity: read.identity }, `identity-${saves}`),
				/* @__PURE__ */ u(GoalsSection$1, { goals: read.goals }, `goals-${saves}`),
				read.features.length ? sections$1(read.features).map(([name, features]) => /* @__PURE__ */ u(GuidelineSection, {
					name,
					features
				}, `${name}-${saves}`)) : /* @__PURE__ */ u(GuidelineSection, {
					name: "Guidelines",
					features: []
				})
			] })
		]
	});
}
//#endregion
//#region src/admin-guidelines.tsx
var IDENTITY = [
	["name", "Name"],
	["speaks_as", "Speaks as"],
	["purpose", "Purpose"],
	["audience", "Who it is for"],
	["helps_with", "What it can help with"]
];
var SAVED = "Saved. It is followed first from the next prompt, for every host.";
var CLEARED = "Cleared. The host's are followed alone from the next prompt.";
function editOf(read) {
	return {
		identity: read.identity,
		goals: read.goals,
		guidelines: read.guidelines
	};
}
function usePart(save) {
	const [busy, setBusy] = d(false);
	const [said, setSaid] = d(null);
	async function run(part, change, done = SAVED) {
		setBusy(true);
		setSaid(null);
		const saved = await save(part, change);
		setBusy(false);
		setSaid(saved ? done : null);
		if (saved) window.dispatchEvent(new Event(SAVED_EVENT));
		return saved;
	}
	return {
		busy,
		run,
		status: said && /* @__PURE__ */ u("p", {
			className: "notice",
			role: "status",
			children: said
		}),
		changed: () => setSaid(null)
	};
}
function Buttons({ busy, part, empty, onClear }) {
	return /* @__PURE__ */ u("p", { children: [
		/* @__PURE__ */ u("button", {
			type: "submit",
			disabled: busy,
			children: part ? `Save ${part}` : "Save"
		}),
		" ",
		/* @__PURE__ */ u("button", {
			type: "button",
			className: "secondary",
			disabled: busy || empty,
			onClick: onClear,
			children: part ? `Clear ${part}` : "Clear"
		})
	] });
}
function IdentitySection({ identity, save }) {
	const [fields, setFields] = d(identity);
	const [kept, setKept] = d(identity);
	const { busy, run, status, changed } = usePart(save);
	const blank = Object.fromEntries(IDENTITY.map(([k]) => [k, ""]));
	function put(value, done) {
		run("identity", { identity: value }, done).then((saved) => {
			if (saved) {
				setFields(saved.identity);
				setKept(saved.identity);
			}
		});
	}
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": "admin-guidelines-identity",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "admin-guidelines-identity",
				children: "Identity"
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "Told to the LLM before the host's identity. \"Who are you?\" is still answered from the host's."
			}),
			/* @__PURE__ */ u("form", {
				className: "customization-edit",
				onSubmit: (e) => {
					e.preventDefault();
					put(fields);
				},
				children: [
					IDENTITY.map(([key, label]) => /* @__PURE__ */ u("label", { children: [/* @__PURE__ */ u("span", { children: label }), /* @__PURE__ */ u("input", {
						value: fields[key],
						readOnly: busy,
						onInput: (e) => {
							changed();
							setFields({
								...fields,
								[key]: e.currentTarget.value
							});
						}
					})] }, key)),
					status,
					/* @__PURE__ */ u(Buttons, {
						busy,
						part: "the identity",
						empty: !Object.values(kept).some(Boolean),
						onClear: () => put(blank, CLEARED)
					})
				]
			})
		]
	});
}
function GoalsSection({ goals, save }) {
	const [text, setText] = d(goals.join("\n"));
	const [kept, setKept] = d(goals);
	const { busy, run, status, changed } = usePart(save);
	function put(value, done) {
		run("goals", { goals: value }, done).then((saved) => {
			if (saved) {
				setText(saved.goals.join("\n"));
				setKept(saved.goals);
			}
		});
	}
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": "admin-guidelines-goals",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "admin-guidelines-goals",
				children: "Goals"
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "What every reply aims for first, one goal on each line."
			}),
			/* @__PURE__ */ u("form", {
				className: "customization-edit",
				onSubmit: (e) => {
					e.preventDefault();
					put(text.split("\n"));
				},
				children: [
					/* @__PURE__ */ u("label", { children: [/* @__PURE__ */ u("span", {
						className: "sr-only",
						children: "Goals"
					}), /* @__PURE__ */ u("textarea", {
						rows: 4,
						value: text,
						readOnly: busy,
						onInput: (e) => {
							changed();
							setText(e.currentTarget.value);
						}
					})] }),
					status,
					/* @__PURE__ */ u(Buttons, {
						busy,
						part: "the goals",
						empty: kept.length === 0,
						onClear: () => put([], CLEARED)
					})
				]
			})
		]
	});
}
function FeatureGuidelines({ feature, save }) {
	const [text, setText] = d(feature.text);
	const [kept, setKept] = d(feature.text);
	const { busy, run, status, changed } = usePart(save);
	function put(value, done) {
		run(`guidelines ${feature.key}`, { guidelines: { [feature.key]: value } }, done).then((saved) => {
			if (saved) {
				const now = saved.guidelines[feature.key] ?? "";
				setText(now);
				setKept(now);
			}
		});
	}
	return /* @__PURE__ */ u("form", {
		className: "customization-edit guideline",
		"aria-label": feature.label,
		onSubmit: (e) => {
			e.preventDefault();
			put(text);
		},
		children: [
			/* @__PURE__ */ u("label", { children: [/* @__PURE__ */ u("span", { children: [feature.label, !kept && /* @__PURE__ */ u("span", {
				className: "muted",
				children: " · none"
			})] }), /* @__PURE__ */ u("textarea", {
				rows: 3,
				value: text,
				readOnly: busy,
				onInput: (e) => {
					changed();
					setText(e.currentTarget.value);
				}
			})] }),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: feature.changes
			}),
			status,
			/* @__PURE__ */ u(Buttons, {
				busy,
				empty: !kept,
				onClear: () => put("", CLEARED)
			})
		]
	});
}
function sections(features) {
	const grouped = /* @__PURE__ */ new Map();
	for (const f of features) grouped.set(f.section, [...grouped.get(f.section) ?? [], f]);
	return [...grouped.entries()];
}
function AdminGuidelinesPage() {
	const { refresh } = useAdmin();
	const [read, setRead] = d(null);
	const [error, setError] = d(null);
	const last = A(null);
	const [restores, setRestores] = d({});
	h(() => {
		const started = performance.now();
		getAdminGuidelines().then((got) => {
			console.info(`Admin guidelines shown (${Math.round(performance.now() - started)} ms)`);
			last.current = got;
			setRead(got);
		}).catch(async (e) => {
			console.error("Could not read the admin guidelines", e);
			if (e instanceof ServerRefusal && e.status === 401) return refresh();
			setError("The admin guidelines could not be read. Reload the page to try again.");
		});
	}, []);
	const queue = A(Promise.resolve());
	function inTurn(run) {
		const next = queue.current.then(run);
		queue.current = next.catch(() => void 0);
		return next;
	}
	const save = (part, change) => inTurn(() => saveNow(part, change));
	const history = {
		name: "Admin guidelines",
		idPrefix: "admin-guidelines",
		madeBy: {
			shipped: "Empty at first",
			generated: "Drafted by the LLM",
			saved: "Saved"
		},
		load: getAdminGuidelinesHistory,
		compare: compareAdminGuidelinesChange,
		restore: (part, number) => inTurn(async () => {
			try {
				const restored = await restoreAdminGuidelinesChange(part, number);
				last.current = restored;
				return restored;
			} catch (e) {
				if (e instanceof ServerRefusal && e.status === 401) await refresh();
				throw e;
			}
		})
	};
	async function saveNow(part, change) {
		if (!last.current) return null;
		setError(null);
		const started = performance.now();
		const before = editOf(last.current);
		try {
			const saved = await saveAdminGuidelines({
				...before,
				...change,
				guidelines: {
					...before.guidelines,
					...change.guidelines
				}
			});
			last.current = saved;
			console.info(`Admin guidelines saved: ${part} (${Math.round(performance.now() - started)} ms)`);
			setRead(saved);
			return saved;
		} catch (e) {
			console.error(`Could not save the admin guidelines: ${part}`, e);
			if (e instanceof ServerRefusal && e.status === 401) {
				await refresh();
				return null;
			}
			setError(e instanceof ServerRefusal ? e.message : "Could not save. Try again.");
			return null;
		}
	}
	if (!read) return error ? /* @__PURE__ */ u("p", {
		className: "error",
		children: error
	}) : /* @__PURE__ */ u("p", {
		className: "muted busy",
		children: "Reading the admin guidelines…"
	});
	return /* @__PURE__ */ u("div", {
		className: "admin-guidelines",
		children: [
			/* @__PURE__ */ u("p", {
				className: "notice",
				children: "These come first, over every host's: the LLM follows them first, and a host's identity, goals and guidelines only where they don't conflict. Hosts can't see or change them. Empty parts add nothing."
			}),
			error && /* @__PURE__ */ u("p", {
				className: "error",
				role: "alert",
				children: error
			}),
			/* @__PURE__ */ u(HistorySection, {
				source: history,
				onRestored: (restored, part) => {
					setRead(restored);
					setRestores((n) => ({
						...n,
						[part]: (n[part] ?? 0) + 1
					}));
				}
			}),
			/* @__PURE__ */ u(IdentitySection, {
				identity: read.identity,
				save
			}, `identity-${restores.identity ?? 0}`),
			/* @__PURE__ */ u(GoalsSection, {
				goals: read.goals,
				save
			}, `goals-${restores.goals ?? 0}`),
			sections(read.features).map(([name, features]) => /* @__PURE__ */ u("section", {
				className: "panel",
				"aria-labelledby": `admin-guidelines-${name.toLowerCase().replace(/[^a-z]+/g, "-")}`,
				children: [/* @__PURE__ */ u("h2", {
					id: `admin-guidelines-${name.toLowerCase().replace(/[^a-z]+/g, "-")}`,
					children: name
				}), features.map((f) => /* @__PURE__ */ u(FeatureGuidelines, {
					feature: f,
					save
				}, `${f.key}-${restores[f.key] ?? 0}`))]
			}, name))
		]
	});
}
//#endregion
//#region src/laptop-key.ts
var DB = "imageskin-laptop";
var STORE = "keys";
var KEY = "laptop";
function request(r) {
	return new Promise((resolve, reject) => {
		r.onsuccess = () => resolve(r.result);
		r.onerror = () => reject(r.error ?? /* @__PURE__ */ new Error("IndexedDB request failed"));
	});
}
function openDb() {
	const open = indexedDB.open(DB, 1);
	open.onupgradeneeded = () => open.result.createObjectStore(STORE);
	return request(open);
}
var store = {
	async load() {
		const db = await openDb();
		try {
			return await request(db.transaction(STORE).objectStore(STORE).get(KEY));
		} finally {
			db.close();
		}
	},
	async save(pair) {
		const db = await openDb();
		try {
			await request(db.transaction(STORE, "readwrite").objectStore(STORE).put(pair, KEY));
		} finally {
			db.close();
		}
	}
};
var pair = null;
function canProve() {
	return Boolean(globalThis.isSecureContext && globalThis.crypto?.subtle && globalThis.indexedDB);
}
function keyPair() {
	pair ??= (async () => {
		const kept = await store.load();
		if (kept) return kept;
		const made = await crypto.subtle.generateKey({
			name: "ECDSA",
			namedCurve: "P-256"
		}, false, ["sign", "verify"]);
		await store.save(made);
		console.info("Laptop key made");
		return made;
	})();
	pair.catch(() => pair = null);
	return pair;
}
var BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
function base32(bytes) {
	let bits = 0;
	let value = 0;
	let out = "";
	for (const byte of bytes) {
		value = value << 8 | byte;
		bits += 8;
		while (bits >= 5) {
			out += BASE32[value >>> bits - 5 & 31];
			bits -= 5;
		}
	}
	if (bits > 0) out += BASE32[value << 5 - bits & 31];
	return out;
}
function base64(bytes) {
	return btoa(String.fromCharCode(...new Uint8Array(bytes)));
}
async function idFromSpki(spki) {
	return "LT-" + (base32(new Uint8Array(await crypto.subtle.digest("SHA-256", spki))).slice(0, 20).match(/.{4}/g) ?? []).join("-");
}
async function publicSpki() {
	return crypto.subtle.exportKey("spki", (await keyPair()).publicKey);
}
async function laptopId() {
	const id = await idFromSpki(await publicSpki());
	console.info("Laptop ID shown");
	return id;
}
async function prove(challenge) {
	const start = performance.now();
	const { privateKey } = await keyPair();
	const signature = await crypto.subtle.sign({
		name: "ECDSA",
		hash: "SHA-256"
	}, privateKey, new TextEncoder().encode(challenge));
	const proof = {
		public_key: base64(await publicSpki()),
		challenge,
		signature: base64(signature)
	};
	console.info(`Laptop proof sent (${Math.round(performance.now() - start)} ms)`);
	return proof;
}
function laptopEntry(id) {
	return `[[laptop]]\nname = "My laptop"\nid = "${id}"\n`;
}
//#endregion
//#region src/admin.tsx
var GUIDE = "https://github.com/larry94555/ImageSkinForLLM/blob/main/docs/guides/Admin-Password-Guide.pdf";
var CHECK_MS = 6e4;
var AdminContext = X({
	session: null,
	listed: null,
	askListed: () => {},
	ended: null,
	refresh: async () => {},
	signIn: async () => {},
	signOut: async () => {},
	dismiss: () => {}
});
function useAdmin() {
	return x(AdminContext);
}
function minutes(n) {
	return `${n} minute${n === 1 ? "" : "s"}`;
}
function endedMessage(session) {
	if (session.ended === "password changed") return "Signed out as administrator because the administrator password was changed.";
	if (session.ended === "laptop removed") return "Signed out as administrator.";
	return `Signed out as administrator after ${minutes(session.timeout_minutes)} without activity.`;
}
function AdminProvider({ children }) {
	const [session, setSession] = d(null);
	const [ended, setEnded] = d(null);
	const [listed, setListed] = d(null);
	async function refresh() {
		try {
			const read = await getAdminSession();
			setSession(read);
			if (read.ended) {
				console.info(`Admin signed out: ${read.ended}`);
				setEnded(endedMessage(read));
			}
		} catch (e) {
			console.error("Could not read the administrator sign-in", e);
		}
	}
	h(() => {
		refresh();
	}, []);
	const asked = A(false);
	function askListed() {
		if (asked.current) return;
		asked.current = true;
		(async () => {
			const answer = await isLaptopListed(canProve() ? await prove(await getAdminChallenge()) : void 0);
			setListed(answer);
			if (!answer && canProve()) console.info(`This laptop's ID: ${await laptopId()}`);
		})().catch((err) => {
			console.error("Could not ask whether this laptop is listed", err);
			setListed(true);
		});
	}
	const signedIn = session?.signed_in === true;
	h(() => {
		if (!signedIn) return;
		const timer = setInterval(() => void refresh(), CHECK_MS);
		return () => clearInterval(timer);
	}, [signedIn]);
	async function signIn(password) {
		const started = performance.now();
		await signInAsAdmin(password, canProve() ? await prove(await getAdminChallenge()) : void 0);
		console.info(`Admin signed in (${Math.round(performance.now() - started)} ms)`);
		setEnded(null);
		await refresh();
	}
	async function signOut() {
		await signOutAsAdmin();
		console.info("Admin signed out: signed out");
		await refresh();
	}
	const shared = {
		session,
		listed,
		askListed,
		ended,
		refresh,
		signIn,
		signOut,
		dismiss: () => setEnded(null)
	};
	return /* @__PURE__ */ u(AdminContext.Provider, {
		value: shared,
		children
	});
}
function useAdminActivity(active) {
	const { session, refresh } = useAdmin();
	const last = A(0);
	const on = active && session?.signed_in === true;
	h(() => {
		if (!on) return;
		function activity() {
			const now = Date.now();
			if (now - last.current < 6e4) return;
			last.current = now;
			adminActivity().then(async (still) => {
				if (!still) await refresh();
			}).catch((e) => console.error("Could not tell the server of admin activity", e));
		}
		document.addEventListener("click", activity);
		document.addEventListener("keydown", activity);
		return () => {
			document.removeEventListener("click", activity);
			document.removeEventListener("keydown", activity);
		};
	}, [on]);
}
function AdminLink({ current }) {
	const { session } = useAdmin();
	if (!session?.signed_in) return null;
	return /* @__PURE__ */ u("a", {
		href: "#/admin",
		className: current ? "settings-link current" : "settings-link",
		children: "Admin"
	});
}
function AdminEndedNotice() {
	const { ended, dismiss } = useAdmin();
	if (!ended) return null;
	return /* @__PURE__ */ u("p", {
		className: "notice",
		role: "status",
		children: [
			ended,
			" ",
			/* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				onClick: dismiss,
				children: "OK"
			})
		]
	});
}
function LaptopId() {
	const [id, setId] = d(null);
	const [failed, setFailed] = d(false);
	const [copied, setCopied] = d(false);
	const usable = canProve();
	h(() => {
		if (!usable) return;
		laptopId().then(setId, (err) => {
			console.error("Could not make this laptop's key", err);
			setFailed(true);
		});
	}, [usable]);
	async function copy() {
		if (!id) return;
		try {
			await navigator.clipboard.writeText(laptopEntry(id));
			setCopied(true);
		} catch (err) {
			console.error("Could not copy the laptop ID", err);
		}
	}
	let shown;
	if (!usable) shown = /* @__PURE__ */ u("p", {
		className: "muted",
		children: "This laptop's ID can't be shown at this address."
	});
	else if (failed) shown = /* @__PURE__ */ u("p", {
		className: "muted",
		children: "This laptop's ID couldn't be made in this browser."
	});
	else shown = /* @__PURE__ */ u(S, { children: /* @__PURE__ */ u("p", { children: [
		"This laptop's ID: ",
		/* @__PURE__ */ u("code", { children: id ?? "…" }),
		" ",
		/* @__PURE__ */ u("button", {
			type: "button",
			className: "secondary",
			disabled: !id,
			onClick: () => void copy(),
			children: copied ? "Copied" : "Copy"
		})
	] }) });
	return /* @__PURE__ */ u("div", {
		className: "laptop-id",
		children: [/* @__PURE__ */ u("h3", { children: "This laptop" }), shown]
	});
}
function AdminSection() {
	const { session, listed, askListed, signIn, signOut } = useAdmin();
	const [password, setPassword] = d("");
	const [busy, setBusy] = d(false);
	const [error, setError] = d(null);
	const shown = Boolean(session?.signed_in || listed);
	h(() => {
		if (session) askListed();
	}, [session !== null]);
	h(() => {
		if (shown) console.info("Admin sign-in shown");
	}, [shown]);
	async function submit(e) {
		e.preventDefault();
		setBusy(true);
		setError(null);
		try {
			await signIn(password);
			setPassword("");
		} catch (err) {
			console.error("Could not sign in as administrator", err);
			setError(err instanceof ServerRefusal ? err.message : "Could not sign in. Try again in a moment.");
		} finally {
			setBusy(false);
		}
	}
	async function leave() {
		setBusy(true);
		try {
			await signOut();
		} catch (err) {
			console.error("Could not sign out as administrator", err);
			setError("Could not sign out. Try again.");
		} finally {
			setBusy(false);
		}
	}
	let body = /* @__PURE__ */ u("p", {
		className: "muted",
		children: "Checking…"
	});
	if (session?.signed_in) body = /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("p", { children: [
		"Signed in as administrator. You are signed out after ",
		minutes(session.timeout_minutes),
		" ",
		"without activity."
	] }), /* @__PURE__ */ u("p", { children: [
		/* @__PURE__ */ u("a", {
			className: "button",
			href: "#/admin",
			children: "Open the admin view"
		}),
		" ",
		/* @__PURE__ */ u("button", {
			type: "button",
			className: "secondary",
			disabled: busy,
			onClick: () => void leave(),
			children: "Sign out as administrator"
		})
	] })] });
	else if (session && !session.password_set) body = /* @__PURE__ */ u("p", {
		className: "muted",
		children: [
			"Signing in as the administrator is off, as no administrator password is set on this computer. Whoever runs the computer sets it in the file admin.toml, as the",
			" ",
			/* @__PURE__ */ u("a", {
				href: GUIDE,
				target: "_blank",
				rel: "noreferrer",
				children: "admin password guide"
			}),
			" ",
			"says."
		]
	});
	else if (session) body = /* @__PURE__ */ u("form", {
		onSubmit: (e) => void submit(e),
		children: [
			/* @__PURE__ */ u("label", { children: [
				"Administrator password",
				" ",
				/* @__PURE__ */ u("input", {
					type: "password",
					autoComplete: "current-password",
					value: password,
					onInput: (e) => setPassword(e.currentTarget.value)
				})
			] }),
			" ",
			/* @__PURE__ */ u("button", {
				type: "submit",
				disabled: busy || password === "",
				children: "Sign in as administrator"
			})
		]
	});
	if (!shown) {
		if (listed !== false) return null;
		return /* @__PURE__ */ u("section", {
			className: "panel",
			"aria-label": "This laptop",
			children: /* @__PURE__ */ u(LaptopId, {})
		});
	}
	return /* @__PURE__ */ u("section", {
		className: "panel",
		"aria-labelledby": "settings-admin",
		children: [
			/* @__PURE__ */ u("h2", {
				id: "settings-admin",
				children: "Administrator"
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "Running the site as a whole, apart from the host and participant views."
			}),
			error && /* @__PURE__ */ u("p", {
				className: "error",
				children: error
			}),
			body,
			/* @__PURE__ */ u(LaptopId, {})
		]
	});
}
function AdminPage({ section = "resources" }) {
	const { session, listed, askListed } = useAdmin();
	h(() => {
		if (session) askListed();
	}, [session !== null]);
	if (!session?.signed_in) {
		if (!listed) return null;
		return /* @__PURE__ */ u("div", {
			className: "host-page admin-page",
			children: [
				/* @__PURE__ */ u("h1", { children: "Admin" }),
				/* @__PURE__ */ u("p", {
					className: "lead",
					children: "Site-wide administration, separate from the host and participant views."
				}),
				/* @__PURE__ */ u(AdminSection, {})
			]
		});
	}
	const tab = (to, href, label) => /* @__PURE__ */ u("a", {
		href,
		className: section === to ? "current" : void 0,
		"aria-current": section === to ? "page" : void 0,
		children: label
	});
	return /* @__PURE__ */ u("div", {
		className: "host-page admin-page",
		children: [
			/* @__PURE__ */ u("h1", { children: "Admin" }),
			/* @__PURE__ */ u("p", {
				className: "lead",
				children: "Site-wide administration, separate from the host and participant views."
			}),
			/* @__PURE__ */ u("nav", {
				className: "admin-tabs",
				"aria-label": "Admin pages",
				children: [
					tab("resources", "#/admin", "Resources"),
					tab("settings", "#/admin/settings", "Admin settings"),
					tab("guidelines", "#/admin/guidelines", "Admin guidelines")
				]
			}),
			section === "settings" ? /* @__PURE__ */ u(AdminSettingsPage, {}) : section === "guidelines" ? /* @__PURE__ */ u(AdminGuidelinesPage, {}) : /* @__PURE__ */ u(ResourceDashboard, {})
		]
	});
}
//#endregion
//#region src/leave-guard.tsx
var LEAVE_TITLE = "Your change isn't accepted yet";
var LEAVE_PROCEED = "Proceed without the change";
var LEAVE_CANCEL = "Cancel";
var decided = null;
function goWithoutAsking(href) {
	decided = href;
	window.addEventListener("hashchange", () => decided = null, { once: true });
	window.location.hash = href;
}
function useLeaveGuard(pending, unchanged) {
	const { ask, dialog } = useConfirm();
	const now = A({
		pending,
		unchanged
	});
	now.current = {
		pending,
		unchanged
	};
	const allowed = A(null);
	h(() => {
		const confirmLeave = (href) => {
			console.info(`Leaving setup for ${href} with the sample neither accepted nor rejected`);
			ask({
				title: LEAVE_TITLE,
				keepLabel: LEAVE_CANCEL,
				confirmLabel: LEAVE_PROCEED,
				children: /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("p", { children: ["Your change takes effect only once you accept its sample video. If you proceed, nothing changes. ", now.current.unchanged] }), /* @__PURE__ */ u("p", {
					className: "muted",
					children: "Choose Cancel to stay and accept or reject the sample video."
				})] })
			}).then((proceed) => {
				if (!proceed) return;
				allowed.current = href;
				window.location.hash = href;
			});
		};
		const leaving = (from, to) => {
			if (decided === to) {
				decided = null;
				return false;
			}
			return now.current.pending && pageFor(to) !== pageFor(from) && allowed.current !== to;
		};
		const onClick = (e) => {
			if (!(e.target instanceof Element)) return;
			const href = e.target.closest("a[href^='#/']")?.getAttribute("href");
			if (!href || !leaving(window.location.hash, href)) return;
			e.preventDefault();
			e.stopPropagation();
			confirmLeave(href);
		};
		blockLeaving((from, to) => {
			if (!leaving(from, to)) {
				if (allowed.current === to) allowed.current = null;
				return false;
			}
			history.pushState(history.state, "", from);
			confirmLeave(to);
			return true;
		});
		const onUnload = (e) => {
			if (now.current.pending) e.preventDefault();
		};
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
//#endregion
//#region src/setting-guard.tsx
var SettingGuard = X({
	needed: () => false,
	confirm: async () => true
});
function useSettingGuard() {
	return x(SettingGuard);
}
function usePrepareStopGuard(onDiscarded) {
	const stopped = A(false);
	const { ask, dialog } = useConfirm();
	const [failed, setFailed] = d(null);
	async function confirm(title = "Change this setting?") {
		if (!stopped.current) return true;
		setFailed(null);
		if (!await ask({
			title,
			children: /* @__PURE__ */ u("p", { children: "Changing a setting will require restarting the preparation over again." }),
			keepLabel: "Cancel change",
			confirmLabel: "Confirm change"
		})) return false;
		const started = performance.now();
		try {
			await discardPrepare();
			console.info(`Stopped prepare dropped for a setting change (${Math.round(performance.now() - started)} ms)`);
		} catch (e) {
			console.error("Could not drop the stopped prepare; the setting is left as it was", e);
			setFailed(`The setting was not changed: the stopped preparation could not be cleared (${e.message}). Try again.`);
			return false;
		}
		stopped.current = false;
		onDiscarded();
		return true;
	}
	return {
		guard: {
			needed: () => stopped.current,
			confirm
		},
		onStopped: (now) => stopped.current = now,
		dialog: /* @__PURE__ */ u(S, { children: [failed && /* @__PURE__ */ u("p", {
			className: "error",
			role: "alert",
			children: failed
		}), dialog] })
	};
}
//#endregion
//#region src/detail-bar.tsx
function DetailBar() {
	const { settings, change } = x(SettingsContext);
	const [failed, setFailed] = d(false);
	const [picked, setPicked] = d(null);
	const shown = picked ?? settings.detail;
	const latest = A(null);
	const saving = A(Promise.resolve());
	function choose(detail) {
		setFailed(false);
		setPicked(detail);
		latest.current = detail;
		saving.current = saving.current.then(async () => {
			if (latest.current !== detail) return;
			try {
				await change({ detail });
				console.info(`Level of detail set to ${detail}`);
			} catch (e) {
				console.error(`Could not set the level of detail to ${detail}`, e);
				setFailed(true);
			}
			if (latest.current === detail) setPicked(null);
		});
	}
	return /* @__PURE__ */ u("div", {
		className: "detail-bar",
		children: [/* @__PURE__ */ u("label", { children: [/* @__PURE__ */ u("span", { children: "Level of detail" }), /* @__PURE__ */ u("span", {
			className: "detail-poles",
			children: [
				/* @__PURE__ */ u("span", {
					className: "muted",
					children: "High level"
				}),
				/* @__PURE__ */ u("input", {
					type: "range",
					min: 1,
					max: 5,
					step: 1,
					value: shown,
					"aria-valuetext": `${shown} of 5`,
					onChange: (e) => choose(Number(e.currentTarget.value))
				}),
				/* @__PURE__ */ u("span", {
					className: "muted",
					children: "In depth"
				})
			]
		})] }), failed && /* @__PURE__ */ u("p", {
			className: "error",
			children: "The level of detail could not be changed. Try again."
		})]
	});
}
//#endregion
//#region src/exit.tsx
function ExitScreen({ onStartAgain }) {
	h(() => console.info("Exit screen shown"), []);
	return /* @__PURE__ */ u("section", {
		className: "exit-screen",
		children: [
			/* @__PURE__ */ u("h1", { children: "Goodbye" }),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "You have left the chat. Your conversation is kept for when you return."
			}),
			/* @__PURE__ */ u("button", {
				type: "button",
				onClick: () => {
					console.info("Start again");
					onStartAgain();
				},
				children: "Start again"
			})
		]
	});
}
//#endregion
//#region src/face-movement.tsx
var CHOICES = [
	["off", "Off"],
	["slight", "Slight"],
	["normal", "Normal"]
];
function FaceMovementChoice(props) {
	const { settings, change } = x(SettingsContext);
	const [failed, setFailed] = d(false);
	const [picked, setPicked] = d(null);
	const shown = picked ?? settings.face_movement;
	const guard = useSettingGuard();
	async function choose(face_movement) {
		setFailed(false);
		setPicked(face_movement);
		if (!await guard.confirm()) {
			setPicked(null);
			return;
		}
		try {
			await change({ face_movement });
			props.onChanged?.();
		} catch (e) {
			console.error(`Could not change the face movement to ${face_movement}`, e);
			setFailed(true);
		}
		setPicked(null);
	}
	return /* @__PURE__ */ u("fieldset", {
		className: "face-movement",
		children: [
			/* @__PURE__ */ u("legend", { children: "Face movement while speaking" }),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: "How much the cheeks and the face around the mouth move with it. Off moves only the lips and jaw. After changing it, Prepare again to see it."
			}),
			CHOICES.map(([value, label]) => /* @__PURE__ */ u("label", {
				className: "choice",
				children: [
					/* @__PURE__ */ u("input", {
						type: "radio",
						name: "face_movement",
						value,
						checked: shown === value,
						disabled: props.disabled,
						onChange: () => void choose(value)
					}),
					" ",
					/* @__PURE__ */ u("span", { children: label })
				]
			}, value)),
			failed && /* @__PURE__ */ u("p", {
				className: "error",
				children: "The face movement could not be changed. Try again."
			})
		]
	});
}
function speechRecognition() {
	const w = window;
	return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}
function talkProblem(error) {
	if (error === "aborted") return null;
	if (error === "no-speech") return "I didn't hear anything. Hold the button while you speak.";
	if (error === "not-allowed" || error === "service-not-allowed") return "The browser isn't allowed to use the microphone. Allow it in the address bar.";
	if (error === "audio-capture") return "No microphone was found.";
	return "Speech recognition didn't work. Try again, or type your question.";
}
function heard(results) {
	return Array.from(results, (r) => r[0]?.transcript ?? "").join(" ").replace(/\s+/g, " ").trim();
}
function leastSure(results) {
	const known = Array.from(results, (r) => r[0]?.confidence ?? 0).filter((c) => c > 0);
	return known.length ? Math.min(...known) : null;
}
function TalkButton(props) {
	const Maker = speechRecognition();
	const [listening, setListening] = d(false);
	const recognition = A(null);
	const said = A("");
	const sure = A(null);
	const started = A(0);
	const failed = A(false);
	const stopping = A(null);
	const sending = A(false);
	const [tapped, setTapped] = d(false);
	const latched = A(false);
	const editLink = A(null);
	const editing = A(false);
	const [overEditLink, setOverEditLink] = d(false);
	function clearTail() {
		if (stopping.current !== null) window.clearTimeout(stopping.current);
		stopping.current = null;
	}
	h(() => () => {
		clearTail();
		sending.current = false;
		recognition.current?.stop();
	}, []);
	if (!Maker) return null;
	function start() {
		if (props.disabled || recognition.current || !Maker) return;
		const r = new Maker();
		r.lang = navigator.language || "en-US";
		r.continuous = true;
		r.interimResults = true;
		said.current = "";
		sure.current = null;
		failed.current = false;
		sending.current = false;
		editing.current = false;
		latched.current = false;
		started.current = performance.now();
		r.onresult = (e) => {
			said.current = heard(e.results);
			sure.current = leastSure(e.results);
			props.onHearing(said.current);
		};
		r.onerror = (e) => {
			const problem = talkProblem(e.error);
			if (problem) {
				failed.current = true;
				console.error("Push-to-talk failed", e.error);
				props.onProblem(problem);
			}
		};
		r.onend = () => {
			recognition.current = null;
			clearTail();
			latched.current = false;
			setTapped(false);
			const send = sending.current && !failed.current;
			sending.current = false;
			setListening(false);
			const text = said.current;
			const ms = Math.round(performance.now() - started.current);
			const words = text.split(" ").filter(Boolean).length;
			console.info(`Push-to-talk: heard ${words} words in ${ms} ms`);
			if (!send) {
				if (text) console.info("Push-to-talk: ended without sending");
				if (editing.current && text) props.onEdit(text);
				return;
			}
			if (!text) {
				props.onProblem(talkProblem("no-speech"));
				return;
			}
			const confidence = sure.current === null ? "not given" : sure.current.toFixed(2);
			if (sure.current !== null && sure.current < .8) {
				console.info(`Push-to-talk: not sure of the words (confidence ${confidence}), left to check`);
				props.onUnsure(text);
				return;
			}
			console.info(`Push-to-talk: sent (confidence ${confidence})`);
			props.onHeard(text);
		};
		recognition.current = r;
		props.onProblem(null);
		setListening(true);
		console.info("Push-to-talk: listening");
		try {
			r.start();
		} catch (e) {
			console.error("Push-to-talk could not start", e);
			recognition.current = null;
			setListening(false);
			props.onProblem(talkProblem("start"));
		}
	}
	function stop() {
		if (!recognition.current || stopping.current !== null) return;
		sending.current = true;
		stopping.current = window.setTimeout(() => {
			stopping.current = null;
			recognition.current?.stop();
		}, 600);
	}
	function press() {
		if (!recognition.current) {
			start();
			return;
		}
		if (latched.current) {
			latched.current = false;
			setTapped(false);
			stop();
		}
	}
	function edit() {
		if (!recognition.current) return;
		clearTail();
		sending.current = false;
		editing.current = true;
		latched.current = false;
		setTapped(false);
		console.info("Push-to-talk: Edit chosen; left in the box to change");
		recognition.current.stop();
	}
	function overEdit(e) {
		const box = editLink.current?.getBoundingClientRect();
		if (!box || box.width === 0) return false;
		const { clientX: x, clientY: y } = e;
		return x >= box.left && x <= box.right && y >= box.top && y <= box.bottom;
	}
	function release() {
		if (!recognition.current || latched.current || stopping.current !== null) return;
		const ms = Math.round(performance.now() - started.current);
		if (ms < 400) {
			latched.current = true;
			setTapped(true);
			console.info(`Push-to-talk: let go after ${ms} ms; listening until clicked again`);
			return;
		}
		stop();
	}
	return /* @__PURE__ */ u("div", {
		className: "talk-row",
		children: [/* @__PURE__ */ u("button", {
			type: "button",
			className: listening ? "secondary talk listening" : "secondary talk",
			disabled: props.disabled && !listening,
			"aria-pressed": listening,
			onPointerDown: (e) => {
				e.preventDefault();
				e.currentTarget.setPointerCapture?.(e.pointerId);
				press();
			},
			onPointerMove: (e) => setOverEditLink(recognition.current !== null && overEdit(e)),
			onPointerUp: (e) => {
				setOverEditLink(false);
				if (overEdit(e)) edit();
				else release();
			},
			onPointerCancel: stop,
			onKeyDown: (e) => {
				if ((e.key === " " || e.key === "Enter") && !e.repeat) {
					e.preventDefault();
					press();
				}
			},
			onKeyUp: (e) => {
				if (e.key === " " || e.key === "Enter") release();
			},
			children: !listening ? "Hold to talk" : overEditLink ? "Let go to edit" : tapped ? "Click to send or…" : "Let go to send or…"
		}), listening && /* @__PURE__ */ u("button", {
			ref: editLink,
			type: "button",
			className: overEditLink ? "link armed" : "link",
			onClick: edit,
			children: "Edit"
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
		/* @__PURE__ */ u("p", { children: "Only use images you have the right to use. Ideally, use your own picture." }),
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
						"I have the right to use the photos and recording that will be used by the app."
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
var BACK_NOTICE$2 = {
	photos: "You rejected the image. Add new photos and remove the ones you don't want, then Prepare again.",
	sounds: "You rejected the voice. Add new recordings and remove the ones you don't want, then Prepare again.",
	accent: "Choose another accent. The sample video is then made again."
};
var AFTER_CHANGE = " Accept the new sample video at the end of setup to go back to the chat.";
var CHANGE_NOTICE = {
	photos: "Add a new photo, or choose another one, and remove the ones you don't want. Then Prepare again." + AFTER_CHANGE,
	sounds: "Add new recordings and remove the ones you don't want. Then Prepare again." + AFTER_CHANGE,
	accent: "Choose another accent. The sample video is then made again." + AFTER_CHANGE
};
function SetupPage({ change }) {
	const ownVoice = useCustomUse().voice;
	const [changes, setChanges] = d(0);
	const changed = () => setChanges((n) => n + 1);
	const [preparing, setPreparing] = d(false);
	const [back, setBack] = d(null);
	function goBack(to, notice = BACK_NOTICE$2[to]) {
		setBack({
			to,
			notice
		});
		window.setTimeout(() => document.getElementById(to)?.scrollIntoView?.({ behavior: "smooth" }));
	}
	h(() => {
		if (!change) return;
		console.info(`Setup opened to change the ${change}`);
		goBack(change, CHANGE_NOTICE[change]);
	}, [change]);
	const [avatarVoice, setAvatarVoice] = d(false);
	const [undoFailed, setUndoFailed] = d(null);
	const [pending, setPending] = d(false);
	const leaveDialog = useLeaveGuard(pending, "The chat keeps the person and voice it has now.");
	const stopGuard = usePrepareStopGuard(changed);
	h(() => {
		getReview().then((r) => setAvatarVoice(r.own_voice === true)).catch((e) => console.error("Could not get the review", e));
	}, []);
	async function ownPhotoInstead() {
		const started = performance.now();
		setUndoFailed(null);
		try {
			await useAvatarReadyVoice();
			console.info(`Setting up your own photo instead of the avatar's voice (${Math.round(performance.now() - started)} ms)`);
			setAvatarVoice(false);
			changed();
		} catch (e) {
			console.error("Could not set up your own photo instead", e);
			setUndoFailed(e.message);
		}
	}
	const notice = (to) => back?.to === to ? back.notice : null;
	if (avatarVoice) return /* @__PURE__ */ u("div", {
		className: "host-page",
		children: [
			/* @__PURE__ */ u("h1", { children: "Setup" }),
			/* @__PURE__ */ u("p", {
				className: "notice",
				children: [
					"The ready-made avatar is set to speak in your voice, so Prepare makes the avatar's video. ",
					/* @__PURE__ */ u("a", {
						href: "#/avatar-voice",
						children: "Go to your voice for the avatar"
					}),
					", or set up your own photo instead: the avatar then speaks in its ready-made voice until you accept your own sample video."
				]
			}),
			/* @__PURE__ */ u("button", {
				type: "button",
				onClick: () => void ownPhotoInstead(),
				children: "Set up my own photo instead"
			}),
			undoFailed && /* @__PURE__ */ u("p", {
				className: "error",
				children: undoFailed
			})
		]
	});
	return /* @__PURE__ */ u(SettingGuard.Provider, {
		value: stopGuard.guard,
		children: /* @__PURE__ */ u("div", {
			className: "host-page",
			children: [
				/* @__PURE__ */ u("h1", { children: "Setup" }),
				/* @__PURE__ */ u("p", {
					className: "lead",
					children: ownVoice ? "Make the talking person in four steps: add photos, add voice recordings, choose an accent, then prepare a sample video and check it. Without recordings, the person speaks in a ready-made voice." : "Make the talking person in two steps: add photos, then prepare a sample video and check it. Using your own voice is turned off for this site, so the person speaks in a ready-made voice."
				}),
				/* @__PURE__ */ u("p", {
					className: "avatar-instead",
					children: [
						"Rather not use your own photo and voice?",
						" ",
						/* @__PURE__ */ u("a", {
							href: "#/start-now",
							onClick: () => console.info("Choosing a ready-made avatar from Setup"),
							children: "Use a ready-made avatar instead"
						}),
						". Your photos and recordings are kept."
					]
				}),
				ownVoice && /* @__PURE__ */ u("p", {
					className: "notice",
					children: [/* @__PURE__ */ u("a", {
						href: "#/setup/wizard",
						children: "Set up your own photo and voice one step at a time"
					}), ", with help on each step."]
				}),
				/* @__PURE__ */ u(UploadSection, {
					kind: "photos",
					step: 1,
					title: "Photos",
					button: "Add photos",
					hint: "Add the five photos from the recording guide (JPG, PNG or HEIC). At least one is needed; the app will pick the best.",
					accept: "image/jpeg,image/png,image/heic,.heic",
					of: ownVoice ? 4 : 2,
					notice: notice("photos"),
					onChange: changed
				}),
				ownVoice && /* @__PURE__ */ u(UploadSection, {
					kind: "sounds",
					step: 2,
					title: "Voice recordings",
					button: "Add recordings",
					hint: "Add the voice recordings from the recording guide (WAV, M4A or MP3, up to 10 minutes each).",
					accept: "audio/*,.m4a,.wav,.mp3",
					notice: notice("sounds"),
					onChange: changed
				}),
				/* @__PURE__ */ u(ReadyVoiceChoice, {
					changes,
					onChange: changed,
					ownVoice
				}),
				ownVoice && /* @__PURE__ */ u(AccentSection, {
					onChange: changed,
					preparing,
					notice: notice("accent")
				}),
				/* @__PURE__ */ u(PrepareSection, {
					step: ownVoice ? void 0 : {
						n: 2,
						of: 2
					},
					changes,
					onRunning: setPreparing,
					onBack: goBack,
					onPending: setPending,
					onStopped: stopGuard.onStopped
				}),
				leaveDialog,
				stopGuard.dialog
			]
		})
	});
}
function ReadyVoiceChoice(props) {
	const [ready, setReady] = d(null);
	const guard = useSettingGuard();
	const [failed, setFailed] = d(null);
	h(() => {
		getReadyVoice().then((r) => {
			setReady(r);
			console.info(`Ready-made voice: ${r.voice}, in use: ${r.in_use}`);
		}).catch((e) => console.error("Could not read the ready-made voice", e));
	}, [props.changes]);
	if (ready === null || !Array.isArray(ready.voices)) return null;
	async function choose(voice) {
		if (!await guard.confirm()) {
			setReady((r) => r && { ...r });
			return;
		}
		const started = performance.now();
		setFailed(null);
		try {
			setReady(await chooseReadyVoice(voice));
			console.info(`Ready-made voice chosen: ${voice} (${Math.round(performance.now() - started)} ms)`);
			props.onChange();
		} catch (e) {
			console.error("Could not choose the ready-made voice", e);
			setFailed(e.message);
		}
	}
	return /* @__PURE__ */ u("section", {
		className: "panel ready-voice",
		"aria-labelledby": "ready-voice",
		children: [
			/* @__PURE__ */ u("h3", {
				id: "ready-voice",
				children: props.ownVoice ? "No recordings?" : "The voice"
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: props.ownVoice ? "Recordings are optional. Until one passes the checks, or if they are all removed, the person speaks in a ready-made voice instead of their own." : "The person speaks in the ready-made voice chosen here."
			}),
			/* @__PURE__ */ u("label", { children: [
				"Ready-made voice",
				" ",
				/* @__PURE__ */ u("select", {
					value: ready.voice,
					onChange: (e) => void choose(e.currentTarget.value),
					children: ready.voices.map(({ voice, label }) => /* @__PURE__ */ u("option", {
						value: voice,
						children: label
					}, voice))
				})
			] }),
			props.ownVoice && /* @__PURE__ */ u("p", {
				className: ready.in_use ? "notice" : "muted",
				children: ready.in_use ? "In use now: no recording has passed the checks." : "Not in use: the voice is made from your recordings."
			}),
			failed && /* @__PURE__ */ u("p", {
				className: "error",
				children: failed
			})
		]
	});
}
function StepOf({ n, of = 4 }) {
	return /* @__PURE__ */ u("p", {
		className: "step-of",
		children: [
			"Step ",
			n,
			" of ",
			of
		]
	});
}
function UploadSection(props) {
	const { kind } = props;
	const [items, setItems] = d(null);
	const [loadFailed, setLoadFailed] = d(false);
	const [sending, setSending] = d(null);
	const { ask, dialog } = useConfirm();
	const guard = useSettingGuard();
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
		if (!await guard.confirm(`Use ${item.name} instead?`)) return;
		const sent = ++choiceRequests.current;
		props.onChanging?.(true);
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
		props.onChanging?.(false);
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
				if (e instanceof ServerRefusal && e.status === 503) break;
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
		if (files.length && !await guard.confirm(`Add ${files.length === 1 ? files[0].name : `${files.length} files`}?`)) return;
		if (files.length) props.onChanging?.(true);
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
		if (files.length) props.onChanging?.(false);
	}
	async function remove(item) {
		const title = `Remove ${item.name}?`;
		if (!(guard.needed() ? await guard.confirm(title) : await ask({
			title,
			keepLabel: "No, keep it",
			confirmLabel: "Yes, remove it"
		}))) return;
		props.onChanging?.(true);
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
		props.onChanging?.(false);
	}
	const ready = sending === null && (items !== null || loadFailed);
	const loading = items === null && !loadFailed;
	return /* @__PURE__ */ u("section", {
		id: kind,
		className: "panel",
		children: [
			props.step !== null && /* @__PURE__ */ u(StepOf, {
				n: props.step,
				of: props.of
			}),
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
							children: [item.name, item.seconds !== null && ` (${minutes$1(item.seconds)})`]
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
			kind === "sounds" && /* @__PURE__ */ u(VoiceSampleView, { changes: soundChanges }),
			dialog
		]
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
					minutes$1(sample.speech),
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
	const guard = useSettingGuard();
	h(() => {
		getAccent().then(setChoice).catch((e) => {
			console.error("Could not get the accent", e);
			setFailed("Could not load the accent. Reload the page to try again.");
		});
	}, []);
	async function choose(accent) {
		setSaving(accent);
		if (!await guard.confirm()) {
			setSaving(null);
			return;
		}
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
			props.numbered !== false && /* @__PURE__ */ u(StepOf, { n: 3 }),
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
	const { changes, onRunning, wizard } = props;
	const [status, setStatus] = d(null);
	const [loadFailed, setLoadFailed] = d(false);
	const [starting, setStarting] = d(false);
	const [refused, setRefused] = d(null);
	const { choose, dialog } = useConfirm();
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
	async function cancel() {
		const left = status?.left_s != null ? ` About ${countdown(status.left_s)} is left.` : "";
		const answer = await choose({
			title: "Stop preparing the video?",
			children: /* @__PURE__ */ u("p", { children: [
				"Preparing is ",
				status?.percent ?? 0,
				"% done.",
				left,
				" You can stop now, or once the part it is working on is finished (usually within 10 seconds). Either way, Resume Preparation carries on from where it stopped."
			] }),
			keepLabel: "Keep preparing",
			otherLabel: "Stop after this part",
			confirmLabel: "Stop now"
		});
		if (answer === "cancel") return;
		const request = ++requests.current;
		setRefused(null);
		try {
			const stopping = await cancelPrepare(answer === "confirm");
			if (request === requests.current) setStatus(stopping);
		} catch (e) {
			console.error("Could not stop preparing", e);
			setRefused(e.message);
		}
	}
	h(() => {
		read();
	}, [changes]);
	const stopped = status?.state === "running" && status.stopped === true;
	const running = status?.state === "running" && !stopped;
	const cancelling = running && status.cancelling === true;
	const slow = running && !cancelling && status.steps?.find((s) => s.done < s.total)?.slow === true;
	const cancelled = status?.state === "cancelled";
	h(() => onRunning(running), [running]);
	const done = status?.state === "done";
	h(() => wizard?.onDone(done), [done]);
	_(() => props.onStopped?.(cancelled), [cancelled]);
	h(() => {
		if (!running) return;
		const timer = window.setInterval(() => void read(), PREPARE_POLL_MS);
		return () => window.clearInterval(timer);
	}, [running]);
	return /* @__PURE__ */ u("section", {
		className: "prepare panel",
		children: [
			!wizard && /* @__PURE__ */ u(StepOf, {
				n: props.step?.n ?? 4,
				of: props.step?.of
			}),
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
			/* @__PURE__ */ u(FaceMovementChoice, {
				onChanged: () => void read(),
				disabled: running
			}),
			status !== null && !running && /* @__PURE__ */ u("button", {
				type: "button",
				className: starting ? "busy" : void 0,
				onClick: start,
				disabled: starting || status.state === "done",
				children: starting ? "Starting…" : stopped ? "Try again" : {
					idle: "Prepare Video",
					running: "Preparing…",
					done: "Prepare Video",
					failed: "Try again",
					cancelled: "Resume Preparation"
				}[status.state]
			}),
			refused && /* @__PURE__ */ u("p", {
				className: "error",
				children: refused
			}),
			stopped && /* @__PURE__ */ u("p", {
				className: "error",
				children: "Preparing stopped: the app is no longer working on it. Click Try again to carry on where it left off."
			}),
			running && !cancelling && /* @__PURE__ */ u("p", {
				className: "busy",
				children: [
					"Preparing… ",
					status.percent,
					"% done",
					status.left_s != null && ` · about ${countdown(status.left_s)} left`
				]
			}),
			running && /* @__PURE__ */ u("button", {
				type: "button",
				className: cancelling ? "secondary busy" : "secondary",
				onClick: () => void cancel(),
				disabled: cancelling,
				children: cancelling ? "Stopping…" : "Cancel"
			}),
			cancelling && !status.stopping_late && /* @__PURE__ */ u("p", {
				className: "muted",
				children: "Stopping, usually within 10 seconds…"
			}),
			cancelling && status.stopping_late && /* @__PURE__ */ u("p", {
				className: "muted",
				children: "Still stopping: the part it is on, such as loading a library, can't be cut short safely. It stops as soon as that part is done."
			}),
			cancelled && /* @__PURE__ */ u("p", {
				className: "muted",
				children: [
					"Preparing stopped at ",
					status.percent,
					"%. Click Resume Preparation to carry on from where it stopped. ",
					"Changing a setting will require restarting the preparation over again."
				]
			}),
			slow && /* @__PURE__ */ u("p", {
				className: "muted",
				children: "This is taking longer than usual. It's still working."
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
			status?.state === "done" && wizard && /* @__PURE__ */ u("p", {
				className: "done",
				children: "Done. Click Next to watch the sample video."
			}),
			status?.state === "done" && !wizard && /* @__PURE__ */ u("div", {
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
						onBack: props.onBack,
						avatarVoice: props.avatarVoice,
						onPending: props.onPending
					})
				]
			}),
			status?.state === "failed" && (status.failure ? /* @__PURE__ */ u(FailureReport, {
				failure: status.failure,
				at: status.finished_at
			}) : /* @__PURE__ */ u("p", {
				className: "error",
				children: status.error
			})),
			dialog
		]
	});
}
function FailureReport(props) {
	const { failure } = props;
	const [copied, setCopied] = d();
	const text = [
		`Reference: ${failure.reference}`,
		`Step: ${failure.step ?? "Before the first step"}`,
		`Reason: ${failure.message}`,
		`Time: ${props.at ?? "unknown"}`,
		`App version: ${failure.version}`,
		`Browser: ${navigator.userAgent}`,
		`Error: ${failure.details}`
	].join("\n");
	async function copy() {
		try {
			await navigator.clipboard.writeText(text);
			console.info(`Prepare failure copied for support (${failure.reference})`);
			setCopied({ byHand: null });
		} catch (e) {
			console.error("Could not copy the failure's details", e);
			setCopied({ byHand: text });
		}
	}
	return /* @__PURE__ */ u("div", {
		className: "failure",
		role: "alert",
		children: [
			/* @__PURE__ */ u("p", {
				className: "error",
				children: [failure.step ? `“${failure.step}” failed. ` : "Preparing failed. ", failure.message]
			}),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: [
					failure.retry ? "Try again may help. If it keeps failing, please give support the reference " : "Please give support the reference ",
					/* @__PURE__ */ u("strong", { children: failure.reference }),
					"."
				]
			}),
			/* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				onClick: copy,
				children: "Copy details for support"
			}),
			copied && copied.byHand === null && /* @__PURE__ */ u("span", {
				className: "done",
				children: " Copied."
			}),
			copied?.byHand && /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("p", {
				className: "error",
				children: "The browser didn't allow copying. Select the text below and copy it."
			}), /* @__PURE__ */ u("textarea", {
				readOnly: true,
				value: copied.byHand,
				rows: 7,
				"aria-label": "Details for support"
			})] }),
			/* @__PURE__ */ u("details", { children: [/* @__PURE__ */ u("summary", { children: "Details" }), /* @__PURE__ */ u("pre", { children: failure.details })] })
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
	const [rejected, setRejected] = d(null);
	const [saving, setSaving] = d(null);
	const [failed, setFailed] = d(null);
	h(() => {
		getReview().then(setCurrent).catch((e) => console.error("Could not get the review", e));
	}, [props.sample]);
	async function defaultVoice() {
		const started = performance.now();
		setSaving("default-voice");
		setFailed(null);
		try {
			setCurrent(await useAvatarReadyVoice());
			console.info(`Avatar's default voice used again from the review (${Math.round(performance.now() - started)} ms)`);
			goWithoutAsking("#/chat");
		} catch (e) {
			console.error("Could not use the avatar's default voice again", e);
			setFailed(`Could not return to the default voice: ${e.message}`);
		}
		setSaving(null);
	}
	async function decide(decision, back) {
		setSaving(decision);
		setFailed(null);
		try {
			setCurrent(await review(decision));
			if (back) setRejected(props.sample);
			if (back) props.onBack(back);
			else goWithoutAsking("#/chat");
		} catch (e) {
			console.error(`Could not save the review (${decision})`, e);
			setFailed(`Could not save your choice: ${e.message}`);
		}
		setSaving(null);
	}
	const avatar = current?.default_person === true;
	const avatarVoice = props.avatarVoice === true || avatar && current?.own_voice === true;
	const accepted = avatarVoice ? current?.voice_accepted === true : avatar ? current?.own_sample_accepted === true : current?.accepted;
	const pending = current !== null && !accepted && rejected !== props.sample;
	const { onPending } = props;
	h(() => onPending?.(pending), [pending]);
	h(() => () => onPending?.(false), []);
	const rejects = avatarVoice ? REJECTS.filter((r) => r.back !== "photos") : REJECTS;
	async function useIt() {
		setSaving("accept");
		setFailed(null);
		try {
			await switchToOwn(true, "Setup");
		} catch (e) {
			console.error("Could not switch to your own photo and voice", e);
			setFailed(`Could not switch: ${e.message}`);
		}
		setSaving(null);
	}
	return /* @__PURE__ */ u("div", {
		className: "review",
		children: [
			/* @__PURE__ */ u("h3", { children: "Is this right?" }),
			accepted && avatar && !avatarVoice ? /* @__PURE__ */ u("p", {
				className: "done",
				children: [
					"You accepted this sample, but the chat uses a ready-made avatar.",
					" ",
					/* @__PURE__ */ u("button", {
						type: "button",
						className: "link",
						disabled: saving !== null,
						onClick: () => void useIt(),
						children: "Use your own photo and voice in the chat"
					})
				]
			}) : accepted ? /* @__PURE__ */ u("p", {
				className: "done",
				children: ["You accepted this sample. ", /* @__PURE__ */ u("a", {
					href: "#/chat",
					children: "Go to the chat"
				})]
			}) : /* @__PURE__ */ u("p", {
				className: "muted",
				children: avatarVoice ? "Accept it to have the avatar speak in your voice, go back and change what is wrong, or return to the avatar's default voice." : "Accept it to unlock the chat, or go back and change what is wrong."
			}),
			/* @__PURE__ */ u("div", {
				className: "choices",
				children: [
					!accepted && /* @__PURE__ */ u("button", {
						type: "button",
						className: saving === "accept" ? "busy" : void 0,
						disabled: saving !== null,
						onClick: () => void decide("accept"),
						children: "Accept"
					}),
					rejects.map(({ decision, label, back }) => /* @__PURE__ */ u("button", {
						type: "button",
						className: saving === decision ? "secondary busy" : "secondary",
						disabled: saving !== null,
						onClick: () => void decide(decision, back),
						children: label
					}, decision)),
					avatarVoice && /* @__PURE__ */ u("button", {
						type: "button",
						className: saving === "default-voice" ? "secondary busy" : "secondary",
						disabled: saving !== null,
						onClick: () => void defaultVoice(),
						children: "Return to default voice for avatar"
					})
				]
			}),
			failed && /* @__PURE__ */ u("p", {
				className: "error",
				children: failed
			})
		]
	});
}
function ChatPage() {
	const participant = useSettings().view === "participant";
	const [accepted, setAccepted] = d(null);
	const [readyMade, setReadyMade] = d(false);
	h(() => {
		getReview().then((r) => {
			if (r.own_turned_off && !participant) {
				console.info("The chat needs a ready-made avatar: going to Start now");
				window.location.replace("#/start-now");
				return;
			}
			setAccepted(r.accepted);
			setReadyMade(r.default_person === true);
		}).catch((e) => {
			console.error("Could not get the review", e);
			setAccepted(false);
		});
	}, []);
	const [exited, setExited] = d(false);
	const [returned, setReturned] = d(false);
	const asked = A(null);
	if (accepted === null) return /* @__PURE__ */ u("p", {
		className: "muted busy",
		children: "Loading…"
	});
	if (exited) return /* @__PURE__ */ u(ExitScreen, { onStartAgain: () => {
		setExited(false);
		setReturned(true);
	} });
	if (!accepted) {
		if (participant) return /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("h1", { children: "Chat" }), /* @__PURE__ */ u("p", { children: "The chat isn't ready yet. Ask your host to finish setting it up." })] });
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
		children: [
			/* @__PURE__ */ u("h1", {
				className: "sr-only",
				children: "Chat"
			}),
			!participant && /* @__PURE__ */ u(AvatarLinks, { readyMade }),
			/* @__PURE__ */ u(Chat, {
				welcome: returned,
				after: asked.current,
				onExit: (pending) => {
					asked.current = pending;
					setExited(true);
				}
			})
		]
	});
}
function AvatarLinks({ readyMade }) {
	const ownPhoto = useCustomUse().image;
	const links = readyMade ? [[
		"#/start-now",
		"Choose another avatar",
		"another ready-made avatar"
	], [
		OWN_CONSENT,
		"Use your own photo and voice",
		"their own photo and voice"
	]] : [[
		"#/start-now",
		"Use a ready-made avatar",
		"a ready-made avatar"
	], [
		"#/setup/photos",
		"Change your photo",
		"their own photo"
	]];
	if (!ownPhoto) links.pop();
	return /* @__PURE__ */ u("p", {
		className: "avatar-links",
		children: [/* @__PURE__ */ u("span", {
			className: "muted",
			children: "Avatar Choice:"
		}), links.map(([href, label, what]) => /* @__PURE__ */ u("a", {
			href,
			onClick: () => console.info(`Choosing ${what} from the chat`),
			children: label
		}, href))]
	});
}
var CHECK_HEARD = "I am not clear on what you said. Can you edit your question and resend?";
var CANT_ANSWER = "Sorry, I couldn't answer that just now. Please try again in a moment.";
var LINE_TEXT = {
	goodbye: "Goodbye",
	"welcome-back": "Welcome back"
};
var LINE_TIMEOUT_MS = 1e4;
function newReplyId() {
	return Array.from(crypto.getRandomValues(/* @__PURE__ */ new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}
function sleep(ms) {
	return new Promise((resolve) => setTimeout(resolve, ms));
}
var SOUND_KEY = "imageskin.sound";
function loadLesson() {
	try {
		const saved = JSON.parse(localStorage.getItem("imageskin.lesson") ?? "null");
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
function loadQuiz() {
	try {
		const saved = JSON.parse(localStorage.getItem("imageskin.quiz") ?? "null");
		if (typeof saved?.topic !== "string" || typeof saved.question !== "string" || !Number.isInteger(saved.number) || !Number.isInteger(saved.part)) return null;
		const strings = (v) => Array.isArray(v) ? v.filter((s) => typeof s === "string") : [];
		const count = (v) => Number.isInteger(v) ? v : 0;
		return {
			topic: saved.topic,
			number: saved.number,
			question: saved.question,
			part: saved.part,
			asked: strings(saved.asked),
			right: count(saved.right),
			partly: count(saved.partly),
			review: strings(saved.review),
			source: typeof saved.source === "string" ? saved.source : "",
			questions: Number.isInteger(saved.questions) ? saved.questions : void 0
		};
	} catch {
		return null;
	}
}
function loadAssessment() {
	try {
		const saved = JSON.parse(localStorage.getItem("imageskin.assessment") ?? "null");
		return typeof saved?.topic === "string" && typeof saved.question === "string" && typeof saved.source === "string" && [
			saved.total,
			saved.number,
			saved.level,
			saved.part
		].every(Number.isInteger) && Array.isArray(saved.answers) ? saved : null;
	} catch {
		return null;
	}
}
function saveAssessment(assessment) {
	try {
		if (assessment) localStorage.setItem(ASSESSMENT_KEY, JSON.stringify(assessment));
		else localStorage.removeItem(ASSESSMENT_KEY);
	} catch (e) {
		console.error("Could not keep the assessment", e);
	}
}
function saveQuiz(quiz) {
	try {
		if (quiz) localStorage.setItem(QUIZ_KEY, JSON.stringify(quiz));
		else localStorage.removeItem(QUIZ_KEY);
	} catch (e) {
		console.error("Could not keep the quiz", e);
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
var READ_AHEAD_WORDS = 3;
var READY_CHECK_MS = 1e3;
function preparingChat(leftS) {
	if (leftS === null) return "Preparing chat…";
	return `Preparing chat… ${leftS} ${leftS === 1 ? "second" : "seconds"} remaining`;
}
function Chat(props) {
	const metrics = useSettings().show_metrics;
	const { teach_me: teachMe, quiz_me: quizMe, assessment: assessOn, debug } = useSettings();
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
	const promptBox = A(null);
	const [notClear, setNotClear] = d(false);
	const unsure = A(null);
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
	const [quiz, setQuiz] = d(loadQuiz);
	const [choices, setChoices] = d([]);
	const [assessment, setAssessment] = d(loadAssessment);
	const assessing = assessOn && assessment !== null;
	const quizGoing = quizMe && quiz !== null || assessing;
	h(() => {
		setChoices([]);
	}, [
		teachMe,
		quizMe,
		assessOn
	]);
	const [saying, setSaying] = d(props.welcome ? "welcome-back" : null);
	const line = A(null);
	const [ready, setReady] = d(null);
	const [leftS, setLeftS] = d(null);
	const gettingReady = ready === false;
	h(() => {
		let timer;
		let waitedFrom = null;
		const check = () => {
			getChatReady().then(({ ready: now, leftS: left, warming }) => {
				if (gone.current) return;
				setReady(now);
				setLeftS(left);
				if (!now || warming) {
					if (waitedFrom === null) {
						waitedFrom = performance.now();
						console.info(now ? "Chat open while the voice and face are got ready" : "Chat waits while the voice and face are got ready");
					}
					timer = setTimeout(check, READY_CHECK_MS);
				} else if (waitedFrom !== null) console.info(`Voice and face ready for the chat (${Math.round(performance.now() - waitedFrom)} ms)`);
			}, (e) => {
				console.error("Could not ask whether the chat is ready", e);
				if (!gone.current) setReady(true);
			});
		};
		check();
		return () => clearTimeout(timer);
	}, []);
	const busy = sending || speaking || saying !== null || ready !== true;
	const readAheadOf = A("");
	h(() => {
		const text = prompt.trim();
		if (busy) readAheadOf.current = "";
		if (busy || quizGoing || text === readAheadOf.current) return;
		if (text.split(/\s+/).length < READ_AHEAD_WORDS) return;
		const timer = setTimeout(() => {
			readAheadOf.current = text;
			readAhead(text).then((read) => console.debug(`Question read ahead: ${read}`), (e) => console.debug("Could not read the question ahead", e));
		}, 600);
		return () => clearTimeout(timer);
	}, [
		prompt,
		busy,
		quizGoing
	]);
	const inFlight = A(null);
	const clipTotal = A(0);
	const allMade = A(false);
	const clipsEnded = A(0);
	h(() => {
		if (props.welcome) say("welcome-back");
		return () => {
			gone.current = true;
			clearTimeout(line.current?.timer);
		};
	}, []);
	h(() => {
		getChatPhoto().then(({ url, width, height, idle }) => {
			const ratio = width && height ? width / height : null;
			setPhoto({
				url: url ?? null,
				ratio,
				idle: idle ?? void 0
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
		if (props.after) console.info("Waiting for the prompt asked before Exit");
		(props.after ? props.after.catch(() => {}) : Promise.resolve()).then(() => getChat()).then(setTurns).catch((e) => {
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
	async function say(name) {
		line.current = {
			name,
			at: performance.now()
		};
		setSaying(name);
		setClips([]);
		setTimes([]);
		setWhole(false);
		console.info(`Saying ${LINE_TEXT[name]}`);
		let url = null;
		try {
			url = await lineUrl(name);
		} catch (e) {
			console.error(`Could not find the ${LINE_TEXT[name]} video`, e);
		}
		if (gone.current || line.current?.name !== name) return;
		if (url === null) {
			console.warn(`No ${LINE_TEXT[name]} video, so it isn't said`);
			said();
			return;
		}
		setHalted(false);
		setClips([url]);
		line.current.timer = setTimeout(() => {
			console.warn(`${LINE_TEXT[name]} didn't finish playing in time, so the chat went on`);
			said();
		}, LINE_TIMEOUT_MS);
	}
	function said() {
		const done = line.current;
		if (done === null) return;
		clearTimeout(done.timer);
		line.current = null;
		console.info(`Said ${LINE_TEXT[done.name]} (${Math.round(performance.now() - done.at)} ms)`);
		if (done.name === "goodbye") {
			props.onExit?.(inFlight.current);
			return;
		}
		setSaying(null);
		setClips([]);
	}
	function exit() {
		console.info("Exit");
		if (stoppable) stop();
		say("goodbye");
	}
	function started(clip, at) {
		setWaiting(false);
		setTimes((t) => t.map((c, i) => i === clip && c.started === null ? {
			...c,
			started: at
		} : c));
	}
	function ended(clip, at) {
		if (line.current) {
			said();
			return;
		}
		clipsEnded.current = Math.max(clipsEnded.current, clip + 1);
		if (allMade.current && clipsEnded.current >= clipTotal.current) setWaiting(false);
		setTimes((t) => t.map((c, i) => i === clip && c.ended === null ? {
			...c,
			ended: at
		} : c));
	}
	async function send(asked, spoken = false) {
		const text = (asked ?? prompt).trim();
		if (!text || busy) return;
		spoken ||= asked === void 0 && text === unsure.current;
		unsure.current = null;
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
		setNotClear(false);
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
			const asking = sendPrompt(text, replyId, teachMe ? lesson : null, quizMe ? quiz : null, assessOn ? assessment : null, spoken);
			inFlight.current = asking;
			reply = await asking;
			repliedAt = performance.now();
			if (teachMe && reply.lesson !== void 0) {
				const next = reply.lesson;
				setLesson(next);
				saveLesson(next);
				if (next) console.info(`Lesson: ${next.topic}, part ${next.part + 1}`);
			}
			if (quizMe && reply.quiz !== void 0) {
				const next = reply.quiz;
				setQuiz(next);
				saveQuiz(next);
				if (next) console.info(`Quiz: ${next.topic}, question ${next.number}`);
			}
			if (assessOn && reply.assessment !== void 0) {
				const next = reply.assessment;
				setAssessment(next);
				saveAssessment(next);
				if (next) console.info(`Assessment: question ${next.number} of ${next.total}`);
			}
			setChoices(reply.choices ?? []);
			const { role, content } = reply;
			const meant = reply.prompt;
			if (meant && meant !== text) console.info(`Push-to-talk: "${text}" taken as "${meant}"`);
			setTurns((t) => [...(t ?? []).map((turn, i, all) => meant && i === all.length - 1 ? {
				...turn,
				content: meant
			} : turn), {
				role,
				content
			}]);
		} catch (e) {
			const halt = e instanceof ServerRefusal && e.status === 409 && stopped.current === replyId;
			if (halt) console.info("Prompt stopped while it was answered");
			else console.error("Could not get a reply", e);
			setTurns((t) => (t ?? []).slice(0, -1));
			setPrompt((typed) => halt && typed ? typed : text);
			if (!halt) setFailed(e instanceof ServerRefusal && e.status === 400 ? e.message : CANT_ANSWER);
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
			inFlight.current = null;
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
	async function repeat() {
		if (busy) return;
		const replyId = newReplyId();
		replying.current = replyId;
		const stopping = new Promise((resolve) => {
			wakeOnStop.current = () => resolve("stopped");
		});
		const at = (turns ?? []).length - 1;
		console.info("Repeating the latest reply");
		setHalted(false);
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
		try {
			if (await Promise.race([repeatReply(replyId), stopping]) === "stopped") return;
			const count = await Promise.race([followClips(replyId, () => true), stopping]);
			if (gone.current || count === "stopped") return;
			allMade.current = true;
			if (clipsEnded.current >= count) setWaiting(false);
		} catch (e) {
			console.error("Could not repeat the reply", e);
			setUnspoken({ turn: at });
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
		idleUrl: photo === void 0 ? null : photo.idle,
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
	const status = gettingReady ? preparingChat(leftS) : sending ? halted ? "Stopping…" : "Thinking…" : waiting ? "Getting ready to say it…" : null;
	return /* @__PURE__ */ u("div", {
		className: "chat",
		children: [/* @__PURE__ */ u("div", {
			className: "person",
			children: [
				stage,
				/* @__PURE__ */ u(SoundControls, {
					sound,
					onChange: changeSound,
					onStop: stoppable ? stop : void 0,
					onExit: exit,
					saying: saying !== null
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
				turns.length === 0 && !notClear && /* @__PURE__ */ u("p", {
					className: "muted hint",
					children: "Ask a question to start the conversation."
				}),
				/* @__PURE__ */ u(TurnList, {
					turns,
					from: latestExchange(turns),
					unspoken,
					notice: notClear ? CHECK_HEARD : void 0,
					hideReplies: true
				}),
				turns[turns.length - 1]?.role === "assistant" && !notClear && /* @__PURE__ */ u(ReplyActions, {
					disabled: busy,
					onRepeat: () => void repeat(),
					onSimpler: quizGoing ? void 0 : () => void send(SAY_IT_SIMPLER)
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
							ref: promptBox,
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
						children: [
							/* @__PURE__ */ u("button", {
								type: "submit",
								disabled: busy || !prompt.trim(),
								children: "Send"
							}),
							/* @__PURE__ */ u(TalkButton, {
								disabled: busy,
								onHearing: setPrompt,
								onHeard: (text) => void send(text, true),
								onUnsure: (text) => {
									unsure.current = text;
									setNotClear(true);
									promptBox.current?.focus();
								},
								onEdit: (text) => {
									unsure.current = text;
									promptBox.current?.focus();
								},
								onProblem: (problem) => {
									setFailed(problem);
									setNotClear(false);
								}
							}),
							teachMe && !quizGoing && /* @__PURE__ */ u("button", {
								type: "button",
								className: "secondary",
								disabled: busy,
								onClick: () => void send(TEACH_ME),
								children: "Teach me"
							}),
							quizMe && !quizGoing && /* @__PURE__ */ u("button", {
								type: "button",
								className: "secondary",
								disabled: busy,
								onClick: () => void send(QUIZ_ME),
								children: "Quiz me"
							}),
							assessOn && !quizGoing && /* @__PURE__ */ u("button", {
								type: "button",
								className: "secondary",
								disabled: busy,
								onClick: () => void send(ASSESS_ME),
								children: "Assessment"
							})
						]
					})]
				}),
				/* @__PURE__ */ u(DetailBar, {}),
				(teachMe || quizMe || assessOn) && !quizGoing && /* @__PURE__ */ u(Choices, {
					choices,
					disabled: busy,
					onAsk: (q) => void send(q)
				}),
				teachMe && lesson?.active && !quizGoing && /* @__PURE__ */ u(LessonControls, {
					lesson,
					disabled: busy,
					onAsk: (q) => void send(q)
				}),
				quizGoing && !assessing && quiz && /* @__PURE__ */ u(QuizControls, {
					quiz,
					disabled: busy,
					onAsk: (q) => void send(q)
				}),
				assessing && assessment && /* @__PURE__ */ u(AssessmentControls, {
					assessment,
					disabled: busy,
					onAsk: (q) => void send(q)
				}),
				!quizGoing && /* @__PURE__ */ u(Hints, {
					hints,
					disabled: busy,
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
var QUIZ_ME = "Quiz me";
var ASSESS_ME = "Assess me";
function AssessmentControls(props) {
	const { number, total } = props.assessment;
	return /* @__PURE__ */ u("div", {
		className: "lesson",
		children: [/* @__PURE__ */ u("p", {
			className: "muted",
			children: [
				"Assessment · question ",
				number,
				" of ",
				total
			]
		}), /* @__PURE__ */ u("div", {
			className: "lesson-buttons",
			children: /* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				disabled: props.disabled,
				onClick: () => props.onAsk("Stop the assessment"),
				children: "Stop the assessment"
			})
		})]
	});
}
function QuizControls(props) {
	const { topic, number, questions } = props.quiz;
	return /* @__PURE__ */ u("div", {
		className: "lesson",
		children: [/* @__PURE__ */ u("p", {
			className: "muted",
			children: [
				"Quiz: ",
				topic,
				" · question ",
				number,
				questions === void 0 ? "" : ` of ${questions}`
			]
		}), /* @__PURE__ */ u("div", {
			className: "lesson-buttons",
			children: /* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				disabled: props.disabled,
				onClick: () => props.onAsk("Stop the quiz"),
				children: "Stop the quiz"
			})
		})]
	});
}
var SAY_IT_SIMPLER = "Say it simpler";
function ReplyActions(props) {
	return /* @__PURE__ */ u("div", {
		className: "reply-actions",
		children: [/* @__PURE__ */ u("button", {
			type: "button",
			className: "secondary",
			disabled: props.disabled,
			onClick: props.onRepeat,
			children: "Repeat"
		}), props.onSimpler && /* @__PURE__ */ u("button", {
			type: "button",
			className: "secondary",
			disabled: props.disabled,
			onClick: () => {
				console.info("Say it simpler");
				props.onSimpler?.();
			},
			children: SAY_IT_SIMPLER
		})]
	});
}
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
	const [first, setFirst] = d(0);
	if (!line && examples.length === 0) return null;
	const shown = shownExamples(examples, first);
	return /* @__PURE__ */ u("div", {
		className: "hints",
		children: [line && /* @__PURE__ */ u("p", {
			className: "muted",
			children: line
		}), examples.length > 0 && /* @__PURE__ */ u("ul", {
			"aria-label": "Example questions",
			children: [shown.map((question) => /* @__PURE__ */ u("li", { children: /* @__PURE__ */ u("button", {
				type: "button",
				className: "example",
				disabled: props.disabled,
				onClick: () => {
					console.info("Example question asked");
					props.onAsk(question);
				},
				children: question
			}) }, question)), examples.length > 3 && /* @__PURE__ */ u("li", { children: /* @__PURE__ */ u("button", {
				type: "button",
				className: "link",
				onClick: () => {
					const next = (first + 3) % examples.length;
					console.info(`Other topics shown, from ${next + 1} of ${examples.length}`);
					setFirst(next);
				},
				children: "other topics..."
			}) })]
		})]
	});
}
function shownExamples(examples, first) {
	if (examples.length <= 3) return examples;
	return Array.from({ length: 3 }, (_, i) => examples[(first + i) % examples.length]);
}
function latestExchange(turns) {
	for (let i = turns.length - 1; i >= 0; i--) if (turns[i].role === "user") return i;
	return Math.max(turns.length - 1, 0);
}
function TurnList(props) {
	const { turns, from = 0, unspoken, search, notice, hideReplies } = props;
	let counted = 0;
	return /* @__PURE__ */ u("ol", {
		className: "turns",
		children: [turns.slice(from).map((turn, k) => {
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
					}) }) : hideReplies && turn.role === "assistant" && unspoken?.turn !== i ? /* @__PURE__ */ u(HiddenText, { text: turn.content }) : turn.content,
					unspoken?.turn === i && /* @__PURE__ */ u("span", {
						className: "note",
						children: "I couldn't say this one aloud, so here it is as text."
					})
				]
			}, i);
		}), notice && /* @__PURE__ */ u("li", {
			className: "assistant notice",
			role: "status",
			children: [/* @__PURE__ */ u("span", {
				className: "who",
				children: "Reply"
			}), notice]
		})]
	});
}
function HiddenText(props) {
	const [open, setOpen] = d(false);
	function toggle() {
		console.info(open ? "Reply text hidden" : "Reply text shown");
		setOpen(!open);
	}
	return /* @__PURE__ */ u("span", {
		className: "hidden-text",
		children: [/* @__PURE__ */ u("button", {
			type: "button",
			className: "link",
			"aria-expanded": open,
			onClick: toggle,
			children: open ? "Hide text" : "Review text"
		}), /* @__PURE__ */ u("span", {
			className: "reply-text",
			hidden: !open,
			children: props.text
		})]
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
function exchanges(turns) {
	const found = [];
	for (const turn of turns) if (turn.role === "user" || found.length === 0) found.push([turn]);
	else found[found.length - 1].push(turn);
	const last = found[found.length - 1];
	if (last?.length === 1 && last[0].role === "user") found.pop();
	return found;
}
function chatText(turns, count) {
	const all = exchanges(turns);
	const kept = all.slice(Math.max(all.length - count, 0));
	return [`Chat: the last ${kept.length} of ${all.length} exchanges`, ...kept.flat().map((t) => `${t.role === "user" ? "You" : "Reply"}: ${t.content}`)].join("\n\n");
}
function CopyChat(props) {
	const all = exchanges(props.turns).length;
	const [count, setCount] = d(null);
	const [done, setDone] = d();
	if (all === 0) return null;
	const shown = Math.min(count ?? all, all);
	const current = done?.turns === props.turns && done.shown === shown ? done : void 0;
	async function copy() {
		const { turns } = props;
		const text = chatText(turns, shown);
		try {
			await navigator.clipboard.writeText(text);
			console.info(`Chat copied (${shown} of ${all} exchanges, ${text.length} characters)`);
			setDone({
				turns,
				shown,
				byHand: null
			});
		} catch (e) {
			console.error("Could not copy the chat", e);
			setDone({
				turns,
				shown,
				byHand: text
			});
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
			current && current.byHand === null && /* @__PURE__ */ u("span", {
				className: "muted",
				children: "Copied"
			}),
			current?.byHand != null && /* @__PURE__ */ u("textarea", {
				readOnly: true,
				"aria-label": "Chat to copy",
				value: current.byHand,
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
	const idleUrl = props.idleUrl === void 0 ? IDLE_VIDEO_URL : props.idleUrl;
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
			idle !== "none" && idleUrl !== null && /* @__PURE__ */ u("video", {
				className: idle === "ready" ? "idle-video" : "idle-video resting",
				src: idleUrl,
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
	const { sound, onChange, onStop, onExit, saying } = props;
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
			})] }),
			onExit && /* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				onClick: onExit,
				disabled: saying,
				children: "Exit"
			})
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
		const took = metrics && step.seconds !== null ? ` in ${duration$1(step.seconds)}` : "";
		return /* @__PURE__ */ u("span", {
			className: "done",
			children: ["Done", took]
		});
	}
	if (!(status.steps?.findIndex((s) => s.done < s.total) === props.index)) return /* @__PURE__ */ u("span", {
		className: "muted",
		children: "Waiting"
	});
	if (status.state === "cancelled") return /* @__PURE__ */ u("span", {
		className: "muted",
		children: "Stopped"
	});
	if (status.state === "failed" || status.stopped) return /* @__PURE__ */ u("span", {
		className: "error",
		children: "Stopped"
	});
	return /* @__PURE__ */ u("span", {
		className: "busy",
		children: [step.activity ?? (step.total > 1 ? `${step.done} of ${step.total}` : "Working…"), step.left_s !== null && ` · about ${countdown(step.left_s)} left`]
	});
}
function countdown(seconds) {
	const s = Math.max(0, Math.round(seconds));
	const h = Math.floor(s / 3600);
	const m = Math.floor(s % 3600 / 60);
	return [
		h && `${h} h`,
		(h || m) && `${m} min`,
		`${s % 60} s`
	].filter(Boolean).join(" ");
}
function duration$1(seconds) {
	return seconds < 90 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`;
}
function NotFoundPage() {
	return /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("h1", { children: "Page not found" }), /* @__PURE__ */ u("a", {
		className: "button",
		href: "#/",
		children: "Go to the start page"
	})] });
}
//#endregion
//#region src/avatar-voice.tsx
var BACK_NOTICE$1 = {
	sounds: "You rejected the voice. Add new recordings and remove the ones you don't want, then Prepare again.",
	accent: "Choose another accent. The sample video is then made again."
};
function AvatarVoicePage() {
	const [current, setCurrent] = d(null);
	const [failed, setFailed] = d(null);
	const [changes, setChanges] = d(0);
	const changed = () => setChanges((n) => n + 1);
	const [preparing, setPreparing] = d(false);
	const [back, setBack] = d(null);
	const [pending, setPending] = d(false);
	const leaveDialog = useLeaveGuard(pending, "The avatar keeps the voice it has now.");
	const stopGuard = usePrepareStopGuard(changed);
	h(() => {
		const started = performance.now();
		getReview().then((r) => {
			setCurrent(r);
			const took = Math.round(performance.now() - started);
			console.info(`Avatar in your own voice: ${r.own_voice === true}, accepted: ${r.voice_accepted === true} (${took} ms)`);
		}).catch((e) => {
			console.error("Could not get the review", e);
			setFailed("Could not load the page. Reload it to try again.");
		});
	}, []);
	if (current === null) return failed ? /* @__PURE__ */ u("p", {
		className: "error",
		children: failed
	}) : /* @__PURE__ */ u("p", {
		className: "muted busy",
		children: "Loading…"
	});
	if (!current.default_person) return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("h1", { children: "Your voice for an avatar" }),
		/* @__PURE__ */ u("p", { children: "Choose a ready-made avatar first, then give it your voice." }),
		/* @__PURE__ */ u("a", {
			className: "button",
			href: "#/start-now",
			children: "Choose an avatar"
		})
	] });
	if (!current.own_voice) return /* @__PURE__ */ u(VoiceConsent, { onAgreed: setCurrent });
	async function readyVoice() {
		const started = performance.now();
		setFailed(null);
		try {
			await useAvatarReadyVoice();
			console.info(`Avatar's ready-made voice used again (${Math.round(performance.now() - started)} ms)`);
			goWithoutAsking("#/chat");
		} catch (e) {
			console.error("Could not use the avatar's ready-made voice again", e);
			setFailed(e.message);
		}
	}
	const notice = (part) => back === part ? BACK_NOTICE$1[part] ?? null : null;
	return /* @__PURE__ */ u(SettingGuard.Provider, {
		value: stopGuard.guard,
		children: /* @__PURE__ */ u("div", {
			className: "host-page",
			children: [
				/* @__PURE__ */ u("h1", { children: "Your voice for the avatar" }),
				/* @__PURE__ */ u("p", {
					className: "lead",
					children: "The avatar keeps its picture and speaks in a voice made from your recordings. Add them, choose an accent, then prepare a sample video and check it. Until you accept it, the avatar speaks in its ready-made voice."
				}),
				/* @__PURE__ */ u("p", {
					className: "avatar-instead",
					children: [
						"Rather keep its ready-made voice?",
						" ",
						/* @__PURE__ */ u("button", {
							type: "button",
							className: "link",
							onClick: () => void readyVoice(),
							children: "Use the avatar's ready-made voice"
						}),
						". Your recordings are kept."
					]
				}),
				failed && /* @__PURE__ */ u("p", {
					className: "error",
					children: failed
				}),
				/* @__PURE__ */ u("section", {
					className: "panel",
					id: "photos",
					children: [
						/* @__PURE__ */ u(StepOf, { n: 1 }),
						/* @__PURE__ */ u("h2", { children: "Picture" }),
						/* @__PURE__ */ u("p", {
							className: "muted",
							children: "The ready-made avatar's picture, already prepared."
						}),
						/* @__PURE__ */ u("img", {
							className: "avatar-picture",
							src: DEFAULT_PICTURE,
							alt: "The ready-made avatar"
						})
					]
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
					onPending: setPending,
					onStopped: stopGuard.onStopped,
					avatarVoice: true,
					onBack: (to) => {
						setBack(to);
						window.setTimeout(() => document.getElementById(to)?.scrollIntoView?.({ behavior: "smooth" }));
					}
				}),
				leaveDialog,
				stopGuard.dialog
			]
		})
	});
}
function VoiceConsent({ onAgreed }) {
	const [checked, setChecked] = d(false);
	const [saving, setSaving] = d(false);
	const [failed, setFailed] = d(null);
	async function submit(event) {
		event.preventDefault();
		const started = performance.now();
		setSaving(true);
		setFailed(null);
		try {
			const review = await useAvatarOwnVoice();
			console.info(`Avatar to speak in your own voice (${Math.round(performance.now() - started)} ms)`);
			onAgreed(review);
		} catch (e) {
			console.error("Could not give the avatar your voice", e);
			setFailed(e.message);
			setSaving(false);
		}
	}
	return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("h1", { children: "Your voice for the avatar" }),
		/* @__PURE__ */ u("p", { children: "The avatar keeps its picture and speaks in a voice made from recordings you add. Only use recordings of someone who has agreed to this, or of yourself." }),
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
						"The person in the recordings I will upload agreed to have their voice copied by this app."
					]
				}),
				/* @__PURE__ */ u("button", {
					type: "submit",
					disabled: !checked || saving,
					children: "Continue"
				}),
				/* @__PURE__ */ u("a", {
					className: "button secondary",
					href: "#/settings",
					children: "Cancel"
				}),
				failed && /* @__PURE__ */ u("p", {
					className: "error",
					children: failed
				})
			]
		})
	] });
}
//#endregion
//#region src/content.tsx
var READING_POLL_MS = 1e3;
function ContentPage() {
	const [pdfs, setPdfs] = d(null);
	const { ask, dialog } = useConfirm();
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
		if (!await ask({
			title: `Remove ${pdf.name}?`,
			children: /* @__PURE__ */ u("p", { children: "Its wiki pages are removed too." }),
			keepLabel: "No, keep it",
			confirmLabel: "Yes, remove it"
		})) return;
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
		className: "host-page",
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
							size$1(pdf.size),
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
			}),
			dialog
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
	if (build.state === "building" && build.stage !== "outline" && build.parts) return /* @__PURE__ */ u("span", {
		className: "muted busy",
		children: [
			wikiText(build, metrics),
			" ",
			/* @__PURE__ */ u("progress", {
				max: build.parts,
				value: build.part,
				"aria-label": "Wiki parts built"
			})
		]
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
	const time = (what = "", pending = "") => {
		const parts = [];
		if (b.elapsed_s != null) parts.push(`${duration(b.elapsed_s)} so far`);
		if (b.remaining_s != null) parts.push(`about ${duration(b.remaining_s)} left${what}`);
		else if (pending) parts.push(pending);
		return parts.length ? ` (${parts.join(", ")})` : "";
	};
	const sofar = time();
	if (b.state === "waiting") {
		if (b.error) return `Waiting for the AI to be ready to build the wiki…${sofar}`;
		if (b.stopping) return `Waiting to build the wiki: stopping the removed PDF's build${b.ahead && b.ahead > 1 ? `, then ${plural(b.ahead - 1, "PDF")} ahead` : ""}…${sofar}`;
		if (b.ahead) {
			const now = b.building_name ? `, building “${b.building_name}” now` : "";
			return `Waiting to build the wiki: ${plural(b.ahead, "PDF")} ahead${now}…${sofar}`;
		}
		return `Waiting to build the wiki…${sofar}`;
	}
	if (b.state === "building" && b.stage === "outline") {
		const step = Math.min(b.steps + 1, b.steps_planned);
		return b.steps_planned ? `Arranging the wiki's topics: step ${step} of about ${b.steps_planned}…${sofar}` : `Arranging the wiki's topics…${sofar}`;
	}
	if (b.state === "building") {
		const part = Math.min(b.part + 1, b.parts);
		if (!b.parts) return `Building the wiki…${sofar}`;
		const done = Math.round(100 * b.part / b.parts);
		const left = time(" before arranging its topics", "the time left shows once part 1 is done");
		return `Building the wiki: part ${part} of ${b.parts}, ${done}% done…${left}`;
	}
	if (b.state === "failed") return b.error ?? "The wiki could not be built.";
	const n = b.skipped_parts?.length ?? 0;
	const skipped = n ? ` (${plural(n, "part")} of ${b.parts} skipped: the AI's answer couldn't be used)` : "";
	const detail = b.detail_pages ? `, ${plural(b.detail_pages, "detail page")}` : "";
	const took = metrics && b.elapsed_s != null ? `, built in ${duration(b.elapsed_s)}` : "";
	return `Wiki ready: ${plural(b.pages ?? 0, "topic")}${detail}${took}${skipped}`;
}
function duration(seconds) {
	const s = Math.round(seconds);
	if (s < 60) return `${s} s`;
	if (s < 3600) return `${Math.floor(s / 60)} min ${s % 60} s`;
	return `${Math.floor(s / 3600)} h ${Math.floor(s % 3600 / 60)} min`;
}
function plural(n, word) {
	return `${n} ${word}${n === 1 ? "" : "s"}`;
}
function size$1(bytes) {
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
function guideAt(title) {
	const step = STEPS.findIndex((s) => s.title === title);
	if (step < 0) return;
	saveGuide({
		...loadGuide(),
		step
	});
	console.info(`Guide opened from the wizard at: ${title}`);
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
var SCRIPT_1 = [
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
];
var SCRIPT_2 = [
	"Could you call me back around four thirty? My number is five five five, two nine one, eight three zero seven.",
	"It cost about twelve dollars and fifty cents, which felt fair for what it was.",
	"Hmm, I'm not totally sure. I think it was in two thousand nineteen, but don't quote me on that.",
	"Wow. That is genuinely the best news I've heard all week.",
	"I'm sorry to hear that. That sounds really hard, and it makes sense that you're tired.",
	"Here's a fun fact: an octopus has three hearts and blue blood.",
	"Would you like the short version, or the long version with all the details?",
	"Measure twice, cut once. My father used to say that, and he was usually right.",
	"Thanks for listening. Take care of yourself, and let's talk again soon."
];
var QUESTIONS_3 = [
	"What did you do last weekend?",
	"Describe a place you love and why.",
	"Explain how to make something you cook often.",
	"What's something you've changed your mind about?"
];
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
			lines: SCRIPT_1
		})] })
	},
	{
		title: "Recording 2 of 7",
		body: () => /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u(Before, {
			name: "Voice 2",
			minutes: "1½ minutes"
		}), /* @__PURE__ */ u(Script, {
			first: 11,
			lines: SCRIPT_2
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
			/* @__PURE__ */ u(Questions, { items: QUESTIONS_3 }),
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
async function loadHome(consented) {
	try {
		if ((await getStartNow()).chosen) {
			console.info("Home loaded (a default person is chosen)");
			return {
				done: true,
				photo: DEFAULT_PICTURE,
				defaultPerson: true
			};
		}
	} catch (e) {
		console.error("Could not read the default person", e);
	}
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
function setupLink(consented, defaultPerson = false, own = true) {
	if (defaultPerson || !own) return "#/start-now";
	return consented ? "#/setup" : "#/consent";
}
function choices(done, consented, defaultPerson = false, own = true) {
	const setupHref = setupLink(consented);
	const startNow = {
		href: "#/start-now",
		title: "Start now",
		text: "Chat at once with a ready-made avatar: a made-up person in a ready-made voice."
	};
	if (!done && !own) return [startNow];
	if (!done) return [startNow, {
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
		!own ? {
			href: "#/start-now",
			title: "Setup",
			text: "Choose another ready-made avatar."
		} : defaultPerson ? {
			href: setupLink(consented, true),
			title: "Setup",
			text: "Choose another ready-made avatar, or use your own photo and voice."
		} : {
			href: setupHref,
			title: "Setup",
			text: "Change the photos, the voice recordings or the accent."
		}
	];
}
function HomePage({ consented, landing = false }) {
	const use = useCustomUse();
	const [state, setState] = d(null);
	h(() => {
		let active = true;
		loadHome(consented).then((loaded) => {
			if (!active) return;
			if (landing && loaded.done) {
				console.info("Setup is saved, so the visit starts in the chat");
				window.location.replace("#/chat");
				return;
			}
			setState(loaded);
		});
		return () => {
			active = false;
		};
	}, [consented]);
	if (state === null) return /* @__PURE__ */ u("p", {
		className: "muted busy",
		children: "Loading…"
	});
	const shown = choices(state.done, consented, state.defaultPerson, use.image);
	return /* @__PURE__ */ u("section", {
		className: "home",
		children: [
			/* @__PURE__ */ u("div", {
				className: "hero",
				children: [state.photo && /* @__PURE__ */ u("img", {
					className: "portrait",
					src: state.photo,
					alt: "The person in the video"
				}), /* @__PURE__ */ u("div", { children: [/* @__PURE__ */ u("h1", { children: state.done ? "Welcome back" : "Welcome" }), /* @__PURE__ */ u("p", {
					className: "muted",
					children: state.done ? "Setup is done. Pick up where you left off." : "Make a talking video of a person from a few photos and voice recordings. The person then speaks the chatbot's replies."
				})] })]
			}),
			/* @__PURE__ */ u("ul", {
				className: `choices ${[
					"one",
					"two",
					"three"
				][shown.length - 1]}`,
				children: shown.map((c) => /* @__PURE__ */ u("li", { children: /* @__PURE__ */ u("a", {
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
			}),
			!state.done && use.image && use.voice && /* @__PURE__ */ u("p", {
				className: "wizard-link",
				children: [/* @__PURE__ */ u("a", {
					href: "#/setup/wizard",
					children: "Set up with your own photo and voice"
				}), ", one step at a time."]
			})
		]
	});
}
var ICONS = {
	"#/chat": "M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v6a2.5 2.5 0 0 1-2.5 2.5H11l-4 3.5V15h0.5A2.5 2.5 0 0 1 5 12.5z",
	"#/content": "M7 3.5h6.5L18 8v12.5H7zM13.5 3.5V8H18M9.5 12h6M9.5 15.5h6",
	"#/start-now": "M12 4a3.5 3.5 0 1 1 0 7a3.5 3.5 0 0 1 0-7zM5 20a7 7 0 0 1 14 0",
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
//#region src/start-now.tsx
var OPTIONS = {
	accent: [{
		value: "American",
		label: "American"
	}, {
		value: "British",
		label: "British"
	}],
	realism: [{
		value: "photoreal",
		label: "Photorealistic"
	}, {
		value: "animated",
		label: "Animated"
	}]
};
var LEGENDS = {
	accent: "Accent",
	realism: "Look"
};
var FIRST = {
	gender: "female",
	accent: "American",
	realism: "photoreal",
	role: "Professor"
};
var WORKING = [
	"downloading",
	"unpacking",
	"getting-ready"
];
function finishing(status) {
	return status?.state === "ready" && status.chat_ready === false;
}
function progressText(status) {
	if (status.state === "downloading") return `Step 1 of 3: Downloading the avatar… ${status.percent}%`;
	if (status.state === "unpacking") return "Step 2 of 3: Unpacking the avatar…";
	if (status.state === "getting-ready") return "Step 2 of 3: Getting the avatar's voice ready…";
	return "Step 3 of 3: Making the avatar's video for the chat…";
}
function timeText(status, seconds) {
	if (status.left_s != null) return ` · about ${countdown(status.left_s)} left`;
	return finishing(status) && seconds > 0 ? ` ${seconds} s` : "";
}
function useSeconds(on) {
	const [seconds, setSeconds] = d(0);
	h(() => {
		if (!on) return;
		const from = performance.now();
		setSeconds(0);
		const timer = setInterval(() => setSeconds(Math.round((performance.now() - from) / 1e3)), 1e3);
		return () => clearInterval(timer);
	}, [on]);
	return seconds;
}
function facesOf(faces, choice) {
	return faces.filter((f) => f.realism === choice.realism);
}
function withFace(choice, face) {
	return {
		...choice,
		gender: face.gender,
		role: face.role,
		face: face.face
	};
}
function StartNowPage() {
	const use = useCustomUse();
	const [choice, setChoice] = d(FIRST);
	const [faces, setFaces] = d(null);
	const [facesFailed, setFacesFailed] = d(false);
	const change = (changes) => {
		const next = {
			...choice,
			...changes
		};
		const first = facesOf(faces ?? [], next)[0];
		setChoice(next.realism === choice.realism || !first ? next : withFace(next, first));
	};
	const [status, setStatus] = d(null);
	const [refused, setRefused] = d(null);
	const started = A(0);
	h(() => {
		const asked = performance.now();
		getFaces().then((f) => {
			setFaces(f);
			console.info(`${f.length} faces to pick from (${Math.round(performance.now() - asked)} ms)`);
		}).catch((e) => {
			console.error("Could not read the faces", e);
			setFacesFailed(true);
		});
		getStartNow().then((s) => {
			if (s.chosen) setChoice(s.chosen);
			if (WORKING.includes(s.state) || finishing(s)) setStatus(s);
		}).catch((e) => console.error("Could not read the default person", e));
	}, []);
	const working = status !== null && (WORKING.includes(status.state) || finishing(status));
	const seconds = useSeconds(finishing(status));
	h(() => {
		if (finishing(status)) console.info("Avatar ready; waiting for its idle video for the chat");
	}, [finishing(status)]);
	h(() => {
		if (status?.state === "ready" && !finishing(status)) {
			const ms = Math.round(performance.now() - started.current);
			console.info(`Default person ${status.person} ready in ${ms} ms; opening the chat`);
			window.location.hash = "#/chat";
			return;
		}
		if (!working) return;
		const timer = setTimeout(() => {
			getStartNow().then(setStatus).catch((e) => {
				console.error("Could not read how the download is going", e);
				setStatus((s) => s && {
					...s,
					state: "failed",
					error: "Could not reach the app. Try again."
				});
			});
		}, 500);
		return () => clearTimeout(timer);
	}, [status]);
	async function start() {
		setRefused(null);
		started.current = performance.now();
		console.info("Start now with a default person", choice);
		try {
			setStatus(await startNow(choice));
		} catch (e) {
			console.error("Could not start with a default person", e);
			setRefused(e.message);
		}
	}
	const shown = facesOf(faces ?? [], choice);
	const locked = working || faces === null;
	const face = choice.face ?? 1;
	return /* @__PURE__ */ u("section", {
		className: "start-now panel",
		children: [
			/* @__PURE__ */ u("h1", { children: "Avatar Choice: a ready-made avatar" }),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: ["Chat at once with a made-up person who speaks in a ready-made voice.", use.image && " You can switch to your own photo and voice at any time in Settings, under Avatar Choice."]
			}),
			use.image && /* @__PURE__ */ u("p", {
				className: "avatar-instead",
				children: [
					"Rather use your own image and voice?",
					" ",
					/* @__PURE__ */ u("a", {
						className: "button secondary",
						href: "#/consent/own",
						onClick: () => console.info("Choosing your own image and voice from Avatar Choice"),
						children: "Use your own image and voice"
					})
				]
			}),
			/* @__PURE__ */ u("form", {
				onSubmit: (e) => {
					e.preventDefault();
					start();
				},
				children: [
					["accent", "realism"].map((key) => /* @__PURE__ */ u("fieldset", {
						disabled: locked,
						children: [/* @__PURE__ */ u("legend", { children: LEGENDS[key] }), OPTIONS[key].map(({ value, label }) => /* @__PURE__ */ u("label", { children: [
							/* @__PURE__ */ u("input", {
								type: "radio",
								name: key,
								value,
								checked: choice[key] === value,
								onChange: () => change({ [key]: value })
							}),
							" ",
							label
						] }, value))]
					}, key)),
					faces === null && !facesFailed && /* @__PURE__ */ u("p", {
						className: "muted",
						children: "Loading the faces…"
					}),
					facesFailed && /* @__PURE__ */ u("p", {
						className: "error",
						role: "alert",
						children: "Couldn't load the faces to pick from. Reload the page to try again."
					}),
					shown.length > 0 && /* @__PURE__ */ u("fieldset", {
						className: "faces",
						disabled: working,
						children: [/* @__PURE__ */ u("legend", { children: "Face" }), shown.map((f, i) => {
							const picked = f.gender === choice.gender && f.role === choice.role && f.face === face;
							const name = `Face ${i + 1} of ${shown.length}`;
							return /* @__PURE__ */ u("label", {
								className: picked ? "face picked" : "face",
								children: [/* @__PURE__ */ u("input", {
									type: "radio",
									name: "face",
									value: f.name,
									checked: picked,
									onChange: () => {
										console.info(`${name} picked: ${f.name}`);
										setChoice(withFace(choice, f));
									}
								}), /* @__PURE__ */ u("img", {
									src: faceUrl(f.name),
									alt: name
								})]
							}, f.name);
						})]
					}),
					/* @__PURE__ */ u("button", {
						type: "submit",
						disabled: locked,
						className: working ? "busy" : void 0,
						children: status?.state === "failed" ? "Try again" : "Start now"
					})
				]
			}),
			working && /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("p", {
				className: "busy",
				children: [progressText(status), timeText(status, seconds)]
			}), status.state === "downloading" ? /* @__PURE__ */ u("progress", {
				max: 100,
				value: status.percent,
				"aria-label": "Downloading",
				children: [status.percent, "%"]
			}) : /* @__PURE__ */ u("progress", { "aria-label": "Getting the avatar ready" })] }),
			status?.state === "failed" && /* @__PURE__ */ u("p", {
				className: "error",
				role: "alert",
				children: status.error
			}),
			refused && /* @__PURE__ */ u("p", {
				className: "error",
				role: "alert",
				children: refused
			}),
			use.image && /* @__PURE__ */ u("p", {
				className: "muted",
				children: [
					"Or ",
					/* @__PURE__ */ u("a", {
						href: "#/consent/own",
						children: "use your own photos and voice"
					}),
					"."
				]
			})
		]
	});
}
//#endregion
//#region src/resources.tsx
var MB = 1e3 ** 2;
var GB = 1e3 ** 3;
function size(bytes) {
	if (bytes >= GB) return `${(bytes / GB).toFixed(2)} GB`;
	return `${(bytes / MB).toFixed(1)} MB`;
}
var ROWS = [
	[
		"images_and_recordings",
		"Images and voice recordings",
		"The photos and recordings you added."
	],
	[
		"pdfs",
		"PDFs",
		"The PDFs you added."
	],
	[
		"total",
		"Total",
		"All the disk space your files take."
	]
];
function ResourcesPage() {
	const session = useHost().session;
	const host = session?.signed_in === true;
	const [disk, setDisk] = d(null);
	const [failed, setFailed] = d(false);
	h(() => {
		if (!host) return;
		getHostDisk(true).then((read) => {
			setDisk(read);
			console.info(`Resource view opened: ${JSON.stringify(read)}`);
		}, (e) => {
			console.error("Could not read the disk space used", e);
			setFailed(true);
		});
	}, [host]);
	if (session === null) return /* @__PURE__ */ u("p", { children: "Loading…" });
	if (!host) return /* @__PURE__ */ u(HostOnlyPage, {});
	return /* @__PURE__ */ u("div", {
		className: "host-page resources-page",
		children: [
			/* @__PURE__ */ u("h1", { children: "Resources" }),
			/* @__PURE__ */ u("p", {
				className: "lead",
				children: [
					"The disk space used by the files you added, as ",
					session.email,
					"."
				]
			}),
			failed && /* @__PURE__ */ u("p", {
				className: "error",
				children: "The disk space used could not be read. Reload to try again."
			}),
			!failed && disk === null && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Counting…"
			}),
			disk && /* @__PURE__ */ u("section", {
				className: "panel",
				"aria-label": "Disk space used",
				children: [/* @__PURE__ */ u("h2", { children: "Disk space used" }), /* @__PURE__ */ u("dl", {
					className: "disk-used",
					children: ROWS.map(([key, label, about]) => /* @__PURE__ */ u("div", {
						className: key === "total" ? "disk-row total" : "disk-row",
						children: [/* @__PURE__ */ u("dt", { children: [label, /* @__PURE__ */ u("span", {
							className: "muted",
							children: [" · ", about]
						})] }), /* @__PURE__ */ u("dd", { children: size(disk[key]) })]
					}, key))
				})]
			})
		]
	});
}
//#endregion
//#region src/settings-access.tsx
var AccessContext = X(null);
function useSettingsShown() {
	return x(AccessContext);
}
function SettingsAccessProvider({ children }) {
	const session = useHost().session;
	const [shown, setShown] = d(null);
	const host = session?.signed_in;
	h(() => {
		if (host === void 0) return;
		let current = true;
		(async () => {
			const laptop = !host && canProve() ? await prove(await getAdminChallenge()) : void 0;
			const access = await getSettingsAccess(laptop);
			if (!access.shown && laptop) console.info(`This laptop's ID: ${await laptopId()}`);
			return access;
		})().then((access) => {
			if (!current) return;
			console.info(access.shown ? `Settings shown, as ${access.as}` : "Settings hidden");
			setShown(access.shown === true);
		}, (e) => {
			console.error("Could not ask whether Settings is shown", e);
			if (current) setShown(false);
		});
		return () => {
			current = false;
		};
	}, [host]);
	return /* @__PURE__ */ u(AccessContext.Provider, {
		value: shown,
		children
	});
}
//#endregion
//#region src/wiki.tsx
var WIKI_POLL_MS = 2e3;
function busy(build) {
	return build?.state === "waiting" || build?.state === "building";
}
function WikiPage({ pdf }) {
	const participant = useSettings().view === "participant";
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
			!participant && /* @__PURE__ */ u(HostTrail, {}),
			/* @__PURE__ */ u("h1", { children: "Wiki" }),
			pdf ? /* @__PURE__ */ u("p", { children: /* @__PURE__ */ u("a", {
				href: wikiHref(),
				children: "All PDFs"
			}) }) : participant ? /* @__PURE__ */ u("p", {
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
	const participant = useSettings().view === "participant";
	const built = new Set(wiki.contents.map((c) => c.pdf_id));
	const waiting = wiki.pdfs.filter((p) => !built.has(p.id) && (!pdf || p.id === pdf));
	if (wiki.pdfs.length === 0) {
		if (participant) return /* @__PURE__ */ u("p", { children: "There are no PDFs yet." });
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
			!participant && /* @__PURE__ */ u(S, { children: [
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
	const participant = useSettings().view === "participant";
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
				}), !participant && /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u(Rebuild, {
					build,
					onRebuild
				}), /* @__PURE__ */ u(WikiTools, {
					contents,
					onChanged
				})] })]
			}),
			!participant && contents.lost_edits.length > 0 && /* @__PURE__ */ u(LostEdits, {
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
	const participant = useSettings().view === "participant";
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
					!participant && /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("a", {
						href: "#/content",
						children: "Manage Content"
					}), /* @__PURE__ */ u("span", {
						"aria-hidden": "true",
						children: " › "
					})] }),
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
				!participant && /* @__PURE__ */ u(EditActions, {
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
	const participant = useSettings().view === "participant";
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
			edit: participant ? void 0 : {
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
	const participant = useSettings().view === "participant";
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
		}) : entry.edited && !participant && /* @__PURE__ */ u("span", {
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
function HostTrail() {
	return /* @__PURE__ */ u("nav", {
		className: "trail",
		"aria-label": "Where this page is",
		children: [
			/* @__PURE__ */ u("a", {
				href: "#/content",
				children: "Manage Content"
			}),
			/* @__PURE__ */ u("span", {
				"aria-hidden": "true",
				children: " › "
			}),
			/* @__PURE__ */ u("span", { children: "Wiki" })
		]
	});
}
var WHY_NOT$1 = {
	insecure: "The browser allows the camera only on a secure page (HTTPS) or on this computer (localhost), and this page is neither.",
	unsupported: "This browser can't use a camera.",
	refused: "The browser wasn't allowed to use the camera.",
	"no-camera": "No camera was found on this computer.",
	failed: "The camera could not be started. It may be in use by another app."
};
function cameraBlocked() {
	if (window.isSecureContext === false) return "insecure";
	if (!navigator.mediaDevices?.getUserMedia) return "unsupported";
	return null;
}
function reasonOf$1(error) {
	const name = error?.name;
	if (name === "NotAllowedError" || name === "SecurityError") return "refused";
	if (name === "NotFoundError" || name === "OverconstrainedError") return "no-camera";
	if (name === "NotSupportedError") return "unsupported";
	return "failed";
}
var NO_PICTURE = "The camera isn't sending a picture. Wait a moment and try again, or choose another camera.";
function grabFrame(video) {
	const width = video.videoWidth;
	const height = video.videoHeight;
	if (!width || !height) return Promise.reject(/* @__PURE__ */ new Error(NO_PICTURE));
	const canvas = document.createElement("canvas");
	canvas.width = width;
	canvas.height = height;
	const context = canvas.getContext("2d");
	if (!context) return Promise.reject(/* @__PURE__ */ new Error("The picture could not be taken."));
	context.drawImage(video, 0, 0, width, height);
	return new Promise((resolve, reject) => canvas.toBlob((blob) => blob ? resolve({
		blob,
		width,
		height
	}) : reject(/* @__PURE__ */ new Error("The picture could not be taken.")), "image/jpeg", .92));
}
var CAMERA_KEY = "imageskin.camera";
function savedCamera() {
	try {
		return localStorage.getItem(CAMERA_KEY);
	} catch {
		return null;
	}
}
function saveCamera(id) {
	try {
		localStorage.setItem(CAMERA_KEY, id);
	} catch (e) {
		console.warn("Could not remember the camera chosen", e);
	}
}
var NOT_A_PHOTO_CAMERA = /\b(ir|infrared|virtual|obs|snap|manycam|xsplit|nvidia broadcast|droidcam|camo)\b/i;
function betterCamera(cameras, current) {
	const inUse = cameras.find((c) => c.id === current);
	if (!inUse || !NOT_A_PHOTO_CAMERA.test(inUse.label)) return null;
	return cameras.find((c) => !NOT_A_PHOTO_CAMERA.test(c.label)) ?? null;
}
function stopTracks$1(stream) {
	stream?.getTracks().forEach((t) => t.stop());
}
function report$1(r) {
	reportCamera(r).catch((e) => console.error("Could not log the camera's use", e));
}
function CameraPhoto(props) {
	const grab = props.grab ?? grabFrame;
	const [phase, setPhase] = d("starting");
	const [reason, setReason] = d(null);
	const [count, setCount] = d(3);
	const [shot, setShot] = d(null);
	const [grabFailed, setGrabFailed] = d(null);
	const [cameras, setCameras] = d([]);
	const [cameraId, setCameraId] = d(null);
	const label = A("");
	const video = A(null);
	const stream = A(null);
	const timers = A([]);
	const alive = A(true);
	const starts = A(0);
	const guard = useSettingGuard();
	function stopCamera() {
		if (stream.current) console.info("Camera turned off");
		stopTracks$1(stream.current);
		stream.current = null;
	}
	function notUsed(why, error) {
		if (error) console.error(`Camera not used (${why})`, error);
		else console.info(`Camera not used (${why})`);
		report$1({
			taken: false,
			reason: why
		});
		setReason(why);
		setPhase("off");
	}
	async function videoInputs() {
		try {
			return (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput" && d.deviceId).map((d, i) => ({
				id: d.deviceId,
				label: d.label || `Camera ${i + 1}`
			}));
		} catch (e) {
			console.error("Could not list the cameras", e);
			return [];
		}
	}
	function open(id, exact) {
		const video = id ? { deviceId: exact ? { exact: id } : { ideal: id } } : true;
		return navigator.mediaDevices.getUserMedia({
			video,
			audio: false
		});
	}
	async function start(chosen = null, explicit = false) {
		const mine = ++starts.current;
		const latest = () => alive.current && starts.current === mine;
		setPhase("starting");
		setGrabFailed(null);
		const blocked = cameraBlocked();
		if (blocked) {
			notUsed(blocked);
			return;
		}
		const started = performance.now();
		const known = await videoInputs();
		if (!latest()) return;
		let target = chosen;
		if (!explicit) {
			const saved = known.find((c) => c.id === savedCamera());
			const real = known.find((c) => !NOT_A_PHOTO_CAMERA.test(c.label));
			target = (saved && !NOT_A_PHOTO_CAMERA.test(saved.label) ? saved : real ?? saved)?.id ?? null;
		}
		const exact = target !== null && known.some((c) => c.id === target);
		let media = null;
		let failure = null;
		try {
			media = await open(target, exact);
		} catch (e) {
			failure = e;
		}
		if (!media && reasonOf$1(failure) !== "refused" && latest()) {
			const others = (await videoInputs()).filter((c) => c.id !== target);
			others.sort((a, b) => Number(NOT_A_PHOTO_CAMERA.test(a.label)) - Number(NOT_A_PHOTO_CAMERA.test(b.label)));
			for (const other of others) {
				if (!latest()) break;
				try {
					media = await open(other.id, true);
					console.warn(`The first camera wouldn't start (${failure?.name}); opened ${other.label}`);
					break;
				} catch (e) {
					console.warn(`${other.label} wouldn't start either`, e);
				}
			}
		}
		if (!media) {
			if (latest()) notUsed(reasonOf$1(failure), failure);
			return;
		}
		if (!latest()) {
			stopTracks$1(media);
			return;
		}
		stopCamera();
		stream.current = media;
		const track = media.getVideoTracks?.()[0];
		label.current = track?.label ?? "";
		const opened = track?.getSettings?.().deviceId ?? null;
		setCameraId(opened);
		try {
			await track?.applyConstraints?.({
				width: { ideal: 1920 },
				height: { ideal: 1080 }
			});
		} catch (e) {
			console.warn("The camera kept its own size", e);
		}
		if (!latest()) {
			if (stream.current === media) stopCamera();
			return;
		}
		console.info(`Camera on in ${Math.round(performance.now() - started)} ms: ${label.current || "unnamed"}`);
		listCameras(opened, explicit, mine);
		setPhase("live");
	}
	async function listCameras(current, chosen, mine) {
		const found = await videoInputs();
		console.info(`Cameras: ${found.map((c) => c.label).join(", ") || "none listed"}`);
		if (!alive.current || starts.current !== mine) return;
		setCameras(found);
		const better = chosen ? null : betterCamera(found, current);
		if (better) {
			const was = found.find((c) => c.id === current)?.label;
			console.info(`Camera switched from ${was} to ${better.label}: the first can't take the photo`);
			stopCamera();
			start(better.id, true);
		}
	}
	function switchCamera(id) {
		console.info(`Camera chosen: ${cameras.find((c) => c.id === id)?.label ?? id}`);
		saveCamera(id);
		stopCamera();
		start(id, true);
	}
	h(() => {
		const element = video.current;
		if (phase !== "live" || !element || !stream.current) return;
		element.srcObject = stream.current;
		element.play().catch((e) => console.error("Could not play the live picture", e));
	}, [phase]);
	h(() => {
		alive.current = true;
		start();
		return () => {
			alive.current = false;
			timers.current.forEach((t) => window.clearTimeout(t));
			stopCamera();
		};
	}, []);
	const shown = A(null);
	function show(url) {
		if (shown.current && shown.current !== url) URL.revokeObjectURL(shown.current);
		shown.current = url;
	}
	h(() => () => show(null), []);
	function takePhoto() {
		setGrabFailed(null);
		setPhase("counting");
		setCount(3);
		for (let s = 1; s <= 3; s++) timers.current.push(window.setTimeout(() => s < 3 ? setCount(3 - s) : void capture(), s * 1e3));
	}
	async function capture() {
		timers.current = [];
		const element = video.current;
		if (!element) return;
		let grabbed;
		try {
			grabbed = await grab(element);
		} catch (e) {
			console.error("Could not take the picture", e);
			setShot(null);
			setGrabFailed(e.message);
			setPhase("live");
			return;
		}
		stopCamera();
		report$1({
			taken: true,
			width: grabbed.width,
			height: grabbed.height,
			camera: label.current
		});
		console.info(`Camera photo taken: ${grabbed.width}×${grabbed.height}`);
		const url = URL.createObjectURL(grabbed.blob);
		show(url);
		setShot({
			url,
			upload: null,
			error: null
		});
		if (!await guard.confirm("Add the photo you took?")) {
			setPhase("taken");
			return;
		}
		setPhase("checking");
		props.onChanging(true);
		const started = performance.now();
		const name = `camera-${(/* @__PURE__ */ new Date()).toISOString().replace(/[:.]/g, "-")}.jpg`;
		try {
			const upload = await uploadFile("photos", new File([grabbed.blob], name, { type: "image/jpeg" }));
			console.info(`Camera photo checked in ${Math.round(performance.now() - started)} ms`);
			if (alive.current) setShot({
				url,
				upload,
				error: null
			});
			if (upload.problems?.length) {
				if (!await dropFailed(upload) && alive.current) setShot({
					url,
					upload,
					error: null,
					stayed: true
				});
			} else props.onAdded();
		} catch (e) {
			console.error("Camera photo refused", e);
			if (alive.current) setShot({
				url,
				upload: null,
				error: e.message
			});
		}
		props.onChanging(false);
		if (alive.current) setPhase("taken");
	}
	async function dropFailed(upload) {
		try {
			await removeUpload("photos", upload.id);
			console.info(`Camera photo failed its checks and was not kept: ${upload.problems?.join(" ")}`);
			return true;
		} catch (e) {
			console.error("Could not remove the camera photo that failed its checks", e);
			props.onAdded();
			return false;
		}
	}
	function retake() {
		console.info("Retaking the photo");
		show(null);
		setShot(null);
		start(cameraId, cameraId !== null);
	}
	if (phase === "off") return /* @__PURE__ */ u("div", {
		className: "camera off",
		role: "note",
		children: [
			/* @__PURE__ */ u("strong", { children: "The camera can't be used." }),
			" ",
			reason && WHY_NOT$1[reason],
			" Add a photo you already have below instead.",
			reason !== "insecure" && reason !== "unsupported" && /* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				onClick: retake,
				children: "Try the camera again"
			})
		]
	});
	const passed = shot?.upload?.problems?.length === 0;
	return /* @__PURE__ */ u("div", {
		className: "camera",
		children: [
			shot ? /* @__PURE__ */ u("img", {
				className: "camera-view",
				src: shot.url,
				alt: "The photo you took"
			}) : /* @__PURE__ */ u("div", {
				className: "camera-view",
				children: [
					/* @__PURE__ */ u("video", {
						ref: video,
						muted: true,
						playsInline: true,
						"aria-label": "The camera's live picture"
					}),
					/* @__PURE__ */ u("svg", {
						className: "outline",
						viewBox: "0 0 160 120",
						"aria-hidden": "true",
						children: [/* @__PURE__ */ u("ellipse", {
							cx: "80",
							cy: "48",
							rx: "25",
							ry: "33"
						}), /* @__PURE__ */ u("path", { d: "M30 120c4-24 22-34 50-34s46 10 50 34" })]
					}),
					phase === "counting" && /* @__PURE__ */ u("span", {
						className: "countdown",
						children: count
					}),
					phase === "starting" && /* @__PURE__ */ u("p", {
						className: "muted busy camera-note",
						children: "Asking for the camera…"
					})
				]
			}),
			!shot && cameras.length > 1 && /* @__PURE__ */ u("label", {
				className: "camera-choice",
				children: [
					"Camera",
					" ",
					/* @__PURE__ */ u("select", {
						value: cameraId ?? "",
						disabled: phase !== "live",
						onChange: (e) => switchCamera(e.currentTarget.value),
						children: cameras.map((c) => /* @__PURE__ */ u("option", {
							value: c.id,
							children: c.label
						}, c.id))
					})
				]
			}),
			grabFailed && phase === "live" && /* @__PURE__ */ u("p", {
				className: "error",
				children: grabFailed
			}),
			phase === "checking" && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Checking the photo…"
			}),
			shot?.upload && /* @__PURE__ */ u(Checks, {
				item: shot.upload,
				queue: -1
			}),
			shot?.upload && passed && /* @__PURE__ */ u("p", {
				className: "done",
				children: "Kept. Click Next, or Retake to try again."
			}),
			shot?.upload && shot.upload.problems?.length ? shot.stayed ? /* @__PURE__ */ u("p", {
				className: "error",
				children: "This photo could not be removed. It is still in Your photos below: remove it there, then Retake."
			}) : /* @__PURE__ */ u("p", {
				className: "muted",
				children: "Not kept. Retake to try again."
			}) : null,
			shot?.error && /* @__PURE__ */ u("p", {
				className: "error",
				children: shot.error
			}),
			/* @__PURE__ */ u("div", {
				className: "choices",
				children: [(phase === "live" || phase === "counting") && /* @__PURE__ */ u("button", {
					type: "button",
					disabled: phase === "counting",
					onClick: takePhoto,
					children: phase === "counting" ? `Taking in ${count}…` : "Take photo"
				}), phase === "taken" && /* @__PURE__ */ u("button", {
					type: "button",
					className: "secondary",
					onClick: retake,
					children: "Retake"
				})]
			})
		]
	});
}
var WHY_NOT = {
	insecure: "The browser allows the microphone only on a secure page (HTTPS) or on this computer (localhost), and this page is neither.",
	unsupported: "This browser can't record sound.",
	refused: "The browser wasn't allowed to use the microphone.",
	"no-microphone": "No microphone was found on this computer.",
	failed: "The microphone could not be started. It may be in use by another app."
};
var MICROPHONE = {
	echoCancellation: false,
	noiseSuppression: false,
	autoGainControl: false
};
var PASSAGES = [
	{
		name: "Voice 1",
		how: "Read each line, then pause about 1 second (one breath) before the next line.",
		minutes: "1½ minutes",
		say: /* @__PURE__ */ u(Script, {
			first: 1,
			lines: SCRIPT_1
		})
	},
	{
		name: "Voice 2",
		how: "Read each line, then pause about 1 second (one breath) before the next line.",
		minutes: "1½ minutes",
		say: /* @__PURE__ */ u(Script, {
			first: 11,
			lines: SCRIPT_2
		})
	},
	{
		name: "Voice 3",
		how: "Choose two or three questions and answer them out loud in your own words, as if chatting with a friend, for about 20 to 30 seconds each.",
		minutes: "1 minute",
		say: /* @__PURE__ */ u(Questions, { items: QUESTIONS_3 })
	}
];
function microphoneBlocked() {
	if (window.isSecureContext === false) return "insecure";
	if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") return "unsupported";
	return null;
}
function reasonOf(error) {
	const name = error?.name;
	if (name === "NotAllowedError" || name === "SecurityError") return "refused";
	if (name === "NotFoundError" || name === "OverconstrainedError") return "no-microphone";
	if (name === "NotSupportedError") return "unsupported";
	return "failed";
}
var TYPES = [
	"audio/webm;codecs=opus",
	"audio/webm",
	"audio/mp4",
	"audio/ogg;codecs=opus"
];
function recordingType() {
	return TYPES.find((t) => MediaRecorder.isTypeSupported?.(t)) ?? "";
}
function extension(type) {
	if (type.startsWith("audio/mp4")) return "m4a";
	if (type.startsWith("audio/ogg")) return "ogg";
	return "webm";
}
function clock(seconds) {
	const s = Math.floor(seconds);
	return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
function stopTracks(stream) {
	stream?.getTracks().forEach((t) => t.stop());
}
function report(r) {
	reportRecording(r).catch((e) => console.error("Could not log the microphone's use", e));
}
function VoiceRecorder(props) {
	const [phase, setPhase] = d("ready");
	const [reason, setReason] = d(null);
	const [passage, setPassage] = d(0);
	const [seconds, setSeconds] = d(0);
	const [level, setLevel] = d(0);
	const [made, setMade] = d(null);
	const [keptHere, setKeptHere] = d([]);
	const stream = A(null);
	const recorder = A(null);
	const audio = A(null);
	const ticking = A(void 0);
	const frame = A(void 0);
	const alive = A(true);
	const guard = useSettingGuard();
	function stopListening() {
		window.clearInterval(ticking.current);
		if (frame.current !== void 0) cancelAnimationFrame(frame.current);
		frame.current = void 0;
		audio.current?.close().catch(() => {});
		audio.current = null;
		stopTracks(stream.current);
		stream.current = null;
	}
	h(() => {
		alive.current = true;
		return () => {
			alive.current = false;
			if (recorder.current?.state === "recording") recorder.current.stop();
			stopListening();
		};
	}, []);
	const shown = A(null);
	function show(url) {
		if (shown.current && shown.current !== url) URL.revokeObjectURL(shown.current);
		shown.current = url;
	}
	h(() => () => show(null), []);
	function notUsed(why, error) {
		if (error) console.error(`Microphone not used (${why})`, error);
		else console.info(`Microphone not used (${why})`);
		report({
			made: false,
			reason: why
		});
		setReason(why);
		setPhase("off");
	}
	function meter(media) {
		if (typeof AudioContext === "undefined") return;
		try {
			const context = new AudioContext();
			const analyser = context.createAnalyser();
			analyser.fftSize = 1024;
			context.createMediaStreamSource(media).connect(analyser);
			audio.current = context;
			const samples = new Float32Array(analyser.fftSize);
			const draw = () => {
				analyser.getFloatTimeDomainData(samples);
				let peak = 0;
				for (const v of samples) peak = Math.max(peak, Math.abs(v));
				setLevel(peak);
				frame.current = requestAnimationFrame(draw);
			};
			draw();
		} catch (e) {
			console.warn("No level meter", e);
		}
	}
	async function record() {
		const blocked = microphoneBlocked();
		if (blocked) {
			notUsed(blocked);
			return;
		}
		show(null);
		setMade(null);
		setPhase("asking");
		const asked = performance.now();
		let media;
		try {
			media = await navigator.mediaDevices.getUserMedia({
				audio: MICROPHONE,
				video: false
			});
		} catch (e) {
			if (alive.current) notUsed(reasonOf(e), e);
			return;
		}
		if (!alive.current) {
			stopTracks(media);
			return;
		}
		stream.current = media;
		const type = recordingType();
		let rec;
		try {
			rec = new MediaRecorder(media, type ? { mimeType: type } : void 0);
		} catch (e) {
			stopListening();
			notUsed("unsupported", e);
			return;
		}
		const microphone = media.getAudioTracks?.()[0]?.label || "unnamed";
		console.info(`Microphone on in ${Math.round(performance.now() - asked)} ms: ${microphone}`);
		const chunks = [];
		rec.ondataavailable = (e) => {
			if (e.data.size > 0) chunks.push(e.data);
		};
		const started = performance.now();
		rec.onstop = () => {
			const length = (performance.now() - started) / 1e3;
			stopListening();
			if (alive.current) finish(new Blob(chunks, { type: rec.mimeType || type }), length);
		};
		try {
			rec.start(1e3);
		} catch (e) {
			stopListening();
			notUsed("failed", e);
			return;
		}
		recorder.current = rec;
		meter(media);
		setSeconds(0);
		ticking.current = window.setInterval(() => {
			const now = (performance.now() - started) / 1e3;
			setSeconds(now);
			if (now >= 600 && rec.state === "recording") {
				console.info(`Recording stopped at the 10-minute limit`);
				rec.stop();
			}
		}, 250);
		props.onChanging(true);
		console.info(`Recording ${PASSAGES[passage].name} (${rec.mimeType || type || "browser's type"})`);
		setPhase("recording");
	}
	function stop() {
		if (recorder.current?.state === "recording") recorder.current.stop();
	}
	async function finish(blob, length) {
		const format = blob.type || "unknown";
		report({
			made: true,
			seconds: Math.round(length * 10) / 10,
			format
		});
		console.info(`Recording made: ${length.toFixed(1)} s, ${format}`);
		const url = URL.createObjectURL(blob);
		show(url);
		setMade({
			url,
			upload: null,
			error: null
		});
		if (!await guard.confirm("Add the recording you made?")) {
			props.onChanging(false);
			setPhase("made");
			return;
		}
		setPhase("checking");
		const checking = performance.now();
		const name = `voice-${passage + 1}-${(/* @__PURE__ */ new Date()).toISOString().replace(/[:.]/g, "-")}.${extension(format)}`;
		try {
			const upload = await uploadFile("sounds", new File([blob], name, { type: format }));
			console.info(`Recording checked in ${Math.round(performance.now() - checking)} ms`);
			if (alive.current) setMade({
				url,
				upload,
				error: null
			});
			if (upload.problems?.length) {
				if (!await dropFailed(upload) && alive.current) setMade({
					url,
					upload,
					error: null,
					stayed: true
				});
			} else {
				setKeptHere((k) => k.includes(passage) ? k : [...k, passage]);
				props.onAdded();
			}
		} catch (e) {
			console.error("Recording refused", e);
			if (alive.current) setMade({
				url,
				upload: null,
				error: e.message
			});
		}
		props.onChanging(false);
		if (alive.current) setPhase("made");
	}
	async function dropFailed(upload) {
		try {
			await removeUpload("sounds", upload.id);
			console.info(`Recording failed its checks and was not kept: ${upload.problems?.join(" ")}`);
			return true;
		} catch (e) {
			console.error("Could not remove the recording that failed its checks", e);
			props.onAdded();
			return false;
		}
	}
	function goTo(to) {
		console.info(`Recording chosen: ${PASSAGES[to].name}`);
		show(null);
		setMade(null);
		setPassage(to);
		setPhase("ready");
	}
	if (phase === "off") return /* @__PURE__ */ u("div", {
		className: "recorder off",
		role: "note",
		children: [
			/* @__PURE__ */ u("strong", { children: "The microphone can't be used." }),
			" ",
			reason && WHY_NOT[reason],
			" Add recordings you already made below instead.",
			reason !== "insecure" && reason !== "unsupported" && /* @__PURE__ */ u("button", {
				type: "button",
				className: "secondary",
				onClick: () => void record(),
				children: "Try the microphone again"
			})
		]
	});
	const current = PASSAGES[passage];
	const kept = made?.upload?.problems?.length === 0;
	const failed = Boolean(made?.upload?.problems?.length);
	const busy = phase === "asking" || phase === "recording" || phase === "checking";
	return /* @__PURE__ */ u("div", {
		className: "recorder",
		children: [
			/* @__PURE__ */ u("div", {
				className: "passages",
				role: "group",
				"aria-label": "Recordings",
				children: [/* @__PURE__ */ u("span", {
					className: "muted",
					children: "Make them in any order:"
				}), PASSAGES.map((p, i) => /* @__PURE__ */ u("button", {
					type: "button",
					className: i === passage ? "current" : "secondary",
					"aria-pressed": i === passage,
					"aria-label": keptHere.includes(i) ? `${p.name} kept` : p.name,
					disabled: busy,
					onClick: () => goTo(i),
					children: [p.name, keptHere.includes(i) && " ✓"]
				}, p.name))]
			}),
			/* @__PURE__ */ u("h3", { children: [
				"Recording ",
				passage + 1,
				" of ",
				PASSAGES.length,
				": ",
				current.name
			] }),
			/* @__PURE__ */ u("p", {
				className: "muted",
				children: [
					current.how,
					" About ",
					current.minutes,
					"."
				]
			}),
			current.say,
			phase === "recording" && /* @__PURE__ */ u("div", {
				className: "recording",
				role: "status",
				children: [
					/* @__PURE__ */ u("span", {
						className: "rec-dot",
						"aria-hidden": "true"
					}),
					/* @__PURE__ */ u("span", {
						className: "timer",
						children: clock(seconds)
					}),
					/* @__PURE__ */ u("span", {
						className: "level",
						"aria-label": "Sound level",
						children: /* @__PURE__ */ u("span", { style: { width: `${Math.min(100, Math.round(level * 100))}%` } })
					})
				]
			}),
			phase === "asking" && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Asking for the microphone…"
			}),
			phase === "checking" && /* @__PURE__ */ u("p", {
				className: "muted busy",
				children: "Checking the recording…"
			}),
			made && (phase === "made" || phase === "checking") && /* @__PURE__ */ u("audio", {
				controls: true,
				src: made.url,
				"aria-label": "The recording you made"
			}),
			made?.upload && /* @__PURE__ */ u(Checks, {
				item: made.upload,
				queue: -1
			}),
			kept && /* @__PURE__ */ u("p", {
				className: "done",
				children: [
					"Kept.",
					" ",
					passage + 1 < PASSAGES.length ? "Go on to the next recording, or click Next if you have enough." : "That's all three: click Next."
				]
			}),
			failed && (made?.stayed ? /* @__PURE__ */ u("p", {
				className: "error",
				children: "This recording could not be removed. It is still in Your recordings below: remove it there, then Record again."
			}) : /* @__PURE__ */ u("p", {
				className: "muted",
				children: "Not kept. Record again to try again."
			})),
			made?.error && /* @__PURE__ */ u("p", {
				className: "error",
				children: made.error
			}),
			/* @__PURE__ */ u("div", {
				className: "choices",
				children: [
					phase === "ready" && /* @__PURE__ */ u("button", {
						type: "button",
						onClick: () => void record(),
						children: "Start recording"
					}),
					phase === "recording" && /* @__PURE__ */ u("button", {
						type: "button",
						onClick: stop,
						children: "Stop"
					}),
					phase === "made" && /* @__PURE__ */ u("button", {
						type: "button",
						className: kept ? "secondary" : void 0,
						onClick: () => void record(),
						children: "Record again"
					}),
					phase === "made" && kept && passage + 1 < PASSAGES.length && /* @__PURE__ */ u("button", {
						type: "button",
						onClick: () => goTo(passage + 1),
						children: ["Next recording: ", PASSAGES[passage + 1].name]
					})
				]
			})
		]
	});
}
//#endregion
//#region src/wizard.tsx
var HELP = {
	start: "Before you begin",
	photo: "How to take the photos",
	voice: "Record your voice",
	accent: "If something goes wrong",
	prepare: "If something goes wrong",
	review: "If something goes wrong"
};
var STEP_TITLES = {
	start: "Before you start",
	photo: "Your photo",
	voice: "Your voice",
	accent: "Accent",
	prepare: "Prepare the video",
	review: "Watch the sample video"
};
var BACK_STEP = {
	photos: "photo",
	sounds: "voice",
	accent: "accent"
};
function nextStep(step, by) {
	const i = WIZARD_STEPS.indexOf(step) + by;
	return WIZARD_STEPS[Math.min(Math.max(i, 0), WIZARD_STEPS.length - 1)];
}
function WizardPage(props) {
	const [step, setStep] = d(null);
	const opened = A(performance.now());
	const [ready, setReady] = d(false);
	const [failed, setFailed] = d(null);
	const [changes, setChanges] = d(0);
	const changed = () => setChanges((n) => n + 1);
	const [preparing, setPreparing] = d(false);
	const [pending, setPending] = d(false);
	const [notice, setNotice] = d(null);
	const [moving, setMoving] = d(false);
	const movingNow = A(false);
	const leaveDialog = useLeaveGuard(pending, "The chat keeps the person and voice it has now.");
	const stopGuard = usePrepareStopGuard(changed);
	h(() => {
		const started = performance.now();
		getWizardStep().then((saved) => {
			const first = props.consented ? saved : "start";
			console.info(`Wizard opened at ${first} (read in ${Math.round(performance.now() - started)} ms)`);
			opened.current = performance.now();
			setStep(first);
		}).catch((e) => {
			console.error("Could not read the wizard's step; starting at the beginning", e);
			setStep("start");
		});
	}, []);
	async function go(to, why = null) {
		if (step === null || movingNow.current) return;
		movingNow.current = true;
		setMoving(true);
		console.info(`Wizard step: ${to} (${Math.round((performance.now() - opened.current) / 1e3)} s on ${step})`);
		setFailed(null);
		try {
			await saveWizardStep(to);
		} catch (e) {
			console.error(`Could not save the wizard's step (${to})`, e);
		}
		opened.current = performance.now();
		setReady(false);
		setNotice(why);
		setStep(to);
		movingNow.current = false;
		setMoving(false);
		window.scrollTo?.({ top: 0 });
	}
	if (step === null) return /* @__PURE__ */ u("p", {
		className: "muted busy",
		children: "Loading…"
	});
	const index = WIZARD_STEPS.indexOf(step);
	const last = index === WIZARD_STEPS.length - 1;
	let body;
	switch (step) {
		case "start":
			body = /* @__PURE__ */ u(StartStep, {
				consented: props.consented,
				onReady: setReady,
				onConsented: props.onConsented,
				onFailed: setFailed
			});
			break;
		case "photo":
			body = /* @__PURE__ */ u(PhotoStep, {
				notice,
				onReady: setReady,
				onChange: changed
			});
			break;
		case "voice":
			body = /* @__PURE__ */ u(VoiceStep, {
				notice,
				onReady: setReady,
				onChange: changed
			});
			break;
		case "accent":
			body = /* @__PURE__ */ u(AccentStep, {
				notice,
				preparing,
				onReady: setReady,
				onChange: changed
			});
			break;
		case "prepare":
			body = /* @__PURE__ */ u(PrepareSection, {
				changes,
				onRunning: setPreparing,
				onBack: (to) => void go(BACK_STEP[to]),
				onStopped: stopGuard.onStopped,
				wizard: { onDone: setReady }
			});
			break;
		case "review": body = /* @__PURE__ */ u(ReviewStep, {
			onBack: (to, why) => void go(BACK_STEP[to], why),
			onPending: setPending
		});
	}
	return /* @__PURE__ */ u(SettingGuard.Provider, {
		value: stopGuard.guard,
		children: /* @__PURE__ */ u("div", {
			className: "host-page wizard",
			children: [
				/* @__PURE__ */ u("h1", { children: "Set up with your own photo and voice" }),
				/* @__PURE__ */ u("ol", {
					className: "wizard-steps",
					"aria-label": "Steps",
					children: WIZARD_STEPS.map((s, i) => /* @__PURE__ */ u("li", {
						className: i === index ? "current" : i < index ? "done" : void 0,
						"aria-current": i === index ? "step" : void 0,
						children: STEP_TITLES[s]
					}, s))
				}),
				/* @__PURE__ */ u("div", {
					className: "step-row",
					children: [/* @__PURE__ */ u("p", {
						className: "step-of",
						children: [
							"Step ",
							index + 1,
							" of ",
							WIZARD_STEPS.length
						]
					}), /* @__PURE__ */ u("a", {
						className: "need-help",
						href: "#/guide",
						target: "_blank",
						rel: "noopener",
						onClick: () => guideAt(HELP[step]),
						children: "Need help?"
					})]
				}),
				body,
				failed && /* @__PURE__ */ u("p", {
					className: "error",
					children: failed
				}),
				/* @__PURE__ */ u("div", {
					className: "wizard-nav",
					children: [/* @__PURE__ */ u("button", {
						type: "button",
						className: "secondary",
						disabled: index === 0 || moving,
						onClick: () => void go(nextStep(step, -1)),
						children: "Back"
					}), !last && /* @__PURE__ */ u("button", {
						type: "button",
						disabled: !ready || moving,
						onClick: () => void go(nextStep(step, 1)),
						children: "Next"
					})]
				}),
				/* @__PURE__ */ u("p", {
					className: "muted",
					children: [
						"Prefer everything on one page? ",
						/* @__PURE__ */ u("a", {
							href: "#/setup",
							children: "Open the Setup page"
						}),
						"."
					]
				}),
				leaveDialog,
				stopGuard.dialog
			]
		})
	});
}
function StartStep(props) {
	const [checked, setChecked] = d(props.consented);
	const [saving, setSaving] = d(false);
	h(() => props.onReady(props.consented), [props.consented]);
	async function agree(yes) {
		setChecked(yes);
		if (!yes || props.consented) return;
		setSaving(true);
		props.onFailed(null);
		try {
			await confirmConsent();
			console.info("Consent confirmed in the wizard");
			props.onConsented();
		} catch (e) {
			console.error("Could not save consent from the wizard", e);
			props.onFailed("Could not save your answer. Please try again.");
			setChecked(false);
		}
		setSaving(false);
	}
	return /* @__PURE__ */ u("section", {
		className: "panel",
		children: [
			/* @__PURE__ */ u("h2", { children: STEP_TITLES.start }),
			/* @__PURE__ */ u("p", { children: "You will need:" }),
			/* @__PURE__ */ u("ul", {
				className: "needs",
				children: [
					/* @__PURE__ */ u("li", { children: "A clear photo of your face, head and shoulders, looking at the camera." }),
					/* @__PURE__ */ u("li", { children: "A few minutes of your voice, reading aloud in a quiet room. This is optional: without it, a ready-made voice speaks." }),
					/* @__PURE__ */ u("li", { children: "About 20 minutes the first time, while the app prepares the video." })
				]
			}),
			/* @__PURE__ */ u("p", { children: "Only use images you have the right to use. Ideally, use your own picture." }),
			/* @__PURE__ */ u("label", {
				className: "check",
				children: [
					/* @__PURE__ */ u("input", {
						type: "checkbox",
						checked,
						disabled: props.consented || saving,
						onChange: (e) => void agree(e.currentTarget.checked)
					}),
					" ",
					"I have the right to use the photos and recording that will be used by the app."
				]
			})
		]
	});
}
function PhotoStep(props) {
	const [changes, setChanges] = d(0);
	const [taken, setTaken] = d(0);
	function changing(busy) {
		props.onReady(false);
		if (!busy) setChanges((n) => n + 1);
	}
	h(() => {
		let newest = true;
		getPhotoChoice().then((c) => {
			if (newest) props.onReady(Boolean(c.id));
		}).catch((e) => console.error("Could not read the chosen photo", e));
		return () => {
			newest = false;
		};
	}, [changes]);
	return /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("section", {
		className: "panel",
		children: [
			/* @__PURE__ */ u("h2", { children: STEP_TITLES.photo }),
			props.notice && /* @__PURE__ */ u("p", {
				className: "notice",
				children: props.notice
			}),
			/* @__PURE__ */ u("ul", {
				className: "tips",
				children: [
					/* @__PURE__ */ u("li", { children: "Face the camera, with your head and shoulders inside the outline." }),
					/* @__PURE__ */ u("li", { children: "Use soft, even light from the front, with a plain background." }),
					/* @__PURE__ */ u("li", { children: "Keep a neutral face with your mouth closed." })
				]
			}),
			/* @__PURE__ */ u(CameraPhoto, {
				onChanging: changing,
				onAdded: () => {
					setTaken((n) => n + 1);
					props.onChange();
				}
			})
		]
	}), /* @__PURE__ */ u(UploadSection, {
		kind: "photos",
		step: null,
		title: "Your photos",
		button: "Add a photo file",
		hint: "The photos you took, and any you add as files (JPG, PNG or HEIC). Next is ready once one passes the checks.",
		accept: "image/jpeg,image/png,image/heic,.heic",
		notice: null,
		onChanging: changing,
		onChange: () => {
			props.onReady(false);
			setChanges((n) => n + 1);
			props.onChange();
		}
	}, taken)] });
}
function VoiceStep(props) {
	h(() => props.onReady(true), []);
	const [made, setMade] = d(0);
	return /* @__PURE__ */ u(S, { children: [/* @__PURE__ */ u("section", {
		className: "panel",
		children: [
			/* @__PURE__ */ u("h2", { children: "Record your voice" }),
			props.notice && /* @__PURE__ */ u("p", {
				className: "notice",
				children: props.notice
			}),
			/* @__PURE__ */ u("ul", {
				className: "tips",
				children: [
					/* @__PURE__ */ u("li", { children: "Record in a quiet room, about a hand's width from the microphone." }),
					/* @__PURE__ */ u("li", { children: "Read aloud in your normal voice." }),
					/* @__PURE__ */ u("li", { children: "Only your voice: no music, television or other people." })
				]
			}),
			/* @__PURE__ */ u(VoiceRecorder, {
				onChanging: (busy) => props.onReady(!busy),
				onAdded: () => {
					setMade((n) => n + 1);
					props.onChange();
				}
			})
		]
	}), /* @__PURE__ */ u(UploadSection, {
		kind: "sounds",
		step: null,
		title: "Your recordings",
		button: "Add a recording file",
		hint: "The recordings you made, and any you add as files (WAV, M4A or MP3, up to 10 minutes each). Optional: without them, a ready-made voice speaks.",
		accept: "audio/*,.m4a,.wav,.mp3",
		notice: null,
		onChange: props.onChange
	}, made)] });
}
function AccentStep(props) {
	h(() => props.onReady(true), []);
	return /* @__PURE__ */ u(AccentSection, {
		onChange: props.onChange,
		preparing: props.preparing,
		notice: props.notice,
		numbered: false
	});
}
var BACK_NOTICE = {
	photos: "You rejected the image. Add a new photo and remove the ones you don't want.",
	sounds: "You rejected the voice. Add new recordings and remove the ones you don't want.",
	accent: "Choose another accent."
};
function ReviewStep(props) {
	const [status, setStatus] = d(null);
	h(() => {
		getPrepare().then(setStatus).catch((e) => console.error("Could not read the sample video", e));
	}, []);
	if (status === null) return /* @__PURE__ */ u("p", {
		className: "muted busy",
		children: "Loading…"
	});
	if (status.state !== "done") return /* @__PURE__ */ u("section", {
		className: "panel",
		children: [/* @__PURE__ */ u("h2", { children: STEP_TITLES.review }), /* @__PURE__ */ u("p", {
			className: "notice",
			children: "The sample video isn't ready. Go Back to prepare it."
		})]
	});
	return /* @__PURE__ */ u("section", {
		className: "panel sample-video",
		children: [
			/* @__PURE__ */ u("h2", { children: STEP_TITLES.review }),
			/* @__PURE__ */ u("video", {
				controls: true,
				preload: "metadata",
				src: clipUrl("sample", status),
				"aria-label": "Sample video"
			}),
			/* @__PURE__ */ u(ReviewChoices, {
				sample: status.finished_at,
				onBack: (to) => props.onBack(to, BACK_NOTICE[to]),
				onPending: props.onPending
			})
		]
	});
}
//#endregion
//#region src/App.tsx
var NAV = [
	{
		page: "home",
		href: "#/",
		label: "Home",
		views: ["host"]
	},
	{
		page: "setup",
		href: "#/setup",
		label: "Setup",
		views: ["host"]
	},
	{
		page: "chat",
		href: "#/chat",
		label: "Chat",
		views: ["host", "participant"]
	},
	{
		page: "content",
		href: "#/content",
		label: "Manage Content",
		views: ["host"]
	}
];
function current(page, view) {
	if (page === "guide" || page === "start-now" || page === "avatar-voice" || page === "wizard") return "setup";
	if (page === "wiki" || page === "wiki-page") return view === "host" ? "content" : void 0;
	return page;
}
function App() {
	return /* @__PURE__ */ u(SettingsProvider, { children: /* @__PURE__ */ u(AdminProvider, { children: /* @__PURE__ */ u(HostProvider, { children: /* @__PURE__ */ u(SettingsAccessProvider, { children: /* @__PURE__ */ u(Shell, {}) }) }) }) });
}
function Shell() {
	const hash = useHash();
	const view = useSettings().view;
	const participant = view === "participant";
	const settingsLoaded = useSettingsLoaded();
	const host = settingsLoaded && !participant;
	const [consented, setConsented] = d(null);
	h(() => {
		getConsent().then((c) => setConsented(c.agreed)).catch((e) => {
			console.error("Could not load consent", e);
			setConsented(false);
		});
	}, []);
	const defaultPerson = useDefaultPerson(hash, host);
	const hostSession = useHost().session;
	const visitor = hostSession?.signed_in !== true;
	const settingsShown = useSettingsShown();
	const { use: customUse, fresh } = useCustomUseOf(hash, hostSession?.signed_in);
	const route = consented === null || !settingsLoaded || hostSession === null || customUse === null ? null : resolve(hash, consented, participant, visitor, fresh ? customUse : ALLOWED);
	h(() => {
		if (route?.redirect && route.redirect !== window.location.hash) window.location.replace(route.redirect);
	}, [route?.redirect]);
	const landing = A(pageFor(window.location.hash) === "home");
	if (route && route.page !== "home") landing.current = false;
	useAdminActivity(route?.page === "admin" || route?.page === "settings");
	const header = useHeaderHeight();
	const back = A(null);
	if (route && route.page !== "settings" && !route.redirect) back.current = hash || "#/";
	let content = /* @__PURE__ */ u("p", { children: "Loading…" });
	if (route) content = {
		home: /* @__PURE__ */ u(HomePage, {
			consented: consented === true,
			landing: landing.current
		}),
		consent: /* @__PURE__ */ u(ConsentPage, { onConfirmed: () => {
			setConsented(true);
			if (hash !== "#/consent/own") {
				window.location.hash = "#/setup";
				return;
			}
			ownAfterConsent().catch((e) => {
				console.error("Could not switch to your own photo and voice", e);
				window.location.hash = "#/setup";
			});
		} }),
		setup: /* @__PURE__ */ u(SetupPage, { change: setupTarget(hash) }),
		wizard: /* @__PURE__ */ u(WizardPage, {
			consented: consented === true,
			onConsented: () => setConsented(true)
		}),
		"start-now": /* @__PURE__ */ u(StartNowPage, {}),
		"avatar-voice": /* @__PURE__ */ u(AvatarVoicePage, {}),
		chat: /* @__PURE__ */ u(ChatPage, {}),
		content: /* @__PURE__ */ u(ContentPage, {}),
		guide: /* @__PURE__ */ u(GuidePage, {}),
		wiki: /* @__PURE__ */ u(WikiPage, { pdf: wikiTarget(hash).pdf }),
		"wiki-page": /* @__PURE__ */ u(WikiDetailPage, { entry: wikiTarget(hash).entry ?? "" }),
		settings: !settingsShown ? settingsShown === null ? /* @__PURE__ */ u("p", { children: "Loading…" }) : /* @__PURE__ */ u(NotFoundPage, {}) : /* @__PURE__ */ u(SettingsPage, {
			back: back.current ?? (participant ? "#/chat" : "#/"),
			onDataDeleted: () => setConsented(false)
		}),
		admin: /* @__PURE__ */ u(AdminPage, { section: adminTarget(hash) }),
		"host-sign-up": /* @__PURE__ */ u(HostAccountPage, { kind: "up" }),
		"host-sign-in": /* @__PURE__ */ u(HostAccountPage, { kind: "in" }),
		"host-only": /* @__PURE__ */ u(HostOnlyPage, {}),
		resources: /* @__PURE__ */ u(ResourcesPage, {}),
		customization: /* @__PURE__ */ u(CustomizationPage, {}),
		"not-found": /* @__PURE__ */ u(NotFoundPage, {})
	}[route.page];
	return /* @__PURE__ */ u(S, { children: [
		/* @__PURE__ */ u("header", {
			ref: header,
			children: [
				/* @__PURE__ */ u("a", {
					className: "brand",
					href: host ? "#/" : "#/chat",
					children: [/* @__PURE__ */ u(Mark, {}), "ImageSkinForLLM"]
				}),
				/* @__PURE__ */ u("nav", { children: NAV.filter((item) => settingsLoaded && item.views.includes(view)).map((item) => /* @__PURE__ */ u("a", {
					href: item.page === "setup" ? setupLink(consented === true, defaultPerson, customUse?.image !== false) : item.href,
					className: current(route?.page, view) === item.page ? "current" : void 0,
					children: item.label
				}, item.page)) }),
				/* @__PURE__ */ u("span", {
					className: "header-end",
					children: [
						/* @__PURE__ */ u(HostLinks, { page: route?.page }),
						/* @__PURE__ */ u(AdminLink, { current: route?.page === "admin" }),
						settingsLoaded && settingsShown && /* @__PURE__ */ u(SettingsLink, { current: route?.page === "settings" })
					]
				})
			]
		}),
		/* @__PURE__ */ u("main", { children: [/* @__PURE__ */ u(AdminEndedNotice, {}), /* @__PURE__ */ u(CustomUseProvider, {
			value: customUse ?? ALLOWED,
			children: content
		})] }),
		/* @__PURE__ */ u("footer", { children: "Photos and recordings stay on the computer that runs this app." })
	] });
}
function useDefaultPerson(hash, host) {
	const [chosen, setChosen] = d(false);
	h(() => {
		if (!host) return;
		let active = true;
		const started = performance.now();
		getStartNow().then((s) => {
			if (!active) return;
			const yes = Boolean(s.chosen);
			console.info(`Top bar Setup link: ${yes ? "Start now (a ready-made avatar is in use)" : "setup"} (read in ${Math.round(performance.now() - started)} ms)`);
			setChosen(yes);
		}).catch((e) => console.error("Could not read the default person for the top bar", e));
		return () => {
			active = false;
		};
	}, [hash, host]);
	return chosen;
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

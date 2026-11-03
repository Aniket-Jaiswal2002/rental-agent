// Push-to-talk -> /stt (Groq Whisper) -> /chat (agent) -> browser speechSynthesis, plus the live memory panel.
const $ = (id) => document.getElementById(id);
let sessionId = crypto.randomUUID();
let recorder = null, chunks = [], busy = false;
let lastProfile = {};

const LABELS = {
  budget_max: "Budget", areas: "Areas", bhk: "BHK", move_in_date: "Move-in", commute_destination: "Commute to",
  furnishing: "Furnishing", pets: "Pets", tenant_type: "Tenant type", parking: "Parking",
};
const REQUIRED = ["budget_max", "areas", "bhk", "move_in_date", "commute_destination"];
const EMPTY_STATE = { profile: {}, missing_required: REQUIRED, confirmed: false, awaiting_confirmation: false, changelog: [] };
const inr = (n) => "₹" + Number(n).toLocaleString("en-IN");

function fmt(field, v) {
  if (v === null || v === undefined || (Array.isArray(v) && !v.length)) return null;
  if (field === "budget_max") return inr(v);
  if (typeof v === "boolean") return v ? "yes" : "no";
  return Array.isArray(v) ? v.join(", ") : String(v);
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function status(text) { $("status").textContent = text; }

function addMessage(role, text, r) {
  $("transcript").querySelector(".hint")?.remove();
  const div = el("div", "msg " + role);
  for (const u of r?.updates || []) div.append(el("span", "update", "✎ " + u));
  div.append(document.createTextNode(text));
  if (r?.shortlist?.length) {
    const cards = el("div", "cards");
    for (const c of r.shortlist) {
      const card = el("div", "card");
      const top = el("div", "top");
      top.append(el("b", "", c.title), el("span", "rent", inr(c.rent) + "/mo"));
      card.append(top,
        el("div", "facts", `Deposit ${inr(c.deposit)} · ${c.furnishing} · available ${c.available_from} · ` +
          `${c.distance_cyber_city_km} km to Cyber City · ${c.distance_golf_course_road_km} km to Golf Course Rd`),
        el("div", "why", c.tradeoff),
        el("div", "id", `${c.id} · pets ${c.pets_allowed ? "ok" : "no"} · ${c.tenant_preference} · parking ${c.parking ? "yes" : "no"}`));
      cards.append(card);
    }
    div.append(cards, el("span", "via", "Prices, areas and facts above come straight from the listings data, not the model."));
  }
  if (r?.no_match) div.append(el("div", "nomatch", "No listing matches every requirement, so nothing is shown."));
  $("transcript").append(div);
  $("transcript").scrollTop = $("transcript").scrollHeight;
}

function renderMemory(state, askingFor = []) {
  const dl = $("profile"); dl.innerHTML = "";
  for (const [field, label] of Object.entries(LABELS)) {
    const value = fmt(field, state.profile[field]);
    const req = REQUIRED.includes(field);
    const dd = el("dd", value === null && req ? "missing" : "", value ?? (req ? "missing" : "—"));
    if (value !== null && JSON.stringify(lastProfile[field]) !== JSON.stringify(state.profile[field])) {
      dd.classList.add("flash");
      requestAnimationFrame(() => requestAnimationFrame(() => dd.classList.remove("flash")));
    }
    dl.append(el("dt", "", label + (req ? " *" : "")), dd);
  }
  lastProfile = state.profile;

  const stage = $("stage");
  stage.className = "stage" + (state.confirmed ? " confirmed" : "");
  stage.textContent = state.confirmed ? "✓ Confirmed by renter: searching on this profile" :
    state.awaiting_confirmation ? "Read back to renter, waiting for a yes" :
    state.missing_required.length ? `Collecting: ${state.missing_required.length} required field(s) missing` : "Profile complete";

  const asking = $("asking"); asking.innerHTML = "";
  if (askingFor.length) {
    asking.append("Agent is asking for ");
    for (const f of askingFor) asking.append(el("span", "chip", LABELS[f] || f));
  }

  const ol = $("changelog"); ol.innerHTML = "";
  for (const c of state.changelog.slice(-8).reverse()) {
    const li = el("li", "", `turn ${c.turn}: ${LABELS[c.field]} ${fmt(c.field, c.old) ?? "—"} → ${fmt(c.field, c.new) ?? "—"}`);
    if (c.kind === "correction") li.append(el("span", "kind", "correction"));
    ol.append(li);
  }
  if (!state.changelog.length) ol.append(el("li", "", "nothing yet"));
}

let latency = {};
function renderLatency() {
  const box = $("latency"); box.innerHTML = "";
  if (!Object.keys(latency).length) return;
  const ms = (v) => (v === null || v === undefined ? "–" : Math.round(v) + " ms");
  const part = (label, value, cls = "") => { const s = el("span", cls); s.append(label + " ", el("b", "", value)); box.append(s); };
  const spoken = (latency.stt_ms || 0) + (latency.total_ms || 0) - (latency.wait_ms || 0) + (latency.tts_ms || 0);
  part("STT", ms(latency.stt_ms));
  part("model", `${ms(latency.llm_ms)} · ${latency.llm_calls ?? 0} call${latency.llm_calls === 1 ? "" : "s"}`);
  part("tools", ms(latency.tool_ms));
  part("TTS start", ms(latency.tts_ms));
  part("total", ms(spoken));
  if (latency.wait_ms > 1) part("quota wait (excluded)", ms(latency.wait_ms), "wait");
}

function pickVoice() {
  const voices = speechSynthesis.getVoices();
  return voices.find((v) => v.lang === "en-IN") || voices.find((v) => v.lang.startsWith("en")) || null;
}

function speak(text, turn) {
  if (!("speechSynthesis" in window) || !text) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  const voice = pickVoice(); if (voice) u.voice = voice;
  const t0 = performance.now(); let started = 0;
  u.onstart = () => { started = performance.now(); latency.tts_ms = started - t0; renderLatency(); };
  u.onend = () => {
    if (!started) return;
    fetch("/latency/tts", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, turn, tts_ms: started - t0, speech_ms: performance.now() - started }) });
  };
  speechSynthesis.speak(u);
}

async function sendText(text, sttMs = null) {
  if (!text.trim()) { status("Didn't catch that. Try again."); return; }
  addMessage("user", text);
  status("Thinking…");
  const res = await fetch("/chat", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, text, stt_ms: sttMs }) });
  if (!res.ok) { status(`Error ${res.status}: ${(await res.json()).detail}`); return; }
  const r = await res.json();
  addMessage("agent", r.reply, r);
  renderMemory(r.state, r.asking_for);
  latency = { ...r.timings, tts_ms: null }; renderLatency();
  status("");
  speak([...r.updates, r.reply].join(" "), r.turn);
}

function setPtt(recording) {
  $("ptt").classList.toggle("recording", recording);
  $("ptt-label").textContent = recording ? "Listening… release to send" : "Hold to talk";
}

async function startRecording() {
  if (busy || recorder) return;
  speechSynthesis.cancel(); // barge-in: stop the agent talking
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.start();
    setPtt(true);
  } catch (e) {
    status("Microphone unavailable: " + e.message + ". You can type instead.");
  }
}

async function stopRecording() {
  if (!recorder) return;
  const rec = recorder; recorder = null;
  setPtt(false);
  await new Promise((resolve) => { rec.onstop = resolve; rec.stop(); });
  rec.stream.getTracks().forEach((t) => t.stop());
  const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
  if (blob.size < 2000) { status("Too short. Hold the button while you speak."); return; }
  busy = true; $("ptt").disabled = true;
  try {
    status("Transcribing…");
    const form = new FormData(); form.append("audio", blob, "speech.webm");
    const res = await fetch("/stt", { method: "POST", body: form });
    if (!res.ok) { status(`Speech-to-text error ${res.status}: ${(await res.json()).detail}`); return; }
    const { text, stt_ms } = await res.json();
    await sendText(text, stt_ms);
  } finally { busy = false; $("ptt").disabled = false; }
}

const ptt = $("ptt");
ptt.addEventListener("pointerdown", (e) => { e.preventDefault(); startRecording(); });
ptt.addEventListener("pointerup", stopRecording);
ptt.addEventListener("pointerleave", stopRecording);
document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && !e.repeat && document.activeElement !== $("text")) { e.preventDefault(); startRecording(); }
});
document.addEventListener("keyup", (e) => { if (e.code === "Space" && document.activeElement !== $("text")) stopRecording(); });

$("textform").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("text").value; $("text").value = "";
  if (busy) return;
  busy = true; try { await sendText(text); } finally { busy = false; }
});
$("reset").addEventListener("click", async () => {
  await fetch(`/reset/${sessionId}`, { method: "POST" });
  location.reload();
});

fetch("/config").then((r) => r.json()).then((c) => {
  if (c.fake_llm) { $("mode").hidden = false; $("mode").textContent = "FAKE_LLM: canned replies, no API calls"; }
}).catch(() => {});
renderMemory(EMPTY_STATE);
if ("speechSynthesis" in window) speechSynthesis.getVoices(); // warm the voice list

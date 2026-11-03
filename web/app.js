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

function fmt(field, v) {
  if (v === null || v === undefined || (Array.isArray(v) && !v.length)) return null;
  if (field === "budget_max") return "₹" + Number(v).toLocaleString("en-IN");
  if (typeof v === "boolean") return v ? "yes" : "no";
  return Array.isArray(v) ? v.join(", ") : String(v);
}

function status(text) { $("status").textContent = text; }

function addMessage(role, text, extra) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  if (extra?.updates) for (const u of extra.updates) {
    const s = document.createElement("span"); s.className = "update"; s.textContent = u; div.append(s);
  }
  div.append(document.createTextNode(text));
  for (const c of extra?.shortlist || []) {
    const card = document.createElement("div"); card.className = "card";
    const title = document.createElement("b"); title.textContent = `${c.id} · ${c.title}`;
    const facts = document.createElement("div"); facts.className = "facts";
    facts.textContent = `₹${c.rent.toLocaleString("en-IN")}/mo · deposit ₹${c.deposit.toLocaleString("en-IN")} · ` +
      `${c.furnishing} · from ${c.available_from} · ${c.distance_cyber_city_km} km to Cyber City`;
    const why = document.createElement("div"); why.textContent = c.tradeoff;
    card.append(title, facts, why); div.append(card);
  }
  $("transcript").append(div);
  $("transcript").scrollTop = $("transcript").scrollHeight;
}

function renderMemory(state) {
  const dl = $("profile"); dl.innerHTML = "";
  for (const [field, label] of Object.entries(LABELS)) {
    const value = fmt(field, state.profile[field]);
    const dt = document.createElement("dt"); dt.textContent = label + (REQUIRED.includes(field) ? " *" : "");
    const dd = document.createElement("dd");
    dd.textContent = value ?? (REQUIRED.includes(field) ? "missing" : "—");
    if (value === null && REQUIRED.includes(field)) dd.className = "missing";
    if (JSON.stringify(lastProfile[field]) !== JSON.stringify(state.profile[field]) && value !== null) {
      dd.classList.add("flash"); setTimeout(() => dd.classList.remove("flash"), 1500);
    }
    dl.append(dt, dd);
  }
  lastProfile = state.profile;
  $("flags").textContent = state.confirmed ? "✓ Confirmed by renter" :
    state.awaiting_confirmation ? "Waiting for renter to confirm the read-back" :
    state.missing_required.length ? `Missing: ${state.missing_required.map((f) => LABELS[f]).join(", ")}` : "";
  const ol = $("changelog"); ol.innerHTML = "";
  for (const c of state.changelog.slice(-8)) {
    const li = document.createElement("li");
    li.textContent = `turn ${c.turn}: ${LABELS[c.field]} ${fmt(c.field, c.old) ?? "—"} → ${fmt(c.field, c.new) ?? "—"}` +
      (c.kind === "correction" ? " (correction)" : "");
    ol.append(li);
  }
}

let latency = {};
function renderLatency() {
  const ms = (v) => (v === null || v === undefined ? "–" : Math.round(v) + "ms");
  const total = (latency.stt_ms || 0) + (latency.total_ms || 0) + (latency.tts_ms || 0);
  $("latency").textContent = `last turn  STT ${ms(latency.stt_ms)} · LLM ${ms(latency.llm_ms)} (${latency.llm_calls ?? 0} calls) · ` +
    `tools ${ms(latency.tool_ms)} · TTS start ${ms(latency.tts_ms)} · total ${ms(total)}`;
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
  if (!text.trim()) { status("Didn't catch that — try again."); return; }
  addMessage("user", text);
  status("Thinking…");
  const res = await fetch("/chat", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, text, stt_ms: sttMs }) });
  if (!res.ok) { status(`Error ${res.status}: ${(await res.json()).detail}`); return; }
  const r = await res.json();
  addMessage("agent", r.reply, r);
  renderMemory(r.state);
  latency = { ...r.timings, tts_ms: null }; renderLatency();
  status("");
  speak([...r.updates, r.reply].join(" "), r.turn);
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
    $("ptt").classList.add("recording"); $("ptt").textContent = "Listening… release to send";
  } catch (e) {
    status("Microphone unavailable: " + e.message + ". You can type instead.");
  }
}

async function stopRecording() {
  if (!recorder) return;
  const rec = recorder; recorder = null;
  $("ptt").classList.remove("recording"); $("ptt").textContent = "Hold to talk";
  await new Promise((resolve) => { rec.onstop = resolve; rec.stop(); });
  rec.stream.getTracks().forEach((t) => t.stop());
  const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
  if (blob.size < 2000) { status("Too short — hold the button while you speak."); return; }
  busy = true;
  try {
    status("Transcribing…");
    const form = new FormData(); form.append("audio", blob, "speech.webm");
    const res = await fetch("/stt", { method: "POST", body: form });
    if (!res.ok) { status(`Speech-to-text error ${res.status}: ${(await res.json()).detail}`); return; }
    const { text, stt_ms } = await res.json();
    await sendText(text, stt_ms);
  } finally { busy = false; }
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
  sessionId = crypto.randomUUID(); lastProfile = {};
  $("transcript").innerHTML = ""; $("latency").textContent = ""; status("");
  renderMemory({ profile: {}, missing_required: REQUIRED, confirmed: false, awaiting_confirmation: false, changelog: [] });
});

renderMemory({ profile: {}, missing_required: REQUIRED, confirmed: false, awaiting_confirmation: false, changelog: [] });
speechSynthesis?.getVoices(); // warm the voice list

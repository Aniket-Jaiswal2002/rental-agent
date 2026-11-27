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

// One shortlist card. Every value comes from the server's rendered listing; the title
// "{bhk} BHK, {sector} ({area})" is only split for layout, and shown whole if it doesn't match.
function card(c) {
  const box = el("div", "card");
  const m = /^(\d+\s*BHK),\s*(.+?)\s*\((.+)\)$/.exec(c.title || "");
  const name = el("div", "name");
  name.append(el("b", "", m ? m[2] : c.title), el("small", "", c.id));
  const price = el("div", "price");
  const rent = el("span", "rent", inr(c.rent));
  rent.append(el("small", "", "/mo"));
  price.append(rent, el("span", "deposit", `Deposit ${inr(c.deposit)}`));
  const top = el("div", "top");
  top.append(name, price);

  const chips = el("div", "chips");
  const chip = (text, cls = "") => chips.append(el("span", cls, text));
  if (m) { chip(m[1], "key"); chip(m[3], "key"); }
  chip(c.furnishing);
  chip(`available ${c.available_from}`);
  chip(`${c.distance_cyber_city_km} km to Cyber City`);
  chip(`${c.distance_golf_course_road_km} km to Golf Course Rd`);

  box.append(top, chips, el("div", "why", c.tradeoff),
    el("div", "id", `pets ${c.pets_allowed ? "ok" : "no"} · ${c.tenant_preference} · parking ${c.parking ? "yes" : "no"}`));
  return box;
}

function addMessage(role, text, r) {
  $("transcript").querySelector(".hint")?.remove();
  const div = el("div", "msg " + role);
  for (const u of r?.updates || []) div.append(el("span", "update", "✎ " + u));
  div.append(document.createTextNode(text));
  if (r?.shortlist?.length) {
    const cards = el("div", "cards");
    for (const c of r.shortlist) cards.append(card(c));
    div.append(cards, el("span", "via", "Prices, areas and facts above come straight from the listings data, not the model."));
  }
  if (r?.no_match) div.append(el("div", "nomatch", "No listing matches every requirement, so nothing is shown."));
  $("transcript").append(div);
  $("transcript").scrollTop = $("transcript").scrollHeight;
}

const STEPS = ["Collecting", "Read-back", "Confirmed", "Shortlist"];
let shortlistShown = false; // a search result (cards or a no-match notice) was shown for the confirmed profile

function renderMemory(state, askingFor = []) {
  const dl = $("profile"); dl.innerHTML = "";
  for (const [field, label] of Object.entries(LABELS)) {
    const value = fmt(field, state.profile[field]);
    const req = REQUIRED.includes(field);
    const dd = el("dd", value !== null ? "" : req ? "missing" : "open");
    if (value === null && req) dd.append(el("span", "pill", "missing")); else dd.textContent = value ?? "—";
    if (value !== null && JSON.stringify(lastProfile[field]) !== JSON.stringify(state.profile[field])) {
      dd.classList.add("flash");
      requestAnimationFrame(() => requestAnimationFrame(() => dd.classList.remove("flash")));
    }
    const dt = el("dt", value !== null ? "filled" : req ? "missing" : "", label);
    if (req) dt.append(el("span", "req", "*"));
    dl.append(dt, dd);
  }
  lastProfile = state.profile;

  if (!state.confirmed) shortlistShown = false;
  const current = state.confirmed ? (shortlistShown ? 3 : 2) : state.awaiting_confirmation ? 1 : 0;
  const stage = $("stage"); stage.innerHTML = "";
  stage.className = "stage" + (state.confirmed ? " confirmed" : "");
  const steps = el("ol", "steps");
  STEPS.forEach((name, i) => {
    const li = el("li", i < current ? "done" : i === current ? "current" : "");
    li.append(el("span", "n", i < current ? "✓" : String(i + 1)), name);
    if (i === current) li.setAttribute("aria-current", "step");
    steps.append(li);
  });
  stage.append(steps, el("div", "stage-note", state.confirmed ? "✓ Confirmed by renter: searching on this profile" :
    state.awaiting_confirmation ? "Read back to renter, waiting for a yes" :
    state.missing_required.length ? `Collecting: ${state.missing_required.length} required field(s) missing` : "Profile complete"));

  const asking = $("asking"); asking.innerHTML = "";
  if (askingFor.length) {
    asking.append("Agent is asking for ");
    for (const f of askingFor) asking.append(el("span", "chip", LABELS[f] || f));
  }

  const ol = $("changelog"); ol.innerHTML = "";
  // Contradicted values the renter hasn't resolved: held by the agent, never applied to the profile.
  for (const [field, p] of Object.entries(state.pending_conflicts || {})) {
    const li = el("li");
    li.append(el("span", "turn", "now"), `${LABELS[field] || field} ${fmt(field, p.stored) ?? "—"} vs ${fmt(field, p.proposed) ?? "—"}, asking`,
      el("span", "kind conflict", "conflict"));
    ol.append(li);
  }
  for (const c of state.changelog.slice(-8).reverse()) {
    const li = el("li");
    li.append(el("span", "turn", `turn ${c.turn}`), `${LABELS[c.field]} ${fmt(c.field, c.old) ?? "—"} → ${fmt(c.field, c.new) ?? "—"}`);
    if (c.kind) li.append(el("span", "kind " + c.kind, c.kind));
    ol.append(li);
  }
  if (!ol.children.length) ol.append(el("li", "", "nothing yet"));
}

let latency = {};
function renderLatency() {
  const box = $("latency"); box.innerHTML = "";
  if (!Object.keys(latency).length) return;
  const ms = (v) => (v === null || v === undefined ? "–" : Math.round(v) + " ms");
  const part = (label, value, cls = "") => { const s = el("span", cls); s.append(label + " ", el("b", "", value)); box.append(s); };
  const spoken = (latency.stt_ms || 0) + (latency.total_ms || 0) - (latency.wait_ms || 0) + (latency.tts_ms || 0);
  box.append(el("span", "label", "Last turn"));
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
  if (r.state.confirmed && (r.shortlist?.length || r.no_match)) shortlistShown = true;
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

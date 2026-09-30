"use strict";
const $ = (s) => document.querySelector(s);
const api = async (path, body) => {
  const r = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  return r.json();
};
const COLORS = {ALIGN: "#3fc1c9", COHERE: "#4d8df0", FOLLOW: "#b07cf2", ESCAPE: "#ef5b5b", ESCAPE_GROUP: "#ff5fa2", ESCAPE_SELFISH: "#c77dff", FLEE_WITH: "#ff8c42", BURST: "#f4c95d",
  SCAN: "#9fb3bf", RECOVER: "#6cc56c", CONTINUE: "#e6eef2", FORAGE: "#b6e05c"};
let SCHEMA = null, cfg = {}, frame = null, selected = 0, clickMode = "select", es = null, trails = new Map(), lastSeries = [];

/* ------------------------------------------------------------------ launch screen */
async function initLaunch() {
  SCHEMA = await api("/api/schema");
  cfg = {...SCHEMA.defaults};
  const cards = $("#scenarioCards");
  const scenField = SCHEMA.schema[0][1].find((f) => f[0] === "scenario");
  cards.innerHTML = "";
  for (const [k, label] of Object.entries(scenField[3])) {
    const d = document.createElement("div");
    d.className = "card" + (k === cfg.scenario ? " on" : "");
    d.innerHTML = `<b>${k.replace("_", " ")}</b><span>${label}</span>`;
    d.onclick = () => setScenario(k);
    cards.appendChild(d);
  }
  renderForm();
  const kf = SCHEMA.key_files.filter((k) => k.exists).map((k) => k.path);
  $("#keyStatus").innerHTML = `Key files found: ${kf.length ? kf.map((p) => `<code>${p}</code>`).join(", ") : "none"}.<br>
    Keys are read at call time and never logged or sent to the browser.`;
  $("#runsList").innerHTML = SCHEMA.runs.length ? SCHEMA.runs.slice(0, 8).map((r) =>
    `<div><a href="#" data-run="${r.name}">${r.name}</a> <span class="muted">${r.mode || ""} · ${r.survivors ?? "?"} alive</span></div>`).join("")
    : "<span class='muted'>none yet</span>";
  document.querySelectorAll("[data-run]").forEach((a) => a.onclick = (e) => {
    e.preventDefault(); cfg.policy = "replay"; cfg.replay_run = a.dataset.run; renderForm();
  });
  estimate();
}

function setScenario(k) {
  cfg = {...SCHEMA.defaults, ...keepUser(), scenario: k, ...SCHEMA.scenarios[k]};
  document.querySelectorAll(".card").forEach((c, i) => c.classList.toggle("on", Object.keys(SCHEMA.scenarios)[i] === k));
  renderForm();
}
function keepUser() {  // keep policy/model/key choices when switching scenario
  const keep = {};
  for (const k of ["policy", "sampling", "mode", "jev_model", "jev_key", "chat_model", "chat_key", "concurrency", "seed", "n_fish", "speed"]) keep[k] = cfg[k];
  return keep;
}

function renderForm() {
  const form = $("#cfgForm");
  form.innerHTML = "";
  for (const [group, fields] of SCHEMA.schema) {
    const fs = document.createElement("fieldset");
    fs.innerHTML = `<legend>${group}</legend>`;
    for (const [key, label, kind, extra] of fields) {
      if (key === "scenario") continue;
      const row = document.createElement("div");
      row.className = "field";
      const id = "f_" + key;
      let input;
      if (kind === "choice") {
        input = document.createElement("select");
        for (const [v, l] of Object.entries(extra)) {
          const o = document.createElement("option"); o.value = v; o.textContent = `${v} — ${l}`; input.appendChild(o);
        }
        input.value = cfg[key];
      } else if (kind === "bool") {
        input = document.createElement("input"); input.type = "checkbox"; input.checked = !!cfg[key];
      } else {
        input = document.createElement("input");
        input.type = kind === "text" ? "text" : "number";
        if (kind === "float") input.step = "any";
        if (extra.min !== undefined) input.min = extra.min;
        if (extra.max !== undefined) input.max = extra.max;
        input.value = cfg[key];
      }
      input.id = id;
      input.onchange = () => {
        cfg[key] = kind === "bool" ? input.checked : kind === "int" ? parseInt(input.value) : kind === "float" ? parseFloat(input.value) : input.value;
        estimate();
      };
      const lab = document.createElement("label"); lab.htmlFor = id; lab.textContent = label;
      if (kind === "choice") lab.title = Object.entries(extra).map(([a, b]) => `${a}: ${b}`).join("\n");
      row.append(lab, input);
      fs.appendChild(row);
    }
    form.appendChild(fs);
  }
}

function estimate() {
  const n = cfg.n_fish, hz = cfg.decision_hz, T = cfg.episode_s;
  const remote = cfg.policy === "jev" || cfg.policy === "chat";
  const rps = n * hz;
  const calls = rps * T;
  const inflight = rps * 0.25;
  let s = `${n} fish × ${hz} Hz = <b>${rps.toFixed(0)}</b> decisions per simulated second, ${Math.round(calls).toLocaleString()} per episode.`;
  if (remote) {
    s += `<br>At ~0.25 s latency that needs ~${Math.ceil(inflight)} requests in flight at 1x speed (limit ${cfg.concurrency}).`;
    if (cfg.policy === "jev") s += `<br>Jev cost ≈ $${(calls * 4.4e-5).toFixed(2)} per episode (measured ~$0.00004 per decision).`;
    if (cfg.policy === "chat") s += `<br><span class="err">Chat models are slow and costly at this rate; use controlled mode and few fish.</span>`;
    if (inflight > cfg.concurrency && cfg.mode === "interactive") s += `<br><span class="err">Concurrency below the need: expect stale drops and fallbacks.</span>`;
  } else {
    s += "<br>Offline policy: no API calls.";
  }
  $("#estimate").innerHTML = s;
}

async function testModel(which) {
  $("#testOut").textContent = `Testing ${which}…`;
  const r = await api("/api/test", {which, cfg});
  $("#testOut").textContent = r.ok ? `OK ${r.model} in ${r.latency}s\n${JSON.stringify(r.reply, null, 1)}` : `Failed: ${r.error}`;
}

async function launch() {
  $("#launchErr").textContent = "";
  $("#launchBtn").disabled = true;
  const r = await api("/api/launch", {cfg});
  $("#launchBtn").disabled = false;
  if (!r.ok) { $("#launchErr").textContent = r.error; return; }
  trails = new Map(); selected = 0; lastSeries = [];
  $("#launch").hidden = true; $("#dash").hidden = false; $("#endBanner").hidden = true;
  initDash();
  connect();
}

/* ------------------------------------------------------------------ dashboard */
function initDash() {
  const sel = $("#livePolicy");
  sel.innerHTML = "";
  for (const k of Object.keys(SCHEMA.policies)) if (k !== "replay") {
    const o = document.createElement("option"); o.value = k; o.textContent = k; sel.appendChild(o);
  }
  const pk = $("#pKind");
  pk.innerHTML = [["survivors_end", "Survivors at the end"], ["captures_by", "Captures by time T"],
    ["lcf_end", "Largest group fraction at end"], ["polarization_end", "Polarization at end"],
    ["recovers", "Recovers after withdrawal (1 = yes)"]].map(([v, l]) => `<option value="${v}">${l}</option>`).join("");
  $("#legend").innerHTML = Object.entries(COLORS).map(([k, c]) => `<span><i style="background:${c}"></i>${k}</span>`).join("") +
    `<span><i style="background:#ff3355"></i>predator</span><span><i style="background:#56636b"></i>rock</span>`;
  $("#analystModel").textContent = cfg.chat_model ? `(${cfg.chat_model})` : "";
}

function connect() {
  if (es) es.close();
  es = new EventSource("/api/stream");
  es.onmessage = (m) => { frame = JSON.parse(m.data); if (frame.series) lastSeries = frame.series; FX.onFrame(frame); render(); };
}

function worldTransform(cv) {
  const W = frame.w, H = frame.h;
  const cw = cv.clientWidth, ch = cw * H / W;
  const dpr = window.devicePixelRatio || 1;
  if (cv.width !== Math.round(cw * dpr) || cv.height !== Math.round(ch * dpr)) {
    cv.width = Math.round(cw * dpr); cv.height = Math.round(ch * dpr); cv.style.height = ch + "px";
  }
  const s = cv.width / W;
  return {s, dpr, X: (x) => x * s, Y: (y) => (H - y) * s};
}

function render() {
  if (!frame) return;
  const f = frame;
  $("#clock").textContent = `${f.t.toFixed(1)} / ${f.episode_s} s`;
  $("#progFill").style.width = `${100 * f.t / f.episode_s}%`;
  $("#playBtn").textContent = f.paused ? "Resume" : "Pause";
  $("#modeTag").textContent = `${f.cfg.mode} · ${f.cfg.scenario} · seed ${f.cfg.seed}`;
  if (document.activeElement !== $("#livePolicy")) $("#livePolicy").value = f.cfg.policy;
  if (document.activeElement !== $("#liveSampling")) $("#liveSampling").value = f.cfg.sampling;
  if (document.activeElement !== $("#liveRange")) { $("#liveRange").value = f.cfg.vision_range; }
  $("#rangeVal").textContent = `${(+f.cfg.vision_range).toFixed(1)} BL`;
  if (document.activeElement !== $("#liveTurb")) $("#liveTurb").value = f.cfg.turbidity;
  $("#turbVal").textContent = (+f.cfg.turbidity).toFixed(2);
  $("#speedVal").textContent = `${(+f.cfg.speed).toFixed(2)}x`;
  updateTrails(); drawPanels();
  if (f.done && f.summary && $("#endBanner").hidden) {
    const s = f.summary;
    $("#endBanner").hidden = false;
    $("#endBanner").innerHTML = `<b>Episode finished.</b> ${s.survivors} survivors, ${s.captures} captures, largest group ${s.largest_component},
      polarization ${s.polarization}. Policy decisions used: ${(100 * s.inference.policy_fraction).toFixed(1)}%.
      Logs: <code>runs/${f.run_dir}</code>. Bankroll ${s.predictions_bankroll}. <button onclick="this.parentNode.hidden=true">close</button>`;
  }
}

function updateTrails() {
  const alive = new Set();
  for (const q of frame.fish) {
    alive.add(q[0]);
    let t = trails.get(q[0]); if (!t) { t = []; trails.set(q[0], t); }
    const last = t[t.length - 1];
    if (!last || Math.hypot(last[0] - q[1], last[1] - q[2]) > 0.3) t.push([q[1], q[2]]);
    if (t.length > 40) t.shift();
  }
  for (const k of [...trails.keys()]) if (!alive.has(k)) trails.delete(k);
}

function drawPanels() {
  const f = frame, r = f.row || {}, st = f.stats || {};
  const mc = (v, l) => `<div class="mc"><b>${v ?? "–"}</b><span>${l}</span></div>`;
  $("#metricCards").innerHTML = mc(`${r.alive}/${f.cfg.n_fish}`, "alive") + mc(r.captures, "captures") + mc(r.polarization, "polarization") +
    mc(r.largest_component, "largest group") + mc(r.components, "groups (6 BL)") + mc(r.mean_energy, "mean energy") +
    mc(r.depleted, "depleted frac") + mc(r.contacts, "contacts") + mc(r.misses ?? 0, "strikes spoiled (crowd)");
  const mix = f.escape_mix || {}, tot = Object.values(mix).reduce((a, b) => a + b, 0);
  const lab = {solo: ["solo", COLORS.ESCAPE], cooperative: ["cooperative", COLORS.ESCAPE_GROUP],
    selfish: ["selfish herd", COLORS.ESCAPE_SELFISH], flee_with: ["flee with neighbour", COLORS.FLEE_WITH]};
  $("#metricCards").innerHTML += `<div class="mc" style="grid-column:1/-1"><span>escape strategies so far</span><div class="mixbar">` +
    Object.entries(lab).map(([k, [name, c]]) => { const v = mix[k] || 0; return v ? `<i style="flex:${v};background:${c}" title="${name}: ${v}"></i>` : ""; }).join("") +
    `</div><span>${tot ? Object.entries(lab).filter(([k]) => mix[k]).map(([k, [name]]) => `${name} ${Math.round(100 * mix[k] / tot)}%`).join(" · ") : "none yet"}</span></div>`;
  const pct = (x) => x == null ? "–" : `${(100 * x).toFixed(1)}%`;
  $("#infCards").innerHTML = mc(st.policy, "policy") + mc(r.achieved_hz, "achieved Hz / fish") + mc(st.latency_p50, "latency p50 s") +
    mc(st.latency_p95, "latency p95 s") + mc(r.decision_age, "decision age s") + mc(pct(st.fallback_fraction), "fallback") +
    mc(pct(st.policy_fraction), "decisions by policy") + mc(r.in_flight, "in flight") + mc(st.requests, "requests") +
    mc(st.failures, "failures") + mc(st.stale, "stale drops") + mc(st.timeouts, "timeouts") + mc(st.invalid, "invalid target") +
    mc(st.busy_skips, "busy skips") + mc(st.cost != null ? "$" + st.cost.toFixed(3) : "–", "API cost") +
    mc((st.model_versions || []).join(" ") || "–", "model version");
  $("#errors").textContent = (f.errors || []).map((e) => `t=${e.t} fish ${e.fish}: ${e.error}`).join("\n");
  $("#events").innerHTML = f.events.slice().reverse().map((e) => `<div class="${e.type}">${e.t.toFixed(1)}s ${e.text}</div>`).join("");
  $("#bankroll").textContent = f.bankroll;
  $("#predList").innerHTML = f.predictions.slice().reverse().map((p) =>
    `<div class="${p.status}">#${p.id} ${p.kind}${p.at != null ? "@" + p.at : ""} ${p.op} ${p.value} · stake ${p.stake} · odds ${p.odds} · made ${p.made_t}s · ${p.status}${p.actual != null ? " (actual " + p.actual + ")" : ""}</div>`).join("");
  drawSpark();
}

function drawSpark() {
  const cv = $("#spark"), g = cv.getContext("2d"), dpr = window.devicePixelRatio || 1;
  cv.width = cv.clientWidth * dpr; cv.height = 150 * dpr;
  g.clearRect(0, 0, cv.width, cv.height);
  const S = lastSeries; if (S.length < 2) return;
  const T = frame.episode_s, W = cv.width, H = cv.height - 14 * dpr;
  const lines = [["alive", "#e6eef2", (r) => r.alive / frame.cfg.n_fish], ["polarization", "#3fc1c9", (r) => r.polarization],
    ["largest group", "#b07cf2", (r) => r.largest_component], ["energy", "#6cc56c", (r) => r.mean_energy]];
  g.strokeStyle = "#1d3a4d"; g.strokeRect(0, 0, W, H);
  const xa = frame.cfg.attack_s / T * W; g.strokeStyle = "#ef5b5b66"; g.beginPath(); g.moveTo(xa, 0); g.lineTo(xa, H); g.stroke();
  if (frame.cfg.withdraw_s > 0) { const xw = frame.cfg.withdraw_s / T * W; g.strokeStyle = "#6cc56c66"; g.beginPath(); g.moveTo(xw, 0); g.lineTo(xw, H); g.stroke(); }
  lines.forEach(([name, c, fn], k) => {
    const gr = g.createLinearGradient(0, 0, 0, H);
    gr.addColorStop(0, c + "40"); gr.addColorStop(1, c + "00");
    g.beginPath();
    S.forEach((r, i) => { const x = r.t / T * W, y = H - fn(r) * H; i ? g.lineTo(x, y) : g.moveTo(x, y); });
    g.lineTo(S[S.length - 1].t / T * W, H); g.lineTo(S[0].t / T * W, H); g.closePath();
    if (k === 0) { g.fillStyle = gr; g.fill(); }
    g.strokeStyle = c; g.lineWidth = 1.8 * dpr; g.shadowColor = c; g.shadowBlur = 6 * dpr; g.beginPath();
    S.forEach((r, i) => { const x = r.t / T * W, y = H - fn(r) * H; i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke();
    g.shadowBlur = 0;
    g.fillStyle = c; g.font = `${10 * dpr}px sans-serif`; g.fillText(name, 4 * dpr + k * 80 * dpr, cv.height - 2 * dpr);
  });
}

/* ------------------------------------------------------------------ selected fish inspector */
async function pollFish() {
  if (!$("#dash").hidden && frame) {
    try {
      const d = await api(`/api/fish?id=${selected}`);
      if (!d.error) drawLocal(d);
    } catch (e) { /* server restarting */ }
  }
  setTimeout(pollFish, 250);
}

function drawLocal(d) {
  $("#selId").textContent = `#${d.fish}${d.alive ? "" : " (captured)"}`;
  $("#selAction").textContent = `${d.action.id} · ${d.action.source} · E ${d.energy.toFixed(2)} · v ${d.speed}${d.burst_ok ? "" : " · burst off"}`;
  const cv = $("#local"), g = cv.getContext("2d"), dpr = window.devicePixelRatio || 1;
  const size = cv.clientWidth * dpr; cv.width = size; cv.height = size;
  const v = d.view, R = v.range, s = size / (2 * (R + 3));
  const cx = size / 2, cy = size / 2;
  const P = (x, y) => [cx - y * s, cy - x * s];          // body frame: forward (x) up, left (y) to the left
  g.clearRect(0, 0, size, size);
  const half = v.fov_deg / 2 * Math.PI / 180;
  g.fillStyle = "#000"; g.beginPath(); g.arc(cx, cy, R * s, 0, 7); g.fill();
  g.fillStyle = "#0f3346"; g.beginPath(); g.moveTo(cx, cy);
  g.arc(cx, cy, R * s, -Math.PI / 2 - half, -Math.PI / 2 + half); g.closePath(); g.fill();
  g.setLineDash([4, 4]); g.strokeStyle = "#3fc1c9aa"; g.beginPath(); g.arc(cx, cy, R * s, 0, 7); g.stroke(); g.setLineDash([]);
  g.strokeStyle = "#3fc1c922"; for (const k of [0.25, 0.5, 0.75]) { g.beginPath(); g.arc(cx, cy, R * s * k, 0, 7); g.stroke(); }
  const sw = (performance.now() / 1500) % (2 * Math.PI);
  const sg = g.createConicGradient ? g.createConicGradient(sw - 0.6, cx, cy) : null;
  if (sg) { sg.addColorStop(0, "rgba(63,193,201,0)"); sg.addColorStop(0.095, "rgba(63,193,201,0.22)"); sg.addColorStop(0.1, "rgba(63,193,201,0)");
    g.fillStyle = sg; g.beginPath(); g.arc(cx, cy, R * s, 0, 7); g.fill(); }
  // occlusion shadows behind every body in range (fish, predators, rocks)
  const occ = v.entities.filter((e) => Math.hypot(e.x, e.y) < R).map((e) => [e.x, e.y, e.kind === "fish" ? v.fish_r : v.pred_r]).concat(v.rocks);
  g.fillStyle = "#52667033";
  for (const [x, y, r] of occ) {
    const dd = Math.hypot(x, y); if (dd <= r) continue;
    const a = Math.atan2(y, x), w = Math.asin(Math.min(1, r / dd));
    const p1 = P(x + 0, y + 0);
    g.beginPath();
    const A = [a - w, a + w].map((b) => [Math.cos(b), Math.sin(b)]);
    const n1 = P(A[0][0] * dd, A[0][1] * dd), n2 = P(A[1][0] * dd, A[1][1] * dd);
    const f1 = P(A[0][0] * R, A[0][1] * R), f2 = P(A[1][0] * R, A[1][1] * R);
    g.moveTo(...n1); g.lineTo(...f1); g.lineTo(...f2); g.lineTo(...n2); g.closePath(); g.fill();
  }
  for (const [x, y, r] of v.rocks) { const [a, b] = P(x, y); g.fillStyle = "#56636b"; g.beginPath(); g.arc(a, b, r * s, 0, 7); g.fill(); }
  for (const e of v.entities) {
    const [a, b] = P(e.x, e.y);
    const alpha = e.status === "visible" ? 1 : e.status === "hidden" ? 0.45 : 0.18;
    const col = e.kind === "predator" ? `rgba(255,51,85,${alpha})` : `rgba(207,227,236,${alpha})`;
    g.save(); g.translate(a, b); g.rotate(-e.h - Math.PI / 2);
    const L = (e.kind === "predator" ? 2.2 : 1.1) * s;
    g.beginPath(); g.moveTo(L * 0.6, 0); g.lineTo(-L * 0.4, L * 0.28); g.lineTo(-L * 0.4, -L * 0.28); g.closePath();
    if (e.status === "hidden") { g.setLineDash([2, 2]); g.strokeStyle = col; g.stroke(); g.setLineDash([]); } else { g.fillStyle = col; g.fill(); }
    g.restore();
    if (e.slot) { g.fillStyle = e.kind === "predator" ? "#ff7a8a" : "#3fc1c9"; g.font = `${11 * dpr}px sans-serif`; g.fillText(e.slot, a + 6 * dpr, b - 6 * dpr); }
  }
  g.fillStyle = COLORS[d.action.kind] || "#fff";
  g.beginPath(); g.moveTo(cx, cy - 0.8 * s); g.lineTo(cx + 0.3 * s, cy + 0.5 * s); g.lineTo(cx - 0.3 * s, cy + 0.5 * s); g.closePath(); g.fill();
  // probabilities
  const ld = d.last_decision;
  const probs = ld ? Object.entries(ld.probs).sort((a, b) => b[1] - a[1]) : [];
  $("#probs").innerHTML = probs.map(([k, p]) => `<div class="prob ${k === ld.applied ? "chosen" : ""}" title="${(ld.candidates[k] || "").replace(/"/g, "&quot;")}">
    <span>${k}</span><div class="b"><div style="width:${(100 * p).toFixed(1)}%"></div></div><span>${(100 * p).toFixed(0)}%</span></div>`).join("") || "<span class='muted'>no decision yet</span>";
  $("#decMeta").textContent = ld ? `t=${ld.t}s · ${ld.source}${ld.latency != null ? " · " + ld.latency + " s" : ""}${ld.age != null ? " · age " + ld.age + " s" : ""}${ld.jev_choice ? " · Jev top " + ld.jev_choice : ""}` : "";
  if (!$("#obsJson").closest("details").open) return;
  $("#obsJson").textContent = JSON.stringify(ld ? ld.obs : d.observation, null, 1);
}

/* ------------------------------------------------------------------ interactions */
function worldPoint(ev) {
  const cv = $("#world"), rect = cv.getBoundingClientRect();
  const x = (ev.clientX - rect.left) / rect.width * frame.w;
  const y = frame.h - (ev.clientY - rect.top) / rect.height * frame.h;
  return [x, y];
}
const cmd = (o) => api("/api/cmd", o);

function bind() {
  $("#launchBtn").onclick = launch;
  $("#testJev").onclick = () => testModel("jev");
  $("#testChat").onclick = () => testModel("chat");
  $("#playBtn").onclick = () => cmd({op: frame && frame.paused ? "resume" : "pause"});
  $("#stepBtn").onclick = () => cmd({op: "step"});
  $("#speed").oninput = (e) => { const v = Math.pow(2, +e.target.value); $("#speedVal").textContent = v.toFixed(2) + "x"; };
  $("#speed").onchange = (e) => cmd({op: "set", key: "speed", value: Math.pow(2, +e.target.value)});
  $("#livePolicy").onchange = (e) => cmd({op: "set", key: "policy", value: e.target.value});
  $("#liveSampling").onchange = (e) => cmd({op: "set", key: "sampling", value: e.target.value});
  $("#liveRange").onchange = (e) => cmd({op: "set", key: "vision_range", value: +e.target.value});
  $("#liveTurb").onchange = (e) => cmd({op: "set", key: "turbidity", value: +e.target.value});
  $("#newRun").onclick = async () => { if (es) es.close(); $("#dash").hidden = true; $("#launch").hidden = false; await initLaunch(); };
  $("#falseAlarm").onclick = () => cmd({op: "false_alarm", fish: selected});
  $("#withdrawBtn").onclick = () => cmd({op: "withdraw"});
  document.querySelectorAll("#clickMode button").forEach((b) => b.onclick = () => {
    clickMode = b.dataset.mode; document.querySelectorAll("#clickMode button").forEach((x) => x.classList.toggle("on", x === b));
  });
  $("#world").onclick = (ev) => {
    if (!frame) return;
    const [x, y] = worldPoint(ev);
    if (clickMode === "predator") return cmd({op: "place_predator", x, y});
    if (clickMode === "rock") return cmd({op: "add_rock", x, y, r: 2.5});
    let best = null, bd = 1e9;
    for (const q of frame.fish) { const d = Math.hypot(q[1] - x, q[2] - y); if (d < bd) { bd = d; best = q[0]; } }
    if (best != null && bd < 4) selected = best;
  };
  $("#pGo").onclick = async () => {
    const r = await api("/api/predict", {kind: $("#pKind").value, op: $("#pOp").value, value: +$("#pVal").value,
      stake: +$("#pStake").value, at: $("#pAt").value});
    if (!r.ok) alert("Prediction not accepted (episode over, or no bankroll left).");
  };
  $("#aGo").onclick = async () => {
    $("#aOut").textContent = "Thinking…";
    const r = await api("/api/analyst", {question: $("#aQ").value});
    $("#aOut").textContent = r.ok ? `${r.answer}\n— ${r.model}` : `Failed: ${r.error}`;
  };
  document.addEventListener("keydown", (e) => {
    if ($("#dash").hidden || ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
    if (e.code === "Space") { e.preventDefault(); $("#playBtn").click(); }
    if (e.key === ".") cmd({op: "step"});
  });
  window.addEventListener("resize", () => frame && render());
}

bind();
initLaunch().then(async () => {
  // if a run is already live (page reload), go straight to the viewer
  if (SCHEMA.running) { $("#launch").hidden = true; $("#dash").hidden = false; initDash(); connect(); }
});
pollFish();

"use strict";
const $ = (s) => document.querySelector(s);
const api = async (path, body) => {
  const r = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  return r.json();
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const hm = (min) => `${Math.floor(min / 60)}:${String(Math.floor(min % 60)).padStart(2, "0")}`;
let SCHEMA = null, cfg = {}, frame = null, prevFrame = null, frameAt = 0, frameGap = 250, selected = -1,
  clickMode = "select", es = null, view = null, siteColor = {};
const ACTION_COLORS = {WAIT: "#a89d80", EXPLORE: "#8bc34a", INSPECT: "#29b6f6", FOLLOW: "#b07cf2", ADVERTISE: "#f4b400", STOP: "#ef5350"};

/* ------------------------------------------------------------------ launch screen */
async function initLaunch() {
  SCHEMA = await api("/api/schema");
  cfg = {...SCHEMA.defaults};
  const cards = $("#scenarioCards");
  const scen = SCHEMA.schema[0][1].find((f) => f[0] === "scenario")[3];
  cards.innerHTML = "";
  for (const [k, label] of Object.entries(scen)) {
    const d = document.createElement("div");
    d.className = "card" + (k === cfg.scenario ? " on" : "");
    d.dataset.k = k;
    d.innerHTML = `<b>${k.replace(/_/g, " ")}</b><span>${esc(label)}</span>`;
    d.onclick = () => setScenario(k);
    cards.appendChild(d);
  }
  renderForm();
  const kf = SCHEMA.key_files.filter((k) => k.exists).map((k) => k.path);
  $("#keyStatus").innerHTML = `Key files found: ${kf.length ? kf.map((p) => `<code>${esc(p)}</code>`).join(", ") : "none"}.<br>
    Keys are read at call time and never logged or sent to the browser.`;
  $("#runsList").innerHTML = SCHEMA.runs.length ? SCHEMA.runs.slice(0, 8).map((r) =>
    `<div><a href="#" data-run="${esc(r.name)}">${esc(r.name)}</a> <span class="muted">→ ${esc(r.chosen ?? "none")}
      ${r.correct ? "(best)" : r.chosen ? "(not best)" : ""}${r.cost ? ` · $${r.cost.toFixed(3)}` : ""}</span></div>`).join("")
    : "<span class='muted'>none yet</span>";
  document.querySelectorAll("[data-run]").forEach((a) => a.onclick = (e) => {
    e.preventDefault(); cfg.policy = "replay"; cfg.replay_run = a.dataset.run; renderForm(); estimate();
  });
  estimate();
  $("#rejoinBtn").hidden = !SCHEMA.running;
}

function setScenario(k) {
  const keep = {};
  for (const x of ["policy", "sampling", "jev_model", "jev_key", "chat_model", "chat_key", "concurrency", "seed", "speed", "n_scouts"]) keep[x] = cfg[x];
  cfg = {...SCHEMA.defaults, ...keep, scenario: k, ...SCHEMA.scenarios[k]};
  document.querySelectorAll(".card").forEach((c) => c.classList.toggle("on", c.dataset.k === k));
  renderForm(); estimate();
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
      input.id = "f_" + key;
      input.onchange = () => {
        cfg[key] = kind === "bool" ? input.checked : kind === "int" ? parseInt(input.value) : kind === "float" ? parseFloat(input.value) : input.value;
        estimate();
      };
      const lab = document.createElement("label"); lab.htmlFor = input.id; lab.textContent = label;
      row.append(lab, input);
      fs.appendChild(row);
    }
    form.appendChild(fs);
  }
}

function estimate() {
  // Measured: ~3.8 decisions per scout per simulated hour; Jev ~$0.000025 per decision (100-scout classic run: 780 decisions, $0.016).
  const n = cfg.n_scouts, hrs = Math.min(cfg.max_hours, 2.5);
  const dec = Math.round(n * 3.8 * hrs), worst = Math.round(n * 3.8 * cfg.max_hours);
  let s = `${n} scouts decide about every 15 simulated minutes: ≈ <b>${dec.toLocaleString()}</b> decisions for a typical ~2 h decision
    (at most ${worst.toLocaleString()} if no quorum forms in ${cfg.max_hours} h).`;
  if (cfg.policy === "jev") {
    s += `<br>Jev cost ≈ <b>$${(dec * 2.5e-5).toFixed(3)}</b> per run (worst case $${(worst * 2.5e-5).toFixed(2)}), at ~$0.000025 per decision.`;
    s += `<br>Each simulated minute waits for that minute's decisions (${cfg.concurrency} in flight, ~0.2 s each), so wall time is about 30-60 s.`;
  } else if (cfg.policy === "chat") {
    s += `<br><span class="err">Chat models are slow and much more expensive per decision; use few scouts.</span>`;
  } else {
    s += "<br>Offline policy: no API calls, free.";
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
  startDash(r.run);
}

/* ------------------------------------------------------------------ dashboard */
function startDash(run) {
  $("#launch").hidden = true; $("#dash").hidden = false; $("#endBanner").hidden = true;
  $("#runTag").textContent = run || "";
  selected = -1; frame = null; prevFrame = null;
  const pol = $("#livePolicy"); pol.innerHTML = "";
  for (const k of Object.keys(SCHEMA.policies)) if (k !== "replay") pol.append(new Option(k, k));
  if (es) es.close();
  es = new EventSource("/api/stream");
  es.onmessage = (ev) => onFrame(JSON.parse(ev.data));
  buildKnobs();
  resize();
}

function onFrame(f) {
  const now = performance.now();
  if (frame && f.t !== frame.t) { frameGap = Math.min(1500, Math.max(40, now - frameAt)); prevFrame = frame; frameAt = now; }
  else if (!frame) { frameAt = now; }
  frame = f;
  f.sites.forEach((s) => siteColor[s.label] = s.color);
  $("#clock").textContent = `${hm(f.t)} h`;
  $("#runTag").textContent = f.run;
  $("#progFill").style.width = `${Math.min(100, 100 * f.t / f.max_t)}%`;
  $("#playBtn").textContent = f.paused ? "Resume" : "Pause";
  const sp = $("#speed");
  if (document.activeElement !== sp) sp.value = Math.log10(f.speed);
  $("#speedVal").textContent = `${f.speed.toFixed(f.speed < 10 ? 1 : 0)} min/s`;
  if (document.activeElement !== $("#livePolicy")) $("#livePolicy").value = f.policy;
  if (document.activeElement !== $("#liveSampling")) $("#liveSampling").value = f.sampling;
  renderSites(f); renderMetrics(f); renderInference(f); renderEvents(f); renderPreds(f); drawSupport(f); syncKnobs(f);
  if (f.ended) showEnd(f);
}

function showEnd(f) {
  const b = $("#endBanner");
  const o = f.outcome;
  b.innerHTML = o ? `<b>Lift-off at ${hm(o.t)} h to site ${o.chosen}</b> (quality ${o.chosen_quality}).
      The best site was ${o.best} (${o.best_quality}). ${o.correct ? "<span class='won'>Correct choice.</span>" : "<span class='lost'>Not the best site.</span>"}
      ${o.split ? "<span class='lost'> The swarm split.</span>" : ""} Bankroll ${f.bankroll}.`
    : `<b>No decision</b> within ${hm(f.max_t)} h. Bankroll ${f.bankroll}.`;
  b.hidden = false;
}

function card(label, value, title) { return `<div class="mc" title="${esc(title || "")}"><b>${value}</b><span>${label}</span></div>`; }

function renderSites(f) {
  const m = f.metrics, Q = m.quorum_count;
  $("#qCount").textContent = Q;
  const maxAt = Math.max(Q * 1.4, ...Object.values(m.sites).map((s) => s.at_site));
  let h = `<tr><th>Site</th><th>True quality</th><th>Dist</th><th>Known by</th><th>Dancing</th><th>Circuits 30 min</th><th>At site / quorum</th><th></th></tr>`;
  for (const s of f.sites) {
    const x = m.sites[s.label] || {};
    const future = s.appears_min > f.t;
    h += `<tr class="${s.label === m.best ? "best" : ""}">
      <td><span class="sw" style="background:${s.color}"></span><b>${s.label}</b>${future ? ` <span class="muted">(from ${hm(s.appears_min)})</span>` : ""}${m.quorum[s.label] !== undefined ? ` <span class="tag">quorum ${hm(m.quorum[s.label])}</span>` : ""}</td>
      <td><input type="range" min="0" max="1" step="0.01" value="${s.quality}" data-q="${s.label}"> ${s.quality.toFixed(2)}</td>
      <td>${(s.dist / 1000).toFixed(1)} km</td><td>${x.known_by}</td><td>${x.dancers}</td><td>${x.circuits_30}</td>
      <td><div class="qbar"><div style="width:${100 * x.at_site / maxAt}%;background:${s.color}"></div><i style="left:${100 * Q / maxAt}%"></i></div> ${x.at_site}</td>
      <td><button data-mis="${s.label}" title="5 scouts start believing this site is excellent">misinform</button>
          <button data-fake="${s.label}" title="Inject 5 fake dances for this site">fake dances</button></td></tr>`;
  }
  const t = $("#siteTable");
  if (t.dataset.busy) return;
  t.innerHTML = h;
  t.querySelectorAll("[data-q]").forEach((r) => {
    r.onpointerdown = () => t.dataset.busy = "1";
    r.onchange = () => { delete t.dataset.busy; api("/api/cmd", {op: "site_quality", site: r.dataset.q, quality: parseFloat(r.value)}); };
  });
  t.querySelectorAll("[data-mis]").forEach((b) => b.onclick = () => api("/api/cmd", {op: "misinform", site: b.dataset.mis, n: 5}));
  t.querySelectorAll("[data-fake]").forEach((b) => b.onclick = () => api("/api/cmd", {op: "fake_dances", site: b.dataset.fake, n: 5}));
  const ps = $("#pSite");
  if (ps.options.length !== f.sites.length) { ps.innerHTML = ""; f.sites.forEach((s) => ps.append(new Option(`site ${s.label}`, s.label))); }
}

function renderMetrics(f) {
  const m = f.metrics, st = m.states;
  $("#metricCards").innerHTML = [
    card("leading site", m.leader || "-"), card("consensus", (100 * m.consensus).toFixed(0) + "%", "share of recent circuits for the leader"),
    card("best site share", (100 * m.best_share).toFixed(0) + "%", `site ${m.best}`), card("sites discovered", `${m.discovered}/${f.sites.length}`),
    card("lift-off", m.liftoff_at ? hm(m.liftoff_at) : "-"), card("mean energy", m.mean_energy),
    card("on cluster", (st.idle || 0) + (st.waiting || 0)), card("dancing", st.dancing || 0), card("flying / at sites", st.trip || 0),
  ].join("");
}

function renderInference(f) {
  const i = f.inference;
  $("#infCards").innerHTML = [
    card("decisions", i.decisions), card("model calls", i.completed), card("p50 latency", i.latency_p50 != null ? i.latency_p50 + " s" : "-"),
    card("p95 latency", i.latency_p95 != null ? i.latency_p95 + " s" : "-"), card("fallbacks", i.fallbacks), card("failures", i.failures),
    card("cost", "$" + i.cost.toFixed(4)), card("per decision", i.cost_per_decision ? "$" + i.cost_per_decision.toFixed(6) : "-"),
    card("model", (i.models[0] || i.policy).replace("typesafe/", "")),
  ].join("");
  $("#errors").innerHTML = f.errors.map(esc).join("<br>");
}

function renderEvents(f) {
  const el = $("#events");
  const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 4;
  el.innerHTML = f.events.map((e) => `<div class="${e.kind}"><span class="muted">${hm(e.t)}</span> ${esc(e.detail)}</div>`).join("");
  if (atBottom) el.scrollTop = el.scrollHeight;
}

function renderPreds(f) {
  $("#bankroll").textContent = f.bankroll;
  $("#predList").innerHTML = f.predictions.slice().reverse().map((p) =>
    `<div class="${p.status}">${esc(p.label)} · ${p.stake} at ${p.odds}x · ${p.status}${p.payout ? " +" + p.payout : ""}</div>`).join("");
}

/* live knobs */
const KNOBS = [["dance_bandwidth", "Dance bandwidth (/10 min)", 0, 20, 0.5], ["quality_noise", "Assessment noise", 0, 0.6, 0.01],
  ["follow_success", "Follower finds site", 0, 1, 0.05], ["confidence_calibration", "Confidence calibration", -1, 1, 0.1],
  ["quorum_frac", "Quorum fraction", 0.02, 0.6, 0.01], ["dance_attrition", "Circuit attrition", 0, 50, 1],
  ["discover_rate", "Search success", 0, 1, 0.05]];
function buildKnobs() {
  const el = $("#knobs"); el.innerHTML = "";
  for (const [k, label, lo, hi, step] of KNOBS) {
    const row = document.createElement("div"); row.className = "field";
    row.innerHTML = `<label>${label}</label><input type="range" min="${lo}" max="${hi}" step="${step}" data-k="${k}"><span data-v="${k}"></span>`;
    const r = row.querySelector("input");
    r.onchange = () => api("/api/cmd", {op: "set", key: k, value: parseFloat(r.value)});
    r.oninput = () => row.querySelector("span").textContent = r.value;
    el.appendChild(row);
  }
}
function syncKnobs(f) {
  for (const [k] of KNOBS) {
    const r = document.querySelector(`[data-k="${k}"]`);
    if (r && document.activeElement !== r) { r.value = f.live[k]; document.querySelector(`[data-v="${k}"]`).textContent = f.live[k]; }
  }
}

/* support chart */
function drawSupport(f) {
  const c = $("#support"), dpr = devicePixelRatio || 1, W = c.clientWidth, H = 170;
  c.width = W * dpr; c.height = H * dpr;
  const g = c.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
  const S = f.series; if (S.length < 2) return;
  const t0 = S[0].t, t1 = Math.max(S[S.length - 1].t, t0 + 30);
  let ymax = 50; for (const r of S) for (const s of f.sites) ymax = Math.max(ymax, r[s.label] || 0);
  const X = (t) => 30 + (W - 40) * (t - t0) / (t1 - t0), Y = (v) => H - 18 - (H - 28) * v / ymax;
  g.strokeStyle = "#3b3524"; g.fillStyle = "#a89d80"; g.font = "10px sans-serif";
  for (let v = 0; v <= ymax; v += Math.ceil(ymax / 4 / 50) * 50) { g.beginPath(); g.moveTo(30, Y(v)); g.lineTo(W - 10, Y(v)); g.stroke(); g.fillText(v, 2, Y(v) + 3); }
  for (let t = Math.ceil(t0 / 60) * 60; t <= t1; t += 60) g.fillText(hm(t), X(t) - 10, H - 4);
  for (const s of f.sites) {
    g.strokeStyle = s.color; g.lineWidth = s.label === f.metrics.best ? 2.5 : 1.5; g.beginPath();
    S.forEach((r, i) => i ? g.lineTo(X(r.t), Y(r[s.label] || 0)) : g.moveTo(X(r.t), Y(r[s.label] || 0)));
    g.stroke();
    const last = S[S.length - 1];
    g.fillStyle = s.color; g.fillText(s.label, X(last.t) + 2, Y(last[s.label] || 0) + 3);
  }
  for (const [lab, t] of Object.entries(f.metrics.quorum)) {
    g.strokeStyle = siteColor[lab]; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(X(t), 5); g.lineTo(X(t), H - 18); g.stroke(); g.setLineDash([]);
  }
}

/* ------------------------------------------------------------------ landscape canvas */
function resize() {
  const c = $("#world"), dpr = devicePixelRatio || 1;
  c.width = c.clientWidth * dpr; c.height = c.clientHeight * dpr;
}
addEventListener("resize", resize);

function computeView(f) {
  const c = $("#world");
  const W = c.clientWidth, H = c.clientHeight;
  let R = 500; for (const s of f.sites) R = Math.max(R, Math.abs(s.x) * H / W, Math.abs(s.y), s.dist * 0.75);
  const scale = Math.min(W, H) / 2 / (R * 1.12);
  return {W, H, scale, cx: W / 2, cy: H / 2};
}
const toScreen = (v, x, y) => [v.cx + x * v.scale, v.cy - y * v.scale];

function draw() {
  requestAnimationFrame(draw);
  if ($("#dash").hidden || !frame) return;
  const c = $("#world"), g = c.getContext("2d"), dpr = devicePixelRatio || 1;
  if (c.width !== Math.round(c.clientWidth * dpr)) resize();
  const f = frame, v = view = computeView(f), now = performance.now();
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  // meadow
  const bg = g.createRadialGradient(v.cx, v.cy, 20, v.cx, v.cy, Math.max(v.W, v.H) * 0.7);
  bg.addColorStop(0, "#2c3b1c"); bg.addColorStop(1, "#141d0e");
  g.fillStyle = bg; g.fillRect(0, 0, v.W, v.H);
  if ($("#tRings").checked) {
    g.strokeStyle = "#ffffff14"; g.fillStyle = "#ffffff40"; g.font = "10px sans-serif";
    for (let r = 1000; r * v.scale < Math.max(v.W, v.H); r += 1000) {
      g.beginPath(); g.arc(v.cx, v.cy, r * v.scale, 0, 7); g.stroke(); g.fillText(`${r / 1000} km`, v.cx + r * v.scale + 3, v.cy - 3);
    }
  }
  // sites
  const m = f.metrics;
  for (const s of f.sites) {
    const [x, y] = toScreen(v, s.x, s.y);
    const future = s.appears_min > f.t;
    const at = (m.sites[s.label] || {}).at_site || 0;
    const q = m.quorum[s.label] !== undefined;
    g.globalAlpha = future ? 0.3 : 1;
    if (q) { g.fillStyle = s.color + "33"; g.beginPath(); g.arc(x, y, 30 + 4 * Math.sin(now / 250), 0, 7); g.fill(); }
    // tree-cavity glyph: trunk ring with quality arc
    g.fillStyle = "#3d2b1a"; g.beginPath(); g.arc(x, y, 15, 0, 7); g.fill();
    g.lineWidth = 3; g.strokeStyle = s.color; g.beginPath(); g.arc(x, y, 15, -Math.PI / 2, -Math.PI / 2 + 2 * Math.PI * ($("#tTruth").checked ? s.quality : 1)); g.stroke();
    g.fillStyle = "#120b05"; g.beginPath(); g.ellipse(x, y + 2, 5, 7, 0, 0, 7); g.fill();
    g.fillStyle = "#fff"; g.font = "bold 13px sans-serif"; g.fillText(s.label, x - 4, y - 20);
    g.font = "10px sans-serif"; g.fillStyle = "#f1ead8b0";
    g.fillText(`${$("#tTruth").checked ? "q " + s.quality.toFixed(2) + " · " : ""}${at} here`, x - 22, y + 29);
    g.globalAlpha = 1;
  }
  // swarm cluster
  const nOn = (m.states.idle || 0) + (m.states.waiting || 0) + (m.states.dancing || 0);
  const cl = g.createRadialGradient(v.cx, v.cy - 4, 2, v.cx, v.cy, 26);
  cl.addColorStop(0, "#ffd54f"); cl.addColorStop(0.7, "#c68a00"); cl.addColorStop(1, "#c68a0000");
  g.fillStyle = cl; g.beginPath(); g.ellipse(v.cx, v.cy + 4, 20, 26, 0, 0, 7); g.fill();
  g.strokeStyle = "#5d4037"; g.lineWidth = 3; g.beginPath(); g.moveTo(v.cx - 40, v.cy - 24); g.lineTo(v.cx + 40, v.cy - 28); g.stroke();
  // outcome: lift-off arrow
  if (f.outcome) {
    const s = f.sites.find((z) => z.label === f.outcome.chosen);
    const [x, y] = toScreen(v, s.x, s.y);
    const k = ((now / 2500) % 1);
    g.strokeStyle = s.color; g.lineWidth = 2; g.setLineDash([6, 5]); g.beginPath(); g.moveTo(v.cx, v.cy); g.lineTo(x, y); g.stroke(); g.setLineDash([]);
    g.fillStyle = "#ffd54f"; g.beginPath(); g.arc(v.cx + (x - v.cx) * k, v.cy + (y - v.cy) * k, 9, 0, 7); g.fill();
  }
  // scouts (interpolated between the last two frames)
  const a = prevFrame ? Math.min(1, (now - frameAt) / frameGap) : 1;
  const prev = new Map((prevFrame ? prevFrame.scouts : []).map((s) => [s[0], s]));
  for (const s of f.scouts) {
    const [id, x1, y1, st, tgt, circ, , stub, mis] = s;
    const p = prev.get(id) || s;
    let wx = p[1] + (x1 - p[1]) * a, wy = p[2] + (y1 - p[2]) * a;
    let [x, y] = toScreen(v, wx, wy);
    const col = tgt ? (siteColor[tgt] || "#fff") : "#f1ead8";
    if (st === "d") {  // waggle dance: a figure-eight on the cluster
      const ph = now / 180 + id;
      x += 5 * Math.sin(ph); y += 3 * Math.sin(2 * ph);
      g.strokeStyle = col; g.lineWidth = 1; g.globalAlpha = 0.6;
      g.beginPath(); for (let i = 0; i < 20; i++) { const q = i / 20 * 2 * Math.PI; g.lineTo(x - 5 * Math.sin(ph) + 5 * Math.sin(q), y - 3 * Math.sin(2 * ph) + 3 * Math.sin(2 * q)); } g.stroke();
      g.globalAlpha = 1;
    }
    if (st === "t" && tgt && $("#tTrails").checked) {
      g.strokeStyle = col + "40"; g.lineWidth = 1; g.beginPath(); g.moveTo(v.cx, v.cy); g.lineTo(x, y); g.stroke();
    }
    const r = id === selected ? 4.5 : st === "t" ? 2.6 : 2.2;
    g.fillStyle = st === "t" || st === "d" ? col : "#e0c060";
    g.beginPath(); g.ellipse(x, y, r * 1.3, r, 0, 0, 7); g.fill();
    if (stub || mis) { g.strokeStyle = stub ? "#ef5350" : "#b07cf2"; g.lineWidth = 1; g.beginPath(); g.arc(x, y, r + 2, 0, 7); g.stroke(); }
    if (id === selected) { g.strokeStyle = "#fff"; g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 9, 0, 7); g.stroke(); }
    if ($("#tIds").checked) { g.fillStyle = "#fff9"; g.font = "9px sans-serif"; g.fillText(id, x + 4, y - 3); }
  }
  g.fillStyle = "#f1ead8"; g.font = "11px sans-serif";
  g.fillText(`swarm: ${f.sites.length ? nOn : 0} scouts on the cluster`, 10, v.H - 10);
}

function legend() {
  $("#legend").innerHTML = `<span><i style="background:#e0c060"></i>scout resting on the cluster</span>
    <span><i style="background:#29b6f6"></i>flying or dancing (colour = site)</span>
    <span><i style="border:1px solid #ef5350"></i>stubborn</span><span><i style="border:1px solid #b07cf2"></i>misinformed</span>
    <span>ring arc around a site = true quality · pulsing halo = quorum reached</span>`;
}

$("#world").addEventListener("click", (e) => {
  if (!frame || !view) return;
  const rect = e.target.getBoundingClientRect();
  const mx = e.clientX - rect.left, my = e.clientY - rect.top;
  if (clickMode === "site") {
    const x = (mx - view.cx) / view.scale, y = -(my - view.cy) / view.scale;
    const q = parseFloat(prompt("Quality of the new site (0..1)?", "0.95"));
    if (!isNaN(q)) api("/api/cmd", {op: "add_site", x, y, quality: q});
    return;
  }
  let best = -1, bd = 14;
  for (const s of frame.scouts) {
    const [x, y] = toScreen(view, s[1], s[2]);
    const d = Math.hypot(x - mx, y - my);
    if (d < bd) { bd = d; best = s[0]; }
  }
  if (best >= 0) { selected = best; refreshScout(); }
});

async function refreshScout() {
  if (selected < 0 || $("#dash").hidden) return;
  const d = await api(`/api/scout?id=${selected}`);
  if (d.error) return;
  $("#selId").textContent = d.scout;
  $("#selTraits").textContent = d.traits.length ? `(${d.traits.join(", ")})` : "";
  $("#selState").textContent = `${d.state} · energy ${d.energy}`;
  $("#history").innerHTML = d.history.slice().reverse().map(([t, act, what]) =>
    `<div><span class="muted">${hm(t)}</span> <b>${esc(act)}</b> ${esc(what)}</div>`).join("") || "<span class='muted'>no decisions yet</span>";
  const L = d.last;
  if (!L) { $("#probs").innerHTML = ""; $("#obsJson").textContent = JSON.stringify(d.observation_now, null, 1); return; }
  $("#decMeta").textContent = `at ${hm(L.t)} · ${L.source}${L.latency ? " · " + L.latency + " s" : ""}${L.model ? " · " + L.model.replace("typesafe/", "") : ""}`;
  $("#probs").innerHTML = Object.entries(L.probs).sort((x, y) => y[1] - x[1]).map(([k, p]) => {
    const col = ACTION_COLORS[k.split("_")[0]] || "#f4b400";
    return `<div class="prob ${k === L.applied ? "chosen" : ""}" title="${esc(L.cands[k])}"><span>${esc(k)}</span>
      <div class="b"><div style="width:${100 * p}%;background:${col}"></div></div><span>${(100 * p).toFixed(0)}%</span></div>`;
  }).join("");
  $("#obsJson").textContent = JSON.stringify(L.obs, null, 1);
}
setInterval(refreshScout, 1000);

/* ------------------------------------------------------------------ controls */
$("#testJev").onclick = () => testModel("jev");
$("#testChat").onclick = () => testModel("chat");
$("#launchBtn").onclick = launch;
$("#rejoinBtn").onclick = () => startDash("");
$("#playBtn").onclick = () => api("/api/cmd", {op: frame && frame.paused ? "resume" : "pause"});
$("#stepBtn").onclick = () => api("/api/cmd", {op: "step", n: 5});
$("#speed").onchange = (e) => api("/api/cmd", {op: "set", key: "speed", value: Math.pow(10, parseFloat(e.target.value))});
$("#livePolicy").onchange = (e) => api("/api/cmd", {op: "set", key: "policy", value: e.target.value});
$("#liveSampling").onchange = (e) => api("/api/cmd", {op: "set", key: "sampling", value: e.target.value});
$("#stubbornBtn").onclick = () => api("/api/cmd", {op: "stubborn", n: 5});
$("#newRun").onclick = async () => { if (es) es.close(); await initLaunch(); $("#dash").hidden = true; $("#launch").hidden = false; };
document.querySelectorAll("#clickMode button").forEach((b) => b.onclick = () => {
  clickMode = b.dataset.mode;
  document.querySelectorAll("#clickMode button").forEach((x) => x.classList.toggle("on", x === b));
});
function predForm() {
  const k = $("#pKind").value;
  $("#pSite").hidden = k !== "winner"; $("#pHour").hidden = k !== "by_hour"; $("#pYes").hidden = !(k === "correct" || k === "split");
}
$("#pKind").onchange = predForm;
$("#pGo").onclick = async () => {
  const k = $("#pKind").value;
  const value = k === "winner" ? $("#pSite").value : k === "by_hour" ? parseFloat($("#pHour").value) : $("#pYes").value;
  const r = await api("/api/predict", {kind: k, value, stake: parseFloat($("#pStake").value)});
  if (!r.ok) alert("Bet not accepted (run over or bankroll too low).");
};
$("#aGo").onclick = async () => {
  $("#aOut").textContent = "Asking…";
  const r = await api("/api/analyst", {question: $("#aQ").value});
  $("#aOut").textContent = r.ok ? r.answer : `Failed: ${r.error}`;
  if (r.ok) $("#analystModel").textContent = r.model;
};
addEventListener("keydown", (e) => {
  if (e.code === "Space" && !$("#dash").hidden && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) {
    e.preventDefault(); $("#playBtn").click();
  }
});

predForm(); legend(); initLaunch(); requestAnimationFrame(draw);

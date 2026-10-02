"use strict";
const $ = (s) => document.querySelector(s);
const api = async (path, body) => {
  const r = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  return r.json();
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const hhmm = (min) => { const m = Math.round(min) + 480; return `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`; };
const SUS_COLORS = ["#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231", "#911eb4", "#46f0f0", "#f032e6", "#bcf60c",
  "#fabebe", "#008080", "#e6beff", "#9a6324", "#fffac8", "#aaffc3", "#808000"];
const KEY = new Set(["trait", "alibi", "motive", "hide_district", "hide_type", "hide_found"]);
let SCHEMA = null, cfg = {}, preset = "classic", frame = null, CASE = null, SECRET = null, es = null, selected = -1,
  seenNotes = 0, view = null, hover = null, pulses = [];

/* ------------------------------------------------------------------ launch screen */
async function initLaunch() {
  SCHEMA = await api("/api/schema");
  cfg = {...SCHEMA.defaults};
  const cards = $("#presetCards");
  cards.innerHTML = "";
  for (const [k, p] of Object.entries(SCHEMA.presets)) {
    const d = document.createElement("div");
    d.className = "card" + (k === preset ? " on" : "");
    d.dataset.k = k;
    d.innerHTML = `<b>${k.replace(/_/g, " ")}</b><span>${esc(p.label)}</span>`;
    d.onclick = () => setPreset(k);
    cards.appendChild(d);
  }
  renderForm();
  const kf = SCHEMA.key_files.filter((k) => k.exists).map((k) => k.path);
  $("#keyStatus").innerHTML = `Key files found: ${kf.length ? kf.map((p) => `<code>${esc(p)}</code>`).join(", ") : "none"}.<br>
    Keys are read at call time and never logged or sent to the browser.`;
  $("#runsList").innerHTML = SCHEMA.runs.length ? SCHEMA.runs.slice(0, 10).map((r) =>
    `<div>${esc(r.name)} <span class="muted">${r.parts ?? "-"}/3${r.solved ? " solved" : ""}${r.cost ? ` · $${r.cost.toFixed(4)}` : ""}</span></div>`).join("")
    : "<span class='muted'>none yet</span>";
  $("#rejoinBtn").hidden = !SCHEMA.running;
  estimate(); preview();
}

function setPreset(k) {
  preset = k;
  const keep = {};
  for (const x of ["seed", "speed", "jev_model", "jev_key", "chat_model", "chat_key", "concurrency"]) keep[x] = cfg[x];
  cfg = {...SCHEMA.defaults, ...keep, ...SCHEMA.presets[k].overrides};
  document.querySelectorAll(".card").forEach((c) => c.classList.toggle("on", c.dataset.k === k));
  renderForm(); estimate(); preview();
}

function renderForm() {
  const form = $("#cfgForm");
  form.innerHTML = "";
  for (const [group, fields] of SCHEMA.schema) {
    const fs = document.createElement("fieldset");
    fs.innerHTML = `<legend>${group}</legend>`;
    if ((group.startsWith("Solo") && cfg.mode !== "solo") || (group.startsWith("Swarm") && cfg.mode !== "swarm")) fs.className = "dim";
    for (const [key, label, kind, extra] of fields) {
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
        if (key === "mode") renderForm();
        estimate();
        if (["seed", "n_addresses", "n_suspects", "n_motives", "n_hideouts", "redundancy", "lie_rate", "red_herring_rate", "pointer_rate"].includes(key)) preview();
      };
      const lab = document.createElement("label"); lab.htmlFor = input.id; lab.textContent = label;
      row.append(lab, input);
      fs.appendChild(row);
    }
    form.appendChild(fs);
  }
}

let pvTimer = null;
function preview() {
  clearTimeout(pvTimer);
  pvTimer = setTimeout(async () => {
    const q = new URLSearchParams();
    for (const k of ["seed", "n_addresses", "n_suspects", "n_motives", "n_hideouts", "redundancy", "lie_rate", "red_herring_rate", "pointer_rate"]) q.set(k, cfg[k]);
    const r = await api("/api/preview?" + q);
    const c = $("#preview");
    drawMap(c, {map: r.map, brief: r.brief}, null, {preview: true});
    const k = r.kinds;
    const key = ["trait", "alibi", "motive", "hide_district", "hide_type"].reduce((s, x) => s + (k[x] || 0), 0);
    $("#pvInfo").textContent = `${r.map.addresses.length} addresses · ${Object.keys(r.brief.suspects).length} suspects`;
    $("#pvKinds").innerHTML = `${key} key leads, ${k.lie || 0} lies, ${k.pointer || 0} pointers, ${k.herring || 0} red herrings,
      ${k.bland || 0} empty. Solvable by counting all leads: ${Object.values(r.solvable).every(Boolean) ? "yes" : "<span class='err'>no</span>"}.
      <br>${esc(r.brief.victim)}.`;
  }, 150);
}

function estimate() {
  let s;
  if (cfg.mode === "solo") {
    const steps = Math.min(cfg.visit_budget, Math.round(cfg.deadline_hours * 60 / 38)) + 1;
    s = `Solo: up to ${cfg.visit_budget} visits within ${cfg.deadline_hours} h (about ${steps} decisions).`;
    if (cfg.policy === "jev") s += `<br>Jev ≈ <b>$${(steps * 0.00024).toFixed(3)}</b> per case (measured ~$0.00024 per call, ~0.3 s each).`;
    else if (cfg.policy === "chat") s += `<br>gpt-6-astra ≈ <b>$${(steps * 0.018).toFixed(2)}</b> per case at list price
      ($${cfg.chat_price_in}/M in, $${cfg.chat_price_cached}/M cached, $${cfg.chat_price_out}/M out; ~3.5k tokens a step, ~4 s each).`;
    else s += "<br>Offline policy: no API calls, free.";
  } else {
    const calls = cfg.n_irregulars * cfg.swarm_ticks;
    s = `Swarm: ${cfg.n_irregulars} Irregulars × up to ${cfg.swarm_ticks} ticks = at most <b>${calls.toLocaleString()}</b> decisions.`;
    if (cfg.swarm_policy === "hybrid_genius") s += `<br>Jev actions only ≈ <b>$${(calls * 0.00006).toFixed(2)}</b> at most, plus up to ${cfg.hub_max_calls} gpt-6-astra calls at the Yard (≈ $0.02-0.05 each).`;
    else if (cfg.swarm_policy === "hybrid") s += `<br>Jev actions only ≈ <b>$${(calls * 0.00006).toFixed(2)}</b> at most; votes are counted exactly (free).`;
    else if (cfg.swarm_policy === "jev") s += `<br>Jev ≈ <b>$${(calls * 0.000105).toFixed(2)}</b> per case at most (~$0.0001 per call); each tick waits ≈ 2 s for its calls.`;
    else s += "<br>Offline policy: no API calls, free.";
    if (cfg.budget_cap_usd > 0) s += `<br>Capped at $${cfg.budget_cap_usd}; after that the reflex rule decides.`;
  }
  $("#estimate").innerHTML = s;
}

async function testModel(which) {
  const o = $("#testOut"); o.hidden = false; o.textContent = `Testing ${which}…`;
  const r = await api("/api/test", {which, cfg});
  o.textContent = r.ok ? `OK ${r.model} in ${r.latency}s\n${JSON.stringify(r.reply, null, 1)}` : `Failed: ${r.error}`;
}

async function launch() {
  $("#launchErr").textContent = "";
  $("#launchBtn").disabled = true;
  const r = await api("/api/launch", {cfg});
  $("#launchBtn").disabled = false;
  if (!r.ok) { $("#launchErr").textContent = r.error; return; }
  startDash();
}

/* ------------------------------------------------------------------ dashboard */
function startDash() {
  $("#launch").hidden = true; $("#dash").hidden = false; $("#endBanner").hidden = true;
  frame = null; CASE = null; SECRET = null; selected = -1; seenNotes = 0; pulses = [];
  $("#tTruth").checked = false;
  if (es) es.close();
  es = new EventSource("/api/stream");
  es.onmessage = (ev) => onFrame(JSON.parse(ev.data));
}

function onFrame(f) {
  if (f.case) CASE = f.case;
  if (f.secret) SECRET = f.secret;
  const first = !frame;
  frame = f;
  const solo = f.mode === "solo";
  document.querySelectorAll(".solo-only").forEach((e) => e.hidden = !solo);
  document.querySelectorAll(".swarm-only").forEach((e) => e.hidden = solo);
  if (first) { renderBrief(); buildGuessForm(); legend(); if (!solo) buildKnobs(); }
  $("#modeTag").textContent = solo ? `Solo · ${f.policy}` : `Swarm · ${f.irregulars.length} Irregulars · ${f.policy}`;
  $("#clock").textContent = hhmm(f.minute);
  const prog = solo ? Math.max(f.visits / f.budget, f.minute / f.deadline) : f.tick / f.ticks;
  $("#progFill").style.width = `${Math.min(100, 100 * prog)}%`;
  $("#progText").textContent = solo ? `visit ${f.visits}/${f.budget}` : `tick ${f.tick}/${f.ticks}`;
  $("#runTag").textContent = f.run;
  $("#playBtn").textContent = f.paused ? "Resume" : "Pause";
  const sp = $("#speed");
  if (document.activeElement !== sp) sp.value = Math.log10(f.speed);
  $("#speedVal").textContent = `${f.speed.toFixed(f.speed < 10 ? 1 : 0)}/s`;
  if (!solo) for (const s of f.shares) pulses.push({x: s[1], y: s[2], t0: performance.now()});
  if (solo) { renderNotebook(f); renderBelief(f); } else { renderTally(f); drawSeries(f); if (selected >= 0) loadIrregular(selected); syncKnobs(f); }
  renderInference(f); renderEvents(f); renderGuesses(f);
  if (f.ended) showEnd(f);
}

function truthOn() { return $("#tTruth").checked && SECRET; }

function renderBrief() {
  if (!CASE) return;
  const b = CASE.brief;
  $("#brief").innerHTML = `<div><b>Victim:</b> ${esc(b.victim)}; lived at ${esc(b.victim_home)}.</div>
    <div class="mt"><b>Suspects</b></div>` + Object.entries(b.suspects).map(([k, v], i) =>
    `<div class="sus"><span style="color:${SUS_COLORS[i % 16]}">●</span> <b>${k}</b> ${esc(v)}</div>`).join("") +
    `<div class="mt"><b>Motives</b> ${Object.entries(b.motives).map(([k, v]) => `<b>${k}</b> ${esc(v)}`).join(" · ")}</div>
    <div class="mt"><b>Possible hideouts</b> ${Object.entries(b.possible_hideouts).map(([k, v]) => `<b>${k}</b> ${esc(v)}`).join(" · ")}</div>`;
}

function name(kind, id) {
  if (!CASE || !id) return id || "?";
  if (kind === "culprit") return `${id} ${(CASE.brief.suspects[id] || "").split(",")[0]}`;
  if (kind === "motive") return `${id} ${(CASE.brief.motives[id] || "").split(":")[0]}`;
  return `${id} ${(CASE.brief.possible_hideouts[id] || "").split(",")[0]}`;
}

function renderNotebook(f) {
  const el = $("#notebook");
  const kinds = truthOn() ? SECRET.lead_kinds : null;
  el.innerHTML = f.notebook.slice().reverse().map((n, i) => {
    const k = kinds ? kinds[n.address] : "";
    const cls = k === "lie" ? "k-lie" : KEY.has(k) ? "k-key" : k === "pointer" ? "k-pointer" : "";
    const fresh = f.notebook.length > seenNotes && i === 0 ? " fresh" : "";
    const a = CASE ? CASE.map.addresses.find((x) => x.id === n.address) : null;
    return `<div class="nb ${cls}${fresh}"><div class="addr">${n.n ? `#${n.n} · ` : ""}${hhmm(n.minute)} · ${n.address} ${esc(a ? a.street + ", " + a.district : "")}${k ? ` · <i>${k}</i>` : ""}</div>${esc(n.text)}</div>`;
  }).join("");
  seenNotes = f.notebook.length;
  $("#nbMeta").textContent = `${f.notebook.length} leads`;
}

function renderBelief(f) {
  const L = f.last;
  if (!L) { $("#belief").innerHTML = "<span class='muted small'>waiting for the first decision…</span>"; return; }
  const truth = truthOn() ? SECRET.truth : (f.ended && SECRET ? SECRET.truth : null);
  let h = "";
  for (const k of ["culprit", "motive", "hideout"]) {
    const b = L.belief[k] || {};
    const rows = Object.entries(b).sort((x, y) => y[1] - x[1]).slice(0, 5);
    h += `<div class="bgroup"><h4>${k}</h4>` + rows.map(([id, p]) => {
      const cls = truth ? (id === truth[k] ? "truth" : id === L.pick[k] ? "wrongpick" : "") : "";
      return `<div class="brow ${cls}"><span class="nm">${esc(name(k, id))}</span><div class="bar2"><div style="width:${100 * p}%"></div></div><span>${(100 * p).toFixed(0)}%</span></div>`;
    }).join("") + "</div>";
  }
  $("#belief").innerHTML = h;
  const m = L.meta || {};
  $("#decMeta").textContent = m.model ? `${m.model.replace("typesafe/", "")} · ${m.in || 0}+${m.out || 0} tok · $${(m.cost || 0).toFixed(4)}` : L.source;
  let note = L.note ? esc(L.note) : "";
  if (L.action_probs) note += `<br>move: ${Object.entries(L.action_probs).map(([k, v]) => `${k.replace("VISIT_", "")} ${(100 * v).toFixed(0)}%`).join(", ")}`;
  $("#decNote").innerHTML = `<b>${esc(L.action || "accuse")}</b> ${note}`;
}

function renderTally(f) {
  $("#need").textContent = f.need;
  const cv = f.coverage;
  $("#cov").textContent = `${cv.key_leads_found}/${cv.key_leads} key leads seen · ${cv.addresses} addresses walked`;
  const truth = SECRET && (truthOn() || f.ended) ? SECRET.truth : null;
  const maxV = Math.max(f.need * 1.2, ...f.tally.map((t) => t[1]));
  let h = `<div class="small muted">Full answers (culprit / motive / hideout)</div>`;
  h += f.tally.length ? f.tally.slice(0, 5).map(([[c, m, hd], n]) => {
    const ok = truth && c === truth.culprit && m === truth.motive && hd === truth.hideout;
    const ci = CASE ? Object.keys(CASE.brief.suspects).indexOf(c) : 0;
    return `<div class="trow"><div><span style="color:${ok ? "var(--good)" : "inherit"}">${esc(name("culprit", c))} / ${m} / ${hd}</span>
      <div class="qbar"><div style="width:${100 * n / maxV}%;background:${SUS_COLORS[ci % 16]}"></div><i style="left:${100 * f.need / maxV}%"></i></div></div><b>${n}</b></div>`;
  }).join("") : `<div class="small muted">no Irregular holds a full answer yet</div>`;
  h += `<div class="small muted mt">Culprit votes</div><div class="small">` + (f.parts.culprit.slice(0, 6).map(([c, n]) => {
    const ci = CASE ? Object.keys(CASE.brief.suspects).indexOf(c) : 0;
    return `<span style="color:${SUS_COLORS[ci % 16]}">●</span> ${c} ${n}`;
  }).join(" &nbsp; ") || "none") + "</div>";
  if (f.hub) {
    const A = f.hub.answer;
    h = `<div class="small" style="margin-bottom:6px"><b>Holmes at Scotland Yard</b> has ${f.hub.leads} leads.
      ${A ? `Latest: ${esc(name("culprit", A.culprit))} / ${A.motive} / ${A.hideout} ${A.confident ? "<b>(sure)</b>" : "(not sure yet)"}<br><span class="muted">${esc(A.note || "")}</span>` : "No announcement yet."}</div>` + h;
  }
  $("#tally").innerHTML = h;
}

function drawSeries(f) {
  const c = $("#series"), dpr = devicePixelRatio || 1, W = c.clientWidth, H = 120;
  c.width = W * dpr; c.height = H * dpr;
  const g = c.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
  const S = f.series; const n = f.ticks;
  const ymax = Math.max(f.need * 1.2, ...S.map((r) => Math.max(r.top, r.firm)));
  const X = (t) => 24 + (W - 30) * t / n, Y = (v) => H - 14 - (H - 22) * v / ymax;
  g.strokeStyle = "#3d372c"; g.fillStyle = "#a59a82"; g.font = "10px sans-serif";
  g.beginPath(); g.moveTo(24, Y(f.need)); g.lineTo(W - 6, Y(f.need)); g.setLineDash([4, 3]); g.stroke(); g.setLineDash([]);
  g.fillText("quorum", W - 46, Y(f.need) - 3); g.fillText("0", 4, H - 12); g.fillText(Math.round(ymax), 2, 12);
  const line = (key, color, w) => { g.strokeStyle = color; g.lineWidth = w; g.beginPath(); S.forEach((r, i) => i ? g.lineTo(X(r.tick), Y(r[key])) : g.moveTo(X(r.tick), Y(r[key]))); g.stroke(); };
  if (S.length) {
    line("firm", "#6b6250", 1); line("top", "#d9a441", 2);
    if (SECRET && (truthOn() || f.ended)) { line("truth", "#7cc47c", 1.5); line("frame", "#e0675b", 1.2); }
  }
  g.fillStyle = "#a59a82";
  g.fillText("leading answer", 28, 10);
}

async function loadIrregular(i) {
  const d = await api(`/api/irregular?id=${i}`);
  if (d.error) return;
  $("#selId").textContent = i;
  $("#selTraits").textContent = truthOn() && d.traits.length ? `(${d.traits.join(", ")})` : "";
  const L = d.last || {};
  const v = d.vote;
  $("#irrDetail").innerHTML = `<div>At <b>${esc(d.observation.you.at)}</b> · hears ${d.observation.you.irregulars_within_earshot} Irregulars</div>
    <div>Last: <b>${esc(L.action || "-")}</b> <span class="muted">(${esc(L.source || "")})</span> → ${esc(L.result || "")}</div>
    <div>Vote: ${esc(v.culprit ? name("culprit", v.culprit) : "unsure")} / ${v.motive || "unsure"} / ${v.hideout || "unsure"}</div>
    <div class="mt"><b>Leads it holds</b></div>` + d.observation.my_leads.map((l) => `<div>• ${esc(l.lead)} <span class="muted">(${esc(l.source)})</span></div>`).join("");
}

function card(label, value, title) { return `<div class="mc" title="${esc(title || "")}"><b>${value}</b><span>${label}</span></div>`; }

function renderInference(f) {
  const i = f.inference;
  $("#infCards").innerHTML = [
    card("decisions", i.decisions), card("model calls", i.calls), card("p50 latency", i.latency_p50 != null ? i.latency_p50 + " s" : "-"),
    card("tokens in", (i.tokens_in / 1000).toFixed(1) + "k", `${i.tokens_cached} cached`), card("tokens out", (i.tokens_out / 1000).toFixed(1) + "k"),
    card("cost", "$" + i.cost.toFixed(4)), card("fallbacks", i.fallbacks), card("timeouts", i.timeouts),
    card("model", (i.models[0] || i.policy).replace("typesafe/", "")),
  ].join("");
  $("#errors").innerHTML = f.errors.map(esc).join("<br>");
}

function renderEvents(f) {
  const el = $("#events");
  const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 4;
  el.innerHTML = f.events.map((e) => `<div class="${e.kind}"><span class="muted">${hhmm(e.t)}</span> ${e.address ? `<span class="muted">${e.address}</span> ` : ""}${esc(e.detail)}</div>`).join("");
  if (atBottom) el.scrollTop = el.scrollHeight;
}

function buildGuessForm() {
  if (!CASE) return;
  const fill = (sel, obj, kind) => { sel.innerHTML = ""; for (const k of Object.keys(obj)) sel.append(new Option(name(kind, k), k)); };
  fill($("#gC"), CASE.brief.suspects, "culprit"); fill($("#gM"), CASE.brief.motives, "motive"); fill($("#gH"), CASE.brief.possible_hideouts, "hideout");
}

function renderGuesses(f) {
  $("#guesses").innerHTML = f.guesses.map((g) => `<div>${hhmm(g.minute)} (${f.mode === "solo" ? "visit" : "tick"} ${g.progress}): ${g.culprit} / ${g.motive} / ${g.hideout}
    <b>${g.status === "open" ? "" : g.status}</b></div>`).join("") || "<span class='muted'>Lock in a guess; it is scored against the truth and the detective at the end.</span>";
}

const KNOBS = [["comm_range", "Shouting range (x10 m)", 0, 400, 5], ["bandwidth", "Messages per tick", 0, 12, 1],
  ["forget_rate", "Forget chance per tick", 0, 1, 0.05], ["quorum_frac", "Quorum share", 0.05, 1, 0.01]];
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

function showEnd(f) {
  const b = $("#endBanner");
  const t = SECRET ? SECRET.truth_names : null;
  const o = f.mode === "solo" ? f.accusation : f.outcome;
  if (!o || !t) return;
  const mark = (k) => o.ok[k] ? "<span class='ok'>✓</span>" : "<span class='no'>✗</span>";
  const head = f.mode === "solo"
    ? `<b>${o.forced ? "Out of time or visits: forced accusation" : "Accusation"}</b> after ${o.visits} visits, at ${hhmm(o.minute)}.`
    : o.quorum ? `<b>Quorum</b> of ${o.votes} Irregulars at tick ${o.tick}.` : `<b>Case went cold</b>: no quorum in ${o.tick} ticks (best ${o.votes}/${o.need}); plurality shown.`;
  b.innerHTML = `${head} Cost $${f.inference.cost.toFixed(4)}, ${(f.inference.tokens_in / 1000).toFixed(1)}k tokens in.<br>
    Culprit ${mark("culprit")} ${esc(name("culprit", o.culprit))} — truth: ${esc(t.culprit)}<br>
    Motive ${mark("motive")} ${esc(name("motive", o.motive))} — truth: ${esc(t.motive)}<br>
    Hideout ${mark("hideout")} ${esc(name("hideout", o.hideout))} — truth: ${esc(t.hideout)}
    ${f.guesses.length ? `<br>Your best guess: ${Math.max(...f.guesses.map((g) => parseInt(g.status) || 0))}/3.` : ""}
    <button id="hideEnd">Close</button><button id="againBtn">New run</button>`;
  b.hidden = false;
  $("#hideEnd").onclick = () => b.hidden = true;
  $("#againBtn").onclick = () => { if (es) es.close(); $("#dash").hidden = true; $("#launch").hidden = false; initLaunch(); };
  $("#tTruth").checked = true;
}

/* ------------------------------------------------------------------ map */
const DIST_COLORS = {"Kensington": "#3a3226", "Marylebone": "#33302a", "Bloomsbury": "#2f3129", "Soho": "#372b2b",
  "Covent Garden": "#2e2d33", "Westminster": "#2c3330", "The City": "#36322a", "Whitechapel": "#352d27",
  "Southwark": "#2b3136", "Limehouse": "#2d2f2b"};

function mapView(c) {
  const W = c.clientWidth, H = c.clientHeight;
  const s = Math.min(W / 1000, H / 700);
  return {s, ox: (W - 1000 * s) / 2, oy: (H - 700 * s) / 2, W, H};
}

function drawMap(c, cs, f, opt = {}) {
  if (!cs) return;
  const dpr = devicePixelRatio || 1;
  c.width = c.clientWidth * dpr; c.height = c.clientHeight * dpr;
  const g = c.getContext("2d"); g.scale(dpr, dpr);
  const v = mapView(c); if (!opt.preview) view = v;
  const P = (x, y) => [v.ox + x * v.s, v.oy + y * v.s];
  const M = cs.map;
  g.fillStyle = "#241f18"; g.fillRect(0, 0, v.W, v.H);
  // districts
  for (const d of M.districts) {
    const [x, y] = P(d.x, d.y);
    const gr = g.createRadialGradient(x, y, 5, x, y, 110 * v.s);
    gr.addColorStop(0, DIST_COLORS[d.name] || "#333"); gr.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = gr; g.beginPath(); g.arc(x, y, 110 * v.s, 0, 7); g.fill();
  }
  // river
  g.strokeStyle = "#34505e"; g.lineWidth = 16 * v.s; g.lineCap = "round"; g.lineJoin = "round"; g.beginPath();
  M.thames.forEach(([x, y], i) => { const [a, b] = P(x, y); i ? g.lineTo(a, b) : g.moveTo(a, b); }); g.stroke();
  if (!opt.preview) { g.fillStyle = "#4f6f7d"; g.font = `italic ${Math.max(9, 12 * v.s)}px Georgia`; const [rx, ry] = P(210, 548); g.fillText("River Thames", rx, ry); }
  const A = {}; for (const a of M.addresses) A[a.id] = a;
  // streets
  g.strokeStyle = "rgba(165,154,130,0.16)"; g.lineWidth = 1;
  g.beginPath(); for (const [i, j] of M.edges) { const [x1, y1] = P(A[i].x, A[i].y), [x2, y2] = P(A[j].x, A[j].y); g.moveTo(x1, y1); g.lineTo(x2, y2); } g.stroke();
  // district labels
  g.fillStyle = "rgba(239,230,210,0.35)"; g.font = `${Math.max(9, 13 * v.s)}px Georgia`; g.textAlign = "center";
  for (const d of M.districts) { const [x, y] = P(d.x, d.y - 62); g.fillText(d.name, x, y); }
  g.textAlign = "left";
  const solo = f && f.mode === "solo";
  const visited = new Set(solo ? f.path : []);
  const truth = !opt.preview && truthOn() ? SECRET : null;
  // addresses
  for (const a of M.addresses) {
    const [x, y] = P(a.x, a.y);
    let col = "rgba(239,230,210,0.45)", r = Math.max(1.8, 2.6 * v.s);
    if (truth) {
      const k = truth.lead_kinds[a.id];
      col = k === "lie" ? "#e0675b" : KEY.has(k) ? "#7cc47c" : k === "pointer" ? "#6fa8dc" : k === "herring" ? "rgba(217,164,65,0.55)" : col;
    }
    if (visited.has(a.id)) { g.fillStyle = "rgba(217,164,65,0.25)"; g.beginPath(); g.arc(x, y, r * 3.2, 0, 7); g.fill(); col = truth ? col : "#d9a441"; r *= 1.4; }
    if (hover && hover.id === a.id) r *= 1.8;
    g.fillStyle = col; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill();
  }
  // landmarks
  const mark = (id, label, color, shape) => {
    const a = A[id]; if (!a) return; const [x, y] = P(a.x, a.y); const s = Math.max(4, 6 * v.s);
    g.strokeStyle = color; g.fillStyle = color; g.lineWidth = 2;
    if (shape === "x") { g.beginPath(); g.moveTo(x - s, y - s); g.lineTo(x + s, y + s); g.moveTo(x + s, y - s); g.lineTo(x - s, y + s); g.stroke(); }
    else if (shape === "sq") g.strokeRect(x - s, y - s, 2 * s, 2 * s);
    else if (shape === "tri") { g.beginPath(); g.moveTo(x, y - s - 2); g.lineTo(x + s, y + s); g.lineTo(x - s, y + s); g.closePath(); g.stroke(); }
    else if (shape === "home") { g.beginPath(); g.arc(x, y, s * 0.9, 0, 7); g.stroke(); }
    else { g.beginPath(); for (let k = 0; k < 10; k++) { const rr = k % 2 ? s * 0.45 : s * 1.1, an = -Math.PI / 2 + k * Math.PI / 5; g.lineTo(x + rr * Math.cos(an), y + rr * Math.sin(an)); } g.closePath(); g.fill(); }
    if (label) { g.font = `${Math.max(9, 11 * v.s)}px sans-serif`; g.fillText(label, x + s + 3, y + 4); }
  };
  mark(M.baker, opt.preview ? "" : "221B", "#d9a441", "star");
  mark(M.yard, opt.preview ? "" : "Yard", "#6fa8dc", "sq");
  mark(M.scene, opt.preview ? "" : "scene", "#e0675b", "x");
  const sids = Object.keys(M.suspect_homes);
  for (const [h, id] of Object.entries(M.hideouts)) {
    const isT = truth && truth.truth.hideout === h;
    mark(id, h, isT ? "#7cc47c" : "#b9a77e", "tri");
  }
  if (!opt.preview) sids.forEach((s, i) => {
    const isT = truth && truth.truth.culprit === s;
    mark(M.suspect_homes[s], s, isT ? "#7cc47c" : SUS_COLORS[i % 16], "home");
  });
  if (!f) return;
  if (solo) {
    // path
    g.strokeStyle = "rgba(217,164,65,0.75)"; g.lineWidth = 2; g.setLineDash([5, 4]); g.beginPath();
    f.path.forEach((id, i) => { const [x, y] = P(A[id].x, A[id].y); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke(); g.setLineDash([]);
    const [x, y] = P(A[f.at].x, A[f.at].y);
    const t = performance.now() / 400;
    g.strokeStyle = "#ffd27a"; g.lineWidth = 2; g.beginPath(); g.arc(x, y, 9 + 3 * Math.sin(t), 0, 7); g.stroke();
    g.fillStyle = "#111"; g.beginPath(); g.arc(x, y, 6, 0, 7); g.fill();
    g.fillStyle = "#ffd27a"; g.font = "bold 9px Georgia"; g.textAlign = "center"; g.fillText("H", x, y + 3); g.textAlign = "left";
  } else {
    const now = performance.now();
    pulses = pulses.filter((p) => now - p.t0 < 900);
    for (const p of pulses) {
      const k = (now - p.t0) / 900; const [x, y] = P(p.x, p.y);
      g.strokeStyle = `rgba(217,164,65,${0.5 * (1 - k)})`; g.lineWidth = 1.2; g.beginPath(); g.arc(x, y, f.comm_range * v.s * k, 0, 7); g.stroke();
    }
    if (f.hub && A[f.hub.yard]) {  // the Yard's listening range
      const [yx, yy] = P(A[f.hub.yard].x, A[f.hub.yard].y);
      g.strokeStyle = "rgba(111,168,220,0.5)"; g.setLineDash([4, 4]); g.beginPath(); g.arc(yx, yy, f.comm_range * v.s, 0, 7); g.stroke(); g.setLineDash([]);
    }
    const order = CASE ? Object.keys(CASE.brief.suspects) : [];
    for (const r of f.irregulars) {
      const [i, ax, ay, cu, , , flags] = r;
      const jit = (i * 2.399963) % 6.283, rad = 5 + (i * 3.7) % 7;
      const [x, y] = P(ax + rad * Math.cos(jit), ay + rad * Math.sin(jit));
      const ci = order.indexOf(cu);
      g.fillStyle = cu ? SUS_COLORS[ci % 16] : "#8a8170";
      g.beginPath(); g.arc(x, y, i === selected ? 5 : 3.2, 0, 7); g.fill();
      if (truth && (flags & 1)) { g.strokeStyle = "#e0675b"; g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 5.5, 0, 7); g.stroke(); }
      if (i === selected) { g.strokeStyle = "#fff"; g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 7, 0, 7); g.stroke(); }
    }
  }
}

function legend() {
  const t = truthOn();
  let h = `<span><i style="background:#d9a441"></i>221B Baker Street</span><span><i style="background:#e0675b"></i>scene (×)</span>
    <span><i style="background:#b9a77e"></i>possible hideout (▲)</span><span><i style="border:2px solid #aaa;background:none"></i>suspect home</span>`;
  if (frame && frame.mode === "solo") h += `<span><i style="background:#d9a441;opacity:.6"></i>visited</span>`;
  else h += `<span><i style="background:#8a8170"></i>Irregular, coloured by culprit vote</span>`;
  if (t) h += `<span><i style="background:#7cc47c"></i>true key lead</span><span><i style="background:#e0675b"></i>lie</span><span><i style="background:#6fa8dc"></i>pointer</span>`;
  $("#legend").innerHTML = h;
}

function loop() {
  if (frame && CASE && !$("#dash").hidden) { drawMap($("#map"), CASE, frame); }
  requestAnimationFrame(loop);
}

function onMapMove(ev) {
  if (!view || !CASE) return;
  const rect = $("#map").getBoundingClientRect();
  const mx = (ev.clientX - rect.left - view.ox) / view.s, my = (ev.clientY - rect.top - view.oy) / view.s;
  let best = null, bd = 1e9;
  for (const a of CASE.map.addresses) { const d = (a.x - mx) ** 2 + (a.y - my) ** 2; if (d < bd) { bd = d; best = a; } }
  const tip = $("#tip");
  if (!best || bd > 225) { hover = null; tip.hidden = true; return; }
  hover = best;
  let lead = "";
  if (frame && frame.mode === "solo") { const n = frame.notebook.find((x) => x.address === best.id); if (n) lead = `<div class="mt">${esc(n.text)}</div>`; }
  if (truthOn()) lead += `<div class="muted">lead kind: ${SECRET.lead_kinds[best.id]}</div>`;
  tip.innerHTML = `<b>${best.id}</b> ${esc(best.street)}, ${esc(best.district)} <span class="muted">(${esc(best.type)})</span>${lead}`;
  tip.style.left = `${ev.clientX - rect.left + 14}px`; tip.style.top = `${ev.clientY - rect.top + 10}px`; tip.hidden = false;
}

function onMapClick(ev) {
  if (!frame || frame.mode !== "swarm" || !view) return;
  const rect = $("#map").getBoundingClientRect();
  const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
  let best = -1, bd = 1e9;
  for (const r of frame.irregulars) {
    const [i, ax, ay] = r; const jit = (i * 2.399963) % 6.283, rad = 5 + (i * 3.7) % 7;
    const x = view.ox + (ax + rad * Math.cos(jit)) * view.s, y = view.oy + (ay + rad * Math.sin(jit)) * view.s;
    const d = (x - mx) ** 2 + (y - my) ** 2; if (d < bd) { bd = d; best = i; }
  }
  if (best >= 0 && bd < 200) { selected = best; loadIrregular(best); }
}

/* ------------------------------------------------------------------ wiring */
$("#launchBtn").onclick = launch;
$("#rejoinBtn").onclick = startDash;
$("#testJev").onclick = () => testModel("jev");
$("#testChat").onclick = () => testModel("chat");
$("#playBtn").onclick = () => api("/api/cmd", {op: frame && frame.paused ? "resume" : "pause"});
$("#stepBtn").onclick = () => api("/api/cmd", {op: "step", n: 1});
$("#speed").onchange = (e) => api("/api/cmd", {op: "set", key: "speed", value: Math.pow(10, parseFloat(e.target.value))});
$("#newRun").onclick = () => { if (es) es.close(); $("#dash").hidden = true; $("#launch").hidden = false; initLaunch(); };
$("#tTruth").onchange = async () => {
  if ($("#tTruth").checked && !SECRET) SECRET = await api("/api/secret");
  legend(); if (frame) onFrame(frame);
};
$("#gGo").onclick = () => api("/api/guess", {culprit: $("#gC").value, motive: $("#gM").value, hideout: $("#gH").value});
$("#map").addEventListener("mousemove", onMapMove);
$("#map").addEventListener("mouseleave", () => { hover = null; $("#tip").hidden = true; });
$("#map").addEventListener("click", onMapClick);
addEventListener("keydown", (e) => { if (e.code === "Space" && !$("#dash").hidden && e.target.tagName !== "INPUT") { e.preventDefault(); $("#playBtn").click(); } });
addEventListener("resize", () => { if (!$("#launch").hidden) preview(); });
legend();
initLaunch();
requestAnimationFrame(loop);

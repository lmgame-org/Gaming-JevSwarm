"use strict";
const $ = (s) => document.querySelector(s);
const api = async (path, body) => {
  const r = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  return r.json();
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const hhmm = (min) => { const m = Math.round(min) + 480; return `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`; };
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)");

// Suspect and district palettes: distinct hues that stay readable on both map papers.
const SUS_COLORS = ["#d1495b", "#2a9d8f", "#e9a03b", "#3d6fd1", "#8e5bd0", "#5c9e3a", "#d16ba5", "#1f9fc4", "#b5651d",
  "#6b7f2a", "#c4453c", "#4a8f8a", "#a07ad6", "#7d8590", "#d08a2e", "#2f7d5a"];
const DISTRICT_HUES = {"Kensington": "#d1495b", "Marylebone": "#e9a03b", "Bloomsbury": "#b5a12a", "Soho": "#5c9e3a",
  "Covent Garden": "#2a9d8f", "Westminster": "#1f9fc4", "The City": "#3d6fd1", "Whitechapel": "#8e5bd0",
  "Southwark": "#d16ba5", "Limehouse": "#b5651d"};
const KEY = new Set(["trait", "alibi", "motive", "hide_district", "hide_type", "hide_found"]);
// Measured on the 20-case benchmark (2 Oct 2026); hybrid + Yard genius from the 3-case pilot.
const BENCH = [
  {label: "Solo · gpt-6-astra", stat: "11/20 · $0.35", cfg: {mode: "solo", policy: "chat"}},
  {label: "Solo · Jev", stat: "5/20 · $0.005", cfg: {mode: "solo", policy: "jev"}},
  {label: "Solo · rule algorithm", stat: "9/20 · free", cfg: {mode: "solo", policy: "rule"}},
  {label: "Solo · random", stat: "0/20 · free", cfg: {mode: "solo", policy: "random"}},
  {label: "Baker Street Irregulars · gpt-6-astra Holmes, Jev boys", stat: "19/20 · $0.62", cfg: {mode: "swarm", swarm_policy: "baker_street", holmes: "chat", boy_policy: "jev", n_irregulars: 12, swarm_ticks: 48}},
  {label: "Baker Street Irregulars · counting Holmes, Jev boys", stat: "19/20 · $0.002", cfg: {mode: "swarm", swarm_policy: "baker_street", holmes: "rule", boy_policy: "jev", n_irregulars: 12, swarm_ticks: 48}},
  {label: "Baker Street Irregulars · counting Holmes, rule boys", stat: "19/20 · free", cfg: {mode: "swarm", swarm_policy: "baker_street", holmes: "rule", boy_policy: "rule", n_irregulars: 12, swarm_ticks: 48}},
  {label: "Swarm Detectives · Jev · 1 km", stat: "5/20 · $0.17", cfg: {mode: "swarm", swarm_policy: "jev", n_irregulars: 100, swarm_ticks: 32, comm_range: 100}},
  {label: "Swarm Detectives · Jev · 2 km", stat: "10/20 · $0.13", cfg: {mode: "swarm", swarm_policy: "jev", n_irregulars: 100, swarm_ticks: 32, comm_range: 200}},
  {label: "Swarm Detectives · rule · 1 km", stat: "13/20 · free", cfg: {mode: "swarm", swarm_policy: "rule", n_irregulars: 100, swarm_ticks: 32, comm_range: 100}},
  {label: "Swarm Detectives · rule · 2 km", stat: "18/20 · free", cfg: {mode: "swarm", swarm_policy: "rule", n_irregulars: 100, swarm_ticks: 32, comm_range: 200}},
  {label: "Swarm Detectives · random · 1 km", stat: "0/20 · free", cfg: {mode: "swarm", swarm_policy: "random", n_irregulars: 100, swarm_ticks: 32, comm_range: 100}},
  {label: "Swarm Detectives · hybrid · 1 km", stat: "10/20 · $0.21", cfg: {mode: "swarm", swarm_policy: "hybrid", n_irregulars: 100, swarm_ticks: 32, comm_range: 100}},
  {label: "Swarm Detectives · hybrid · 2 km", stat: "17/20 · $0.13", cfg: {mode: "swarm", swarm_policy: "hybrid", n_irregulars: 100, swarm_ticks: 32, comm_range: 200}},
];
const SOLO_OPTS = [
  {v: "chat", label: "gpt-6-astra", sub: "A large model that re-reads the whole notebook before each move", stat: "About $0.35 per case"},
  {v: "jev", label: "Jev", sub: "A fast, cheap model: one short decision per move", stat: "About $0.005 per case"},
  {v: "rule", label: "Rule algorithm", sub: "No model: follows tips and counts which facts agree", stat: "Free"},
  {v: "random", label: "Random", sub: "Visits at random and guesses: the floor to beat", stat: "Free"},
];
const HOLMES_OPTS = [
  {v: "chat", label: "gpt-6-astra", sub: "Reads every report and writes the next assignments itself", stat: "About $0.62 per case"},
  {v: "rule", label: "Exact counting algorithm", sub: "No model: tallies which facts agree and plans by fixed rules", stat: "About $0.002 per case (with Jev boys)"},
  {v: "jev", label: "Jev", sub: "Not available yet: Jev can't write assignments in this version", disabled: true},
];
const BOY_OPTS = [
  {v: "jev", label: "Jev", sub: "Decides which nearby door to try, whether to follow a suspect, and when to run back"},
  {v: "rule", label: "Rule algorithm", sub: "Works through the assignment in order and hurries back with a strong lead"},
  {v: "random", label: "Random", sub: "Makes every small choice at random"},
];
const OTHER_OPTS = [
  {v: "jev", label: "Jev swarm", sub: "Every boy chooses his moves and his vote with Jev", stat: "About $0.13-0.17 per case"},
  {v: "rule", label: "Rule swarm", sub: "Every boy follows the same simple rule; no model", stat: "Free"},
  {v: "hybrid", label: "Hybrid", sub: "Jev chooses moves and what to share; votes come from counting facts", stat: "About $0.13-0.21 per case"},
  {v: "hybrid_genius", label: "Hybrid + genius at the Yard", sub: "Leads shouted near Scotland Yard go to gpt-6-astra, who decides", stat: "About $0.41 per case"},
  {v: "random", label: "Random swarm", sub: "Random moves, shouts and votes: the floor to beat", stat: "Free"},
];
const TRACK_DEFAULTS = {
  solo: {mode: "solo"},
  baker: {mode: "swarm", swarm_policy: "baker_street", n_irregulars: 12, swarm_ticks: 48},
  other: {mode: "swarm", n_irregulars: 100, swarm_ticks: 32},
};

let SCHEMA = null, cfg = {}, PREVIEW_INFO = null, lastOther = "jev", frame = null, CASE = null, SECRET = null, es = null, selected = -1,
  seenNotes = 0, view = null, hover = null, pulses = [];

/* ------------------------------------------------------------------ theme */
function effectiveTheme() {
  const t = document.documentElement.dataset.theme;
  return t || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function applyThemeLabels() {
  const next = effectiveTheme() === "dark" ? "Light" : "Dark";
  document.querySelectorAll(".theme-toggle").forEach((b) => b.textContent = next);
}
function toggleTheme() {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("irregulars-theme", next); } catch (e) { /* storage unavailable */ }
  themeChanged();
}
function themeChanged() {
  applyThemeLabels();
  BASES.clear();
  if (!$("#launch").hidden) preview();
  if (frame) onFrame(frame, true);
}
try { const t = localStorage.getItem("irregulars-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* ignore */ }
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (!document.documentElement.dataset.theme) themeChanged(); });

function seriesVar(c) {
  if (!c) return "--ink";
  if (c.mode === "solo") return c.policy === "chat" ? "--genius" : c.policy === "jev" ? "--jev" : "--rule";
  const sp = c.swarm_policy;
  return sp === "baker_street" ? "--baker" : sp && sp.startsWith("hybrid") ? "--hybrid" : sp === "jev" ? "--jev" : "--rule";
}

/* ------------------------------------------------------------------ launch screen */
function trackOf(c) { return c.mode === "solo" ? "solo" : c.swarm_policy === "baker_street" ? "baker" : "other"; }
function squad() { return trackOf(cfg) === "solo" ? 0 : Math.max(1, cfg.n_irregulars | 0); }
function clockHours() { return trackOf(cfg) === "solo" ? cfg.deadline_hours : cfg.swarm_ticks * cfg.tick_min / 60; }

async function initLaunch() {
  SCHEMA = await api("/api/schema");
  if (!cfg.mode) cfg = {...SCHEMA.defaults};
  const kf = SCHEMA.key_files.filter((k) => k.exists).map((k) => k.path);
  $("#keyStatus").innerHTML = `<p>Key files found: ${kf.length ? kf.map((p) => `<code>${esc(p)}</code>`).join(", ") : "none"}.</p>
    <p class="muted">Keys are read when a call is made and are never logged or sent to the browser.</p>`;
  $("#runsList").innerHTML = SCHEMA.runs.length ? SCHEMA.runs.slice(0, 12).map((r) =>
    `<div>${esc(r.name)} · ${r.parts ?? "-"}/3${r.solved ? " solved" : ""}${r.cost ? ` · $${r.cost.toFixed(4)}` : ""}</div>`).join("")
    : "<span class='muted'>No runs yet.</span>";
  $("#rejoinBtn").hidden = !SCHEMA.running;
  refreshAll(true);
}

function refreshAll(withPreview = false) {
  renderTracks(); renderCase(); renderForm(); estimate();
  if (withPreview) preview();
}

function setCfg(patch, opts = {}) {
  Object.assign(cfg, patch);
  if (opts.render !== false) refreshAll(opts.preview);
  else { estimate(); if (opts.preview) preview(); }
}

function loadBench(i) {
  const b = BENCH[i]; if (!b) return;
  const keep = {};
  for (const x of ["seed", "speed", "jev_model", "jev_key", "chat_model", "chat_key", "concurrency"]) keep[x] = cfg[x];
  cfg = {...SCHEMA.defaults, ...keep, ...b.cfg};
  refreshAll(true);
}

function setTrack(t) {
  const cur = trackOf(cfg);
  if (cur === t) return;
  if (cur === "other") lastOther = cfg.swarm_policy;
  const patch = {...TRACK_DEFAULTS[t]};
  if (t === "other") patch.swarm_policy = lastOther || "jev";
  if (t === "other" && patch.swarm_policy === "hybrid_genius") patch.comm_range = 200;
  setCfg(patch);
}

/* small control builders */
function optGroup(title, note, opts, value, onPick, ser) {
  const g = document.createElement("div"); g.className = "group";
  g.innerHTML = `<h4>${esc(title)}</h4>${note ? `<p class="note">${esc(note)}</p>` : ""}`;
  const row = document.createElement("div"); row.className = "opts"; row.setAttribute("role", "radiogroup"); row.setAttribute("aria-label", title);
  for (const o of opts) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "opt"; b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(o.v === value));
    if (o.disabled) b.disabled = true;
    if (ser) b.style.setProperty("--ser", `var(${ser(o.v)})`);
    b.innerHTML = `<b>${esc(o.label)}</b><span class="sub">${esc(o.sub || "")}</span>${o.stat ? `<span class="stat">${esc(o.stat)}</span>` : ""}`;
    b.onclick = () => onPick(o.v);
    row.appendChild(b);
  }
  g.appendChild(row);
  return g;
}

function numCtl(label, value, {min, max, step = 1, hint = "", unit = ""}, onChange) {
  const d = document.createElement("div"); d.className = "ctl";
  const id = "c_" + label.replace(/\W+/g, "_").toLowerCase();
  d.innerHTML = `<label for="${id}">${esc(label)}${unit ? ` <span class="val">${esc(unit)}</span>` : ""}</label>
    <input id="${id}" type="number" min="${min}" max="${max}" step="${step}" value="${value}">${hint ? `<span class="hint">${hint}</span>` : ""}`;
  d.querySelector("input").onchange = (e) => { const v = parseFloat(e.target.value); if (!Number.isNaN(v)) onChange(Math.min(max, Math.max(min, v))); };
  return d;
}

function sliderCtl(label, value, {min, max, step, fmt, hint = "", off = false}, onChange) {
  const d = document.createElement("div"); d.className = "ctl" + (off ? " off" : "");
  const id = "s_" + label.replace(/\W+/g, "_").toLowerCase();
  d.innerHTML = `<label for="${id}">${esc(label)} <span class="val">${fmt(value)}</span></label>
    <input id="${id}" type="range" min="${min}" max="${max}" step="${step}" value="${value}" ${off ? "disabled" : ""}>
    ${hint ? `<span class="hint">${hint}</span>` : ""}`;
  const r = d.querySelector("input"), val = d.querySelector(".val");
  r.oninput = () => val.textContent = fmt(parseFloat(r.value));
  r.onchange = () => onChange(parseFloat(r.value));
  return d;
}

function toggleCtl(label, checked, hint, onChange) {
  const d = document.createElement("div"); d.className = "ctl";
  const id = "t_" + label.replace(/\W+/g, "_").toLowerCase();
  d.innerHTML = `<label class="toggle" for="${id}"><input id="${id}" type="checkbox" ${checked ? "checked" : ""}><span class="track" aria-hidden="true"></span>${esc(label)}</label>
    ${hint ? `<span class="hint">${esc(hint)}</span>` : ""}`;
  d.querySelector("input").onchange = (e) => onChange(e.target.checked);
  return d;
}

function ctlGrid(...items) { const d = document.createElement("div"); d.className = "ctls"; items.filter(Boolean).forEach((x) => d.appendChild(x)); return d; }

function benchLine(match) {
  const b = BENCH.find((x) => Object.entries(x.cfg).every(([k, v]) => ["n_irregulars", "swarm_ticks"].includes(k) || cfg[k] === v) &&
    (!match || match(x)));
  const d = document.createElement("div"); d.className = "bench-line";
  if (b) { const cost = b.stat.split(" · ")[1]; d.innerHTML = cost === "free" ? "Measured cost: <b>free</b> (no model calls)." : `Measured cost on 20 test cases: <b>${cost} per case</b>.`; }
  else d.textContent = "No measured cost for this exact setup yet; see the estimate on the right.";
  return d;
}

function renderTracks() {
  const t = trackOf(cfg);
  document.querySelectorAll("#tracks button").forEach((b) => {
    b.setAttribute("aria-selected", String(b.dataset.track === t));
    b.onclick = () => setTrack(b.dataset.track);
  });
  const p = $("#trackPanel"); p.innerHTML = "";
  const intro = document.createElement("p"); intro.className = "how";
  intro.innerHTML = {
    solo: "<b>How it works.</b> The detective starts at 221B Baker Street, takes a cab to one address at a time and reads the lead there. When it is sure, or runs out of visits or time, it names the culprit, motive and hideout.",
    baker: "<b>How it works.</b> Holmes stays at 221B and never visits an address himself. He hands out assignments; Wiggins splits the street boys across them; the boys check addresses on foot and run back to report. Holmes reads the reports, sends the boys out again, and names the answer when he is sure (or gives his best answer when time runs out).",
    other: "<b>How it works.</b> About 100 Irregulars start spread over the city with no one in charge. Each knows only what it finds and what nearby boys shout to it. The case closes when enough of them vote for the same answer; if they never agree in time, the case goes cold.",
  }[t];
  p.appendChild(intro);
  if (t === "solo") {
    p.appendChild(optGroup("The detective", "Who makes every decision: where to go next and what to accuse.", SOLO_OPTS, cfg.policy, (v) => setCfg({policy: v}),
      (v) => seriesVar({mode: "solo", policy: v})));
    p.appendChild(ctlGrid(
      numCtl("Most visits allowed", cfg.visit_budget, {min: 1, max: 200, unit: "visits", hint: "Each visit is a cab ride plus an interview"}, (v) => setCfg({visit_budget: v | 0})),
      numCtl("Interview length", cfg.interview_min, {min: 0, max: 240, unit: "case minutes", hint: "Time spent at each address"}, (v) => setCfg({interview_min: v})),
      cfg.policy === "jev" ? sliderCtl("Jev accuses when its readiness reaches", cfg.jev_accuse_at, {min: 0.1, max: 0.9, step: 0.05, fmt: (x) => x.toFixed(2),
        hint: "After each visit Jev rates how ready it is to accuse, from 0 to 1"}, (v) => setCfg({jev_accuse_at: v})) : null));
    p.appendChild(benchLine());
  } else if (t === "baker") {
    p.appendChild(optGroup("Holmes, the decision-maker", "Reads every report, decides where to send the boys, and alone names the answer.",
      HOLMES_OPTS, cfg.holmes, (v) => setCfg({holmes: v}), (v) => v === "chat" ? "--genius" : "--baker"));
    p.appendChild(optGroup("The street boys, his eyes on the street", "Carry out the assignments and report back. They never accuse anyone.",
      BOY_OPTS, cfg.boy_policy, (v) => setCfg({boy_policy: v}), (v) => v === "jev" ? "--jev" : "--rule"));
    p.appendChild(ctlGrid(
      numCtl("Number of street boys", cfg.n_irregulars, {min: 1, max: 100, unit: "boys", hint: "About a dozen in the stories"}, (v) => {
        const n = v | 0, bribed = Math.round(cfg.liar_frac * squad()), wrong = Math.round(cfg.misinformed_frac * squad());
        setCfg({n_irregulars: n, liar_frac: Math.min(1, bribed / n), misinformed_frac: Math.min(1, wrong / n)});
      }),
      toggleCtl("Wiggins collects reports", cfg.wiggins, "On: boys report to Wiggins at a post near their work, and he carries batches to Holmes. Off: every boy runs all the way back to 221B.", (v) => setCfg({wiggins: v})),
      toggleCtl("Pay the boys", cfg.pay === "shilling_guinea", "On: a shilling a day and a guinea for the key lead, so boys finish their assignment. Off: they give up after two addresses.",
        (v) => setCfg({pay: v ? "shilling_guinea" : "none"})),
      numCtl("Most planning rounds for Holmes", cfg.hq_max_calls, {min: 1, max: 64, unit: "rounds", hint: "Each round he reads all reports and sends boys out again"}, (v) => setCfg({hq_max_calls: v | 0}))));
    p.appendChild(benchLine());
  } else {
    p.appendChild(optGroup("Type of swarm", "How each boy decides where to go, what to shout and how to vote.", OTHER_OPTS, cfg.swarm_policy, (v) => {
      lastOther = v;
      setCfg(v === "hybrid_genius" ? {swarm_policy: v, comm_range: Math.max(cfg.comm_range, 200)} : {swarm_policy: v});
    }, (v) => seriesVar({mode: "swarm", swarm_policy: v})));
    p.appendChild(ctlGrid(
      numCtl("Number of Irregulars", cfg.n_irregulars, {min: 3, max: 400, unit: "boys", hint: "They start spread over the whole map"}, (v) => {
        const n = v | 0, bribed = Math.round(cfg.liar_frac * squad()), wrong = Math.round(cfg.misinformed_frac * squad());
        setCfg({n_irregulars: n, liar_frac: Math.min(1, bribed / n), misinformed_frac: Math.min(1, wrong / n)});
      }),
      sliderCtl("How far a shout carries", cfg.comm_range / 100, {min: 0.25, max: 4, step: 0.25, fmt: (x) => `${x.toFixed(2)} km`,
        hint: "Boys hear leads and votes from others within this distance"}, (v) => setCfg({comm_range: v * 100})),
      sliderCtl("Votes needed to close the case", cfg.quorum_frac, {min: 0.05, max: 1, step: 0.01, fmt: (x) => `${Math.round(x * 100)}% (${Math.max(2, Math.round(x * cfg.n_irregulars))} boys)`,
        hint: "This many boys must hold exactly the same answer"}, (v) => setCfg({quorum_frac: v})),
      toggleCtl("Defend against liars", cfg.corroboration === "address", "On: each address counts once, and a boy caught contradicting what another saw first-hand is no longer believed.",
        (v) => setCfg({corroboration: v ? "address" : "none"}))));
    p.appendChild(benchLine((b) => b.cfg.comm_range === undefined || b.cfg.comm_range === cfg.comm_range));
  }
}

function renderCase() {
  const p = $("#casePanel"); p.innerHTML = "";
  const t = trackOf(cfg), n = squad();
  const info = PREVIEW_INFO;
  const name = document.createElement("div");
  name.className = "case-name";
  name.innerHTML = info ? `${esc(info.title)} <span class="meta">${esc(info.sub)}</span>` : "&nbsp;";
  p.appendChild(name);
  const hrs = clockHours();
  p.appendChild(ctlGrid(
    numCtl("Case number", cfg.seed, {min: 0, max: 99999, hint: "The same number always gives the same map, people and leads"}, (v) => setCfg({seed: v | 0}, {preview: true})),
    numCtl("Addresses on the map", cfg.n_addresses, {min: 20, max: 300, hint: "Each holds one lead"}, (v) => setCfg({n_addresses: v | 0}, {preview: true})),
    numCtl("Suspects", cfg.n_suspects, {min: 3, max: 16, hint: "One of them is the culprit"}, (v) => setCfg({n_suspects: v | 0}, {preview: true})),
    numCtl("Time limit", +hrs.toFixed(2), {min: 1, max: 96, step: 0.25, unit: "case hours",
      hint: t === "solo" ? "The detective must accuse by then" : t === "baker" ? "At the limit Holmes gives his best answer" : "If the boys haven't agreed by then, the case goes cold"},
    (v) => t === "solo" ? setCfg({deadline_hours: v}) : setCfg({swarm_ticks: Math.max(1, Math.round(v * 60 / cfg.tick_min))})),
    sliderCtl("Red herrings", cfg.red_herring_rate, {min: 0, max: 1, step: 0.05, fmt: (x) => `${Math.round(x * 100)}%`,
      hint: "Share of addresses without real evidence whose lead looks suspicious but proves nothing"},
      (v) => setCfg({red_herring_rate: v}, {preview: true}))));
  const dec = document.createElement("div"); dec.className = "group";
  dec.innerHTML = `<h4>Who can't be trusted</h4>`;
  const lies = info ? info.lies : null;
  const noBoys = t === "solo";
  dec.appendChild(ctlGrid(
    sliderCtl("Witnesses who lie", cfg.lie_rate, {min: 0, max: 0.5, step: 0.05,
      fmt: (x) => `${Math.round(x * 100)}%`,
      hint: lies != null ? `This case has ${lies} lying witness${lies === 1 ? "" : "es"}. Each lie contradicts one true fact (true facts turn up at two addresses). Applies to every approach.` : "Applies to every approach."},
    (v) => setCfg({lie_rate: v}, {preview: true})),
    sliderCtl("Street boys who lie (bribed by Moriarty)", noBoys ? 0 : Math.round(cfg.liar_frac * n), {min: 0, max: Math.max(1, n), step: 1, off: noBoys,
      fmt: (x) => noBoys ? "n/a" : `${x} of ${n}`,
      hint: noBoys ? "Not used: a solo detective has no boys." : t === "baker" ? "They report made-up leads for every address they are sent to." : "They all push the same wrong answer with made-up leads and votes."},
    (v) => setCfg({liar_frac: v / n})),
    sliderCtl("Street boys who get a fact wrong", noBoys ? 0 : Math.round(cfg.misinformed_frac * n), {min: 0, max: Math.max(1, n), step: 1, off: noBoys,
      fmt: (x) => noBoys ? "n/a" : `${x} of ${n}`,
      hint: noBoys ? "Not used: a solo detective has no boys." : t === "baker" ? "Each brings back one wrong report." : "Each starts out believing one false lead."},
    (v) => setCfg({misinformed_frac: v / n}))));
  const adv = document.createElement("details");
  const swarmOnly = t !== "other";
  adv.innerHTML = `<summary>More: stubborn and forgetful boys (Swarm Detectives only)</summary>`;
  adv.appendChild(ctlGrid(
    sliderCtl("Boys who never change their vote", swarmOnly ? 0 : Math.round(cfg.stubborn_frac * n), {min: 0, max: Math.max(1, n), step: 1, off: swarmOnly,
      fmt: (x) => swarmOnly ? "n/a" : `${x} of ${n}`,
      hint: swarmOnly ? "Not used here: the Baker Street Irregulars don't vote, and a solo detective has no boys." : "Once they hold a full answer they keep it, whatever they hear."},
    (v) => setCfg({stubborn_frac: v / n})),
    sliderCtl("Forgetfulness", swarmOnly ? 0 : cfg.forget_rate, {min: 0, max: 1, step: 0.05, off: swarmOnly,
      fmt: (x) => swarmOnly ? "n/a" : `${Math.round(x * 100)}% chance per tick`,
      hint: swarmOnly ? "Not used here: the Baker Street Irregulars hand over everything they carry." : "Each tick, each boy may forget one lead he was holding."},
    (v) => setCfg({forget_rate: v}))));
  dec.appendChild(adv);
  p.appendChild(dec);
}

function groupOpen(group) {
  if (group.startsWith("Solo")) return cfg.mode === "solo";
  if (group.startsWith("Swarm")) return cfg.mode === "swarm" && cfg.swarm_policy !== "baker_street";
  if (group.startsWith("Baker")) return cfg.mode === "swarm" && cfg.swarm_policy === "baker_street";
  return false;
}

function renderForm() {
  const form = $("#cfgForm");
  const wasOpen = {};
  form.querySelectorAll("details").forEach((d) => wasOpen[d.dataset.g] = d.open);
  form.innerHTML = "";
  for (const [group, fields] of SCHEMA.schema) {
    const d = document.createElement("details");
    d.dataset.g = group;
    d.open = group in wasOpen ? wasOpen[group] : false;
    const irrelevant = (group.startsWith("Solo") && cfg.mode !== "solo") || (group.startsWith("Swarm") && cfg.mode !== "swarm") ||
      (group.startsWith("Baker") && !(cfg.mode === "swarm" && cfg.swarm_policy === "baker_street"));
    if (irrelevant) d.className = "dim";
    d.innerHTML = `<summary>${esc(group)}${irrelevant ? ' <span class="meta">not used by this setup</span>' : ""}</summary>`;
    for (const [key, label, kind, extra] of fields) {
      const row = document.createElement("div");
      row.className = "field";
      let input;
      if (kind === "choice") {
        input = document.createElement("select");
        for (const [v, l] of Object.entries(extra)) {
          const o = document.createElement("option"); o.value = v; o.textContent = l.length > 46 ? `${v}: ${l.slice(0, 44)}…` : `${v}: ${l}`;
          o.title = l; input.appendChild(o);
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
        const v = kind === "bool" ? input.checked : kind === "int" ? parseInt(input.value) : kind === "float" ? parseFloat(input.value) : input.value;
        const pv = ["seed", "n_addresses", "n_suspects", "n_motives", "n_hideouts", "redundancy", "lie_rate", "red_herring_rate", "pointer_rate"].includes(key);
        setCfg({[key]: v}, {preview: pv});
      };
      const lab = document.createElement("label"); lab.htmlFor = input.id; lab.textContent = label;
      row.append(lab, input);
      d.appendChild(row);
    }
    form.appendChild(d);
  }
}

function caseTitle(brief, seed) {
  const m = /found dead at \d+ ([^,]+),/.exec(brief.victim || "");
  const victim = (brief.victim || "").split(",").slice(0, 2).join(",");
  return {title: m ? `The ${m[1]} Affair` : "The Case", sub: `Case no. ${seed} · ${victim}`};
}

let pvTimer = null, PREVIEW = null;
function preview() {
  clearTimeout(pvTimer);
  pvTimer = setTimeout(async () => {
    const q = new URLSearchParams();
    for (const k of ["seed", "n_addresses", "n_suspects", "n_motives", "n_hideouts", "redundancy", "lie_rate", "red_herring_rate", "pointer_rate"]) q.set(k, cfg[k]);
    const r = await api("/api/preview?" + q);
    PREVIEW = {map: r.map, brief: r.brief};
    drawMap($("#preview"), PREVIEW, null, {preview: true});
    const k = r.kinds;
    const key = ["trait", "alibi", "motive", "hide_district", "hide_type"].reduce((s, x) => s + (k[x] || 0), 0);
    const t = caseTitle(r.brief, cfg.seed);
    PREVIEW_INFO = {...t, lies: k.lie || 0};
    $("#pvTitle").textContent = t.title;
    $("#pvInfo").textContent = `${r.map.addresses.length} addresses · ${Object.keys(r.brief.suspects).length} suspects`;
    $("#pvKinds").innerHTML = `${esc(t.sub)}.<br>On the map: ${key} real clues, ${k.lie || 0} lie${(k.lie || 0) === 1 ? "" : "s"}, ${k.pointer || 0} "ask at..." tips,
      ${k.herring || 0} red herrings and ${k.bland || 0} empty addresses. All the clues together point to the right answer:
      ${Object.values(r.solvable).every(Boolean) ? "yes" : "<span class='err'>no</span>"}.`;
    renderCase();
  }, 150);
}

function setupName(c) {
  const t = trackOf(c);
  if (t === "solo") return `Solo · ${(SOLO_OPTS.find((o) => o.v === c.policy) || {}).label || c.policy}`;
  if (t === "baker") return `Baker Street Irregulars · ${c.holmes === "chat" ? "gpt-6-astra" : "counting"} Holmes · ${c.boy_policy === "jev" ? "Jev" : c.boy_policy} boys`;
  return `Swarm Detectives · ${(OTHER_OPTS.find((o) => o.v === c.swarm_policy) || {}).label || c.swarm_policy}`;
}

function estimate() {
  let s;
  const chip = $("#familyChip");
  chip.style.setProperty("--chip", `var(${seriesVar(cfg)})`);
  chip.textContent = setupName(cfg);
  const t = trackOf(cfg);
  if (t === "solo") {
    const steps = Math.min(cfg.visit_budget, Math.round(cfg.deadline_hours * 60 / 38)) + 1;
    s = `<p>One detective, at most ${cfg.visit_budget} visits in ${cfg.deadline_hours} case hours (about ${steps} decisions).</p>`;
    if (cfg.policy === "jev") s += `<p>Estimated cost: about <b>$${(steps * 0.00024).toFixed(3)}</b> per case. Each decision takes 0.2-0.3 s.</p>`;
    else if (cfg.policy === "chat") s += `<p>Estimated cost: about <b>$${(steps * 0.018).toFixed(2)}</b> per case at list price. Each decision takes 4-5 s.</p>`;
    else s += "<p>No model is used: free and instant.</p>";
  } else if (t === "baker") {
    s = `<p>Holmes at 221B with ${cfg.wiggins ? "Wiggins and " : ""}${cfg.n_irregulars} street boys, ${clockHours()} case hours.</p>`;
    const boys = cfg.boy_policy === "jev" ? cfg.n_irregulars * 0.00016 : 0;
    s += cfg.holmes === "chat" ? `<p>Estimated cost: about <b>$${(0.62 + boys).toFixed(2)}</b> per case (up to ${cfg.hq_max_calls} planning rounds by gpt-6-astra, about 13 s each).</p>`
      : `<p>Estimated cost: ${boys ? `about <b>$${boys.toFixed(3)}</b> per case, for the boys' Jev calls` : "<b>free</b> and instant"}.</p>`;
  } else {
    const calls = cfg.n_irregulars * cfg.swarm_ticks;
    s = `<p>${cfg.n_irregulars} Irregulars for up to ${cfg.swarm_ticks} ticks of ${cfg.tick_min} case minutes: at most ${calls.toLocaleString()} decisions.</p>`;
    if (cfg.swarm_policy === "hybrid_genius") s += `<p>Estimated cost: at most about <b>$${(calls * 0.00006).toFixed(2)}</b> for Jev, plus up to ${cfg.hub_max_calls} gpt-6-astra calls at the Yard.</p>`;
    else if (cfg.swarm_policy === "hybrid") s += `<p>Estimated cost: at most about <b>$${(calls * 0.00006).toFixed(2)}</b> per case; the votes themselves are free.</p>`;
    else if (cfg.swarm_policy === "jev") s += `<p>Estimated cost: at most about <b>$${(calls * 0.000105).toFixed(2)}</b> per case. Each tick waits 1-2 s for its calls.</p>`;
    else s += "<p>No model is used: free and instant.</p>";
    if (cfg.budget_cap_usd > 0) s += `<p>Spending is capped at $${cfg.budget_cap_usd}; above it the simple rule decides.</p>`;
  }
  $("#estimate").innerHTML = s;
}

async function testModel(which) {
  const o = $("#testOut"); o.hidden = false; o.textContent = `Testing ${which}…`;
  const r = await api("/api/test", {which, cfg});
  o.textContent = r.ok ? `OK: ${r.model} answered in ${r.latency} s\n${JSON.stringify(r.reply, null, 1)}` : `Failed: ${r.error}`;
}

async function launch() {
  $("#launchErr").textContent = "";
  $("#launchBtn").disabled = true;
  const r = await api("/api/launch", {cfg});
  $("#launchBtn").disabled = false;
  if (!r.ok) { $("#launchErr").textContent = r.error; return; }
  startDash();
}

/* ------------------------------------------------------------------ viewer */
function startDash() {
  $("#launch").hidden = true; $("#dash").hidden = false; $("#endBanner").hidden = true;
  frame = null; CASE = null; SECRET = null; selected = -1; seenNotes = 0; pulses = []; AG.cur.clear(); AG.prev.clear(); AG.det = null; AG.last = 0;
  TRAILS.clear(); CAPS_SEEN = new Set(); LAST_REPORTS = 0; LAST_PLAN = 0; Object.assign(CAM, {z: 1, cx: 500, cy: 350, to: null});
  $("#captions").innerHTML = ""; $("#stamp").hidden = true; $("#titleCard").hidden = true;
  $("#tTruth").checked = false;
  $("#selId").textContent = "-"; $("#irrDetail").innerHTML = ""; $("#selTraits").textContent = "";
  if (es) es.close();
  es = new EventSource("/api/stream");
  es.onmessage = (ev) => onFrame(JSON.parse(ev.data));
  scrollTo(0, 0);
}

function onFrame(f, redraw = false) {
  if (f.case) CASE = f.case;
  if (f.secret) SECRET = f.secret;
  const first = !frame || (frame.run !== f.run);
  if (!redraw) tween(f);
  frame = f;
  const solo = f.mode === "solo";
  document.querySelectorAll(".solo-only").forEach((e) => e.hidden = !solo);
  document.querySelectorAll(".swarm-only").forEach((e) => e.hidden = solo);
  if (first && CASE) { renderBrief(); buildGuessForm(); if (!solo && !f.hq) buildKnobs(); setTimeout(() => titleCard(f), 50); }
  if (!redraw && CASE) captionsFor(f);
  const live = $("#liveDot");
  live.className = `live ${f.ended ? "closed" : f.paused ? "paused" : "on"}`;
  live.textContent = f.ended ? "Closed" : f.paused ? "Paused" : "Live";
  if (first || redraw) legend();
  document.querySelectorAll(".swarm-knobs").forEach((e) => e.hidden = solo || !!f.hq);
  const tag = $("#modeTag");
  const sc = {mode: f.mode, policy: f.policy, swarm_policy: f.hq ? "baker_street" : f.policy};
  tag.style.setProperty("--chip", `var(${seriesVar(sc)})`);
  tag.textContent = solo ? `Solo · ${f.policy === "chat" ? "gpt-6-astra" : f.policy}` : f.hq
    ? `Baker Street Irregulars · ${f.hq.holmes === "chat" ? "gpt-6-astra" : "counting"} Holmes`
    : `Swarm Detectives · ${f.policy} · ${f.irregulars.length} boys`;
  if (CASE) {
    const seed = (/_s(\d+)$/.exec(f.run || "") || [0, "?"])[1];
    const t = caseTitle(CASE.brief, seed);
    $("#caseTitle").innerHTML = `${esc(t.title)}<span class="meta">${esc(t.sub)} · <span class="mono">${esc(f.run)}</span></span>`;
  }
  $("#clock").textContent = hhmm(f.minute);
  const prog = solo ? Math.max(f.visits / f.budget, f.minute / f.deadline) : f.tick / f.ticks;
  $("#progFill").style.width = `${Math.min(100, 100 * prog)}%`;
  $("#progText").textContent = solo ? `visit ${f.visits} of ${f.budget}` : `tick ${f.tick} of ${f.ticks}`;
  $("#playBtn").innerHTML = f.paused ? `<span class="ico" aria-hidden="true">▶</span> <span class="lbl">Resume</span>`
    : `<span class="ico" aria-hidden="true">❚❚</span> <span class="lbl">Pause</span>`;
  const sp = $("#speed");
  if (document.activeElement !== sp) sp.value = Math.log10(f.speed);
  $("#speedVal").textContent = `${f.speed.toFixed(f.speed < 10 ? 1 : 0)}/s`;
  if (!redraw && !REDUCED.matches) {
    if (!solo) for (const s of f.shares) pulses.push({x: s[1], y: s[2], t0: performance.now()});
    if (f.hq) for (const [x, y] of f.hq.deliveries) pulses.push({x, y, t0: performance.now(), r: 30});
  }
  if (solo) { renderNotebook(f); renderBelief(f); }
  else if (f.hq) { renderHQ(f); drawReports(f); if (selected >= 0 && !redraw) loadIrregular(selected); }
  else { renderTally(f); drawSeries(f); if (selected >= 0 && !redraw) loadIrregular(selected); syncKnobs(f); }
  renderInference(f); renderEvents(f); renderGuesses(f);
  if (f.ended) showEnd(f);
}

function truthOn() { return $("#tTruth").checked && SECRET; }

function renderBrief() {
  const b = CASE.brief;
  $("#brief").innerHTML = `<p><b>Victim:</b> ${esc(b.victim)}. Lived at ${esc(b.victim_home)}.</p>
    <h4>Suspects</h4>` + Object.entries(b.suspects).map(([k, v], i) =>
    `<div class="sus"><i style="background:${SUS_COLORS[i % 16]}"></i><b>${k}</b><span>${esc(v)}</span></div>`).join("") +
    `<h4>Motives</h4><div>${Object.entries(b.motives).map(([k, v]) => `<b class="mono">${k}</b> ${esc(v)}`).join("<br>")}</div>
    <h4>Possible hideouts</h4><div>${Object.entries(b.possible_hideouts).map(([k, v]) => `<b class="mono">${k}</b> ${esc(v)}`).join("<br>")}</div>`;
}

function name(kind, id) {
  if (!CASE || !id) return id || "?";
  if (kind === "culprit") return `${id} ${(CASE.brief.suspects[id] || "").split(",")[0]}`;
  if (kind === "motive") return `${id} ${(CASE.brief.motives[id] || "").split(":")[0]}`;
  return `${id} ${(CASE.brief.possible_hideouts[id] || "").split(",")[0]}`;
}

function addrLabel(id) {
  const a = CASE ? CASE.map.addresses.find((x) => x.id === id) : null;
  return a ? `${a.street}, ${a.district}` : "";
}

function renderNotebook(f) {
  const el = $("#notebook");
  const kinds = truthOn() ? SECRET.lead_kinds : null;
  el.innerHTML = f.notebook.slice().reverse().map((n, i) => {
    const k = kinds ? kinds[n.address] : "";
    const cls = k === "lie" ? "k-lie" : KEY.has(k) ? "k-key" : k === "pointer" ? "k-pointer" : "";
    const fresh = f.notebook.length > seenNotes && i === 0 ? " fresh" : "";
    return `<div class="nb ${cls}${fresh}"><div class="addr">${n.n ? `#${n.n} · ` : ""}${hhmm(n.minute)} · ${n.address} ${esc(addrLabel(n.address))}${k ? ` · ${k}` : ""}</div>
      <div class="txt">${esc(n.text)}</div></div>`;
  }).join("");
  seenNotes = f.notebook.length;
  $("#nbMeta").textContent = `${f.notebook.length} lead${f.notebook.length === 1 ? "" : "s"}, newest first`;
}

function renderBelief(f) {
  const L = f.last;
  const el = $("#belief");
  el.style.setProperty("--series", `var(${seriesVar({mode: "solo", policy: f.policy})})`);
  if (!L) { el.innerHTML = "<p class='muted small'>Waiting for the first decision…</p>"; return; }
  el.dataset.hint = "";
  const truth = SECRET && (truthOn() || f.ended) ? SECRET.truth : null;
  let h = "";
  for (const k of ["culprit", "motive", "hideout"]) {
    const rows = Object.entries(L.belief[k] || {}).sort((x, y) => y[1] - x[1]).slice(0, 5);
    h += `<div class="bgroup"><h4>${k}</h4>` + rows.map(([id, p]) => {
      const cls = truth ? (id === truth[k] ? "truth" : id === L.pick[k] ? "wrongpick" : "") : "";
      return `<div class="brow ${cls}"><span class="nm">${esc(name(k, id))}</span><div class="bar2"><div style="width:${100 * p}%"></div></div><span class="pc">${(100 * p).toFixed(0)}%</span></div>`;
    }).join("") + "</div>";
  }
  el.innerHTML = h;
  const m = L.meta || {};
  $("#decMeta").textContent = m.model ? `${m.model.replace("typesafe/", "")} · ${m.in || 0}+${m.out || 0} tok · $${(m.cost || 0).toFixed(4)}` : (L.source || "");
  let note = L.note ? esc(L.note) : "";
  if (L.action_probs) note += `<br>Move: ${Object.entries(L.action_probs).map(([k, v]) => `${k.replace("VISIT_", "")} ${(100 * v).toFixed(0)}%`).join(", ")}`;
  const act = L.action ? (L.action.startsWith("VISIT_") ? `Next: visit ${L.action.slice(6)} ${esc(addrLabel(L.action.slice(6)))}` : L.action === "ACCUSE" ? "Next: accuse" : esc(L.action)) : "Accused";
  $("#decNote").innerHTML = `<b>${act}</b>${note ? ". " + note : ""}`;
}

function renderTally(f) {
  $("#sideTitle").innerHTML = `How the swarm is voting <span class="meta">${f.need} matching votes close the case</span>`;
  const cv = f.coverage;
  $("#cov").textContent = `${cv.key_leads_found} of ${cv.key_leads} real clues found · ${cv.addresses} addresses visited`;
  const truth = SECRET && (truthOn() || f.ended) ? SECRET.truth : null;
  const maxV = Math.max(f.need * 1.2, ...f.tally.map((t) => t[1]));
  let h = "";
  if (f.hub) {
    const A = f.hub.answer;
    h += `<div class="small" style="margin-bottom:10px"><b>Holmes at Scotland Yard</b> has ${f.hub.leads} leads.
      ${A ? `Latest: ${esc(name("culprit", A.culprit))} / ${A.motive} / ${A.hideout} ${A.confident ? "<b>(sure)</b>" : "(not sure yet)"}<br><span class="muted">${esc(A.note || "")}</span>` : "No announcement yet."}</div>`;
  }
  h += `<h4 class="meta" style="margin:0 0 4px">Most popular full answers (culprit / motive / hideout)</h4>`;
  h += f.tally.length ? f.tally.slice(0, 5).map(([[c, m, hd], n]) => {
    const ok = truth && c === truth.culprit && m === truth.motive && hd === truth.hideout;
    const ci = CASE ? Object.keys(CASE.brief.suspects).indexOf(c) : 0;
    return `<div class="trow"><div><span${ok ? ' style="color:var(--good);font-weight:600"' : ""}>${esc(name("culprit", c))} / ${m} / ${hd}${ok ? " ✓" : ""}</span>
      <div class="qbar"><div style="width:${100 * n / maxV}%;background:${SUS_COLORS[ci % 16]}"></div><i style="left:${100 * f.need / maxV}%"></i></div></div><b>${n}</b></div>`;
  }).join("") : `<p class="muted small">No boy holds a full answer yet.</p>`;
  h += `<h4 class="meta" style="margin:10px 0 4px">Votes for the culprit alone</h4><div class="small">` + (f.parts.culprit.slice(0, 6).map(([c, n]) => {
    const ci = CASE ? Object.keys(CASE.brief.suspects).indexOf(c) : 0;
    return `<span style="color:${SUS_COLORS[ci % 16]}">●</span> <span class="mono">${c} ${n}</span>`;
  }).join(" &nbsp; ") || "none") + "</div>";
  $("#tally").innerHTML = h;
}

function chartFrame(c, H) {
  const dpr = devicePixelRatio || 1, W = c.clientWidth;
  c.width = W * dpr; c.height = H * dpr;
  const g = c.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
  return {g, W, H};
}

function drawLineChart(c, f, lines, ymax, marker) {
  if (!c.clientWidth) return;
  const {g, W, H} = chartFrame(c, 130);
  const n = f.ticks, L = 30, B = H - 18, T = 8;
  const X = (t) => L + (W - L - 8) * t / n, Y = (v) => B - (B - T) * v / ymax;
  g.font = `11px ${css("--f-mono") || "monospace"}`; g.fillStyle = css("--muted"); g.strokeStyle = css("--line"); g.lineWidth = 1;
  for (const v of [0, ymax / 2, ymax]) { g.beginPath(); g.moveTo(L, Y(v)); g.lineTo(W - 8, Y(v)); g.stroke(); g.fillText(Math.round(v), 2, Y(v) + 4); }
  for (const t of [0, Math.round(n / 2), n]) g.fillText(t, Math.min(W - 18, X(t) - 6), H - 4);
  if (marker) {
    g.setLineDash([4, 3]); g.strokeStyle = css("--ink"); g.beginPath(); g.moveTo(L, Y(marker.v)); g.lineTo(W - 8, Y(marker.v)); g.stroke(); g.setLineDash([]);
    g.fillStyle = css("--ink"); g.fillText(marker.label, W - 8 - g.measureText(marker.label).width, Y(marker.v) - 4);
  }
  const S = f.series;
  for (const ln of lines) {
    if (!S.length) break;
    if (ln.area) {
      g.beginPath(); g.moveTo(X(S[0].tick), B);
      S.forEach((r) => g.lineTo(X(r.tick), Y(r[ln.key]))); g.lineTo(X(S[S.length - 1].tick), B); g.closePath();
      g.globalAlpha = 0.12; g.fillStyle = ln.color; g.fill(); g.globalAlpha = 1;
    }
    g.strokeStyle = ln.color; g.lineWidth = ln.w || 1.5; g.lineJoin = "round"; g.beginPath();
    S.forEach((r, i) => i ? g.lineTo(X(r.tick), Y(r[ln.key])) : g.moveTo(X(r.tick), Y(r[ln.key]))); g.stroke();
    const last = S[S.length - 1];
    g.fillStyle = ln.color; g.beginPath(); g.arc(X(last.tick), Y(last[ln.key]), 2.5, 0, 7); g.fill();
  }
  $("#seriesLegend").innerHTML = lines.map((ln) => `<span><i style="background:${ln.color};border-radius:2px;height:3px"></i>${esc(ln.label)}</span>`).join("");
}

function drawSeries(f) {
  const ymax = Math.max(f.need * 1.2, 5, ...f.series.map((r) => Math.max(r.top, r.firm)));
  const lines = [{key: "top", label: "leading answer", color: css("--ink"), w: 2, area: true}, {key: "firm", label: "firm votes", color: css("--faint")}];
  if (SECRET && (truthOn() || f.ended)) lines.push({key: "truth", label: "true answer", color: css("--good")}, {key: "frame", label: "liars' answer", color: css("--bad")});
  drawLineChart($("#series"), f, lines, ymax, {v: f.need, label: "quorum"});
}

function drawReports(f) {
  const ymax = Math.max(10, ...f.series.map((r) => r.reports));
  drawLineChart($("#series"), f, [{key: "reports", label: "reports at 221B", color: css("--ink"), w: 2, area: true},
    {key: "out", label: "boys out", color: css("--faint")}], ymax, null);
}

function renderHQ(f) {
  const q = f.hq, A = q.answer, truth = SECRET && (truthOn() || f.ended) ? SECRET.truth : null;
  const mark = (k) => truth && A ? (A[k] === truth[k] ? " <span style='color:var(--good)'>✓</span>" : " <span style='color:var(--bad)'>✗</span>") : "";
  const cov = f.coverage;
  $("#sideTitle").innerHTML = `Holmes at 221B <span class="meta">${q.holmes === "chat" ? "gpt-6-astra" : "exact counting"} · planning round ${q.calls} of ${q.max_calls}</span>`;
  $("#cov").textContent = `${q.reports} reports received · ${cov.key_leads_found} of ${cov.key_leads} real clues reported`;
  let h = `<div class="hq-answer"><b>Current answer:</b> ${A ? `${esc(name("culprit", A.culprit))}${mark("culprit")} / ${esc(name("motive", A.motive))}${mark("motive")} / ${esc(name("hideout", A.hideout))}${mark("hideout")} <span class="meta">${A.accuse ? "named as the answer" : "his best guess, not sure yet"}</span>` : "<span class='muted'>none yet</span>"}</div>`;
  if (A && A.note) h += `<p class="small muted" style="margin:4px 0 0">${esc(A.note)}</p>`;
  h += `<h4>What he still needs to know</h4><ul class="hq-q">` + (q.open_questions || []).map((x) => `<li>${esc(x)}</li>`).join("") + `</ul>`;
  const W = q.wiggins;
  if (W) h += `<h4>Wiggins</h4><div class="small">${({post: "At his post", to_baker: "Running reports to Baker Street", to_post: "Taking orders to the boys", baker: "At Baker Street"})[W.state] || W.state}, carrying ${W.bag} report${W.bag === 1 ? "" : "s"}.</div>`;
  h += `<h4>Boys' current assignments</h4>` + (q.assignments.length ? q.assignments.map((a) =>
    `<div class="asg"><span class="dot" style="background:${DISTRICT_HUES[a.district] || css("--faint")}"></span><div><b>${esc(a.district)}</b>
      <span class="mono">${a.addresses.join(" ")}</span>${a.watch ? `, watch ${a.watch}` : ""} · ${a.boys.length ? `${a.boys.length} boy${a.boys.length === 1 ? "" : "s"} on it` : "Wiggins is taking these orders out"}
      ${a.look_for ? `<div class="muted">${esc(a.look_for)}</div>` : ""}</div></div>`).join("") : "<p class='muted small'>No boys out right now.</p>");
  const kinds = truthOn() ? SECRET.lead_kinds : null;
  h += `<h4>Latest reports to reach him</h4><div class="reports">` + q.notebook.slice(-8).reverse().map((r) =>
    `<div><span class="muted">${esc(r.boy_name)} · ${r.address.startsWith("tail:") ? "tailing" : r.address}${kinds && r.fake ? " · <b style='color:var(--bad)'>false</b>" : ""}</span><br>${esc(r.text)}</div>`).join("") + `</div>`;
  $("#tally").innerHTML = h;
}

async function loadIrregular(i) {
  const d = await api(`/api/irregular?id=${i}`);
  if (d.error) return;
  if (frame && frame.hq) {
    $("#selId").textContent = `${i} · ${d.name}`;
    $("#selTraits").textContent = truthOn() && d.traits.length ? `(${d.traits.join(", ")})` : "";
    const L = d.last || {}, a = d.assignment || {};
    $("#irrDetail").innerHTML = `<p style="margin:0">${esc(d.state)}${a.district ? ` · assignment in ${esc(a.district)}` : ""}${a.watch ? `, watching ${a.watch}` : ""}</p>
      <p style="margin:4px 0">Last: <b>${esc(L.action || "-")}</b>. ${esc(L.result || "")}</p>
      <p class="muted" style="margin:0">Checked ${d.checked.length} of ${d.targets.length} assigned addresses · ${d.delivered} reports delivered</p>
      <h4>Reports he is carrying</h4>` + (d.carrying.map((t) => `<div>• ${esc(t)}</div>`).join("") || "<div class='muted'>Nothing yet.</div>");
    return;
  }
  $("#selId").textContent = i;
  $("#selTraits").textContent = truthOn() && d.traits.length ? `(${d.traits.join(", ")})` : "";
  const L = d.last || {};
  const v = d.vote;
  $("#irrDetail").innerHTML = `<p style="margin:0">At <b>${esc(d.observation.you.at)}</b> · hears ${d.observation.you.irregulars_within_earshot} Irregulars</p>
    <p style="margin:4px 0">Last: <b>${esc(L.action || "-")}</b> <span class="muted">(${esc(L.source || "")})</span>. ${esc(L.result || "")}</p>
    <p style="margin:0">Vote: ${esc(v.culprit ? name("culprit", v.culprit) : "unsure")} / ${v.motive || "unsure"} / ${v.hideout || "unsure"}</p>
    <h4>Leads he holds</h4>` + d.observation.my_leads.map((l) => `<div>• ${esc(l.lead)} <span class="muted">(${esc(l.source)})</span></div>`).join("");
}

function card(label, value, title) { return `<div class="mc" title="${esc(title || "")}"><b>${value}</b><span>${label}</span></div>`; }

function renderInference(f) {
  const i = f.inference;
  $("#infCards").innerHTML = [
    card("decisions made", i.decisions), card("model calls", i.calls), card("typical call time", i.latency_p50 != null ? i.latency_p50 + " s" : "-"),
    card("tokens sent", (i.tokens_in / 1000).toFixed(1) + "k", `${i.tokens_cached} of them cached`), card("tokens received", (i.tokens_out / 1000).toFixed(1) + "k"),
    card("cost so far", "$" + i.cost.toFixed(4)), card("rule stood in", i.fallbacks, "decisions made by the simple rule because a call failed or was too slow"),
    card("calls too slow", i.timeouts), card("model", (i.models[0] || i.policy).replace("typesafe/", "")),
  ].join("");
  $("#errors").innerHTML = f.errors.map(esc).join("<br>");
}

function renderEvents(f) {
  const el = $("#events");
  const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 4;
  el.innerHTML = f.events.map((e) => `<div class="${e.kind}"><span class="t">${hhmm(e.t)}</span><span>${e.address ? `<span class="mono muted">${e.address}</span> ` : ""}${esc(e.detail)}</span></div>`).join("");
  if (atBottom) el.scrollTop = el.scrollHeight;
}

function buildGuessForm() {
  const fill = (sel, obj, kind) => { sel.innerHTML = ""; for (const k of Object.keys(obj)) sel.append(new Option(name(kind, k), k)); };
  fill($("#gC"), CASE.brief.suspects, "culprit"); fill($("#gM"), CASE.brief.motives, "motive"); fill($("#gH"), CASE.brief.possible_hideouts, "hideout");
}

function renderGuesses(f) {
  $("#guesses").innerHTML = f.guesses.map((g) => `<div><span class="mono">${hhmm(g.minute)}</span> (${f.mode === "solo" ? "visit" : "tick"} ${g.progress}): ${g.culprit} / ${g.motive} / ${g.hideout}
    <b>${g.status === "open" ? "" : g.status}</b></div>`).join("") || "<span class='muted'>Pick a culprit, motive and hideout, then lock it in. You can lock in more than one guess.</span>";
}

const KNOBS = [["comm_range", "Shouting range (×10 m)", 0, 400, 5], ["bandwidth", "Messages per tick", 0, 12, 1],
  ["forget_rate", "Forget chance per tick", 0, 1, 0.05], ["quorum_frac", "Quorum share", 0.05, 1, 0.01]];
function buildKnobs() {
  const el = $("#knobs"); el.innerHTML = "";
  for (const [k, label, lo, hi, step] of KNOBS) {
    const row = document.createElement("div"); row.className = "field";
    row.innerHTML = `<label for="k_${k}">${label}</label><input id="k_${k}" type="range" min="${lo}" max="${hi}" step="${step}" data-k="${k}"><span data-v="${k}"></span>`;
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
  if (b.dataset.run === f.run && b.dataset.shown) return;
  const t = SECRET ? SECRET.truth_names : null;
  const o = f.mode === "solo" ? f.accusation : f.outcome;
  if (!o || !t) return;
  const cold = f.mode === "swarm" && !f.hq && !o.quorum;
  const parts = Object.values(o.ok).filter(Boolean).length;
  const cls = cold ? "wrong" : parts === 3 ? "solved" : parts > 0 ? "partly" : "wrong";
  const icon = cold ? "⌛" : parts === 3 ? "✓" : parts > 0 ? "◐" : "✗";
  const verdict = cold ? "Case went cold: no quorum" : parts === 3 ? "Solved" : parts > 0 ? `Partly right: ${parts} of 3` : "Wrong on all three";
  const how = f.mode === "solo" ? `${o.forced ? "Out of visits or time; forced accusation" : "Accused"} after ${o.visits} visits at ${hhmm(o.minute)}.`
    : f.hq ? `${o.forced ? "Out of time; Holmes gave his best answer" : "Holmes named the answer"} at ${hhmm(o.minute)} from ${o.reports} reports.`
    : o.quorum ? `Quorum of ${o.votes} Irregulars at tick ${o.tick}.` : `Best answer had ${o.votes} of ${o.need} votes after ${o.tick} ticks (the plurality is shown).`;
  const mk = (k) => o.ok[k] ? "<span class='ok'>✓ right</span>" : "<span class='no'>✗ wrong</span>";
  const best = f.guesses.length ? ` Your best guess: ${Math.max(...f.guesses.map((g) => parseInt(g.status) || 0))}/3.` : "";
  b.className = `end ${cls}`;
  b.dataset.run = f.run; b.dataset.shown = "1";
  b.innerHTML = `<div class="badge" aria-hidden="true">${icon}</div>
    <div class="verdict">${verdict}</div>
    <div class="small muted">${how} Cost $${f.inference.cost.toFixed(4)}.${best}</div>
    <div class="parts">
      <span>Culprit ${mk("culprit")}</span><span>${esc(name("culprit", o.culprit))} <span class="muted">· truth: ${esc(t.culprit)}</span></span>
      <span>Motive ${mk("motive")}</span><span>${esc(name("motive", o.motive))} <span class="muted">· truth: ${esc(t.motive)}</span></span>
      <span>Hideout ${mk("hideout")}</span><span>${esc(name("hideout", o.hideout))} <span class="muted">· truth: ${esc(t.hideout)}</span></span>
    </div>
    <div class="actions" style="grid-column:1/-1"><button id="hideEnd" class="ghost">Close</button><button id="againBtn" class="primary">New case</button></div>`;
  b.hidden = false;
  verdictStamp(cold ? "cold" : cls, verdict);
  setTimeout(focusTruth, 400);
  $("#hideEnd").onclick = () => b.hidden = true;
  $("#againBtn").onclick = () => goLaunch();
  if (!$("#tTruth").checked) { $("#tTruth").checked = true; legend(); }
}

function goLaunch() {
  if (es) es.close();
  $("#dash").hidden = true; $("#launch").hidden = false; $("#endBanner").hidden = true;
  delete $("#endBanner").dataset.shown;
  document.body.classList.remove("present");
  initLaunch();
}

/* ------------------------------------------------------------------ map: cached base layer */
const BASES = new Map();

function mapView(c) {
  const W = c.clientWidth, H = c.clientHeight;
  const s = Math.min(W / 1000, H / 700);
  return {s, ox: (W - 1000 * s) / 2, oy: (H - 700 * s) / 2, W, H};
}

function hull(pts) {
  pts = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (pts.length < 3) return pts;
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo = [], up = [];
  for (const p of pts) { while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
  for (const p of pts.slice().reverse()) { while (up.length >= 2 && cross(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}

function smoothPath(g, pts) {
  g.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length - 1; i++) {
    const mx = (pts[i][0] + pts[i + 1][0]) / 2, my = (pts[i][1] + pts[i + 1][1]) / 2;
    g.quadraticCurveTo(pts[i][0], pts[i][1], mx, my);
  }
  const l = pts[pts.length - 1]; g.lineTo(l[0], l[1]);
}

function label(g, text, x, y, opt = {}) {
  g.font = opt.font || `500 11px ${css("--f-ui") || "sans-serif"}`;
  if ("letterSpacing" in g) g.letterSpacing = opt.spacing || "0px";
  g.textAlign = opt.align || "left";
  g.lineJoin = "round"; g.lineWidth = 3; g.strokeStyle = css("--map-paper"); g.strokeText(text, x, y);
  g.fillStyle = opt.color || css("--map-ink"); g.fillText(text, x, y);
  if ("letterSpacing" in g) g.letterSpacing = "0px";
  g.textAlign = "left";
}

function baseLayer(c, cs, cam = null) {
  const dpr = devicePixelRatio || 1, fit = mapView(c);
  const zoomed = cam && Math.abs(cam.z - 1) > 0.01;
  const key = `${c.id}|${fit.W}x${fit.H}|${effectiveTheme()}|${cs.map.addresses.length}|${cs.map.scene}|${cs.map.baker}` +
    (zoomed ? `|${cam.z.toFixed(3)}|${cam.cx.toFixed(1)}|${cam.cy.toFixed(1)}` : "");
  if (BASES.has(key)) return {img: BASES.get(key), v: fit, zoomed};
  // a settled zoom is drawn crisply at the camera's own scale
  const v = zoomed ? {...fit, s: fit.s * cam.z, ox: fit.W / 2 - cam.cx * fit.s * cam.z, oy: fit.H / 2 - cam.cy * fit.s * cam.z} : fit;
  if (BASES.size > 16) BASES.delete(BASES.keys().next().value);
  const off = document.createElement("canvas");
  off.width = v.W * dpr; off.height = v.H * dpr;
  const g = off.getContext("2d"); g.scale(dpr, dpr);
  const P = (x, y) => [v.ox + x * v.s, v.oy + y * v.s];
  const M = cs.map;
  g.fillStyle = css("--map-paper"); g.fillRect(0, 0, v.W, v.H);
  // districts: soft tinted areas around their addresses
  const byD = {};
  for (const a of M.addresses) (byD[a.district] = byD[a.district] || []).push(P(a.x, a.y));
  // drawn opaque on a scratch canvas, then laid down once at low alpha so overlaps don't darken
  const tint = document.createElement("canvas");
  tint.width = off.width; tint.height = off.height;
  const t = tint.getContext("2d"); t.scale(dpr, dpr);
  t.fillStyle = css("--map-ink"); t.strokeStyle = css("--map-ink"); t.lineJoin = "round"; t.lineWidth = 30 * v.s;
  for (const pts of Object.values(byD)) {
    const h = hull(pts); if (h.length < 3) continue;
    t.beginPath(); h.forEach(([x, y], i) => i ? t.lineTo(x, y) : t.moveTo(x, y)); t.closePath(); t.fill(); t.stroke();
  }
  g.save(); g.setTransform(1, 0, 0, 1, 0, 0); g.globalAlpha = effectiveTheme() === "dark" ? 0.05 : 0.045;
  g.drawImage(tint, 0, 0); g.restore();
  // the Thames: a soft band with a thin bank line
  const river = M.thames.map(([x, y]) => P(x, y));
  g.lineCap = "round"; g.lineJoin = "round";
  g.strokeStyle = css("--river-bank"); g.lineWidth = 19 * v.s + 2; g.beginPath(); smoothPath(g, river); g.stroke();
  g.strokeStyle = css("--river"); g.lineWidth = 19 * v.s; g.beginPath(); smoothPath(g, river); g.stroke();
  // streets as hairlines
  const A = {}; for (const a of M.addresses) A[a.id] = a;
  g.strokeStyle = css("--map-street"); g.lineWidth = 1; g.beginPath();
  for (const [i, j] of M.edges) { const [x1, y1] = P(A[i].x, A[i].y), [x2, y2] = P(A[j].x, A[j].y); g.moveTo(x1, y1); g.lineTo(x2, y2); }
  g.stroke();
  // addresses
  g.fillStyle = css("--map-dot");
  for (const a of M.addresses) { const [x, y] = P(a.x, a.y); g.beginPath(); g.arc(x, y, Math.max(1.4, 2 * v.s), 0, 7); g.fill(); }
  // labels
  const small = v.W < 520;
  for (const d of M.districts) {
    const pts = byD[d.name] || [P(d.x, d.y)];
    const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length, top = Math.min(...pts.map((p) => p[1]));
    label(g, d.name.toUpperCase(), cx, top - 10, {align: "center", spacing: small ? "1px" : "2px", color: css("--district"),
      font: `600 ${small ? 8 : 10}px ${css("--f-ui") || "sans-serif"}`});
  }
  if (!small) {
    const [rx, ry] = P(150, 548);
    label(g, "River Thames", rx, ry, {font: `italic ${Math.max(10, 13 * v.s)}px ${css("--f-head") || "serif"}`, color: css("--river-bank"), spacing: "1px"});
    // scale bar (1 km = 100 map units) and north arrow
    const [sx, sy] = P(24, 680), len = 100 * v.s;
    g.strokeStyle = css("--map-ink"); g.lineWidth = 1.5; g.beginPath(); g.moveTo(sx, sy); g.lineTo(sx + len, sy);
    g.moveTo(sx, sy - 4); g.lineTo(sx, sy + 1); g.moveTo(sx + len, sy - 4); g.lineTo(sx + len, sy + 1); g.stroke();
    label(g, "1 km", sx + len / 2, sy - 6, {align: "center", font: `10px ${css("--f-mono") || "monospace"}`});
    const [nx, ny] = P(968, 40);
    g.fillStyle = css("--map-ink"); g.beginPath(); g.moveTo(nx, ny - 12); g.lineTo(nx + 5, ny + 4); g.lineTo(nx, ny); g.lineTo(nx - 5, ny + 4); g.closePath(); g.fill();
    label(g, "N", nx, ny + 16, {align: "center", font: `600 10px ${css("--f-ui") || "sans-serif"}`});
  }
  BASES.set(key, off);
  return {img: off, v: fit, zoomed};
}

/* ------------------------------------------------------------------ map: streets, camera, agents, overlays */
// Street graph for walking along the streets (client-side shortest paths, cached per case).
const GRAPH = {key: null, adj: null, A: null, paths: new Map()};
function graph(cs) {
  const key = `${cs.map.addresses.length}|${cs.map.scene}|${cs.map.baker}`;
  if (GRAPH.key === key) return GRAPH;
  const A = {}; for (const a of cs.map.addresses) A[a.id] = a;
  const adj = {}; for (const a of cs.map.addresses) adj[a.id] = [];
  for (const [i, j] of cs.map.edges) {
    const w = Math.hypot(A[i].x - A[j].x, A[i].y - A[j].y);
    adj[i].push([j, w]); adj[j].push([i, w]);
  }
  Object.assign(GRAPH, {key, adj, A, paths: new Map()});
  return GRAPH;
}
function streetPath(cs, a, b) {
  const G = graph(cs);
  if (!G.A[a] || !G.A[b]) return null;
  const k = a + ">" + b;
  if (G.paths.has(k)) return G.paths.get(k);
  const dist = {[a]: 0}, prev = {}, done = new Set();
  const todo = [[0, a]];
  while (todo.length) {
    todo.sort((x, y) => x[0] - y[0]);
    const [d, u] = todo.shift();
    if (done.has(u)) continue; done.add(u);
    if (u === b) break;
    for (const [v, w] of G.adj[u]) if (d + w < (dist[v] ?? 1e18)) { dist[v] = d + w; prev[v] = u; todo.push([d + w, v]); }
  }
  const ids = [b]; while (ids[0] !== a && prev[ids[0]]) ids.unshift(prev[ids[0]]);
  const pts = ids.map((id) => [G.A[id].x, G.A[id].y]);
  const segs = []; let total = 0;
  for (let i = 1; i < pts.length; i++) { const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); segs.push(l); total += l; }
  const path = {pts, segs, total};
  G.paths.set(k, path);
  return path;
}
function along(path, f) {
  if (!path) return null;
  if (path.pts.length === 1 || f <= 0) return path.pts[0];
  if (f >= 1) return path.pts[path.pts.length - 1];
  let d = f * path.total;
  for (let i = 0; i < path.segs.length; i++) {
    if (d <= path.segs[i]) { const t = path.segs[i] ? d / path.segs[i] : 0, p = path.pts[i], q = path.pts[i + 1]; return [p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]; }
    d -= path.segs[i];
  }
  return path.pts[path.pts.length - 1];
}

// Camera: zoom z around a map point (cx, cy); z = 1 and the centre of the map is the plain fitted view.
const CAM = {z: 1, cx: 500, cy: 350, from: null, to: null, t0: 0, dur: 0};
function camNow() {
  if (!CAM.to) return CAM;
  const k = CAM.dur ? Math.min(1, (performance.now() - CAM.t0) / CAM.dur) : 1, e = ease(k);
  CAM.z = CAM.from.z + (CAM.to.z - CAM.from.z) * e; CAM.cx = CAM.from.cx + (CAM.to.cx - CAM.from.cx) * e; CAM.cy = CAM.from.cy + (CAM.to.cy - CAM.from.cy) * e;
  if (k >= 1) CAM.to = null;
  return CAM;
}
function camTo(z, cx, cy, dur = 1400) {
  CAM.from = {z: CAM.z, cx: CAM.cx, cy: CAM.cy}; CAM.to = {z, cx, cy}; CAM.t0 = performance.now(); CAM.dur = REDUCED.matches ? 0 : dur;
}
function camReset(dur = 900) { camTo(1, 500, 350, dur); }
function project(v, x, y) { const c = CAM; return [v.W / 2 + (x - c.cx) * v.s * c.z, v.H / 2 + (y - c.cy) * v.s * c.z]; }
function unproject(v, X, Y) { const c = CAM; return [c.cx + (X - v.W / 2) / (v.s * c.z), c.cy + (Y - v.H / 2) / (v.s * c.z)]; }

const AG = {prev: new Map(), cur: new Map(), t0: 0, dur: 0, last: 0, det: null, tick: 0};
const TRAILS = new Map();

function tween(f) {
  const now = performance.now();
  const gap = AG.last ? Math.min(1400, Math.max(120, now - AG.last)) : 0;
  AG.last = now;
  const shown = new Map();
  for (const i of AG.cur.keys()) shown.set(i, agentPos(i));
  AG.prev = shown;
  AG.cur = new Map();
  if (f.mode !== "solo") for (const r of f.irregulars) AG.cur.set(r[0], [r[1], r[2]]);
  if (f.mode === "solo" && (CASE || f.case)) {
    const at = f.at, before = AG.det ? AG.det.toId : at;
    AG.det = {fromId: before, toId: at};
  }
  AG.tick = f.tick || 0;
  AG.t0 = now; AG.dur = REDUCED.matches ? 0 : gap * 0.9;
}
function tweenK() { return AG.dur ? Math.min(1, (performance.now() - AG.t0) / AG.dur) : 1; }
function ease(k) { return k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; }
function agentPos(i) {
  const c = AG.cur.get(i), p = AG.prev.get(i) || c;
  if (!c) return p;
  const k = ease(tweenK());
  return [p[0] + (c[0] - p[0]) * k, p[1] + (c[1] - p[1]) * k];
}
function detPos() {
  const d = AG.det; if (!d || !CASE) return null;
  const path = streetPath(CASE, d.fromId, d.toId);
  return along(path, ease(tweenK()));
}
// Baker Street walkers follow the streets of their current leg, at the case clock between frames.
function legPos(leg, fallback) {
  if (!leg || !CASE) return fallback;
  const [from, to, t0, t1] = leg;
  const tickNow = AG.tick - 1 + tweenK();
  const f = Math.min(1, Math.max(0, (tickNow - t0) / Math.max(1, t1 - t0)));
  return along(streetPath(CASE, from, to), f) || fallback;
}
function trail(id, p) {
  const now = performance.now();
  let t = TRAILS.get(id);
  if (!t) { t = []; TRAILS.set(id, t); }
  const last = t[t.length - 1];
  if (!last || Math.hypot(last[0] - p[0], last[1] - p[1]) > 1.5) t.push([p[0], p[1], now]);
  while (t.length && now - t[0][2] > 1800) t.shift();
  return t;
}
function drawTrail(g, v, pts, color, width = 2) {
  if (pts.length < 2 || REDUCED.matches) return;
  const now = performance.now();
  g.strokeStyle = color; g.lineCap = "round"; g.lineWidth = width;
  for (let i = 1; i < pts.length; i++) {
    const age = (now - pts[i][2]) / 1800;
    g.globalAlpha = Math.max(0, 0.45 * (1 - age));
    const [x1, y1] = project(v, pts[i - 1][0], pts[i - 1][1]), [x2, y2] = project(v, pts[i][0], pts[i][1]);
    g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
  }
  g.globalAlpha = 1;
}

function dot(g, x, y, r, fill, ring) {
  g.fillStyle = ring || css("--map-paper"); g.beginPath(); g.arc(x, y, r + 2, 0, 7); g.fill();
  g.fillStyle = fill; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill();
}

function star(g, x, y, r, fill) {
  g.fillStyle = fill; g.strokeStyle = css("--map-paper"); g.lineWidth = 2; g.beginPath();
  for (let k = 0; k < 10; k++) { const rr = k % 2 ? r * 0.45 : r, an = -Math.PI / 2 + k * Math.PI / 5; g.lineTo(x + rr * Math.cos(an), y + rr * Math.sin(an)); }
  g.closePath(); g.stroke(); g.fill();
}

function drawMap(c, cs, f, opt = {}) {
  if (!cs || !c.clientWidth) return;
  const dpr = devicePixelRatio || 1;
  const cam = opt.preview ? {z: 1, cx: 500, cy: 350} : camNow();
  const {img, v, zoomed} = baseLayer(c, cs, !opt.preview && !CAM.to ? cam : null);
  if (c.width !== Math.round(v.W * dpr) || c.height !== Math.round(v.H * dpr)) { c.width = v.W * dpr; c.height = v.H * dpr; }
  const g = c.getContext("2d");
  const saved = {z: CAM.z, cx: CAM.cx, cy: CAM.cy};
  if (opt.preview) Object.assign(CAM, {z: 1, cx: 500, cy: 350});
  g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, c.width, c.height);
  g.fillStyle = css("--map-paper"); g.fillRect(0, 0, c.width, c.height);
  // base layer under the camera: screen = W/2 + (fit - fitCentre) * z
  if (zoomed) { g.drawImage(img, 0, 0); }
  else {
    const fcx = v.ox + cam.cx * v.s, fcy = v.oy + cam.cy * v.s;
    g.setTransform(dpr * cam.z, 0, 0, dpr * cam.z, dpr * (v.W / 2 - fcx * cam.z), dpr * (v.H / 2 - fcy * cam.z));
    g.drawImage(img, 0, 0, img.width / dpr, img.height / dpr);
  }
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (!opt.preview) view = v;
  const P = (x, y) => project(v, x, y);
  const M = cs.map;
  const A = {}; for (const a of M.addresses) A[a.id] = a;
  const truth = !opt.preview && truthOn() ? SECRET : null;
  const small = v.W < 520;
  const solo = f && f.mode === "solo";
  const now = performance.now();
  if (truth) {
    for (const a of M.addresses) {
      const k = truth.lead_kinds[a.id];
      const col = k === "lie" ? css("--bad") : KEY.has(k) ? css("--good") : k === "pointer" ? css("--info") : null;
      if (!col) continue;
      const [x, y] = P(a.x, a.y); g.fillStyle = col; g.beginPath(); g.arc(x, y, 3, 0, 7); g.fill();
    }
  }
  // solo: the cab route along the streets, and visited addresses
  if (solo) {
    g.strokeStyle = css("--accent"); g.lineWidth = 2; g.setLineDash([6, 5]); g.lineJoin = "round"; g.globalAlpha = 0.8; g.beginPath();
    for (let i = 1; i < f.path.length - 1; i++) {
      const sp = streetPath(cs, f.path[i - 1], f.path[i]); if (!sp) continue;
      sp.pts.forEach(([x0, y0], j) => { const [x, y] = P(x0, y0); j ? g.lineTo(x, y) : g.moveTo(x, y); });
    }
    if (f.path.length > 1 && AG.det) {
      const sp = streetPath(cs, AG.det.fromId, AG.det.toId), k = ease(tweenK());
      if (sp) { let d = 0; const lim = k * sp.total; const [x0, y0] = P(sp.pts[0][0], sp.pts[0][1]); g.moveTo(x0, y0);
        for (let j = 1; j < sp.pts.length && d < lim; j++) { const seg = sp.segs[j - 1]; const q = d + seg <= lim ? sp.pts[j] : along(sp, k); const [x, y] = P(q[0], q[1]); g.lineTo(x, y); d += seg; } }
    }
    g.stroke(); g.setLineDash([]); g.globalAlpha = 1;
    for (const id of new Set(f.path)) { const [x, y] = P(A[id].x, A[id].y); dot(g, x, y, 2.6, css("--accent")); }
  }
  // landmarks
  const lm = (id, txt, draw) => { const a = A[id]; if (!a) return; const [x, y] = P(a.x, a.y); draw(x, y); if (txt && !small) label(g, txt, x + 9, y + 4); };
  for (const [h, id] of Object.entries(M.hideouts)) lm(id, h, (x, y) => {
    const isT = truth && truth.truth.hideout === h;
    g.fillStyle = isT ? css("--good") : css("--map-paper"); g.strokeStyle = isT ? css("--good") : css("--map-ink"); g.lineWidth = 1.5;
    g.beginPath(); g.moveTo(x, y - 6); g.lineTo(x + 5.5, y + 4); g.lineTo(x - 5.5, y + 4); g.closePath(); g.fill(); g.stroke();
  });
  if (!opt.preview) Object.entries(M.suspect_homes).forEach(([s, id], i) => lm(id, s, (x, y) => {
    const isT = truth && truth.truth.culprit === s;
    g.strokeStyle = isT ? css("--good") : SUS_COLORS[i % 16]; g.lineWidth = isT ? 3 : 2; g.fillStyle = css("--map-paper");
    g.beginPath(); g.arc(x, y, 5, 0, 7); g.fill(); g.stroke();
  }));
  lm(M.yard, "Scotland Yard", (x, y) => { g.fillStyle = css("--info"); g.strokeStyle = css("--map-paper"); g.lineWidth = 2; g.strokeRect(x - 5, y - 5, 10, 10); g.fillRect(x - 5, y - 5, 10, 10); });
  lm(M.scene, "Scene", (x, y) => {
    g.strokeStyle = css("--map-paper"); g.lineWidth = 5; g.beginPath(); g.moveTo(x - 5, y - 5); g.lineTo(x + 5, y + 5); g.moveTo(x + 5, y - 5); g.lineTo(x - 5, y + 5); g.stroke();
    g.strokeStyle = css("--bad"); g.lineWidth = 2.5; g.stroke();
  });
  lm(M.baker, "221B", (x, y) => star(g, x, y, 8, css("--accent")));
  if (!f) { if (opt.preview) Object.assign(CAM, saved); return; }
  // when the case is closed and the truth is shown: pulse the culprit's home and the true hideout
  if (f.ended && truth && !REDUCED.matches) {
    const pts = [M.suspect_homes[truth.truth.culprit], M.hideouts[truth.truth.hideout]].filter(Boolean);
    for (const id of pts) {
      const [x, y] = P(A[id].x, A[id].y), k = (now % 1600) / 1600;
      g.strokeStyle = css("--good"); g.lineWidth = 2; g.globalAlpha = 0.7 * (1 - k);
      g.beginPath(); g.arc(x, y, 8 + 22 * k, 0, 7); g.stroke(); g.globalAlpha = 1;
    }
  }
  // shouts and report hand-overs as quiet expanding rings
  pulses = pulses.filter((p) => now - p.t0 < 1000);
  for (const p of pulses) {
    const k = (now - p.t0) / 1000, [x, y] = P(p.x, p.y);
    g.strokeStyle = css("--map-ink"); g.globalAlpha = 0.28 * (1 - k); g.lineWidth = 1;
    g.beginPath(); g.arc(x, y, (p.r || f.comm_range) * v.s * CAM.z * (0.15 + 0.85 * k), 0, 7); g.stroke(); g.globalAlpha = 1;
  }
  if (solo) {
    const dp = detPos();
    if (dp) {
      drawTrail(g, v, trail("det", dp), css("--accent"), 3);
      const [x, y] = P(dp[0], dp[1]);
      if (!REDUCED.matches && !f.ended) { g.strokeStyle = css("--accent"); g.globalAlpha = 0.5; g.lineWidth = 2; g.beginPath(); g.arc(x, y, 11 + 3 * Math.sin(now / 350), 0, 7); g.stroke(); g.globalAlpha = 1; }
      dot(g, x, y, 7, css("--ink"));
      g.fillStyle = css("--map-paper"); g.font = `700 9px ${css("--f-head") || "serif"}`; g.textAlign = "center"; g.fillText("H", x, y + 3); g.textAlign = "left";
    }
    return;
  }
  if (f.hub && A[f.hub.yard]) {
    const [yx, yy] = P(A[f.hub.yard].x, A[f.hub.yard].y);
    g.strokeStyle = css("--info"); g.globalAlpha = 0.6; g.setLineDash([4, 4]); g.beginPath(); g.arc(yx, yy, f.comm_range * v.s * CAM.z, 0, 7); g.stroke(); g.setLineDash([]); g.globalAlpha = 1;
  }
  if (f.hq) {
    const W = f.hq.wiggins;
    for (const r of f.irregulars) {
      const [i, sx, sy, dist, , state, flags, tgt, tailing, , leg] = r;
      const p = legPos(leg, [sx, sy]);
      const jit = (i * 2.399963) % 6.283, rad = state === "idle" ? 8 + (i * 3.7) % 6 : 0;
      const q = [p[0] + rad * Math.cos(jit), p[1] + rad * Math.sin(jit)];
      const col = dist ? (DISTRICT_HUES[dist] || css("--faint")) : css("--faint");
      if (state !== "idle") drawTrail(g, v, trail("b" + i, q), col, 2);
      const [x, y] = P(q[0], q[1]);
      if (tgt && A[tgt] && state !== "idle") {
        const [tx, ty] = P(A[tgt].x, A[tgt].y);
        g.strokeStyle = css("--map-ink"); g.globalAlpha = 0.18; g.setLineDash([2, 3]); g.lineWidth = 1;
        g.beginPath(); g.moveTo(x, y); g.lineTo(tx, ty); g.stroke(); g.setLineDash([]); g.globalAlpha = 1;
      }
      dot(g, x, y, i === selected ? 5 : 3.8, col, state === "back" ? css("--ink") : null);
      if (tailing) { g.strokeStyle = css("--bad"); g.lineWidth = 1; g.setLineDash([2, 2]); g.beginPath(); g.arc(x, y, 8, 0, 7); g.stroke(); g.setLineDash([]); }
      if (truth && (flags & 1)) { g.strokeStyle = css("--bad"); g.lineWidth = 2; g.beginPath(); g.arc(x, y, 8, 0, 7); g.stroke(); }
      if (i === selected) { g.strokeStyle = css("--ink"); g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 9, 0, 7); g.stroke(); }
    }
    if (W) {
      if (A[W.post] && W.post !== f.hq.baker) { const [px, py] = P(A[W.post].x, A[W.post].y); g.strokeStyle = css("--ink"); g.lineWidth = 1.5; g.strokeRect(px - 7, py - 7, 14, 14); }
      const wp = legPos(W.leg, [W.x, W.y]);
      drawTrail(g, v, trail("W", wp), css("--ink"), 2.5);
      const [wx, wy] = P(wp[0], wp[1]);
      dot(g, wx, wy, 8, css("--ink"));
      g.fillStyle = css("--map-paper"); g.font = `700 10px ${css("--f-head") || "serif"}`; g.textAlign = "center"; g.fillText("W", wx, wy + 3.5); g.textAlign = "left";
    }
    return;
  }
  const order = CASE ? Object.keys(CASE.brief.suspects) : [];
  for (const r of f.irregulars) {
    const [i, , , cu, , , flags] = r;
    const p = agentPos(i) || [r[1], r[2]];
    const jit = (i * 2.399963) % 6.283, rad = 5 + (i * 3.7) % 7;
    const q = [p[0] + rad * Math.cos(jit), p[1] + rad * Math.sin(jit)];
    const [x, y] = P(q[0], q[1]);
    const ci = order.indexOf(cu);
    dot(g, x, y, i === selected ? 4.6 : 3.2, cu ? SUS_COLORS[ci % 16] : css("--faint"));
    if (truth && (flags & 1)) { g.strokeStyle = css("--bad"); g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 7, 0, 7); g.stroke(); }
    if (i === selected) { g.strokeStyle = css("--ink"); g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 8, 0, 7); g.stroke(); }
  }
}

/* ------------------------------------------------------------------ demo overlays: title card, captions, verdict stamp */
let CAPS_SEEN = new Set(), LAST_REPORTS = 0, LAST_PLAN = 0;
function caption(html, kind = "") {
  const box = $("#captions");
  const el = document.createElement("div");
  el.className = `cap ${kind}`; el.innerHTML = html;
  box.appendChild(el);
  while (box.children.length > 2) box.removeChild(box.firstChild);
  const life = kind === "big" ? 7000 : Math.max(2600, Math.min(5200, 7000 / Math.max(0.5, frame ? frame.speed : 1)));
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 600); }, life);
}
function captionsFor(f) {
  const quote = (t, n = 150) => `<q>${esc(t.length > n ? t.slice(0, n - 1) + "…" : t)}</q>`;
  for (const e of f.events) {
    const key = `${e.t}|${e.kind}|${e.detail}`;
    if (CAPS_SEEN.has(key)) continue;
    CAPS_SEEN.add(key);
    if (CAPS_SEEN.size < 4 && (e.kind === "case" || e.kind === "start")) continue;
    if (e.kind === "lead" && e.visit) caption(`<b>Visit ${e.visit} · ${esc(addrLabel(e.address))}</b>${quote(e.detail)}`);
    else if (e.kind === "hub" && !f.hq) caption(`<b>Holmes at the Yard</b>${quote(e.detail.replace(/^Holmes[^:]*:\s*/, ""), 170)}`);
    else if (e.kind === "tally") caption(`<b>The swarm is voting</b>${esc(e.detail.replace(/^tick \d+: /, ""))}`);
    else if (e.kind === "accuse" || e.kind === "timeout") caption(`<b>${e.kind === "accuse" ? "Case closed" : "Out of time"}</b>${esc(e.detail)}`, "big");
    else if (e.kind === "intervention" || e.kind === "guess" || e.kind === "budget") caption(esc(e.detail), "note");
  }
  if (f.hq && f.hq.calls > LAST_PLAN) {
    LAST_PLAN = f.hq.calls;
    const q = f.hq, A = q.answer || {};
    const dists = [...new Set(q.assignments.map((a) => a.district))];
    const where = dists.length ? `Sends boys to ${dists.length > 1 ? dists.slice(0, -1).join(", ") + " and " + dists[dists.length - 1] : dists[0]}.` : "Waits for more reports.";
    const guess = A.culprit ? ` ${A.accuse ? "Names" : "Best guess so far"}: ${esc(name("culprit", A.culprit).replace(/^S\d+ /, ""))}, ${esc(name("motive", A.motive).replace(/^M\d+ /, ""))}, ${esc(name("hideout", A.hideout).replace(/^H\d+ /, ""))}.` : "";
    caption(`<b>Holmes, planning round ${q.calls}</b>${where}${guess}${A.note ? quote(A.note, 140) : ""}`);
  }
  if (f.hq) {
    const n = f.hq.reports;
    if (n > LAST_REPORTS) caption(`<b>${n - LAST_REPORTS} new report${n - LAST_REPORTS === 1 ? "" : "s"} reach 221B</b>${f.hq.wiggins ? "Wiggins hands them to Holmes." : "A boy runs in with his findings."}`, "note");
    LAST_REPORTS = n;
  }
}
function titleCard(f) {
  if (!CASE) return;
  const seed = (/_s(\d+)$/.exec(f.run || "") || [0, "?"])[1];
  const t = caseTitle(CASE.brief, seed);
  const el = $("#titleCard");
  el.innerHTML = `<div class="tc-kicker">${esc($("#modeTag").textContent)}</div><div class="tc-title">${esc(t.title)}</div><div class="tc-sub">${esc(t.sub)}</div>`;
  el.hidden = false; el.classList.remove("out");
  setTimeout(() => el.classList.add("out"), REDUCED.matches ? 1500 : 2600);
  setTimeout(() => { el.hidden = true; }, REDUCED.matches ? 1600 : 3400);
}
function verdictStamp(cls, verdict) {
  const el = $("#stamp");
  el.className = `stamp ${cls}`;
  el.textContent = {solved: "Solved", partly: "Partly right", wrong: "Wrong", cold: "Case went cold"}[cls] || verdict;
  el.hidden = false;
}
function focusTruth() {
  if (!CASE || !SECRET) return;
  const M = CASE.map, A = {}; for (const a of M.addresses) A[a.id] = a;
  const ids = [M.suspect_homes[SECRET.truth.culprit], M.hideouts[SECRET.truth.hideout], M.scene].filter((x) => A[x]);
  if (!ids.length) return;
  const xs = ids.map((i) => A[i].x), ys = ids.map((i) => A[i].y);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const v = view || {W: 1000, H: 700, s: 1};
  const zx = v.W / ((Math.max(...xs) - Math.min(...xs) + 220) * v.s), zy = v.H / ((Math.max(...ys) - Math.min(...ys) + 220) * v.s);
  camTo(Math.min(2.2, Math.max(1, Math.min(zx, zy))), cx, cy, 1600);
}

function legend() {
  const t = truthOn();
  const item = (color, text, shape = "") => `<span><i style="background:${color};${shape}"></i>${text}</span>`;
  let h = item("var(--accent)", "221B Baker Street") + item("var(--info)", "Scotland Yard", "border-radius:2px") +
    item("var(--bad)", "scene") + item("transparent", "possible hideout (▲)", "border:1.5px solid var(--map-ink);border-radius:2px") +
    item("transparent", "suspect's home", "border:2px solid var(--muted)");
  if (frame && frame.mode === "solo") h += item("var(--accent)", "visited, with the cab route");
  else if (frame && frame.hq) h += item("var(--ink)", "W = Wiggins (□ his post)") + item(DISTRICT_HUES.Soho, "street boy, coloured by the district he was sent to") +
    item("var(--surface)", "boy running back to report", "border:2px solid var(--ink)");
  else if (frame) h += item("var(--faint)", "street boy, coloured by the suspect he votes for (grey: undecided)");
  if (t) h += item("var(--good)", "real clue") + item("var(--bad)", "lie") + item("var(--info)", "\"ask at...\" tip");
  $("#legend").innerHTML = h;
}

function loop() {
  if (frame && CASE && !$("#dash").hidden) drawMap($("#map"), CASE, frame);
  requestAnimationFrame(loop);
}

function onMapMove(ev) {
  if (!view || !CASE) return;
  const rect = $("#map").getBoundingClientRect();
  const [mx, my] = unproject(view, ev.clientX - rect.left, ev.clientY - rect.top);
  let best = null, bd = 1e9;
  for (const a of CASE.map.addresses) { const d = (a.x - mx) ** 2 + (a.y - my) ** 2; if (d < bd) { bd = d; best = a; } }
  const tip = $("#tip");
  if (!best || bd > 225 / (CAM.z * CAM.z)) { hover = null; tip.hidden = true; return; }
  hover = best;
  let lead = "";
  if (frame && frame.mode === "solo") { const n = frame.notebook.find((x) => x.address === best.id); if (n) lead = `<div style="margin-top:4px">${esc(n.text)}</div>`; }
  if (truthOn()) lead += `<div class="muted">lead: ${SECRET.lead_kinds[best.id]}</div>`;
  tip.innerHTML = `<b>${best.id}</b> ${esc(best.street)}, ${esc(best.district)} <span class="muted">(${esc(best.type)})</span>${lead}`;
  const x = ev.clientX - rect.left + 14, y = ev.clientY - rect.top + 10;
  tip.style.left = `${Math.min(x, rect.width - 220)}px`; tip.style.top = `${y}px`; tip.hidden = false;
}

function onMapClick(ev) {
  if (!frame || frame.mode !== "swarm" || !view) return;
  const rect = $("#map").getBoundingClientRect();
  const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
  let best = -1, bd = 1e9;
  for (const r of frame.irregulars) {
    const i = r[0], p = frame.hq ? legPos(r[10], [r[1], r[2]]) : (agentPos(i) || [r[1], r[2]]);
    const idle = frame.hq ? r[5] === "idle" : true;
    const jit = (i * 2.399963) % 6.283, rad = frame.hq ? (idle ? 8 + (i * 3.7) % 6 : 0) : 5 + (i * 3.7) % 7;
    const [x, y] = project(view, p[0] + rad * Math.cos(jit), p[1] + rad * Math.sin(jit));
    const d = (x - mx) ** 2 + (y - my) ** 2; if (d < bd) { bd = d; best = i; }
  }
  if (best >= 0 && bd < 250) { selected = best; loadIrregular(best); }
}

/* ------------------------------------------------------------------ wiring */
$("#launchBtn").onclick = launch;
$("#rejoinBtn").onclick = startDash;
$("#testJev").onclick = () => testModel("jev");
$("#testChat").onclick = () => testModel("chat");
$("#playBtn").onclick = () => api("/api/cmd", {op: frame && frame.paused ? "resume" : "pause"});
$("#stepBtn").onclick = () => api("/api/cmd", {op: "step", n: 1});
$("#speed").onchange = (e) => api("/api/cmd", {op: "set", key: "speed", value: Math.pow(10, parseFloat(e.target.value))});
$("#newRun").onclick = goLaunch;
document.querySelectorAll(".theme-toggle").forEach((b) => b.onclick = toggleTheme);
$("#tTruth").onchange = async () => {
  if ($("#tTruth").checked && !SECRET) SECRET = await api("/api/secret");
  legend(); if (frame) onFrame(frame, true);
};
$("#gGo").onclick = () => api("/api/guess", {culprit: $("#gC").value, motive: $("#gM").value, hideout: $("#gH").value});
$("#map").addEventListener("mousemove", onMapMove);
$("#map").addEventListener("mouseleave", () => { hover = null; $("#tip").hidden = true; });
$("#map").addEventListener("click", onMapClick);
$("#map").addEventListener("dblclick", () => camReset());
function togglePresent() {
  document.body.classList.toggle("present");
  $("#presentBtn").textContent = document.body.classList.contains("present") ? "Exit presentation" : "Present";
  BASES.clear(); setTimeout(() => { BASES.clear(); if (frame) onFrame(frame, true); }, 60);
}
$("#presentBtn").onclick = togglePresent;
addEventListener("keydown", (e) => {
  if ($("#dash").hidden || ["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
  if (e.key === "p" || e.key === "P") togglePresent();
  else if (e.key === "r" || e.key === "R") { $("#tTruth").click(); }
  else if (e.key === "f" || e.key === "F") { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen?.().catch(() => {}); }
  else if (e.key === "0") camReset();
});
addEventListener("keydown", (e) => { if (e.code === "Space" && !$("#dash").hidden && !["INPUT", "SELECT", "BUTTON"].includes(e.target.tagName)) { e.preventDefault(); $("#playBtn").click(); } });
let rzTimer = null;
addEventListener("resize", () => { clearTimeout(rzTimer); rzTimer = setTimeout(() => { BASES.clear(); if (!$("#launch").hidden && PREVIEW) drawMap($("#preview"), PREVIEW, null, {preview: true}); if (frame) onFrame(frame, true); }, 120); });
applyThemeLabels();
if (document.fonts) document.fonts.ready.then(() => { BASES.clear(); if (PREVIEW && !$("#launch").hidden) drawMap($("#preview"), PREVIEW, null, {preview: true}); });
initLaunch();
requestAnimationFrame(loop);

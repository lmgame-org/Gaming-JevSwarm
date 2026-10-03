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
const FAMILIES = [
  {id: "solo", name: "Solo detective", color: "--genius", desc: "One detective takes cabs around London and reads each lead first-hand. 20 visits, 12 hours.",
    presets: ["classic", "genius", "rule", "liars", "small"]},
  {id: "swarm", name: "Self-organising swarm", color: "--jev", desc: "100 Irregulars spread over the city, shout what they find and close the case by quorum.",
    presets: ["swarm", "swarm_rule", "swarm_liars", "swarm_quiet"]},
  {id: "hybrid", name: "Hybrid swarm", color: "--hybrid", desc: "Jev Irregulars choose where to go and what to share; exact counting sets their votes.",
    presets: ["swarm_hybrid", "swarm_hybrid_genius"]},
  {id: "baker", name: "Baker Street", color: "--baker", desc: "Holmes stays at 221B and directs Wiggins and a dozen boys, who run back to report.",
    presets: ["baker_street", "baker_street_counting"]},
];
// Measured cost per case (20-case benchmark, 2 Oct 2026, or the pilot where marked ≈).
const PRESET_COST = {classic: "$0.005", genius: "$0.35", rule: "free", liars: "≈$0.005", small: "≈$0.004", swarm: "$0.17",
  swarm_rule: "free", swarm_liars: "≈$0.17", swarm_quiet: "≈$0.20", swarm_hybrid: "$0.21", swarm_hybrid_genius: "≈$0.41",
  baker_street: "$0.62", baker_street_counting: "$0.002"};
const PRESET_NAME = {classic: "Jev detective", genius: "gpt-6-astra detective", rule: "Rule detective", liars: "Many lying witnesses",
  small: "Small case", swarm: "100 Jev Irregulars", swarm_rule: "Rule swarm", swarm_liars: "Swarm with 15% liars",
  swarm_quiet: "Short shouting range", swarm_hybrid: "Hybrid swarm", swarm_hybrid_genius: "Hybrid + genius at the Yard",
  baker_street: "Holmes: gpt-6-astra", baker_street_counting: "Holmes: exact counting"};

const PRESET_DESC = {classic: "Jev picks each visit and its current suspicion.", genius: "gpt-6-astra reads the whole notebook each step.",
  rule: "Follows pointers and counts corroborating leads.", liars: "Jev against twice as many lying witnesses.",
  small: "40 addresses and 6 suspects: a quick case.", swarm: "Every Irregular decides and votes with Jev.",
  swarm_rule: "A simple shared rule decides for every Irregular.", swarm_liars: "15 of the boys push Moriarty's story.",
  swarm_quiet: "Shouts carry only 500 m.", swarm_hybrid: "Jev moves and shares; votes come from exact counting.",
  swarm_hybrid_genius: "Leads reaching Scotland Yard go to gpt-6-astra.", baker_street: "gpt-6-astra reads every report and plans.",
  baker_street_counting: "Exact counting reads the reports; Jev boys."};

let SCHEMA = null, cfg = {}, preset = "classic", frame = null, CASE = null, SECRET = null, es = null, selected = -1,
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
async function initLaunch() {
  SCHEMA = await api("/api/schema");
  cfg = {...SCHEMA.defaults, ...SCHEMA.presets[preset].overrides};
  renderFamilies();
  renderForm();
  const kf = SCHEMA.key_files.filter((k) => k.exists).map((k) => k.path);
  $("#keyStatus").innerHTML = `<p>Key files found: ${kf.length ? kf.map((p) => `<code>${esc(p)}</code>`).join(", ") : "none"}.</p>
    <p class="muted">Keys are read when a call is made and are never logged or sent to the browser.</p>`;
  $("#runsList").innerHTML = SCHEMA.runs.length ? SCHEMA.runs.slice(0, 12).map((r) =>
    `<div>${esc(r.name)} · ${r.parts ?? "-"}/3${r.solved ? " solved" : ""}${r.cost ? ` · $${r.cost.toFixed(4)}` : ""}</div>`).join("")
    : "<span class='muted'>No runs yet.</span>";
  $("#rejoinBtn").hidden = !SCHEMA.running;
  estimate(); preview();
}

function renderFamilies() {
  const el = $("#families");
  el.innerHTML = "";
  const known = new Set(FAMILIES.flatMap((f) => f.presets));
  const extra = Object.keys(SCHEMA.presets).filter((k) => !known.has(k));
  for (const fam of FAMILIES) {
    const keys = fam.presets.filter((k) => SCHEMA.presets[k]).concat(fam.id === "solo" ? extra : []);
    if (!keys.length) continue;
    const box = document.createElement("div");
    box.className = "family";
    box.style.setProperty("--fam", `var(${fam.color})`);
    box.innerHTML = `<h3>${fam.name}</h3><p>${esc(fam.desc)}</p>`;
    for (const k of keys) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "fam-card" + (k === preset ? " on" : "");
      b.dataset.k = k;
      b.style.setProperty("--fam", `var(${seriesVar({...SCHEMA.defaults, ...SCHEMA.presets[k].overrides})})`);
      b.innerHTML = `<b>${esc(PRESET_NAME[k] || k.replace(/_/g, " "))}</b><span class="cost">${PRESET_COST[k] || ""}</span>
        <span class="desc">${esc(PRESET_DESC[k] || SCHEMA.presets[k].label)}</span>`;
      b.onclick = () => setPreset(k);
      box.appendChild(b);
    }
    el.appendChild(box);
  }
}

function setPreset(k) {
  preset = k;
  const keep = {};
  for (const x of ["seed", "speed", "jev_model", "jev_key", "chat_model", "chat_key", "concurrency"]) keep[x] = cfg[x];
  cfg = {...SCHEMA.defaults, ...keep, ...SCHEMA.presets[k].overrides};
  document.querySelectorAll(".fam-card").forEach((c) => c.classList.toggle("on", c.dataset.k === k));
  renderForm(true); estimate(); preview();
}

function groupOpen(group) {
  if (group === "Run" || group === "Case") return true;
  if (group.startsWith("Solo")) return cfg.mode === "solo";
  if (group.startsWith("Swarm")) return cfg.mode === "swarm" && cfg.swarm_policy !== "baker_street";
  if (group.startsWith("Baker")) return cfg.mode === "swarm" && cfg.swarm_policy === "baker_street";
  return false;
}

function renderForm(reset = false) {
  const form = $("#cfgForm");
  const wasOpen = {};
  if (!reset) form.querySelectorAll("details").forEach((d) => wasOpen[d.dataset.g] = d.open);
  form.innerHTML = "";
  for (const [group, fields] of SCHEMA.schema) {
    const d = document.createElement("details");
    d.dataset.g = group;
    d.open = group in wasOpen ? wasOpen[group] || groupOpen(group) : groupOpen(group);
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
        cfg[key] = kind === "bool" ? input.checked : kind === "int" ? parseInt(input.value) : kind === "float" ? parseFloat(input.value) : input.value;
        if (key === "mode" || key === "swarm_policy") renderForm();
        estimate();
        if (["seed", "n_addresses", "n_suspects", "n_motives", "n_hideouts", "redundancy", "lie_rate", "red_herring_rate", "pointer_rate"].includes(key)) preview();
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
    $("#pvTitle").textContent = t.title;
    $("#pvInfo").textContent = `${r.map.addresses.length} addresses · ${Object.keys(r.brief.suspects).length} suspects`;
    $("#pvKinds").innerHTML = `${esc(t.sub)}.<br>${key} key leads, ${k.lie || 0} lies, ${k.pointer || 0} pointers,
      ${k.herring || 0} red herrings, ${k.bland || 0} empty. Solvable by counting every lead:
      ${Object.values(r.solvable).every(Boolean) ? "yes" : "<span class='err'>no</span>"}.`;
  }, 150);
}

function estimate() {
  let s;
  const chip = $("#familyChip");
  chip.style.setProperty("--chip", `var(${seriesVar(cfg)})`);
  chip.textContent = PRESET_NAME[preset] || "Custom";
  if (cfg.mode === "solo") {
    const steps = Math.min(cfg.visit_budget, Math.round(cfg.deadline_hours * 60 / 38)) + 1;
    s = `<p>One detective, up to ${cfg.visit_budget} visits within ${cfg.deadline_hours} case hours (about ${steps} decisions).</p>`;
    if (cfg.policy === "jev") s += `<p>Jev: about <b>$${(steps * 0.00024).toFixed(3)}</b> per case, 0.2-0.3 s per decision.</p>`;
    else if (cfg.policy === "chat") s += `<p>gpt-6-astra: about <b>$${(steps * 0.018).toFixed(2)}</b> per case at list price, 4-5 s per decision.</p>`;
    else s += "<p>No model calls: free and instant.</p>";
  } else if (cfg.swarm_policy === "baker_street") {
    s = `<p>Holmes at 221B, ${cfg.wiggins ? "Wiggins and " : ""}${cfg.n_irregulars} boys, ${cfg.swarm_ticks} ticks of ${cfg.tick_min} minutes.</p>`;
    s += cfg.holmes === "chat" ? `<p>gpt-6-astra Holmes: about <b>$0.62</b> per case (up to ${cfg.hq_max_calls} plans, ~13 s each).</p>`
      : `<p>Exact-counting Holmes: about <b>$0.002</b> per case${cfg.boy_policy === "jev" ? " (the boys' Jev calls)" : ", free with rule boys"}.</p>`;
  } else {
    const calls = cfg.n_irregulars * cfg.swarm_ticks;
    s = `<p>${cfg.n_irregulars} Irregulars × up to ${cfg.swarm_ticks} ticks: at most ${calls.toLocaleString()} decisions.</p>`;
    if (cfg.swarm_policy === "hybrid_genius") s += `<p>Jev actions about <b>$${(calls * 0.00006).toFixed(2)}</b> at most, plus up to ${cfg.hub_max_calls} gpt-6-astra calls at the Yard.</p>`;
    else if (cfg.swarm_policy === "hybrid") s += `<p>Jev actions about <b>$${(calls * 0.00006).toFixed(2)}</b> at most; votes are counted exactly.</p>`;
    else if (cfg.swarm_policy === "jev") s += `<p>Jev about <b>$${(calls * 0.000105).toFixed(2)}</b> per case at most; each tick waits 1-2 s for its calls.</p>`;
    else s += "<p>No model calls: free and instant.</p>";
    if (cfg.budget_cap_usd > 0) s += `<p>Capped at $${cfg.budget_cap_usd}; above it the reflex rule decides.</p>`;
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
  if (first && CASE) { renderBrief(); buildGuessForm(); if (!solo && !f.hq) buildKnobs(); }
  if (first || redraw) legend();
  document.querySelectorAll(".swarm-knobs").forEach((e) => e.hidden = solo || !!f.hq);
  const tag = $("#modeTag");
  const sc = {mode: f.mode, policy: f.policy, swarm_policy: f.hq ? "baker_street" : f.policy};
  tag.style.setProperty("--chip", `var(${seriesVar(sc)})`);
  tag.textContent = solo ? `Solo · ${f.policy === "chat" ? "gpt-6-astra" : f.policy}` : f.hq
    ? `Baker Street · ${f.hq.holmes === "chat" ? "gpt-6-astra" : "counting"} Holmes · ${f.irregulars.length} boys`
    : `Swarm · ${f.policy} · ${f.irregulars.length} Irregulars`;
  if (CASE) {
    const seed = (/_s(\d+)$/.exec(f.run || "") || [0, "?"])[1];
    const t = caseTitle(CASE.brief, seed);
    $("#caseTitle").innerHTML = `${esc(t.title)}<span class="meta">${esc(t.sub)} · <span class="mono">${esc(f.run)}</span></span>`;
  }
  $("#clock").textContent = hhmm(f.minute);
  const prog = solo ? Math.max(f.visits / f.budget, f.minute / f.deadline) : f.tick / f.ticks;
  $("#progFill").style.width = `${Math.min(100, 100 * prog)}%`;
  $("#progText").textContent = solo ? `visit ${f.visits}/${f.budget}` : `tick ${f.tick}/${f.ticks}`;
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
  $("#nbMeta").textContent = `${f.notebook.length} lead${f.notebook.length === 1 ? "" : "s"}`;
}

function renderBelief(f) {
  const L = f.last;
  const el = $("#belief");
  el.style.setProperty("--series", `var(${seriesVar({mode: "solo", policy: f.policy})})`);
  if (!L) { el.innerHTML = "<p class='muted small'>Waiting for the first decision…</p>"; return; }
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
  $("#decNote").innerHTML = `<b>${esc(L.action || "Accuse")}</b>${note ? ". " + note : ""}`;
}

function renderTally(f) {
  $("#sideTitle").innerHTML = `Votes <span class="meta">quorum ${f.need}</span>`;
  const cv = f.coverage;
  $("#cov").textContent = `${cv.key_leads_found}/${cv.key_leads} key leads seen · ${cv.addresses} addresses walked`;
  const truth = SECRET && (truthOn() || f.ended) ? SECRET.truth : null;
  const maxV = Math.max(f.need * 1.2, ...f.tally.map((t) => t[1]));
  let h = "";
  if (f.hub) {
    const A = f.hub.answer;
    h += `<div class="small" style="margin-bottom:10px"><b>Holmes at Scotland Yard</b> has ${f.hub.leads} leads.
      ${A ? `Latest: ${esc(name("culprit", A.culprit))} / ${A.motive} / ${A.hideout} ${A.confident ? "<b>(sure)</b>" : "(not sure yet)"}<br><span class="muted">${esc(A.note || "")}</span>` : "No announcement yet."}</div>`;
  }
  h += `<h4 class="meta" style="margin:0 0 4px">Full answers (culprit / motive / hideout)</h4>`;
  h += f.tally.length ? f.tally.slice(0, 5).map(([[c, m, hd], n]) => {
    const ok = truth && c === truth.culprit && m === truth.motive && hd === truth.hideout;
    const ci = CASE ? Object.keys(CASE.brief.suspects).indexOf(c) : 0;
    return `<div class="trow"><div><span${ok ? ' style="color:var(--good);font-weight:600"' : ""}>${esc(name("culprit", c))} / ${m} / ${hd}${ok ? " ✓" : ""}</span>
      <div class="qbar"><div style="width:${100 * n / maxV}%;background:${SUS_COLORS[ci % 16]}"></div><i style="left:${100 * f.need / maxV}%"></i></div></div><b>${n}</b></div>`;
  }).join("") : `<p class="muted small">No Irregular holds a full answer yet.</p>`;
  h += `<h4 class="meta" style="margin:10px 0 4px">Culprit votes</h4><div class="small">` + (f.parts.culprit.slice(0, 6).map(([c, n]) => {
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
  $("#sideTitle").innerHTML = `Holmes at 221B <span class="meta">${q.holmes === "chat" ? "gpt-6-astra" : "exact counting"} · plans ${q.calls}/${q.max_calls}</span>`;
  $("#cov").textContent = `${q.reports} reports · ${cov.key_leads_found}/${cov.key_leads} key leads`;
  let h = `<div class="hq-answer"><b>Current answer:</b> ${A ? `${esc(name("culprit", A.culprit))}${mark("culprit")} / ${esc(name("motive", A.motive))}${mark("motive")} / ${esc(name("hideout", A.hideout))}${mark("hideout")} <span class="meta">${A.accuse ? "named" : "not sure yet"}</span>` : "<span class='muted'>none yet</span>"}</div>`;
  if (A && A.note) h += `<p class="small muted" style="margin:4px 0 0">${esc(A.note)}</p>`;
  h += `<h4>Open questions</h4><ul class="hq-q">` + (q.open_questions || []).map((x) => `<li>${esc(x)}</li>`).join("") + `</ul>`;
  const W = q.wiggins;
  if (W) h += `<h4>Wiggins</h4><div class="small">${({post: "At his post", to_baker: "Running reports to Baker Street", to_post: "Taking orders to the boys", baker: "At Baker Street"})[W.state] || W.state}, carrying ${W.bag} report${W.bag === 1 ? "" : "s"}.</div>`;
  h += `<h4>Assignments</h4>` + (q.assignments.length ? q.assignments.map((a) =>
    `<div class="asg"><span class="dot" style="background:${DISTRICT_HUES[a.district] || css("--faint")}"></span><div><b>${esc(a.district)}</b>
      <span class="mono">${a.addresses.join(" ")}</span>${a.watch ? `, watch ${a.watch}` : ""} · ${a.boys.length} boy${a.boys.length === 1 ? "" : "s"}
      ${a.look_for ? `<div class="muted">${esc(a.look_for)}</div>` : ""}</div></div>`).join("") : "<p class='muted small'>None out.</p>");
  const kinds = truthOn() ? SECRET.lead_kinds : null;
  h += `<h4>Latest reports</h4><div class="reports">` + q.notebook.slice(-8).reverse().map((r) =>
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
      <h4>Carrying</h4>` + (d.carrying.map((t) => `<div>• ${esc(t)}</div>`).join("") || "<div class='muted'>Nothing yet.</div>");
    return;
  }
  $("#selId").textContent = i;
  $("#selTraits").textContent = truthOn() && d.traits.length ? `(${d.traits.join(", ")})` : "";
  const L = d.last || {};
  const v = d.vote;
  $("#irrDetail").innerHTML = `<p style="margin:0">At <b>${esc(d.observation.you.at)}</b> · hears ${d.observation.you.irregulars_within_earshot} Irregulars</p>
    <p style="margin:4px 0">Last: <b>${esc(L.action || "-")}</b> <span class="muted">(${esc(L.source || "")})</span>. ${esc(L.result || "")}</p>
    <p style="margin:0">Vote: ${esc(v.culprit ? name("culprit", v.culprit) : "unsure")} / ${v.motive || "unsure"} / ${v.hideout || "unsure"}</p>
    <h4>Leads it holds</h4>` + d.observation.my_leads.map((l) => `<div>• ${esc(l.lead)} <span class="muted">(${esc(l.source)})</span></div>`).join("");
}

function card(label, value, title) { return `<div class="mc" title="${esc(title || "")}"><b>${value}</b><span>${label}</span></div>`; }

function renderInference(f) {
  const i = f.inference;
  $("#infCards").innerHTML = [
    card("decisions", i.decisions), card("model calls", i.calls), card("median latency", i.latency_p50 != null ? i.latency_p50 + " s" : "-"),
    card("tokens in", (i.tokens_in / 1000).toFixed(1) + "k", `${i.tokens_cached} cached`), card("tokens out", (i.tokens_out / 1000).toFixed(1) + "k"),
    card("cost", "$" + i.cost.toFixed(4)), card("fallbacks", i.fallbacks), card("timeouts", i.timeouts),
    card("model", (i.models[0] || i.policy).replace("typesafe/", "")),
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
    <b>${g.status === "open" ? "" : g.status}</b></div>`).join("") || "<span class='muted'>Lock in a guess at any time; it is scored against the truth when the case closes.</span>";
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
  $("#hideEnd").onclick = () => b.hidden = true;
  $("#againBtn").onclick = () => goLaunch();
  if (!$("#tTruth").checked) { $("#tTruth").checked = true; legend(); }
}

function goLaunch() {
  if (es) es.close();
  $("#dash").hidden = true; $("#launch").hidden = false; $("#endBanner").hidden = true;
  delete $("#endBanner").dataset.shown;
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

function baseLayer(c, cs) {
  const dpr = devicePixelRatio || 1, v = mapView(c);
  const key = `${c.id}|${v.W}x${v.H}|${effectiveTheme()}|${cs.map.addresses.length}|${cs.map.scene}|${cs.map.baker}`;
  if (BASES.has(key)) return {img: BASES.get(key), v};
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
  return {img: off, v};
}

/* ------------------------------------------------------------------ map: agents, tweening, overlays */
const AG = {prev: new Map(), cur: new Map(), t0: 0, dur: 0, last: 0, det: null};

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
    const cs = f.case || CASE;
    const A = cs.map.addresses.find((x) => x.id === f.at);
    const to = A ? [A.x, A.y] : null;
    AG.det = {from: AG.det ? detPos() : to, to};
  }
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
  const d = AG.det; if (!d || !d.to) return null;
  const k = ease(tweenK()), a = d.from || d.to;
  return [a[0] + (d.to[0] - a[0]) * k, a[1] + (d.to[1] - a[1]) * k];
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
  const {img, v} = baseLayer(c, cs);
  if (c.width !== Math.round(v.W * dpr) || c.height !== Math.round(v.H * dpr)) { c.width = v.W * dpr; c.height = v.H * dpr; }
  const g = c.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, c.width, c.height); g.drawImage(img, 0, 0);
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (!opt.preview) view = v;
  const P = (x, y) => [v.ox + x * v.s, v.oy + y * v.s];
  const M = cs.map;
  const A = {}; for (const a of M.addresses) A[a.id] = a;
  const truth = !opt.preview && truthOn() ? SECRET : null;
  const small = v.W < 520;
  const solo = f && f.mode === "solo";
  // truth overlay: what each lead really is
  if (truth) {
    for (const a of M.addresses) {
      const k = truth.lead_kinds[a.id];
      const col = k === "lie" ? css("--bad") : KEY.has(k) ? css("--good") : k === "pointer" ? css("--info") : null;
      if (!col) continue;
      const [x, y] = P(a.x, a.y); g.fillStyle = col; g.beginPath(); g.arc(x, y, 3, 0, 7); g.fill();
    }
  }
  // solo: route and visited addresses
  if (solo) {
    const pts = f.path.map((id) => P(A[id].x, A[id].y));
    const dp = detPos();
    g.strokeStyle = css("--accent"); g.lineWidth = 2; g.setLineDash([6, 5]); g.lineJoin = "round"; g.beginPath();
    pts.slice(0, -1).forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y));
    if (dp && pts.length > 1) { const [x, y] = P(dp[0], dp[1]); g.lineTo(x, y); }
    g.stroke(); g.setLineDash([]);
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
  if (!f) return;
  const now = performance.now();
  // shouts and deliveries as quiet expanding rings
  pulses = pulses.filter((p) => now - p.t0 < 1000);
  for (const p of pulses) {
    const k = (now - p.t0) / 1000, [x, y] = P(p.x, p.y);
    g.strokeStyle = css("--map-ink"); g.globalAlpha = 0.28 * (1 - k); g.lineWidth = 1;
    g.beginPath(); g.arc(x, y, (p.r || f.comm_range) * v.s * (0.15 + 0.85 * k), 0, 7); g.stroke(); g.globalAlpha = 1;
  }
  if (solo) {
    const dp = detPos();
    if (dp) {
      const [x, y] = P(dp[0], dp[1]);
      if (!REDUCED.matches && !f.ended) { g.strokeStyle = css("--accent"); g.globalAlpha = 0.5; g.lineWidth = 2; g.beginPath(); g.arc(x, y, 11 + 3 * Math.sin(now / 350), 0, 7); g.stroke(); g.globalAlpha = 1; }
      dot(g, x, y, 7, css("--ink"));
      g.fillStyle = css("--map-paper"); g.font = `700 9px ${css("--f-head") || "serif"}`; g.textAlign = "center"; g.fillText("H", x, y + 3); g.textAlign = "left";
    }
    return;
  }
  if (f.hub && A[f.hub.yard]) {
    const [yx, yy] = P(A[f.hub.yard].x, A[f.hub.yard].y);
    g.strokeStyle = css("--info"); g.globalAlpha = 0.6; g.setLineDash([4, 4]); g.beginPath(); g.arc(yx, yy, f.comm_range * v.s, 0, 7); g.stroke(); g.setLineDash([]); g.globalAlpha = 1;
  }
  if (f.hq) {
    const W = f.hq.wiggins;
    for (const r of f.irregulars) {
      const [i, , , dist, , state, flags, tgt, tailing] = r;
      const p = agentPos(i) || [r[1], r[2]];
      const jit = (i * 2.399963) % 6.283, rad = state === "idle" ? 8 + (i * 3.7) % 6 : 0;
      const [x, y] = P(p[0] + rad * Math.cos(jit), p[1] + rad * Math.sin(jit));
      if (tgt && A[tgt] && state !== "idle") {
        const [tx, ty] = P(A[tgt].x, A[tgt].y);
        g.strokeStyle = css("--map-ink"); g.globalAlpha = 0.25; g.setLineDash([2, 3]); g.lineWidth = 1;
        g.beginPath(); g.moveTo(x, y); g.lineTo(tx, ty); g.stroke(); g.setLineDash([]); g.globalAlpha = 1;
      }
      dot(g, x, y, i === selected ? 5 : 3.6, dist ? (DISTRICT_HUES[dist] || css("--faint")) : css("--faint"), state === "back" ? css("--ink") : null);
      if (tailing) { g.strokeStyle = css("--bad"); g.lineWidth = 1; g.setLineDash([2, 2]); g.beginPath(); g.arc(x, y, 8, 0, 7); g.stroke(); g.setLineDash([]); }
      if (truth && (flags & 1)) { g.strokeStyle = css("--bad"); g.lineWidth = 2; g.beginPath(); g.arc(x, y, 8, 0, 7); g.stroke(); }
      if (i === selected) { g.strokeStyle = css("--ink"); g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 9, 0, 7); g.stroke(); }
    }
    if (W) {
      if (A[W.post] && W.post !== f.hq.baker) { const [px, py] = P(A[W.post].x, A[W.post].y); g.strokeStyle = css("--ink"); g.lineWidth = 1.5; g.strokeRect(px - 7, py - 7, 14, 14); }
      const [wx, wy] = P(W.x, W.y);
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
    const [x, y] = P(p[0] + rad * Math.cos(jit), p[1] + rad * Math.sin(jit));
    const ci = order.indexOf(cu);
    dot(g, x, y, i === selected ? 4.6 : 3.2, cu ? SUS_COLORS[ci % 16] : css("--faint"));
    if (truth && (flags & 1)) { g.strokeStyle = css("--bad"); g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 7, 0, 7); g.stroke(); }
    if (i === selected) { g.strokeStyle = css("--ink"); g.lineWidth = 1.5; g.beginPath(); g.arc(x, y, 8, 0, 7); g.stroke(); }
  }
}

function legend() {
  const t = truthOn();
  const item = (color, text, shape = "") => `<span><i style="background:${color};${shape}"></i>${text}</span>`;
  let h = item("var(--accent)", "221B Baker Street") + item("var(--info)", "Scotland Yard", "border-radius:2px") +
    item("var(--bad)", "scene") + item("transparent", "possible hideout (▲)", "border:1.5px solid var(--map-ink);border-radius:2px") +
    item("transparent", "suspect's home", "border:2px solid var(--muted)");
  if (frame && frame.mode === "solo") h += item("var(--accent)", "visited, with the cab route");
  else if (frame && frame.hq) h += item("var(--ink)", "W = Wiggins (□ his post)") + item(DISTRICT_HUES.Soho, "boy, coloured by assignment district") +
    item("var(--surface)", "running back to report", "border:2px solid var(--ink)");
  else if (frame) h += item("var(--faint)", "Irregular, coloured by culprit vote (grey = unsure)");
  if (t) h += item("var(--good)", "true key lead") + item("var(--bad)", "lie") + item("var(--info)", "pointer");
  $("#legend").innerHTML = h;
}

function loop() {
  if (frame && CASE && !$("#dash").hidden) drawMap($("#map"), CASE, frame);
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
    const i = r[0], p = agentPos(i) || [r[1], r[2]];
    const idle = frame.hq ? r[5] === "idle" : true;
    const jit = (i * 2.399963) % 6.283, rad = frame.hq ? (idle ? 8 + (i * 3.7) % 6 : 0) : 5 + (i * 3.7) % 7;
    const x = view.ox + (p[0] + rad * Math.cos(jit)) * view.s, y = view.oy + (p[1] + rad * Math.sin(jit)) * view.s;
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
addEventListener("keydown", (e) => { if (e.code === "Space" && !$("#dash").hidden && !["INPUT", "SELECT", "BUTTON"].includes(e.target.tagName)) { e.preventDefault(); $("#playBtn").click(); } });
let rzTimer = null;
addEventListener("resize", () => { clearTimeout(rzTimer); rzTimer = setTimeout(() => { BASES.clear(); if (!$("#launch").hidden && PREVIEW) drawMap($("#preview"), PREVIEW, null, {preview: true}); if (frame) onFrame(frame, true); }, 120); });
applyThemeLabels();
if (document.fonts) document.fonts.ready.then(() => { BASES.clear(); if (PREVIEW && !$("#launch").hidden) drawMap($("#preview"), PREVIEW, null, {preview: true}); });
initLaunch();
requestAnimationFrame(loop);

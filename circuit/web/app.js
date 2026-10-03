"use strict";
/* Circuit: launch screen and live viewer. No framework; canvas for the schematic and the pipeline diagram. */

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = (p, body) => fetch(p, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json());
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

let SCHEMA = null, cfg = {}, PREV = null, STATIC = null, FRAME = null, ES = null;
let SECRET = null, SEL = null, HOVER = null, LAYOUT = null, PLAYOUT = null;
const agentPos = {};
const flashes = [];
let lastProbeN = 0;

const MODE_INFO = {
  jev: { name: "Jev swarm", color: "--jev" },
  hybrid: { name: "Hybrid swarm", color: "--hybrid" },
  cone: { name: "Exact cone tracing", color: "--cone" },
  rule_swarm: { name: "Rule swarm", color: "--rule" },
  genius: { name: "Solo genius", color: "--genius" },
};
const SWARM = new Set(["jev", "hybrid", "rule_swarm"]);

/* ---------------------------------------------------------------------------------------------- theme */
function effectiveTheme() {
  const t = document.documentElement.dataset.theme;
  return t || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function applyThemeLabels() { document.querySelectorAll(".theme-toggle").forEach((b) => (b.textContent = effectiveTheme() === "dark" ? "Light" : "Dark")); }
function toggleTheme() {
  const t = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("circuit-theme", t); } catch (e) { /* storage blocked */ }
  applyThemeLabels();
  redrawAll();
}
try { const t = localStorage.getItem("circuit-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* storage blocked */ }
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { applyThemeLabels(); redrawAll(); });
document.querySelectorAll(".theme-toggle").forEach((b) => b.addEventListener("click", toggleTheme));
applyThemeLabels();

/* ---------------------------------------------------------------------------------------------- layout */
const COLS = [
  { key: "IF", w: 1.0 }, { key: "IF/ID", w: 0.62 }, { key: "ID decode", w: 1.0 }, { key: "ID control", w: 1.0 },
  { key: "ID registers", w: 1.0 }, { key: "ID/EX", w: 0.62 }, { key: "EX fwd+branch", w: 1.0 }, { key: "EX ALU", w: 1.0 },
  { key: "EX/MEM", w: 0.62 }, { key: "MEM", w: 0.75 }, { key: "MEM/WB", w: 0.62 }, { key: "WB", w: 0.9 },
];
function colOf(b) {
  switch (b.stage) {
    case "IF": return 0;
    case "IF/ID": return 1;
    case "ID": return b.group === "decoder" ? 2 : (b.group === "control" || b.group === "hazard") ? 3 : 4;
    case "ID/EX": return 5;
    case "EX": return b.group === "alu" ? 7 : 6;
    case "EX/MEM": return 8;
    case "MEM": return 9;
    case "MEM/WB": return 10;
    default: return 11;
  }
}
function shortName(n) { return n.replace(/^(ifid|idex|exmem|memwb)_/, ""); }

function layout(blocks, W, H, compact) {
  const top = compact ? 6 : 26, bottom = compact ? 6 : 40, pad = compact ? 3 : 8;
  const tw = COLS.reduce((s, c) => s + c.w, 0);
  const cols = COLS.map(() => []);
  blocks.forEach((b) => cols[colOf(b)].push(b));
  const maxRows = Math.max(...cols.map((c) => c.length));
  const rowH = (H - top - bottom) / maxRows;
  const pos = {};
  let x = pad;
  const unit = (W - pad * 2) / tw;
  const colX = [];
  COLS.forEach((c, i) => {
    const cw = c.w * unit;
    colX.push([x, cw]);
    const list = cols[i];
    const y0 = top + (H - top - bottom - list.length * rowH) / 2;
    list.forEach((b, k) => {
      const bw = cw - (compact ? 2 : 10), bh = Math.max(3, rowH - (compact ? 1.5 : 6));
      pos[b.name] = { x: x + (cw - bw) / 2, y: y0 + k * rowH + (rowH - bh) / 2, w: bw, h: bh, b };
    });
    x += cw;
  });
  return { pos, colX, top, rowH, W, H, bottom };
}

function fitCanvas(c) {
  const r = c.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(10, Math.round(r.width)), h = Math.max(10, Math.round(r.height));
  if (c.width !== w * dpr || c.height !== h * dpr) { c.width = w * dpr; c.height = h * dpr; }
  const ctx = c.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}
function alpha(color, a) {
  // color is a #rrggbb css var value
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color);
  if (!m) return color;
  return `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a})`;
}

/* ---------------------------------------------------------------------------------------------- launch */
async function initLaunch() {
  SCHEMA = await api("/api/schema");
  cfg = { ...SCHEMA.defaults };
  renderModes(); renderCase(); renderForm(); renderKeys(); renderRuns(); estimate();
  $("#rejoinBtn").hidden = !SCHEMA.running;
  preview();
}
function setCfg(patch, opts = {}) {
  Object.assign(cfg, patch);
  renderModes(); estimate();
  if (opts.form !== false) renderForm();
  if (opts.panel) renderCase();
  if (opts.preview) preview();
}
function renderModes() {
  const el = $("#modes");
  el.innerHTML = "";
  Object.entries(SCHEMA.modes).forEach(([k, desc]) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "mode"; b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(cfg.mode === k));
    const [title, rest] = desc.split(": ");
    b.innerHTML = `<b><i class="dot" style="background:var(${MODE_INFO[k].color})"></i>${esc(title)}</b><span>${esc(rest || "")}</span>`;
    b.addEventListener("click", () => setCfg({ mode: k }, { panel: true }));
    el.appendChild(b);
  });
  $("#modeChip").textContent = MODE_INFO[cfg.mode].name;
}
function ctl(label, input, hint) {
  const d = document.createElement("div");
  d.className = "ctl";
  d.innerHTML = `<label>${esc(label)}</label>`;
  d.appendChild(input);
  if (hint) { const h = document.createElement("div"); h.className = "hint"; h.textContent = hint; d.appendChild(h); }
  return d;
}
function numInput(key, { min, max, step = 1 } = {}, opts = {}) {
  const i = document.createElement("input");
  i.type = "number"; i.value = cfg[key]; i.step = step;
  if (min !== undefined) i.min = min;
  if (max !== undefined) i.max = max;
  i.addEventListener("change", () => setCfg({ [key]: Number(i.value) }, opts));
  return i;
}
function selInput(key, choices, opts = {}) {
  const s = document.createElement("select");
  Object.entries(choices).forEach(([k, v]) => { const o = document.createElement("option"); o.value = k; o.textContent = v; s.appendChild(o); });
  s.value = cfg[key];
  s.addEventListener("change", () => setCfg({ [key]: s.value }, opts));
  return s;
}
function renderCase() {
  const el = $("#casePanel");
  el.innerHTML = "";
  const seed = document.createElement("div");
  seed.className = "seedrow";
  const si = numInput("seed", { min: 0 }, { preview: true, panel: true });
  const prev = document.createElement("button"); prev.type = "button"; prev.textContent = "◀"; prev.title = "previous bug";
  const next = document.createElement("button"); next.type = "button"; next.textContent = "▶"; next.title = "next bug";
  const rnd = document.createElement("button"); rnd.type = "button"; rnd.textContent = "random";
  prev.onclick = () => setCfg({ seed: Math.max(0, cfg.seed - 1) }, { preview: true, panel: true });
  next.onclick = () => setCfg({ seed: cfg.seed + 1 }, { preview: true, panel: true });
  rnd.onclick = () => setCfg({ seed: Math.floor(Math.random() * 1000) }, { preview: true, panel: true });
  seed.append(si, prev, next, rnd);
  const bt = SCHEMA.schema.find((g) => g[0] === "The bug")[1].find((f) => f[0] === "bug_type")[3];
  const g1 = document.createElement("div"); g1.className = "ctls";
  g1.append(ctl("Bug number", seed, "same number, same bug"), ctl("Kind of bug", selInput("bug_type", bt, { preview: true }), "the bug type is hidden from the investigators"),
    ctl("Cycles per check probe", numInput("window", { min: 1, max: 12 }, { preview: true }), "a check shows this many cycles"));
  const g2 = document.createElement("div"); g2.className = "ctls";
  g2.append(ctl("Probe budget", numInput("probe_budget", { min: 1 }), "checks + bench drives, every mode"),
    ctl("Dollar budget per case", numInput("budget_usd", { min: 0, step: 0.05 }), "the genius gets exactly this"));
  el.append(g1, g2);
  if (SWARM.has(cfg.mode)) {
    const g3 = document.createElement("div"); g3.className = "ctls";
    g3.append(ctl("Irregulars", numInput("n_irregulars", { min: 1, max: 64 })),
      ctl("Probes per Irregular per round", numInput("probes_per_irregular", { min: 1, max: 6 })),
      ctl("Most rounds", numInput("max_rounds", { min: 1, max: 40 })),
      ctl("Each Irregular gets", selInput("assign", { mixed: "a block or a window (mixed)", block: "one block", window: "a window of the waveform" })));
    el.append(g3);
  } else if (cfg.mode === "genius") {
    const g3 = document.createElement("div"); g3.className = "ctls";
    g3.append(ctl("Probes per turn", numInput("probes_per_turn", { min: 1, max: 20 })), ctl("Most turns", numInput("max_turns", { min: 1, max: 30 })));
    el.append(g3);
  }
}
function renderForm() {
  const f = $("#cfgForm");
  f.innerHTML = "";
  SCHEMA.schema.forEach(([group, fields]) => {
    const fs = document.createElement("fieldset");
    fs.innerHTML = `<legend>${esc(group)}</legend>`;
    const g = document.createElement("div"); g.className = "ctls";
    fields.forEach(([key, label, kind, extra]) => {
      let inp;
      if (kind === "choice") inp = selInput(key, extra, { form: false, panel: true, preview: key === "bug_type" });
      else if (kind === "bool") {
        inp = document.createElement("input"); inp.type = "checkbox"; inp.checked = !!cfg[key];
        inp.addEventListener("change", () => setCfg({ [key]: inp.checked }, { form: false, panel: true }));
      } else if (kind === "text") {
        inp = document.createElement("input"); inp.type = "text"; inp.value = cfg[key];
        inp.addEventListener("change", () => setCfg({ [key]: inp.value }, { form: false }));
      } else inp = numInput(key, { min: extra.min, max: extra.max, step: kind === "float" ? "any" : 1 }, { form: false, panel: true, preview: key === "seed" || key === "window" });
      g.appendChild(ctl(label, inp));
    });
    fs.appendChild(g);
    f.appendChild(fs);
  });
}
function renderKeys() {
  $("#keyStatus").innerHTML = SCHEMA.key_files.map((k) => `<div class="mono">${k.exists ? "✓" : "·"} ${esc(k.path)}</div>`).join("");
}
function renderRuns() {
  const r = SCHEMA.runs || [];
  $("#runsList").innerHTML = r.length ? r.map((x) => `<div class="run"><span class="mono">${esc(x.name.slice(0, 15))}</span>
    <span>${esc(MODE_INFO[x.mode]?.name || x.mode)} #${x.seed}</span><span class="${x.fix_ok ? "ok" : "no"}">${x.fix_ok ? "fixed" : "not fixed"}</span>
    <span class="muted">${x.probes} probes · $${(x.cost || 0).toFixed(3)}</span></div>`).join("") : "<span class='muted'>none yet</span>";
}
function estimate() {
  const c = cfg, lines = [];
  if (SWARM.has(c.mode)) {
    lines.push(`<p><b>${c.n_irregulars}</b> Irregulars × up to <b>${c.probes_per_irregular}</b> probes per round, at most <b>${c.max_rounds}</b> rounds.</p>`);
    if (c.mode === "jev") lines.push("<p>Jev decides every probe and judges every block; Jev Holmes names the bug. Typically well under $0.01 per case.</p>");
    if (c.mode === "hybrid") lines.push("<p>Jev decides every probe and which input to follow; the verdicts and the deduction are exact. Typically well under $0.01 per case.</p>");
    if (c.mode === "rule_swarm") lines.push("<p>No model calls: free.</p>");
  } else if (c.mode === "cone") lines.push("<p>One exact tracer checks the nearest unchecked block on the back-trace, one probe at a time. Free.</p>");
  else lines.push(`<p>gpt-6-astra reads the whole netlist each turn (up to ${c.max_turns} turns, ${c.probes_per_turn} probes per turn). Roughly $0.03-0.06 per turn.</p>`);
  lines.push(`<p class="muted">Budgets for every mode: ${c.probe_budget} probes, $${Number(c.budget_usd).toFixed(2)}.</p>`);
  $("#estimate").innerHTML = lines.join("");
}
let pvTimer = null;
function preview() {
  clearTimeout(pvTimer);
  pvTimer = setTimeout(async () => {
    const q = new URLSearchParams({ seed: cfg.seed, bug_type: cfg.bug_type, window: cfg.window });
    PREV = await api("/api/preview?" + q);
    $("#pvTitle").textContent = `Bug #${cfg.seed}: ${PREV.brief.test}`;
    $("#pvInfo").textContent = `${PREV.n} cycles`;
    $("#pvFail").innerHTML = `<p>${esc(PREV.brief.failure)}</p>`;
    $("#pvTests").innerHTML = PREV.results.map((r) => `<span class="${r.ok ? "good" : "bad"}" title="${esc(r.desc)}">${r.ok ? "✓" : "✗"} ${esc(r.name)}</span>`).join("");
    $("#pvSrc").textContent = PREV.brief.program.join("\n");
    drawPreview();
  }, 120);
}
function drawPreview() {
  if (!PREV) return;
  const c = $("#preview");
  const { ctx, w, h } = fitCanvas(c);
  PLAYOUT = layout(PREV.blocks, w, h, true);
  ctx.clearRect(0, 0, w, h);
  const starts = new Set(PREV.starts.map((s) => s[0]));
  for (const p of Object.values(PLAYOUT.pos)) {
    ctx.fillStyle = p.b.trusted ? css("--pipe") : css("--logic");
    ctx.strokeStyle = starts.has(p.b.name) ? css("--bad") : css("--line2");
    ctx.lineWidth = starts.has(p.b.name) ? 2 : 1;
    roundRect(ctx, p.x, p.y, p.w, p.h, 2); ctx.fill(); ctx.stroke();
  }
}
async function testModel(which) {
  const out = $("#testOut");
  out.hidden = false; out.textContent = "checking…";
  const r = await api("/api/test", { which, cfg });
  out.textContent = JSON.stringify(r, null, 1);
}
async function launch() {
  $("#launchErr").textContent = "";
  const r = await api("/api/launch", { cfg });
  if (!r.ok) { $("#launchErr").textContent = r.error || "launch failed"; return; }
  startDash();
}
$("#launchBtn").addEventListener("click", launch);
$("#rejoinBtn").addEventListener("click", startDash);
$("#testJev").addEventListener("click", () => testModel("jev"));
$("#testChat").addEventListener("click", () => testModel("chat"));

/* ---------------------------------------------------------------------------------------------- dashboard */
async function startDash() {
  STATIC = await api("/api/static");
  if (STATIC.error) return;
  FRAME = null; SECRET = null; SEL = null; lastProbeN = 0; flashes.length = 0;
  for (const k of Object.keys(agentPos)) delete agentPos[k];
  $("#launch").hidden = true; $("#dash").hidden = false;
  const m = MODE_INFO[STATIC.mode];
  $("#dTitle").textContent = `${m.name} · bug #${STATIC.cfg.seed} · ${STATIC.brief.test}`;
  $("#fTest").textContent = STATIC.brief.test;
  $("#fText").textContent = STATIC.brief.failure;
  $("#speed").value = STATIC.cfg.speed;
  $("#speedVal").textContent = STATIC.cfg.speed;
  $("#inspector").hidden = true;
  $("#resultCard").hidden = true;
  $("#tTruth").checked = false;
  renderLegend();
  if (ES) ES.close();
  ES = new EventSource("/api/stream");
  ES.onmessage = (e) => onFrame(JSON.parse(e.data));
  ES.onerror = () => { /* the server ends the stream when a new case starts */ };
  redrawAll();
}
function onFrame(f) {
  FRAME = f;
  if (f.probe_log && f.probes > lastProbeN) {
    const fresh = f.probes - lastProbeN;
    f.probe_log.slice(-fresh).forEach((p) => flashes.push({ block: p.block, t0: performance.now(), bad: p.mismatch }));
    lastProbeN = f.probes;
  }
  renderMetrics(f); renderSuspects(f); renderEvents(f); renderGuesses(f);
  $("#dPhase").textContent = f.ended ? "finished" : `${f.mode === "genius" ? "turn" : "round"} ${f.round} · ${f.phase}`;
  $("#bPause").textContent = f.paused ? "Resume" : "Pause";
  if (f.ended) showResult(f);
  drawWave();
}
function renderLegend() {
  const items = [["--logic", "logic block"], ["--pipe", "register / memory (verified)"], ["--front", "next on the back-trace", true],
    ["--good", "cleared"], ["--warn", "unsure"], ["--bad", "suspect"]];
  $("#legend").innerHTML = items.map(([v, t, ring]) => `<span><i style="${ring ? `border:2px solid var(${v});background:transparent` : `background:var(${v})`}"></i>${t}</span>`).join("");
}
function card(label, value, title) { return `<div class="mc" title="${esc(title || "")}"><b>${value}</b><span>${label}</span></div>`; }
function renderMetrics(f) {
  $("#metrics").innerHTML = [
    card("probes used", `${f.probes}<span class="meta">/${f.probe_budget}</span>`, "checks and bench drives"),
    card("model spend", `$${f.cost.toFixed(4)}`, `cap $${f.budget_usd}`),
    card("model calls", f.calls, `${f.failures} failed, ${f.fallbacks} fell back to the rule`),
    card(f.mode === "genius" ? "turn" : "round", f.round, f.phase),
    card("Irregulars", f.agents.length),
    card("seconds", f.elapsed.toFixed(0)),
  ].join("");
}
function renderSuspects(f) {
  const rows = Object.entries(f.heat).filter(([, v]) => v[1] === "x" || v[1] === "u" || v[1] === "r")
    .sort((a, b) => b[1][0] - a[1][0]).slice(0, 8);
  const label = { x: "suspect", u: "unsure", r: "red herring" };
  const col = { x: "--bad", u: "--warn", r: "--faint" };
  let html = rows.length ? rows.map(([b, v]) => `<div class="sus" data-b="${esc(b)}"><span class="mono">${esc(b)}</span><span class="meta">${label[v[1]]} ${v[0].toFixed(2)}</span>
      <div class="bar"><i style="width:${Math.round(v[0] * 100)}%;background:var(${col[v[1]]})"></i></div></div>`).join("") : "<p class='muted'>No suspects yet.</p>";
  const cleared = Object.values(f.heat).filter((v) => v[1] === "c").length;
  html += `<p class="meta">${cleared} block${cleared === 1 ? "" : "s"} cleared.` +
    (f.frontier.length ? ` Next on the back-trace: ${f.frontier.slice(0, 5).map((x) => `<span class="mono">${esc(x[0])}@${x[1]}</span>`).join(", ")}` : "") + "</p>";
  if (f.answer) html += `<p><b>Named:</b> <span class="mono">${esc(f.answer.block)}.${esc(f.answer.port)}</span> — ${esc(f.answer.desc || "")}</p>`;
  $("#suspects").innerHTML = html;
  $("#suspects").querySelectorAll(".sus").forEach((d) => d.addEventListener("click", () => select(d.dataset.b)));
}
function renderEvents(f) {
  $("#events").innerHTML = f.events.slice().reverse().map((e) => `<div class="ev ${esc(e.kind)}"><span class="t">${e.t.toFixed(1)}s</span>${esc(e.text)}</div>`).join("");
}
function renderGuesses(f) {
  if (!f.guesses.length) return;
  $("#guesses").innerHTML = f.guesses.map((g) => `<div>You suspected <span class="mono">${esc(g.block)}</span> after ${g.probes} probes` +
    (f.ended && f.secret ? (g.block === f.secret.block ? " — <span class='ok'>right</span>" : " — <span class='no'>wrong</span>") : "") + "</div>").join("");
}
function showResult(f) {
  const r = f.result, s = f.secret, a = f.answer;
  if (!r || !s) return;
  const el = $("#resultCard");
  el.hidden = false;
  el.className = "card result " + (r.fix_ok ? "win" : "lose");
  const mk = (ok) => `<span class="${ok ? "ok" : "no"}">${ok ? "yes" : "no"}</span>`;
  el.innerHTML = `<h3>${r.fix_ok ? "Fixed: every test passes" : "Not fixed"}</h3>
    <p class="small">${a ? `Named <span class="mono">${esc(a.block)}.${esc(a.port)}</span>: ${esc(a.desc || "")}` : "No answer."}</p>
    <p class="small">The bug: <span class="mono">${esc(s.block)}.${esc(s.port)}</span>, ${esc(s.type_label)}: ${esc(s.desc)}.</p>
    <div class="marks small"><span>Faulty block</span>${mk(r.block_ok)}<span>Exact location (block + signal)</span>${mk(r.location_ok)}
      <span>Bug type</span>${mk(r.type_ok)}<span>Fix passes the tests</span><span>${mk(r.fix_ok)} <span class="meta">${r.tests_passed ?? "-"}/${r.tests_total}</span></span>
      <span>Probes</span><span class="mono">${f.probes}/${f.probe_budget}</span><span>Model spend</span><span class="mono">$${f.cost.toFixed(4)}</span></div>
    <button type="button" id="bNew2" class="primary">New case</button>`;
  $("#bNew2").onclick = goLaunch;
}

/* ---------------------------------------------------------------------------------------------- schematic */
function blockStatus(name) { return FRAME && FRAME.heat[name]; }
function drawSchem(now) {
  const c = $("#schem");
  if (!STATIC || $("#dash").hidden) return;
  const { ctx, w, h } = fitCanvas(c);
  LAYOUT = layout(STATIC.blocks, w, h, false);
  const L = LAYOUT;
  ctx.clearRect(0, 0, w, h);
  // column headers and separators
  ctx.font = "600 10.5px " + css("--f-ui");
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  L.colX.forEach(([x, cw], i) => {
    ctx.fillStyle = css("--muted");
    ctx.fillText(COLS[i].key, x + cw / 2, 12);
    if (COLS[i].w < 0.7) { ctx.fillStyle = alpha(css("--pipe"), 0.35); ctx.fillRect(x + 2, L.top - 4, cw - 4, h - L.top - L.bottom + 8); }
  });
  // edges of the selected / hovered block
  const focus = HOVER || SEL;
  if (focus) {
    for (const [src, dst, port] of STATIC.edges) {
      if (src !== focus && dst !== focus) continue;
      const a = L.pos[src], b = L.pos[dst];
      if (!a || !b) continue;
      const x1 = a.x + a.w, y1 = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2;
      ctx.strokeStyle = dst === focus ? css("--info") : css("--accent");
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      if (x2 > x1) { const mx = (x1 + x2) / 2; ctx.moveTo(x1, y1); ctx.bezierCurveTo(mx, y1, mx, y2, x2, y2); }
      else { ctx.moveTo(x1, y1); ctx.bezierCurveTo(x1 + 40, y1 - 60, x2 - 40, y2 - 60, x2, y2); }
      ctx.stroke();
    }
  }
  const truth = ($("#tTruth").checked && SECRET) || (FRAME && FRAME.ended && FRAME.secret) || null;
  const guessSet = new Set((FRAME?.guesses || []).map((g) => g.block));
  const starts = new Set(STATIC.starts.map((s) => s[0]));
  ctx.font = "10.5px " + css("--f-mono");
  for (const p of Object.values(L.pos)) {
    const st = blockStatus(p.b.name);
    ctx.fillStyle = p.b.trusted ? css("--pipe") : css("--logic");
    roundRect(ctx, p.x, p.y, p.w, p.h, 4); ctx.fill();
    if (st) {
      const [s, k] = st;
      if (k === "x") { ctx.fillStyle = alpha(css("--bad"), 0.25 + 0.6 * s); roundRect(ctx, p.x, p.y, p.w, p.h, 4); ctx.fill(); }
      else if (k === "c") { ctx.fillStyle = alpha(css("--good"), 0.22); roundRect(ctx, p.x, p.y, p.w, p.h, 4); ctx.fill(); }
      else if (k === "u") { ctx.fillStyle = alpha(css("--warn"), 0.3); roundRect(ctx, p.x, p.y, p.w, p.h, 4); ctx.fill(); }
      else if (k === "r") { ctx.fillStyle = alpha(css("--faint"), 0.25); roundRect(ctx, p.x, p.y, p.w, p.h, 4); ctx.fill(); }
    }
    ctx.lineWidth = 1; ctx.strokeStyle = css("--line2"); ctx.setLineDash([]);
    if (st && st[1] === "f") { ctx.strokeStyle = css("--front"); ctx.lineWidth = 1.5 + 3 * st[0]; }
    if (st && st[1] === "r") ctx.setLineDash([4, 3]);
    if (starts.has(p.b.name) && !st) { ctx.strokeStyle = css("--bad"); ctx.lineWidth = 1.5; }
    if (p.b.name === SEL) { ctx.strokeStyle = css("--ink"); ctx.lineWidth = 2; }
    roundRect(ctx, p.x, p.y, p.w, p.h, 4); ctx.stroke(); ctx.setLineDash([]);
    if (FRAME?.answer && FRAME.answer.block === p.b.name) {
      ctx.strokeStyle = css("--accent"); ctx.lineWidth = 2.5; roundRect(ctx, p.x - 3, p.y - 3, p.w + 6, p.h + 6, 6); ctx.stroke();
    }
    if (truth && truth.block === p.b.name) {
      ctx.strokeStyle = css("--bad"); ctx.lineWidth = 2.5; ctx.setLineDash([5, 3]);
      roundRect(ctx, p.x - 5, p.y - 5, p.w + 10, p.h + 10, 7); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = css("--bad"); ctx.font = "600 10px " + css("--f-ui"); ctx.textAlign = "right";
      ctx.fillText("BUG", p.x + p.w, p.y - 9); ctx.font = "10.5px " + css("--f-mono");
    }
    ctx.fillStyle = css("--ink"); ctx.textAlign = "center"; ctx.textBaseline = "middle";
    let label = p.b.trusted ? shortName(p.b.name) : p.b.name;
    while (label.length > 2 && ctx.measureText(label).width > p.w - 6) label = label.slice(0, -1);
    if (p.h >= 9) ctx.fillText(label, p.x + p.w / 2, p.y + p.h / 2 + 0.5);
    if (guessSet.has(p.b.name)) { ctx.fillStyle = css("--accent"); ctx.font = "13px " + css("--f-ui"); ctx.fillText("★", p.x + p.w - 6, p.y + 5); ctx.font = "10.5px " + css("--f-mono"); }
  }
  // probe flashes
  for (let i = flashes.length - 1; i >= 0; i--) {
    const fl = flashes[i], p = L.pos[fl.block];
    const age = (now - fl.t0) / 900;
    if (age > 1 || !p) { flashes.splice(i, 1); continue; }
    ctx.strokeStyle = alpha(fl.bad ? css("--bad") : css("--info"), 1 - age);
    ctx.lineWidth = 2;
    roundRect(ctx, p.x - 6 * age - 2, p.y - 6 * age - 2, p.w + 12 * age + 4, p.h + 12 * age + 4, 6); ctx.stroke();
  }
  drawAgents(ctx, L, w, h);
}
function drawAgents(ctx, L, w, h) {
  if (!FRAME) return;
  const color = css(MODE_INFO[FRAME.mode].color);
  const at = {};
  FRAME.agents.forEach((a) => { const k = a.status === "idle" || !a.block ? "_hq" : a.block; (at[k] = at[k] || []).push(a); });
  for (const [k, list] of Object.entries(at)) {
    list.forEach((a, i) => {
      let tx, ty;
      if (k === "_hq") { tx = 20 + (a.id - 1) * 20; ty = h - 16; }
      else {
        const p = L.pos[k];
        if (!p) return;
        const n = list.length;
        tx = p.x + p.w - 4 - (i % 4) * 13 - (n > 4 ? 0 : 0);
        ty = p.y + p.h / 2 + (i >= 4 ? 10 : 0);
      }
      const cur = agentPos[a.id] || (agentPos[a.id] = { x: 20 + (a.id - 1) * 20, y: h - 16 });
      cur.x += (tx - cur.x) * 0.12; cur.y += (ty - cur.y) * 0.12;
      ctx.beginPath(); ctx.arc(cur.x, cur.y, 7.5, 0, Math.PI * 2);
      ctx.fillStyle = color; ctx.fill();
      ctx.lineWidth = 1.5; ctx.strokeStyle = a.status === "probing" ? css("--ink") : css("--surface"); ctx.stroke();
      ctx.fillStyle = "#fff"; ctx.font = "600 9px " + css("--f-ui"); ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(FRAME.mode === "genius" ? "G" : FRAME.mode === "cone" ? "T" : String(a.id), cur.x, cur.y + 0.5);
    });
  }
  ctx.fillStyle = css("--muted"); ctx.font = "10.5px " + css("--f-ui"); ctx.textAlign = "left";
  const idle = (at._hq || []).length;
  ctx.fillText(idle ? "Baker Street (waiting for the next round)" : "", 20 + idle * 20, h - 16);
}
function hit(x, y) {
  if (!LAYOUT) return null;
  for (const p of Object.values(LAYOUT.pos)) if (x >= p.x && x <= p.x + p.w && y >= p.y && y <= p.y + p.h) return p.b.name;
  return null;
}
$("#schem").addEventListener("mousemove", (e) => {
  const r = e.target.getBoundingClientRect();
  HOVER = hit(e.clientX - r.left, e.clientY - r.top);
  e.target.title = HOVER ? `${HOVER}: ${LAYOUT.pos[HOVER].b.spec}` : "";
});
$("#schem").addEventListener("mouseleave", () => (HOVER = null));
$("#schem").addEventListener("click", (e) => {
  const r = e.target.getBoundingClientRect();
  const b = hit(e.clientX - r.left, e.clientY - r.top);
  if (b) select(b);
});

function select(name) {
  SEL = name;
  const b = STATIC.blocks.find((x) => x.name === name);
  const el = $("#inspector");
  el.hidden = false;
  const fr = FRAME?.frontier.find((x) => x[0] === name);
  const cyc = fr ? fr[1] : (STATIC.brief.first_bad_cycle ?? 0);
  const st = blockStatus(name);
  const stText = st ? ({ x: "suspect", c: "cleared", u: "unsure", r: "red herring", f: "next on the back-trace" }[st[1]]) : "not looked at";
  el.innerHTML = `<div class="card-head"><h3 class="mono">${esc(name)}</h3><span class="meta">${esc(b.stage)} · ${esc(b.group)} · ${stText}</span></div>
    <p class="small">${esc(b.spec)}</p>
    <p class="small muted">${Object.entries(b.ins).map(([p, n]) => `<span class="mono">${esc(p)}</span>←${esc(n)}`).join(", ") || "no inputs"}<br>
      outputs: ${Object.entries(b.outs).map(([p, w]) => `<span class="mono">${esc(p)}</span>:${w}`).join(", ")}${b.trusted ? " · verified IP" : ""}</p>
    <div class="insp-head small"><span>Free look at cycle</span><input type="number" id="iCyc" min="0" max="${STATIC.n - 1}" value="${cyc}">
      <button type="button" id="iLook">Look</button><button type="button" id="iGuess" class="primary">I suspect this block</button></div>
    <p class="meta">A free look shows the values only. Comparing them with the spec is what costs the investigators a probe.</p>
    <div id="iRows"></div>`;
  $("#iLook").onclick = () => look(name);
  $("#iGuess").onclick = async () => { await api("/api/guess", { block: name }); };
  look(name);
}
async function look(name) {
  const cyc = Number($("#iCyc").value) || 0;
  const r = await api(`/api/inspect?block=${encodeURIComponent(name)}&cycle=${cyc}`);
  if (r.error) return;
  const fmt = (o) => Object.entries(o).map(([k, v]) => `${k}=${v}`).join(" ");
  $("#iRows").innerHTML = `<table class="rows"><tr><th>cyc</th><th>instr</th><th>in</th><th>out</th></tr>` +
    r.rows.map((x) => `<tr><td>${x.cycle}</td><td>${esc(x.instr || "-")}</td><td>${esc(fmt(x.in))}</td><td>${esc(fmt(x.out))}</td></tr>`).join("") + "</table>";
}

/* ---------------------------------------------------------------------------------------------- pipeline diagram */
function drawWave() {
  if (!STATIC || $("#dash").hidden) return;
  const c = $("#wave");
  const { ctx, w, h } = fitCanvas(c);
  ctx.clearRect(0, 0, w, h);
  const n = STATIC.n, left = 44, top = 16, rows = ["IF", "ID", "EX", "MEM", "WB"];
  const rh = (h - top - 34) / rows.length, cw = (w - left - 6) / n;
  ctx.font = "10px " + css("--f-mono"); ctx.textBaseline = "middle";
  // probed windows
  const log = FRAME?.probe_log || [];
  log.forEach((p, i) => {
    if (p.type !== "check" || !p.window) return;
    const x = left + p.window[0] * cw, ww = (p.window[1] - p.window[0] + 1) * cw;
    const recent = i >= log.length - 3;
    ctx.fillStyle = alpha(p.mismatch ? css("--bad") : css("--info"), recent ? 0.22 : 0.07);
    ctx.fillRect(x, top, ww, rh * rows.length);
    ctx.fillStyle = alpha(p.mismatch ? css("--bad") : css("--info"), 0.8);
    ctx.fillRect(x, h - 30 + (i % 3) * 5, ww, 3);
  });
  rows.forEach((r, k) => {
    ctx.fillStyle = css("--muted"); ctx.textAlign = "left";
    ctx.fillText(r, 6, top + k * rh + rh / 2);
  });
  ctx.textAlign = "center";
  for (let cy = 0; cy < n; cy++) {
    const occ = STATIC.occupancy[cy];
    for (let k = 0; k < 5; k++) {
      const pc = occ[k];
      const x = left + cy * cw, y = top + k * rh;
      ctx.strokeStyle = css("--trace"); ctx.lineWidth = 0.5; ctx.strokeRect(x, y, cw, rh);
      if (pc !== null && cw >= 9) { ctx.fillStyle = css("--ink"); ctx.fillText(String(pc), x + cw / 2, y + rh / 2); }
    }
    if (cy % 5 === 0) { ctx.fillStyle = css("--faint"); ctx.fillText(String(cy), left + cy * cw + cw / 2, 7); }
  }
  // failure and frontier
  const fc = STATIC.brief.first_bad_cycle;
  if (fc !== null && fc !== undefined) {
    ctx.strokeStyle = css("--bad"); ctx.lineWidth = 2;
    ctx.strokeRect(left + fc * cw, top, cw, rh * rows.length);
    ctx.fillStyle = css("--bad"); ctx.textAlign = "left"; ctx.font = "600 10px " + css("--f-ui");
    ctx.fillText("fails here", Math.min(w - 60, left + fc * cw + cw + 3), top - 6 < 8 ? 8 : top - 6);
  }
  (FRAME?.frontier || []).forEach(([b, cy]) => {
    const x = left + cy * cw + cw / 2;
    ctx.fillStyle = css("--front");
    ctx.beginPath(); ctx.moveTo(x - 4, h - 34); ctx.lineTo(x + 4, h - 34); ctx.lineTo(x, h - 30); ctx.fill();
  });
  $("#wvInfo").textContent = `${STATIC.brief.test}: ${n} cycles · bands = checked windows (red: caught a mismatch) · ▾ next on the back-trace`;
  c.onmousemove = (e) => {
    const r = c.getBoundingClientRect();
    const cy = Math.floor((e.clientX - r.left - left) / cw);
    if (cy < 0 || cy >= n) return;
    const occ = STATIC.occupancy[cy];
    const txt = rows.map((s, k) => `${s} ${occ[k] === null ? "-" : (STATIC.brief.program[occ[k]] || `${occ[k]}: NOP`).replace(/^\s*\d+: /, `${occ[k]} `)}`).join(" | ");
    $("#wvHover").textContent = `cycle ${cy}: ${txt}`;
  };
}

/* ---------------------------------------------------------------------------------------------- controls */
$("#bPause").addEventListener("click", () => api("/api/cmd", { action: FRAME?.paused ? "resume" : "pause" }));
$("#bStep").addEventListener("click", () => api("/api/cmd", { action: "step" }));
$("#speed").addEventListener("input", (e) => {
  $("#speedVal").textContent = e.target.value;
  api("/api/cmd", { action: "set", cfg: { speed: Number(e.target.value) } });
});
$("#bNew").addEventListener("click", goLaunch);
$("#tTruth").addEventListener("change", () => { if ($("#tTruth").checked && !SECRET) api("/api/secret").then((s) => { if (!s.error) SECRET = s; }); });
function goLaunch() {
  if (ES) { ES.close(); ES = null; }
  $("#dash").hidden = true; $("#launch").hidden = false;
  initLaunch();
}
function redrawAll() { drawPreview(); drawWave(); }
window.addEventListener("resize", redrawAll);
function loop(now) { drawSchem(now); requestAnimationFrame(loop); }
requestAnimationFrame(loop);

initLaunch();

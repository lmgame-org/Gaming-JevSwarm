"use strict";
/* Circuit: launch screen and live viewer. No framework; canvas for the schematic, the timeline and the vote chart.
   Patterns follow holmes/web (camera, tweened agents, captions, title card, stamp, end banner), redrawn for a chip. */

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = (p, body) => fetch(p, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json());
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)");
const ease = (k) => (k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2);

let SCHEMA = null, cfg = {}, PREV = null, ST = null, F = null, es = null, SECRET = null;
let track = "leader";

/* ---------------------------------------------------------------------------------------------- theme */
function effectiveTheme() { return document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); }
function themeLabels() { document.querySelectorAll(".theme-toggle").forEach((b) => (b.textContent = effectiveTheme() === "dark" ? "Light" : "Dark")); }
function toggleTheme() {
  const t = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("circuit-theme", t); } catch (e) { /* storage blocked */ }
  themeLabels(); BASES.clear(); drawPreview(); drawWave(); drawSeries();
}
try { const t = localStorage.getItem("circuit-theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) { /* storage blocked */ }
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { themeLabels(); BASES.clear(); });
document.querySelectorAll(".theme-toggle").forEach((b) => b.addEventListener("click", toggleTheme));
themeLabels();

function alpha(color, a) {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(color);
  return m ? `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a})` : color;
}
function fitCanvas(c) {
  const r = c.getBoundingClientRect(), dpr = devicePixelRatio || 1;
  const w = Math.max(10, Math.round(r.width)), h = Math.max(10, Math.round(r.height));
  if (c.width !== w * dpr || c.height !== h * dpr) { c.width = w * dpr; c.height = h * dpr; }
  const g = c.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { g, w, h };
}
function rr(g, x, y, w, h, r) {
  g.beginPath(); g.moveTo(x + r, y); g.arcTo(x + w, y, x + w, y + h, r); g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r); g.arcTo(x, y, x + w, y, r); g.closePath();
}

/* ---------------------------------------------------------------------------------------------- families */
const FAM = {
  solo: { name: "Solo debugger", color: "--solo", sub: "One investigator, one probe at a time, 10 probes" },
  leader: { name: "Baker Street", color: "--boy", sub: "Holmes plans at 221B, Wiggins runs reports, a dozen boys probe" },
  swarm: { name: "Swarm", color: "--irr", sub: "100 Irregulars, no leader: radio range, liar defence, quorum" },
};
const OPT = {
  solo_policy: { chat: ["gpt-6-astra", "the genius: reads the netlist and asks for probes"], jev: ["Jev", "one quick call per probe"],
    rule: ["rule (cone tracing)", "re-measures mismatches, follows the back-trace (free)"], random: ["random", "a baseline (free)"] },
  holmes: { chat: ["gpt-6-astra", "reads every report and plans the errands"], rule: ["exact counting", "back-trace planner, two boys per mismatch (free)"] },
  boy_policy: { jev: ["Jev", "a small local choice each step"], rule: ["rule", "do the errand, re-measure, run back (free)"], random: ["random", "a baseline (free)"] },
  swarm_policy: { jev: ["Jev", "Jev decides what to chase and how to vote"], hybrid: ["hybrid", "Jev chases, exact counting votes"],
    rule: ["rule", "reproduce, share, vote only what you reproduced (free)"], random: ["random", "a baseline (free)"] },
};
function benchKey(c) {
  if (c.mode === "solo") return `solo_${c.solo_policy === "chat" ? "genius" : c.solo_policy}`;
  if (c.mode === "leader") return `baker_${c.holmes === "chat" ? "genius" : "rule"}_${c.boy_policy}${c.wiggins ? "" : "_nowiggins"}`;
  return `swarm_${c.swarm_policy}_r${c.comm_range}`;
}
function setupLabel(c) {
  if (c.mode === "solo") return `Solo · ${OPT.solo_policy[c.solo_policy][0]}`;
  if (c.mode === "leader") return `Baker Street · ${c.holmes === "chat" ? "gpt-6-astra" : "counting"} Holmes, ${c.boy_policy} boys${c.wiggins ? "" : ", no Wiggins"}`;
  return `Swarm · ${c.swarm_policy} · ${c.comm_range} wires`;
}
function famColor(c) { return css(c.mode === "solo" ? "--solo" : c.mode === "leader" ? "--boy" : "--irr"); }

/* ---------------------------------------------------------------------------------------------- schematic layout */
const COLS = [
  { key: "IF", w: 1.0 }, { key: "IF/ID", w: 0.6 }, { key: "ID decode", w: 1.0 }, { key: "ID control", w: 1.05 },
  { key: "ID registers", w: 1.0 }, { key: "ID/EX", w: 0.6 }, { key: "EX fwd + branch", w: 1.05 }, { key: "EX ALU", w: 1.0 },
  { key: "EX/MEM", w: 0.6 }, { key: "MEM", w: 0.75 }, { key: "MEM/WB", w: 0.6 }, { key: "WB", w: 0.9 },
];
const VW = 1000, VH = 640, TOP = 34, FLOOR = 572;
function colOf(b) {
  switch (b.stage) {
    case "IF": return 0; case "IF/ID": return 1;
    case "ID": return b.group === "decoder" ? 2 : (b.group === "control" || b.group === "hazard") ? 3 : 4;
    case "ID/EX": return 5; case "EX": return b.group === "alu" ? 7 : 6;
    case "EX/MEM": return 8; case "MEM": return 9; case "MEM/WB": return 10; default: return 11;
  }
}
const short = (n) => n.replace(/^(ifid|idex|exmem|memwb)_/, "");
function layout(blocks) {
  const tw = COLS.reduce((s, c) => s + c.w, 0), unit = (VW - 16) / tw;
  const cols = COLS.map(() => []);
  blocks.forEach((b) => cols[colOf(b)].push(b));
  const maxRows = Math.max(...cols.map((c) => c.length)), rowH = (FLOOR - TOP - 10) / maxRows;
  const pos = {}, colX = [];
  let x = 8;
  COLS.forEach((c, i) => {
    const cw = c.w * unit; colX.push([x, cw]);
    const list = cols[i], y0 = TOP + (FLOOR - TOP - 10 - list.length * rowH) / 2;
    list.forEach((b, k) => {
      const bw = cw - 12, bh = rowH - 6;
      pos[b.name] = { x: x + 6, y: y0 + k * rowH + 3, w: bw, h: bh, cx: x + cw / 2, cy: y0 + k * rowH + rowH / 2, b };
    });
    x += cw;
  });
  return { pos, colX, rowH };
}
let LAY = null, ADJ = null, BY = {};
function prepare(blocks, edges) {
  LAY = layout(blocks);
  BY = {}; blocks.forEach((b) => (BY[b.name] = b));
  ADJ = {}; blocks.forEach((b) => (ADJ[b.name] = new Set()));
  for (const [a, b] of edges) { if (a !== b) { ADJ[a].add(b); ADJ[b].add(a); } }
  PATHS.clear();
}
const PATHS = new Map();
function wirePath(a, b) {
  if (!a || !b || a === b || !ADJ[a] || !ADJ[b]) return null;
  const k = a + ">" + b;
  if (PATHS.has(k)) return PATHS.get(k);
  const prev = { [a]: null }, q = [a];
  while (q.length) { const u = q.shift(); if (u === b) break; for (const v of ADJ[u]) if (!(v in prev)) { prev[v] = u; q.push(v); } }
  const ids = []; let u = b; while (u) { ids.unshift(u); u = prev[u]; }
  const pts = ids.map((id) => [LAY.pos[id].cx, LAY.pos[id].cy]);
  if (PATHS.size > 4000) PATHS.clear();
  PATHS.set(k, pts);
  return pts;
}
function along(pts, f) {
  if (!pts || pts.length === 1) return pts ? pts[0] : null;
  const segs = []; let total = 0;
  for (let i = 1; i < pts.length; i++) { const l = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); segs.push(l); total += l; }
  let d = Math.max(0, Math.min(1, f)) * total;
  for (let i = 0; i < segs.length; i++) {
    if (d <= segs[i]) { const t = segs[i] ? d / segs[i] : 0; return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t]; }
    d -= segs[i];
  }
  return pts[pts.length - 1];
}
const DESK = [120, FLOOR + 40];
function postXY(col) { if (col === null || col === undefined || !LAY) return null; const [x, cw] = LAY.colX[col]; return [x + cw / 2, FLOOR + 34]; }

/* ---------------------------------------------------------------------------------------------- camera */
const CAM = { z: 1, cx: VW / 2, cy: VH / 2, from: null, to: null, t0: 0, dur: 0, drag: null };
function view(c) { const W = c.clientWidth, H = c.clientHeight; return { W, H, s: Math.min(W / VW, H / VH) }; }
function camNow() {
  if (!CAM.to) return CAM;
  const k = CAM.dur ? Math.min(1, (performance.now() - CAM.t0) / CAM.dur) : 1, e = ease(k);
  CAM.z = CAM.from.z + (CAM.to.z - CAM.from.z) * e; CAM.cx = CAM.from.cx + (CAM.to.cx - CAM.from.cx) * e; CAM.cy = CAM.from.cy + (CAM.to.cy - CAM.from.cy) * e;
  if (k >= 1) CAM.to = null;
  return CAM;
}
function camTo(z, cx, cy, dur = 900) { CAM.from = { z: CAM.z, cx: CAM.cx, cy: CAM.cy }; CAM.to = { z, cx, cy }; CAM.t0 = performance.now(); CAM.dur = REDUCED.matches ? 0 : dur; }
const P = (v, x, y) => [v.W / 2 + (x - CAM.cx) * v.s * CAM.z, v.H / 2 + (y - CAM.cy) * v.s * CAM.z];
const UP = (v, X, Y) => [CAM.cx + (X - v.W / 2) / (v.s * CAM.z), CAM.cy + (Y - v.H / 2) / (v.s * CAM.z)];

/* ---------------------------------------------------------------------------------------------- base layer */
const BASES = new Map();
function baseLayer(c) {
  const v = view(c), dpr = devicePixelRatio || 1;
  const key = `${v.W}x${v.H}|${effectiveTheme()}|${CAM.z.toFixed(3)}|${CAM.cx.toFixed(1)}|${CAM.cy.toFixed(1)}|${ST ? ST.cfg.seed : 0}`;
  if (BASES.has(key)) return BASES.get(key);
  if (BASES.size > 8) BASES.delete(BASES.keys().next().value);
  const off = document.createElement("canvas"); off.width = v.W * dpr; off.height = v.H * dpr;
  const g = off.getContext("2d"); g.scale(dpr, dpr);
  g.fillStyle = css("--board"); g.fillRect(0, 0, v.W, v.H);
  const S = v.s * CAM.z;
  // stage bands
  LAY.colX.forEach(([x, cw], i) => {
    const [x1, y1] = P(v, x, TOP - 6), [x2, y2] = P(v, x + cw, FLOOR);
    g.fillStyle = COLS[i].w < 0.7 ? css("--band-pipe") : (i % 2 ? css("--band") : "transparent");
    g.fillRect(x1, y1, x2 - x1, y2 - y1);
    g.fillStyle = css("--muted"); g.font = `600 ${Math.max(8, 10.5 * Math.min(1.4, S))}px ${css("--f-ui")}`; g.textAlign = "center";
    const [lx, ly] = P(v, x + cw / 2, TOP - 14); g.fillText(COLS[i].key, lx, ly);
  });
  // bench floor
  const [fx1, fy1] = P(v, 0, FLOOR + 6), [fx2, fy2] = P(v, VW, VH);
  g.fillStyle = css("--band-pipe"); g.fillRect(fx1, fy1, fx2 - fx1, fy2 - fy1);
  // wires
  // forward wires solid; feedback wires (to an earlier stage) fainter, so the pipeline still reads left to right
  const back = (a, b) => LAY.pos[b] && LAY.pos[a] && LAY.pos[b].x <= LAY.pos[a].x + LAY.pos[a].w;
  g.lineWidth = Math.max(0.6, 0.8 * S);
  g.strokeStyle = css("--wire"); g.beginPath();
  for (const [a, b] of ST.edges) if (!back(a, b)) wireCurve(g, v, a, b);
  g.stroke();
  g.save(); g.globalAlpha = 0.35; g.setLineDash([3, 4]); g.beginPath();
  for (const [a, b] of ST.edges) if (back(a, b)) wireCurve(g, v, a, b);
  g.stroke(); g.restore();
  // blocks
  for (const p of Object.values(LAY.pos)) {
    const [x, y] = P(v, p.x, p.y), w = p.w * S, h = p.h * S;
    rr(g, x, y, w, h, 4 * Math.min(1, S)); g.fillStyle = p.b.trusted ? css("--pipe") : css("--logic"); g.fill();
    g.strokeStyle = css("--line2"); g.lineWidth = 1; g.stroke();
    if (h > 9) {
      g.fillStyle = p.b.trusted ? css("--pipe-ink") : css("--board-ink");
      g.font = `${p.b.trusted ? 400 : 500} ${Math.min(13, Math.max(8, 10 * S))}px ${css("--f-mono")}`; g.textAlign = "center"; g.textBaseline = "middle";
      let lab = p.b.trusted ? short(p.b.name) : p.b.name;
      while (lab.length > 2 && g.measureText(lab).width > w - 6) lab = lab.slice(0, -1);
      g.fillText(lab, x + w / 2, y + h / 2 + 0.5);
    }
  }
  g.textBaseline = "alphabetic";
  // 221B desk
  const [dx, dy] = P(v, 12, FLOOR + 12), dw = 150 * S, dh = 52 * S;
  rr(g, dx, dy, dw, dh, 6); g.fillStyle = css("--surface"); g.fill(); g.strokeStyle = css("--line2"); g.stroke();
  g.fillStyle = css("--muted"); g.font = `600 ${Math.max(8, 10 * S)}px ${css("--f-ui")}`; g.textAlign = "left";
  g.fillText(ST.mode === "leader" ? "221B BAKER STREET" : ST.mode === "solo" ? "THE BENCH" : "THE BENCH FLOOR", dx + 8 * S, dy + 14 * S);
  BASES.set(key, off);
  return off;
}
function wireCurve(g, v, a, b, only) {
  const A = LAY.pos[a], B = LAY.pos[b];
  if (!A || !B) return;
  const [x1, y1] = P(v, A.x + A.w, A.cy), [x2, y2] = P(v, B.x, B.cy);
  g.moveTo(x1, y1);
  if (x2 > x1 + 4) { const mx = (x1 + x2) / 2; g.bezierCurveTo(mx, y1, mx, y2, x2, y2); }
  else { const lift = P(v, 0, TOP - 4)[1]; g.bezierCurveTo(x1 + 30, Math.min(y1, y2) - 40, x2 - 30, lift + 10, x2, y2); }
}

/* ---------------------------------------------------------------------------------------------- agents and tweening */
const AG = { prev: new Map(), cur: new Map(), t0: 0, dur: 0, last: 0 };
const RUN0 = new Map();     // boy id -> tick he started running back
let WIG0 = null;            // tick Wiggins started running
const FLASH = [];
const RIPPLE = [];
let lastProbeN = 0;
function anchorOf(a) {
  if (a.block && LAY.pos[a.block]) return { block: a.block, xy: [LAY.pos[a.block].cx, LAY.pos[a.block].cy] };
  if (a.where === "post" && F && F.post !== null && F.post !== undefined) return { block: null, xy: postXY(F.post) };
  return { block: null, xy: [DESK[0] + 30, DESK[1]] };
}
function retarget(f) {
  const now = performance.now();
  const gap = AG.last ? Math.min(1400, Math.max(150, now - AG.last)) : 0;
  AG.last = now;
  const shown = new Map();
  for (const id of AG.cur.keys()) shown.set(id, agentXY(id));
  AG.prev = new Map();
  for (const [id, xy] of shown) AG.prev.set(id, { xy, block: (AG.cur.get(id) || {}).block });
  AG.cur = new Map();
  for (const a of f.agents) AG.cur.set(a.id, anchorOf(a));
  AG.t0 = now; AG.dur = REDUCED.matches ? 0 : gap * 0.92;
}
function tk() { return AG.dur ? Math.min(1, (performance.now() - AG.t0) / AG.dur) : 1; }
function agentXY(id) {
  const c = AG.cur.get(id); if (!c) return null;
  const p = AG.prev.get(id);
  if (!p) return c.xy;
  const k = ease(tk());
  if (F && F.mode !== "swarm" && p.block && c.block && p.block !== c.block) {
    const pts = wirePath(p.block, c.block);
    if (pts) return along(pts, k);
  }
  return [p.xy[0] + (c.xy[0] - p.xy[0]) * k, p.xy[1] + (c.xy[1] - p.xy[1]) * k];
}

/* ---------------------------------------------------------------------------------------------- drawing the live map */
const VOTEC = ["--v1", "--v2", "--v3", "--v4", "--v5"];
function voteColor(label) {
  if (!F || !F.tally) return css("--faint");
  const i = F.tally.findIndex((t) => t[0] === label);
  return i >= 0 && i < VOTEC.length ? css(VOTEC[i]) : css("--muted");
}
function truthOn() { return $("#tTruth").checked && SECRET; }
let HOVER = null, SEL = null;

function drawMap(now) {
  const c = $("#map");
  if (!ST || $("#dash").hidden || !LAY) return;
  camNow();
  const { g, w, h } = fitCanvas(c), v = view(c), S = v.s * CAM.z;
  g.drawImage(baseLayer(c), 0, 0, w, h);
  if (!F) return;
  // focus wires (selected / hovered block)
  const focus = (HOVER && HOVER.kind === "block" && HOVER.id) || (SEL && SEL.kind === "block" && SEL.id);
  if (focus) {
    for (const [a, b] of ST.edges) {
      if (a !== focus && b !== focus) continue;
      g.strokeStyle = b === focus ? css("--wire-hot") : css("--wire-out"); g.lineWidth = 1.6;
      g.beginPath(); wireCurve(g, v, a, b); g.stroke();
    }
  }
  // heat
  const starts = new Set(ST.starts.map((s) => s[0]));
  for (const p of Object.values(LAY.pos)) {
    const [x, y] = P(v, p.x, p.y), bw = p.w * S, bh = p.h * S, st = F.heat[p.b.name];
    if (st) {
      const [s, k] = st;
      g.save(); rr(g, x, y, bw, bh, 4 * Math.min(1, S));
      if (k === "x") { g.fillStyle = alpha(css("--bad"), 0.3 + 0.5 * s); g.fill(); }
      else if (k === "c") { g.fillStyle = alpha(css("--good"), 0.22); g.fill(); }
      else if (k === "u") { g.fillStyle = alpha(css("--warn"), 0.28); g.fill(); }
      else if (k === "f") { g.setLineDash([4, 3]); g.lineDashOffset = -now / 60; g.strokeStyle = css("--front"); g.lineWidth = 1.2 + 2.2 * s; g.stroke(); }
      g.restore();
    }
    if (starts.has(p.b.name)) {
      g.fillStyle = css("--bad"); g.beginPath(); g.arc(x + bw - 3, y + 3, 4.5, 0, 7); g.fill();
      g.fillStyle = "#fff"; g.font = `700 7px ${css("--f-ui")}`; g.textAlign = "center"; g.fillText("!", x + bw - 3, y + 5.5);
    }
    if (SEL && SEL.kind === "block" && SEL.id === p.b.name) { rr(g, x - 2, y - 2, bw + 4, bh + 4, 6); g.strokeStyle = css("--ink"); g.lineWidth = 2; g.stroke(); }
    if (F.answer && F.answer.fixes.some((x2) => x2.block === p.b.name)) { rr(g, x - 4, y - 4, bw + 8, bh + 8, 7); g.strokeStyle = css("--accent"); g.lineWidth = 2.5; g.stroke(); }
    if (truthOn() && SECRET.bugs.some((bg) => bg.block === p.b.name)) {
      g.save(); g.setLineDash([5, 3]); rr(g, x - 6, y - 6, bw + 12, bh + 12, 8); g.strokeStyle = css("--bad"); g.lineWidth = 2.5; g.stroke(); g.restore();
      g.fillStyle = css("--bad"); g.font = `700 ${Math.max(9, 10 * S)}px ${css("--f-ui")}`; g.textAlign = "right"; g.fillText("BUG", x + bw + 4, y - 8);
    }
    if ((F.guesses || []).some((q) => q.block === p.b.name)) { g.fillStyle = css("--accent"); g.font = `14px ${css("--f-ui")}`; g.textAlign = "left"; g.fillText("★", x + 2, y + 11); }
  }
  // probe flashes
  for (let i = FLASH.length - 1; i >= 0; i--) {
    const fl = FLASH[i], p = LAY.pos[fl.block], age = (now - fl.t0) / 1000;
    if (age > 1 || !p) { FLASH.splice(i, 1); continue; }
    const [x, y] = P(v, p.x, p.y), bw = p.w * S, bh = p.h * S, e = 7 * age;
    rr(g, x - e, y - e, bw + 2 * e, bh + 2 * e, 6); g.strokeStyle = alpha(fl.bad ? css("--bad") : css("--info"), 1 - age); g.lineWidth = 2; g.stroke();
  }
  if (F.mode === "solo") drawSolo(g, v, S, now);
  else if (F.mode === "leader") drawLeader(g, v, S, now);
  else drawSwarm(g, v, S, now);
}
function token(g, x, y, r, fill, label, ring) {
  g.beginPath(); g.arc(x, y, r, 0, 7); g.fillStyle = fill; g.fill();
  g.lineWidth = ring ? 2 : 1.4; g.strokeStyle = ring ? css("--ink") : css("--surface"); g.stroke();
  if (label) { g.fillStyle = effectiveTheme() === "dark" && fill === css("--holmes") ? "#131816" : "#fff"; g.font = `600 ${Math.max(8, r * 1.05)}px ${css("--f-ui")}`;
    g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(label, x, y + 0.5); g.textBaseline = "alphabetic"; }
}
function drawSolo(g, v, S, now) {
  const tr = F.trail || [];
  // the probe path: a fading polyline through every block probed, numbered
  const pts = tr.map((t) => LAY.pos[t.block]).filter(Boolean);
  if (pts.length > 1) {
    for (let i = 1; i < pts.length; i++) {
      const a = P(v, pts[i - 1].cx, pts[i - 1].cy), b = P(v, pts[i].cx, pts[i].cy);
      g.strokeStyle = alpha(css("--solo"), 0.15 + 0.6 * (i / pts.length)); g.lineWidth = 2;
      g.setLineDash([6, 4]); g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
    }
    g.setLineDash([]);
  }
  tr.forEach((t, i) => {
    const p = LAY.pos[t.block]; if (!p) return;
    const [x, y] = P(v, p.x + 10, p.y + p.h - 4);
    g.beginPath(); g.arc(x, y, 7, 0, 7); g.fillStyle = t.mismatch ? css("--bad") : css("--surface"); g.fill();
    g.strokeStyle = css("--solo"); g.lineWidth = 1.4; g.stroke();
    g.fillStyle = t.mismatch ? "#fff" : css("--ink"); g.font = `600 8px ${css("--f-mono")}`; g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(String(i + 1), x, y + 0.5); g.textBaseline = "alphabetic";
  });
  const a = F.agents[0], xy = agentXY(a.id);
  if (xy) { const [x, y] = P(v, xy[0], xy[1]); token(g, x, y - 12, 9, css("--solo"), F.policy === "chat" ? "G" : F.policy === "jev" ? "J" : "D", true); }
}
function drawLeader(g, v, S, now) {
  // Holmes at his desk, Wiggins at his post (or running to Baker Street with the bag)
  const [hx, hy] = P(v, 30, FLOOR + 44); token(g, hx, hy, 10, css("--holmes"), "H");
  g.fillStyle = css("--ink"); g.font = `${Math.max(9, 10.5 * Math.min(1.3, S))}px ${css("--f-ui")}`; g.textAlign = "left";
  g.fillText(F.holmes && F.holmes.kind === "chat" ? "Holmes · gpt-6-astra" : "Holmes · counting", hx + 15, hy + 4);
  const post = F.post !== null && F.post !== undefined ? postXY(F.post) : null;
  if (post) {
    let wxy = post;
    if (F.transit && F.transit.length) {
      if (WIG0 === null) WIG0 = F.tick;
      const arr = Math.min(...F.transit.map((t) => t.arrive)), span = Math.max(1, arr - WIG0);
      const k = Math.min(1, (F.tick - 1 + tk() - WIG0) / span);
      wxy = [post[0] + (DESK[0] - post[0]) * k, post[1] + (DESK[1] - post[1]) * k];
    } else WIG0 = null;
    const [px, py] = P(v, post[0], post[1]);
    g.strokeStyle = css("--wiggins"); g.lineWidth = 1.5; g.beginPath(); g.moveTo(px, py + 12); g.lineTo(px, py - 14); g.stroke();
    g.fillStyle = css("--wiggins"); g.beginPath(); g.moveTo(px, py - 14); g.lineTo(px + 12, py - 10); g.lineTo(px, py - 6); g.fill();
    const [wx, wy] = P(v, wxy[0], wxy[1]); token(g, wx + 12, wy + 2, 9, css("--wiggins"), "W");
    if (F.bag) { g.fillStyle = css("--muted"); g.font = `10px ${css("--f-ui")}`; g.textAlign = "left"; g.fillText(`bag: ${F.bag}`, wx + 24, wy + 6); }
  }
  // dashed lines from each boy to the blocks left on his errand
  const runners = new Map((F.runners || []).map((r) => [r.boy, r]));
  for (const a of F.agents) {
    const xy = agentXY(a.id); if (!xy) continue;
    if (a.items && a.items.length && a.status !== "returning") {
      g.save(); g.setLineDash([3, 4]); g.strokeStyle = alpha(css("--boy"), 0.55); g.lineWidth = 1.2;
      a.items.forEach((b, i) => {
        if ((a.done || []).includes(i)) return;
        const p = LAY.pos[b]; if (!p) return;
        const [x1, y1] = P(v, xy[0], xy[1]), [x2, y2] = P(v, p.cx, p.cy);
        g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke();
      });
      g.restore();
    }
  }
  for (const a of F.agents) {
    let xy = agentXY(a.id); if (!xy) continue;
    const r = runners.get(a.id);
    if (r) {   // running back with the report, envelope in hand
      if (!RUN0.has(a.id)) RUN0.set(a.id, F.tick);
      const t0 = RUN0.get(a.id), dest = r.to === "post" && post ? post : DESK, span = Math.max(1, r.arrive - t0);
      const k = Math.min(1, (F.tick - 1 + tk() - t0) / span);
      xy = [xy[0] + (dest[0] - xy[0]) * k, xy[1] + (dest[1] - xy[1]) * k];
    } else RUN0.delete(a.id);
    const [x, y] = P(v, xy[0], xy[1]);
    const liar = truthOn() && (F.liars || SECRET.liars || []).includes(a.id);
    token(g, x + ((a.id % 4) - 1.5) * 6, y + (a.id % 3) * 5 - 5, 7.5, css("--boy"), String(a.id), a.status === "probing");
    if (liar) { g.strokeStyle = css("--liar"); g.lineWidth = 2; g.beginPath(); g.arc(x + ((a.id % 4) - 1.5) * 6, y + (a.id % 3) * 5 - 5, 10.5, 0, 7); g.stroke(); }
    if (r) { g.fillStyle = css("--surface"); g.strokeStyle = css("--boy"); g.lineWidth = 1; g.fillRect(x + 6, y - 14, 10, 7); g.strokeRect(x + 6, y - 14, 10, 7);
      g.beginPath(); g.moveTo(x + 6, y - 14); g.lineTo(x + 11, y - 10); g.lineTo(x + 16, y - 14); g.stroke(); }
    if (SEL && SEL.kind === "agent" && SEL.id === a.id) { g.strokeStyle = css("--ink"); g.lineWidth = 2; g.beginPath(); g.arc(x, y, 13, 0, 7); g.stroke(); }
  }
}
let DOTS = [];
function drawSwarm(g, v, S, now) {
  DOTS = [];
  // radio ripples where someone shared this tick
  for (let i = RIPPLE.length - 1; i >= 0; i--) {
    const rp = RIPPLE[i], age = (now - rp.t0) / 1400, p = LAY.pos[rp.block];
    if (age > 1 || !p) { RIPPLE.splice(i, 1); continue; }
    const [x, y] = P(v, p.cx, p.cy), R = (14 + 26 * (F.range || 2)) * S * ease(age);
    g.strokeStyle = alpha(css("--info"), 0.45 * (1 - age)); g.lineWidth = 1.2; g.beginPath(); g.arc(x, y, R, 0, 7); g.stroke();
  }
  const byBlock = {};
  for (const a of F.agents) (byBlock[a.block] = byBlock[a.block] || []).push(a);
  const leading = F.tally && F.tally[0] ? F.tally[0][0] : null;
  for (const [b, list] of Object.entries(byBlock)) {
    const p = LAY.pos[b]; if (!p) continue;
    list.forEach((a, i) => {
      const xy = agentXY(a.id); if (!xy) return;
      // a strip of dots along the bottom edge of the block, below its label
      const per = Math.max(6, Math.floor((p.w - 8) / 6.5)), col = i % per, row = Math.floor(i / per);
      const ox = -p.w / 2 + 5 + col * ((p.w - 10) / Math.max(1, per - 1)), oy = p.h / 2 - 3.2 - row * 4.2;
      const [x, y] = P(v, xy[0] + ox, xy[1] + oy);
      const vc = a.vote ? voteColor(a.vote) : css("--irr");
      DOTS.push({ id: a.id, x, y });
      g.beginPath(); g.arc(x, y, a.vote ? 2.9 : 2.3, 0, 7); g.fillStyle = a.vote ? vc : alpha(vc, 0.85); g.fill();
      if (a.vote === leading && a.vote) { g.strokeStyle = css("--surface"); g.lineWidth = 0.8; g.stroke(); }
      if (truthOn() && (F.liars || SECRET.liars || []).includes(a.id)) { g.strokeStyle = css("--liar"); g.lineWidth = 1.6; g.beginPath(); g.arc(x, y, 5.5, 0, 7); g.stroke(); }
      if (SEL && SEL.kind === "agent" && SEL.id === a.id) { g.strokeStyle = css("--ink"); g.lineWidth = 2; g.beginPath(); g.arc(x, y, 8, 0, 7); g.stroke(); }
    });
  }
}

/* ---------------------------------------------------------------------------------------------- map interaction */
function hitTest(e) {
  const c = $("#map"), r = c.getBoundingClientRect(), v = view(c), X = e.clientX - r.left, Y = e.clientY - r.top;
  if (F && F.mode !== "swarm") {
    for (const a of F.agents) { const xy = agentXY(a.id); if (!xy) continue; const [x, y] = P(v, xy[0], xy[1]); if (Math.hypot(x - X, y - Y) < 11) return { kind: "agent", id: a.id, X, Y }; }
  }
  if (F && F.mode === "swarm") {
    let best = null, bd = 6;
    for (const d of DOTS) { const dd = Math.hypot(d.x - X, d.y - Y); if (dd < bd) { bd = dd; best = d; } }
    if (best) return { kind: "agent", id: best.id, X, Y };
  }
  const [mx, my] = UP(v, X, Y);
  for (const p of Object.values(LAY.pos)) {
    if (mx >= p.x && mx <= p.x + p.w && my >= p.y && my <= p.y + p.h) return { kind: "block", id: p.b.name, X, Y };
  }
  return null;
}
function setupMap() {
  const c = $("#map");
  c.addEventListener("wheel", (e) => {
    e.preventDefault(); const r = c.getBoundingClientRect(), v = view(c);
    const [mx, my] = UP(v, e.clientX - r.left, e.clientY - r.top);
    const z = Math.max(1, Math.min(5, CAM.z * Math.exp(-e.deltaY * 0.0015)));
    CAM.to = null; CAM.cx = mx - (mx - CAM.cx) * CAM.z / z; CAM.cy = my - (my - CAM.cy) * CAM.z / z; CAM.z = z;
    if (z === 1) { CAM.cx = VW / 2; CAM.cy = VH / 2; }
  }, { passive: false });
  c.addEventListener("pointerdown", (e) => { CAM.drag = { x: e.clientX, y: e.clientY, cx: CAM.cx, cy: CAM.cy, moved: false }; });
  window.addEventListener("pointerup", () => { setTimeout(() => (CAM.drag = null), 0); });
  c.addEventListener("pointermove", (e) => {
    if (CAM.drag && (e.buttons & 1)) {
      const v = view(c), dx = e.clientX - CAM.drag.x, dy = e.clientY - CAM.drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) CAM.drag.moved = true;
      if (CAM.z > 1) { CAM.cx = CAM.drag.cx - dx / (v.s * CAM.z); CAM.cy = CAM.drag.cy - dy / (v.s * CAM.z); }
      return;
    }
    HOVER = hitTest(e); showTip(HOVER);
  });
  c.addEventListener("mouseleave", () => { HOVER = null; showTip(null); });
  c.addEventListener("dblclick", () => camTo(1, VW / 2, VH / 2));
  c.addEventListener("click", (e) => {
    if (CAM.drag && CAM.drag.moved) return;
    const h = hitTest(e); if (!h) return;
    select(h.kind, h.id);
    if (h.kind === "block" && CAM.z < 1.5) { const p = LAY.pos[h.id]; camTo(1.8, p.cx, p.cy); }
  });
}
function showTip(h) {
  const t = $("#tip");
  if (!h || !F) { t.hidden = true; return; }
  let html = "";
  if (h.kind === "block") {
    const b = BY[h.id], st = F.heat[h.id], here = F.agents.filter((a) => a.block === h.id).length;
    const status = st ? { x: "confirmed bad", c: "cleared", u: "mismatched once", f: "next on the back-trace", r: "red herring" }[st[1]] : (b.trusted ? "verified IP" : "not looked at");
    html = `<b>${esc(h.id)}</b> <span class="meta">${esc(b.stage)} · ${status}${here ? ` · ${here} agent${here > 1 ? "s" : ""} here` : ""}</span><br>${esc(b.spec)}`;
  } else {
    const a = F.agents.find((x) => x.id === h.id);
    html = `<b>${F.mode === "leader" ? "boy" : "Irregular"} #${h.id}</b> <span class="meta">${esc(a.status)}</span><br>${esc(a.last || "")}`;
  }
  t.innerHTML = html; t.hidden = false;
  const card = $("#map").parentElement.getBoundingClientRect(), r = $("#map").getBoundingClientRect();
  t.style.left = Math.min(card.width - 340, h.X + r.left - card.left + 14) + "px"; t.style.top = (h.Y + r.top - card.top + 14) + "px";
}

/* ---------------------------------------------------------------------------------------------- selection */
async function select(kind, id) {
  SEL = { kind, id };
  if (kind === "block") {
    const b = BY[id], st = F && F.heat[id];
    const status = st ? { x: "confirmed bad", c: "cleared", u: "mismatched once", f: "next on the back-trace" }[st[1]] : (b.trusted ? "verified IP (never broken)" : "not looked at yet");
    $("#selTitle").textContent = id; $("#selMeta").textContent = `${b.stage} · ${b.group} · ${status}`;
    const fr = F ? F.frontier.find((x) => x[0] === id) : null;
    const cyc = fr ? fr[1] : (ST.starts[0] ? ST.starts[0][1] : 0);
    $("#selBody").innerHTML = `<p>${esc(b.spec)}</p>
      <div class="kv small"><span>inputs</span><span class="mono">${Object.entries(b.ins).map(([p, n]) => `${esc(p)}←${esc(n)}`).join(", ") || "-"}</span>
      <span>outputs</span><span class="mono">${Object.entries(b.outs).map(([p, w]) => `${esc(p)}:${w}`).join(", ")}</span>
      <span>possible faults</span><span class="mono">${b.faults.length ? esc(b.faults.join(", ")) : "none (verified)"}</span></div>
      <div class="row gap small" style="margin-top:8px"><span>free look at cycle</span><input id="iCyc" type="number" min="0" max="${ST.n - 1}" value="${cyc}" style="width:80px">
        <button id="iLook">Look</button>${b.trusted ? "" : `<button id="iGuess" class="primary">I suspect it</button>`}</div>
      <div class="meta">A free look shows values only; comparing them with the spec is what costs the investigators a probe.</div><div id="iRows"></div>`;
    $("#iLook").onclick = () => look(id);
    if ($("#iGuess")) $("#iGuess").onclick = () => api("/api/guess", { block: id });
    look(id);
  } else {
    const d = await api(`/api/agent?id=${id}`);
    const who = d.role === "boy" ? "Boy" : d.role === "irr" ? "Irregular" : "Debugger";
    $("#selTitle").textContent = `${who} #${id}`;
    $("#selMeta").textContent = d.role === "boy" ? `${d.status}${d.liar ? " · BRIBED" : ""}` : d.role === "irr" ? `${(d.action || "").toLowerCase()} at ${d.at}${d.liar ? " · LIAR" : ""}` : d.policy;
    const sus = (d.suspects || []).map((s) => `<div class="mono small">${esc(s.block)}: ${s.bad_measurements} bad, ${s.confirmed ? "confirmed" : "unconfirmed"}</div>`).join("") || "<span class='muted'>none</span>";
    let kv = "";
    if (d.role === "boy") kv = `<span>errand</span><span>${esc(d.errand || "none")}</span><span>reports so far</span><span>${d.reports_by_him}</span><span>Holmes trusts him</span><span>${d.distrusted_by_holmes ? "no" : "yes"}</span>`;
    else if (d.role === "irr") kv = `<span>vote</span><span class="mono">${esc((d.vote || "unsure").replace("|", " / "))}</span><span>plan</span><span>${esc(d.plan ? d.plan.join(" ") : "reflex")}</span>
      <span>cleared blocks</span><span>${d.cleared}</span><span>votes heard</span><span class="mono">${esc((d.heard_votes || []).map(([l, k]) => `${l.split("|")[0]}×${k}`).join(", ") || "-")}</span>
      <span>distrusts</span><span class="mono">${esc((d.distrusts || []).join(", ") || "nobody")}</span>`;
    else kv = `<span>at</span><span class="mono">${esc(d.at || "-")}</span><span>doing</span><span>${esc(d.last || "")}</span>`;
    const probes = (d.probes || []).map((p) => `<div class="mono small">${esc(p.probe)}</div>`).join("");
    $("#selBody").innerHTML = `<div class="kv small">${kv}</div><h4 class="sub-h" style="margin-top:8px">Suspects in its notebook</h4>${sus}${probes ? `<h4 class="sub-h" style="margin-top:8px">Last probes</h4>${probes}` : ""}`;
  }
  renderRoster();
}
async function look(id) {
  const cyc = Number($("#iCyc").value) || 0;
  const r = await api(`/api/inspect?block=${encodeURIComponent(id)}&cycle=${cyc}`);
  if (r.error) return;
  const fmt = (o) => Object.entries(o).map(([k, v]) => `${k}=${v}`).join(" ");
  $("#iRows").innerHTML = `<table class="rows"><tr><th>cyc</th><th>instr</th><th>in</th><th>out</th></tr>` +
    r.rows.map((x) => `<tr><td>${x.cycle}</td><td>${esc(x.instr || "-")}</td><td>${esc(fmt(x.in))}</td><td>${esc(fmt(x.out))}</td></tr>`).join("") + "</table>";
}

/* ---------------------------------------------------------------------------------------------- launch */
async function initLaunch() {
  SCHEMA = await api("/api/schema");
  cfg = { ...SCHEMA.defaults, ...(window.__cfg || {}) };
  track = cfg.mode;
  renderTracks(); renderCase(); renderForm(); renderKeys(); renderRuns(); estimate();
  $("#rejoinBtn").hidden = !SCHEMA.running;
  preview();
}
function setCfg(patch, o = {}) {
  Object.assign(cfg, patch); window.__cfg = cfg;
  if (o.tracks !== false) renderTracks();
  if (o.form !== false) renderForm();
  if (o.case) renderCase();
  estimate();
  if (o.preview) preview();
}
function benchLine(key) {
  const b = (SCHEMA.bench || {})[key];
  return b ? `${b.solved}/${b.n} solved · ${b.cost}` : "not benchmarked yet";
}
function optGroup(title, key, note) {
  const d = document.createElement("div"); d.className = "group";
  d.innerHTML = `<h4>${esc(title)}</h4>${note ? `<p class="meta" style="margin:-4px 0 8px">${esc(note)}</p>` : ""}`;
  const box = document.createElement("div"); box.className = "opts";
  for (const [k, [name, sub]] of Object.entries(OPT[key])) {
    const b = document.createElement("button"); b.type = "button"; b.className = "opt"; b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(cfg[key] === k));
    const probe = { ...cfg, [key]: k };
    b.innerHTML = `<b>${esc(name)}</b><span class="sub">${esc(sub)}</span><span class="stat">${esc(benchLine(benchKey(probe)))}</span>`;
    b.onclick = () => setCfg({ [key]: k });
    box.appendChild(b);
  }
  d.appendChild(box);
  return d;
}
function slider(key, label, { min, max, step, fmt = (x) => x, hint = "" }) {
  const d = document.createElement("div"); d.className = "ctl";
  d.innerHTML = `<label>${esc(label)} <span class="val">${esc(fmt(cfg[key]))}</span></label><input type="range" min="${min}" max="${max}" step="${step}" value="${cfg[key]}">${hint ? `<span class="hint">${esc(hint)}</span>` : ""}`;
  const i = d.querySelector("input");
  i.oninput = () => { d.querySelector(".val").textContent = fmt(Number(i.value)); };
  i.onchange = () => setCfg({ [key]: Number(i.value) }, { preview: ["rare_frac", "double_frac", "window"].includes(key) });
  return d;
}
function toggle(key, label, hint) {
  const d = document.createElement("div"); d.className = "ctl";
  d.innerHTML = `<label class="toggle"><input type="checkbox" ${cfg[key] ? "checked" : ""}><span class="track"></span>${esc(label)}</label>${hint ? `<span class="hint">${esc(hint)}</span>` : ""}`;
  d.querySelector("input").onchange = (e) => setCfg({ [key]: e.target.checked });
  return d;
}
function selectCtl(key, label, choices, o = {}) {
  const d = document.createElement("div"); d.className = "ctl";
  d.innerHTML = `<label>${esc(label)}</label><select>${Object.entries(choices).map(([k, v]) => `<option value="${esc(k)}" ${String(cfg[key]) === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>`;
  d.querySelector("select").onchange = (e) => setCfg({ [key]: e.target.value }, o);
  return d;
}
function grid(...items) { const d = document.createElement("div"); d.className = "ctls"; items.forEach((x) => d.appendChild(x)); return d; }
function renderTracks() {
  const t = $("#tracks"); t.innerHTML = "";
  for (const [k, f] of Object.entries(FAM)) {
    const b = document.createElement("button"); b.type = "button"; b.setAttribute("role", "tab"); b.setAttribute("aria-selected", String(cfg.mode === k));
    b.innerHTML = `<b><i style="background:var(${f.color})"></i>${esc(f.name)}</b><span>${esc(f.sub)}</span>`;
    b.onclick = () => setCfg({ mode: k });
    t.appendChild(b);
  }
  const p = $("#trackPanel"); p.innerHTML = "";
  const how = document.createElement("p"); how.className = "how";
  if (cfg.mode === "solo") {
    how.innerHTML = "<b>One debugger</b> works alone: every probe costs 15 minutes and one of a small budget. It accuses when it is sure, or when its probes or time run out.";
    p.append(how, optGroup("The debugger", "solo_policy"), grid(slider("probe_budget", "Probes allowed", { min: 2, max: 40, step: 1, hint: "checks, bench drives and (genius) waveform reads" })));
  } else if (cfg.mode === "leader") {
    how.innerHTML = "<b>Holmes</b> never leaves 221B: he reads reports, sends <b>boys</b> on errands of one to three blocks, and names the bug when sure. <b>Wiggins</b> carries orders to a forward post and runs the reports back. Bribed boys hide the bug and frame an innocent block.";
    p.append(how, optGroup("Holmes, the decision-maker", "holmes"), optGroup("The street boys", "boy_policy"),
      grid(slider("n_boys", "Number of boys", { min: 1, max: 40, step: 1 }), toggle("wiggins", "Wiggins collects reports at a forward post", "off: every boy walks back to 221B"),
        slider("errand_max", "Blocks per errand", { min: 1, max: 6, step: 1 })));
  } else {
    how.innerHTML = "<b>100 Irregulars</b> start one per block, with no leader. Each tick each one checks its block, moves one wire, shares its findings by radio, or waits; the case closes when enough of them vote the same block and fault. Liars push a frame-up.";
    p.append(how, optGroup("The Irregulars", "swarm_policy"),
      grid(slider("comm_range", "Radio range (wires)", { min: 0, max: 8, step: 1 }), slider("n_agents", "Irregulars", { min: 10, max: 200, step: 10 }),
        slider("quorum_frac", "Quorum (share voting the same)", { min: 0.1, max: 0.6, step: 0.05, fmt: (x) => `${Math.round(x * 100)}%` }),
        slider("bandwidth", "Shares taken in per tick", { min: 1, max: 10, step: 1 })));
  }
  const bl = document.createElement("div"); bl.className = "bench-line";
  bl.innerHTML = `Benchmark for this setup: <b>${esc(benchLine(benchKey(cfg)))}</b>`;
  p.appendChild(bl);
  $("#setupChip").textContent = setupLabel(cfg); $("#setupChip").style.setProperty("--chip", famColor(cfg));
}
function renderCase() {
  const el = $("#casePanel"); el.innerHTML = "";
  const head = document.createElement("div"); head.className = "row gap";
  head.innerHTML = `<span class="case-name" id="caseName">Bug #${cfg.seed}</span><span class="grow"></span>`;
  const seed = document.createElement("div"); seed.className = "seedrow";
  seed.innerHTML = `<button type="button" title="previous bug">◀</button><input type="number" min="0" value="${cfg.seed}" style="width:90px"><button type="button" title="next bug">▶</button><button type="button">random</button>`;
  const [prev, inp, next, rnd] = seed.children;
  prev.onclick = () => setCfg({ seed: Math.max(0, cfg.seed - 1) }, { case: true, preview: true });
  next.onclick = () => setCfg({ seed: cfg.seed + 1 }, { case: true, preview: true });
  rnd.onclick = () => setCfg({ seed: Math.floor(Math.random() * 1000) }, { case: true, preview: true });
  inp.onchange = () => setCfg({ seed: Number(inp.value) }, { case: true, preview: true });
  head.appendChild(seed);
  const presets = document.createElement("div"); presets.className = "presets";
  for (const [k, p] of Object.entries(SCHEMA.presets)) {
    const b = document.createElement("button"); b.type = "button"; b.textContent = p.label;
    b.onclick = () => { const o = { ...SCHEMA.defaults, seed: cfg.seed, ...p.overrides }; cfg = o; setCfg({}, { case: true, preview: true }); };
    presets.appendChild(b);
  }
  const pct = (x) => `${Math.round(x * 100)}%`;
  el.append(head,
    grid(selectCtl("failure_info", "What the investigators are told", { final: "only the final wrong values", first: "the first wrong instruction" }, { preview: true }),
      selectCtl("test_pick", "Which failing test", { longest: "the longest", shortest: "the shortest" }, { preview: true }),
      slider("window", "Cycles per check", { min: 1, max: 8, step: 1 }),
      slider("deadline_hours", "Time limit", { min: 1, max: 12, step: 0.5, fmt: (x) => `${x} h (${Math.round(x * 4)} ticks)` })),
    grid(slider("noise", "Glitched readings", { min: 0, max: 0.2, step: 0.01, fmt: pct }),
      slider("rare_frac", "Rare-trigger bugs", { min: 0, max: 1, step: 0.1, fmt: pct }),
      slider("double_frac", "Two-bug cases", { min: 0, max: 1, step: 0.1, fmt: pct }),
      slider("liar_frac", "Bribed boys / lying Irregulars", { min: 0, max: 0.4, step: 0.05, fmt: pct }),
      toggle("liar_defence", "Liar defence", "two sources per mismatch; outvoted sources lose trust"),
      slider("budget_usd", "Model spend cap per case", { min: 0, max: 2, step: 0.05, fmt: (x) => `$${Number(x).toFixed(2)}` })));
  const ph = document.createElement("div"); ph.innerHTML = `<h4 class="sub-h">Presets</h4>`; ph.appendChild(presets);
  el.appendChild(ph);
}
function renderForm() {
  const f = $("#cfgForm"); f.innerHTML = "";
  for (const [group, fields] of SCHEMA.schema) {
    const d = document.createElement("details"); d.innerHTML = `<summary>${esc(group)}</summary>`;
    for (const [key, label, kind, extra] of fields) {
      const row = document.createElement("div"); row.className = "field";
      let input;
      if (kind === "choice") input = `<select>${Object.entries(extra).map(([k, v]) => `<option value="${esc(k)}" ${String(cfg[key]) === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>`;
      else if (kind === "bool") input = `<input type="checkbox" ${cfg[key] ? "checked" : ""}>`;
      else if (kind === "text") input = `<input type="text" value="${esc(cfg[key])}">`;
      else input = `<input type="number" value="${cfg[key]}" step="${kind === "float" ? "any" : 1}">`;
      row.innerHTML = `<label>${esc(label)}</label>${input}`;
      const el = row.querySelector("select,input");
      el.onchange = () => {
        const val = kind === "bool" ? el.checked : kind === "int" || kind === "float" ? Number(el.value) : el.value;
        setCfg({ [key]: val }, { form: false, case: true, preview: ["seed", "bug_type", "failure_info", "test_pick", "rare_frac", "double_frac", "window"].includes(key) });
      };
      d.appendChild(row);
    }
    f.appendChild(d);
  }
}
function renderKeys() { $("#keyStatus").innerHTML = SCHEMA.key_files.map((k) => `<div class="mono">${k.exists ? "✓" : "·"} ${esc(k.path)}</div>`).join(""); }
function renderRuns() {
  const r = SCHEMA.runs || [];
  $("#runsList").innerHTML = r.length ? r.map((x) => `<div>${esc(x.name.slice(9, 15))} ${esc(x.setting || x.mode)} #${x.seed} <span class="${x.fix_ok ? "ok" : "no"}">${x.fix_ok ? "fixed" : "not fixed"}</span> · $${(x.cost || 0).toFixed(3)}</div>`).join("") : "<span class='muted'>none yet</span>";
}
function estimate() {
  const c = cfg, b = (SCHEMA.bench || {})[benchKey(c)], L = [];
  const usesChat = (c.mode === "solo" && c.solo_policy === "chat") || (c.mode === "leader" && c.holmes === "chat");
  const usesJev = (c.mode === "solo" && c.solo_policy === "jev") || (c.mode === "leader" && c.boy_policy === "jev") || (c.mode === "swarm" && ["jev", "hybrid"].includes(c.swarm_policy));
  L.push(`<p><b>${esc(setupLabel(c))}</b>, ${c.deadline_hours} case hours.</p>`);
  if (b) {
    const cost = b.cost === "free" ? "free" : b.cost;
    L.push(`<p>On the hardened benchmark this setup solved <b>${b.solved} of ${b.n}</b> cases (${Math.round(100 * b.solved / b.n)}%). Cost: <b>${esc(cost)}</b>${b.wall ? `; a headless case takes about ${b.wall}` : ""}.</p>`);
  } else L.push(`<p class="muted">This exact setup has not been benchmarked.</p>`);
  L.push(`<p class="muted">Model calls: ${usesChat ? "gpt-6-astra" : ""}${usesChat && usesJev ? " + " : ""}${usesJev ? "Jev" : ""}${!usesChat && !usesJev ? "none (free)" : ""}. Spend is capped at $${Number(c.budget_usd).toFixed(2)} per case.</p>`);
  const missing = SCHEMA.key_files.filter((k) => !k.exists).length === SCHEMA.key_files.length;
  if ((usesChat || usesJev) && missing) L.push(`<p class="err">No key file found; model calls will fall back to the rule.</p>`);
  $("#estimate").innerHTML = L.join("");
}
let pvTimer = null;
function preview() {
  clearTimeout(pvTimer);
  pvTimer = setTimeout(async () => {
    const q = new URLSearchParams({ seed: cfg.seed, bug_type: cfg.bug_type, window: cfg.window, failure_info: cfg.failure_info,
      test_pick: cfg.test_pick, rare_frac: cfg.rare_frac, double_frac: cfg.double_frac, noise: cfg.noise });
    PREV = await api("/api/preview?" + q);
    $("#pvTitle").textContent = `Bug #${cfg.seed}: ${PREV.brief.test}`;
    if ($("#caseName")) $("#caseName").textContent = `Bug #${cfg.seed}: ${PREV.brief.test} (${PREV.n} cycles)`;
    $("#pvInfo").textContent = `${PREV.n} cycles`;
    $("#pvFail").textContent = PREV.brief.failure;
    $("#pvTests").innerHTML = PREV.results.map((r) => `<span class="${r.ok ? "good" : "bad"}" title="${esc(r.desc)}">${r.ok ? "✓" : "✗"} ${esc(r.name)}</span>`).join("");
    const k = PREV.check;
    $("#pvChecks").innerHTML = [
      [k.reachable, k.reachable ? "Solvable from this test: the failure's back-trace reaches every broken block" : "This test's back-trace misses a broken block; another failing test shows it"],
      [true, `${k.failing} of 9 tests fail; this one runs ${k.cycles} cycles`],
      ["info", `Back-trace: ${k.slice_nodes.toLocaleString()} block-cycles over ${k.slice_blocks} of the ${k.suspect_blocks} logic blocks`],
      ["info", cfg.failure_info === "final" ? "Investigators see only the final wrong values" : "Investigators see the first wrong instruction"],
    ].map(([ok, t]) => `<li class="${ok === "info" ? "info" : ok ? "" : "bad"}">${esc(t)}</li>`).join("");
    $("#pvSrc").textContent = PREV.brief.program.join("\n");
    drawPreview();
  }, 140);
}
function drawPreview() {
  if (!PREV || $("#launch").hidden) return;
  const c = $("#preview"), { g, w, h } = fitCanvas(c);
  const L = layout(PREV.blocks), s = Math.min(w / VW, h / VH), ox = (w - VW * s) / 2, oy = (h - VH * s) / 2;
  g.fillStyle = css("--board"); g.fillRect(0, 0, w, h);
  const mx = Math.max(1, ...Object.values(PREV.slice)), starts = new Set(PREV.starts.map((x) => x[0]));
  for (const p of Object.values(L.pos)) {
    const x = ox + p.x * s, y = oy + p.y * s, bw = p.w * s, bh = p.h * s;
    rr(g, x, y, bw, bh, 2); g.fillStyle = p.b.trusted ? css("--pipe") : css("--logic"); g.fill();
    const n = PREV.slice[p.b.name] || 0;
    if (n) { rr(g, x, y, bw, bh, 2); g.fillStyle = alpha(css("--front"), 0.12 + 0.6 * Math.sqrt(n / mx)); g.fill(); }
    g.strokeStyle = starts.has(p.b.name) ? css("--bad") : css("--line2"); g.lineWidth = starts.has(p.b.name) ? 2 : 0.8; g.stroke();
  }
}
async function testModel(which) { const o = $("#testOut"); o.hidden = false; o.textContent = "checking…"; o.textContent = JSON.stringify(await api("/api/test", { which, cfg }), null, 1); }
async function launch() {
  $("#launchErr").textContent = "";
  const r = await api("/api/launch", { cfg });
  if (!r.ok) { $("#launchErr").textContent = r.error || "launch failed"; return; }
  startDash();
}
$("#launchBtn").onclick = launch;
$("#rejoinBtn").onclick = startDash;
$("#testJev").onclick = () => testModel("jev");
$("#testChat").onclick = () => testModel("chat");

/* ---------------------------------------------------------------------------------------------- dashboard */
async function startDash() {
  ST = await api("/api/static");
  if (ST.error) return;
  prepare(ST.blocks, ST.edges); BASES.clear();
  F = null; SECRET = null; SEL = null; lastProbeN = 0; FLASH.length = 0; RIPPLE.length = 0; RUN0.clear(); WIG0 = null;
  AG.prev = new Map(); AG.cur = new Map(); AG.last = 0; CAM.z = 1; CAM.cx = VW / 2; CAM.cy = VH / 2; CAM.to = null;
  $("#launch").hidden = true; $("#dash").hidden = false; $("#endBanner").hidden = true; $("#showResult").hidden = true; $("#stamp").hidden = true;
  delete $("#endBanner").dataset.shown;
  $("#tTruth").checked = false; $("#captions").innerHTML = "";
  document.querySelectorAll(".fam-solo").forEach((e) => (e.hidden = ST.mode !== "solo"));
  document.querySelectorAll(".fam-leader").forEach((e) => (e.hidden = ST.mode !== "leader"));
  document.querySelectorAll(".fam-swarm").forEach((e) => (e.hidden = ST.mode !== "swarm"));
  $("#modeTag").textContent = setupLabel(ST.cfg); $("#modeTag").style.setProperty("--chip", famColor(ST.cfg));
  $("#caseTitle").innerHTML = `Bug #${ST.cfg.seed}: ${esc(ST.brief.test)} <span class="meta">${esc(ST.brief.failure)}</span>`;
  $("#speed").value = Math.log10(ST.cfg.speed); $("#speedVal").textContent = `${ST.cfg.speed.toFixed(1)}/s`;
  $("#selTitle").textContent = "Selection"; $("#selMeta").textContent = "click a block or an agent on the schematic"; $("#selBody").innerHTML = "";
  renderBrief(); renderLegend(); fillGuess();
  titleCard();
  if (es) es.close();
  if (new URLSearchParams(location.search).has("still")) {   // one frame, no stream (for screenshots)
    $("#titleCard").hidden = true;
    const f = await api("/api/frame"); onFrame(f); onFrame(f);
    return;
  }
  es = new EventSource("/api/stream");
  es.onmessage = (e) => onFrame(JSON.parse(e.data));
}
function titleCard() {
  const t = $("#titleCard");
  t.innerHTML = `<div class="tc-kicker">Bug #${ST.cfg.seed} · ${esc(ST.brief.test)} · ${esc(setupLabel(ST.cfg))}</div>
    <div class="tc-title">${esc(ST.brief.failure.replace(/^[a-z_]+ fails: /, ""))}</div>
    <div class="tc-sub">${esc(ST.brief.failing_tests.length)} of 9 tests fail. Find the broken block, the signal, the bug type and the fix within ${ST.cfg.deadline_hours} hours of bench time.</div>`;
  t.hidden = false; t.classList.remove("out");
  setTimeout(() => t.classList.add("out"), REDUCED.matches ? 1500 : 3200);
  setTimeout(() => (t.hidden = true), REDUCED.matches ? 1600 : 4100);
}
function onFrame(f) {
  const first = !F;
  F = f;
  if (f.secret) SECRET = { ...f.secret, liars: f.liars || [] };
  retarget(f);
  if (f.probe_log && f.probes > lastProbeN) {
    const fresh = Math.min(f.probes - lastProbeN, 30);
    if (!first) f.probe_log.slice(-fresh).forEach((p) => FLASH.push({ block: p.block, bad: p.mismatch, t0: performance.now() }));
    lastProbeN = f.probes;
  }
  if (f.mode === "swarm" && f.shares) f.shares.slice(0, 25).forEach((b) => RIPPLE.push({ block: b, t0: performance.now() }));
  const hrs = (f.tick * f.tick_min) / 60, clock = 9 * 60 + f.tick * f.tick_min;
  $("#clock").textContent = `${String(Math.floor(clock / 60) % 24).padStart(2, "0")}:${String(Math.round(clock % 60)).padStart(2, "0")}`;
  $("#progFill").style.width = `${Math.min(100, (100 * f.tick) / f.deadline)}%`;
  $("#progText").textContent = `${hrs.toFixed(1)} / ${((f.deadline * f.tick_min) / 60).toFixed(0)} h`;
  const live = $("#liveDot"); live.className = "live " + (f.ended ? "closed" : f.paused ? "paused" : "on"); live.textContent = f.ended ? "Closed" : f.paused ? "Paused" : "Live";
  $("#playBtn").innerHTML = f.paused ? `<span aria-hidden="true">▶</span> <span class="lbl">Resume</span>` : `<span aria-hidden="true">❚❚</span> <span class="lbl">Pause</span>`;
  if (f.mode === "solo") renderSolo(f); else if (f.mode === "leader") renderLeader(f); else renderSwarm(f);
  renderEvents(f); renderUsage(f); renderGuesses(f); captions(f); drawWave();
  if (SEL && SEL.kind === "agent" && Math.random() < 0.3) select("agent", SEL.id);
  if (f.ended) endBanner(f);
}

/* ---------------------------------------------------------------------------------------------- side panels */
function beliefRows(list, max) {
  return list.map((b) => `<div class="brow${truthOn() && SECRET.bugs.some((x) => x.block === b.block) ? " truth" : ""}" data-b="${esc(b.block)}">
    <span class="nm">${esc(b.block)}</span><div class="bar2"><div style="width:${Math.round(100 * Math.min(1, b.score / max))}%;--series:var(${b.confirmed ? "--bad" : "--warn"})"></div></div>
    <span class="pc">${esc(b.note)}</span></div>`).join("");
}
function bindRows(el) { el.querySelectorAll("[data-b]").forEach((d) => (d.onclick = () => select("block", d.dataset.b))); }
let NB_N = 0;
function renderSolo(f) {
  $("#soloMeta").textContent = `${f.probes_used}/${f.probe_budget} probes`;
  const rows = (f.belief || []).map((b) => ({ block: b.block, score: b.bad + (b.confirmed ? 2 : 0), confirmed: b.confirmed, note: b.confirmed ? "confirmed" : `${b.bad} bad` }));
  $("#belief").innerHTML = rows.length ? `<div class="bgroup"><h4>Suspects</h4>${beliefRows(rows, 4)}</div>` : `<p class="muted small">No block has misbehaved yet.</p>`;
  bindRows($("#belief"));
  const ans = f.answer ? f.answer.fixes.map((x) => `<b class="mono">${esc(x.block)}.${esc(x.port)}</b>: ${esc(x.desc)}`).join("<br>") : null;
  $("#soloNote").innerHTML = `${f.cleared_n} block${f.cleared_n === 1 ? "" : "s"} cleared. ` + (ans ? `<br>Accused: ${ans}` :
    `Now: ${esc(f.thought || "thinking")}` + (f.next && f.next.length ? `<br>Next on the back-trace: <span class="mono">${esc(f.next.join(", "))}</span>` : ""));
  const tr = f.trail || [];
  $("#nbMeta").textContent = `${tr.length} probe${tr.length === 1 ? "" : "s"}`;
  $("#notebook").innerHTML = tr.slice().reverse().map((t, i) => `<div class="nb ${t.type === "read" ? "read" : t.mismatch ? "bad" : "good"}${i === 0 && tr.length > NB_N ? " fresh" : ""}" data-b="${esc(t.block)}">
    <div class="addr">#${tr.length - i} · ${esc(t.block)} · ${esc(t.where)}</div><div>${t.type === "read" ? "waveform read" : t.mismatch ? "does NOT match its spec" : "matches its spec"}</div></div>`).join("") || `<p class="muted small">Nothing probed yet.</p>`;
  NB_N = tr.length; bindRows($("#notebook"));
}
function renderLeader(f) {
  const h = f.holmes || {};
  $("#hqMeta").textContent = `${h.kind === "chat" ? "gpt-6-astra" : "counting"} · ${h.calls || 0} model plan${h.calls === 1 ? "" : "s"} · ${f.queue} errand${f.queue === 1 ? "" : "s"} queued`;
  const ans = f.answer || h.answer_now;
  const ansTxt = ans && ans.fixes && ans.fixes.length ? ans.fixes.map((x) => `<b class="mono">${esc(x.block)}.${esc(x.port)}</b>: ${esc(x.desc)}`).join("<br>") : "<span class='muted'>no answer yet</span>";
  const openq = (h.open || []).map((o) => `<li><span class="mono">${esc(o.block)}</span> mismatched for boy ${esc(o.by.join(", "))}; needs another boy to confirm</li>`).join("");
  $("#hq").innerHTML = `<h4 class="sub-h">${f.answer ? "Holmes names" : "His answer so far"}</h4><div class="hq-answer">${ansTxt}</div>
    <h4 class="sub-h" style="margin-top:10px">Open questions</h4><ul class="hq-q">${openq || "<li class='muted'>none</li>"}
    ${h.next && h.next.length ? `<li>next on the back-trace: <span class="mono">${esc(h.next.slice(0, 4).join(", "))}</span></li>` : ""}</ul>
    ${h.distrusted && h.distrusted.length ? `<p class="small err" style="margin:8px 0 0">No longer believes boy${h.distrusted.length > 1 ? "s" : ""} ${esc(h.distrusted.join(", "))}.</p>` : ""}`;
  const reps = (f.reports || []).slice().reverse();
  $("#repMeta").textContent = f.wiggins ? `Wiggins' bag: ${f.bag}` : "boys report in person";
  $("#reports").innerHTML = reps.map((r) => `<div data-b="${esc(r.block)}"><span class="t">t${r.tick}</span><span>boy #${r.boy}: <span class="mono">${esc(r.block)}</span> ${r.bad ? "<span class='no'>does NOT match</span>" : "matches its spec"}</span></div>`).join("") || "<p class='muted small'>No report has reached Baker Street yet.</p>";
  bindRows($("#reports"));
  renderRoster();
}
function renderRoster() {
  if (!F || F.mode !== "leader") return;
  const liars = truthOn() ? (F.liars || SECRET.liars || []) : [];
  $("#roster").innerHTML = F.agents.map((a) => `<div class="boy${SEL && SEL.kind === "agent" && SEL.id === a.id ? " sel" : ""}" data-id="${a.id}">
    <b>#${a.id}</b>${liars.includes(a.id) ? " <span class='no'>bribed</span>" : ""}<span class="st">${esc(a.status)}${a.items && a.items.length ? ": " + esc(a.items.join(", ")) : ""}</span></div>`).join("");
  $("#roster").querySelectorAll("[data-id]").forEach((d) => (d.onclick = () => select("agent", Number(d.dataset.id))));
}
function renderSwarm(f) {
  const need = Math.ceil(f.quorum_need), voting = f.agents.filter((a) => a.vote).length;
  $("#voteMeta").textContent = `${voting} of ${f.agents.length} voting · quorum ${need}`;
  const rows = (f.tally || []).map(([lab, k], i) => `<div class="trow" data-b="${esc(lab.split("|")[0])}"><div class="top"><span><i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:var(${VOTEC[i] || "--muted"})"></i>
    <span class="mono">${esc(lab.replace("|", " / "))}</span></span><b>${k}</b></div>
    <div class="qbar"><div style="width:${Math.min(100, (100 * k) / Math.max(need, 1) * 0.8)}%;background:var(${VOTEC[i] || "--muted"})"></div><i style="left:80%"></i></div>
    ${f.labels && f.labels[lab] ? `<div class="meta">${esc(f.labels[lab])}</div>` : ""}</div>`).join("");
  $("#tally").innerHTML = rows || "<p class='muted small'>Nobody votes yet: an Irregular votes only for a bug it has reproduced itself (or that three trusted sources measured).</p>";
  bindRows($("#tally"));
  drawSeries();
}
function drawSeries() {
  if (!F || F.mode !== "swarm") return;
  const c = $("#series"), { g, w, h } = fitCanvas(c), s = F.series || [], need = F.quorum_need, T = F.deadline;
  g.clearRect(0, 0, w, h);
  const X = (t) => 30 + (w - 40) * (t / T), Y = (k) => h - 18 - (h - 30) * Math.min(1, k / Math.max(need * 1.25, 1));
  g.strokeStyle = css("--line"); g.lineWidth = 1; g.beginPath(); g.moveTo(30, h - 18); g.lineTo(w - 10, h - 18); g.stroke();
  g.strokeStyle = css("--ink"); g.setLineDash([4, 3]); g.beginPath(); g.moveTo(30, Y(need)); g.lineTo(w - 10, Y(need)); g.stroke(); g.setLineDash([]);
  g.fillStyle = css("--muted"); g.font = `10px ${css("--f-ui")}`; g.textAlign = "left"; g.fillText(`quorum ${Math.ceil(need)}`, 32, Y(need) - 4);
  const line = (idx, col) => { g.strokeStyle = col; g.lineWidth = 2; g.beginPath(); s.forEach((p, i) => { const x = X(p[0]), y = Y(p[idx]); i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke(); };
  if (s.length) { line(3, alpha(css("--irr"), 0.6)); line(1, css("--v1")); }
  g.fillStyle = css("--muted"); g.textAlign = "left"; g.fillText("top vote", 32, 12); g.fillStyle = css("--irr"); g.fillText("· all voting", 84, 12);
  g.textAlign = "right"; g.fillStyle = css("--muted"); g.fillText(`tick ${T}`, w - 10, h - 4);
}
function renderLegend() {
  const sw = (fill, stroke, dash) => `<svg width="18" height="12"><rect x="1" y="1" width="16" height="10" rx="2" fill="${fill}" stroke="${stroke}" ${dash ? 'stroke-dasharray="3 2"' : ""}/></svg>`;
  const dot = (c, r = 5, ring) => `<svg width="14" height="14"><circle cx="7" cy="7" r="${r}" fill="${c}" ${ring ? `stroke="${ring}" stroke-width="2"` : ""}/></svg>`;
  const blocks = [[sw(css("--logic"), css("--line2")), "logic block (where bugs live)"], [sw(css("--pipe"), css("--line2")), "register / memory (verified)"],
    [sw(alpha(css("--good"), 0.35), css("--line2")), "cleared: matches its spec"], [sw(alpha(css("--warn"), 0.4), css("--line2")), "mismatched once (glitch or bug?)"],
    [sw(alpha(css("--bad"), 0.6), css("--line2")), "confirmed: wrong value repeated"], [sw("none", css("--front"), true), "next on the back-trace"],
    [dot(css("--bad"), 4), "where the wrong final values sit"]];
  let agents;
  if (ST.mode === "solo") agents = [[dot(css("--solo"), 6), "the debugger"], [`<svg width="30" height="12"><line x1="1" y1="6" x2="29" y2="6" stroke="${css("--solo")}" stroke-width="2" stroke-dasharray="5 3"/></svg>`, "its probe path, numbered (red: mismatch)"]];
  else if (ST.mode === "leader") agents = [[dot(css("--holmes"), 6), "Holmes at 221B"], [dot(css("--wiggins"), 6), "Wiggins and his post"], [dot(css("--boy"), 6), "a boy (dashed: blocks left on his errand)"],
    [`<svg width="14" height="12"><rect x="2" y="2" width="10" height="7" fill="none" stroke="${css("--boy")}"/></svg>`, "running back with a report"]];
  else agents = [[dot(css("--irr"), 3), "an Irregular (unsure)"], [dot(css("--v1"), 3.5), "voting the leading answer"], [dot(css("--v2"), 3.5), "voting another answer"],
    [`<svg width="18" height="14"><circle cx="9" cy="7" r="6" fill="none" stroke="${css("--info")}"/></svg>`, "a radio share (range)"]];
  const spoil = [[`<svg width="18" height="12"><rect x="1" y="1" width="16" height="10" rx="2" fill="none" stroke="${css("--bad")}" stroke-dasharray="3 2" stroke-width="2"/></svg>`, "the bug (Reveal)"],
    [dot("none", 5, css("--liar")), "a liar (Reveal)"], [sw("none", css("--accent")), "the investigators' answer"]];
  const grp = (t, items) => `<div class="lg-group"><b>${t}</b>${items.map(([i, l]) => `<span class="lg">${i}${esc(l)}</span>`).join("")}</div>`;
  $("#legend").innerHTML = grp("Blocks", blocks) + grp(ST.mode === "solo" ? "The debugger" : ST.mode === "leader" ? "Baker Street" : "The swarm", agents) + grp("Answers and spoilers", spoil);
}
function renderBrief() {
  const b = ST.brief;
  $("#brief").innerHTML = `<p>${esc(b.failure)}</p>
    <h4>Tests</h4><div class="tests">${ST.results.map((r) => `<span class="${r.ok ? "good" : "bad"}">${r.ok ? "✓" : "✗"} ${esc(r.name)}</span>`).join("")}</div>
    <h4>Back-trace start points</h4><div class="mono small">${esc(b.start_points.join(", "))}</div>
    <h4>The program (${esc(b.test)})</h4><pre class="src">${esc(b.program.join("\n"))}</pre>`;
}
function fillGuess() {
  $("#gBlock").innerHTML = ST.blocks.filter((b) => !b.trusted).map((b) => `<option value="${esc(b.name)}">${esc(b.name)}</option>`).join("");
  $("#gGo").onclick = () => api("/api/guess", { block: $("#gBlock").value });
}
function renderGuesses(f) {
  if (!f.guesses.length) { $("#guesses").innerHTML = "<span class='muted'>Name the block you think is broken; you will see at the end whether you beat the investigators.</span>"; return; }
  $("#guesses").innerHTML = f.guesses.map((g) => `<div>You suspected <b class="mono">${esc(g.block)}</b> at tick ${g.tick}` +
    (f.ended && f.secret ? (f.secret.bugs.some((x) => x.block === g.block) ? " <span class='ok'>right</span>" : " <span class='no'>wrong</span>") : "") + "</div>").join("");
}
function renderUsage(f) {
  const c = (l, v, t) => `<div class="mc" title="${esc(t || "")}"><b>${v}</b><span>${l}</span></div>`;
  $("#infCards").innerHTML = c("model calls", f.calls) + c("spend", `$${f.cost.toFixed(4)}`, `cap $${f.budget_usd}`) + c("probes", f.probes) +
    c("fell back", f.fallbacks, "calls that failed or timed out and used the rule") + c("ticks", `${f.tick}/${f.deadline}`) + c("seconds", f.elapsed.toFixed(0));
  $("#errors").textContent = (f.errors || []).slice(-1).join(" ");
}
function renderEvents(f) {
  const el = $("#events"), atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 8;
  el.innerHTML = f.events.slice(-80).map((e) => `<div class="${esc(e.kind)}${e.mismatch ? " bad" : ""}"><span class="t">t${e.tick}</span><span>${esc(e.text)}</span></div>`).join("");
  if (atBottom) el.scrollTop = el.scrollHeight;
}
const SEEN = new Set();
function captions(f) {
  const box = $("#captions");
  for (const e of f.events.slice(-12)) {
    const key = `${e.t}|${e.text}`;
    if (SEEN.has(key)) continue;
    SEEN.add(key);
    let cls = null, title = null;
    if (e.kind === "accuse") { cls = "big"; title = "The accusation"; }
    else if (e.kind === "quorum") { cls = "big"; title = "Quorum"; }
    else if (e.kind === "cold") { cls = "bad"; title = "Time is up"; }
    else if (e.kind === "holmes") { cls = "note"; title = "Holmes"; }
    else if (e.kind === "genius") { cls = "note"; title = "The genius"; }
    else if (e.kind === "wiggins") { cls = "note"; title = "Wiggins"; }
    else if ((e.kind === "probe" || e.kind === "report") && e.mismatch !== false && /NOT|MISMATCH/.test(e.text)) { cls = "bad"; title = "Mismatch"; }
    if (!cls || f.ended && e.kind !== "end") continue;
    const d = document.createElement("div"); d.className = `cap ${cls}`; d.innerHTML = `<b>${esc(title)}</b>${esc(e.text.slice(0, 220))}`;
    box.appendChild(d);
    while (box.children.length > 2) box.firstChild.remove();
    setTimeout(() => d.classList.add("out"), 5200); setTimeout(() => d.remove(), 5800);
  }
}
function endBanner(f) {
  const b = $("#endBanner");
  if (b.dataset.shown) return;
  b.dataset.shown = "1";
  const r = f.result, s = f.secret, a = f.answer, sm = f.summary || {};
  const cls = r.fix_ok ? "solved" : r.block_ok ? "partly" : "wrong";
  const verdict = r.fix_ok ? "Fixed: every test passes" : sm.wrong_quorum ? "Wrong quorum: the swarm agreed on a wrong answer" : !a ? (f.mode === "swarm" ? "No quorum: the swarm gave no answer" : "No answer") : r.block_ok ? "Right block, wrong fix" : "Wrong block";
  const st = $("#stamp"); st.className = `stamp ${cls}`; st.textContent = r.fix_ok ? "Fixed" : sm.wrong_quorum ? "Framed" : r.block_ok ? "Close" : "Not fixed"; st.hidden = false;
  const mk = (ok) => ok ? "<span class='ok'>✓ right</span>" : "<span class='no'>✗ wrong</span>";
  const named = a ? a.fixes.map((x) => `<span class="mono">${esc(x.block)}.${esc(x.port)}</span> ${esc(x.desc)}`).join("; ") : "-";
  const truth = s.bugs.map((x) => `<span class="mono">${esc(x.block)}.${esc(x.port)}</span> ${esc(x.desc)}${x.rare ? " (rare trigger)" : ""}`).join("; ");
  b.className = `end ${cls}`;
  b.innerHTML = `<div class="badge" aria-hidden="true">${r.fix_ok ? "✓" : r.block_ok ? "◐" : "✗"}</div>
    <div class="verdict">${verdict}</div>
    <div class="small muted">${sm.sim_hours !== undefined ? `After ${sm.sim_hours} case hours, ` : ""}${f.probes} probes, $${f.cost.toFixed(4)}.${f.liars && f.liars.length ? ` Liars: #${f.liars.join(", #")}.` : ""}</div>
    <div class="parts"><span>Named</span><span>${named}</span><span>The bug</span><span>${truth}</span>
      <span>Block</span><span>${mk(r.block_ok)}</span><span>Signal / type</span><span>${mk(r.location_ok)} / ${mk(r.type_ok)}</span>
      <span>Fix</span><span>${mk(r.fix_ok)} <span class="meta">${r.tests_passed ?? "-"}/${r.tests_total} tests pass</span></span></div>
    <div class="actions"><button id="hideEnd" class="ghost">Close</button><button id="againBtn" class="primary">New case</button></div>`;
  b.hidden = false;
  $("#hideEnd").onclick = () => { b.hidden = true; $("#showResult").hidden = false; };
  $("#againBtn").onclick = goLaunch;
  $("#tTruth").checked = true;
}

/* ---------------------------------------------------------------------------------------------- timeline */
function drawWave() {
  if (!ST || $("#dash").hidden) return;
  const c = $("#wave"), { g, w, h } = fitCanvas(c);
  g.fillStyle = css("--board"); g.fillRect(0, 0, w, h);
  const n = ST.n, left = 46, top = 16, rows = ["IF", "ID", "EX", "MEM", "WB"], rh = (h - top - 40) / rows.length, cw = (w - left - 6) / n;
  const log = (F && F.probe_log) || [];
  log.forEach((p, i) => {
    if (p.type !== "check" || !p.window) return;
    const x = left + p.window[0] * cw, ww = (p.window[1] - p.window[0] + 1) * cw, recent = i >= log.length - 4;
    g.fillStyle = alpha(p.mismatch ? css("--bad") : css("--info"), recent ? 0.22 : 0.06); g.fillRect(x, top, ww, rh * rows.length);
    g.fillStyle = alpha(p.mismatch ? css("--bad") : css("--info"), 0.85); g.fillRect(x, h - 34 + (i % 4) * 5, Math.max(1.5, ww), 3);
  });
  g.font = `10px ${css("--f-mono")}`; g.textBaseline = "middle";
  rows.forEach((r, k) => { g.fillStyle = css("--muted"); g.textAlign = "left"; g.fillText(r, 8, top + k * rh + rh / 2); });
  g.textAlign = "center";
  for (let cy = 0; cy < n; cy++) {
    const occ = ST.occupancy[cy];
    for (let k = 0; k < 5; k++) {
      const x = left + cy * cw, y = top + k * rh;
      g.strokeStyle = css("--wire"); g.lineWidth = 0.5; g.strokeRect(x, y, cw, rh);
      if (occ[k] !== null && cw >= 9) { g.fillStyle = css("--board-ink"); g.fillText(String(occ[k]), x + cw / 2, y + rh / 2); }
    }
    if (cy % 10 === 0) { g.fillStyle = css("--faint"); g.fillText(String(cy), left + cy * cw + cw / 2, 7); }
  }
  for (const [b, cy] of ST.starts) { const x = left + cy * cw + cw / 2; g.fillStyle = css("--bad"); g.beginPath(); g.arc(x, top + rh * 4.5, 3, 0, 7); g.fill(); }
  ((F && F.frontier) || []).forEach(([b, cy]) => { const x = left + cy * cw + cw / 2; g.fillStyle = css("--front"); g.beginPath(); g.moveTo(x - 4, h - 40); g.lineTo(x + 4, h - 40); g.lineTo(x, h - 35); g.fill(); });
  g.textBaseline = "alphabetic";
  $("#wvInfo").textContent = `${n} cycles · bands: checked windows (red: a mismatch) · ▾ next on the back-trace · red dot: wrong final value`;
  c.onmousemove = (e) => {
    const r = c.getBoundingClientRect(), cy = Math.floor((e.clientX - r.left - left) / cw);
    if (cy < 0 || cy >= n) return;
    const occ = ST.occupancy[cy];
    $("#wvHover").textContent = `cycle ${cy}: ` + rows.map((s, k) => `${s} ${occ[k] === null ? "-" : (ST.brief.program[occ[k]] || `${occ[k]}: NOP`).replace(/^\s*\d+: /, `${occ[k]} `)}`).join(" | ");
  };
}

/* ---------------------------------------------------------------------------------------------- controls */
$("#playBtn").onclick = () => api("/api/cmd", { action: F && F.paused ? "resume" : "pause" });
$("#stepBtn").onclick = () => api("/api/cmd", { action: "step" });
$("#speed").oninput = (e) => { const s = Math.pow(10, Number(e.target.value)); $("#speedVal").textContent = `${s.toFixed(1)}/s`; api("/api/cmd", { action: "set", cfg: { speed: s } }); };
$("#tTruth").onchange = async () => {
  if ($("#tTruth").checked && !SECRET) { const s = await api("/api/secret"); if (!s.error) SECRET = { ...s, liars: s.liars || [] }; }
  if (F && F.mode === "leader") renderRoster();
};
$("#newRun").onclick = goLaunch;
$("#showResult").onclick = () => { $("#endBanner").hidden = false; $("#showResult").hidden = true; };
$("#presentBtn").onclick = () => { document.body.classList.toggle("present"); BASES.clear(); };
document.addEventListener("keydown", (e) => {
  if ($("#dash").hidden || ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
  if (e.key === " ") { e.preventDefault(); $("#playBtn").click(); }
  else if (e.key === "ArrowRight") $("#stepBtn").click();
  else if (e.key === "r" || e.key === "R") { $("#tTruth").checked = !$("#tTruth").checked; $("#tTruth").onchange(); }
  else if (e.key === "p" || e.key === "P") $("#presentBtn").click();
});
function goLaunch() {
  if (es) es.close();
  $("#dash").hidden = true; $("#launch").hidden = false; $("#endBanner").hidden = true;
  document.body.classList.remove("present");
  initLaunch();
}
window.addEventListener("resize", () => { BASES.clear(); drawPreview(); drawWave(); drawSeries(); });
setupMap();
function loop(now) { drawMap(now); requestAnimationFrame(loop); }
requestAnimationFrame(loop);
// ?watch opens the running (or last) case straight away; ?theme=dark|light forces a theme
const QS = new URLSearchParams(location.search);
if (QS.get("theme")) { document.documentElement.dataset.theme = QS.get("theme"); themeLabels(); }
if (QS.has("watch")) initLaunch().then(startDash); else initLaunch();

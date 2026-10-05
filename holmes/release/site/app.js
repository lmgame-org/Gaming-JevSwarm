/* The Irregulars: replay the real benchmark runs of one case, three ways, on one shared clock (case minutes). */
const $ = (s, el = document) => el.querySelector(s);
const ANS = ["#d9a52e", "#4f8fd1", "#a26ad1", "#4f9a5e"], OTHER = "#8a7f6a", RED = "#a3171d", INK = "#2a1d12";
const PART = {culprit: "culprit", motive: "motive", hideout: "hideout"};
let INDEX = [], kind = "standard", filter = "all", C = null, minute = 0, playing = false, last = 0;

const hm = (m) => `${Math.floor(m / 60)}h ${String(Math.floor(m % 60)).padStart(2, "0")}m`;
const secs = (s) => s == null ? "?" : s < 60 ? `${Math.round(s)} s` : `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, "0")} s`;
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[c]));

async function init() {
  INDEX = await (await fetch("data/index.json")).json();
  document.querySelectorAll(".kinds button").forEach((b) => b.onclick = () => { kind = b.dataset.kind;
    document.querySelectorAll(".kinds button").forEach((x) => x.setAttribute("aria-selected", String(x === b))); fillCases(); });
  document.querySelectorAll(".filters button").forEach((b) => b.onclick = () => { filter = b.dataset.f;
    document.querySelectorAll(".filters button").forEach((x) => x.classList.toggle("on", x === b)); fillCases(); });
  $("#caseSel").onchange = (e) => load(e.target.value);
  $("#time").oninput = (e) => { minute = +e.target.value; draw(); };
  $("#play").onclick = () => { playing = !playing; $("#play").innerHTML = playing ? "&#10074;&#10074;" : "&#9654;"; last = performance.now();
    if (playing && minute >= endMinute()) minute = 0; if (playing) requestAnimationFrame(tick); };
  fillCases("standard_57.json");
}

function fillCases(pick) {
  const rows = INDEX.filter((r) => r.kind === kind && (filter === "all" || (filter === "holmesOnly" && r.baker && !r.solo && !r.swarm) ||
    (filter === "swarmWrong" && r.swarm_agreed && !r.swarm)));
  const mark = (ok) => ok ? "✓" : "✗";
  $("#caseSel").innerHTML = rows.map((r) => `<option value="${r.file}">Case ${r.seed} · Lone ${mark(r.solo)} · Holmes ${mark(r.baker)} · Swarm ${mark(r.swarm)}</option>`).join("");
  const want = pick && rows.find((r) => r.file === pick) ? pick : rows.length ? rows[0].file : null;
  if (want) { $("#caseSel").value = want; load(want); }
}

async function load(file) {
  C = await (await fetch("data/" + file)).json();
  minute = 0; $("#time").value = 0; $("#time").max = Math.ceil(endMinute());
  $("#caseTitle").textContent = `Case ${C.seed} · ${C.kind === "frameup" ? "frame-up (somebody lies)" : "standard"} · ${C.brief.victim.split(",").slice(0, 2).join(",")}`;
  $("#truth").textContent = `Truth: ${C.truth.culprit} · ${C.truth.motive.split(":")[0]} · ${C.truth.hideout}`;
  buildLogs(); draw();
}

const endMinute = () => C ? Math.max(C.solo.minutes, C.baker.minute, C.swarm.minute) + 20 : 720;

function tick(now) {
  if (!playing) return;
  const sp = +$("#speed").value;
  minute = Math.min(endMinute(), minute + (now - last) / 1000 * sp); last = now;
  $("#time").value = minute; draw();
  if (minute >= endMinute()) { playing = false; $("#play").innerHTML = "&#9654;"; return; }
  requestAnimationFrame(tick);
}

/* ---------------------------------------------------------------- the map */
function mapper(cv) { const s = cv.width / 1000; return {s, P: ([x, y]) => [x * s, y * s]}; }
function baseMap(cv) {
  const g = cv.getContext("2d"), {s, P} = mapper(cv), M = C.map, idx = {};
  M.ids.forEach((id, i) => idx[id] = i);
  const A = (id) => P(M.addresses[idx[id]]);
  g.fillStyle = "#efe2c2"; g.fillRect(0, 0, cv.width, cv.height);
  g.lineCap = "round"; g.lineJoin = "round";
  g.beginPath(); M.thames.forEach((p, i) => { const [x, y] = P(p); i ? g.lineTo(x, y) : g.moveTo(x, y); });
  g.strokeStyle = "rgba(60,90,120,0.4)"; g.lineWidth = 24 * s; g.stroke(); g.strokeStyle = "#9cbad2"; g.lineWidth = 19 * s; g.stroke();
  g.beginPath(); for (const [a, b] of M.edges) { const [ax, ay] = A(a), [bx, by] = A(b); g.moveTo(ax, ay); g.lineTo(bx, by); }
  g.strokeStyle = "rgba(255,250,235,0.9)"; g.lineWidth = 3.5; g.stroke(); g.strokeStyle = "rgba(110,82,48,0.45)"; g.lineWidth = 1; g.stroke();
  g.fillStyle = "rgba(92,66,40,0.7)"; for (const a of M.addresses) { const [x, y] = P(a); g.beginPath(); g.arc(x, y, 2.2, 0, 7); g.fill(); }
  g.font = "600 11px Inter, sans-serif"; g.textAlign = "center"; g.fillStyle = "rgba(78,56,32,0.6)";
  for (const d of M.districts) { const [x, y] = P([d.x, d.y]); g.fillText(d.name.toUpperCase(), x, y - 38 * s); }
  const [bx, by] = A(M.baker); g.fillStyle = INK; g.font = "700 13px Inter"; g.fillText("★ 221B", bx, by - 10);
  const [cx, cy] = A(M.scene); g.strokeStyle = RED; g.lineWidth = 3.5;
  g.beginPath(); g.moveTo(cx - 7, cy - 7); g.lineTo(cx + 7, cy + 7); g.moveTo(cx + 7, cy - 7); g.lineTo(cx - 7, cy + 7); g.stroke();
  return {g, P, A, s};
}
function lerpTicks(ticks, m) {          // the two ticks around minute m, and how far between them
  let i = 0; while (i + 1 < ticks.length && ticks[i + 1].minute <= m) i++;
  const a = ticks[i], b = ticks[Math.min(ticks.length - 1, i + 1)];
  const k = b.minute > a.minute ? Math.max(0, Math.min(1, (m - a.minute) / (b.minute - a.minute))) : 0;
  return {i, a, b, k};
}

/* ---------------------------------------------------------------- the three panels */
function drawSolo() {
  const el = $("#p-solo"), cv = $("canvas", el), {g, A} = baseMap(cv), S = C.solo, st = S.stops, m = Math.min(minute, S.minutes);
  let i0 = 0; while (i0 + 1 < st.length && st[i0 + 1].minute <= m) i0++;
  const nx = st[Math.min(st.length - 1, i0 + 1)], k = nx.minute > st[i0].minute ? Math.min(1, (m - st[i0].minute) / (nx.minute - st[i0].minute)) : 0;
  g.strokeStyle = RED; g.lineWidth = 2.5; g.setLineDash([7, 5]); g.beginPath();
  st.slice(0, i0 + 1).forEach((s, i) => { const [x, y] = A(s.at); i ? g.lineTo(x, y) : g.moveTo(x, y); });
  const p = A(st[i0].at), q = A(nx.at), cab = [p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k];
  g.lineTo(...cab); g.stroke(); g.setLineDash([]);
  const found = {};
  st.slice(1, i0 + 1).forEach((s) => { const [x, y] = A(s.at); if (s.part) found[s.part] = (found[s.part] || 0) + 1;
    g.fillStyle = s.part ? RED : "rgba(163,23,29,0.25)"; g.beginPath(); g.arc(x, y, s.part ? 6 : 4, 0, 7); g.fill(); });
  g.fillStyle = RED; g.beginPath(); g.arc(cab[0], cab[1], 7, 0, 7); g.fill();
  status(el, m, (S.wall || 0) * Math.min(1, (i0 + k) / (st.length - 1)), minute >= S.minutes ? S.solved : null, `doors ${Math.min(i0, S.visits)} of ${S.budget}`);
  tray(el, found);
}
function drawBaker() {
  const el = $("#p-baker"), cv = $("canvas", el), {g, P, A} = baseMap(cv), B = C.baker, m = Math.min(minute, B.minute);
  const {i, a, b, k} = lerpTicks(B.ticks, m);
  const [bx, by] = A(C.map.baker); const gl = g.createRadialGradient(bx, by, 0, bx, by, 50);
  gl.addColorStop(0, "rgba(224,179,87,0.45)"); gl.addColorStop(1, "rgba(224,179,87,0)"); g.fillStyle = gl; g.fillRect(bx - 50, by - 50, 100, 100);
  a.boys.forEach((p, j) => { const q = b.boys[j] || p, [x, y] = P([p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k]);
    g.fillStyle = "#2f5f8f"; g.beginPath(); g.arc(x, y, 5, 0, 7); g.fill(); });
  if (a.w) { const q = b.w || a.w, [x, y] = P([a.w[0] + (q[0] - a.w[0]) * k, a.w[1] + (q[1] - a.w[1]) * k]);
    g.fillStyle = "#e0b357"; g.beginPath(); g.arc(x, y, 7, 0, 7); g.fill(); g.strokeStyle = INK; g.lineWidth = 1.5; g.stroke(); }
  const found = {}; B.ticks.slice(0, i + 1).forEach((t) => t.new.forEach((n) => found[n.part] = (found[n.part] || 0) + 1));
  status(el, m, a.wall + ((b.wall || a.wall) - a.wall) * k, minute >= B.minute ? B.solved : null, `reports at 221B: ${a.reports}`);
  tray(el, found);
}
function drawSwarm() {
  const el = $("#p-swarm"), cv = $("canvas", el), {g, P} = baseMap(cv), SW = C.swarm, m = Math.min(minute, SW.minute);
  const {a, b, k} = lerpTicks(SW.ticks, m);
  g.strokeStyle = "rgba(163,57,46,0.15)"; g.lineWidth = 1;
  (a.shares || []).slice(0, 20).forEach((s) => { const [x, y] = P(s); g.beginPath(); g.arc(x, y, 200 * cv.width / 1000 * (0.3 + 0.7 * k), 0, 7); g.stroke(); });
  a.boys.forEach((p, j) => { const q = b.boys[j] || p, [x, y] = P([p[0] + (q[0] - p[0]) * k, p[1] + (q[1] - p[1]) * k]);
    const v = k < 0.5 ? a.vote[j] : b.vote[j];
    if (v === -2) { g.strokeStyle = "rgba(60,45,30,0.6)"; g.lineWidth = 1.2; g.beginPath(); g.arc(x, y, 3.5, 0, 7); g.stroke(); return; }
    g.fillStyle = v >= 0 ? ANS[v % 4] : OTHER; g.beginPath(); g.arc(x, y, 5, 0, 7); g.fill(); });
  const lead = a.vote.filter((v) => v === 0).length;
  status(el, m, a.wall + ((b.wall || a.wall) - a.wall) * k, minute >= SW.minute ? (SW.quorum ? SW.solved : false) : null, `votes for the leading answer: ${lead} / 30`);
  const t = el.querySelector(".tray");
  t.innerHTML = SW.answers.map((A, i) => `<span class="on" style="color:${ANS[i % 4]}">● ${esc(A.parts.join(" · "))}</span>`).join("") || "<span>no full answers yet</span>";
}
function status(el, m, wall, verdict, extra) {
  const v = verdict == null ? "" : verdict ? '<b class="solved">SOLVED</b>' : '<b class="unsolved">UNSOLVED</b>';
  el.querySelector(".status").innerHTML = `<span>case ${hm(m)} · real ${secs(wall)} · ${extra}</span>${v}`;
}
function tray(el, found) {
  el.querySelector(".tray").innerHTML = ["culprit", "motive", "hideout"].map((p) =>
    `<span class="${found[p] ? "on" : ""}">${found[p] ? "●" : "○"} ${PART[p]} clues ${found[p] || 0}</span>`).join("");
}

/* ---------------------------------------------------------------- logs */
function buildLogs() {
  const solo = C.solo.stops.slice(1).map((s) => ({m: s.minute,
    h: `${s.part ? `<b>${PART[s.part]} clue.</b> ` : ""}${esc(s.clue || "")}${s.note ? `<br><i>Astra: ${esc(s.note)}</i>` : ""}`}));
  solo.push({m: C.solo.minutes, h: `<b>${C.solo.solved ? "Solved" : "Unsolved"}</b>: ${verdict(C.solo.ok)}`});
  const baker = C.baker.orders.map((o) => ({m: o.minute, h: `<i>Holmes: ${esc(o.text)}</i>`}));
  C.baker.ticks.forEach((t) => t.new.forEach((n) => baker.push({m: t.minute, h: `<b>${PART[n.part]} report.</b> ${esc(n.text)}`})));
  baker.sort((x, y) => x.m - y.m);
  baker.push({m: C.baker.minute, h: `<b>${C.baker.solved ? "Solved" : "Unsolved"}</b>: ${verdict(C.baker.ok)}`});
  const swarm = []; let prev = -1;
  C.swarm.ticks.forEach((t) => { const n = t.vote.filter((v) => v === 0).length, any = t.vote.filter((v) => v !== -2).length;
    if (n !== prev && (n > 0 || any > 0)) { swarm.push({m: t.minute, h: `${any} boys hold a full answer; ${n} back the leading one${C.swarm.answers[0] ? ` (${esc(C.swarm.answers[0].parts.join(" · "))})` : ""}`}); prev = n; } });
  swarm.push({m: C.swarm.minute, h: C.swarm.quorum ? `<b>${C.swarm.solved ? "Solved" : "Agreed, but wrong"}</b>: ${verdict(C.swarm.ok)}` : "<b>No agreement in 12 hours</b>"});
  for (const [id, items] of [["p-solo", solo], ["p-baker", baker], ["p-swarm", swarm]])
    $(`#${id} .log`).innerHTML = items.map((x) => `<li data-m="${x.m}"><span class="t">${hm(x.m)}</span>${x.h}</li>`).join("");
}
function verdict(ok) {
  if (!ok) return "";
  return ["culprit", "motive", "hideout"].map((k) => `${k} ${ok[k] ? "✓" : "✗"}`).join(", ");
}
function markLogs() {
  document.querySelectorAll(".log").forEach((ol) => { let lastPast = null;
    ol.querySelectorAll("li").forEach((li) => { const past = +li.dataset.m <= minute; li.classList.toggle("future", !past); if (past) lastPast = li; });
    if (lastPast && playing) ol.scrollTop = lastPast.offsetTop - ol.offsetTop - ol.clientHeight + lastPast.clientHeight + 8; });
}

function draw() {
  if (!C) return;
  $("#clock").textContent = hm(Math.min(minute, 720));
  drawSolo(); drawBaker(); drawSwarm(); markLogs();
}
init();

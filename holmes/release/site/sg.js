// Scatter and gather: the blog's side-by-side figure of how each detective spreads out over the city and how the
// evidence comes back together into an answer, with an evidence board and two progress charts beneath.
// Data: data/sg/<kind>_<seed>.json, written by release/export_scatter.py from the logged runs.
(function () {
  const root = document.getElementById("sg");
  if (!root) return;
  const NS = "http://www.w3.org/2000/svg";
  const END = 720;                       // 12 case hours, in minutes
  // timeline windows: one per row and wide on a desktop, compact on a phone (set per build from the figure's width)
  let W, H, X0, X1, XV, Y0 = 18, Y1;
  const size = () => {
    const wide = root.clientWidth >= 640;
    W = wide ? 900 : 300; H = wide ? 250 : 210; X0 = wide ? 44 : 34; XV = W - 22; X1 = XV - (wide ? 52 : 32); Y1 = H - 22;
    panels.classList.toggle("sg-rows", wide);
  };
  const WHO = [
    { key: "baker", name: "Holmes (GPT6-Astra) + Jev Swarm", color: "#8a1c1c", how: "Astra plans at 221B (◆); 12 Jev boys decide each step (|)" },
    { key: "solo", name: "The Lone Genius (GPT6-Astra)", color: "#3d6a99", how: "GPT6-Astra makes every decision (◆), one stop at a time" },
    { key: "swarm", name: "Jev Swarm", color: "#c08a2e", how: "100 Jev boys each decide every 15 min (|); no leader, answer by vote" },
  ];
  const PART = { culprit: "#6a3d8f", motive: "#2e7d6b", hideout: "#a0522d" };
  const LIE = "#d03030", OK = "#2e7d32", BAD = "#c62828", ASTRA = "#1d3557";
  // a Jev boy's decision each quarter-hour: go somewhere (check, move, tail), talk (share, report back), or wait
  const KIND = { C: "go", M: "go", T: "go", S: "talk", R: "talk", F: "talk", L: "talk", W: "wait" };
  const KCOL = { go: "#4f6d8a", talk: "#e09b20", wait: "#cdbfa3" };
  const diamond = (cx, cy, r) => `M${cx},${cy - r} L${cx + r},${cy} L${cx},${cy + r} L${cx - r},${cy} Z`;
  const x = m => X0 + (Math.min(m, END) / END) * (X1 - X0);
  const hm = m => `${Math.floor(m / 60)}h ${String(Math.round(m % 60)).padStart(2, "0")}m`;
  const el = (tag, attrs, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };
  const h = (tag, cls, parent, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  };

  // ---------------------------------------------------------------- controls and layout
  const bar = h("div", "sg-bar", root);
  const kindSel = h("select", "", bar);
  [["standard", "Standard cases"], ["frameup", "Frame-up cases"]].forEach(([v, t]) => {
    const o = h("option", "", kindSel, t); o.value = v;
  });
  const seedSel = h("select", "", bar);
  for (let i = 1; i <= 100; i++) { const o = h("option", "", seedSel, `Case ${i}`); o.value = i; }
  const play = h("button", "", bar, "Pause");
  const replay = h("button", "", bar, "Replay");
  const slider = h("input", "", bar); slider.type = "range"; slider.min = 0; slider.max = END; slider.step = 1;
  const clock = h("span", "sg-clock", bar);
  kindSel.setAttribute("aria-label", "Case set"); seedSel.setAttribute("aria-label", "Case number");
  slider.setAttribute("aria-label", "Case time");
  const legend = h("div", "sg-key", root);
  h("div", "sg-zhint", root, "Zoom any window with + / −, a double-click, a pinch or ⌘/Ctrl-scroll; drag to move around when zoomed in.");
  const panels = h("div", "sg-grid", root);
  h("div", "sg-head", root, "Evidence board");
  const boardKey = h("div", "sg-bkey", root);
  const boards = h("div", "sg-grid", root);
  const charts = h("div", "sg-charts", root);

  // the colour key, drawn with the same marks the figure uses
  const sw = (svg) => `<svg viewBox="0 0 22 14" width="22" height="14" aria-hidden="true">${svg}</svg>`;
  const dotK = (fill, stroke) => sw(`<circle cx="11" cy="7" r="4.5" fill="${fill}" ${stroke ? `stroke="${stroke}" stroke-width="1.6"` : ""}/>`);
  const lineK = (c, dash) => sw(`<line x1="1" y1="7" x2="21" y2="7" stroke="${c}" stroke-width="2.4" ${dash ? 'stroke-dasharray="3 2"' : ""}/>`);
  const tickK = c => sw(`<line x1="11" y1="1" x2="11" y2="13" stroke="${c}" stroke-width="2.4"/>`);
  const pinK = (cls, c) => `<span class="sg-pin ${cls}" style="--c:${c}">clue</span>`;
  const group = (title, rows) => `<div class="sg-kg"><div class="sg-kt">${title}</div>` +
    rows.map(([m, t]) => `<div class="sg-ki">${m}<span>${t}</span></div>`).join("") + `</div>`;
  legend.innerHTML = `<div class="sg-kh">How to read the colours</div><div class="sg-kgrid">` +
    group("Dots: an address checked (in every window)", [
      [dotK(PART.culprit), "key clue to the <b>culprit</b>"], [dotK(PART.motive), "key clue to the <b>motive</b>"],
      [dotK(PART.hideout), "key clue to the <b>hideout</b>"], [dotK("#b9ad94"), "nothing decisive there"],
      [dotK("#fff", LIE), "a <b>lie</b> (frame-up cases)"]]) +
    group("Decision points", [
      [sw(`<path d="${diamond(11, 7, 5.5)}" fill="${ASTRA}"/>`), "GPT6-Astra decides (Holmes plans, or the Lone Genius picks its next stop)"],
      [tickK(KCOL.go), "a Jev boy decides to <b>move</b> (check, go, tail)"],
      [tickK(KCOL.talk), "a Jev boy decides to <b>share or report</b>"],
      [tickK(KCOL.wait), "a Jev boy decides to <b>wait</b>"]]) +
    group("Evidence reaching the answer", [
      [lineK(PART.culprit), "a clue carried to the answer, in its clue colour"],
      [lineK(LIE, true), "a lie carried to the answer"],
      [lineK(OK), "Jev Swarm: a vote for a fully right answer"],
      [lineK(BAD), "Jev Swarm: a vote for a wrong answer"]]) +
    `</div>`;
  boardKey.innerHTML = [[pinK("on", PART.motive), "clue in hand (filled, in its clue colour)"],
    [pinK("", PART.motive), "clue not found yet (dashed)"], [pinK("lie on", LIE), "a lie picked up"]]
    .map(([m, t]) => `<div class="sg-ki">${m}<span>${t}</span></div>`).join("");

  // zoom a timeline window: + / − / reset buttons, double-click, pinch or ctrl/⌘-scroll; drag to pan once zoomed
  function zoomable(svg, title) {
    let vb = [0, 0, W, H];
    const tools = h("span", "sg-zoom", title);
    const set = () => {
      svg.setAttribute("viewBox", vb.join(" "));
      const z = W / vb[2];
      svg.classList.toggle("zoomed", z > 1.01);
      lvl.textContent = z > 1.01 ? `${z.toFixed(1)}×` : "";
    };
    const zoomAt = (f, px, py) => {
      const nw = Math.min(W, Math.max(W / 16, vb[2] / f)), nh = nw * H / W;
      vb = [px - (px - vb[0]) * nw / vb[2], py - (py - vb[1]) * nh / vb[3], nw, nh];
      vb[0] = Math.max(0, Math.min(W - nw, vb[0])); vb[1] = Math.max(0, Math.min(H - nh, vb[1]));
      set();
    };
    const pt = e => { const r = svg.getBoundingClientRect();
      return [vb[0] + (e.clientX - r.left) / r.width * vb[2], vb[1] + (e.clientY - r.top) / r.height * vb[3]]; };
    const mid = () => [vb[0] + vb[2] / 2, vb[1] + vb[3] / 2];
    const btn = (t, label, f) => { const b = h("button", "", tools, t); b.type = "button"; b.title = label; b.setAttribute("aria-label", label); b.onclick = f; };
    btn("+", "Zoom in", () => zoomAt(2, ...mid()));
    btn("−", "Zoom out", () => zoomAt(0.5, ...mid()));
    btn("reset", "Reset zoom", () => { vb = [0, 0, W, H]; set(); });
    const lvl = h("span", "sg-zl", tools);
    svg.addEventListener("dblclick", e => { e.preventDefault(); zoomAt(2, ...pt(e)); });
    svg.addEventListener("wheel", e => {
      if (!e.ctrlKey && !e.metaKey) return;  // plain scrolling still scrolls the page
      e.preventDefault(); zoomAt(Math.exp(-e.deltaY * 0.01), ...pt(e));
    }, { passive: false });
    let drag = null;
    svg.addEventListener("pointerdown", e => {
      if (vb[2] >= W) return;
      drag = { x: e.clientX, y: e.clientY, vb: vb.slice() }; svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", e => {
      if (!drag) return;
      const r = svg.getBoundingClientRect();
      vb[0] = Math.max(0, Math.min(W - vb[2], drag.vb[0] - (e.clientX - drag.x) / r.width * vb[2]));
      vb[1] = Math.max(0, Math.min(H - vb[3], drag.vb[1] - (e.clientY - drag.y) / r.height * vb[3]));
      set();
    });
    const end = () => { drag = null; };
    svg.addEventListener("pointerup", end); svg.addEventListener("pointercancel", end);
  }

  let C = null, T = 0, playing = true, last = null, items = [];

  function load(kind, seed) {
    return fetch(`data/sg/${kind}_${seed}.json`).then(r => r.json()).then(d => { C = d; build(); T = 0; playing = true; });
  }

  // in hand at minute t: the Lone Genius once it has been there, Holmes once a report reached Baker Street,
  // the swarm once any boy has been there (they start one at every address)
  function inHand(w, d) {
    const m = {};
    if (w === "baker") d.baker.reports.forEach(([t, a]) => { if (!(a in m)) m[a] = t; });
    else d[w].visits.forEach(([t, , a]) => { if (!(a in m)) m[a] = t; });
    return m;
  }

  // ---------------------------------------------------------------- build one case
  function build() {
    size();
    panels.innerHTML = ""; boards.innerHTML = ""; charts.innerHTML = ""; items = [];
    const d = C, keyPart = {}, isLie = {};
    d.keys.forEach(([a, p]) => { keyPart[a] = p; });
    d.lies.forEach(([a]) => { isLie[a] = true; });
    const ends = WHO.map(w => d[w.key].end);
    const last = Math.max(...ends);
    slider.max = Math.ceil(Math.max(last, 60) / 15) * 15;

    WHO.forEach(w => {
      const r = d[w.key];
      const card = h("div", "sg-panel", panels);
      const title = h("div", "sg-title", card);
      const dot = h("span", "sg-dot", title); dot.style.background = w.color;
      h("b", "", title, w.name);
      h("div", "sg-how", card, w.how);
      // the dots, explained in place: what each colour found
      const dl = h("div", "sg-dots", card);
      dl.innerHTML = (w.key === "swarm"
        ? "<b>Dots</b> (stacked at 0h): the 100 boys start one per address, so the whole city is checked at once; zoom in to see them. "
        : "<b>Dots</b>: each address checked. ") +
        [[PART.culprit, "culprit clue"], [PART.motive, "motive clue"], [PART.hideout, "hideout clue"], ["#b9ad94", "nothing decisive"]]
          .map(([c, t]) => `<span><i style="background:${c}"></i>${t}</span>`).join("") +
        `<span><i class="lie" style="border-color:${LIE}"></i>lie</span>`;
      const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${w.name}: scatter and gather` }, card);
      zoomable(svg, title);
      const n = r.lanes, ly = i => n === 1 ? (Y0 + Y1) / 2 : Y0 + (i + 0.5) * (Y1 - Y0) / n;
      const ym = (Y0 + Y1) / 2;
      // time axis
      for (let hr = 0; hr <= 12; hr += 3) {
        el("line", { x1: x(hr * 60), x2: x(hr * 60), y1: Y0 - 6, y2: Y1 + 4, class: "sg-grid-line" }, svg);
        el("text", { x: x(hr * 60), y: H - 6, class: "sg-tick" }, svg).textContent = `${hr}h`;
      }
      const g = el("g", {}, svg);
      const add = (node, t) => { items.push({ node, t }); return node; };
      // scatter: from the start out over the lanes
      const src = el("circle", { cx: 12, cy: ym, r: 5, fill: w.color }, svg);
      el("text", { x: 12, y: ym - 9, class: "sg-lbl" }, svg).textContent = w.key === "swarm" ? "city" : "221B";
      const laneFirst = {};
      r.visits.forEach(v => { if (!(v[1] in laneFirst)) laneFirst[v[1]] = v; });
      Object.values(laneFirst).forEach(([t, lane]) => {
        const y = ly(lane);
        add(el("path", { d: `M12,${ym} C${X0 - 6},${ym} ${X0 - 14},${y} ${x(t)},${y}`, class: "sg-fan",
          stroke: w.color }, g), t);
      });
      if (w.key === "solo") {  // one chain, one stop after another
        let px = x(0), py = ym;
        r.visits.forEach(([t]) => {
          add(el("line", { x1: px, y1: py, x2: x(t), y2: ym, stroke: w.color, class: "sg-chain" }, g), t);
          px = x(t); py = ym;
        });
      }
      const dotR = n > 50 ? 1.6 : n > 1 ? 2.6 : 3.4;
      const where = {};
      r.visits.forEach(([t, lane, a]) => {
        const cx = x(t) + (w.key === "swarm" ? (lane % 4) * 1.2 : 0), cy = ly(lane);
        where[a] = [cx, cy];
        const k = keyPart[a], lie = isLie[a];
        add(el("circle", { cx, cy, r: k || lie ? dotR + 1.2 : dotR, fill: k ? PART[k] : lie ? "#fff" : "#b9ad94",
          stroke: lie ? LIE : "none", "stroke-width": lie ? 1.4 : 0 }, g), t);
      });
      // decision points: GPT6-Astra's as diamonds, every Jev boy's as a short tick on its lane
      if (r.decisions && w.key !== "solo") {
        const hgt = Math.max(1.2, Math.min(5, (Y1 - Y0) / n * 0.8));
        r.decisions.forEach(([t, row]) => {
          const by = { go: "", talk: "", wait: "" };
          for (let i = 0; i < row.length; i++) {
            const k = KIND[row[i]];
            if (k) by[k] += `M${x(t)},${ly(i) - hgt / 2} v${hgt} `;
          }
          for (const k in by) if (by[k]) add(el("path", { d: by[k], stroke: KCOL[k], "stroke-width": n > 50 ? 0.9 : 1.4 }, g), t);
        });
      }
      if (w.key === "solo") {
        (r.decisions || []).forEach(t => {
          const dm = add(el("path", { d: diamond(x(t), ym, 4.2), fill: ASTRA, stroke: "#fff", "stroke-width": 0.8 }, g), t);
          el("title", {}, dm).textContent = `GPT6-Astra decides at ${hm(t)}`;
        });
      }
      if (w.key === "baker") {
        el("text", { x: 2, y: 11, class: "sg-lbl", style: "text-anchor: start" }, svg).textContent = "Astra";
        (r.plans || []).forEach(([t, k]) => {
          add(el("line", { x1: x(t), x2: x(t), y1: 13, y2: Y1, class: "sg-plan" }, g), t);
          const dm = add(el("path", { d: diamond(x(t), 8, 5), fill: ASTRA, stroke: "#fff", "stroke-width": 0.8 }, g), t);
          el("title", {}, dm).textContent = `Holmes (GPT6-Astra) plans at ${hm(t)}: ${k} errand${k === 1 ? "" : "s"}`;
        });
      }
      // gather: evidence travelling to the answer
      const vy = ym;
      if (w.key === "solo" || w.key === "baker") {
        const sent = w.key === "solo" ? r.visits.map(([t, , a]) => [t, a]) : r.reports;
        sent.forEach(([t, a]) => {
          const k = keyPart[a], lie = isLie[a];
          if (!k && !lie) return;
          const [sx, sy] = where[a] || [x(t), vy];
          const fx = w.key === "baker" ? x(t) : sx;
          add(el("path", { d: `M${fx},${sy} C${(fx + XV) / 2},${sy} ${(fx + XV) / 2},${vy} ${XV - 21},${vy}`,
            class: "sg-gather", stroke: lie ? LIE : PART[k], "stroke-dasharray": lie ? "3 2" : "none" }, g), t);
        });
      }
      if (w.key === "swarm") {  // no centre: the only gathering is each boy casting a vote for a full answer
        (r.ballots || []).forEach(([t, boy, i]) => {
          const right = r.answers[i] && r.answers[i].ok.every(Boolean);
          const sy = ly(boy), fx = x(t);
          add(el("path", { d: `M${fx},${sy} C${(fx + XV) / 2},${sy} ${(fx + XV) / 2},${vy} ${XV - 21},${vy}`,
            class: "sg-vote", stroke: right ? OK : BAD }, g), t);
        });
      }
      // the answer node: three slots, coloured by whether the working answer is right
      // the answer node: culprit, motive, hideout, each a tick when right and a cross when wrong
      const ring = el("rect", { x: XV - 20, y: vy - 15, width: 40, height: 30, rx: 5, fill: "#fff", stroke: w.color, "stroke-width": 2 }, svg);
      el("title", {}, ring).textContent = "Working answer: culprit · motive · hideout (✓ right, ✗ wrong)";
      const slots = [-12, 0, 12].map(dx => el("text", { x: XV + dx, y: vy + 3, class: "sg-mark" }, svg));
      ["C", "M", "H"].forEach((t, i) => { el("text", { x: XV - 12 + i * 12, y: vy + 11.5, class: "sg-cmh" }, svg).textContent = t; });
      el("text", { x: XV, y: vy + 26, class: "sg-lbl" }, svg).textContent = w.key === "swarm" ? "vote" : "answer";
      const votes = w.key === "swarm" ? el("text", { x: XV, y: vy - 20, class: "sg-lbl" }, svg) : null;
      const status = h("div", "sg-status", card);
      items.push({ update(t) {
        const cur = pickAt(r.picks, t);
        const ok = cur ? cur[2] : null;
        slots.forEach((s, i) => { s.textContent = !cur ? "?" : ok[i] ? "✓" : "✗"; s.setAttribute("fill", !cur ? "#bbb" : ok[i] ? OK : BAD); });
        ring.setAttribute("stroke-width", t >= r.end ? 4 : 2);
        if (votes) {
          const v = voteAt(r.votes, t);
          votes.textContent = v ? `${Math.max(...v)}/30` : "";
        }
        const solved = Object.values(r.ok).every(Boolean);
        status.innerHTML = t >= r.end
          ? `<b class="${solved ? "ok" : "bad"}">${solved ? "Solved" : "Unsolved"}</b> at ${hm(r.end)}`
          : `Working… ${r.visits.filter(v => v[0] <= t).length} addresses so far`;
      } });

      // the evidence board for this detective
      const b = h("div", "sg-board", boards);
      const bt = h("div", "sg-title", b);
      const bd = h("span", "sg-dot", bt); bd.style.background = w.color;
      h("b", "", bt, w.name);
      const ans = h("div", "sg-answer", b);
      const rows = ["Culprit", "Motive", "Hideout"].map(lbl => {
        const row = h("div", "sg-row", ans); h("span", "sg-k", row, lbl); return h("span", "sg-v", row, "—");
      });
      const pins = h("div", "sg-pins", b);
      const have = inHand(w.key, d);
      const pinEls = d.keys.map(([a, p, label]) => {
        const e = h("span", "sg-pin", pins, label); e.style.setProperty("--c", PART[p]); return [e, have[a]];
      }).concat(d.lies.map(([a, label]) => {
        const e = h("span", "sg-pin lie", pins, "lie: " + label); e.style.setProperty("--c", LIE); return [e, have[a]];
      }));
      const tally = h("div", "sg-tally", b);
      items.push({ update(t) {
        const cur = pickAt(r.picks, t);
        const ok = cur ? cur[2] : null;
        rows.forEach((e, i) => {
          e.textContent = cur ? `${ok[i] ? "✓" : "✗"} ${cur[1][i] || "—"}` : "—";
          e.className = "sg-v " + (cur ? (ok[i] ? "ok" : "bad") : "");
        });
        let k = 0, l = 0;
        pinEls.forEach(([e, at], i) => {
          const on = at != null && at <= t;
          e.classList.toggle("on", on);
          if (on) { if (i < d.keys.length) k++; else l++; }
        });
        tally.textContent = `Key evidence in hand ${k}/${d.keys.length}` + (d.lies.length ? ` · lies picked up ${l}` : "");
      } });
    });

    // two charts side by side: key evidence in hand, and how much of the working answer is right
    const mk = (title, yMax, ylabels) => {
      const box = h("div", "sg-chart", charts);
      h("div", "sg-ctitle", box, title);
      const s = el("svg", { viewBox: "0 0 320 150", role: "img", "aria-label": title }, box);
      const cx = m => 34 + (Math.min(m, END) / END) * 276, cy = v => 128 - (v / yMax) * 110;
      for (let hr = 0; hr <= 12; hr += 3) {
        el("line", { x1: cx(hr * 60), x2: cx(hr * 60), y1: 18, y2: 128, class: "sg-grid-line" }, s);
        el("text", { x: cx(hr * 60), y: 143, class: "sg-tick" }, s).textContent = `${hr}h`;
      }
      ylabels.forEach(v => {
        el("line", { x1: 34, x2: 310, y1: cy(v), y2: cy(v), class: "sg-grid-line" }, s);
        el("text", { x: 28, y: cy(v) + 3, class: "sg-tick", "text-anchor": "end" }, s).textContent = v;
      });
      const cursor = el("line", { x1: 34, x2: 34, y1: 14, y2: 128, class: "sg-cursor" }, s);
      return { s, cx, cy, cursor };
    };
    const A = mk("Key evidence in hand", d.keys.length, [0, Math.round(d.keys.length / 2), d.keys.length]);
    const B = mk("Parts of the working answer that are right", 3, [0, 1, 2, 3]);
    WHO.forEach(w => {
      const r = d[w.key];
      const have = inHand(w.key, d);
      const times = d.keys.map(([a]) => have[a]).filter(t => t != null).sort((p, q) => p - q);
      const stepA = [[0, 0]]; times.forEach((t, i) => stepA.push([t, i + 1]));
      const stepB = [[0, 0]].concat(r.picks.map(([t, , ok]) => [t, ok.filter(Boolean).length]));
      [[A, stepA], [B, stepB]].forEach(([c, pts]) => {
        const path = el("path", { fill: "none", stroke: w.color, "stroke-width": 2 }, c.s);
        const head = el("circle", { r: 3, fill: w.color }, c.s);
        items.push({ update(t) {
          const end = Math.min(t, r.end);
          let dd = "", y = 0;
          pts.forEach(([pt, v], i) => {
            if (pt > end) return;
            dd += (i ? ` L${c.cx(pt)},${c.cy(y)} L${c.cx(pt)},${c.cy(v)}` : `M${c.cx(pt)},${c.cy(v)}`);
            y = v;
          });
          dd += ` L${c.cx(end)},${c.cy(y)}`;
          path.setAttribute("d", dd);
          head.setAttribute("cx", c.cx(end)); head.setAttribute("cy", c.cy(y));
        } });
      });
    });
    items.push({ update(t) { [A, B].forEach(c => { c.cursor.setAttribute("x1", c.cx(t)); c.cursor.setAttribute("x2", c.cx(t)); }); } });
  }

  function pickAt(picks, t) {
    let cur = null;
    for (const p of picks) { if (p[0] <= t) cur = p; else break; }
    return cur;
  }
  function voteAt(votes, t) {
    let cur = null;
    for (const v of votes) { if (v[0] <= t) cur = v[1]; else break; }
    return cur;
  }
  function render() {
    items.forEach(it => it.update ? it.update(T) : (it.node.style.opacity = it.t <= T ? 1 : 0));
    slider.value = T;
    clock.textContent = `case time ${hm(T)}`;
  }
  function frame(ts) {
    if (last != null && playing && C) {
      T = Math.min(+slider.max, T + (ts - last) / 1000 * 36);  // 36 case minutes a second: 12 hours in 20 s
      if (T >= +slider.max) { playing = false; play.textContent = "Play"; }
    }
    last = ts;
    if (C) render();
    requestAnimationFrame(frame);
  }
  play.onclick = () => { if (T >= +slider.max) T = 0; playing = !playing; play.textContent = playing ? "Pause" : "Play"; };
  replay.onclick = () => { T = 0; playing = true; play.textContent = "Pause"; };
  slider.oninput = () => { T = +slider.value; playing = false; play.textContent = "Play"; };
  const change = () => load(kindSel.value, seedSel.value).then(() => { play.textContent = "Pause"; });
  kindSel.onchange = change; seedSel.onchange = change;

  seedSel.value = root.dataset.seed || 57;
  kindSel.value = root.dataset.kind || "standard";
  load(kindSel.value, seedSel.value).then(() => {
    playing = false; play.textContent = "Play";
    // start playing the first time the figure scrolls into view
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver(es => {
        if (es.some(e => e.isIntersecting)) { T = 0; playing = true; play.textContent = "Pause"; io.disconnect(); }
      }, { threshold: 0.35 });
      io.observe(root);
    } else { playing = true; play.textContent = "Pause"; }
    requestAnimationFrame(frame);
  });
})();

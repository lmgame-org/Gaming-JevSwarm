"use strict";
/* Fancy world renderer: 60 fps interpolation between 20 Hz server frames, animated fish with tail beats,
   ocean light, bubbles, escape pulses, capture bursts, predator pursuit lines. Viewer only. */
const FX = (() => {
  let prev = null, cur = null, recvAt = 0, interval = 50;
  const lastKind = new Map(), lastPos = new Map();
  const pulses = [], particles = [], bubbles = [];
  let bg = null, bgKey = "", seenCaptures = 0, t0 = performance.now();
  const PULSE_KINDS = new Set(["ESCAPE", "FLEE_WITH", "BURST"]);

  function onFrame(f) {
    const now = performance.now();
    if (cur) interval = Math.min(200, Math.max(20, 0.8 * interval + 0.2 * (now - recvAt)));
    prev = cur; cur = f; recvAt = now;
    if (!prev || f.t < prev.t) { seenCaptures = f.captures.length; pulses.length = 0; particles.length = 0; lastKind.clear(); }
    for (const q of f.fish) {
      const [id, x, y, , , , kind] = q;
      const was = lastKind.get(id);
      if (was !== undefined && was !== kind && PULSE_KINDS.has(kind))
        pulses.push({x, y, born: now, color: COLORS[kind] || "#fff", big: kind === "ESCAPE"});
      lastKind.set(id, kind);
      lastPos.set(id, [x, y]);
    }
    const nCap = f.captures.length;
    // captures list is the last 20; detect new ones by time
    for (const [t, id] of f.captures) {
      if (t > (onFrame.lastCapT ?? -1)) {
        const p = lastPos.get(id);
        if (p) burst(p[0], p[1], now);
      }
    }
    if (nCap) onFrame.lastCapT = f.captures[nCap - 1][0];
    seenCaptures = nCap;
  }

  function burst(x, y, now) {
    pulses.push({x, y, born: now, color: "#ff3355", big: true, capture: true});
    for (let i = 0; i < 26; i++) {
      const a = Math.random() * 6.283, v = 1.5 + Math.random() * 4;
      particles.push({x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, born: now, life: 700 + Math.random() * 600,
        r: 0.12 + Math.random() * 0.25, c: Math.random() < 0.6 ? "255,70,90" : "255,210,220"});
    }
  }

  const lerp = (a, b, u) => a + (b - a) * u;
  const lerpAng = (a, b, u) => { let d = ((b - a + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI; return a + d * u; };

  function background(cv, W, H) {
    const key = `${cv.width}x${cv.height}`;
    if (bg && bgKey === key) return bg;
    bgKey = key;
    bg = document.createElement("canvas"); bg.width = cv.width; bg.height = cv.height;
    const g = bg.getContext("2d");
    const lg = g.createLinearGradient(0, 0, 0, cv.height);
    lg.addColorStop(0, "#0b3550"); lg.addColorStop(0.55, "#082a40"); lg.addColorStop(1, "#04121d");
    g.fillStyle = lg; g.fillRect(0, 0, cv.width, cv.height);
    // sandy speckle floor texture
    for (let i = 0; i < cv.width * cv.height / 900; i++) {
      g.fillStyle = `rgba(160,200,220,${Math.random() * 0.05})`;
      g.fillRect(Math.random() * cv.width, Math.random() * cv.height, 1.5, 1.5);
    }
    const s = cv.width / W;
    g.strokeStyle = "rgba(90,150,180,0.07)"; g.lineWidth = 1;
    for (let x = 0; x <= W; x += 10) { g.beginPath(); g.moveTo(x * s, 0); g.lineTo(x * s, cv.height); g.stroke(); }
    for (let y = 0; y <= H; y += 10) { g.beginPath(); g.moveTo(0, y * s); g.lineTo(cv.width, y * s); g.stroke(); }
    const vg = g.createRadialGradient(cv.width / 2, cv.height / 2, cv.height * 0.3, cv.width / 2, cv.height / 2, cv.width * 0.75);
    vg.addColorStop(0, "rgba(0,0,0,0)"); vg.addColorStop(1, "rgba(0,0,0,0.55)");
    g.fillStyle = vg; g.fillRect(0, 0, cv.width, cv.height);
    return bg;
  }

  function caustics(g, cv, time) {
    g.save(); g.globalCompositeOperation = "lighter";
    const n = 9;
    for (let i = 0; i < n; i++) {
      const x = (0.5 + 0.45 * Math.sin(time * 0.00007 * (i + 3) + i * 1.7)) * cv.width;
      const y = (0.5 + 0.45 * Math.cos(time * 0.00005 * (i + 2) + i * 2.3)) * cv.height;
      const r = cv.width * (0.08 + 0.05 * Math.sin(time * 0.0004 + i));
      const rg = g.createRadialGradient(x, y, 0, x, y, r);
      rg.addColorStop(0, "rgba(80,200,230,0.07)"); rg.addColorStop(1, "rgba(80,200,230,0)");
      g.fillStyle = rg; g.beginPath(); g.arc(x, y, r, 0, 6.283); g.fill();
    }
    // light shafts from the surface
    for (let i = 0; i < 4; i++) {
      const x = (0.15 + 0.25 * i + 0.05 * Math.sin(time * 0.0002 + i)) * cv.width;
      const lg = g.createLinearGradient(x, 0, x + cv.width * 0.1, cv.height);
      lg.addColorStop(0, "rgba(140,220,255,0.06)"); lg.addColorStop(1, "rgba(140,220,255,0)");
      g.fillStyle = lg; g.beginPath();
      g.moveTo(x - cv.width * 0.03, 0); g.lineTo(x + cv.width * 0.03, 0);
      g.lineTo(x + cv.width * 0.16, cv.height); g.lineTo(x + cv.width * 0.06, cv.height); g.closePath(); g.fill();
    }
    g.restore();
  }

  function drawBubbles(g, cv, s, dt) {
    while (bubbles.length < 45) bubbles.push({x: Math.random() * cv.width, y: cv.height + Math.random() * cv.height,
      r: (0.08 + Math.random() * 0.22) * s, v: (0.6 + Math.random()) * s, w: Math.random() * 6});
    g.strokeStyle = "rgba(190,235,255,0.35)"; g.lineWidth = 1;
    for (const b of bubbles) {
      b.y -= b.v * dt; b.w += dt * 2;
      const x = b.x + Math.sin(b.w) * s * 0.3;
      if (b.y < -10) { b.y = cv.height + 10; b.x = Math.random() * cv.width; }
      g.beginPath(); g.arc(x, b.y, b.r, 0, 6.283); g.stroke();
    }
  }

  function fishShape(g, x, y, h, L, color, phase, speed, glow, dim) {
    g.save(); g.translate(x, y); g.rotate(-h);
    const beat = Math.sin(phase) * (0.25 + 0.12 * speed);
    if (glow) { g.shadowColor = color; g.shadowBlur = L * 0.9; }
    g.globalAlpha = dim ? 0.5 : 1;
    // tail
    g.save(); g.translate(-L * 0.38, 0); g.rotate(beat);
    g.beginPath(); g.moveTo(0, 0); g.lineTo(-L * 0.32, L * 0.2); g.quadraticCurveTo(-L * 0.24, 0, -L * 0.32, -L * 0.2); g.closePath();
    g.fillStyle = color; g.fill(); g.restore();
    // body with a light belly gradient
    const gr = g.createLinearGradient(0, -L * 0.2, 0, L * 0.2);
    gr.addColorStop(0, color); gr.addColorStop(0.5, "#ffffff"); gr.addColorStop(1, color);
    g.beginPath();
    g.moveTo(L * 0.55, 0);
    g.bezierCurveTo(L * 0.35, L * 0.24, -L * 0.25, L * 0.2, -L * 0.42, 0);
    g.bezierCurveTo(-L * 0.25, -L * 0.2, L * 0.35, -L * 0.24, L * 0.55, 0);
    g.fillStyle = gr; g.globalAlpha *= 0.95; g.fill();
    g.shadowBlur = 0;
    g.fillStyle = "#0a1a24"; g.beginPath(); g.arc(L * 0.33, -L * 0.06, Math.max(0.8, L * 0.045), 0, 6.283); g.fill();
    g.restore();
  }

  function sharkShape(g, x, y, h, L, phase, mode) {
    g.save(); g.translate(x, y); g.rotate(-h);
    const beat = Math.sin(phase) * 0.18;
    g.shadowColor = mode === "withdraw" ? "rgba(255,51,85,0.2)" : "rgba(255,51,85,0.9)"; g.shadowBlur = L * 0.6;
    g.globalAlpha = mode === "withdraw" ? 0.55 : 1;
    g.save(); g.translate(-L * 0.42, 0); g.rotate(beat);
    g.beginPath(); g.moveTo(0, 0); g.lineTo(-L * 0.3, L * 0.26); g.lineTo(-L * 0.2, 0); g.lineTo(-L * 0.3, -L * 0.3); g.closePath();
    g.fillStyle = "#6d7f8c"; g.fill(); g.restore();
    const gr = g.createLinearGradient(0, -L * 0.18, 0, L * 0.18);
    gr.addColorStop(0, "#56687a"); gr.addColorStop(0.55, "#c9d3da"); gr.addColorStop(1, "#56687a");
    g.beginPath(); g.moveTo(L * 0.6, 0);
    g.bezierCurveTo(L * 0.4, L * 0.2, -L * 0.3, L * 0.17, -L * 0.45, 0);
    g.bezierCurveTo(-L * 0.3, -L * 0.17, L * 0.4, -L * 0.2, L * 0.6, 0);
    g.fillStyle = gr; g.fill();
    g.shadowBlur = 0;
    // pectoral fins
    g.fillStyle = "#5b6d7c";
    g.beginPath(); g.moveTo(L * 0.1, L * 0.12); g.lineTo(-L * 0.08, L * 0.36); g.lineTo(-L * 0.02, L * 0.12); g.fill();
    g.beginPath(); g.moveTo(L * 0.1, -L * 0.12); g.lineTo(-L * 0.08, -L * 0.36); g.lineTo(-L * 0.02, -L * 0.12); g.fill();
    g.fillStyle = "#ff3355"; g.beginPath(); g.arc(L * 0.42, -L * 0.07, L * 0.035, 0, 6.283); g.fill();
    g.restore();
  }

  let lastDraw = performance.now();
  function draw() {
    requestAnimationFrame(draw);
    if (!cur || $("#dash").hidden) return;
    const now = performance.now(), dt = Math.min(0.1, (now - lastDraw) / 1000); lastDraw = now;
    const f = cur, cv = $("#world"), g = cv.getContext("2d");
    const {s, X, Y, dpr} = worldTransform(cv);
    const u = f.paused || f.done ? 1 : Math.min(1, (now - recvAt) / interval);
    const fancy = $("#tFancy") ? $("#tFancy").checked : true;
    const time = now - t0;
    g.drawImage(background(cv, f.w, f.h), 0, 0);
    if (fancy) caustics(g, cv, time);
    // rocks with shading
    for (const [x, y, r] of f.rocks) {
      const rg = g.createRadialGradient(X(x) - r * s * 0.35, Y(y) - r * s * 0.35, r * s * 0.1, X(x), Y(y), r * s);
      rg.addColorStop(0, "#8b979e"); rg.addColorStop(1, "#2c363c");
      g.fillStyle = rg; g.beginPath(); g.arc(X(x), Y(y), r * s, 0, 6.283); g.fill();
      g.strokeStyle = "rgba(0,0,0,0.4)"; g.lineWidth = 2; g.stroke();
    }
    for (const [x, y, r] of f.food) {
      const rg = g.createRadialGradient(X(x), Y(y), 0, X(x), Y(y), r * s);
      rg.addColorStop(0, "rgba(182,224,92,0.55)"); rg.addColorStop(1, "rgba(182,224,92,0)");
      g.fillStyle = rg; g.beginPath(); g.arc(X(x), Y(y), r * s, 0, 6.283); g.fill();
    }
    // interpolated positions
    const pmap = new Map();
    if (prev) for (const q of prev.fish) pmap.set(q[0], q);
    const pos = f.fish.map((q) => {
      const p = pmap.get(q[0]) || q;
      return [q[0], lerp(p[1], q[1], u), lerp(p[2], q[2], u), lerpAng(p[3], q[3], u), q[4], q[5], q[6], q[7]];
    });
    const sel = pos.find((q) => q[0] === selected);
    if (sel && $("#tCone").checked) {
      const R = f.cfg.vision_range * (1 - f.cfg.turbidity), half = f.cfg.fov_deg / 2 * Math.PI / 180;
      const cg = g.createRadialGradient(X(sel[1]), Y(sel[2]), 0, X(sel[1]), Y(sel[2]), R * s);
      cg.addColorStop(0, "rgba(63,193,201,0.28)"); cg.addColorStop(1, "rgba(63,193,201,0.04)");
      g.fillStyle = cg; g.strokeStyle = "rgba(63,193,201,0.5)"; g.setLineDash([6, 5]);
      g.beginPath(); g.moveTo(X(sel[1]), Y(sel[2]));
      g.arc(X(sel[1]), Y(sel[2]), R * s, -sel[3] - half, -sel[3] + half); g.closePath(); g.fill(); g.stroke(); g.setLineDash([]);
    }
    const ppmap = new Map();
    if (prev) for (const p of prev.preds) ppmap.set(p[0], p);
    const preds = f.preds.map((p) => { const q = ppmap.get(p[0]) || p; return [p[0], lerp(q[1], p[1], u), lerp(q[2], p[2], u), lerpAng(q[3], p[3], u), p[4], p[5]]; });
    if ($("#tPredVision").checked) for (const p of preds) {
      const R = SCHEMA.defaults.pred_vision, half = Math.PI / 2;
      const cg = g.createRadialGradient(X(p[1]), Y(p[2]), 0, X(p[1]), Y(p[2]), R * s);
      cg.addColorStop(0, "rgba(255,51,85,0.16)"); cg.addColorStop(1, "rgba(255,51,85,0)");
      g.fillStyle = cg; g.beginPath(); g.moveTo(X(p[1]), Y(p[2])); g.arc(X(p[1]), Y(p[2]), R * s, -p[3] - half, -p[3] + half); g.closePath(); g.fill();
    }
    // trails that fade toward the tail
    if ($("#tTrails").checked) {
      g.lineCap = "round";
      for (const [k, t] of trails) {
        if (t.length < 2) continue;
        const col = k === selected ? "255,255,255" : "150,200,220";
        for (let i = 1; i < t.length; i++) {
          g.strokeStyle = `rgba(${col},${(i / t.length) * (k === selected ? 0.7 : 0.22)})`;
          g.lineWidth = (k === selected ? 2 : 1.2) * (0.3 + i / t.length);
          g.beginPath(); g.moveTo(X(t[i - 1][0]), Y(t[i - 1][1])); g.lineTo(X(t[i][0]), Y(t[i][1])); g.stroke();
        }
      }
    }
    // pulses (escape waves and captures)
    for (let i = pulses.length - 1; i >= 0; i--) {
      const p = pulses[i], a = (now - p.born) / (p.big ? 1100 : 800);
      if (a >= 1) { pulses.splice(i, 1); continue; }
      g.strokeStyle = p.color; g.globalAlpha = (1 - a) * (p.capture ? 0.9 : 0.55); g.lineWidth = p.capture ? 3 : 1.5;
      g.beginPath(); g.arc(X(p.x), Y(p.y), (p.big ? 5 : 3) * s * a + 3, 0, 6.283); g.stroke(); g.globalAlpha = 1;
    }
    // predator pursuit lines
    for (const p of preds) {
      if (p[4] !== "pursue" || p[5] == null) continue;
      const tq = pos.find((q) => q[0] === p[5]); if (!tq) continue;
      g.strokeStyle = "rgba(255,51,85,0.55)"; g.setLineDash([4, 6]); g.lineDashOffset = -time / 40; g.lineWidth = 1.5;
      g.beginPath(); g.moveTo(X(p[1]), Y(p[2])); g.lineTo(X(tq[1]), Y(tq[2])); g.stroke(); g.setLineDash([]);
    }
    // fish
    const useAct = $("#tAction").checked, useE = $("#tEnergy").checked, lab = $("#tLabels").checked;
    const L = Math.max(9, 1.5 * s);
    for (const q of pos) {
      const [id, x, y, h, v, e, kind, src] = q;
      let col = useAct ? COLORS[kind] || "#ccc" : "#cfe3ec";
      if (useE) col = `hsl(${Math.round(120 * e)},75%,58%)`;
      const phase = time * 0.004 * (1.2 + v) + id * 1.3;
      fishShape(g, X(x), Y(y), h, L, col, phase, v, fancy && PULSE_KINDS.has(kind), false);
      if (src === "fallback") { g.strokeStyle = "rgba(244,162,89,0.7)"; g.lineWidth = 1; g.beginPath(); g.arc(X(x), Y(y), L * 0.7, 0, 6.283); g.stroke(); }
      if (id === selected) {
        const r = L * (0.9 + 0.1 * Math.sin(time * 0.006));
        g.strokeStyle = "#fff"; g.lineWidth = 1.5; g.beginPath(); g.arc(X(x), Y(y), r, 0, 6.283); g.stroke();
      }
      if (lab) { g.fillStyle = "#9fb3bf"; g.font = `${10 * dpr}px sans-serif`; g.fillText(id, X(x) + 6 * dpr, Y(y) - 6 * dpr); }
    }
    for (const p of preds) {
      sharkShape(g, X(p[1]), Y(p[2]), p[3], Math.max(26, 4 * s), time * 0.006 + p[0], p[4]);
      g.fillStyle = "#ff8a9a"; g.font = `600 ${11 * dpr}px sans-serif`; g.fillText(`P${p[0]} · ${p[4]}`, X(p[1]) + 14 * dpr, Y(p[2]) - 12 * dpr);
    }
    // capture particles
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i], a = (now - p.born) / p.life;
      if (a >= 1) { particles.splice(i, 1); continue; }
      p.x += p.vx * dt; p.y += p.vy * dt; p.vx *= 0.96; p.vy *= 0.96;
      g.fillStyle = `rgba(${p.c},${1 - a})`; g.beginPath(); g.arc(X(p.x), Y(p.y), p.r * s, 0, 6.283); g.fill();
    }
    if (fancy) drawBubbles(g, cv, s, dt);
    // HUD
    const k = dpr;
    g.fillStyle = "rgba(4,18,29,0.6)"; g.beginPath(); g.roundRect ? g.roundRect(10 * k, 10 * k, 250 * k, 50 * k, 8 * k) : g.rect(10 * k, 10 * k, 250 * k, 50 * k); g.fill();
    g.fillStyle = "#d8e7ef"; g.font = `600 ${13 * k}px sans-serif`;
    const r = f.row || {};
    g.fillText(`t ${f.t.toFixed(1)} s   alive ${r.alive ?? "–"}   captures ${r.captures ?? 0}`, 20 * k, 31 * k);
    g.fillStyle = "#7d98a8"; g.font = `${11 * k}px sans-serif`;
    g.fillText(`${f.cfg.policy} · ${f.cfg.mode}${f.paused ? " · paused" : ""}${f.done ? " · finished" : ""}`, 20 * k, 49 * k);
  }
  requestAnimationFrame(draw);
  return {onFrame};
})();

/* GraphRAG X-Ray — rendering and interaction.
   One graph shows one index at a time; the comparison rows in the rail switch it.
   Details are disclosed on demand: relationship, entity and community inspectors. */
(function () {
  "use strict";
  const X = window.XR;
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function fail(message) {
    const el = $("stageStatus");
    el.hidden = false;
    el.innerHTML = '<p class="status-title">The graph couldn’t load</p><p>' + esc(message) + '</p><button type="button" class="btn" id="reloadBtn">Reload</button>';
    $("reloadBtn").addEventListener("click", () => location.reload());
  }

  if (!X || !X.model) {
    fail((X && X.error) || "The data files didn’t load. Keep data.js and sim.js next to index.html.");
    return;
  }
  try { init(X.model); } catch (err) { console.error(err); fail(err && err.message ? err.message : String(err)); }

  function init(M) {
    const E = M.edges, N = M.nodes, B = M.B;
    const LEVELS = X.LEVELS.map((l) => l.name);
    const METHOD = { orig: "Original GraphRAG", prop: "Proposed method" };
    const VERDICT = { correct: "Correct", partial: "Incomplete", incorrect: "Incorrect" };
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const FONT = getComputedStyle(document.body).fontFamily;
    const featured = M.queries.filter((q) => q.featured);
    const byName = new Map(N.map((n) => [n.name, n]));
    const incident = N.map(() => []);
    E.forEach((e) => { incident[e.s].push(e.i); incident[e.t].push(e.i); });

    const SMALL = new Set(["of", "to", "the", "and", "in", "at", "a", "for", "on"]);
    const tc = (s) => String(s).toLowerCase().split(" ")
      .map((w, i) => (i > 0 && SMALL.has(w) ? w : w.replace(/^([^a-z]*)([a-z])/, (m, p, c) => p + c.toUpperCase()))).join(" ");
    const pct = (v) => (v * 100).toFixed(1) + "%";
    const int = (v) => Math.round(v).toLocaleString("en-GB");

    /* ---------- glyphs ---------- */
    const svg = (inner, size) => '<svg width="' + (size || 16) + '" height="' + (size || 16) + '" viewBox="0 0 16 16" aria-hidden="true">' + inner + "</svg>";
    const GLYPH = {
      ok: svg('<circle cx="8" cy="8" r="3.5" fill="var(--evid)"/>'),
      in: svg('<circle cx="8" cy="8" r="3" fill="var(--ink-3)"/>'),
      rec: svg('<path d="M4.2 8.3l2.4 2.4 5.2-5.3" fill="none" stroke="var(--kept)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'),
      lost: svg('<path d="M5 5l6 6M11 5l-6 6" stroke="var(--lost)" stroke-width="1.8" stroke-linecap="round"/>'),
      miss: svg('<circle cx="8" cy="8" r="3.25" fill="none" stroke="var(--ink-3)" stroke-width="1.5"/>')
    };
    const VERDICT_GLYPH = {
      correct: GLYPH.rec,
      incorrect: GLYPH.lost,
      partial: svg('<path d="M4.5 8h7" stroke="var(--ink-2)" stroke-width="1.8" stroke-linecap="round"/>')
    };
    const CHEV_RIGHT = '<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M4.5 2.5 8 6l-3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    const CHEV_LEFT = '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3.5 5.5 8 10 12.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    /* ---------- state ---------- */
    const S = { method: "orig", level: 0, q: M.queries.indexOf(featured[0]), custom: null, hover: null, sel: null, hot: null, ctxOpen: false };
    let trans = null;
    const Q = () => S.custom || M.queries[S.q];
    const kindId = (o, kind) => (o && o.kind === kind ? o.id : null);
    const sameTarget = (a, b) => (a && b ? a.kind === b.kind && a.id === b.id && a.rep === b.rep : a === b);

    /* ---------- evidence helpers ---------- */
    function hopEnds(q, k) {
      if (q.featured) return [byName.get(q.hops[k][0]), byName.get(q.hops[k][1])];
      const e = E[q.hopIdx[k]];
      return [N[e.s], N[e.t]];
    }
    const hopLabel = (q, k) => (q.featured && q.hops[k][2] ? q.hops[k][2] : E[q.hopIdx[k]].labels[0]);
    function edgeLabel(i) { const q = Q(), k = q.hopIdx.indexOf(i); return k >= 0 ? hopLabel(q, k) : E[i].labels[0]; }
    function edgeEnds(i) { const q = Q(), k = q.hopIdx.indexOf(i); return k >= 0 ? hopEnds(q, k) : [N[E[i].s], N[E[i].t]]; }
    const hopClass = (h) => (!h.avail ? "lost" : !h.retrieved ? "miss" : h.state === 3 ? "rec" : "ok");
    const HOP_WORD = { ok: "Retrieved", rec: "Recovered", lost: "Lost", miss: "Not retrieved" };
    const stCls = (st) => (st === 0 ? "in" : st === 3 ? "rec" : "lost");
    const ST_SHORT = ["In summary", "Lost · boundary", "Lost · budget", "Recovered"];
    const ST_LONG = ["In the community summary", "Lost at the community boundary", "Lost at the summary budget", "Recovered"];

    /* ---------- colours ---------- */
    const C = {};
    function readColors() {
      const cs = getComputedStyle(document.documentElement);
      ["bg", "ink", "ink-2", "ink-3", "line-2", "lost", "kept", "evid", "edge", "lost-faint", "kept-faint", "node", "node-core", "hull", "hull-2"]
        .forEach((k) => { C[k] = cs.getPropertyValue("--" + k).trim(); });
    }
    readColors();

    /* ---------- canvas geometry ---------- */
    const stage = $("stage"), cv = $("graph"), ctx = cv.getContext("2d");
    let W = 0, H = 0, base = { s: 1, ox: 0, oy: 0 }, view = { k: 1, x: 0, y: 0 };
    const px = new Float64Array(N.length), py = new Float64Array(N.length);
    const hullCache = new Map();

    function resize() {
      const r = stage.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1);
      if (!r.width || !r.height) return;
      W = r.width; H = r.height;
      cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
      cv.style.width = W + "px"; cv.style.height = H + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const b = M.bounds, padX = 56, padTop = 52, padBottom = 56;
      const s = Math.min((W - 2 * padX) / (b.x1 - b.x0), (H - padTop - padBottom) / (b.y1 - b.y0));
      base = { s: s, ox: padX + (W - 2 * padX - (b.x1 - b.x0) * s) / 2 - b.x0 * s, oy: padTop + (H - padTop - padBottom - (b.y1 - b.y0) * s) / 2 - b.y0 * s };
      project();
    }
    function project() {
      for (let i = 0; i < N.length; i++) {
        px[i] = (N[i].x * base.s + base.ox) * view.k + view.x;
        py[i] = (N[i].y * base.s + base.oy) * view.k + view.y;
      }
      hullCache.clear();
      $("zoomFit").disabled = view.k === 1 && view.x === 0 && view.y === 0;
      $("zoomOut").disabled = view.k <= 1;
      $("zoomIn").disabled = view.k >= 8;
    }
    const nodeR = (i) => Math.max(1.3, N[i].rr * base.s * 1.05) * Math.sqrt(view.k);

    function convexHull(pts) {
      pts.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
      if (pts.length < 3) return pts;
      const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
      const lo = [], up = [];
      for (const p of pts) { while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
      for (let i = pts.length - 1; i >= 0; i--) { const p = pts[i]; while (up.length >= 2 && cross(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
      return lo.slice(0, -1).concat(up.slice(0, -1));
    }
    function hulls(L) {
      if (hullCache.has(L)) return hullCache.get(L);
      const out = [], pad = 11 * Math.sqrt(view.k);
      M.levels[L].groups.forEach((g) => {
        const pts = [];
        g.nodes.forEach((i) => { for (let a = 0; a < 12; a++) { const t = (a / 12) * Math.PI * 2; pts.push([px[i] + Math.cos(t) * pad, py[i] + Math.sin(t) * pad]); } });
        const poly = convexHull(pts);
        let minY = Infinity, cx = 0, area = 0;
        poly.forEach((p, j) => { const q = poly[(j + 1) % poly.length]; minY = Math.min(minY, p[1]); cx += p[0]; area += p[0] * q[1] - q[0] * p[1]; });
        out.push({ key: g.key, rep: g.nodes[0], poly: poly, minY: minY, cx: cx / poly.length, area: Math.abs(area) / 2 });
      });
      hullCache.set(L, out);
      return out;
    }
    function inPoly(poly, x, y) {
      let sign = 0;
      for (let j = 0; j < poly.length; j++) {
        const a = poly[j], b = poly[(j + 1) % poly.length], c = (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0]);
        if (c !== 0) { const sg = c > 0 ? 1 : -1; if (!sign) sign = sg; else if (sg !== sign) return false; }
      }
      return true;
    }

    /* ---------- drawing ---------- */
    const ease = (t) => 1 - Math.pow(1 - t, 3);
    const span = (t, a, b) => Math.max(0, Math.min(1, (t - a) / (b - a)));
    // the graph cross-fades in 440 ms; a level change then also re-traces the evidence path
    function progress() { return trans ? ease(Math.min(1, (performance.now() - trans.t0) / 440)) : 1; }
    function beginTransition(kind) {
      trans = reduceMotion ? null : { kind: kind, method: S.method, level: S.level, t0: performance.now(), dur: kind === "level" ? traceMs(Q()) : 440 };
    }
    let raf = 0;
    function requestDraw() { if (!raf) raf = requestAnimationFrame(frame); }
    function frame() {
      raf = 0;
      draw();
      if (trans) { if (performance.now() - trans.t0 >= trans.dur) { trans = null; draw(); } else requestDraw(); }
    }

    /* ---------- evidence trace ----------
       On a level change the question's evidence path is traced again in two passes. First the
       relationships retrieved at the new level are connected, each growing out from an entity
       already reached, so the retrieved context builds up as a tree and every entity reached
       lights up. Then the missed relationships are drawn from the retrieved side: a lost one
       breaks off halfway in red, one whose summary is not read is drawn in grey, and each
       evidence entity left unreached is marked. When everything is retrieved, only the first
       pass runs. */
    const TRACE_LEAD = 320, TRACE_GAP = 240, TRACE_TAIL = 420;
    const hopMs = (n) => Math.max(260, Math.min(440, 2000 / Math.max(1, n)));
    const traceMs = (q) => TRACE_LEAD + q.hopIdx.length * hopMs(q.hopIdx.length) + TRACE_GAP + TRACE_TAIL;
    const litNodes = (ev) => {
      const s = new Set();
      ev.hops.forEach((h) => { if (h.retrieved) { s.add(E[h.i].s); s.add(E[h.i].t); } });
      return s;
    };
    // Order of the trace: retrieved links first, each one starting from an entity already
    // reached (or, when none is, the next link in the path); then the missed links, again
    // starting from the retrieved side where possible.
    function traceSeq(q, ev) {
      const seen = new Set(), seq = [];
      const run = (idx, grow) => {
        const left = idx.slice();
        while (left.length) {
          let k = left.findIndex((j) => { const e = hopEnds(q, j); return seen.has(e[0].i) || seen.has(e[1].i); });
          if (k < 0) k = 0;
          const j = left.splice(k, 1)[0], e = hopEnds(q, j);
          let a = e[0].i, b = e[1].i;
          if (seen.has(b) && !seen.has(a)) { const t = a; a = b; b = t; }
          seq.push({ j: j, a: a, b: b });
          if (grow) { seen.add(a); seen.add(b); }
        }
      };
      const all = ev.hops.map((h, j) => j);
      run(all.filter((j) => ev.hops[j].retrieved), true);
      const nRet = seq.length;
      run(all.filter((j) => !ev.hops[j].retrieved), false);
      return { seq: seq, nRet: nRet };
    }
    function partial(a, b, f, color, width, dash) {
      const x = px[a] + (px[b] - px[a]) * f, y = py[a] + (py[b] - py[a]) * f;
      ctx.strokeStyle = color; ctx.lineWidth = width; ctx.setLineDash(dash || []); ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(px[a], py[a]); ctx.lineTo(x, y); ctx.stroke(); ctx.setLineDash([]);
      return [x, y];
    }
    function drawTrace(q, evFrom, evTo, el, isHot) {
      const hm = hopMs(q.hopIdx.length), lead = ease(Math.min(1, el / TRACE_LEAD));
      const plan = traceSeq(q, evTo), litEnd = litNodes(evTo), litBefore = litNodes(evFrom);
      const lit = new Map(), missed = new Map(), marked = new Set(), rings = [];
      // the previous level's path fades out first
      q.ents.forEach((i) => (litBefore.has(i) ? lit : missed).set(i, 1 - lead));
      if (lead < 1) evFrom.hops.forEach((h) => drawHop(h, 1 - lead, false));
      plan.seq.forEach((s, k) => {
        const h = evTo.hops[s.j], cls = hopClass(h), a = s.a, b = s.b;
        const t0 = TRACE_LEAD + k * hm + (k >= plan.nRet ? TRACE_GAP : 0), p = span(el, t0, t0 + hm), since = el - (t0 + hm);
        if (p <= 0) {
          // not traced yet: a faint guide shows the link that is still to come
          ctx.globalAlpha = 0.35 * lead; partial(a, b, 1, C["ink-3"], 1, [2, 4]); ctx.globalAlpha = 1;
          return;
        }
        if (cls === "lost") {
          const settle = span(p, 0.55, 1);
          if (settle < 1) { ctx.globalAlpha = 1 - settle; partial(a, b, 0.5 * ease(span(p, 0, 0.55)), C.lost, 2.4); }
          if (settle > 0) drawHop(h, ease(settle), isHot(h.i));
        } else if (p < 1) {
          ctx.globalAlpha = 1;
          const tip = partial(a, b, ease(p), cls === "rec" ? C.kept : cls === "ok" ? C.evid : C["ink-3"], 2.7);
          ctx.fillStyle = ctx.strokeStyle; ctx.beginPath(); ctx.arc(tip[0], tip[1], 3, 0, Math.PI * 2); ctx.fill();
        } else drawHop(h, 1, isHot(h.i));
        ctx.globalAlpha = 1;
        if (p < 1) return;
        if (h.retrieved) {
          lit.set(a, 1); lit.set(b, 1);
          if (since < 360) rings.push([b, since / 360, C.evid]);
        } else {
          // this link failed: point out the evidence entities it leaves unreached
          [a, b].forEach((i) => {
            if (litEnd.has(i) || marked.has(i)) return;   // retrieved through another link, or already marked
            marked.add(i);
            missed.set(i, Math.max(missed.get(i) || 0, ease(Math.min(1, since / 300))));
            if (since < 420) rings.push([i, since / 420, C.lost]);
          });
        }
      });
      // one ring marks the moment an entity is retrieved (blue) or found missing (red)
      rings.forEach(([i, s, col]) => {
        ctx.globalAlpha = 0.6 * (1 - s); ctx.strokeStyle = col; ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.arc(px[i], py[i], nodeR(i) + 4 + 9 * ease(s), 0, Math.PI * 2); ctx.stroke();
      });
      ctx.globalAlpha = 1;
      return { lit: (i) => lit.get(i) || 0, missed: (i) => missed.get(i) || 0 };
    }

    const STY = { 0: ["edge", 0.7, null, "butt"], 1: ["lost-faint", 0.8, [3, 3], "butt"], 2: ["lost-faint", 1.1, [0.6, 2.8], "round"], 3: ["kept-faint", 1, null, "butt"] };

    function draw() {
      if (!W) return;
      const k = progress(), q = Q();
      const toL = S.level, toM = S.method, fromL = trans ? trans.level : toL, fromM = trans ? trans.method : toM;
      const to = M.levels[toL][toM], from = M.levels[fromL][fromM];
      const evid = new Set(q.hopIdx), evNodes = new Set(q.ents);
      ctx.clearRect(0, 0, W, H);

      drawHulls(toL, fromL === toL ? 1 : k);
      if (fromL !== toL) drawHulls(fromL, 1 - k);

      for (const st of [0, 2, 1, 3]) {
        const sty = STY[st];
        for (let pass = 0; pass < 3; pass++) {
          const a = pass === 0 ? 1 : pass === 1 ? k : 1 - k;
          if (a < 0.01) continue;
          ctx.beginPath();
          let any = false;
          for (let i = 0; i < E.length; i++) {
            if (evid.has(i)) continue;
            const t = to[i], f = from[i];
            if (pass === 0 ? !(t === f && t === st) : pass === 1 ? !(t !== f && t === st) : !(t !== f && f === st)) continue;
            ctx.moveTo(px[E[i].s], py[E[i].s]); ctx.lineTo(px[E[i].t], py[E[i].t]); any = true;
          }
          if (!any) continue;
          ctx.globalAlpha = a; ctx.strokeStyle = C[sty[0]]; ctx.lineWidth = sty[1]; ctx.setLineDash(sty[2] || []); ctx.lineCap = sty[3];
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 1; ctx.setLineDash([]); ctx.lineCap = "butt";

      const focusNode = kindId(S.hover, "node") != null ? kindId(S.hover, "node") : kindId(S.sel, "node");
      if (focusNode != null) incident[focusNode].forEach((i) => { if (!evid.has(i)) emphEdge(i, to[i], false); });
      const labelled = new Set();
      [kindId(S.sel, "edge"), kindId(S.hover, "edge"), S.hot].forEach((i) => {
        if (i != null && !evid.has(i) && !labelled.has(i)) { labelled.add(i); emphEdge(i, to[i], true); }
      });

      const evTo = M.evaluate(q, toL, toM), evFrom = trans ? M.evaluate(q, fromL, fromM) : evTo;
      const isHot = (i) => S.hot === i || kindId(S.hover, "edge") === i || kindId(S.sel, "edge") === i;
      let marks;
      if (trans && trans.kind === "level" && fromL !== toL) marks = drawTrace(q, evFrom, evTo, performance.now() - trans.t0, isHot);
      else {
        q.hopIdx.forEach((i, j) => {
          const ht = evTo.hops[j], hf = evFrom.hops[j];
          if (hopClass(ht) === hopClass(hf) && ht.state === hf.state) drawHop(ht, 1, isHot(i));
          else { drawHop(hf, 1 - k, false); drawHop(ht, k, isHot(i)); }
        });
        const lf = litNodes(evFrom), lt = litNodes(evTo);
        const lit = (i) => (lf.has(i) ? 1 - k : 0) + (lt.has(i) ? k : 0);
        marks = { lit: lit, missed: (i) => 1 - Math.min(1, lit(i)) };
      }

      drawNodes(evNodes, focusNode, marks.lit, marks.missed);
      drawLabels(q, focusNode);
    }

    function drawHulls(L, alpha) {
      if (alpha < 0.01) return;
      const lv = M.levels[L];
      const active = new Set([S.hover, S.sel].filter((o) => o && o.kind === "group").map((o) => lv.gOf[o.rep]));
      hulls(L).forEach((h) => {
        ctx.beginPath();
        h.poly.forEach((p, j) => (j ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
        ctx.closePath();
        ctx.globalAlpha = alpha;
        ctx.fillStyle = active.has(h.key) ? C["hull-2"] : C.hull;
        ctx.fill();
        if (active.has(h.key)) { ctx.strokeStyle = C["line-2"]; ctx.lineWidth = 1; ctx.lineJoin = "round"; ctx.stroke(); }
      });
      ctx.globalAlpha = 1;
    }

    function edgeText(text, x, y, color) {
      ctx.font = "500 12px " + FONT; ctx.textAlign = "center"; ctx.textBaseline = "bottom";
      const w = ctx.measureText(text).width, tx = Math.min(Math.max(x, w / 2 + 12), W - w / 2 - 12), ty = Math.max(20, y - 10);
      ctx.lineJoin = "round"; ctx.lineWidth = 5; ctx.strokeStyle = C.bg; ctx.strokeText(text, tx, ty);
      ctx.fillStyle = color; ctx.fillText(text, tx, ty);
    }

    function emphEdge(i, st, withLabel) {
      const e = E[i], col = st === 0 ? C["ink-2"] : st === 3 ? C.kept : C.lost;
      ctx.globalAlpha = 1; ctx.strokeStyle = col; ctx.lineWidth = withLabel ? 2 : 1.2;
      ctx.setLineDash(st === 1 ? [4, 3] : st === 2 ? [0.6, 3] : []); ctx.lineCap = st === 2 ? "round" : "butt";
      ctx.beginPath(); ctx.moveTo(px[e.s], py[e.s]); ctx.lineTo(px[e.t], py[e.t]); ctx.stroke();
      ctx.setLineDash([]); ctx.lineCap = "butt";
      if (withLabel) edgeText(edgeLabel(i), (px[e.s] + px[e.t]) / 2, (py[e.s] + py[e.t]) / 2, st === 0 ? C.ink : col);
    }

    function marker(cls, x, y) {
      if (cls === "ok") return;
      ctx.fillStyle = C.bg; ctx.beginPath(); ctx.arc(x, y, 6.5, 0, Math.PI * 2); ctx.fill();
      ctx.lineWidth = 1.7; ctx.lineCap = "round"; ctx.lineJoin = "round";
      ctx.beginPath();
      if (cls === "lost") { ctx.strokeStyle = C.lost; ctx.moveTo(x - 2.8, y - 2.8); ctx.lineTo(x + 2.8, y + 2.8); ctx.moveTo(x + 2.8, y - 2.8); ctx.lineTo(x - 2.8, y + 2.8); }
      else if (cls === "rec") { ctx.strokeStyle = C.kept; ctx.moveTo(x - 3.1, y + 0.2); ctx.lineTo(x - 0.9, y + 2.4); ctx.lineTo(x + 3.2, y - 2.3); }
      else { ctx.strokeStyle = C["ink-3"]; ctx.arc(x, y, 3, 0, Math.PI * 2); }
      ctx.stroke();
    }

    function drawHop(h, alpha, hot) {
      if (alpha < 0.01) return;
      const e = E[h.i], x1 = px[e.s], y1 = py[e.s], x2 = px[e.t], y2 = py[e.t], cls = hopClass(h);
      ctx.globalAlpha = alpha; ctx.lineCap = "round";
      if (cls === "lost") { ctx.strokeStyle = C.lost; ctx.lineWidth = hot ? 3 : 2.2; ctx.setLineDash(h.state === 2 ? [0.6, 4.4] : [6, 4.5]); }
      else if (cls === "miss") { ctx.strokeStyle = C["ink-3"]; ctx.lineWidth = hot ? 3 : 2.2; ctx.setLineDash([]); }
      else { ctx.strokeStyle = cls === "rec" ? C.kept : C.evid; ctx.lineWidth = hot ? 3.6 : 2.7; ctx.setLineDash([]); }
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); ctx.setLineDash([]);
      marker(cls, (x1 + x2) / 2, (y1 + y2) / 2);
      if (hot) edgeText(edgeLabel(h.i), (x1 + x2) / 2, (y1 + y2) / 2, cls === "lost" ? C.lost : cls === "rec" ? C.kept : C.ink);
      ctx.globalAlpha = 1; ctx.lineCap = "butt";
    }

    // lit(i): how far evidence entity i is shown as retrieved (filled) rather than hollow;
    // missed(i): how far it carries the dashed red mark of an entity left unretrieved
    function drawNodes(evNodes, focusNode, lit, missed) {
      const strong = new Set();
      if (focusNode != null) incident[focusNode].forEach((i) => { strong.add(E[i].s); strong.add(E[i].t); });
      ["node", "node-core"].forEach((tok) => {
        ctx.fillStyle = C[tok]; ctx.beginPath();
        for (let i = 0; i < N.length; i++) {
          if (evNodes.has(i)) continue;
          if ((tok === "node-core") !== (N[i].core || strong.has(i))) continue;
          const r = nodeR(i);
          ctx.moveTo(px[i] + r, py[i]); ctx.arc(px[i], py[i], r, 0, Math.PI * 2);
        }
        ctx.fill();
      });
      evNodes.forEach((i) => {
        const r = nodeR(i) + 1.6, on = Math.min(1, lit(i));
        ctx.globalAlpha = 1; ctx.fillStyle = C.bg; ctx.beginPath(); ctx.arc(px[i], py[i], r + 2, 0, Math.PI * 2); ctx.fill();
        if (on > 0.01) { ctx.globalAlpha = on; ctx.fillStyle = C.evid; ctx.beginPath(); ctx.arc(px[i], py[i], r, 0, Math.PI * 2); ctx.fill(); }
        if (on < 0.99) {
          ctx.globalAlpha = 1 - on; ctx.strokeStyle = C.evid; ctx.lineWidth = 1.6;
          ctx.beginPath(); ctx.arc(px[i], py[i], r - 0.8, 0, Math.PI * 2); ctx.stroke();
        }
        const m = missed(i);
        if (m > 0.01) {
          ctx.globalAlpha = 0.9 * m; ctx.strokeStyle = C.lost; ctx.lineWidth = 1.2; ctx.setLineDash([2.5, 2.5]);
          ctx.beginPath(); ctx.arc(px[i], py[i], r + 3.5, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
        }
      });
      ctx.globalAlpha = 1;
      if (focusNode != null) {
        ctx.strokeStyle = C.ink; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(px[focusNode], py[focusNode], nodeR(focusNode) + 4.5, 0, Math.PI * 2); ctx.stroke();
      }
    }

    function drawLabels(q, focusNode) {
      const boxes = [];
      const clash = (box) => boxes.some((b) => box[0] < b[0] + b[2] && box[0] + box[2] > b[0] && box[1] < b[1] + b[3] && box[1] + box[3] > b[1]);
      const put = (i, text, weight, required) => {
        ctx.font = weight + " 12px " + FONT;
        const w = ctx.measureText(text).width, r = nodeR(i) + 7, x0 = px[i], y0 = py[i];
        // right, left, above, below — the first free slot wins; evidence labels always render
        const slots = [[x0 + r, y0], [x0 - r - w, y0], [x0 - w / 2, y0 - r - 4], [x0 - w / 2, y0 + r + 4]]
          .map((p) => [Math.min(Math.max(p[0], 10), W - w - 10), Math.min(Math.max(p[1], 14), H - 14)]);
        let pick = slots.find((p) => !clash([p[0] - 3, p[1] - 9, w + 6, 18]));
        if (!pick) { if (!required) return; pick = slots[0]; }
        boxes.push([pick[0] - 3, pick[1] - 9, w + 6, 18]);
        ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.lineJoin = "round";
        ctx.lineWidth = 4.5; ctx.strokeStyle = C.bg; ctx.strokeText(text, pick[0], pick[1]);
        ctx.fillStyle = C.ink; ctx.fillText(text, pick[0], pick[1]);
      };
      q.ents.forEach((i) => boxes.push([px[i] - nodeR(i) - 3, py[i] - nodeR(i) - 3, 2 * nodeR(i) + 6, 2 * nodeR(i) + 6]));
      q.ents.forEach((i) => put(i, tc(N[i].short), "500", true));
      if (focusNode != null && !q.ents.includes(focusNode)) put(focusNode, tc(N[focusNode].name), "600", true);

      const lv = M.levels[S.level], drawn = new Set();
      [S.sel, S.hover].forEach((o) => {
        if (!o || o.kind !== "group") return;
        const key = lv.gOf[o.rep];
        if (drawn.has(key)) return;
        drawn.add(key);
        const h = hulls(S.level).find((x) => x.key === key);
        if (!h) return;
        const meta = M.groupMeta(S.level, key), text = "Community " + meta.id + " · " + meta.title;
        ctx.font = "500 12px " + FONT; ctx.textAlign = "center"; ctx.textBaseline = "bottom";
        const w = ctx.measureText(text).width, x = Math.min(Math.max(h.cx, w / 2 + 12), W - w / 2 - 12), y = Math.max(20, h.minY - 4);
        ctx.lineWidth = 5; ctx.strokeStyle = C.bg; ctx.strokeText(text, x, y);
        ctx.fillStyle = C["ink-2"]; ctx.fillText(text, x, y);
      });
    }

    /* ---------- hit testing ---------- */
    function hitTest(mx, my) {
      let best = null, bd = Infinity;
      for (let i = 0; i < N.length; i++) {
        const dx = px[i] - mx, dy = py[i] - my, d2 = dx * dx + dy * dy, lim = Math.max(8, nodeR(i) + 4);
        if (d2 < lim * lim && d2 < bd) { bd = d2; best = i; }
      }
      if (best != null) return { kind: "node", id: best };
      const segD2 = (i) => {
        const e = E[i], x1 = px[e.s], y1 = py[e.s], dx = px[e.t] - x1, dy = py[e.t] - y1, l2 = dx * dx + dy * dy || 1;
        const t = Math.max(0, Math.min(1, ((mx - x1) * dx + (my - y1) * dy) / l2)), ex = x1 + t * dx - mx, ey = y1 + t * dy - my;
        return ex * ex + ey * ey;
      };
      let be = null, bde = Infinity;
      Q().hopIdx.forEach((i) => { const d = segD2(i); if (d < 49 && d < bde) { bde = d; be = i; } });
      if (be == null) for (let i = 0; i < E.length; i++) { const d = segD2(i); if (d < 12 && d < bde) { bde = d; be = i; } }
      if (be != null) return { kind: "edge", id: be };
      const hit = hulls(S.level).filter((h) => inPoly(h.poly, mx, my)).sort((a, b) => a.area - b.area)[0];
      return hit ? { kind: "group", rep: hit.rep, id: hit.key } : null;
    }

    /* ---------- rail: comparison ---------- */
    const cmpRows = { orig: $("mOrig"), prop: $("mProp") };
    function renderCompare() {
      const q = Q();
      ["orig", "prop"].forEach((m) => {
        const el = cmpRows[m], ev = M.evaluate(q, S.level, m);
        el.setAttribute("aria-checked", String(S.method === m));
        el.tabIndex = S.method === m ? 0 : -1;
        const v = el.querySelector(".verdict");
        v.className = "verdict " + ev.outcome;
        v.innerHTML = VERDICT_GLYPH[ev.outcome] + VERDICT[ev.outcome];
        const meter = el.querySelector(".meter");
        if (meter.children.length !== ev.n) meter.innerHTML = "<i></i>".repeat(ev.n);
        ev.hops.forEach((h, j) => { meter.children[j].className = hopClass(h); });
        el.querySelector(".m-caption").textContent = ev.retrieved + " of " + ev.n + " evidence relationships retrieved";
        el.setAttribute("aria-label", METHOD[m] + ": " + VERDICT[ev.outcome] + ", " + ev.retrieved + " of " + ev.n + " evidence relationships retrieved");
      });
    }

    /* ---------- typed questions ---------- */
    const CUSTOM_NOTE = "Evidence for a typed question is the shortest relationship chain between the entities it names. " +
      "Loss, retrieval and judging then run exactly as they do for the benchmark questions.";
    const ename = (m) => tc(m.short || m.name);
    function customMeta(q) {
      const n = q.hopIdx.length;
      if (q.shape === "star") return q.id + " · " + ename(q.matched[0]) + " · its " + n + " most-cited relationships as evidence";
      return q.id + " · " + q.matched.map(ename).join(" → ") + " · " + n + " evidence relationship" + (n === 1 ? "" : "s");
    }
    function customExpected(q) {
      const n = q.hopIdx.length;
      let s = q.shape === "star"
        ? "Evidence needed: the " + n + " strongest relationships of " + ename(q.matched[0]) + "."
        : "Evidence needed: the " + n + "-relationship chain linking " + q.matched.map(ename).join(" → ") + ".";
      if (q.unlinked && q.unlinked.length) s += " No path connects " + q.unlinked.map((u) => tc(u[0]) + " and " + tc(u[1])).join("; ") + ".";
      return s;
    }
    function customAnswer(q, ev) {
      const got = ev.hops.filter((h) => h.retrieved), miss = ev.n - got.length;
      if (!got.length) return "The retrieved summaries contain none of the " + ev.n + " relationships this question needs, so there is nothing in the context to answer from.";
      const facts = got.map((h) => { const en = edgeEnds(h.i); return tc(en[0].short) + " " + edgeLabel(h.i) + " " + tc(en[1].short); });
      let s = "From the retrieved summaries: " + facts.join("; ") + ".";
      if (!miss) s += q.shape === "chain" ? " The chain is complete." : "";
      else if (q.shape === "chain") s += " " + miss + " link" + (miss > 1 ? "s" : "") + " in the chain " + (miss > 1 ? "are" : "is") + " missing from the context, so the connection can't be completed.";
      else s += " " + miss + " of its relationships " + (miss > 1 ? "are" : "is") + " missing from the context.";
      return s;
    }

    /* ---------- rail: evidence (default) ---------- */
    function evidenceHTML() {
      const q = Q(), ev = M.evaluate(q, S.level, S.method), lv = M.levels[S.level];
      let h = '<section class="block"><h3 class="label">Answer · ' + METHOD[S.method] + '</h3><p class="answer">' +
        esc(q.custom ? customAnswer(q, ev) : q.answers[ev.outcome]) + '</p><p class="expected">' +
        (q.custom ? esc(customExpected(q)) : "Expected: " + esc(q.gold)) + "</p></section>";
      h += '<section class="block"><h3 class="label">Evidence path</h3><ol class="hops">';
      ev.hops.forEach((hop, j) => {
        const ends = hopEnds(q, j), cls = hopClass(hop);
        h += '<li><button type="button" class="hop" data-action="edge" data-id="' + hop.i + '" data-hot="' + hop.i + '">' +
          '<span class="glyph">' + GLYPH[cls] + "</span><span>" +
          '<span class="hop-ents">' + esc(tc(ends[0].short)) + '<span class="arr">→</span>' + esc(tc(ends[1].short)) + "</span>" +
          '<span class="hop-rel">' + esc(hopLabel(q, j)) + "</span></span>" +
          '<span class="hop-state ' + cls + '">' + HOP_WORD[cls] + "</span></button></li>";
      });
      h += "</ol>" + (q.custom ? '<p class="expected">' + esc(CUSTOM_NOTE) + "</p>" : "") +
        '</section><section class="block"><button type="button" class="disclosure" data-action="toggle-ctx" aria-expanded="' + S.ctxOpen + '"><span>' +
        ev.ranked.length + " community " + (ev.ranked.length === 1 ? "summary" : "summaries") + " retrieved</span>" + CHEV_RIGHT + "</button>";
      if (S.ctxOpen) {
        h += '<ul class="rows">';
        ev.ranked.forEach((key) => {
          const g = lv.groups.get(key), meta = M.groupMeta(S.level, key);
          const n = ev.hops.filter((x) => x.retrieved && x.host === key).length;
          h += '<li><button type="button" class="row" data-action="group" data-rep="' + g.nodes[0] + '"><span class="id">' + meta.id + '</span><span class="t">' +
            esc(meta.title) + '</span><span class="m">' + (n ? n + " evidence" : "no evidence") + "</span></button></li>";
        });
        h += "</ul>";
      }
      return h + "</section>";
    }

    /* ---------- rail: inspectors ---------- */
    function budgetRank(i, L) {
      const lv = M.levels[L], g = lv.groups.get(lv.gOf[E[i].s]);
      const sorted = g.intra.slice().sort((x, y) => E[y].cd - E[x].cd || E[y].w - E[x].w || x - y);
      return { g: g, rank: sorted.indexOf(i) + 1, total: sorted.length, admitted: sorted.filter((j) => lv.orig[j] === 0).length };
    }
    function reasonOrig(i, L) {
      const lv = M.levels[L], e = E[i], st = lv.orig[i], ma = M.groupMeta(L, lv.gOf[e.s]), mb = M.groupMeta(L, lv.gOf[e.t]);
      if (st === 1) return "Its entities are in different communities — " + ma.id + " (" + ma.title + ") and " + mb.id + " (" + mb.title + "). Each summary only describes relationships inside its own community.";
      const r = budgetRank(i, L);
      if (st === 2) return "Community " + ma.id + " needs " + int(r.g.need) + " tokens of input against an " + int(B) + "-token budget. Relationships are added in order of combined degree; this one ranks " + r.rank + " of " + r.total + ", and the budget ran out after " + r.admitted + ".";
      return "Both entities are in community " + ma.id + " (" + ma.title + "). It ranks " + r.rank + " of " + r.total + " and fits within the summary budget.";
    }
    function reasonProp(i, L) {
      const lv = M.levels[L], e = E[i], sp = lv.prop[i], ga = lv.gOf[e.s], gb = lv.gOf[e.t];
      if (sp === 0) return "Kept in the summary, as in the original index.";
      if (sp === 3) {
        if (ga !== gb) {
          const hosts = (lv.bridgeHosts.get(i) || []).map((key) => M.groupMeta(L, key).id);
          return "Written as a bridge record into the summary of community " + hosts.join(" and ") + ", so it survives the community boundary.";
        }
        return "Kept as a compact fact: full descriptions stop at 80% of the budget, and the remaining relationships are written as short facts.";
      }
      if (sp === 1) return e.w < 4
        ? "Still lost. Bridge records are only written for cross-community relationships of weight 4 or more; this one has weight " + e.w + "."
        : "Still lost. Both communities spent their bridge allowance on higher-priority relationships.";
      return "Still lost. Even as compact facts, community " + M.groupMeta(L, ga).id + "’s relationships exceed the budget.";
    }
    const stateLine = (who, st) => '<div class="state-line"><span class="who">' + who + '</span><span class="glyph">' + GLYPH[stCls(st)] +
      '</span><span class="st-word ' + stCls(st) + '">' + ST_LONG[st] + "</span></div>";
    const stChip = (st) => '<span class="st ' + stCls(st) + '"><i></i>' + ST_SHORT[st] + "</span>";

    function groupRow(L, key) {
      const g = M.levels[L].groups.get(key), meta = M.groupMeta(L, key);
      return '<li><button type="button" class="row" data-action="group" data-rep="' + g.nodes[0] + '"><span class="id">' + meta.id + '</span><span class="t">' +
        esc(meta.title) + '</span><span class="m">' + g.nodes.length + " entities</span></button></li>";
    }
    function entityRow(i) {
      const n = N[i], meta = M.groupMeta(S.level, M.levels[S.level].gOf[i]);
      return '<li><button type="button" class="row" data-action="node" data-id="' + i + '"><span class="id">' + meta.id + '</span><span class="t">' +
        esc(tc(n.name)) + '</span><span class="m">' + incident[i].length + " relationships</span></button></li>";
    }

    function edgeHTML(i) {
      const L = S.level, lv = M.levels[L], e = E[i], ends = edgeEnds(i), isEv = Q().hopIdx.includes(i);
      let h = '<p class="i-kicker">' + (isEv ? "Evidence relationship" : "Relationship") + '</p><h2 class="i-title">' + esc(tc(ends[0].name)) +
        '<span class="arr">→</span>' + esc(tc(ends[1].name)) + '</h2><p class="i-sub">' + esc(edgeLabel(i)) + "</p>" +
        '<p class="i-meta">Weight ' + e.w + " · " + e.tok + " tokens · combined degree " + e.cd + "</p>";
      h += '<section class="i-section"><h3 class="label">At ' + LEVELS[L].toLowerCase() + " level</h3>" +
        stateLine("Original", lv.orig[i]) + '<p class="i-p">' + esc(reasonOrig(i, L)) + "</p>" +
        stateLine("Proposed", lv.prop[i]) + '<p class="i-p">' + esc(reasonProp(i, L)) + "</p></section>";
      h += '<section class="i-section"><h3 class="label">Across index levels</h3><table class="levels-table"><thead><tr><th>Level</th><th>Original</th><th>Proposed</th></tr></thead><tbody>';
      for (let l = 0; l < 4; l++) {
        h += "<tr" + (l === L ? ' class="cur"' : "") + '><td><button type="button" class="lvl-link" data-action="level" data-level="' + l + '">' + LEVELS[l] +
          "</button></td><td>" + stChip(M.levels[l].orig[i]) + "</td><td>" + stChip(M.levels[l].prop[i]) + "</td></tr>";
      }
      h += '</tbody></table></section><section class="i-section"><h3 class="label">Entities</h3><ul class="rows">' + entityRow(E[i].s) + entityRow(E[i].t) + "</ul></section>";
      return h;
    }

    function nodeHTML(i) {
      const n = N[i], L = S.level, lv = M.levels[L], inc = incident[i];
      const o = inc.filter((j) => lv.orig[j] === 0).length, p = inc.filter((j) => lv.prop[j] === 0 || lv.prop[j] === 3).length;
      let h = '<p class="i-kicker">' + esc(tc(n.type)) + '</p><h2 class="i-title">' + esc(tc(n.name)) + "</h2>" +
        '<ul class="rows" style="margin-top:12px">' + groupRow(L, lv.gOf[i]) + "</ul>";
      h += '<section class="i-section"><h3 class="label">Its relationships at ' + LEVELS[L].toLowerCase() + ' level</h3><div class="kv">' +
        '<span class="h">Index</span><span class="h n">In a summary</span><span class="h n">Lost</span>' +
        "<span>Original</span><span class=\"n\">" + o + " of " + inc.length + '</span><span class="n">' + (inc.length - o) + "</span>" +
        "<span>Proposed</span><span class=\"n\">" + p + " of " + inc.length + '</span><span class="n">' + (inc.length - p) + "</span></div></section>";
      const lost = inc.filter((j) => lv.orig[j] !== 0).sort((x, y) => E[y].w - E[x].w || x - y);
      if (lost.length) {
        h += '<section class="i-section"><h3 class="label">Lost in the original index</h3><ul class="rows">';
        lost.slice(0, 8).forEach((j) => {
          const other = E[j].s === i ? E[j].t : E[j].s, sp = lv.prop[j];
          h += '<li><button type="button" class="row row-edge" data-action="edge" data-id="' + j + '" data-hot="' + j + '"><span class="glyph">' + GLYPH[stCls(sp)] +
            '</span><span class="t">' + esc(tc(N[other].short)) + ' <span class="sub">· ' + esc(E[j].labels[0]) + '</span></span><span class="m ' + stCls(sp) + '">' +
            (sp === 3 ? "Recovered" : sp === 0 ? "In summary" : "Still lost") + "</span></button></li>";
        });
        if (lost.length > 8) h += '<li class="more">' + (lost.length - 8) + " more</li>";
        h += "</ul></section>";
      }
      return h;
    }

    function groupHTML(sel) {
      const L = S.level, lv = M.levels[L], key = lv.gOf[sel.rep], g = lv.groups.get(key), meta = M.groupMeta(L, key);
      const cO = [0, 0, 0, 0], cP = [0, 0, 0, 0];
      g.intra.forEach((j) => { cO[lv.orig[j]]++; cP[lv.prop[j]]++; });
      const bridged = g.cross.filter((j) => (lv.bridgeHosts.get(j) || []).includes(key)).length;
      const scale = Math.max(g.need, B), over = g.need > B;
      let h = '<p class="i-kicker">Community ' + meta.id + " · " + LEVELS[L] + ' level</p><h2 class="i-title">' + esc(meta.title) + '</h2><p class="i-p">' + esc(meta.summary) + "</p>";
      h += '<section class="i-section"><h3 class="label">Summary input</h3><div class="budget"><b style="width:' + (Math.min(g.need, B) / scale * 100).toFixed(2) + '%"></b>' +
        (over ? '<s style="left:' + (B / scale * 100).toFixed(2) + "%;width:" + ((g.need - B) / scale * 100).toFixed(2) + '%"></s><em style="left:' + (B / scale * 100).toFixed(2) + '%"></em>' : "") +
        '</div><div class="budget-caption"><span class="' + (over ? "over" : "") + '">' + int(g.need) + " tokens needed</span><span>" + int(B) + "-token budget</span></div></section>";
      const row = (label, a, b) => "<span>" + label + '</span><span class="n">' + int(a) + '</span><span class="n">' + int(b) + "</span>";
      h += '<section class="i-section"><h3 class="label">Relationships</h3><div class="kv"><span class="h"></span><span class="h n">Original</span><span class="h n">Proposed</span>' +
        row("In the summary", cO[0], cP[0] + cP[3]) + row("Dropped at the budget", cO[2], cP[2]) + row("Crossing the boundary, not described", g.cross.length, g.cross.length - bridged) +
        '</div><p class="i-p">' + g.nodes.length + " entities · " + g.intra.length + " relationships inside this community</p></section>";
      const top = g.nodes.slice().sort((a, b) => N[b].deg - N[a].deg).slice(0, 5);
      h += '<section class="i-section"><h3 class="label">Most connected entities</h3><ul class="rows">' + top.map(entityRow).join("") + "</ul></section>";
      if (L < 3) {
        const up = M.levels[L + 1].gOf[sel.rep], upMeta = M.groupMeta(L + 1, up);
        h += '<section class="i-section"><h3 class="label">At ' + LEVELS[L + 1].toLowerCase() + ' level</h3><ul class="rows"><li><button type="button" class="row" data-action="group-up" data-rep="' +
          sel.rep + '"><span class="id">' + upMeta.id + '</span><span class="t">Merges into ' + esc(upMeta.title) + '</span><span class="m">' + CHEV_RIGHT + "</span></button></li></ul></section>";
      }
      return h;
    }

    function renderContext() {
      const el = $("context"), sel = S.sel;
      if (!sel) { el.innerHTML = evidenceHTML(); return; }
      const back = '<button type="button" class="back" data-action="back">' + CHEV_LEFT + "Evidence path</button>";
      el.innerHTML = back + (sel.kind === "edge" ? edgeHTML(sel.id) : sel.kind === "node" ? nodeHTML(sel.id) : groupHTML(sel));
    }

    /* ---------- metrics, level, question ---------- */
    const METRICS = [["retention", "Relationships retained"], ["retrieval", "Evidence retrieved"], ["correct", "Answers correct"]];
    const metricCells = METRICS.map((m) => {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td>" + m[1] + '</td><td class="o"></td><td class="p"></td><td class="d"></td>';
      $("metricsBody").appendChild(tr);
      return { key: m[0], o: tr.children[1], p: tr.children[2], d: tr.children[3] };
    });
    $("metricsFoot").textContent = M.queries.length + " questions at the selected index level";

    function tween(el, value) {
      const from = el._v == null ? value : el._v;
      el._v = value;
      if (reduceMotion || Math.abs(from - value) < 1e-9) { el.textContent = pct(value); return; }
      const t0 = performance.now();
      const step = (now) => {
        const t = Math.min(1, (now - t0) / 380), e = 1 - Math.pow(1 - t, 3);
        el.textContent = pct(from + (value - from) * e);
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }
    function renderMetrics() {
      const m = M.metrics[S.level];
      metricCells.forEach((c) => {
        const o = m.orig[c.key], p = m.prop[c.key], d = (p - o) * 100;
        tween(c.o, o); tween(c.p, p);
        c.d.textContent = (d > 0.05 ? "+" : d < -0.05 ? "−" : "±") + Math.abs(d).toFixed(1) + " pts";
        c.d.className = "d" + (d < -0.05 ? " neg" : "");
      });
    }

    const stepper = $("stepper");
    function renderLevel() {
      const s = M.levels[S.level].stats, p = (S.level / 3) * 100;
      const count = s.groups === 1 ? "1 community" : s.groups + " communities";
      let budget;
      if (s.over === 0) budget = (s.groups === 1 ? "its summary fits" : "every summary fits") + " the " + int(B) + "-token budget";
      else if (s.over === s.groups) budget = (s.groups === 1 ? "its summary exceeds" : "every summary exceeds") + " the " + int(B) + "-token budget";
      else budget = s.over + " of " + s.groups + " summaries exceed the " + int(B) + "-token budget";
      $("levelDesc").textContent = count + " · " + budget;
      $("thumb").style.left = p + "%";
      $("trackFill").style.width = p + "%";
      stepper.querySelectorAll(".stop").forEach((el, i) => el.classList.toggle("on", i <= S.level));
      $("stopLabels").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(+b.dataset.level === S.level)));
      stepper.setAttribute("aria-valuenow", String(S.level));
      stepper.setAttribute("aria-valuetext", LEVELS[S.level] + " level, " + count);
    }

    const qTrigger = $("qTrigger"), qMenu = $("qMenu"), qList = $("qList");
    featured.forEach((q) => {
      const b = document.createElement("button");
      b.type = "button"; b.setAttribute("role", "option"); b.dataset.q = String(M.queries.indexOf(q));
      b.innerHTML = '<span class="mi-text">' + esc(q.text) + '</span><span class="mi-meta">' + q.id + " · " + esc(q.type) + "</span>";
      qList.appendChild(b);
    });
    function renderQuestion() {
      const q = Q();
      $("qText").textContent = q.text;
      $("qMeta").textContent = q.custom ? customMeta(q) : q.id + " · " + q.type + " · " + (featured.indexOf(q) + 1) + " of " + featured.length;
      [...qList.children].forEach((b) => b.setAttribute("aria-selected", String(!S.custom && +b.dataset.q === S.q)));
    }

    function renderStage() {
      $("stageLabel").textContent = METHOD[S.method] + " · " + LEVELS[S.level] + " level";
      const s = M.levels[S.level].stats[S.method];
      cv.setAttribute("aria-label", "Knowledge graph under " + METHOD[S.method] + " at " + LEVELS[S.level].toLowerCase() + " level: " + int(s.lost) + " of " + int(E.length) + " relationships unavailable in community summaries.");
    }

    function renderAll() { renderQuestion(); renderCompare(); renderContext(); renderMetrics(); renderLevel(); renderStage(); requestDraw(); }

    /* ---------- actions ---------- */
    function setMethod(m) {
      if (m === S.method) return;
      beginTransition("method"); S.method = m;
      renderCompare(); renderContext(); renderStage(); requestDraw();
    }
    function setLevel(L) {
      L = Math.max(0, Math.min(3, L));
      if (L === S.level) return;
      beginTransition("level"); S.level = L;
      renderCompare(); renderContext(); renderMetrics(); renderLevel(); renderStage(); requestDraw();
    }
    function setQuery(i) {
      if (i === S.q && !S.custom) return;
      S.custom = null; S.q = i; S.sel = null; S.hot = null; S.ctxOpen = false;
      renderAll();
    }
    function setCustom(q) {
      S.custom = q; S.sel = null; S.hot = null; S.ctxOpen = false;
      renderAll();
    }
    function select(target) {
      if (target && target.kind === "group" && S.sel && S.sel.kind === "group" && M.levels[S.level].gOf[S.sel.rep] === M.levels[S.level].gOf[target.rep]) target = null;
      else if (sameTarget(target, S.sel)) target = null;
      S.sel = target; S.hot = null;
      renderContext(); requestDraw();
      if (window.innerWidth <= 1120 && target) $("rail").scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
    }

    /* ---------- events: graph ---------- */
    let drag = null;
    const local = (ev) => { const r = cv.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; };
    cv.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      cv.setPointerCapture(ev.pointerId);
      drag = { x0: ev.clientX, y0: ev.clientY, vx: view.x, vy: view.y, moved: false };
    });
    cv.addEventListener("pointermove", (ev) => {
      if (drag) {
        const dx = ev.clientX - drag.x0, dy = ev.clientY - drag.y0;
        if (!drag.moved && dx * dx + dy * dy > 16) { drag.moved = true; cv.classList.add("panning"); S.hover = null; }
        if (drag.moved) { view.x = drag.vx + dx; view.y = drag.vy + dy; project(); requestDraw(); return; }
      }
      const [mx, my] = local(ev), hit = hitTest(mx, my);
      if (!sameTarget(hit, S.hover)) { S.hover = hit; cv.style.cursor = hit ? "pointer" : ""; requestDraw(); }
    });
    cv.addEventListener("pointerup", (ev) => {
      const moved = drag && drag.moved;
      drag = null; cv.classList.remove("panning");
      if (moved) return;
      const [mx, my] = local(ev);
      select(hitTest(mx, my));
    });
    cv.addEventListener("pointercancel", () => { drag = null; cv.classList.remove("panning"); });
    cv.addEventListener("pointerleave", () => { if (!drag && S.hover) { S.hover = null; requestDraw(); } });

    function targetView(mx, my, f) {
      const k = Math.max(1, Math.min(8, view.k * f)), r = k / view.k;
      if (k === 1) return { k: 1, x: 0, y: 0 };
      return { k: k, x: mx - (mx - view.x) * r, y: my - (my - view.y) * r };
    }
    function animateView(target) {
      if (reduceMotion) { view = target; project(); requestDraw(); return; }
      const start = { k: view.k, x: view.x, y: view.y }, t0 = performance.now();
      const step = (now) => {
        const t = Math.min(1, (now - t0) / 300), e = 1 - Math.pow(1 - t, 3);
        view = t < 1 ? { k: start.k + (target.k - start.k) * e, x: start.x + (target.x - start.x) * e, y: start.y + (target.y - start.y) * e } : target;
        project(); draw();
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    }
    cv.addEventListener("wheel", (ev) => {
      if (!(ev.ctrlKey || ev.metaKey)) return;
      ev.preventDefault();
      const [mx, my] = local(ev);
      view = targetView(mx, my, Math.exp(-ev.deltaY * 0.01));
      project(); requestDraw();
    }, { passive: false });
    $("zoomIn").addEventListener("click", () => animateView(targetView(W / 2, H / 2, 1.6)));
    $("zoomOut").addEventListener("click", () => animateView(targetView(W / 2, H / 2, 1 / 1.6)));
    $("zoomFit").addEventListener("click", () => animateView({ k: 1, x: 0, y: 0 }));

    /* ---------- events: rail ---------- */
    const rail = $("rail");
    rail.addEventListener("click", (ev) => {
      const b = ev.target instanceof Element ? ev.target.closest("[data-action]") : null;
      if (!b) return;
      const a = b.dataset.action;
      if (a === "method") setMethod(b.dataset.method);
      else if (a === "edge") select({ kind: "edge", id: +b.dataset.id });
      else if (a === "node") select({ kind: "node", id: +b.dataset.id });
      else if (a === "group") select({ kind: "group", rep: +b.dataset.rep, id: null });
      else if (a === "group-up") { const rep = +b.dataset.rep; setLevel(S.level + 1); S.sel = { kind: "group", rep: rep, id: null }; renderContext(); requestDraw(); }
      else if (a === "level") setLevel(+b.dataset.level);
      else if (a === "back") { S.sel = null; S.hot = null; renderContext(); requestDraw(); }
      else if (a === "toggle-ctx") { S.ctxOpen = !S.ctxOpen; renderContext(); }
    });
    rail.addEventListener("mouseover", (ev) => {
      const b = ev.target instanceof Element ? ev.target.closest("[data-hot]") : null, i = b ? +b.dataset.hot : null;
      if (i !== S.hot) { S.hot = i; requestDraw(); }
    });
    rail.addEventListener("mouseleave", () => { if (S.hot != null) { S.hot = null; requestDraw(); } });
    $("compare").addEventListener("keydown", (ev) => {
      if (!["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(ev.key)) return;
      ev.preventDefault();
      const m = S.method === "orig" ? "prop" : "orig";
      setMethod(m); cmpRows[m].focus();
    });

    /* ---------- events: level control ---------- */
    function levelFromPointer(ev) {
      const r = stepper.querySelector(".stepper-inner").getBoundingClientRect();
      return Math.round(Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width)) * 3);
    }
    let stepDrag = false;
    stepper.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      stepDrag = true; stepper.setPointerCapture(ev.pointerId); stepper.focus({ preventScroll: true });
      setLevel(levelFromPointer(ev));
    });
    stepper.addEventListener("pointermove", (ev) => { if (stepDrag) setLevel(levelFromPointer(ev)); });
    stepper.addEventListener("pointerup", () => { stepDrag = false; });
    stepper.addEventListener("keydown", (ev) => {
      const map = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 };
      if (ev.key in map) { ev.preventDefault(); setLevel(S.level + map[ev.key]); }
      else if (ev.key === "Home") { ev.preventDefault(); setLevel(0); }
      else if (ev.key === "End") { ev.preventDefault(); setLevel(3); }
    });

    /* ---------- events: menus ---------- */
    /* ---------- theme ---------- */
    const themeBtn = $("themeBtn"), sunIcon = themeBtn.querySelector(".i-sun"), moonIcon = themeBtn.querySelector(".i-moon");
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
    const isDark = () => (document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : systemDark.matches);
    function renderTheme() {
      const dark = isDark(), label = dark ? "Switch to light theme" : "Switch to dark theme";
      // show the theme you would get, not the one you are in
      sunIcon.hidden = !dark; moonIcon.hidden = dark;
      themeBtn.setAttribute("aria-label", label);
      themeBtn.title = label;
    }
    themeBtn.addEventListener("click", () => {
      const next = isDark() ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("xray-theme", next); } catch (e) { /* private browsing */ }
      renderTheme(); // the canvas repaints from the data-theme observer below
    });
    systemDark.addEventListener("change", renderTheme);
    renderTheme();

    const askForm = $("askForm"), askInput = $("askInput"), askHint = $("askHint");
    const HINT = (() => {
      const top = N.filter((n) => n.core && n.type === "PERSON").sort((a, b) => b.deg - a.deg).slice(0, 3).map((n) => tc(n.short || n.name));
      return "Name people, places or things in the novel — " + top.join(", ") + ", and so on.";
    })();
    function setHint(text, bad) { askHint.textContent = text; askHint.classList.toggle("bad", !!bad); }
    setHint(HINT, false);

    function openMenu(open) {
      qMenu.hidden = !open;
      qTrigger.setAttribute("aria-expanded", String(open));
      if (!open) return;
      const sel = qList.querySelector('[aria-selected="true"]');
      (S.custom ? askInput : sel || qList.firstElementChild).focus();
    }
    qTrigger.addEventListener("click", () => openMenu(qMenu.hidden));
    qList.addEventListener("click", (ev) => {
      const b = ev.target instanceof Element ? ev.target.closest("[data-q]") : null;
      if (!b) return;
      setQuery(+b.dataset.q); openMenu(false); qTrigger.focus();
    });
    qList.addEventListener("keydown", (ev) => {
      const items = [...qList.children], idx = items.indexOf(document.activeElement);
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        if (ev.key === "ArrowDown" && idx === items.length - 1) { askInput.focus(); return; }
        items[(idx + (ev.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus();
      }
    });
    askForm.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const r = M.ask(askInput.value);
      if (!r.ok) {
        setHint(r.reason === "empty" ? "Type a question first."
          : r.reason === "no-path" ? "Those entities aren’t connected anywhere in this graph."
          : "No entity in this index matched. " + HINT, true);
        askInput.focus();
        return;
      }
      setHint(HINT, false);
      setCustom(r.query);
      openMenu(false);
      qTrigger.focus();
    });
    askInput.addEventListener("input", () => { if (askHint.classList.contains("bad")) setHint(HINT, false); });
    askInput.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowUp") { ev.preventDefault(); qList.lastElementChild.focus(); }
    });
    document.addEventListener("pointerdown", (ev) => {
      const t = ev.target instanceof Element ? ev.target : null;
      if (!qMenu.hidden && !(t && t.closest(".question"))) openMenu(false);
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") {
        if (!qMenu.hidden) { openMenu(false); qTrigger.focus(); }
        else if (S.sel) { S.sel = null; S.hot = null; renderContext(); requestDraw(); }
        return;
      }
      const t = ev.target instanceof Element ? ev.target : null;
      if (ev.metaKey || ev.ctrlKey || ev.altKey || (t && t.closest("input, textarea, [contenteditable], [role=listbox]"))) return;
      // match on physical keys too, so shortcuts work on non-US keyboard layouts
      const key = ev.key, code = ev.code;
      if (key === "1" || code === "Digit1") setMethod("orig");
      else if (key === "2" || code === "Digit2") setMethod("prop");
      else if (key === "[" || code === "BracketLeft") setLevel(S.level - 1);
      else if (key === "]" || code === "BracketRight") setLevel(S.level + 1);
    });

    /* ---------- lifecycle ---------- */
    new ResizeObserver(() => { resize(); draw(); }).observe(stage);
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { readColors(); requestDraw(); });
    new MutationObserver(() => { readColors(); requestDraw(); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    resize();
    renderAll();
    draw();
    $("stageStatus").hidden = true;
  }
})();

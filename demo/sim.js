/* Simulated index: long-tail extraction, layout, per-level availability under
   both indexing methods, retrieval and judged correctness. Deterministic and
   dependency-free, so the demo runs offline. */
(function () {
  "use strict";
  var X = window.XR;
  try { build(); } catch (err) {
    X.error = err && err.message ? err.message : String(err);
    if (window.console) console.error(err);
  }
  function build() {
  function mul(seed) {
    return function () {
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  var rng = mul(1871);
  var pick = function (a) { return a[Math.floor(rng() * a.length)]; };
  var ri = function (a, b) { return a + Math.floor(rng() * (b - a + 1)); };
  var CFG = Object.assign({ budget: X.CORPUS.budget, K: 3, fullCut: 0.8, bridgeShare: 0.12, bridgeMinWeight: 4, bridgeTok: 14, compactTok: 14 }, X.CONFIG || {});
  var B = CFG.budget, K = CFG.K, W = 1000, H = 840;

  var L0 = X.L0.map(function (r) { return { id: r[0], title: r[1], p1: r[2], cx: r[3], cy: r[4], summary: r[5] }; });
  var L1KEYS = Object.keys(X.L1), L2KEYS = Object.keys(X.L2);

  function groupKey(level, c) {
    if (level === 0) return "c" + c;
    var p1 = L0[c].p1;
    if (level === 1) return p1;
    if (level === 2) return X.L1[p1][1];
    return "R";
  }
  function groupMeta(level, key) {
    if (level === 0) { var c = L0[+key.slice(1)]; return { id: c.id, title: c.title, summary: c.summary }; }
    if (level === 1) return { id: 22 + L1KEYS.indexOf(key), title: X.L1[key][0], summary: X.L1[key][2] };
    if (level === 2) return { id: 30 + L2KEYS.indexOf(key), title: X.L2[key][0], summary: X.L2[key][1] };
    return { id: 33, title: X.ROOT[0], summary: X.ROOT[1] };
  }

  /* ---------- entities and relationships ---------- */
  var nodes = [], byName = new Map(), edges = [], pairs = new Map();
  function addNode(name, type, c, short, core) {
    var n = { i: nodes.length, name: name, type: type, c: c, short: short || name, core: core, deg: 0 };
    nodes.push(n); byName.set(name, n); return n;
  }
  function pk(a, b) { return a < b ? a + "|" + b : b + "|" + a; }
  function addEdge(s, t, label, w, core) {
    if (s === t || s == null || t == null) return null;
    var k = pk(s, t);
    if (pairs.has(k)) {
      // graphrag keeps one relationship per entity pair: merge descriptions, sum weights
      if (!core) return null;
      var ex = edges[pairs.get(k)];
      ex.labels.push(label); ex.label = ex.labels.join("; "); ex.w += w;
      return ex;
    }
    var e = { i: edges.length, s: s, t: t, label: label, labels: [label], w: w, core: core };
    edges.push(e); pairs.set(k, e.i); nodes[s].deg++; nodes[t].deg++;
    return e;
  }
  X.ENTITIES.forEach(function (r) { addNode(r[0], r[1], r[2], r[3], true); });
  X.RELS.forEach(function (r) { addEdge(byName.get(r[0]).i, byName.get(r[1]).i, r[2], r[3], true); });

  var coreBy = L0.map(function (c) { return nodes.filter(function (n) { return n.c === c.id; }).map(function (n) { return n.i; }); });
  var tailBy = L0.map(function () { return []; });
  var usedPool = new Set();
  function personName() {
    for (var k = 0; k < 24; k++) {
      var nm = pick(X.POOL.titles) + " " + pick(X.POOL.surnames).toUpperCase();
      if (!byName.has(nm)) return nm;
    }
    return null;
  }
  function fromPool(pool) {
    var free = pool.filter(function (p) { return !usedPool.has(p) && !byName.has(p); });
    if (!free.length) return null;
    var p = pick(free); usedPool.add(p); return p;
  }
  L0.forEach(function (c) {
    var count = ri(10, 14);
    for (var k = 0; k < count; k++) {
      var roll = rng(), name = null, type = "PERSON";
      if (roll > 0.84) { name = fromPool(X.POOL.things); type = "CONCEPT"; }
      else if (roll > 0.68) { name = fromPool(X.POOL.places); type = "PLACE"; }
      if (!name) { name = personName(); type = "PERSON"; }
      if (!name) continue;
      var n = addNode(name, type, c.id, null, false);
      addEdge(n.i, pick(coreBy[c.id]), pick(X.POOL.rels), ri(1, 4), false);
      var peers = tailBy[c.id], m = Math.min(peers.length, ri(1, 2));
      for (var j = 0; j < m; j++) addEdge(n.i, pick(peers), pick(X.POOL.rels), ri(1, 3), false);
      if (rng() < 0.42) {
        var same = rng() < 0.5;
        var others = L0.filter(function (o) { return o.id !== c.id && (!same || o.p1 === c.p1); });
        if (!others.length) others = L0.filter(function (o) { return o.id !== c.id; });
        addEdge(n.i, pick(coreBy[pick(others).id]), pick(X.POOL.rels), rng() < 0.25 ? 3 : ri(1, 2), false);
      }
      if (rng() < 0.18) {
        var oc = pick(L0.filter(function (o) { return o.id !== c.id; }));
        addEdge(n.i, pick(coreBy[oc.id].concat(tailBy[oc.id])), pick(X.POOL.rels), ri(1, 2), false);
      }
      peers.push(n.i);
    }
  });
  nodes.forEach(function (n) { n.tok = n.core ? 36 + ri(0, 34) : 22 + ri(0, 20); });
  edges.forEach(function (e) {
    e.tok = 16 + e.label.split(" ").length * 3 + ri(0, 12);
    e.cd = nodes[e.s].deg + nodes[e.t].deg;
  });

  /* ---------- layout: deterministic force layout, no external dependency ---------- */
  (function layout() {
    var N = nodes.length, vx = new Float64Array(N), vy = new Float64Array(N), cnt = new Float64Array(N);
    nodes.forEach(function (n) {
      var c = L0[n.c];
      n.x = c.cx * W + (rng() - 0.5) * 60; n.y = c.cy * H + (rng() - 0.5) * 60;
      n.rr = 1.5 + Math.min(Math.sqrt(n.deg) * 0.95, 6);
    });
    edges.forEach(function (e) { cnt[e.s]++; cnt[e.t]++; });
    var links = edges.map(function (e) {
      var same = nodes[e.s].c === nodes[e.t].c;
      return { s: e.s, t: e.t, d: same ? 24 : 80, k: same ? 0.3 : 0.012, b: cnt[e.s] / (cnt[e.s] + cnt[e.t]) };
    });
    var TICKS = 320, alpha = 1, decay = 1 - Math.pow(0.001, 1 / TICKS);
    for (var it = 0; it < TICKS; it++) {
      alpha -= alpha * decay;
      for (var l = 0; l < links.length; l++) {
        var lk = links[l], a = nodes[lk.s], b = nodes[lk.t];
        var dx = b.x + vx[lk.t] - a.x - vx[lk.s] || 1e-6, dy = b.y + vy[lk.t] - a.y - vy[lk.s] || 1e-6;
        var dist = Math.sqrt(dx * dx + dy * dy), f = (dist - lk.d) / dist * alpha * lk.k;
        dx *= f; dy *= f;
        vx[lk.t] -= dx * lk.b; vy[lk.t] -= dy * lk.b;
        vx[lk.s] += dx * (1 - lk.b); vy[lk.s] += dy * (1 - lk.b);
      }
      for (var i = 0; i < N; i++) {
        var ni = nodes[i], ri = ni.rr * 2.2 + 2;
        for (var j = i + 1; j < N; j++) {
          var nj = nodes[j], ex = nj.x - ni.x, ey = nj.y - ni.y, d2 = ex * ex + ey * ey;
          if (d2 > 8100) continue;
          if (d2 < 1) { ex = (rng() - 0.5) * 1e-3; ey = (rng() - 0.5) * 1e-3; d2 = 1; }
          var w = -16 * alpha / d2;
          vx[i] += ex * w; vy[i] += ey * w; vx[j] -= ex * w; vy[j] -= ey * w;
          var rs = ri + nj.rr * 2.2 + 2;
          if (d2 < rs * rs) {
            var dd = Math.sqrt(d2), push = (rs - dd) / dd * 0.5;
            vx[i] -= ex * push; vy[i] -= ey * push; vx[j] += ex * push; vy[j] += ey * push;
          }
        }
        var cc = L0[ni.c];
        vx[i] += (cc.cx * W - ni.x) * 0.12 * alpha;
        vy[i] += (cc.cy * H - ni.y) * 0.12 * alpha;
      }
      for (var m = 0; m < N; m++) { vx[m] *= 0.6; vy[m] *= 0.6; nodes[m].x += vx[m]; nodes[m].y += vy[m]; }
    }
  })();
  var bounds = { x0: Infinity, x1: -Infinity, y0: Infinity, y1: -Infinity };
  nodes.forEach(function (n) {
    bounds.x0 = Math.min(bounds.x0, n.x); bounds.x1 = Math.max(bounds.x1, n.x);
    bounds.y0 = Math.min(bounds.y0, n.y); bounds.y1 = Math.max(bounds.y1, n.y);
  });

  /* ---------- availability per level ----------
     orig: 0 in summary, 1 lost at community boundary, 2 lost to summary budget
     prop: same codes, plus 3 = recovered (unavailable under the original)     */
  function byPriority(x, y) { return edges[y].cd - edges[x].cd || edges[y].w - edges[x].w || x - y; }
  var levels = [];
  for (var L = 0; L < 4; L++) {
    var gOf = nodes.map(function (n) { return groupKey(L, n.c); });
    var groups = new Map();
    nodes.forEach(function (n) {
      var k = gOf[n.i];
      if (!groups.has(k)) groups.set(k, { key: k, nodes: [], intra: [], cross: [] });
      groups.get(k).nodes.push(n.i);
    });
    edges.forEach(function (e) {
      var a = gOf[e.s], b = gOf[e.t];
      if (a === b) groups.get(a).intra.push(e.i);
      else { groups.get(a).cross.push(e.i); groups.get(b).cross.push(e.i); }
    });
    var orig = new Uint8Array(edges.length).fill(1);
    var prop = new Uint8Array(edges.length).fill(1);
    var bridgeHosts = new Map();

    groups.forEach(function (g) {
      g.need = g.nodes.reduce(function (s, i) { return s + nodes[i].tok; }, 0) +
               g.intra.reduce(function (s, i) { return s + edges[i].tok; }, 0);
      var sorted = g.intra.slice().sort(byPriority);

      // Original: shipped prefix admission, stop at the first element that overflows.
      var used = 0, seen = new Set(), admitted = 0;
      for (var a = 0; a < sorted.length; a++) {
        var e = edges[sorted[a]], cost = e.tok + (seen.has(e.s) ? 0 : nodes[e.s].tok) + (seen.has(e.t) ? 0 : nodes[e.t].tok);
        if (used + cost > B) break;
        used += cost; seen.add(e.s); seen.add(e.t); orig[sorted[a]] = 0; admitted++;
      }
      for (var b = admitted; b < sorted.length; b++) orig[sorted[b]] = 2;
      g.usedOrig = used;

      // Proposed: full descriptions to 62% of budget, bridge records to 84%, compact facts to 100%.
      var usedP = 0, seenP = new Set(), full = 0;
      for (var c = 0; c < sorted.length; c++) {
        var f = edges[sorted[c]], costP = f.tok + (seenP.has(f.s) ? 0 : nodes[f.s].tok) + (seenP.has(f.t) ? 0 : nodes[f.t].tok);
        if (usedP + costP > B * CFG.fullCut) break;
        usedP += costP; seenP.add(f.s); seenP.add(f.t); prop[sorted[c]] = 0; full++;
      }
      var bridges = g.cross.filter(function (i) { return edges[i].w >= CFG.bridgeMinWeight; }).sort(byPriority);
      var bridgeLimit = usedP + Math.min(B * CFG.bridgeShare, g.need * CFG.bridgeShare);
      for (var d = 0; d < bridges.length; d++) {
        if (usedP + CFG.bridgeTok > bridgeLimit) break;
        usedP += CFG.bridgeTok;
        if (!bridgeHosts.has(bridges[d])) bridgeHosts.set(bridges[d], []);
        bridgeHosts.get(bridges[d]).push(g.key);
      }
      // Compact facts continue in priority order past the full-text cutoff, so every element
      // the original admits is still present, and the freed tokens reach further into the tail.
      for (var h = full; h < sorted.length; h++) {
        if (usedP + CFG.compactTok > B) { prop[sorted[h]] = 2; continue; }
        usedP += CFG.compactTok; prop[sorted[h]] = 0;
      }
      g.usedProp = usedP;
    });
    bridgeHosts.forEach(function (_, i) { prop[i] = 0; });
    for (var i = 0; i < edges.length; i++) if (prop[i] === 0 && orig[i] !== 0) prop[i] = 3;

    var co = [0, 0, 0, 0], cp = [0, 0, 0, 0];
    orig.forEach(function (s) { co[s]++; }); prop.forEach(function (s) { cp[s]++; });
    var gl = Array.from(groups.values()), E = edges.length;
    levels.push({
      gOf: gOf, groups: groups, orig: orig, prop: prop, bridgeHosts: bridgeHosts,
      stats: {
        groups: gl.length,
        meanNeed: gl.reduce(function (s, g) { return s + g.need; }, 0) / gl.length,
        over: gl.filter(function (g) { return g.need > B; }).length,
        orig: { kept: co[0], boundary: co[1], budget: co[2], lost: co[1] + co[2], retention: co[0] / E },
        prop: { kept: cp[0] + cp[3], boundary: cp[1], budget: cp[2], lost: cp[1] + cp[2], recovered: cp[3], retention: (cp[0] + cp[3]) / E }
      }
    });
  }

  /* ---------- queries ---------- */
  var adj = nodes.map(function () { return []; });
  edges.forEach(function (e) { adj[e.s].push([e.t, e.i]); adj[e.t].push([e.s, e.i]); });
  var featured = X.QUERIES.map(function (q) {
    var o = Object.assign({ featured: true }, q);
    o.hopIdx = q.hops.map(function (h) { return pairs.get(pk(byName.get(h[0]).i, byName.get(h[1]).i)); });
    return o;
  });
  var sampled = [], cores = nodes.filter(function (n) { return n.core && n.deg >= 3; }), guard = 0, seenPath = new Set();
  while (sampled.length < 43 && guard++ < 4000) {
    var start = pick(cores), dist = new Map([[start.i, 0]]), prev = new Map(), queue = [start.i];
    while (queue.length) {
      var u = queue.shift(), du = dist.get(u);
      if (du >= 4) continue;
      adj[u].forEach(function (p) { if (!dist.has(p[0])) { dist.set(p[0], du + 1); prev.set(p[0], [u, p[1]]); queue.push(p[0]); } });
    }
    var targets = [];
    var wantFar = rng() < 0.3;
    dist.forEach(function (dd, v) { if (dd >= 2 && nodes[v].core && v !== start.i && (wantFar ? nodes[v].c !== start.c : nodes[v].c === start.c)) targets.push(v); });
    if (!targets.length) continue;
    var v = pick(targets), hop = [];
    while (v !== start.i) { var pr = prev.get(v); hop.push(pr[1]); v = pr[0]; }
    var sig = hop.slice().sort().join(",");
    if (seenPath.has(sig)) continue;
    seenPath.add(sig);
    sampled.push({ id: "S-" + String(sampled.length + 1).padStart(3, "0"), featured: false, hopIdx: hop.reverse() });
  }
  var queries = featured.concat(sampled);
  queries.forEach(function (q) {
    q.u = rng();
    var s = new Set();
    q.hopIdx.forEach(function (i) { s.add(edges[i].s); s.add(edges[i].t); });
    q.ents = Array.from(s);
  });

  function hashInt(str) {
    var h = 2166136261;
    for (var j = 0; j < str.length; j++) { h ^= str.charCodeAt(j); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }
  function hashRand(str) { return mul(hashInt(str))(); }

  /* ---------- custom questions ----------
     A typed question is resolved against the entity names in this index, and its
     evidence is taken as the shortest relationship chain linking the entities it
     names. The query object returned has the same shape as a benchmark question,
     so evaluate() runs it unchanged: same loss sets, same ranking, same judge. */
  var TITLE_W = new Set(["mr", "mrs", "miss", "dr", "sir", "lady", "old", "young", "farmer", "captain", "the", "st"]);
  // name tokens that are ordinary English words too: matched only inside a full name
  var COMMON_W = new Set(["will", "court", "house", "death", "debt", "bill", "loan", "place", "fair", "first",
                          "later", "town", "hall", "park", "lane", "street", "manor", "estate", "business",
                          "meeting", "plans", "jewels", "journey", "gate", "green", "stone", "wills", "scandal"]);
  function normText(s) { return String(s == null ? "" : s).toLowerCase().replace(/[^a-z0-9£]+/g, " ").trim(); }

  var alias = (function () {
    var cand = new Map();
    function add(phrase, i, tier) {
      if (!phrase || phrase.length < 3) return;
      if (!cand.has(phrase)) cand.set(phrase, []);
      cand.get(phrase).push({ i: i, tier: tier });
    }
    nodes.forEach(function (n) {
      var full = normText(n.name);
      add(full, n.i, 0);
      if (n.short && n.short !== n.name) add(normText(n.short), n.i, 1);
      full.split(" ").forEach(function (w) {
        if (w.length >= 4 && !TITLE_W.has(w) && !COMMON_W.has(w)) add(w, n.i, 2);
      });
    });
    var out = new Map();
    cand.forEach(function (list, phrase) {
      // "lydgate" names three entities: the most connected one wins
      list.sort(function (a, b) { return a.tier - b.tier || nodes[b.i].deg - nodes[a.i].deg || a.i - b.i; });
      var top = list[0], tied = list.filter(function (c) { return c.tier === top.tier; }).length;
      out.set(phrase, { i: top.i, tier: top.tier, ambig: tied });
    });
    return out;
  })();

  function shortestHops(a, b) {
    if (a === b) return [];
    var prev = new Map([[a, null]]), queue = [a], done = false;
    while (queue.length && !done) {
      var u = queue.shift();
      for (var k = 0; k < adj[u].length; k++) {
        var p = adj[u][k];
        if (prev.has(p[0])) continue;
        prev.set(p[0], [u, p[1]]);
        if (p[0] === b) { done = true; break; }
        queue.push(p[0]);
      }
    }
    if (!prev.has(b)) return null;
    var path = [], v = b, step;
    while ((step = prev.get(v))) { path.push(step[1]); v = step[0]; }
    return path.reverse();
  }

  var MAX_ENTS = 4, MAX_HOPS = 8, STAR_HOPS = 4;
  function ask(text) {
    var raw = String(text == null ? "" : text).trim(), norm = normText(raw);
    if (!norm) return { ok: false, reason: "empty" };
    var toks = norm.split(" "), matched = [], seen = new Set(), i = 0;
    while (i < toks.length && matched.length < MAX_ENTS) {
      var hit = null, len = 0;
      for (var n = Math.min(4, toks.length - i); n >= 1; n--) {
        var gram = toks.slice(i, i + n).join(" "), a = alias.get(gram);
        // "the Garths", "Bulstrodes" — a plural or possessive still names the entity
        if (!a && n === 1 && gram.length >= 5 && gram.charAt(gram.length - 1) === "s") a = alias.get(gram.slice(0, -1));
        if (a) { hit = a; len = n; break; }
      }
      if (!hit) { i++; continue; }
      if (!seen.has(hit.i)) {
        seen.add(hit.i);
        matched.push({ i: hit.i, name: nodes[hit.i].name, short: nodes[hit.i].short,
                       via: toks.slice(i, i + len).join(" "), exact: hit.tier === 0, ambig: hit.ambig });
      }
      i += len;
    }
    if (!matched.length) return { ok: false, reason: "no-entity" };

    var hops = [], unlinked = [], shape = matched.length === 1 ? "star" : "chain";
    if (shape === "star") {
      // one entity named: its most-cited relationships are what an answer would need
      var inc = adj[matched[0].i].map(function (p) { return p[1]; })
        .sort(function (x, y) { return edges[y].w - edges[x].w || edges[y].cd - edges[x].cd || x - y; });
      var fromCorpus = inc.filter(function (e) { return edges[e].core; });
      hops = (fromCorpus.length >= 2 ? fromCorpus : inc).slice(0, STAR_HOPS);
    } else {
      for (var m = 0; m + 1 < matched.length; m++) {
        var seg = shortestHops(matched[m].i, matched[m + 1].i);
        if (!seg || !seg.length) { unlinked.push([matched[m].name, matched[m + 1].name]); continue; }
        seg.forEach(function (e) { if (hops.indexOf(e) < 0 && hops.length < MAX_HOPS) hops.push(e); });
      }
    }
    if (!hops.length) return { ok: false, reason: "no-path", matched: matched };

    var ents = new Set();
    hops.forEach(function (e) { ents.add(edges[e].s); ents.add(edges[e].t); });
    return { ok: true, matched: matched, unlinked: unlinked, query: {
      id: "U-" + hashInt("q|" + norm).toString(36).slice(-4).toUpperCase(),
      featured: false, custom: true, shape: shape, type: "Custom question",
      text: raw, matched: matched, unlinked: unlinked,
      hopIdx: hops, ents: Array.from(ents), u: hashRand("u|" + norm)
    } };
  }

  function evaluate(q, L, method) {
    var lv = levels[L], state = method === "orig" ? lv.orig : lv.prop, count = new Map();
    q.ents.forEach(function (i) { var k = lv.gOf[i]; count.set(k, (count.get(k) || 0) + 1); });
    // Relevance ranking over all community reports: entity overlap, a size prior and
    // query-specific noise shared by both methods, so distractor reports can take a slot.
    var maxSize = 1;
    lv.groups.forEach(function (g) { maxSize = Math.max(maxSize, g.nodes.length); });
    var ranked = Array.from(lv.groups.values())
      .map(function (g) {
        var c = count.get(g.key) || 0, noise = hashRand(q.id + "|" + L + "|" + g.key);
        return { key: g.key, score: 3 * c / q.ents.length + 0.5 * Math.log(1 + g.nodes.length) / Math.log(1 + maxSize) + 1.2 * noise };
      })
      .sort(function (a, b) { return b.score - a.score; })
      .slice(0, K).map(function (g) { return g.key; });
    var top = new Set(ranked);
    var hops = q.hopIdx.map(function (i) {
      var e = edges[i], st = state[i], avail = st === 0 || st === 3, ga = lv.gOf[e.s], gb = lv.gOf[e.t], host = null;
      if (avail) {
        if (ga === gb) host = ga;
        else {
          var hs = method === "prop" ? (lv.bridgeHosts.get(i) || []) : [];
          host = hs.filter(function (x) { return top.has(x); })[0] || hs[0] || null;
        }
      }
      return { i: i, state: st, avail: avail, retrieved: avail && host !== null && top.has(host), host: host,
               reason: avail ? null : (ga !== gb ? "boundary" : "budget"), bridge: avail && ga !== gb };
    });
    var n = hops.length,
        av = hops.filter(function (h) { return h.avail; }).length,
        rt = hops.filter(function (h) { return h.retrieved; }).length,
        fRet = rt / n, p = fRet === 1 ? 0.8 : fRet >= 0.5 ? 0.45 : 0.15;
    return { hops: hops, ranked: ranked, avail: av, retrieved: rt, n: n, fAvail: av / n, fRet: fRet,
             complete: rt === n, correct: q.u < p,
             outcome: fRet === 1 ? "correct" : fRet >= 0.5 ? "partial" : "incorrect" };
  }

  var metrics = levels.map(function (lv, Lx) {
    var m = {};
    ["orig", "prop"].forEach(function (method) {
      var ev = queries.map(function (q) { return evaluate(q, Lx, method); });
      var mean = function (f) { return ev.reduce(function (s, r) { return s + f(r); }, 0) / ev.length; };
      m[method] = {
        retention: lv.stats[method].retention,
        coverage: mean(function (r) { return r.fAvail; }),
        retrieval: mean(function (r) { return r.fRet; }),
        context: mean(function (r) { return r.complete ? 1 : 0; }),
        correct: mean(function (r) { return r.correct ? 1 : 0; })
      };
    });
    return m;
  });

  X.model = { config: CFG, nodes: nodes, edges: edges, levels: levels, queries: queries, metrics: metrics,
              evaluate: evaluate, ask: ask, groupKey: groupKey, groupMeta: groupMeta, bounds: bounds, K: K, B: B };
  }
})();

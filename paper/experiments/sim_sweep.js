/* Re-runs the GraphRAG X-Ray simulation (demo/data.js + demo/sim.js) headlessly
   under each configuration and writes paper/results/simulation.json.
   The simulation is synthetic: a Middlemarch-shaped graph with generated
   long-tail entities, weights, token counts and a stochastic answer judge. */
"use strict";
const path = require("path"), fs = require("fs");
const DEMO = path.resolve(__dirname, "../../demo");
const OUT = path.resolve(__dirname, "../results/simulation.json");

function build(cfg) {
  for (const f of ["data.js", "sim.js"]) delete require.cache[require.resolve(path.join(DEMO, f))];
  global.window = global;
  global.XR = undefined;
  require(path.join(DEMO, "data.js"));
  window.XR.CONFIG = cfg || {};
  require(path.join(DEMO, "sim.js"));
  if (window.XR.error) throw new Error(window.XR.error);
  return window.XR.model;
}

function rng(seed) { return () => { seed |= 0; seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

// question-paired bootstrap of (proposed - original) mean evidence retrieved
function pairedCI(diffs, B = 4000) {
  const r = rng(20260815), n = diffs.length, stats = [];
  for (let b = 0; b < B; b++) { let s = 0; for (let i = 0; i < n; i++) s += diffs[Math.floor(r() * n)]; stats.push(s / n); }
  stats.sort((a, b) => a - b);
  return [stats[Math.floor(0.025 * B)], stats[Math.floor(0.975 * B) - 1]];
}

function summarize(M) {
  return M.levels.map((lv, L) => {
    const ev = M.queries.map((q) => [M.evaluate(q, L, "orig"), M.evaluate(q, L, "prop")]);
    const diffs = ev.map(([o, p]) => p.fRet - o.fRet);
    return {
      level: L, communities: lv.stats.groups, over_budget: lv.stats.over, mean_need: lv.stats.meanNeed,
      orig: { ...M.metrics[L].orig, boundary: lv.stats.orig.boundary, budget: lv.stats.orig.budget },
      prop: { ...M.metrics[L].prop, boundary: lv.stats.prop.boundary, budget: lv.stats.prop.budget, recovered: lv.stats.prop.recovered },
      retrieval_diff: diffs.reduce((a, b) => a + b, 0) / diffs.length, retrieval_diff_ci: pairedCI(diffs),
      query_regressions: ev.filter(([o, p]) => p.retrieved < o.retrieved).length,
      edge_regressions: Array.from(lv.orig).filter((s, i) => s === 0 && !(lv.prop[i] === 0 || lv.prop[i] === 3)).length,
    };
  });
}

const base = build({});
const result = {
  corpus: { entities: base.nodes.length, relationships: base.edges.length, core_entities: base.nodes.filter((n) => n.core).length,
            core_relationships: base.edges.filter((e) => e.core).length, questions: base.queries.length,
            featured: base.queries.filter((q) => q.featured).length },
  config: base.config,
  default: summarize(base),
  sweeps: {},
};
const sweeps = {
  bridgeShare: [0, 0.06, 0.12, 0.24].map((v) => ({ bridgeShare: v })),
  bridgeMinWeight: [3, 4, 5, 999].map((v) => ({ bridgeMinWeight: v })),
  fullCut: [0.6, 0.8, 1.0].map((v) => ({ fullCut: v })),
  K: [2, 3, 6].map((v) => ({ K: v })),
  budget: [4000, 8000, 16000].map((v) => ({ budget: v })),
};
for (const [name, cfgs] of Object.entries(sweeps)) {
  result.sweeps[name] = cfgs.map((cfg) => ({ cfg, levels: summarize(build(cfg)) }));
}
fs.writeFileSync(OUT, JSON.stringify(result, null, 1));
const pct = (v) => (100 * v).toFixed(1);
console.log("corpus", JSON.stringify(result.corpus));
for (const r of result.default) console.log(`L${r.level} comms=${r.communities} over=${r.over_budget} ret ${pct(r.orig.retention)}->${pct(r.prop.retention)} cov ${pct(r.orig.coverage)}->${pct(r.prop.coverage)} retr ${pct(r.orig.retrieval)}->${pct(r.prop.retrieval)} [diff CI ${r.retrieval_diff_ci.map(pct).join(",")}] correct ${pct(r.orig.correct)}->${pct(r.prop.correct)} qreg=${r.query_regressions} ereg=${r.edge_regressions}`);
for (const [name, rows] of Object.entries(result.sweeps)) for (const row of rows) {
  const l0 = row.levels[0], l3 = row.levels[3];
  console.log(name, JSON.stringify(row.cfg), `leaf ret ${pct(l0.prop.retention)} retr ${pct(l0.orig.retrieval)}->${pct(l0.prop.retrieval)} correct ${pct(l0.prop.correct)} | root ret ${pct(l3.orig.retention)}->${pct(l3.prop.retention)} retr ${pct(l3.prop.retrieval)}`);
}

"""Figures (PNG, 300 dpi) and table data (JSON) for the final report.

Everything is read from paper/results and paper/generated, the same files the
paper uses, so the report and the paper cannot disagree on a number.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mtick  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "paper" / "results"
GEN = ROOT / "paper" / "generated"
OUT = ROOT / "report" / "assets"
OUT.mkdir(parents=True, exist_ok=True)
MAIN = "rgi_f0.8_b0.12_m2"
INK, LOST, KEPT, EVID, GREY = "#1d1d1f", "#c2362d", "#17875a", "#3056d3", "#a1a1a6"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "font.size": 10, "axes.titlesize": 10, "axes.labelsize": 10, "legend.fontsize": 9,
    "xtick.labelsize": 9, "ytick.labelsize": 9, "axes.spines.top": False, "axes.spines.right": False,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.03, "savefig.dpi": 300,
})
PCT = mtick.FuncFormatter(lambda v, _: f"{100 * v:.0f}%")


def pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}"


def num(x: float) -> str:
    return f"{int(round(x)):,}"


# ---------------------------------------------------------------- macros
macros = {}
for m in re.finditer(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}", (GEN / "macros.tex").read_text()):
    macros[m.group(1)] = m.group(2).replace("{,}", ",")
tables: dict[str, dict] = {}

# ---------------------------------------------------------------- corpus
graph = pd.read_csv(RES / "graph_stats.csv")
qs = json.loads((ROOT / "data" / "graphrag_bench" / "novel_questions.json").read_text())
qtypes = pd.Series([q["question_type"] for q in qs]).value_counts()

fig, ax = plt.subplots(figsize=(6.0, 2.4))
ax.barh(qtypes.index[::-1], qtypes.values[::-1], color=EVID, height=0.6)
for y, v in enumerate(qtypes.values[::-1]):
    ax.text(v + 15, y, f"{v:,} ({100 * v / len(qs):.1f}%)", va="center", fontsize=9)
ax.set_xlabel("Questions in GraphRAG-Bench Novel")
ax.set_xlim(0, qtypes.max() * 1.3)
fig.savefig(OUT / "f_qtypes.png"); plt.close(fig)

g = graph.sort_values("relationships", ascending=False).reset_index(drop=True)
fig, ax = plt.subplots(figsize=(6.0, 2.8))
x = np.arange(len(g))
ax.bar(x, g.relationships, color=INK, width=0.7, label="Relationships after pruning")
ax.set_yscale("log")
ax.set_ylabel("Relationships (log scale)")
ax2 = ax.twinx()
ax2.plot(x, g.entities, "o", color=LOST, ms=4, label="Entities after pruning")
ax2.set_ylabel("Entities")
ax2.spines["right"].set_visible(True)
ax.set_xticks(x, [n.replace("Novel-", "") for n in g.novel], rotation=60, ha="right", fontsize=8)
ax.set_xlabel("Novel (GraphRAG-Bench identifier)")
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, frameon=False, loc="upper right")
fig.savefig(OUT / "f_novels.png"); plt.close(fig)

tables["corpus"] = {
    "header": ["Quantity", "Value"],
    "rows": [
        ["Novels / questions", f"{len(graph)} / {len(qs):,}"],
        ["Characters / tokens (o200k_base)", f"{num(graph.chars.sum())} / {num(graph.tokens.sum())}"],
        ["Text units (1,200 tokens, 100 overlap)", num(graph.text_units.sum())],
        ["Extracted entities / relationships", f"{num(graph.raw_entities.sum())} / {num(graph.raw_relationships.sum())}"],
        ["After pruning: entities / relationships", f"{num(graph.entities.sum())} / {num(graph.relationships.sum())}"],
        ["Mean degree, pooled (median over novels)", f"{2 * graph.relationships.sum() / graph.entities.sum():.1f} ({graph.mean_degree.median():.1f})"],
        ["Communities, all levels", num(sum(graph[f'communities_l{i}'].sum() for i in range(5)))],
        ["Deepest level reached", str(int(graph.max_level.max()))],
        ["Summary input budget", "8,000 tokens"],
        ["Largest novel's share of relationships", f"{100 * graph.relationships.max() / graph.relationships.sum():.0f}%"],
        ["LLM calls", "0"],
    ],
}
tables["qtypes"] = {"header": ["Question type", "Questions", "Share"],
                    "rows": [[k, f"{v:,}", f"{100 * v / len(qs):.1f}%"] for k, v in qtypes.items()]}

# ---------------------------------------------------------------- census
L = pd.read_csv(RES / "level_census.csv")
cols = ["relationships", "covered", "boundary", "budget_lost", "indirect", "outside", "via_compact", "via_bridge",
        "fallback", "regressions", "communities", "fits", "trimmed", "second_order", "passages",
        "expo_scope", "expo_endpoint", "expo_elsewhere", "expo_absent", "expo_regressions"]
m8 = L[(L.budget == 8000) & L.method.isin(["graphrag", MAIN])]
P = m8.groupby(["level", "method"])[cols].sum()
P["share"] = P.covered / P.relationships


def boot(v: np.ndarray, B: int = 10000) -> tuple[float, float]:
    rng = np.random.default_rng(20260815)
    s = v[rng.integers(0, len(v), size=(B, len(v)))].mean(axis=1)
    return float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))


rows = []
for lvl in range(4):
    gq, rq = P.loc[(lvl, "graphrag")], P.loc[(lvl, MAIN)]
    gm = m8[(m8.level == lvl) & (m8.method == "graphrag")]
    rm = m8[(m8.level == lvl) & (m8.method == MAIN)]
    d = (rm.covered.values / rm.relationships.values) - (gm.covered.values / gm.relationships.values)
    lo, hi = boot(d)
    rows.append([str(lvl) + (" (root)" if lvl == 0 else " (default)" if lvl == 2 else ""),
                 num(gq.communities), pct(gq.share), pct(gq.boundary / gq.relationships), pct(gq.indirect / gq.relationships),
                 pct(gq.budget_lost / gq.relationships, 2), pct(rq.share), f"+{pct(d.mean())} [{pct(lo)}, {pct(hi)}]"])
tables["census"] = {"header": ["Level", "Comm.", "In scope", "Boundary", "Sub-summary", "Budget", "RGI in scope", "Mean gain [95% CI]"],
                    "rows": rows}

rows = []
for lvl in range(4):
    for meth, nm in (("graphrag", "GraphRAG"), (MAIN, "RGI")):
        x = P.loc[(lvl, meth)]
        rows.append([str(lvl) if meth == "graphrag" else "", nm, pct(x.expo_scope / x.relationships), pct(x.expo_endpoint / x.relationships),
                     pct(x.expo_elsewhere / x.relationships), pct(x.expo_absent / x.relationships)])
tables["exposure"] = {"header": ["Level", "Index", "In scope", "Endpoint", "Elsewhere", "Absent"], "rows": rows}

rows = []
for lvl in range(4):
    gq, rq = P.loc[(lvl, "graphrag")], P.loc[(lvl, MAIN)]
    rows.append([str(lvl), num(gq.fits), num(gq.trimmed), num(gq.second_order), num(gq.passages), num(rq.passages),
                 num(rq.via_bridge), num(rq.via_compact)])
tables["inputs"] = {"header": ["Level", "Fit", "Trimmed", "Sub-summary", "Units (GraphRAG)", "Units (RGI)", "Bridge records", "Compact facts"],
                    "rows": rows}

fig, ax = plt.subplots(figsize=(6.0, 3.2))
cats = [("In scope: full unit", "covered_passage", INK), ("In scope: compact fact", "via_compact", "#5b5b60"),
        ("In scope: bridge record", "via_bridge", KEPT), ("Boundary", "boundary", LOST),
        ("Sub-summary only", "indirect", "#e6a19b"), ("Budget", "budget_lost", "#7a1d17"), ("Outside LCC", "outside", GREY)]
labels, ypos, y = [], [], 0
for lvl in range(4):
    for meth, name in (("graphrag", "GraphRAG"), (MAIN, "RGI")):
        r = P.loc[(lvl, meth)]
        vals = {"covered_passage": r.covered - r.via_compact - r.via_bridge, "via_compact": r.via_compact, "via_bridge": r.via_bridge,
                "boundary": r.boundary, "indirect": r.indirect, "budget_lost": r.budget_lost, "outside": r.outside}
        left = 0.0
        for lab, key, col in cats:
            w = vals[key] / r.relationships
            ax.barh(y, w, left=left, color=col, height=0.72, edgecolor="white", linewidth=0.3, label=lab if y == 0 else None)
            left += w
        labels.append(f"Level {lvl}, {name}"); ypos.append(y); y += 1
    y += 0.5
ax.set_yticks(ypos, labels); ax.invert_yaxis(); ax.set_xlim(0, 1); ax.xaxis.set_major_formatter(PCT)
ax.set_xlabel("Share of all relationships, pooled over 20 novels")
ax.legend(ncol=3, loc="lower center", bbox_to_anchor=(0.42, 1.0), frameon=False, fontsize=8, handlelength=1.2, columnspacing=0.9)
fig.savefig(OUT / "f_census.png"); plt.close(fig)

fig, axes = plt.subplots(1, 2, figsize=(6.0, 2.5), sharey=True)
for ax, lvl in zip(axes, (2, 0)):
    for meth, col, name, ls in (("graphrag", LOST, "GraphRAG", "--"), (MAIN, KEPT, "RGI", "-")):
        d = L[(L.level == lvl) & (L.method == meth)].groupby("budget")[["covered", "relationships"]].sum()
        ax.plot(d.index, d.covered / d.relationships, ls, color=col, marker="o", ms=4, lw=1.4, label=name)
    ax.set_xscale("log", base=2); ax.set_xticks([4000, 8000, 16000, 32000], ["4k", "8k", "16k", "32k"])
    ax.set_title(f"Level {lvl}" + (" (default)" if lvl == 2 else " (root)")); ax.yaxis.set_major_formatter(PCT)
axes[0].set_ylabel("Relationships in scope"); axes[1].legend(frameon=False, loc="upper left")
fig.supxlabel("Summary input budget (tokens)", fontsize=10, y=-0.05)
fig.savefig(OUT / "f_budget.png"); plt.close(fig)

# per-novel gains at level 2
gm = m8[(m8.level == 2) & (m8.method == "graphrag")].set_index("novel")
rm = m8[(m8.level == 2) & (m8.method == MAIN)].set_index("novel")
pn = pd.DataFrame({"g": gm.covered / gm.relationships, "r": rm.covered / rm.relationships}).sort_values("g")
fig, ax = plt.subplots(figsize=(6.0, 3.4))
yy = np.arange(len(pn))
ax.hlines(yy, pn.g, pn.r, color=GREY, lw=1.2)
ax.plot(pn.g, yy, "o", color=LOST, ms=4.5, label="GraphRAG")
ax.plot(pn.r, yy, "o", color=KEPT, ms=4.5, label="RGI")
ax.set_yticks(yy, [n.replace("Novel-", "") for n in pn.index], fontsize=8)
ax.xaxis.set_major_formatter(PCT); ax.set_xlabel("Relationships in scope at level 2, per novel")
ax.legend(frameon=False, loc="lower right")
fig.savefig(OUT / "f_pernovel.png"); plt.close(fig)
macros["PerNovelImproved"] = str(int((pn.r > pn.g).sum()))
macros["PerNovelMinGain"] = pct((pn.r - pn.g).min())
macros["PerNovelMaxGain"] = pct((pn.r - pn.g).max())

# ---------------------------------------------------------------- selection
S = pd.read_csv(RES / "selection_loss.csv")
sa = S.groupby("level")[["communities", "entities", "intra", "intra_in_input", "bound", "cross_in_input"]].sum()
tables["selection"] = {"header": ["Level", "Communities", "Within-community relationships", "Reach the input", "Share", "Upper bound", "Cross-community in inputs"],
                       "rows": [[str(l), num(r.communities), num(r.intra), num(r.intra_in_input), f"{pct(r.intra_in_input / r.intra)}%",
                                 num(r.bound), num(r.cross_in_input)] for l, r in sa.iterrows()]}
fig, ax = plt.subplots(figsize=(6.0, 2.4))
xs = np.arange(len(sa))
ax.bar(xs - 0.18, sa.intra_in_input / sa.intra, 0.34, color=LOST, label="Reach the input (measured)")
ax.bar(xs + 0.18, sa.bound / sa.intra, 0.34, color=GREY, label="Upper bound, one per entity")
ax.set_xticks(xs, [f"Level {l}" for l in sa.index]); ax.yaxis.set_major_formatter(PCT)
ax.set_ylabel("Share of within-community\nrelationships"); ax.legend(frameon=False, loc="upper left")
fig.savefig(OUT / "f_selection.png"); plt.close(fig)

# ---------------------------------------------------------------- gold
T = pd.read_csv(RES / "gold_triples.csv")
G = pd.read_csv(RES / "gold_questions.csv")
rows, gold_plot = [], []
for lvl, d in G.groupby("level"):
    b = (d.base_covered < d.n_gold).astype(float).to_numpy(); r = (d.rgi_covered < d.n_gold).astype(float).to_numpy()
    lo, hi = boot(r - b)
    rows.append([f"Level {lvl}", num(len(d)), pct(b.mean()), pct(r.mean()), f"-{pct(b.mean() - r.mean())} [{pct(-hi)}, {pct(-lo)}]",
                 pct(d.base_covered.sum() / d.n_gold.sum()), pct(d.rgi_covered.sum() / d.n_gold.sum())])
    gold_plot.append((lvl, b.mean(), r.mean()))
tables["gold"] = {"header": ["Level", "Questions", "Missing a gold relationship (GraphRAG)", "Same under RGI", "Change [95% CI]",
                             "Gold relationships in scope (GraphRAG)", "Same under RGI"], "rows": rows}
d2 = G[G.level == 2]
tables["gold_types"] = {"header": ["Question type (level 2)", "Questions", "GraphRAG", "RGI", "Change"],
                        "rows": [[t, num(len(d)), pct((d.base_covered < d.n_gold).mean()), pct((d.rgi_covered < d.n_gold).mean()),
                                  f"-{pct((d.base_covered < d.n_gold).mean() - (d.rgi_covered < d.n_gold).mean())}"] for t, d in d2.groupby("type")]}
tables["linking"] = {"header": ["Step", "Triples", "Share"],
                     "rows": [["Gold triples in the benchmark", num(len(T)), "100.0%"],
                              ["Parsed into (head, relation, tail)", num(T.parsed.sum()), f"{pct(T.parsed.mean())}%"],
                              ["Both endpoints linked (token_set_ratio >= 85)", num(T.linked.sum()), f"{pct(T.linked.mean())}%"],
                              ["Resolved to a relationship in the graph", num((T.n_rel > 0).sum()), f"{pct((T.n_rel > 0).mean())}%"]]}
fig, ax = plt.subplots(figsize=(6.0, 2.4))
xs = np.arange(4)
b = [g[1] for g in gold_plot]; r = [g[2] for g in gold_plot]
ax.bar(xs - 0.18, b, 0.34, color=LOST, label="GraphRAG"); ax.bar(xs + 0.18, r, 0.34, color=KEPT, label="RGI")
for i in range(4):
    ax.text(xs[i] - 0.18, b[i] + 0.02, pct(b[i], 0) + "%", ha="center", fontsize=8)
    ax.text(xs[i] + 0.18, r[i] + 0.02, pct(r[i], 0) + "%", ha="center", fontsize=8)
ax.set_xticks(xs, ["Level 0 (root)", "Level 1", "Level 2 (default)", "Level 3"]); ax.set_ylim(0, 1.12)
ax.yaxis.set_major_formatter(PCT); ax.set_ylabel("Questions with a gold\nrelationship out of scope"); ax.legend(frameon=False, ncol=2)
fig.savefig(OUT / "f_gold.png"); plt.close(fig)

# ---------------------------------------------------------------- sensitivity and ablations
rows = []
for size, d in ((1200, RES), (600, RES / "chunk600"), (300, RES / "chunk300")):
    gs = pd.read_csv(d / "graph_stats.csv"); lc = pd.read_csv(d / "level_census.csv"); lc = lc[lc.budget == 8000]
    def share(lvl, meth):
        x = lc[(lc.level == lvl) & (lc.method == meth)][["covered", "relationships"]].sum()
        return x.covered / x.relationships
    rows.append([f"{size:,}" + (" (default)" if size == 1200 else ""), num(gs.text_units.sum()), num(gs.relationships.sum()),
                 f"{2 * gs.relationships.sum() / gs.entities.sum():.1f}", pct(share(2, "graphrag")), pct(share(2, MAIN)),
                 pct(share(0, "graphrag")), pct(share(0, MAIN))])
tables["chunk"] = {"header": ["Text-unit size", "Units", "Relationships", "Mean degree", "Level 2 GraphRAG", "Level 2 RGI", "Level 0 GraphRAG", "Level 0 RGI"],
                   "rows": rows}

abl = L[(L.budget == 8000) & L.method.str.startswith("rgi")]
order = [("rgi_f0.8_b0_m2", "No bridge records (b = 0)"), ("rgi_f0.8_b0.06_m2", "Bridge share b = 0.06"), (MAIN, "Default (b = 0.12, f = 0.8, m = 2)"),
         ("rgi_f0.8_b0.24_m2", "Bridge share b = 0.24"), ("rgi_f0.6_b0.12_m2", "Full-item cutoff f = 0.6"),
         ("rgi_f1_b0.12_m2", "Full-item cutoff f = 1.0 (no compact tier)"), ("rgi_f0.8_b0.12_m1", "Minimum support m = 1"),
         ("rgi_f0.8_b0.12_m3", "Minimum support m = 3")]
rows = [["GraphRAG (baseline)", pct(P.loc[(2, "graphrag")].share), "n/a", pct(P.loc[(0, "graphrag")].share), "n/a"]]
for meth, name in order:
    a2 = abl[(abl.level == 2) & (abl.method == meth)][["covered", "relationships", "via_bridge"]].sum()
    a0 = abl[(abl.level == 0) & (abl.method == meth)][["covered", "relationships", "via_bridge"]].sum()
    rows.append([name, pct(a2.covered / a2.relationships), pct(a2.via_bridge / a2.relationships),
                 pct(a0.covered / a0.relationships), pct(a0.via_bridge / a0.relationships)])
tables["ablation"] = {"header": ["Configuration", "Level 2 in scope", "Level 2 bridged", "Level 0 in scope", "Level 0 bridged"], "rows": rows}

# ---------------------------------------------------------------- simulation
sim = json.loads((RES / "simulation.json").read_text())
names = ["Leaf (22)", "Community (8)", "Higher (3)", "Root (1)"]
tables["sim"] = {"header": ["Level (communities)", "Retained, original", "Retained, RGI", "Evidence retrieved, original", "Evidence retrieved, RGI",
                            "Judged correct, original", "Judged correct, RGI"],
                 "rows": [[nm, pct(r["orig"]["retention"]), pct(r["prop"]["retention"]), pct(r["orig"]["retrieval"]), pct(r["prop"]["retrieval"]),
                           pct(r["orig"]["correct"]), pct(r["prop"]["correct"])] for nm, r in zip(names, sim["default"])]}
sw = sim["sweeps"]
def lv(name, i, L_, key, m="prop"):
    return pct(sw[name][i]["levels"][L_][m][key])
tables["sim_sweeps"] = {"header": ["Setting", "Leaf evidence retrieved (original)", "Leaf evidence retrieved (RGI)", "Root relationships retained (RGI)"],
                        "rows": [[f"Reports read K = {k}", lv("K", i, 0, "retrieval", "orig"), lv("K", i, 0, "retrieval"), lv("K", i, 3, "retention")] for i, k in enumerate((2, 3, 6))]
                        + [[f"Bridge share {b}", lv("bridgeShare", i, 0, "retrieval", "orig"), lv("bridgeShare", i, 0, "retrieval"), lv("bridgeShare", i, 3, "retention")] for i, b in enumerate(("0", "0.06", "0.12", "0.24"))]
                        + [[f"Bridge threshold weight {w}", lv("bridgeMinWeight", i, 0, "retrieval", "orig"), lv("bridgeMinWeight", i, 0, "retrieval"), lv("bridgeMinWeight", i, 3, "retention")] for i, w in enumerate(("3", "4", "5", "off"))]
                        + [[f"Full-item cutoff {f}", lv("fullCut", i, 0, "retrieval", "orig"), lv("fullCut", i, 0, "retrieval"), lv("fullCut", i, 3, "retention")] for i, f in enumerate(("0.6", "0.8", "1.0"))]
                        + [[f"Budget {b} tokens", lv("budget", i, 0, "retrieval", "orig"), lv("budget", i, 0, "retrieval"), lv("budget", i, 3, "retention")] for i, b in enumerate(("4,000", "8,000", "16,000"))]}
fig, ax = plt.subplots(figsize=(6.0, 2.4))
xs = np.arange(4)
o = [r["orig"]["retrieval"] for r in sim["default"]]; p = [r["prop"]["retrieval"] for r in sim["default"]]
ax.plot(xs, o, "--o", color=LOST, ms=5, lw=1.4, label="Original GraphRAG"); ax.plot(xs, p, "-o", color=KEPT, ms=5, lw=1.4, label="RGI")
ax.set_xticks(xs, ["Leaf", "Community", "Higher", "Root"]); ax.set_ylim(0.3, 1.0); ax.yaxis.set_major_formatter(PCT)
ax.set_ylabel("Evidence retrieved"); ax.legend(frameon=False, loc="lower center", ncol=2)
fig.savefig(OUT / "f_sim.png"); plt.close(fig)

(OUT / "tables.json").write_text(json.dumps(tables, indent=1))
(OUT / "macros.json").write_text(json.dumps(macros, indent=1))
print(len(tables), "tables;", len(macros), "macros;", sorted(p.name for p in OUT.glob("f_*.png")))

"""Turn paper/results into the figures, tables and number macros the paper inputs.

Nothing in paper/main.tex is typed by hand: every figure comes from
paper/figures/*.pdf and every number from paper/generated/*.tex.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "paper" / "results"
FIG = ROOT / "paper" / "figures"
GEN = ROOT / "paper" / "generated"
FIG.mkdir(exist_ok=True)
GEN.mkdir(exist_ok=True)

MAIN = "rgi_f0.8_b0.12_m2"
LEVEL_NAMES = {0: "0 (root)", 1: "1", 2: "2 (default)", 3: "3"}
INK, LOST, KEPT, EVID, GREY = "#1d1d1f", "#c2362d", "#17875a", "#3056d3", "#a1a1a6"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times", "Times New Roman", "DejaVu Serif"],
    "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "legend.fontsize": 7,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "pdf.fonttype": 42, "savefig.bbox": "tight", "savefig.pad_inches": 0.02,
})

macros: dict[str, str] = {}


def macro(name: str, value) -> None:
    macros[name] = str(value)


def pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}"


def num(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", "{,}")


def boot_mean(values: np.ndarray, B: int = 10000, seed: int = 20260815) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(B, len(values)))
    m = values[idx].mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


# ------------------------------------------------------------------ corpus
graph = pd.read_csv(RES / "graph_stats.csv")
meta = json.loads((RES / "census.json").read_text())
qs = json.loads((ROOT / "data" / "graphrag_bench" / "novel_questions.json").read_text())
macro("NNovels", len(graph))
macro("NChars", num(graph.chars.sum()))
macro("NTokens", num(graph.tokens.sum()))
macro("NUnits", num(graph.text_units.sum()))
macro("NRawEntities", num(graph.raw_entities.sum()))
macro("NRawRels", num(graph.raw_relationships.sum()))
macro("NEntities", num(graph.entities.sum()))
macro("NRels", num(graph.relationships.sum()))
macro("NCommunities", num(sum(graph[f"communities_l{i}"].sum() for i in range(5))))
macro("MeanDegree", f"{2 * graph.relationships.sum() / graph.entities.sum():.1f}")
macro("MedianDegree", f"{graph.mean_degree.median():.1f}")
macro("MaxLevelMax", int(graph.max_level.max()))
macro("NQuestions", num(len(qs)))
macro("RuntimeS", f"{meta['runtime_s']:.0f}")
macro("EquivChecks", meta["sort_context_equivalence_checks"])
macro("BigNovelShare", pct(graph.relationships.max() / graph.relationships.sum(), 0))

# ------------------------------------------------------------------ census
L = pd.read_csv(RES / "level_census.csv")
L["share"] = L.covered / L.relationships


def pooled(df: pd.DataFrame) -> pd.DataFrame:
    s = df.groupby(["level", "method"])[["relationships", "covered", "boundary", "budget_lost", "indirect", "outside",
                                         "via_compact", "via_bridge", "fallback", "regressions",
                                         "communities", "fits", "trimmed", "second_order", "passages", "facts", "bridges",
                                         "expo_scope", "expo_endpoint", "expo_elsewhere", "expo_absent", "expo_regressions"]].sum()
    s["share"] = s.covered / s.relationships
    return s


main8 = L[(L.budget == 8000) & L.method.isin(["graphrag", MAIN])]
P = pooled(main8)
rows = []
for lvl in range(4):
    g, r = P.loc[(lvl, "graphrag")], P.loc[(lvl, MAIN)]
    gm = main8[(main8.level == lvl) & (main8.method == "graphrag")].share.to_numpy()
    rm = main8[(main8.level == lvl) & (main8.method == MAIN)].share.to_numpy()
    lo, hi = boot_mean(rm - gm)
    rows.append((lvl, g, r, gm.mean(), rm.mean(), lo, hi))
    tag = "ABCD"[lvl]
    macro(f"Cov{tag}G", pct(g.share)); macro(f"Cov{tag}R", pct(r.share))
    macro(f"Bnd{tag}G", pct(g.boundary / g.relationships)); macro(f"Ind{tag}G", pct(g.indirect / g.relationships))
    macro(f"Bud{tag}G", num(g.budget_lost))
    macro(f"Macro{tag}G", pct(gm.mean())); macro(f"Macro{tag}R", pct(rm.mean()))
    macro(f"MacroDiff{tag}", pct(rm.mean() - gm.mean())); macro(f"MacroDiff{tag}Lo", pct(lo)); macro(f"MacroDiff{tag}Hi", pct(hi))
    macro(f"Bridge{tag}", num(r.via_bridge)); macro(f"Compact{tag}", num(r.via_compact))
    macro(f"Second{tag}", num(g.second_order)); macro(f"Comms{tag}", num(g.communities)); macro(f"Trim{tag}", num(g.trimmed))
for lvl in range(4):
    tag = "ABCD"[lvl]
    g, r = P.loc[(lvl, "graphrag")], P.loc[(lvl, MAIN)]
    for t, x in (("G", g), ("R", r)):
        macro(f"Abs{tag}{t}", pct(x.expo_absent / x.relationships))
        macro(f"Near{tag}{t}", pct((x.expo_scope + x.expo_endpoint) / x.relationships))
        macro(f"Else{tag}{t}", pct(x.expo_elsewhere / x.relationships))
        macro(f"Pass{tag}{t}", num(x.passages))
    macro(f"ExpoRegr{tag}", num(r.expo_regressions))
macro("ExpoRegrTotal", num(L[L.method == MAIN].expo_regressions.sum()))
m8 = L[(L.method == MAIN) & (L.budget == 8000)].groupby("level")[["expo_regressions", "relationships"]].sum()
macro("ExpoRegrEight", num(m8.expo_regressions.sum()))
macro("ExpoRegrMaxShare", f"{100 * (m8.expo_regressions / m8.relationships).max():.2f}")
macro("ExpoRegrAll", num(L[L.method.str.startswith("rgi")].expo_regressions.sum()))
macro("Regressions", int(L[L.method.str.startswith("rgi")].regressions.sum()))
macro("Fallbacks", int(L[L.method.str.startswith("rgi")].fallback.sum()))
macro("CensusConfigs", int(L[L.method.str.startswith("rgi")].shape[0]))
macro("MaxTokensRGI", num(L[(L.method.str.startswith("rgi")) & (L.budget == 8000)].max_tokens.max()))
macro("Outside", num(P.loc[(2, "graphrag")].outside))

with open(GEN / "tab_census.tex", "w") as f:
    f.write("\\setlength{\\tabcolsep}{4pt}\n\\begin{tabular}{@{}lrrrrrl@{}}\n\\toprule\n")
    f.write(" & \\multicolumn{4}{c}{GraphRAG (pooled)} & RGI & Mean gain \\\\\n")
    f.write("\\cmidrule(lr){2-5}\\cmidrule(lr){6-6}\n")
    f.write("Level & Scope & Bnd. & Sub. & Bud. & Scope & [95\\% CI] \\\\\n\\midrule\n")
    for lvl, g, r, gm, rm, lo, hi in rows:
        f.write(f"{lvl} & {pct(g.share)} & {pct(g.boundary / g.relationships)} & {pct(g.indirect / g.relationships)} & "
                f"{pct(g.budget_lost / g.relationships, 2)} & \\textbf{{{pct(r.share)}}} & +{pct(rm - gm)} [{pct(lo)}, {pct(hi)}] \\\\\n")
    f.write("\\bottomrule\n\\end{tabular}\n")

with open(GEN / "tab_exposure.tex", "w") as f:
    f.write("\\begin{tabular}{@{}llrrrr@{}}\n\\toprule\n")
    f.write("Level & Index & In scope & Endpoint & Elsewhere & Absent \\\\\n\\midrule\n")
    for lvl in range(4):
        for meth, nm in (("graphrag", "GraphRAG"), (MAIN, "RGI")):
            x = P.loc[(lvl, meth)]
            lead = LEVEL_NAMES[lvl] if meth == "graphrag" else ""
            f.write(f"{lead} & {nm} & {pct(x.expo_scope / x.relationships)} & {pct(x.expo_endpoint / x.relationships)} & "
                    f"{pct(x.expo_elsewhere / x.relationships)} & {pct(x.expo_absent / x.relationships)} \\\\\n")
        if lvl < 3:
            f.write("\\addlinespace\n")
    f.write("\\bottomrule\n\\end{tabular}\n")

# stacked bars: where every relationship ends up
fig, ax = plt.subplots(figsize=(3.45, 2.25))
cats = [("Full passage", "covered_passage", INK), ("Compact fact", "via_compact", "#5b5b60"), ("Bridge record", "via_bridge", KEPT),
        ("Boundary", "boundary", LOST), ("Sub-summary only", "indirect", "#e6a19b"), ("Budget", "budget_lost", "#7a1d17"),
        ("Outside LCC", "outside", GREY)]
labels, ypos = [], []
y = 0
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
        labels.append(f"Level {lvl}  {name}")
        ypos.append(y)
        y += 1
    y += 0.5
ax.set_yticks(ypos, labels)
ax.invert_yaxis()
ax.set_xlim(0, 1)
ax.set_xticks([0, .25, .5, .75, 1], ["0", "25", "50", "75", "100%"])
ax.set_xlabel("Share of all relationships (pooled over 20 novels)")
handles, labs = ax.get_legend_handles_labels()
ax.legend(handles, labs, ncol=4, loc="lower center", bbox_to_anchor=(0.42, 1.0), frameon=False, handlelength=1, columnspacing=0.8, fontsize=6)
fig.savefig(FIG / "fig_census.pdf")
plt.close(fig)

# budget sweep
fig, axes = plt.subplots(1, 2, figsize=(3.45, 1.55), sharey=True)
for ax, lvl in zip(axes, (2, 0)):
    for meth, col, name, ls in (("graphrag", LOST, "GraphRAG", "--"), (MAIN, KEPT, "RGI", "-")):
        d = L[(L.level == lvl) & (L.method == meth)].groupby("budget")[["covered", "relationships"]].sum()
        ax.plot(d.index, d.covered / d.relationships, ls, color=col, marker="o", ms=2.5, lw=1.1, label=name)
    ax.set_xscale("log", base=2)
    ax.set_xticks([4000, 8000, 16000, 32000], ["4k", "8k", "16k", "32k"])
    ax.set_title(f"Level {lvl}" + (" (default)" if lvl == 2 else " (root)"), pad=2)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{100 * v:.0f}%"))
axes[0].set_ylabel("Relationships in input")
axes[1].legend(frameon=False, loc="upper left")
fig.supxlabel("Summary input budget (tokens)", fontsize=8, y=-0.14)
fig.savefig(FIG / "fig_budget.pdf")
plt.close(fig)
for lvl in (0, 2):
    for b in (4000, 32000):
        for meth, t in (("graphrag", "G"), (MAIN, "R")):
            d = L[(L.level == lvl) & (L.method == meth) & (L.budget == b)]
            macro(f"Budget{'AC'[lvl // 2]}{ {4000: 'Four', 32000: 'ThirtyTwo'}[b] }{t}", pct(d.covered.sum() / d.relationships.sum()))

# ablations at level 2 and level 0
abl = L[(L.budget == 8000) & L.method.str.startswith("rgi")]
ABL_NAME = {"rgi_f0.8_b0_m2": "AblNoBridge", "rgi_f0.8_b0.06_m2": "AblBSix", MAIN: "AblMain", "rgi_f0.8_b0.24_m2": "AblBTwentyFour",
            "rgi_f0.6_b0.12_m2": "AblFSix", "rgi_f1_b0.12_m2": "AblFOne", "rgi_f0.8_b0.12_m1": "AblMOne", "rgi_f0.8_b0.12_m3": "AblMThree"}
order = [("rgi_f0.8_b0_m2", "No bridges ($b{=}0$)"), ("rgi_f0.8_b0.06_m2", "$b{=}0.06$"), (MAIN, "$b{=}0.12$ (default)"),
         ("rgi_f0.8_b0.24_m2", "$b{=}0.24$"), ("rgi_f0.6_b0.12_m2", "$f{=}0.6$"), ("rgi_f1_b0.12_m2", "$f{=}1.0$ (no compact tier)"),
         ("rgi_f0.8_b0.12_m1", "$m{=}1$"), ("rgi_f0.8_b0.12_m3", "$m{=}3$")]
with open(GEN / "tab_ablation.tex", "w") as f:
    f.write("\\begin{tabular}{@{}lrrrr@{}}\n\\toprule\n & \\multicolumn{2}{c}{Level 2 (default)} & \\multicolumn{2}{c}{Level 0 (root)} \\\\\n")
    f.write("\\cmidrule(lr){2-3}\\cmidrule(l){4-5}\nConfiguration & In input & Bridged & In input & Bridged \\\\\n\\midrule\n")
    g2, g0 = P.loc[(2, "graphrag")], P.loc[(0, "graphrag")]
    f.write(f"GraphRAG & {pct(g2.share)} & n/a & {pct(g0.share)} & n/a \\\\\n\\midrule\n")
    for meth, name in order:
        a2 = abl[(abl.level == 2) & (abl.method == meth)][["covered", "relationships", "via_bridge"]].sum()
        a0 = abl[(abl.level == 0) & (abl.method == meth)][["covered", "relationships", "via_bridge"]].sum()
        f.write(f"{name} & {pct(a2.covered / a2.relationships)} & {pct(a2.via_bridge / a2.relationships)} & "
                f"{pct(a0.covered / a0.relationships)} & {pct(a0.via_bridge / a0.relationships)} \\\\\n")
        macro(ABL_NAME[meth] + "A", pct(a2.covered / a2.relationships))
        macro(ABL_NAME[meth] + "C", pct(a0.covered / a0.relationships))
    f.write("\\bottomrule\n\\end{tabular}\n")

# chunk sensitivity at level 2
with open(GEN / "tab_chunk.tex", "w") as f:
    f.write("\\begin{tabular}{@{}rrrrrr@{}}\n\\toprule\nChunk & Mean & \\multicolumn{2}{c}{In input, level 2} & \\multicolumn{2}{c}{In input, level 0} \\\\\n")
    f.write("\\cmidrule(lr){3-4}\\cmidrule(l){5-6}\ntokens & degree & GraphRAG & RGI & GraphRAG & RGI \\\\\n\\midrule\n")
    for size, d in ((1200, RES), (600, RES / "chunk600"), (300, RES / "chunk300")):
        gs = pd.read_csv(d / "graph_stats.csv")
        lc = pd.read_csv(d / "level_census.csv")
        lc = lc[lc.budget == 8000]
        def share(lvl, meth):
            x = lc[(lc.level == lvl) & (lc.method == meth)][["covered", "relationships"]].sum()
            return x.covered / x.relationships
        deg = 2 * gs.relationships.sum() / gs.entities.sum()
        f.write(f"{size}{' (default)' if size == 1200 else ''} & {deg:.1f} & {pct(share(2, 'graphrag'))} & \\textbf{{{pct(share(2, MAIN))}}} & "
                f"{pct(share(0, 'graphrag'))} & \\textbf{{{pct(share(0, MAIN))}}} \\\\\n")
        cn = {1200: "Default", 600: "Six", 300: "Three"}[size]
        macro(f"Chunk{cn}G", pct(share(2, "graphrag"))); macro(f"Chunk{cn}R", pct(share(2, MAIN)))
        macro(f"Chunk{cn}Deg", f"{deg:.1f}")
        macro(f"Chunk{cn}Regr", int(lc[lc.method.str.startswith('rgi')].regressions.sum()))
    f.write("\\bottomrule\n\\end{tabular}\n")

# ------------------------------------------------------------------ selection loss (standard pipeline)
S = pd.read_csv(RES / "selection_loss.csv")
sa = S.groupby("level")[["communities", "entities", "intra", "intra_in_input", "bound", "cross_in_input"]].sum()
with open(GEN / "tab_selection.tex", "w") as f:
    f.write("\\begin{tabular}{@{}rrrrrr@{}}\n\\toprule\nLevel & Comm. & Intra rels & Reach input & Share & Cross rels in \\\\\n\\midrule\n")
    for lvl, r in sa.iterrows():
        f.write(f"{lvl} & {num(r.communities)} & {num(r.intra)} & {num(r.intra_in_input)} & {pct(r.intra_in_input / r.intra)}\\% & {num(r.cross_in_input)} \\\\\n")
    f.write("\\bottomrule\n\\end{tabular}\n")
macro("SelMin", pct((sa.intra_in_input / sa.intra).min()))
macro("SelMax", pct((sa.intra_in_input / sa.intra).max()))
macro("SelLZero", pct(sa.loc[0].intra_in_input / sa.loc[0].intra))
macro("SelLTwo", pct(sa.loc[2].intra_in_input / sa.loc[2].intra))
macro("SelCrossTotal", num(sa.cross_in_input.sum()))
macro("SelKeptTotal", num(sa.intra_in_input.sum()))

# ------------------------------------------------------------------ gold evidence
T = pd.read_csv(RES / "gold_triples.csv")
G = pd.read_csv(RES / "gold_questions.csv")
macro("NTriples", num(len(T)))
macro("TripleParsed", pct(T.parsed.mean()))
macro("TripleLinked", pct(T.linked.mean()))
macro("TripleRel", pct((T.n_rel > 0).mean()))
macro("UnlinkRate", pct(1 - T.linked.mean()))
macro("NGoldQ", num(G.qid.nunique()))
macro("GoldQShare", pct(G.qid.nunique() / len(qs)))
gold_rows = []
for lvl, d in G.groupby("level"):
    b = (d.base_covered < d.n_gold).astype(float).to_numpy()
    r = (d.rgi_covered < d.n_gold).astype(float).to_numpy()
    lo, hi = boot_mean(r - b)
    gold_rows.append((lvl, b.mean(), r.mean(), lo, hi, d.base_covered.sum() / d.n_gold.sum(), d.rgi_covered.sum() / d.n_gold.sum()))
    tag = "ABCD"[lvl]
    macro(f"GoldLost{tag}G", pct(b.mean())); macro(f"GoldLost{tag}R", pct(r.mean()))
    macro(f"GoldCov{tag}G", pct(d.base_covered.sum() / d.n_gold.sum())); macro(f"GoldCov{tag}R", pct(d.rgi_covered.sum() / d.n_gold.sum()))
    macro(f"GoldDiff{tag}Lo", pct(-hi)); macro(f"GoldDiff{tag}Hi", pct(-lo))
for lvl, d in G.groupby("level"):
    tag = "ABCD"[lvl]
    macro(f"GoldNear{tag}G", pct(d.base_endpoint.sum() / d.n_gold.sum())); macro(f"GoldNear{tag}R", pct(d.rgi_endpoint.sum() / d.n_gold.sum()))
    macro(f"GoldAny{tag}G", pct(d.base_any.sum() / d.n_gold.sum())); macro(f"GoldAny{tag}R", pct(d.rgi_any.sum() / d.n_gold.sum()))
    macro(f"GoldAbsQ{tag}G", pct((d.base_any < d.n_gold).mean())); macro(f"GoldAbsQ{tag}R", pct((d.rgi_any < d.n_gold).mean()))
d2 = G[G.level == 2]
with open(GEN / "tab_gold.tex", "w") as f:
    f.write("\\begin{tabular}{@{}lrrrr@{}}\n\\toprule\n & & \\multicolumn{2}{c}{$\\Pr[Y(q)\\cap L_\\ell\\neq\\emptyset]$} & \\\\\n\\cmidrule(lr){3-4}\n")
    f.write("Slice & $n$ & GraphRAG & RGI & Change [95\\% CI] \\\\\n\\midrule\n")
    for lvl, b, r, lo, hi, _, _ in gold_rows:
        f.write(f"Level {LEVEL_NAMES[lvl]} & {num(len(G[G.level == lvl]))} & {pct(b)} & {pct(r)} & $-${pct(b - r)} [{pct(-hi)}, {pct(-lo)}] \\\\\n")
    f.write("\\midrule\n\\multicolumn{5}{@{}l}{\\emph{Level 2 by question type}} \\\\\n")
    for typ, d in d2.groupby("type"):
        b = (d.base_covered < d.n_gold).mean(); r = (d.rgi_covered < d.n_gold).mean()
        f.write(f"{typ} & {num(len(d))} & {pct(b)} & {pct(r)} & $-${pct(b - r)} \\\\\n")
    f.write("\\bottomrule\n\\end{tabular}\n")

fig, ax = plt.subplots(figsize=(3.45, 1.45))
x = np.arange(4)
b = [g[1] for g in gold_rows]; r = [g[2] for g in gold_rows]
ax.bar(x - 0.18, b, 0.34, color=LOST, label="GraphRAG")
ax.bar(x + 0.18, r, 0.34, color=KEPT, label="RGI")
for i in range(4):
    ax.text(x[i] - 0.18, b[i] + 0.02, pct(b[i], 0), ha="center", fontsize=6)
    ax.text(x[i] + 0.18, r[i] + 0.02, pct(r[i], 0), ha="center", fontsize=6)
ax.set_xticks(x, [f"Level {LEVEL_NAMES[i]}" for i in range(4)])
ax.set_ylim(0, 1.12)
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{100 * v:.0f}%"))
ax.set_ylabel("Questions with a gold\nrelationship missing", fontsize=7)
ax.legend(frameon=False, ncol=2, loc="upper right", fontsize=6.5)
fig.savefig(FIG / "fig_gold.pdf")
plt.close(fig)

# ------------------------------------------------------------------ simulation
sim = json.loads((RES / "simulation.json").read_text())
macro("SimEntities", sim["corpus"]["entities"]); macro("SimRels", sim["corpus"]["relationships"])
macro("SimCoreEntities", sim["corpus"]["core_entities"]); macro("SimCoreRels", sim["corpus"]["core_relationships"])
macro("SimQuestions", sim["corpus"]["questions"]); macro("SimFeatured", sim["corpus"]["featured"])
with open(GEN / "tab_sim.tex", "w") as f:
    f.write("\\begin{tabular}{@{}lrrrrrr@{}}\n\\toprule\n & \\multicolumn{2}{c}{Retained} & \\multicolumn{2}{c}{Evidence retrieved} & \\multicolumn{2}{c}{Judged correct} \\\\\n")
    f.write("\\cmidrule(lr){2-3}\\cmidrule(lr){4-5}\\cmidrule(l){6-7}\nLevel & Orig. & RGI & Orig. & RGI & Orig. & RGI \\\\\n\\midrule\n")
    names = ["Leaf (22)", "Community (8)", "Higher (3)", "Root (1)"]
    for row, nm in zip(sim["default"], names):
        o, p = row["orig"], row["prop"]
        f.write(f"{nm} & {pct(o['retention'])} & {pct(p['retention'])} & {pct(o['retrieval'])} & {pct(p['retrieval'])} & {pct(o['correct'])} & {pct(p['correct'])} \\\\\n")
    f.write("\\bottomrule\n\\end{tabular}\n")
for i, row in enumerate(sim["default"]):
    tag = "ABCD"[i]
    macro(f"SimRet{tag}O", pct(row["orig"]["retention"])); macro(f"SimRet{tag}P", pct(row["prop"]["retention"]))
    macro(f"SimRtr{tag}O", pct(row["orig"]["retrieval"])); macro(f"SimRtr{tag}P", pct(row["prop"]["retrieval"]))
    macro(f"SimCor{tag}O", pct(row["orig"]["correct"])); macro(f"SimCor{tag}P", pct(row["prop"]["correct"]))
    macro(f"SimCI{tag}Lo", pct(row["retrieval_diff_ci"][0])); macro(f"SimCI{tag}Hi", pct(row["retrieval_diff_ci"][1]))
macro("SimRegr", sum(r["query_regressions"] + r["edge_regressions"] for r in sim["default"]))
sw = sim["sweeps"]
def leaf(cfgname, i, key="retrieval", m="prop"):
    return pct(sw[cfgname][i]["levels"][0][m][key])
def root(cfgname, i, key="retrieval", m="prop"):
    return pct(sw[cfgname][i]["levels"][3][m][key])
macro("SimKTwoO", leaf("K", 0, m="orig")); macro("SimKSixO", leaf("K", 2, m="orig"))
macro("SimKTwoP", leaf("K", 0)); macro("SimKSixP", leaf("K", 2))
macro("SimBMThree", leaf("bridgeMinWeight", 0)); macro("SimBMFive", leaf("bridgeMinWeight", 2))
macro("SimBMThreeC", leaf("bridgeMinWeight", 0, "correct")); macro("SimBMFiveC", leaf("bridgeMinWeight", 2, "correct"))
macro("SimBSSix", leaf("bridgeShare", 1)); macro("SimBSTwelve", leaf("bridgeShare", 2)); macro("SimBSTwentyFour", leaf("bridgeShare", 3))
macro("SimFCSix", root("fullCut", 0)); macro("SimFCOne", root("fullCut", 2))
macro("SimFCSixRet", root("fullCut", 0, "retention")); macro("SimFCOneRet", root("fullCut", 2, "retention"))
macro("SimBudFourO", root("budget", 0, "retention", "orig")); macro("SimBudSixteenO", root("budget", 2, "retention", "orig"))
macro("SimBudFourP", root("budget", 0, "retention")); macro("SimBudSixteenP", root("budget", 2, "retention"))

fig, ax = plt.subplots(figsize=(3.45, 1.45))
x = np.arange(4)
o = [r["orig"]["retrieval"] for r in sim["default"]]
p = [r["prop"]["retrieval"] for r in sim["default"]]
ax.plot(x, o, "--o", color=LOST, ms=3, lw=1.1, label="Original GraphRAG")
ax.plot(x, p, "-o", color=KEPT, ms=3, lw=1.1, label="RGI")
ax.set_xticks(x, ["Leaf", "Community", "Higher", "Root"])
ax.set_ylim(0.3, 1.0)
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{100 * v:.0f}%"))
ax.set_ylabel("Evidence retrieved", fontsize=7)
ax.legend(frameon=False, fontsize=6.5, loc="lower center", ncol=2)
fig.savefig(FIG / "fig_sim.pdf")
plt.close(fig)

with open(GEN / "macros.tex", "w") as f:
    f.write("% generated by paper/experiments/analyze.py; do not edit\n")
    for k, v in sorted(macros.items()):
        f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
print(f"{len(macros)} macros, figures: {sorted(p.name for p in FIG.glob('*.pdf'))}")

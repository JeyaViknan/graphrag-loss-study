"""Slide 16: among linked questions, those missing a gold relationship fall from 79.9% to
15.2% at level 2; the result holds across graph densities; which links are bridged
matters more than how much budget bridges get.

    .venv/bin/python paper/verify/slide16_gold_density_bridges.py            # from saved results, ~2 s
    .venv/bin/python paper/verify/slide16_gold_density_bridges.py --fresh    # re-run the census at three text-unit sizes, ~5 min
"""

import sys

import pandas as pd

from _common import MAIN, Checks, pct, provenance, results_dir

res = results_dir(16, "Among linked questions, those missing a gold relationship fall from 79.9% to 15.2% at level 2",
                  [("", ["census_rgi.py"]),
                   ("chunk600", ["census_rgi.py", "--chunk-size", "600", "--no-ablations"]),
                   ("chunk300", ["census_rgi.py", "--chunk-size", "300", "--no-ablations"])])
provenance(res, ["gold_triples.csv", "gold_questions.csv", "level_census.csv",
                 "chunk600/level_census.csv", "chunk300/level_census.csv"])

T = pd.read_csv(res / "gold_triples.csv")
G = pd.read_csv(res / "gold_questions.csv")
d2 = G[G.level == 2]
missing = lambda d, col: (d[col] < d.n_gold).mean()  # noqa: E731  share of questions with a gold relationship out of scope

c = Checks()
c.section("Linked questions missing at least one gold relationship, level 2 (%)",
          "share of questions whose gold relationships are not all in scope, GraphRAG vs RGI at B = 8,000")
c.add("All linked questions (n)", "840", str(d2.qid.nunique()))
c.add("All linked: GraphRAG", "79.9", pct(missing(d2, "base_covered")))
c.add("All linked: RGI", "15.2", pct(missing(d2, "rgi_covered")))
for typ, n, g, r in (("Complex Reasoning", "317", "84.5", "17.0"), ("Contextual Summarize", "183", "79.8", "13.7"),
                     ("Creative Generation", "52", "98.1", "15.4"), ("Fact Retrieval", "288", "71.5", "14.2")):
    d = d2[d2.type == typ]
    c.add(f"{typ} (n)", n, str(len(d)))
    c.add(f"{typ}: GraphRAG", g, pct(missing(d, "base_covered")))
    c.add(f"{typ}: RGI", r, pct(missing(d, "rgi_covered")))

c.section("Gold triples and the pre-registered linking limit",
          "parsed / linked at both ends / resolved to a graph relationship, over all gold triples")
c.add("Gold triples", "4,371", f"{len(T):,}")
c.add("Parse (%)", "99.3", pct(T.parsed.mean()))
c.add("Link at both ends (%)", "45.8", pct(T.linked.mean()))
c.add("Resolve to a graph relationship (%)", "29.8", pct((T.n_rel > 0).mean()))
c.add("Unlink rate (%)", "54.2", pct(1 - T.linked.mean()))
c.claim("Unlink rate is above the frozen 15% limit", 1 - T.linked.mean() > 0.15, "so this is a descriptive subset, not gate G2")

c.section("Robust to graph density: level 2 in-scope (%), B = 8,000",
          "text units of 1,200, 600 and 300 tokens; mean degree = 2 × relationships / entities")
for size, sub, deg, g, r in ((1200, "", "48.1", "12.4", "34.6"), (600, "chunk600", "31.0", "19.9", "43.6"),
                             (300, "chunk300", "19.2", "27.6", "57.0")):
    d = res / sub if sub else res
    gs = pd.read_csv(d / "graph_stats.csv")
    lc = pd.read_csv(d / "level_census.csv")
    lc8 = lc[(lc.budget == 8000) & (lc.level == 2)].groupby("method")[["covered", "relationships"]].sum()
    c.add(f"{size:,} tokens: mean degree", deg, f"{2 * gs.relationships.sum() / gs.entities.sum():.1f}")
    c.add(f"{size:,} tokens: GraphRAG", g, pct(lc8.loc["graphrag"].covered / lc8.loc["graphrag"].relationships))
    c.add(f"{size:,} tokens: RGI", r, pct(lc8.loc[MAIN].covered / lc8.loc[MAIN].relationships))
    regr = int(lc[lc.method.str.startswith("rgi")].regressions.sum())
    c.claim(f"{size:,} tokens: 0 regressions", regr == 0, f"{regr} relationships GraphRAG kept that RGI dropped")

c.section("Which links you bridge matters more than how much budget (level 2, in scope %)",
          "one RGI parameter changed at a time, B = 8,000")
L = pd.read_csv(res / "level_census.csv")
abl = L[(L.budget == 8000) & (L.level == 2)].groupby("method")[["covered", "relationships"]].sum()
s = lambda m: pct(abl.loc[m].covered / abl.loc[m].relationships)  # noqa: E731
c.add("Minimum support m = 3", "21.9", s("rgi_f0.8_b0.12_m3"))
c.add("Minimum support m = 1", "49.8", s("rgi_f0.8_b0.12_m1"))
c.add("Bridge share b = 6%", "29.4", s("rgi_f0.8_b0.06_m2"))
c.add("Bridge share b = 24%", "37.2", s("rgi_f0.8_b0.24_m2"))

sys.exit(c.report())

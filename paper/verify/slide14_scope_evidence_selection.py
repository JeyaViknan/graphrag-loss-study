"""Slide 14: evidence vanishes at the root, and the standard builder drops most
relationships before any budget.

    .venv/bin/python paper/verify/slide14_scope_evidence_selection.py            # from saved results, ~2 s
    .venv/bin/python paper/verify/slide14_scope_evidence_selection.py --fresh    # re-run everything, ~3-4 min
"""

import sys

import pandas as pd

from _common import Checks, pct, provenance, results_dir

res = results_dir(14, "Evidence vanishes at the root, and the standard builder drops most relationships before any budget",
                  [("", ["census_rgi.py", "--no-ablations"]), ("", ["selection_loss.py"])])
provenance(res, ["level_census.csv", "selection_loss.csv"])

L = pd.read_csv(res / "level_census.csv")
g8 = L[(L.method == "graphrag") & (L.budget == 8000)].groupby("level").sum(numeric_only=True)
S = pd.read_csv(res / "selection_loss.csv")
sel = S.groupby("level")[["intra", "intra_in_input", "cross_in_input"]].sum()

c = Checks()
names = {0: "L0 root", 1: "L1", 2: "L2 default", 3: "L3"}

c.section("Scope vs evidence, by level (% of relationships)",
          "GraphRAG at B = 8,000, pooled over all novels: boundary / relationships and expo_absent / relationships")
for lvl, boundary, absent in ((0, "47.2", "87.6"), (1, "71.8", "38.5"), (2, "84.9", "0.4"), (3, "87.9", "0.1")):
    x = g8.loc[lvl]
    c.add(f"{names[lvl]}: lost at a boundary (scope)", boundary, pct(x.boundary / x.relationships))
    c.add(f"{names[lvl]}: no evidence in any input", absent, pct(x.expo_absent / x.relationships))
x = g8.loc[2]
c.add("Level 2: supporting text in a relevant input", "88.2", pct((x.expo_scope + x.expo_endpoint) / x.relationships))

c.section("Standard builder pass rate, by level (%)",
          "GraphRAG's own build_local_context run unchanged: within-community relationships that reach the input / all of them")
for lvl, shown in enumerate(("4.6", "5.3", "6.3", "9.4", "14.3", "16.3")):
    c.add(f"L{lvl}", shown, pct(sel.loc[lvl].intra_in_input / sel.loc[lvl].intra))
c.add("Cross-community records let in instead", "8,702", f"{int(sel.cross_in_input.sum()):,}")
within = int((S.intra_in_input <= S.bound).sum())
c.claim("One record per entity: never more than the bound (P3)", within == len(S),
        f"{within} of {len(S)} novel × level rows within the bound")

sys.exit(c.report())

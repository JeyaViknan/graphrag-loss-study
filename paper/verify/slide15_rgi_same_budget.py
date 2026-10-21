"""Slide 15: at the same budget, RGI lifts the default-level in-scope share from 12.4% to 34.6%.

    .venv/bin/python paper/verify/slide15_rgi_same_budget.py            # from saved results, ~2 s
    .venv/bin/python paper/verify/slide15_rgi_same_budget.py --fresh    # re-run the census, ~2.5 min
"""

import json
import sys

import pandas as pd

from _common import MAIN, Checks, boot_mean, pct, provenance, results_dir

res = results_dir(15, "At the same budget, RGI lifts the default-level in-scope share from 12.4% to 34.6%",
                  [("", ["census_rgi.py"])])
provenance(res, ["level_census.csv"])

L = pd.read_csv(res / "level_census.csv")
L["share"] = L.covered / L.relationships
at8 = L[L.budget == 8000]
pooled = at8.groupby(["level", "method"])[["covered", "relationships"]].sum()
share = lambda lvl, m: pooled.loc[(lvl, m)].covered / pooled.loc[(lvl, m)].relationships  # noqa: E731

c = Checks()
c.section("Relationships in scope, by level (%, B = 8,000)",
          "covered / relationships, pooled over all novels, for GraphRAG and for RGI at the same budget")
for lvl, name, g, r in ((0, "Level 0 (root)", "1.9", "12.4"), (1, "Level 1", "7.8", "27.4"),
                        (2, "Level 2 (default)", "12.4", "34.6"), (3, "Level 3", "12.1", "35.6")):
    c.add(f"{name}: GraphRAG", g, pct(share(lvl, "graphrag")))
    c.add(f"{name}: RGI (same budget)", r, pct(share(lvl, MAIN)))

c.section("Mean gain per novel at level 2",
          "RGI share minus GraphRAG share for each novel, averaged; 95% bootstrap interval over novels (10,000 resamples)")
lv2 = at8[at8.level == 2]
gm = lv2[lv2.method == "graphrag"].set_index("novel").share
rm = lv2[lv2.method == MAIN].set_index("novel").share.reindex(gm.index)
diff = (rm - gm).to_numpy()
lo, hi = boot_mean(diff)
c.add("Mean gain (points)", "+24.6", "+" + pct(diff.mean()))
c.add("95% CI, lower", "20.5", pct(lo))
c.add("95% CI, upper", "28.3", pct(hi))

c.section("Novels improved at level 2")
improved = int((rm > gm).sum())
c.add("Novels improved", "19 / 20", f"{improved} / {len(gm)}")
rels = lv2[lv2.method == "graphrag"].set_index("novel").relationships
for novel in gm.index[~(rm > gm)]:
    c.add(f"The other novel ({novel}): relationships", "33", str(int(rels[novel])))
    c.claim("  and its share was already equal", abs(rm[novel] - gm[novel]) < 1e-12,
            f"GraphRAG {pct(gm[novel])}% = RGI {pct(rm[novel])}%")

c.section("Regressions",
          "relationships GraphRAG kept in scope that RGI dropped, over every novel × level × budget × configuration")
rgi = L[L.method.str.startswith("rgi")]
c.add("Regressions / configurations", "0 / 880", f"{int(rgi.regressions.sum())} / {len(rgi)}")

c.section("Budget: RGI at 4k against GraphRAG at 32k (level 2)")
lvl2 = L[L.level == 2].groupby(["method", "budget"])[["covered", "relationships"]].sum()
c.add("RGI at 4,000 tokens", "26.5", pct(lvl2.loc[(MAIN, 4000)].covered / lvl2.loc[(MAIN, 4000)].relationships))
c.add("GraphRAG at 32,000 tokens", "14.9", pct(lvl2.loc[("graphrag", 32000)].covered / lvl2.loc[("graphrag", 32000)].relationships))

c.section("Footnote: cost of the two-tier layout")
m8 = L[(L.method == MAIN) & (L.budget == 8000)].groupby("level")[["expo_regressions", "relationships", "regressions"]].sum()
c.add("Cases that lose incidental visibility", "570", f"{int(m8.expo_regressions.sum()):,}")
c.add("Largest share at any level (%)", "0.21", f"{100 * (m8.expo_regressions / m8.relationships).max():.2f}")
c.claim("None of them leaves scope", int(m8.regressions.sum()) == 0, f"{int(m8.regressions.sum())} relationships left scope")
over = rgi[rgi.max_tokens > rgi.budget]
c.claim("Same token budget: no RGI input exceeds B", over.empty,
        f"{len(over)} of {len(rgi)} configurations over budget; largest input at B = 8,000 is "
        f"{int(rgi[rgi.budget == 8000].max_tokens.max()):,} tokens")
llm = json.loads((res / "census.json").read_text())["llm_calls"]
c.claim("Zero extra LLM calls", llm == 0, f"census.json records {llm} LLM calls")

sys.exit(c.report())

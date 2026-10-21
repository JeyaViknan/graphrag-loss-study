# Slide verification

Each script recomputes every number and claim on one review slide from the census's raw result files. It prints the slide's value next to the recomputed one and marks each line ✓ or ✗. A script exits with code 0 only if everything matches.

Run them from the repository root:

| Slide | What it checks | Command | Time |
|:--|:--|:--|:--|
| 14 | Boundary loss and missing evidence by level; the standard builder's pass rate; the 2/d̄ bound | `.venv/bin/python paper/verify/slide14_scope_evidence_selection.py` | ~2 s |
| 15 | In-scope share for GraphRAG and RGI; the mean gain and its 95% CI; 19/20 novels; 0/880 regressions; 4k against 32k; budget and LLM-call claims | `.venv/bin/python paper/verify/slide15_rgi_same_budget.py` | ~2 s |
| 16 | Gold questions by type; gold-triple linking; density sensitivity; the m and b ablations | `.venv/bin/python paper/verify/slide16_gold_density_bridges.py` | ~2 s |

## Re-running the experiments first

Add `--fresh` to any command. It re-runs the experiments from the raw novels through GraphRAG 3.1.1's own indexing code, writes them to a new temporary folder, and checks the slide against that fresh output. The saved results in `paper/results/` are not changed, and no language model is called.

| Slide | What `--fresh` re-runs | Measured time |
|:--|:--|:--|
| 14 | Census without ablations (~2 min), plus the standard-builder selection analysis (~10 min) | ~12 min |
| 15 | Full census, including the ablations behind the 880 configurations | ~3 min |
| 16 | Full census, plus the 600- and 300-token sensitivity runs | ~6 to 11 min |

Times were measured on a MacBook Air on 21 October 2026, and all three fresh runs reproduced every value on their slides. For a live demonstration, use `--fresh` on slide 15 only.

## How the numbers are computed

The scripts use the same definitions as `paper/experiments/analyze.py`. They read only the raw CSV files and never the generated numbers in `paper/generated/macros.tex`.

| Quantity | Definition |
|:--|:--|
| Shares | Pooled over all 20 novels at B = 8,000 |
| Mean gain per novel | Uses the bootstrap from `analyze.py`: 10,000 resamples, seed 20260815 |
| File fingerprints | Each script prints the SHA-256 of the result files it read, so you can show which data it used |

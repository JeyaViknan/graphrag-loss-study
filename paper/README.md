# Paper: Residual Graph Indexing

`main.tex` is written for IEEE Access, using the official LaTeX template (`ACCESS_latex_template_20260513`, from the journal's "Preparing Your Article" page). The template's class, logos and fonts sit next to `main.tex`: `ieeeaccess.cls`, `IEEEtran.cls`, `IEEEtran.bst`, `spotcolor.sty`, `logo.png`, `notaglinelogo.png`, `bullet.png` and the `t1*` font files. Upload all of them with the paper if you build it on Overleaf. The downloaded zip is kept in `ieeeaccess_dl/`.

After the abstract, the body has five numbered sections: Introduction, Related Work, Proposed Methodology, Results and Discussion, and Conclusion. The Acknowledgment, References and author biographies follow; the photos are in `photos/`. The earlier IEEEtran journal version is kept in `previous_ieeetran/`.

Every figure comes from `figures/`, and every number in the text and tables is a macro in `generated/`, written by the analysis script.

## Reproduce

From the repository root, with the project's virtual environment:

```bash
TIKTOKEN_CACHE_DIR=$PWD/.cache/tiktoken .venv/bin/python paper/experiments/census_rgi.py
.venv/bin/python paper/experiments/census_rgi.py --chunk-size 600 --no-ablations
.venv/bin/python paper/experiments/census_rgi.py --chunk-size 300 --no-ablations
.venv/bin/python paper/experiments/selection_loss.py
node paper/experiments/sim_sweep.js
.venv/bin/python paper/experiments/analyze.py
cd paper && pdflatex main && bibtex main && pdflatex main && pdflatex main
```

The first command needs the `o200k_base` encoding once; it is cached in `.cache/tiktoken`. No step calls an LLM.

## Files

| Path | What it does |
|:--|:--|
| `experiments/census_rgi.py` | Indexes each GraphRAG-Bench novel with GraphRAG 3.1.1's fast pipeline, then records every relationship's status and evidence tier under GraphRAG and RGI. Also links the gold triples. |
| `experiments/selection_loss.py` | Runs GraphRAG's standard summary-input builder and counts which relationships reach each input. |
| `experiments/sim_sweep.js` | Re-runs the GraphRAG X-Ray simulation (`demo/`) under every configuration. |
| `experiments/analyze.py` | Writes `figures/*.pdf`, `generated/tab_*.tex` and `generated/macros.tex`. |
| `results/` | Raw CSV and JSON outputs. |
| `PUBLICATION_PLAN.md` | Venues, gaps and the recommended route to publication. |

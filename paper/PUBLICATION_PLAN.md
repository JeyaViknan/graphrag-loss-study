# Publication plan for the RGI paper

Written 13 October 2026. Deadlines move and some below come from third-party trackers, so confirm each one on the venue's own call for papers before planning around it.

## Where the paper stands

A reviewer will see four strengths:

- The census is exact and reproducible. It runs GraphRAG 3.1.1's own code on a public benchmark, makes no model calls, and finishes in under three minutes.
- The selection finding is concrete and checkable. GraphRAG's standard summary-input builder admits 4.6% to 16.3% of within-community relationships, and the paper ties this to a specific function and an open issue (microsoft/graphrag #2583).
- The method comes with stated guarantees, and every run checks them: 0 regressions and 0 fallbacks across 880 configuration runs.
- The kill thresholds were committed to git before any data existed.

A reviewer will also find four gaps, and main-track venues will reject on the first one:

1. **No answer-level result on a real LLM-built index.** The simulation is synthetic. Top venues will expect gates G1 to G4 to be run.
2. The entity extractor is a substitute, because NLTK's data could not be downloaded on this network.
3. The census covers one corpus (Novel). Medical is the natural replication.
4. The fast-pipeline graphs are dense (mean degree 48), which inflates boundary and selection loss. The chunk-size sensitivity analysis bounds this effect but doesn't remove it.

The current draft is honest about all four. That makes it publishable now as a measurement paper or a workshop paper, but not yet as a main-track method paper.

## Options, from fastest to most demanding

| Route | Format | Fit now | What it needs first |
|:--|:--|:--|:--|
| arXiv preprint (cs.IR, cross-list cs.CL) | Any | Yes | An arXiv endorser if this is your first cs submission |
| Comment on GraphRAG issue #2583 with the selection numbers | n/a | Yes | Nothing; it builds visibility and goodwill with the maintainers |
| Workshop on RAG or knowledge graphs (at SIGIR, CIKM, KDD, ACL, EMNLP or NeurIPS) | Usually 4 to 8 pages, venue template | Yes | A shorter version; check each call for dates and page limits |
| IEEE conferences (IEEE BigData and its workshops, IEEE ICDM workshops, IEEE ICKG, regional IEEE conferences) | IEEE two-column; the draft is now in IEEE journal format, and switching back to the conference class is one line | Mostly | Remove the biographies (conferences do not use them) and trim to the page limit (often 6 to 8 pages plus references). ICKG 2026's deadline was 19 June 2026, so the next cycle is 2027 |
| IEEE Access (journal) | IEEE | After the LLM run | Gates G1 to G4. The APC is USD 2,160 on IEEE's 2026 list. Review focuses on technical soundness, and a first decision typically takes about 4 to 6 weeks |
| SIGIR 2027 (short or reproducibility/resource track) | ACM template | After the LLM run | Answer-level evidence. Trackers list the full-paper deadline as mid-to-late January 2027 (14 or 22 January, unconfirmed); short and resource tracks have historically come a few weeks later |
| ACL 2027 via ACL Rolling Review | ACL template | After the LLM run | Answer-level evidence. ACL 2027 is in Kyoto, 17 to 22 August 2027; the last ARR window is expected around January 2027 (unofficial) |
| ECIR 2027 | Springer LNCS | No | Its main deadlines (September and October 2026) have passed |

Changing templates is cheap because the paper is LaTeX and every number is a generated macro. For double-blind venues, remove the author block, the repository path and the commit hashes, or point to an anonymized copy of the repository.

## Recommended path

1. **Now, for the final report:** use this draft as it stands. It says clearly what is measured and what is simulated.
2. **Within two to three weeks:** fill in the remaining placeholders (see the checklist below), then post it to arXiv. Post the selection-loss numbers on issue #2583.
3. **Before the next submission:** fix the API key and build the LLM index of Novel. Run G1 to G4 with the two annotators, and re-run the census with GraphRAG's default extractor on a network that can reach NLTK's data. Add the Medical corpus if time allows.
4. **Then submit to one of these:**
   - a SIGIR 2027 short paper, if G4 shows a real oracle-minus-placebo effect by mid-January
   - a RAG or knowledge-graph workshop at SIGIR or ACL 2027, if the effect is small or mixed
   - IEEE Access, for the full journal version with everything included

   If a gate fires, the result is still publishable as a careful null at a workshop or in a negative-results track. The pre-registration is what makes such a null credible.

## Before any submission

- Fill in what is still bracketed in `main.tex`: the running head (journal name, volume, number, month), Aatreye Dev's degree year and research interests, and the acknowledgment. Replace the placeholder images in `photos/` with real photos under the same file names.
- Confirm the venue's page limit. The current draft is 12 pages in the IEEE Access template; the earlier IEEEtran journal version (11 pages) is in `previous_ieeetran/`.
- Re-run `paper/experiments/analyze.py` after any new data, then rebuild. The text has no hand-typed numbers.
- Check the venue's preprint policy if you post to arXiv first. IEEE generally allows preprints, but confirm it for the specific venue.

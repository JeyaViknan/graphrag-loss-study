# Conclusion and Future Work {#ch:conclusion}

## Conclusion {#sec:conclusion}

With community-summary GraphRAG, what can be known about a corpus is settled before anyone asks a question. Our aim was to find where in the pipeline that happens and how much content is discarded there, and then to change the index so the discarded content is kept, or at least recorded, while GraphRAG's summaries, budget and search stay as they are.

We found five places where relationships leave the path to an answer: community boundaries, the input budget, the selection step of the standard input builder, the summarization of large communities from their children's summaries, and entities that are never clustered. Running GraphRAG 3.1.1's own indexing code on all twenty novels of GraphRAG-Bench Novel, with no language model, we measured each of them exactly. At the default query level the summary inputs keep {CovCG}% of {NRels} relationships in scope. At the root, {AbsAG}% of relationships have no evidence in any input at all. The standard input builder passes only {SelMin}% to {SelMax}% of within-community relationships into its inputs, before the budget is even applied.

Residual Graph Indexing keeps GraphRAG's summaries and search as they are, spends the same budget differently, and keeps an account of every relationship. At the default level it raises the in-scope share from {CovCG}% to {CovCR}%, a mean gain of {MacroDiffC} points per novel with a 95% confidence interval of {MacroDiffCLo} to {MacroDiffCHi}. It never dropped a relationship that GraphRAG kept, never exceeded the budget and never needed its fallback, across {CensusConfigs} combinations of novel, level, budget and configuration. Whether that changes answers is the question the pre-registered protocol was built to settle, and it remains open.

## Objectives revisited {#sec:objectives-revisited}

[@tab:objectives] compares the outcome with each objective set in [@sec:objectives]. Four objectives were met in full. Two were met in part, and in both cases the missing part is the language model run.

!table[tab:objectives]{w=3.3,1.0,2.6} Objectives and outcomes
| Objective | Status | Evidence |
| Model of index-time loss with scope and evidence separated | Met | Loss model, evidence tiers and three propositions ([@sec:loss-model], [@sec:props]) |
| Tested toolkit with thresholds frozen before data | Met | Nine modules, ten scripts, 166 passing tests; thresholds committed on 15 August 2026 |
| Exact census on GraphRAG-Bench Novel with GraphRAG's own code | Met, with one substitution | All 20 novels, four levels, four budgets; substitute extractor disclosed |
| RGI with stated guarantees, checked on every run | Met | Zero regressions, zero fallbacks, certificate held on every run |
| Estimate how much lost content questions need | Partly met | {NGoldQ} linked questions analysed; unlink rate {UnlinkRate}% rules out gate G2 |
| Simulator showing effects on retrieval and answers | Met for the simulation | GraphRAG X-Ray with typed questions; answer effects are synthetic |

## What the project showed {#sec:insights}

Some findings were not obvious when the work began.

The first is that boundary loss and evidence loss are different problems. We expected the fine levels of the hierarchy to be where content disappears, because that is where the boundaries are. In the fast pipeline, though, the text that supports a boundary relationship almost always still reaches some summarizer at those levels. The real absence of evidence is at the coarse levels, where large communities are written from their children's summaries. A claim that content is unreachable has to be made about the second problem, not the first.

The second is the selection behaviour of the standard input builder. We set out to measure the effect of the budget, and found that the builder removes most within-community relationships before the budget plays any part, because it keeps one relationship per entity. The effect depends strongly on graph density, and Proposition 3 gives a simple way to estimate it.

A third finding was about where effort is best spent. In the census and in the simulation alike, the choice of which relationships to bridge made far more difference than the amount of budget the bridges received. At fine levels, RGI working with half the default budget kept more relationships in scope than GraphRAG did with four times the default, so putting content explicitly into the right inputs did more good than simply giving the inputs more room.

The fourth finding concerns benchmarks. In GraphRAG-Bench the gold evidence sentences restate the source text instead of quoting it, and more than half of the gold triples cannot be linked to an automatically extracted graph. We discovered this before running any gate, because the linking rule and its failure threshold had been written down beforehand. If we had tuned the linking after looking at the results, the gold analysis would have looked stronger, but part of that strength would have come from the tuning.

## Limitations {#sec:limitations}

The biggest limitation is that answer accuracy was never measured on a real index built by a language model. The team's API key failed validation, and a free tier could not have handled the number of calls the study needs. Every part of the work that does not depend on the model was completed and the rest was prepared, but the central claim, that the lost content changes answers, is still untested on real data.

The census has three further limits. We could not install GraphRAG's default noun-phrase extractor and used a substitute that keeps its output format without reproducing all of its behaviour. The graphs from the fast pipeline are also much denser than graphs extracted by a language model usually are, which makes boundary and selection loss larger, although the sensitivity runs show RGI's gain holding as density falls. Finally, the gold-evidence analysis covers only a biased subset of the questions.

Two parts of the planned toolkit have not been verified yet. The truncation replay needs a written reading of GraphRAG's summarization code, which was started but is unfinished, and the NLI model chosen for gate G1 has not yet been loaded under the installed version of the transformers library. The simulator's effects on answers, as noted before, come from a judge we wrote and should be read as an illustration of the mechanism.

## Future work {#sec:future}

Most of what remains to be done comes straight from the limits listed above:

1. Build an index of GraphRAG-Bench Novel with a language model and run the four gates in their fixed order, with the two annotators for G1 and G3. This settles whether index-time loss changes answers, by question type.
2. Compare GraphRAG, RGI, RGI with placebo residuals and LightRAG at equal token counts, and replicate the study on the Medical corpus of GraphRAG-Bench.
3. Implement query-time residual retrieval in full and measure what the stored facts add beyond the summaries, with the token-exact swap already in the toolkit.
4. Replace the fixed bridge rule with an allocation that depends on the level, or with a salience score learned from past questions.
5. Add short pointers that let multi-topic entities appear in the communities they were not filed under, which is the one form of loss RGI does not address.
6. Repeat the census with GraphRAG's default extractor once its data can be installed, and with a sparser graph extracted by a language model.
7. Share the selection measurements with the GraphRAG maintainers on the open issue, and prepare the research paper for publication, first as a preprint and then at a venue once the answer-level results are in.

## Benefits of the work {#sec:benefits}

The work is useful even before the answer-level test is run. Anyone who builds a GraphRAG index can run the audit and learn, for their own corpus and configuration, how much of the extracted graph their summaries can never see, and through which mechanism. The coverage certificate turns an invisible loss into a recorded one. RGI costs no extra model calls and no extra tokens, so it can be adopted without changing the economics of an index. The census, the toolkit and the simulator are all reproducible from public data on an ordinary laptop, which makes the findings easy to check and to extend.

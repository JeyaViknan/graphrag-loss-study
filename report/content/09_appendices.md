# Appendices

## Pre-registered kill criteria {#app:gates}

The definitions in this appendix are the ones committed to the project repository on 15 August 2026, before any data were collected, and the thresholds themselves are in [@tab:gates]. Writing the definitions down in advance leaves no room to argue, once the data are in, that a gate which fired did not really fire. Gates G1 to G3 fire on their point estimates and G4 on its confidence interval. When a gate fires the study stops at that point: the claim it protects is dropped, the later experiments are not run, and the result is reported as a null.

Gate G1 uses 300 relationships drawn from the permanent cross edges, those that no level contains, stratified by relationship weight into four quartiles of 75 each. For each one, the premise is the passages about its two entities taken from the reports of the two communities involved, and the hypothesis is the relationship's own description. The metric is the share classified as entailed by the NLI model, reported overall and per quartile with bootstrap intervals. The NLI model may not be used until two human annotators have labelled 100 items and reached a Cohen's kappa of at least 0.7.

Gate G2 measures the share of benchmark questions whose gold set intersects the loss set. The loss set for this gate includes boundary and budget loss only. Multi-topic loss is excluded by construction, because a misassigned entity is still read by global search, in the wrong framing. The gate is reported as inconclusive if more than 15% of gold items fail to link.

Gate G3 measures the share of failed answers assigned to the category "index-absent", where a failure that fits several categories is assigned the earliest one in the pipeline. Two annotators label the first 50 failures independently; below a kappa of 0.7 the automated classifier is not used.

Gate G4 is the paired difference in accuracy between the oracle and placebo arms over the same questions, with a 95% bootstrap interval from at least 1,000 resamples by question, reported with McNemar's test and Cohen's h. Its preconditions run in a fixed order: the injection must be token-exact on 50 random examples, then the placebo arm runs, then the oracle arm.

In the same commit we also fixed what would count as a strong result, so that the meaning of "strong" could not be changed after the numbers came in. These markers, listed in [@tab:strength], do not stop the study. They only set how strongly its findings may be stated.

!table[tab:strength]{w=4.2,1.2,1.4} Strength markers committed with the gates
| Measurement | Weak | Strong |
| G1 recoverability on high-weight edges | n/a | below 40% |
| G2 share of questions needing lost content | n/a | above 25% |
| G3 share of index-absent failures | n/a | the largest category |
| G4 oracle minus placebo | n/a | above 5 points |
| E1 weighted share of cross edges at the operating level | above 8% | above 25% |
| E4 leaf communities overflowing at 8,000 tokens | above 20% | still above at 16,000 |
| E3 multi-topic rate among entities in gold evidence | above 15% | plus a clear partial correlation with degree |

Later that day a second commit froze the linking parameters used by gate G2, along with the tokenizer used throughout the study; both are given in [@tab:linkparams].

!table[tab:linkparams]{w=2.4,4.4} Frozen linking parameters
| Parameter | Frozen value |
| Strategy | Link gold triples (the sentence strategy is kept but not run) |
| Scorer | RapidFuzz `token_set_ratio` |
| Threshold | At least 85, for both head and tail |
| Matched against | Entity titles |
| Normalization | Lowercase, punctuation removed, whitespace collapsed |
| Candidate entities | Restricted to the question's own novel |
| Tokenizer for all token counts | tiktoken `o200k_base` |

## RGI summary-input construction {#app:code}

Below is the part of the census script that builds a single RGI summary input, following the algorithm in [@sec:rgi-design]. To fit the page we wrapped long lines and shortened a few helper calls, without changing the logic.

```
# GraphRAG's own input for this community: mode, admitted units, tokens
mode, k_base, base_tokens = base[cid]
facts = []
if mode == "fits":
    k, used = k_base, base_tokens    # keep everything; slack goes to bridges
    pending = []
elif mode == "trimmed":
    k = (ctx.admit(key, recs, int(budget * rgi.full_cut))
         if rgi.full_cut < 1 else k_base)
    k = min(k, k_base)
    used = ctx.tokens(key, recs, k)
    have = covered_by(cid, k)
    base_cov = covered_by(cid, k_base)
    # monotonicity: what GraphRAG's own prefix represented is written first
    reserved = sorted(base_cov - have, key=prio.get)
    rest = sorted(set(c["intra"]) - base_cov, key=prio.get)
    cost = (tok.n(FACTS_HDR) if reserved else 0) + sum(
        tok.n(line(r)) + 1 for r in reserved)
    if used + cost > budget:                 # fallback to GraphRAG's own prefix
        fallback += 1
        k, used, reserved = k_base, base_tokens, []
    facts.extend(reserved)
    pending = rest
else:  # input built from child summaries: they get f*B, the tail is ours
    k, used = 0, int(budget * rgi.full_cut)
    pending = sorted(c["intra"], key=prio.get)

# bridge records: boundary relationships of this community, by priority
bridges, spent = [], 0
allowance = min(budget * rgi.bridge_share, budget - used_after_facts)
for r in sorted((r for r in boundary_of[cid]
                 if n_units(r) >= rgi.bridge_min_units), key=prio.get):
    cost = tok.n(line(r)) + 1 + (0 if bridges else tok.n(BRIDGE_HDR))
    if spent + cost > allowance:
        break
    bridges.append(r)
    spent += cost

# compact facts for in-scope relationships still missing, up to the budget
for r in pending:
    cost = tok.n(line(r)) + 1
    if used_after_bridges + cost > budget:
        break
    facts.append(r)
    used_after_bridges += cost

# exact check on the rendered text; drop trailing facts if merges overflow
total = tok.n(render(k, bridges, facts)) + (int(budget * rgi.full_cut)
                                            if mode == "second_order" else 0)
while total > budget and facts:
    facts.pop()
    total = tok.n(render(k, bridges, facts)) + ...
assert total <= budget
```

After every community has been built, the script assigns each relationship to the represented, bridged or stored set and checks the coverage certificate:

```
residual = {rid for rid, s in rstatus.items() if s != "covered"}
certificate = (set(how) | residual) == set(all_relationship_ids) \
              and not (set(how) & residual)
regressions = sum(1 for rid, s in status.items()
                  if s == "covered" and rstatus[rid] != "covered")
assert certificate
```

## Census output files {#app:outputs}

Each census run writes four tables. They are described in [@tab:outputs], and the columns of the main table are listed in [@tab:census-cols].

!table[tab:outputs]{w=2.2,4.6} Files written by the census
| File | One row per |
| `graph_stats.csv` | Novel: text units, tokens, extracted and pruned entities and relationships, communities per level, removed most-connected entity |
| `level_census.csv` | Novel, level, budget and method: counts of every status, tier and RGI component, plus checks |
| `gold_triples.csv` | Gold triple: whether it parsed and linked, its score and the number of relationships it resolved to |
| `gold_questions.csv` | Question and level: gold relationships in scope under GraphRAG and RGI, by status and tier |

!table[tab:census-cols]{w=2.0,4.8} Main columns of the level census
| Column | Meaning |
| `covered`, `boundary`, `budget_lost`, `indirect`, `outside` | Relationships with each status (indirect means sub-summary) |
| `via_bridge`, `via_compact` | Relationships brought into scope by bridge records and by compact facts |
| `fits`, `trimmed`, `second_order` | Selected communities whose input fits, is cut, or is built from child summaries |
| `passages`, `facts`, `bridges` | Text units, compact facts and bridge records placed in inputs |
| `expo_scope`, `expo_endpoint`, `expo_elsewhere`, `expo_absent` | Relationships in each evidence tier |
| `max_tokens`, `mean_tokens` | Largest and mean input size in tokens |
| `regressions`, `fallback`, `certificate` | Checks on RGI's guarantees |

## GraphRAG X-Ray user guide {#app:xray}

Nothing has to be installed to use the simulator. It is enough to open `demo/index.html` in a modern browser, or to serve the folder locally with `python3 -m http.server` and open the address it prints. The controls are summarized in [@tab:xray-controls].

!table[tab:xray-controls]{w=2.2,4.6} Controls of GraphRAG X-Ray
| Control | Effect |
| Question menu | Choose one of the five featured questions, or type a question about the novel |
| Method panel, or keys 1 and 2 | Show the graph under original GraphRAG or under RGI |
| Level stepper, or keys [ and ] | Move between the leaf, community, higher community and root levels |
| Click a relationship, entity or community | Open an inspector that explains why it is kept or lost at this level |
| Zoom buttons, or Ctrl and scroll | Zoom and pan the graph |
| Theme button | Switch between light and dark themes |
| Escape | Close the menu or the open inspector |

The question menu, with its five featured questions and a field for typing new ones, appears in [@fig:xray-menu]. Names in a typed question are matched to entities, and if none of them matches, the menu reports this and stays on the current question.

![fig:xray-menu](s_xray_menu.png){w=14.4} Question menu with featured questions and a field for typed questions

## Reproduction guide and project timeline {#app:repro}

An ordinary laptop is enough to regenerate every result, in five steps:

1. Set up the Python 3.11 environment from the project's lock file, and install Node.js for the simulator scripts.
2. Using the commands in [@tab:commands], run the census, the two sensitivity runs and the selection analysis. On the first run the `o200k_base` encoding is downloaded once and cached.
3. Run the simulation sweep under Node.js.
4. Run the analysis script. It writes every figure, table and number that appears in the paper and in this report.
5. Run `python -m pytest tests/` and check that all 166 of the toolkit's tests pass.

The main stages of the project are listed in [@tab:timeline]. Most dates are taken from the repository's commit history; for files that have not been committed yet, we used their modification dates.

!table[tab:timeline]{w=1.6,5.2} Project timeline
| Date | Work recorded |
| 15 August 2026 | Repository set up; kill thresholds frozen (commit d223de8); linking parameters and tokenizer frozen (commit 21e43d8) |
| 15 August 2026 | Measurement toolkit, synthetic fixture, 166 tests and the ten experiment scripts; handover document listing the seven differences from the documentation |
| 15 to 16 September 2026 | GraphRAG X-Ray simulator built and redesigned; design documents for RGI |
| 13 October 2026 | Census of all 20 novels, selection analysis, sensitivity runs and ablations; typed questions and theme switching in the simulator; research paper |
| 14 to 16 October 2026 | Final report |

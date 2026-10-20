# Implementation {#ch:impl}

How the design was turned into working code is the subject of this chapter. We go through the repository and how it is laid out, the measurement toolkit, and the census pipeline behind the main results. After that come the linking of gold evidence, the analysis of GraphRAG's standard input builder and the scripts that turn results into figures and numbers, followed by the GraphRAG X-Ray simulator and the tests that check all of these.

## Repository and development environment {#sec:impl-env}

Everything is kept in a single git repository, whose main folders are listed in [@tab:repo]. The Python code runs inside a virtual environment pinned by a lock file. The simulator is written in plain HTML, CSS and JavaScript, while the paper and the diagrams are in LaTeX. Any result in this report can be regenerated from the repository together with the public dataset.

!table[tab:repo]{w=2.2,4.6} Main folders of the project repository
| Folder | Contents |
| `src/graphrag_loss/` | Measurement toolkit: nine Python modules |
| `scripts/` | Ten experiment scripts, E0 to E9 |
| `tests/` | 166 tests and a synthetic GraphRAG index used as a fixture |
| `data/graphrag_bench/` | GraphRAG-Bench Novel corpus and questions (MIT licence) |
| `paper/experiments/` | Census, selection analysis, simulation sweep and analysis scripts |
| `paper/results/` | Result tables in CSV and JSON |
| `paper/generated/` | Generated LaTeX tables and number macros |
| `demo/` | GraphRAG X-Ray simulator |
| `GATES.md` | Kill thresholds and linking parameters, frozen before any data |

## Measurement toolkit {#sec:impl-toolkit}

The toolkit is a Python package with nine modules, and [@tab:modules] gives a one-line summary of each.

!table[tab:modules]{w=1.6,5.2} Modules of the measurement toolkit
| Module | Responsibility |
| `schema.py` | Expected columns of every GraphRAG output file; detects and logs differences from the documentation |
| `io.py` | Loads a frozen index, hashes its files into a manifest, stamps every result with the git commit and GraphRAG version |
| `loss.py` | Boundary census per level and across all levels, multi-topic labelling, replay of the input budget |
| `linking.py` | Links gold evidence to graph elements using the frozen triple strategy |
| `nli.py` | Recoverability check with an NLI model, gated on human agreement |
| `attribution.py` | Classifies a failed answer as index-absent, not selected or not used |
| `injection.py` | Inserts content into a context while keeping its token count exactly constant |
| `stats.py` | Bootstrap intervals, McNemar's test, Cohen's kappa and h, partial correlation, Holm correction |
| `report.py` | Writes each experiment's report with fixed sections, including the counter-evidence |

### Schema and input handling

GraphRAG stores its index as parquet files, and the columns in those files have changed from one version to the next. For each file, the `schema` module records which columns the study expects and compares them with the columns it actually finds. A missing or renamed column is logged, after which the module either carries on, when the difference is harmless, or stops, when some measurement depends on that column; the seven differences in [@tab:divergences] were caught and recorded this way. The `io` module loads the files and turns list-valued columns into plain Python lists, which matters because parquet returns arrays and arrays behave differently when tested for truth. When an index is frozen, `io` also writes a manifest of file hashes. Each result file starts with a header naming the git commit, the GraphRAG version and the manifest hash, so any number can be traced back to the exact index and code that produced it.

### Loss computation

Computing the boundary census is straightforward once one has GraphRAG's community table, since that table lists the relationships lying wholly inside each community. At a given level, a relationship is a boundary relationship if no community at that level lists it, which in code is a set difference:

```
def intra_relationship_ids(communities, level=None):
    rows = (communities if level is None
            else communities[communities.level == level])
    out = set()
    for rids in rows.relationship_ids:
        out.update(io.as_list(rids))
    return out

def cross_edges_at_level(communities, relationships, level):
    return set(relationships.id) - intra_relationship_ids(communities, level)
```

The same module computes the permanent cross edges, those that no level contains, and the share of total edge weight they carry. It also replays GraphRAG's budget rule for the standard pipeline, sorting relationships by combined degree and admitting them until the first overflow, so that the relationships lost to the budget can be listed one by one. A check called `verify_intra_community_edges` confirms on every index that each listed relationship really has both entities in its community. That check needs relationship endpoints, which are entity names, to be mapped to entity identifiers first; without the mapping it passes without testing anything, which is the sixth difference in [@tab:divergences].

### Linking, recoverability and attribution

The `linking` module turns gold evidence into graph elements. It implements two strategies. The frozen default links each gold triple by matching its head and its tail against entity titles with RapidFuzz's `token_set_ratio`, after lowercasing and removing punctuation, and accepts the triple only if both endpoints score at least 85. The sentence strategy is kept for a possible later comparison but is not used in any gate.

For gate G1, the `nli` module sets up the recoverability check. It pulls out the passages of a community report that mention each entity, forms a premise from the reports of the two communities that a relationship connects, and takes the relationship's description as the hypothesis. During calibration it writes a labelling sheet for two annotators, and it will not classify anything until their agreement, measured by Cohen's kappa, reaches 0.7. Gate G3 gets the same treatment from the `attribution` module, which sorts each failed answer into one of three categories in pipeline order and waits until the annotators agree.

### Token-exact injection

Since gate G4 compares two contexts of exactly the same length, the injection code had to be correct. In `inject_with_report`, the new content goes first. The original context pieces are then re-admitted in their original priority order until the token budget is reached, the first piece that does not fit is truncated, and the result is padded to the original count exactly. A difference of even one token raises an error:

```
target = token_len(base_context, tokenizer)
...
assembled = _pad_to_exact(assembled, target, tokenizer, leftover or " ")
result = InjectionResult(context=assembled, base_tokens=target,
                         new_tokens=token_len(assembled, tokenizer), ...)
if not result.is_token_exact:
    raise InjectionError("token-exact contract violated: "
                         f"base={result.base_tokens} new={result.new_tokens}")
```

This is harder than it sounds, because a tokenizer can merge characters across the point where two strings are joined, and the token count of the joined string is then not the sum of its parts. For that reason `_largest_fitting_slice` counts tokens on the joined text while it searches for the longest slice that fits, and `_pad_to_exact` adds or removes one token at a time until the counts agree. The module also samples placebo content of the same size, drawn from lost relationships that are not part of the gold evidence.

### Experiment scripts

The experiments are run by ten scripts in a fixed order (see [@tab:scripts]). Every script writes a comma-separated values (CSV) table along with a short markdown report. If a gate fires or a precondition fails, the script exits with code 2, which makes a sequence of runs stop at the first problem.

!table[tab:scripts]{w=0.7,2.3,3.0,0.8} Experiment scripts
| ID | Script | Purpose | Gate |
| E0 | `00_index.sh` | Build the index and freeze it with a manifest | |
| E0.5 | `01_verify_schema.py` | Integrity checks on the frozen index | 0 |
| E1 | `02_cross_edges.py` | Census of boundary relationships per level | |
| E3 | `03_multitopic.py` | Multi-topic entities, controlled for degree | |
| E4 | `04_truncation_replay.py` | Relationships lost to the input budget | |
| E5 | `05_recoverability.py` | NLI recoverability after annotator calibration | G1 |
| E6 | `06_gold_links.py` | Gold evidence intersected with the loss set | G2 |
| E7 | `07_query.py` | Global search over 125 questions | |
| E8 | `08_attribution.py` | Failure attribution after annotator calibration | G3 |
| E9 | `09_inject.py` | Oracle versus placebo at equal token count | G4 |

Where the order of steps matters, the scripts enforce it. The truncation replay will not start until a written reading of GraphRAG's summarization code is in place, and the injection script goes through its three phases strictly one after another: first the token-exact check, then the placebo arm and last the oracle arm.

## Census pipeline {#sec:impl-census}

The main results in this report come from the census pipeline. It is one script, which indexes every novel separately and then evaluates each relationship at four query levels and four budgets, once under GraphRAG and once under RGI. Its stages, and the GraphRAG function used at each stage, are drawn in [@fig:census-pipe].

![fig:census-pipe](d_census_pipeline.png){w=13.8} Stages of the census pipeline for one novel

### Indexing with GraphRAG's own code

Chunking uses GraphRAG's token chunker with the default 1,200 tokens and 100 tokens of overlap. Edges come from GraphRAG's `_extract_edges`, which connects phrases found in the same text unit and gives each connection a PMI weight. GraphRAG's `prune_graph`, run with its shipped defaults, prunes the graph, and GraphRAG's `cluster_graph` clusters it by calling hierarchical Leiden with a maximum community size of ten and the default seed. Then, for every community, the script gathers the text units of its internal relationships and sorts them by the summed degree of the community's entities in each unit, which is exactly what GraphRAG's `prep_text_units` does, before rendering them with GraphRAG's `get_context_string`.

Only one stage uses code that is not GraphRAG's. Its default noun-phrase extractor needs tagger data from the Natural Language Toolkit (NLTK), and that data could not be downloaded on the network we were using. In its place we wrote a deterministic proper-noun extractor with the same output format, the same stop words and the same rules for valid tokens as the default one. It collects runs of capitalized words, lets short connectors such as "of" sit between them and strips possessive endings. A capitalized word is treated as an ordinary word whenever the same word also occurs in lower case somewhere in the novel, and this rule gets rid of sentence-initial words like "The" or "Then" without any tagger. Wherever the results are reported, the substitution is stated.

### Exact admission

Under GraphRAG's admission rule, text units are added one by one, and the process stops at the first unit that pushes the rendered input over the budget. Re-rendering and re-tokenizing after each addition would be slow, so the script reaches the same cut by binary search over the number of admitted units, with token counts cached:

```
def admit(self, key, records, budget):
    n = len(records)
    if n == 0:
        return 0
    if self.tokens(key, records, n) <= budget:
        return n
    lo, hi = 0, n       # tokens(lo) <= budget < tokens(hi)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if self.tokens(key, records, mid) <= budget:
            lo = mid
        else:
            hi = mid
    return lo
```

A binary search is only correct if the token count grows with the number of units, which holds here because each unit adds text. To be sure that the search returns what GraphRAG would return, the script calls GraphRAG's own `sort_context` on the first overflowing communities of every novel and asserts that the admitted text is identical. The two agreed on all {EquivChecks} communities checked.

### Status, evidence and RGI inputs

For each level, the script reproduces global search's choice of communities, takes the deepest community at or above the level for every entity, and asserts that this always equals the community with the largest identifier, which is the rule GraphRAG implements. It then assigns every relationship its status from [@tab:status]. A community whose input fits keeps all its units; a leaf community that overflows is cut; a parent community that overflows is marked as assembled from its children's summaries.

The RGI builder follows the algorithm in [@sec:rgi-design] line for line. After building each input it renders the text, counts its tokens with the production tokenizer and drops trailing compact facts until the count is within the budget; an assertion then checks that no input exceeds B. After all communities are built, the script checks the coverage certificate, that the represented, bridged and stored sets are disjoint and cover every relationship, and counts any relationship that GraphRAG represented and RGI does not. A failed certificate stops the run.

Evidence tiers are computed last. The function below gives each relationship the strongest tier its evidence reaches:

```
def exposure(ix, sel, admitted, explicit):
    every = set().union(*admitted.values()) if admitted else set()
    out = {}
    for rid, src, tgt in zip(rel.id, rel.source, rel.target):
        if rid in explicit:
            out[rid] = "scope"
            continue
        units = ix["rel_units"][rid]
        near = (admitted.get(sel.get(src), set())
                | admitted.get(sel.get(tgt), set()))
        out[rid] = ("endpoint" if units & near
                    else "elsewhere" if units & every else "absent")
    return out
```

A full run over the twenty novels, including every budget, level and RGI configuration reported in [@ch:results], takes {RuntimeS} seconds on the M2 laptop and makes no model calls. Two further runs repeat the main configurations with text units of 600 and 300 tokens.

## Linking gold evidence {#sec:impl-gold}

For every question, the census script parses each gold triple into its head, relation and tail and links it against the entities of the question's own novel with the frozen configuration: `token_set_ratio` of at least 85 for both endpoints, applied to lowercased text without punctuation. A triple whose two endpoints link identifies the graph relationships between those two entities. The relationships found for all of a question's triples form its gold set Y(q). If two endpoints resolve to the same entity, or the two entities have no relationship in the graph, the triple contributes nothing. For each question and level, the script records how many gold relationships are in scope under GraphRAG and under RGI, and how many reach each evidence tier.

## Selection in the standard pipeline {#sec:impl-selection}

The census measures the fast pipeline, whose input builder works on text units. To measure the standard pipeline's builder, which works on relationship records, a second script runs that builder unchanged on the census graphs. It calls GraphRAG's own `explode_communities`, `_prep_nodes`, `_prep_edges` and `build_local_context`, the same sequence GraphRAG's community-report workflow uses, and then reads which relationship records appear in each community's candidate pool. Descriptions are left as GraphRAG's own placeholder text, because the selection step never reads them. For each level, the script counts the within-community relationships that reach the pool, the cross-community relationships that enter pools, and the upper bound of one relationship per entity from Proposition 3, which it also asserts.

## Analysis and reproducibility {#sec:impl-analysis}

No number in the paper or in this report was copied by hand. An analysis script reads the result tables and writes every figure, every table and more than 270 named numbers, which the paper's LaTeX source and this report's generator insert directly. When a result changes, rerunning the script changes every place it appears. [@tab:commands] lists the commands that regenerate everything from the public dataset.

!table[tab:commands]{w=4.3,2.5} Commands that regenerate the results
| Command | Output |
| `python paper/experiments/census_rgi.py` | Census, RGI and gold links at 1,200-token units |
| `python paper/experiments/census_rgi.py --chunk-size 600 --no-ablations` | Sensitivity run at 600 tokens |
| `python paper/experiments/census_rgi.py --chunk-size 300 --no-ablations` | Sensitivity run at 300 tokens |
| `python paper/experiments/selection_loss.py` | Standard-pipeline selection counts |
| `node paper/experiments/sim_sweep.js` | Simulation results and configuration sweeps |
| `python paper/experiments/analyze.py` | Figures, tables and number macros |

## GraphRAG X-Ray simulator {#sec:impl-xray}

GraphRAG X-Ray is a single web page that runs from local files in any modern browser. It uses no frameworks and loads nothing from the internet. Its three source files follow the organization in [@fig:xrayarch].

### Building the simulated index

The core of the corpus is kept in the data file. It contains the plot entities and relationships of *Middlemarch*, the 22 leaf communities with their titles and summaries, the parent communities above them, and the five hand-written questions, each with its evidence path and three versions of its answer. Everything else is built by the simulation file when the page loads. A long tail of minor entities is generated from name pools using a seeded random number generator, so each run gives the same index; token costs and weights are assigned, and the graph is laid out with a deterministic force-directed algorithm that we wrote from scratch.

At each of the four levels, and for each method, the simulation works out the status of every relationship. Under the original method, relationships are admitted in priority order until the first overflow. The RGI variant keeps full items up to 80% of the budget, uses up to 12% of the budget for bridge records of boundary relationships whose weight is four or more, and fills what remains with compact facts. Scoring is done by a function called `evaluate`, which takes a question, a level and a method, ranks the community reports, keeps the top three, checks which evidence relationships appear in them and then applies the stochastic judge.

### Interface

The graph is drawn on an HTML canvas, with lost relationships shown as red dashed lines, recovered ones as green lines and the evidence path in blue. For the current question, a comparison panel gives each method's verdict, and a stepper moves through the four levels while a table reports the share of relationships retained, the evidence retrieved and the answers judged correct. If the user clicks a relationship, an entity or a community, an inspector opens and explains in plain words why that element is lost or kept at the current level. Light and dark themes are both supported, as are keyboard shortcuts. [@fig:xray-orig] and [@fig:xray-rgi] show one question at the leaf level under each of the two methods.

![fig:xray-orig](s_xray_original.png){w=14.4} GraphRAG X-Ray: original GraphRAG at the leaf level

![fig:xray-rgi](s_xray_rgi.png){w=14.4} GraphRAG X-Ray: the same question under RGI

At the root level, shown in [@fig:xray-root], the single community's summary input overflows its budget, and the metrics table shows how much of the graph is retained by each method.

![fig:xray-root](s_xray_root.png){w=14.4} GraphRAG X-Ray at the root level under RGI

### Typed questions

Beyond the five featured questions, a user can type any question about the novel. The function `ask` resolves the words of the question to entities by matching the longest phrases first against full names, short names and surnames, accepting plural and possessive forms, and breaking ties between entities with the same surname by preferring the most connected one:

```
function ask(text) {
  var raw = String(text == null ? "" : text).trim(), norm = normText(raw);
  if (!norm) return { ok: false, reason: "empty" };
  var toks = norm.split(" "), matched = [], seen = new Set(), i = 0;
  while (i < toks.length && matched.length < MAX_ENTS) {
    var hit = null, len = 0;
    for (var n = Math.min(4, toks.length - i); n >= 1; n--) {
      var gram = toks.slice(i, i + n).join(" "), a = alias.get(gram);
      if (!a && n === 1 && gram.length >= 5
          && gram.charAt(gram.length - 1) === "s")
        a = alias.get(gram.slice(0, -1));
      if (a) { hit = a; len = n; break; }
    }
    ...
```

When the question names two or more entities, the evidence is taken as the shortest chain of relationships linking them in order; when it names one, its strongest relationships from the novel's core are used. The resulting question goes through the same `evaluate` function as the benchmark questions, and the answer panel composes its answer only from the relationships that the method actually retrieved. [@fig:xray-custom] shows a typed question.

![fig:xray-custom](s_xray_custom.png){w=14.4} A typed question resolved to a three-relationship chain

## Testing {#sec:impl-testing}

All 166 tests in the toolkit pass, and [@tab:tests] shows how they are organized. They run against a synthetic GraphRAG index that is stored alongside the tests. This fixture follows GraphRAG's real schema, down to relationship endpoints being stored as entity names, and it is small enough for the correct answers to be worked out by hand. The boundary test is a good example: it asserts that the census returns exactly r6, r7, r8 and r9 at level 0 and exactly r7 and r9 at level 1, where a weaker test would only check that the result looked reasonable.

!table[tab:tests]{w=2.0,0.8,4.0} Test suite of the measurement toolkit
| Test file | Tests | What it checks |
| `test_injection.py` | 75 | Token-exact injection on 50 random contexts, 10 contexts with mixed scripts and punctuation, five insertion sizes; placebo sampling |
| `test_stats.py` | 29 | Bootstrap, McNemar and kappa against scipy and statsmodels |
| `test_schema.py` | 23 | Column checks and the relationship-column spelling in both directions |
| `test_linking.py` | 23 | Triple and sentence linking on known elements |
| `test_loss.py` | 16 | Exact boundary sets per level and across levels |
| **Total** | **166** | |

The census pipeline also has checks of its own, run every time it executes instead of in a separate suite. Its admission rule has to agree with GraphRAG's `sort_context`, the global-search rule has to pick the deepest community, no RGI input may go over its budget, and the coverage certificate has to hold. We checked the simulation in the same way: at all four levels, the RGI variant lost no relationship that the original method had kept, and no question ended up with fewer evidence relationships retrieved. One project rule shaped all of this testing. If a test fails, work stops until the failure is fixed, and failures are never hidden inside an exception handler.
# Requirements and Analysis {#ch:requirements}

Here we set out what the system had to do and the conditions it had to work under. The chapter also describes the dataset and the software environment, and it records two pieces of analysis done before any measurement: a reading of GraphRAG's source code, and an evaluation plan whose thresholds were fixed in advance.

## Requirements analysis {#sec:req}

Three parts of the project share data and code. A measurement layer reads GraphRAG's index and computes the loss, a repair layer builds RGI's summary inputs, and a demonstration layer lets a user explore the mechanism interactively. All three are covered by the requirements that follow.

### Functional requirements

[@tab:freq] lists the functional requirements. Each one is traced to the part of the report where it is met.

!table[tab:freq]{w=0.6,4.6,1.6} Functional requirements
| ID | Requirement | Where it is met |
| F1 | Build the knowledge graph, communities and summary inputs for every novel using GraphRAG 3.1.1's own code | [@sec:impl-census] |
| F2 | Assign every relationship a status and an evidence tier at each query level and budget | [@sec:loss-model] |
| F3 | Reproduce GraphRAG's admission rule exactly and verify it against GraphRAG's own function | [@sec:impl-census] |
| F4 | Build RGI summary inputs within the same budget, with bridge records, compact facts and a residual store | [@sec:rgi-design] |
| F5 | Check RGI's guarantees on every run and stop if any fails | [@sec:impl-census] |
| F6 | Link the benchmark's gold evidence to graph relationships with parameters fixed in advance | [@sec:impl-gold] |
| F7 | Measure which relationships GraphRAG's standard input builder passes into summary inputs | [@sec:impl-selection] |
| F8 | Produce every figure, table and reported number from the result files, without manual copying | [@sec:impl-analysis] |
| F9 | Provide experiment scripts E0 to E9 and the four pre-registered gates for the answer-level test | [@sec:impl-toolkit] |
| F10 | Provide an interactive simulator that compares GraphRAG and RGI by level and accepts typed questions | [@sec:impl-xray] |

### Non-functional requirements

The non-functional requirements came mostly from the nature of the study. A measurement of loss is only useful if it can be trusted, so exactness and reproducibility ranked above speed and convenience. [@tab:nfreq] lists them.

!table[tab:nfreq]{w=1.8,5.0} Non-functional requirements
| Requirement | What it means in this project |
| Exactness | Every count is a census of all relationships, not a sample. Where GraphRAG's behaviour is replayed, the replay gives the same result as GraphRAG's own code |
| Fidelity | Measurements use GraphRAG's shipped defaults and call its functions wherever possible; any substitution is disclosed |
| No model in the measurement path | The census and the RGI construction make no language model calls, so their results depend neither on a model's randomness nor on a paid service |
| Budget neutrality | RGI never uses more tokens than GraphRAG for a summary input or a query context |
| Reproducibility | One command per experiment regenerates every result from the public dataset; seeds are fixed and GraphRAG's clustering seed stays at its default |
| Testability | The toolkit is tested on a synthetic index whose correct answers are known by construction, and a failing test stops the work |
| Performance | A census of all twenty novels, with every configuration, finishes in minutes on a laptop |
| Portability | The simulator runs in a browser from local files, with no server and no external libraries |

## Hardware and software environment {#sec:env}

All work was done on an Apple M2 laptop. [@tab:software] lists the main software and the role of each component. The Python environment is pinned in the project's lock file, which records 153 package versions.

!table[tab:software]{w=2.4,1.2,4.2} Software environment
| Component | Version | Role in the project |
| Python | 3.11.5 | Toolkit, census, analysis |
| graphrag (with graphrag-chunking, graphrag-llm and other sub-packages) | 3.1.1 | System under study; chunking, edge building, pruning, clustering and input builders |
| graspologic-native | 1.2.5 | Hierarchical Leiden clustering called by GraphRAG |
| tiktoken | 0.13.0 | Token counting with the `o200k_base` encoding |
| pandas / numpy / pyarrow | 3.0.5 / 2.4.6 / 25.0.1 | Tables, arrays and GraphRAG's parquet outputs |
| RapidFuzz | 3.14.5 | Fuzzy matching of gold evidence to entity titles |
| scipy / statsmodels | 1.17.1 / 0.14.6 | Bootstrap intervals, McNemar's test, Cohen's kappa |
| matplotlib | 3.11.1 | Charts |
| pytest | 9.1.1 | Test suite |
| litellm / transformers / torch | 1.92.0 / 5.15.0 / 2.13.0 | Model access and NLI for the planned answer-level test |
| Node.js | 23.9.0 | Headless runs of the simulator |
| HTML, CSS and JavaScript (no frameworks) | n/a | GraphRAG X-Ray simulator |
| TeX Live | 2026 | Diagrams and the research paper |

## Dataset: GraphRAG-Bench Novel {#sec:dataset}

The project uses the Novel corpus of GraphRAG-Bench (Xiang et al., 2026), released under the MIT licence. It contains {NNovels} novels with {NChars} characters in total, which come to {NTokens} tokens under the `o200k_base` encoding. The novels range from about 93,000 to about 450,000 characters. The corpus comes with {NQuestions} questions, each tied to one novel. [@fig:qtypes] shows how the questions divide among the four types.

![fig:qtypes](f_qtypes.png){w=13.5} Question types in GraphRAG-Bench Novel

Each question carries a reference answer and two forms of gold evidence: a list of evidence sentences and a list of evidence triples of the form (head, relation, tail). An example from the corpus asks which plant, known scientifically as *Erica vagans*, is also referred to by another common name; the answer is "Cornish heath", and the gold triple is (erica vagans, is also known as, Cornish heath).

Before designing the gold-evidence analysis, we checked how the evidence sentences relate to the source text. They turned out to be restatements rather than extracts. Only 0.1% of them appear in their novel as exact substrings, and 5.4% reach a character n-gram similarity of 85 or more against windows the size of a text unit. Linking evidence by locating sentences in the text, as originally planned, was therefore not workable. We linked the triples instead, as described in [@sec:prereg] and [@sec:impl-gold].

## Feasibility and constraints {#sec:feasibility}

The original plan was to build a GraphRAG index of the corpus with a language model and then measure loss and answer quality on it. We estimated the cost before starting. Indexing the roughly 1.1 million tokens of the corpus needs between 3,000 and 5,500 model calls for extraction, description summarization and community reports. The full answer-level study, including 125 questions under global search and the injection experiments, needs about 6,000 to 10,000 calls and on the order of 150 million tokens, most of them spent by global search.

The plan had to change for two reasons. On a free tier of the model service we had chosen, a daily request limit would have turned a long run into a stall lasting several days, so that tier could not handle the volume. The more serious problem was that the team's API key failed validation when we tried to start; its length and format were not what the service expected, and we stopped before spending any tokens.

We decided to work around this and carry on. A large part of the study needs no model, because GraphRAG's fast pipeline builds the graph, the communities and the summary inputs on its own, and everything that decides what a summary can contain is settled before the summarizer is ever called. A measurement of the summary inputs is therefore an exact measurement of the loss. Only the question of whether the loss changes answers needs a model, and we specified that test completely, freezing its thresholds in advance, so it can be run once access is available.

## Analysis of the GraphRAG 3.1.1 source {#sec:source}

Since the design depends on what GraphRAG 3.1.1 really does, we read the relevant parts of its source before writing any measurement code. Everything in the list below was checked against the installed package.

- Text units default to 1,200 tokens with 100 tokens of overlap, counted with the `o200k_base` encoding.
- `max_input_length`, the summary input budget, is 8,000 tokens unless changed.
- The standard pipeline sorts relationships by combined degree, highest first, and keeps admitting them until the next one would overflow the input; admission ends at the first item that does not fit.
- In the fast pipeline the summary input is made of the text units that support the community's relationships. These are sorted by the summed degree of the community's entities in each unit, and the same first-overflow rule applies.
- When a parent community's input overflows, its report is written from its children's reports instead of its own content. A leaf community that overflows is cut.
- At a given level, global search reads for each entity the report of the community with the largest identifier among those at or above that level, and on every census graph we checked that this was always the deepest such community.
- Before clustering, the fast pipeline prunes the graph. It drops entities seen fewer than twice, edges whose weight is below the 40th percentile, and the single most connected entity.
- Clustering is hierarchical Leiden with a maximum community size of ten and a fixed default seed.

We then compared the package with our own design notes, which had been written from GraphRAG's documentation and paper, and found seven differences, listed in [@tab:divergences]. For each one we adopted the same rule: detect it at run time and log it, carry on if it does no harm, and stop if it breaks an assumption that the measurement relies on.

!table[tab:divergences]{w=2.6,3.2,1.0} Differences between the documentation and GraphRAG 3.1.1
| Documented | Observed in 3.1.1 | Severity |
| Text units list relationships in a column spelled `relationships_ids` | The column is `relationship_ids`; the misspelling no longer exists | High |
| Documents carry a `metadata` column | Documents carry `creation_date` and `raw_data` instead | Low |
| No mention of readable identifiers | Every file carries a `human_readable_id` column | Low |
| No mention of extra columns | Communities add `period`; text units add `covariate_ids` | Low |
| Gold evidence sentences can be found in the text | Evidence sentences are restatements (0.1% exact matches) | High |
| Relationship endpoints are entity identifiers | Endpoints are entity names; communities list entity identifiers | High |
| The tokenizer is not specified | `o200k_base` is the default encoding | Medium |

Of the seven, the sixth was the most dangerous, since it produces no error at all. A check comparing relationship endpoints with the entity identifiers listed in communities would match nothing and still pass, having tested nothing. We only caught it because our tests ran against a synthetic index that copied GraphRAG's real schema, where a simplified schema would have hidden the problem.

## Pre-registered evaluation design {#sec:prereg}

Whether the lost content changes answers is a question that is easy to get wrong once the results are in, because a small effect tempts one to lower the bar for what counts as an effect. We guarded against this by writing down four kill criteria before downloading any corpus or building any index, and committed them to the project's git repository on 15 August 2026 (commit `d223de8`). A second commit the same day (`21e43d8`) added the linking parameters and the tokenizer. The file that holds them is treated as write-once.

Each criterion is a gate. If a gate fires, the claim it protects is dropped, later experiments do not run, and the result is reported as a null. [@tab:gates] lists the gates.

!table[tab:gates]{w=0.6,1.0,3.9,1.3} Kill criteria committed before any data existed
| Gate | Experiment | Question and measurement | Stop if |
| G1 | E5 | Do community summaries already paraphrase the relationships they leave out of scope? Measured by NLI on 300 edges stratified by weight, once two annotators agree at Cohen's kappa of at least 0.7 | More than 70% are entailed |
| G2 | E6 | Do benchmark questions need the lost content? Share of questions whose gold relationships intersect the loss set | Below 10% |
| G3 | E8 | Are wrong answers caused by the index rather than by retrieval or generation? Share of failures attributed to index absence | Below 15% |
| G4 | E9 | Does restoring the lost content change answers? Oracle minus placebo accuracy, paired by question | The 95% CI includes zero |

Two parts of the design deserve explanation. Gate G4 compares two injections of identical token count: the actual lost gold evidence, called the oracle, and randomly chosen lost relationships of the same size, called the placebo. A plain before-and-after comparison cannot separate the effect of the content from the effect of a longer context, which is a known source of change in model behaviour (Liu et al., 2024). The second part concerns gate G2. The frozen linking rule requires both the head and the tail of a gold triple to reach a `token_set_ratio` of at least 85 against an entity title of the question's own novel. A further rule, frozen at the same time, says that if more than 15% of triples fail to link, G2 is reported as inconclusive rather than as a pass or a fail. We apply that rule in [@ch:results].

The commit history is the evidence that the thresholds came first: the commits that froze them precede every commit that produced a number. The same file also records thresholds for a strong result, for example an oracle advantage of more than five accuracy points, so that the meaning of "strong" could not be adjusted once results were in.

# System Design and Methodology {#ch:design}

This chapter describes how the project is put together and why. It begins with the overall architecture and the order in which the work was done, then develops the model of index-time loss that the measurements rest on, and then presents Residual Graph Indexing in full. The last two sections describe the design of the measurement toolkit and of the GraphRAG X-Ray simulator.

## System architecture {#sec:arch}

The project has three layers, shown in [@fig:arch]. The first measures and repairs loss on real data without a language model. It takes the GraphRAG-Bench Novel corpus and GraphRAG 3.1.1's own code as inputs, runs the loss census, the selection analysis and the RGI builder, and writes result tables. An analysis script turns those tables into every figure, table and number that the paper and this report quote.

![fig:arch](d_architecture.png){w=13.6} System architecture of the project

The second layer is the pre-registered answer-level test. It consists of a tested measurement toolkit, ten experiment scripts and the frozen thresholds described in [@sec:prereg]. This layer needs an index built with a language model, so it is implemented and tested but not yet run. The third layer is a controlled simulation, GraphRAG X-Ray, which models a small index in the browser, shows the mechanism visually, and lets us carry the loss through to retrieval and to judged answers.

The layers share definitions rather than code. The loss model in [@sec:loss-model] fixes what "lost" means, and all three layers count loss the same way: by asking, for each relationship, whether it reaches a summary input that is about its own community.

## Methodology and workflow {#sec:workflow}

[@fig:workflow] shows the order in which the work was done. The order matters, because several later decisions depended on earlier ones.

![fig:workflow](d_workflow.png){w=12.6} Project workflow

We began by reading GraphRAG's source code and documentation ([@sec:source]), because the loss mechanisms are properties of specific functions. The kill thresholds were committed next, before any data existed. The measurement toolkit came third, built and tested against a synthetic index. With the tooling in place we built the GraphRAG X-Ray simulation, which made the mechanism concrete enough to reason about and to demonstrate. When it became clear that the language-model index could not be built in time, we moved the main measurement to GraphRAG's fast pipeline, which allowed an exact census on the real corpus. RGI was designed against the simulation and then checked against the census. Ablations and sensitivity runs followed, and the results were written up as a research paper and as this report. Running the answer-level gates on a language-model index is the step that remains.

## Model of index-time loss {#sec:loss-model}

### Notation

The corpus is split into a set of text units U. Extraction produces a knowledge graph G = (V, E), where V is the set of entities and E the set of relationships. Each relationship r = (a, b) has a support U(r), the text units it was extracted from. Clustering produces a set of communities C. Each community c has a level λ(c), with level 0 the coarsest, and the hierarchy is nested: the children of a community divide its entities between them.

Global search at level ℓ reads the summaries of a selected set of communities. For every entity v, it uses the deepest community that contains v and lies at or above level ℓ:

$$ σℓ(v) = the deepest community c with v ∈ c and λ(c) ≤ ℓ,    Sℓ = { σℓ(v) : v ∈ V } $$

An entity that was never clustered has no σℓ(v). Each community c has a summary input I(c), built by an input builder under the budget B, and a summary written by a model from that input. We write T(x) for the number of tokens in a text x under the `o200k_base` encoding, so that T(I(c)) ≤ B. A relationship is *in scope* for a community when both of its entities belong to that community. It is *represented* in an input when its record appears there (standard pipeline) or when one of its supporting text units does (fast pipeline). The List of Symbols at the front of this report collects all of this notation.

### Status of a relationship

At a level ℓ, every relationship r = (a, b) receives exactly one of the six statuses in [@tab:status]. The first two depend only on the clustering; the last four depend on how the input of the shared community was built.

!table[tab:status]{w=1.5,5.3} Status of a relationship r = (a, b) at level ℓ
| Status | Condition |
| Outside | a or b was never clustered, so it has no community at all |
| Boundary | a and b are read through different communities, σℓ(a) ≠ σℓ(b), so r is in neither community's scope |
| Represented | a and b share a community c, and r is represented in I(c) |
| Sub-summary | a and b share a community c whose input was assembled from its children's summaries rather than its own content |
| Selection | a and b share a community c, but the input builder never offered r as a candidate |
| Budget | the builder offered r but cut it when the input reached B |

A relationship is out of scope at level ℓ whenever its status is anything other than represented. We write Lℓ for the set of relationships out of scope at level ℓ. [@fig:losspoints] places these mechanisms on GraphRAG's pipeline, together with the components that RGI adds.

![fig:losspoints](d_loss_points.png){w=14.2} Where content leaves the path to an answer (red) and what RGI adds (green)

A seventh kind of loss works at the level of entities rather than relationships. An entity whose text units cover several topics is filed under one community and read in that community's framing only. We call this multi-topic loss. It does not remove the entity from the index, since global search still reads it, so it falls outside the propositions below.

### Scope and evidence

Scope is a property of the index structure, but it does not settle whether a relationship's evidence reaches a summarizer. In the fast pipeline, a summary input is a set of text units, and a single unit of 1,200 tokens can mention dozens of entities. A relationship can be out of scope for its own communities while the text that supports it sits in some other community's input. In the standard pipeline, a description of an entity can mention a relationship that has no record of its own in the input.

We therefore grade every relationship by the strongest way its evidence reaches a selected input, using the four tiers in [@tab:tiers], from strongest to weakest.

!table[tab:tiers]{w=1.5,5.3} Evidence tiers
| Tier | How the evidence of r reaches the selected inputs |
| In scope | r is represented in the input of its own community |
| Endpoint | a supporting text unit sits in the input of a community that holds one of r's two entities |
| Elsewhere | a supporting text unit sits only in inputs of communities that hold neither entity |
| Absent | no record of r and no supporting text unit appears in any selected input |

The tiers matter for what can be claimed. A relationship in the endpoint tier may still be mentioned by a summary, because the summarizer of an endpoint's community sees the text. A relationship in the absent tier cannot be, which is the subject of the first proposition below.

### The hierarchy trade-off

Moving up the hierarchy merges communities, so fewer relationships cross a boundary. It also makes each community larger, so more content has to pass through the same budget. [@fig:toy] illustrates the trade-off with two children of one parent community. At the child level, the relationship r between a and b crosses a boundary and belongs to neither child. At the parent level r is in scope, but the parent's input now has to carry everything from both children, and if it overflows, the parent is summarized from the children's summaries instead of its own content. The level that is chosen therefore changes the mechanism through which r is lost, and in this example r can be lost at either level.

![fig:toy](d_hierarchy_toy.png){w=12.0} Boundary loss at a fine level and compression at a coarse level

## Three propositions {#sec:props}

The model supports three statements that hold for any corpus, beyond the one we measured.

**Proposition 1 (absent evidence is unreachable).** Fix a level ℓ and any retrieval policy whose context for a question depends only on the question and the summaries of the communities in Sℓ. If the evidence of a relationship r is absent at level ℓ, the context does not change when the text units that support r are edited, for any question.

*Argument.* Each summary depends on the corpus only through its input. If r's evidence is absent, no supporting unit and no record derived from one appears in any input of a community in Sℓ. Editing those units therefore leaves every input, every summary and every context unchanged.

We kept this proposition narrow on purpose; it applies to absent evidence and to nothing else. A relationship can be out of scope and still have its text in some input, and in that case it may surface in a summary anyway. How often that happens is what gate G1 of the pre-registered test is meant to measure.

**Proposition 2 (boundary loss grows toward the leaves).** Take a nested hierarchy and two levels ℓ < ℓ′. Any relationship whose status is boundary at level ℓ is still a boundary relationship at level ℓ′.

*Argument.* In a nested hierarchy, two different communities are either disjoint or nested one inside the other. Suppose σℓ(a) strictly contained σℓ(b). Then σℓ(a) would have a child, at a level no deeper than ℓ, that contains a, and σℓ(a) would not be the deepest community holding a, contrary to how it was chosen. The two communities must therefore be disjoint. Going down to a deeper level ℓ′ can only replace each of them with one of its own descendants, so they remain disjoint and r is still a boundary relationship.

**Proposition 3 (selection bound).** Whatever the budget, GraphRAG 3.1.1's standard input builder can represent no more than |c| of the relationships in scope for a community c. It follows that at most 2/d̄ of c's internal relationships are represented, where d̄ is the mean number of internal relationships per entity of c.

*Argument.* Inside the builder, the function `_prepare_reports_at_level`, a level's relationships are grouped once by source entity and once by target entity. Only the first relationship of each group is kept before the two results are merged, so no entity contributes more than one relationship record and the input can offer at most |c| records. With |c|·d̄/2 internal relationships in c, the share cannot be higher than 2/d̄.

In practice the share is lower than the bound, for two reasons: the single record an entity contributes may point outside its community, and two entities can contribute the same record. On a sparse graph, with d̄ close to 2, the bound barely matters, while on a dense graph it removes most of the relationships. GraphRAG's issue tracker has an independent report of the same behaviour (Grenat, 2026), and [@sec:res-select] puts numbers on it.

## Residual Graph Indexing {#sec:rgi-design}

### Design constraints

Four constraints applied to RGI from the start. The first two keep the comparison fair. GraphRAG's clustering, summary prompt and global search are left exactly as they are, and so is the token budget of every summary input and every query context, because extra tokens alone change how a model behaves (Liu et al., 2024). With both fixed, any difference in results has to come from what the summary inputs contain. The other two are about cost and accounting: RGI may not add any language model call at indexing time, and it has to be able to report, for every relationship in the graph, where that relationship ended up. Behind the design is the video-coding idea from [@sec:video]. The community summaries are the keyframes, which GraphRAG writes as usual, and RGI supplies the residual.

### Loss audit

The loss audit, the first component, works out every relationship's status at every level. Finding boundary and outside relationships only takes a set difference on GraphRAG's own tables, all relationship identifiers minus the ones listed inside the selected communities. For the budget and selection statuses the audit replays the input builder with GraphRAG's own sort order, budget and tokenizer, and since the builder is deterministic the replay matches it exactly. No model is called, and apart from the cost of counting tokens the running time grows linearly with the number of relationships at each level.

### Two-tier summary input

In GraphRAG, items enter the input in priority order until one of them would overflow B, and everything from that item onward is dropped together. RGI works with the same items in the same order and changes only what happens in the last part of the budget, as the comparison in [@fig:layout] shows.

![fig:layout](d_rgi_layout.png){w=14.0} How GraphRAG and RGI fill the same summary input

If a community's input already fits within B, RGI keeps all of it and spends any slack on bridge records. If it overflows, full items are kept only up to a cutoff fB (f = 0.8 by default), and the remaining space is filled with one-line compact facts written as `source,target,support`. At about ten tokens each, compared with roughly 1,200 for a text unit, compact facts let the freed space hold many more relationships. Something is lost in the exchange, since a compact fact records that two entities are related and gives no detail about the relation itself.

One more rule is needed for monotonicity. Stopping the full items at fB instead of B can drop relationships that GraphRAG's own input did represent, so RGI writes compact facts for exactly those relationships before anything else. If even these reserved facts will not fit, RGI uses GraphRAG's own input for that community and spends only the slack that is left. Communities whose input is built from their children's summaries are handled in a similar way: the child summaries are limited to fB, and the tail holds compact facts for the community's own relationships.

### Bridge records

Bridge records can take up to a share b of B in each community, 0.12 by default. A bridge record is a boundary relationship with at least m supporting text units (m = 2 by default). These relationships are ranked by combined degree and written as compact facts into the inputs of both endpoint communities, and a relationship counts as bridged if it lands in at least one of the two. When GraphRAG has already extracted a description of the relationship, the bridge record can carry that description, so no summary has to be rewritten and no model is called.

### Residual store and token-exact substitution

Every relationship that is neither represented nor bridged goes into a residual store, keyed by the communities it touches, or by a global key for relationships whose entities were never clustered. At query time, after global search has chosen its reports, the stored facts of the chosen communities that best match the question can be added to the context. They replace the lowest-ranked part of the context, so that the token count stays exactly the same. The toolkit's implementation of this swap is described in [@sec:impl-toolkit].

### Coverage certificate

At build time, RGI checks for every level that the represented, bridged and stored sets are disjoint and that together they make up the whole relationship set E. If the check fails, the build stops. GraphRAG today discards content without any record. The certificate makes the discard visible and bounded, and it would also catch loss from a mechanism nobody anticipated, such as the selection behaviour of Proposition 3.

### Algorithm

The way RGI builds one community's summary input is drawn in [@fig:rgiflow], and the listing below spells out the same procedure step by step. In it, P is GraphRAG's list of items for the community in GraphRAG's own order, k_G is how many of those items GraphRAG admits under B, E_in and E_bd are the in-scope and boundary relationships, and rep(X) is the set of relationships represented in an input X.

![fig:rgiflow](d_rgi_flow.png){w=10.4} Construction of one RGI summary input

```
Input: items P in GraphRAG order; in-scope set E_in; boundary set E_bd;
       budget B; cutoff f; bridge share b; minimum support m
1   k_G  <- number of items GraphRAG admits under B
2   if T(P) <= B:  X <- P;  pending <- empty
3   else:
4       k <- longest prefix of P with T(P[1..k]) <= f*B          # k <= k_G
5       Q <- rep(P[1..k_G]) minus rep(P[1..k]), by combined degree   # reserved
6       if T(P[1..k] + facts(Q)) > B:  k <- k_G;  Q <- empty         # fallback
7       X <- P[1..k] + facts(Q);  pending <- E_in minus rep(P[1..k_G])
8   for r in E_bd with |U(r)| >= m, by combined degree:
9       stop when bridge tokens exceed min(b*B, B - T(X)); else append bridge(r)
10  for r in pending, by combined degree:
11      stop when T(X + fact(r)) > B;  append fact(r)
12  while T(render(X)) > B:  drop the last compact fact
13  residual(c) <- (E_in + E_bd) minus rep(X)
14  return X
```

### Guarantees

Write R(G, ℓ) for the relationships that are in scope and represented under GraphRAG at level ℓ, and R(RGI, ℓ) for the same set under RGI. For every community and every level, RGI guarantees four things.

No input exceeds the budget, so T(I_RGI(c)) ≤ B in every case. Step 12 checks the bound on the rendered text, using the tokenizer that GraphRAG itself uses.

Monotonicity holds: R(G, ℓ) ⊆ R(RGI, ℓ). When the input fits, X contains all of P. When it does not, either the reserved facts bring back every relationship that GraphRAG's prefix represented and the shorter prefix lost, or the fallback restores GraphRAG's own prefix, and bridges and later facts can only add to this. Because the reserved facts come before every other appended line, step 12 could reach them only if they overflowed by themselves. Step 6 rules that out except for token merges at line boundaries, and the census checks the result on every run.

The cost stays the same. Like GraphRAG, RGI makes one summarization call per community, because it changes what goes into each input and leaves the number of summaries alone.

Coverage is complete. Every relationship in E falls into exactly one of the represented, bridged and stored sets, because the residual store receives a relationship precisely when it is neither represented nor bridged.

Monotonicity, as stated, concerns relationships in scope. In an overflowing input RGI replaces GraphRAG's last full items with compact facts, which takes the prose of those items out of the input. A relationship that was visible only by chance in that prose can therefore lose its visibility, and the census counts how often this happens ([@sec:res-recover]).

## Design of the measurement toolkit {#sec:toolkit-design}

For the answer-level test the census is not enough, since the test also has to run global search, link gold evidence, classify failures and inject content into contexts. We designed a Python package for this work around two rules. Any function that reads GraphRAG's output has to work on a synthetic index whose correct answers are known, which lets the tests check exact sets instead of numbers that merely look plausible. And any experiment with a precondition, for example annotator agreement or a token-exact injection, refuses to run until that precondition is met.

The package's structure is drawn in [@fig:toolkit]. Shared foundations sit in four modules (column names and schema checks, input and output with run records, statistics, and report writing), and the measurements sit in five more: loss computation, gold-evidence linking, NLI-based recoverability, failure attribution and token-exact injection. Ten scripts, numbered E0 to E9, run the experiments in a fixed order, and each one writes a table and a short report. Each module is described in [@sec:impl-toolkit].

![fig:toolkit](d_toolkit_modules.png){w=12.8} Structure of the measurement toolkit

## GraphRAG X-Ray simulator design {#sec:xray-design}

GraphRAG X-Ray was built for two purposes: to make the mechanism visible, and to study its effect on answers in a setting we control. It models a synthetic index shaped like George Eliot's *Middlemarch*, with a core of {SimCoreEntities} entities and {SimCoreRels} relationships taken from the novel's plot. A generated long tail of minor characters, places and things brings this up to {SimEntities} entities and {SimRels} relationships, arranged in 22 leaf communities that nest into 8, then 3, and finally 1 community above them.

In the simulation, summary inputs follow GraphRAG's first-overflow rule and priority order, and the token costs and weights are generated. For each question, retrieval reads the top three summaries, ranked by how many entities they share with the question, by a size prior and by noise that both methods share. A stochastic judge then marks the answer correct with probability 0.8 if all the evidence was retrieved, 0.45 if at least half of it was, and 0.15 otherwise. Of the {SimQuestions} questions, {SimFeatured} were written by hand from the novel; the others were sampled as paths of two to four relationships. The simulated RGI uses the two-tier layout on every input, which is a simpler variant of the algorithm above.

The simulator is split across three files, as [@fig:xrayarch] shows. A data file holds the core of the corpus, a simulation file builds the full index and evaluates both methods at every level, and an interface file draws the graph and handles user interaction. Typed questions are accepted as well. The simulator matches the names in a typed question to entities, takes the shortest chain of relationships between them as the evidence, and evaluates that chain in the same way as the benchmark questions. Since the judge and the long tail are generated, the simulator's numbers illustrate the mechanism under our assumptions and should not be read as measurements on real data.

![fig:xrayarch](d_xray_arch.png){w=13.6} How the GraphRAG X-Ray simulator is organized
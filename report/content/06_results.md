# Results and Discussion {#ch:results}

The measurements and what they found are reported here. After the experimental setup, the chapter takes six questions one at a time. It asks how much each level of the hierarchy loses and how scope differs from evidence, then how GraphRAG's standard input builder selects relationships and how much RGI recovers within the same budget. After that it asks whether the lost content is what the questions need, and how sensitive the results are to the text-unit size and to RGI's parameters. Results from the controlled simulation come next, and a discussion and the threats to validity close the chapter.

## Experimental setup {#sec:res-setup}

Each of the {NNovels} novels was indexed separately with GraphRAG 3.1.1's fast pipeline at its shipped defaults, as described in [@sec:impl-census]. [@tab:corpus-stats] summarizes the corpus and the resulting graphs.

!table[tab:corpus-stats](json:corpus){w=4.2,2.6} Census corpus and index

The graphs vary a great deal in size, as [@fig:novels] shows. The largest holds {BigNovelShare}% of all relationships, and the smallest has only 33. Because a pooled share is dominated by the largest graphs, every main result below is reported in two ways: pooled over all relationships, and as the mean of the per-novel shares, with a 95% bootstrap confidence interval over novels. Each count is a census of every relationship, so no p-values are reported for it.

![fig:novels](f_novels.png){w=13.6} Size of each novel's graph after pruning

The query levels studied are 0 (the root), 1, 2 (GraphRAG's command-line default) and 3. Budgets of 4,000, 8,000, 16,000 and 32,000 tokens were run, with 8,000 the default. RGI ran with its default parameters, f = 0.8, b = 0.12 and m = 2, which were fixed before the census, and with seven variations of them.

## How much each level loses {#sec:res-census}

[@tab:census-main] gives the status of every relationship at each level under GraphRAG, together with RGI's in-scope share and the mean gain over novels. At the default level 2, GraphRAG's summary inputs keep {CovCG}% of relationships in scope. Boundaries account for {BndCG}%. The budget accounts for almost nothing at this level, because nearly every selected community is a leaf of at most ten entities whose input fits within 8,000 tokens.

!table[tab:census-main](json:census){w=1.2,0.8,0.9,0.9,1.1,0.8,1.0,1.6} Share of relationships (%) by status at B = 8,000

The root level looks very different. There only {CovAG}% of relationships stay in scope, {BndAG}% cross a boundary, and {IndAG}% belong to communities whose summary inputs are assembled from their children's summaries in place of their own content. From the root down to level 3, boundary loss climbs steadily from {BndAG}% to {BndDG}%, as Proposition 2 predicts. Where each relationship ends up at each level is drawn in [@fig:census-bars].

![fig:census-bars](f_census.png){w=14.2} Where every relationship ends up at each query level

[@tab:inputs] shows how the summary inputs themselves were built. At the root, {SecondA} of the {CommsA} selected communities overflow and are summarized from their children; no leaf is cut, because every selected community at the root has children. At level 2, {TrimC} leaf communities overflow and are cut at the budget, and {SecondC} parents are assembled from child summaries.

!table[tab:inputs](json:inputs){w=0.7,0.7,0.9,1.1,1.2,1.1,1.2,1.1} Summary inputs at B = 8,000, summed over all novels

## Scope and evidence {#sec:res-evidence}

Being out of scope is not the same as having no evidence in any input. [@tab:exposure] grades every relationship by the strongest way its evidence reaches a selected input, using the tiers of [@tab:tiers].

!table[tab:exposure](json:exposure){w=1.0,1.2,1.1,1.1,1.1,1.0} Strongest form in which evidence reaches a selected input (%), B = 8,000

In the fast pipeline an input is made of text units, and one unit names many entities. At level 2, {NearCG}% of relationships have a supporting unit in the input of a community that holds one of their entities, and only {AbsCG}% have no evidence in any input at all. At level 0 the inputs of oversized communities contain no raw text, and {AbsAG}% of relationships have no evidence anywhere. Proposition 1 applies to exactly these relationships. The fast pipeline therefore loses evidence mainly at coarse levels, through second-hand summarization, and loses scope mainly at fine levels, through boundaries.

## Selection in the standard pipeline {#sec:res-select}

In the fast pipeline the input builder works with text units and lets every relationship through, but the standard pipeline's builder works with relationship records and filters them. We ran that builder, unchanged, on the census graphs, and [@tab:selection] gives the outcome.

!table[tab:selection](json:selection){w=0.7,1.1,1.6,1.2,0.8,1.1,1.5} How many within-community relationships reach the standard pipeline's summary input

Before the budget is even applied, only {SelMin}% to {SelMax}% of within-community relationships reach their community's candidate pool, at every level. [@fig:selection] sets the measured share against the upper bound from Proposition 3 of one relationship per entity. The measured share falls below the bound because the single record an entity contributes often points to an entity in some other community; summed over levels, the builder puts {SelCrossTotal} cross-community relationships into inputs and leaves most of the internal ones out.

![fig:selection](f_selection.png){w=13.2} Measured share of within-community relationships in the standard summary input, set against the bound

With a pooled mean degree of {MeanDegree}, these graphs are dense, and the bound cuts deeply. A graph extracted by a language model is usually far sparser, and the same code would remove fewer of its relationships; the bound gives a practitioner an estimate of the effect from the mean internal degree alone. The behaviour exists in version 3.1.1, and the public issue report says it goes back to version 0.9.0 (Grenat, 2026). When we wrote this, a fix had been proposed but not merged.

## What RGI recovers at the same budget {#sec:res-recover}

[@tab:census-main] shows RGI raising the in-scope share at every level. At the root the share goes from {CovAG}% to {CovAR}%, and at level 2 from {CovCG}% to {CovCR}%, which takes {BridgeC} bridge records and {CompactC} compact facts across the corpus. Averaged over the novels, the level 2 gain is {MacroDiffC} percentage points, with a 95% confidence interval from {MacroDiffCLo} to {MacroDiffCHi}. The gain for each novel is plotted in [@fig:pernovel]. RGI improved {PerNovelImproved} of the 20 novels, the exception being the smallest one, with 33 relationships, where both methods already keep the same share.

![fig:pernovel](f_pernovel.png){w=13.6} In-scope share at level 2 for each novel, GraphRAG and RGI

The guarantees held on every run. Across all {CensusConfigs} combinations of novel, level, budget and configuration, no relationship that GraphRAG kept in scope left scope under RGI ({Regressions} regressions), the fallback of the algorithm was never needed ({Fallbacks} times), no input exceeded {MaxTokensRGI} tokens at a budget of 8,000, and the coverage certificate held.

RGI also reduces absent evidence where Proposition 1 applies. At level 0 the share of relationships with no evidence in any input falls from {AbsAG}% to {AbsAR}%, and at level 1 from {AbsBG}% to {AbsBR}%. At level 2 it barely moves, from {AbsCG}% to {AbsCR}%, because there was little absent evidence to recover.

The two-tier layout does cost something, and the census lets us measure it. At level 2, RGI keeps {PassCR} of the {PassCG} text units that GraphRAG admits and uses the space of the rest for compact facts. Some relationships were visible only incidentally, in units that were replaced, and they lose that visibility. Summed over the four levels at a budget of 8,000 this happened in {ExpoRegrEight} cases, and at no level did it touch more than {ExpoRegrMaxShare}% of the relationships. None of these relationships went out of scope.

[@fig:budget] shows how the two methods react to the budget. At fine levels, a larger budget does less than RGI does: with 4,000 tokens RGI keeps {BudgetCFourR}% of level 2 relationships in scope, which is more than GraphRAG manages with 32,000 ({BudgetCThirtyTwoG}%). The root is different because its inputs overflow, and there the budget matters for both methods, with GraphRAG's share climbing from {BudgetAFourG}% to {BudgetAThirtyTwoG}% over the same range and RGI's from {BudgetAFourR}% to {BudgetAThirtyTwoR}%.

![fig:budget](f_budget.png){w=13.6} In-scope share against the summary input budget

## Is the lost content what questions need? {#sec:res-gold}

How much of the gold evidence we could link to the graph is shown in [@tab:linking]. Of the {NTriples} gold triples, {TripleParsed}% could be parsed and {TripleLinked}% linked at both endpoints, while {TripleRel}% resolved to a relationship in the graph.

!table[tab:linking](json:linking){w=4.3,1.2,1.2} Linking gold triples to the census graphs

That puts the unlink rate at {UnlinkRate}%, far above the 15% limit we froze in advance, and by our own rule this section cannot count as gate G2. What it does describe are the {NGoldQ} questions ({GoldQShare}% of the benchmark) whose gold evidence resolves. These questions are skewed toward prominent entities, which the extractor picks up more reliably and which RGI's priority order also favours. The numbers below therefore describe this subset and should not be taken as estimates for the benchmark as a whole.

Keeping that in mind, [@tab:gold] and [@fig:gold] show that at level 2, {GoldLostCG}% of these questions have at least one gold relationship out of scope under GraphRAG and {GoldLostCR}% under RGI. As [@tab:gold-types] shows, the reduction appears at every level and for all four question types.

!table[tab:gold](json:gold){w=0.9,0.9,1.4,1.0,1.5,1.3,1.0} Share of questions (%) with at least one gold relationship out of scope

![fig:gold](f_gold.png){w=13.2} Share of linked questions with a gold relationship out of scope

!table[tab:gold-types](json:gold_types){w=2.6,1.1,1.1,1.0,1.0} Questions with a gold relationship out of scope at level 2, by type (%)

Evidence gives a different picture by level. At level 2, {GoldAnyCG}% of gold relationships have a supporting text unit in some input under GraphRAG, so their loss at that level is a loss of scope. At the root only {GoldAnyAG}% do, against {GoldAnyAR}% under RGI, and the share of these questions with at least one gold relationship whose evidence is absent from every input falls from {GoldAbsQAG}% to {GoldAbsQAR}%.

## Sensitivity and ablations {#sec:res-ablate}

How dense the graph is depends on the co-occurrence window, so [@tab:chunk] repeats the main configurations with text units of 600 and 300 tokens. With the shorter units the mean degree drops from {ChunkDefaultDeg} to {ChunkSixDeg} and {ChunkThreeDeg}. GraphRAG's in-scope share at level 2 goes up from {ChunkDefaultG}% to {ChunkSixG}% and {ChunkThreeG}%, and RGI's from {ChunkDefaultR}% to {ChunkSixR}% and {ChunkThreeR}%, with no regressions at any size. The amount of loss therefore changes with the graph, but at every unit size we tried the loss was there and RGI improved on GraphRAG.

!table[tab:chunk](json:chunk){w=1.5,0.8,1.1,0.9,0.9,0.8,0.9,0.8} Sensitivity to the text-unit size (in-scope share, %, B = 8,000)

In [@tab:ablation], one RGI parameter is varied at a time. Most inputs fit at level 2, and there the bridge records account for most of the gain; without them RGI reaches only {AblNoBridgeA}%, through compact facts in the few inputs that overflow. The minimum support m has a bigger effect than the share b. Changing b from 0.06 to 0.24 moves the in-scope share from {AblBSixA}% to {AblBTwentyFourA}%, whereas changing m from 3 to 1 moves it from {AblMThreeA}% to {AblMOneA}%.

!table[tab:ablation](json:ablation){w=3.0,1.0,1.0,1.0,1.0} RGI ablations at B = 8,000 (% of relationships)

The root behaves differently, because there bridges and compact facts compete for the same tail of the budget. Taking the bridges out raises the in-scope share ({AblNoBridgeC}% against {AblMainC}%), a lower cutoff of f = 0.6 raises it further to {AblFSixC}% by leaving compact facts more room, and with no compact tier at all (f = 1.0) RGI keeps only {AblFOneC}%. How the budget is best divided thus depends on the level, which we come back to in [@sec:discussion].

## Controlled simulation {#sec:res-sim}

The census ends at the summary input. To follow the loss through retrieval to judged answers we use the GraphRAG X-Ray simulation described in [@sec:xray-design]. Its results come from a model we wrote, so they illustrate the mechanism and are no substitute for measurements on real data. Results at each level are in [@tab:sim-main] and [@fig:sim].

!table[tab:sim-main](json:sim){w=1.6,0.9,0.9,1.0,1.0,0.9,0.9} Controlled simulation results (synthetic data, {SimQuestions} questions, %)

![fig:sim](f_sim.png){w=13.2} Simulated share of evidence retrieved at each level

At every level RGI retrieves more evidence. The paired difference in evidence retrieved at the leaf level lies between {SimCIALo} and {SimCIAHi} percentage points (95% bootstrap interval over questions), and over all four levels no question and no relationship regressed ({SimRegr} cases). [@tab:sim-sweeps] shows how the simulated results change with each parameter.

!table[tab:sim-sweeps](json:sim_sweeps){w=2.6,1.5,1.5,1.5} Simulation results under each configuration (%)

We see three patterns in the sweeps. Reading more summaries does little for the original index: going from K = 2 to K = 6 raises leaf-level evidence retrieval only from {SimKTwoO}% to {SimKSixO}%, since the lost relationships are not in any summary. The choice of which relationships to bridge also matters more than the budget given to bridges. Lowering the bridge threshold from weight 5 to weight 3 lifts retrieval from {SimBMFive}% to {SimBMThree}%, but raising the bridge share from 6% to 24% leaves it where it was ({SimBSSix}% and {SimBSTwentyFour}%), the same ordering we saw on real data in [@sec:res-ablate]. Finally, a larger budget helps both methods at the root, where the original keeps {SimBudFourO}% of relationships with 4,000 tokens and {SimBudSixteenO}% with 16,000. That gain is paid for in tokens on every query, while the residual adds none.

## Discussion {#sec:discussion}

### Scope and evidence are different losses

The census separates two failures that are easy to confuse. Boundaries take relationships out of scope at fine levels, but in the fast pipeline the text that supports them usually still reaches a summarizer whose report is about one of the entities involved. Whether that report then mentions the relationship is up to the model. Second-hand summarization at coarse levels removes the evidence itself, and there Proposition 1 applies in full. A study that reported only one of the two would misjudge the problem, in one direction or the other.

### What RGI does and does not do

RGI is an accounting layer. It makes boundary relationships explicit in the inputs where they matter, restores relationships that the budget would drop, and records everything else. It does not change the clustering, so it cannot remove multi-topic loss, and it cannot make a summarizer use what it is given. Its compact facts carry less information than the text they replace: in the fast pipeline a compact fact holds only the pair of entities and the number of supporting units. In the standard pipeline a bridge record can carry the relationship's extracted description.

### Allocation depends on the level

Most inputs fit at fine levels, so the slack in each input costs nothing and bridges are the only thing RGI can add. At the root, bridges and compact facts compete for the same tokens, and the ablations favour compact facts. Any fixed split of the budget is a compromise between these two situations, and a split that depends on the level, or a salience score learned from questions, would be a natural next step.

### Reconciling with earlier evidence

Edge et al. (2024a) found no significant difference between global search and a summarization baseline with no partition. That baseline has no boundary loss by construction, so the finding is evidence that partition loss does not move aggregate answer quality on broad sensemaking questions. Our claim is narrower and is measured element by element. We expect effects on fact retrieval and multi-hop questions whose evidence crosses communities, and the pre-registered protocol tests that by question type. LightRAG (Guo et al., 2024) avoids the community layer altogether and is competitive on GraphRAG-Bench. Community summaries give a navigable view of a corpus that direct entity retrieval does not offer, and RGI tries to keep that view while accounting for what it costs.

## Threats to validity {#sec:threats}

Several limits apply to these results. [@tab:threats] lists them together with what was done about each.

!table[tab:threats]{w=1.6,3.0,2.2} Threats to validity and how they were handled
| Threat | Why it matters | What was done |
| Substitute extractor | Our proper-noun extractor omits the multi-word common noun phrases that GraphRAG's default extractor keeps, so absolute shares would differ | Kept the default's output format, stop words and token rules; every later stage is GraphRAG's own code; the selection analysis does not depend on extraction |
| Fast pipeline | Its inputs are text units; the standard pipeline's are model-written descriptions whose lengths only a model run produces | Measured the standard builder's selection exactly; left its budget loss to the model run |
| Graph density | Co-occurrence within 1,200-token units gives dense graphs (mean degree {MeanDegree}), which inflates boundary and selection loss | Repeated the census at 600 and 300 tokens |
| Gold linkage | More than half of the gold triples do not link, and those that do favour prominent entities | Reported the subset descriptively and did not treat it as gate G2 |
| Scope versus content | Being in an input does not guarantee being in the summary, and being out of scope does not guarantee absence from it | Reported evidence tiers; gate G1 measures the second gap |
| Concentration | One novel holds {BigNovelShare}% of all relationships | Reported per-novel means with intervals next to every pooled figure |
| Version | Results describe GraphRAG 3.1.1; a merged fix for selection would change [@sec:res-select] | Recorded the version in every result file |
| Simulation | The simulated corpus tail and judge are generated | Labelled every simulated number as synthetic |

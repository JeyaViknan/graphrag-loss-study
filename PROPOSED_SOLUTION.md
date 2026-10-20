# Residual Graph Indexing

**Closing the retrieval-loss gap in GraphRAG**

> *Summaries forget. Residuals remember.*

---

## The pitch

GraphRAG answers broad questions by reading community summaries. We found that it throws information away **while building those summaries — before any question is asked.**

- A relationship between two entities in different communities appears in **no summary at all**.
- A community whose input exceeds the 8,000-token budget **silently drops its least-connected facts**.
- Moving up the hierarchy doesn't fix this. It **moves the loss** from community boundaries to the token budget.

Because this happens at index time, **no retriever that reads those summaries can get it back.** A better search algorithm has nothing to find.

We propose **Residual Graph Indexing (RGI)**. It keeps GraphRAG's summaries and search exactly as they are, and gives the index a *residual*: an exact, audited record of everything the summaries left out, which retrieval can use within the same token budget.

**Same summaries. Same token budget. Zero additional LLM calls. And an index that can prove it hasn't silently discarded a single relationship.**

---

## 1. The problem we found

GraphRAG builds its index in five stages: split documents into text units, extract entities and relationships, group entities into hierarchical communities (Leiden), write one LLM summary per community, then answer global questions by mapping over those summaries.

Information disappears in three places:

| Loss | Where it happens | What disappears | Can a better retriever recover it? |
|:--|:--|:--|:--|
| **L1 · Multi-topic** | Community assignment | An entity's role in the topics it wasn't assigned to | Partly. The entity is still read, but framed under one topic. |
| **L2 · Boundary** | Summary scope | Relationships whose two entities sit in different communities | **No** |
| **L3 · Budget** | Summary input | The lowest-priority elements of a community over budget | **No** |

Two details, verified in the GraphRAG source (v3.1.1), make L3 worse than it sounds:

- Summary input defaults to **8,000 tokens** (`max_input_length`).
- Elements are admitted **in descending order of connectivity** until the budget runs out, and everything after is dropped (`summarize_communities/graph_context/sort_context.py`). The loss is systematically biased against low-degree facts, which are often the specific details a factual question needs.

**The hierarchy trade-off.** Leaf communities are small, so they rarely overflow the budget, but they cut many relationships at their boundaries. Higher levels merge communities, so fewer relationships cross boundaries, but each summary must compress far more. **Choosing a level decides where the loss lands. It does not decide whether it happens.**

## 2. Why this can't be fixed at query time

Global search can only surface what a summary contains. If a relationship is lost at the operating level, then **for every retrieval policy that reads community summaries, the retrieved context cannot include it.** Better ranking, re-ranking, prompting or dynamic community selection change *which* summaries are read, not *what they contain*.

GraphRAG's *local* search does read raw entities and relationships. But it is built for questions about specific entities, and it doesn't give the dataset-wide view that global search exists for. The gap is precise: **questions that need global search's breadth and a fact the summaries dropped.** That gap can only be closed in the index.

## 3. The idea: keyframes and residuals

Video codecs don't store every frame in full. They store **keyframes**, plus **residuals**: exactly what the keyframes couldn't carry. Nothing is lost, and the residual stays small.

RGI applies the same principle to GraphRAG:

- **Keyframes** are the community summaries, unchanged.
- **The residual** is the graph minus what those summaries cover.

GraphRAG's own output records which relationships each community contains, so the residual can be computed **exactly, as a set difference over the index files, with zero LLM calls.** RGI doesn't guess what was lost. It measures it.

## 4. How it works

```
 GraphRAG index (unchanged)
 ─────────────────────────────────────────────────────────────
  entities · relationships · communities · community summaries
                              │
                              ▼
 ① Loss audit ─────── exact loss set per level (L1, L2, L3)
                              │
          ┌───────────────────┼────────────────────┐
          ▼                   ▼                    ▼
 ② Bridge records     ③ Graceful truncation   ④ Residual store
    most important       compact facts,          everything else,
    cross-community      never drops what        attached to the
    relationships        GraphRAG kept           communities it touches
          └───────────────────┼────────────────────┘
                              ▼
 ⑤ Coverage certificate ─ every relationship is accounted for
                              │
                              ▼
 Query time: global search + residual retrieval at the same token budget
```

### ① Loss audit *(built and tested)*

- **L2:** all relationship IDs minus the relationships listed inside communities, per level. This needs no LLM calls. A "permanent" variant tracks relationships that no level contains.
- **L3:** a deterministic replay of GraphRAG's own truncation, with the same sort key, budget and tokenizer.
- **L1:** an entity counts as multi-topic when the text passages it was extracted from split into distinct topics, controlling for how connected the entity is.

The output is the exact loss set at every level. **GraphRAG X-Ray**, our interactive prototype, visualises it.

### ② Bridge records → repairs L2 where it matters most

For each community, rank the relationships it lost at its boundary by **salience**: weight × combined degree, the same priority signal GraphRAG already uses. Append the top-ranked ones to **both** communities' summaries as a short *Connections to other communities* section, capped at a fixed share of the summary input (starting value: 12%).

Each record is generated from a template using the relationship description GraphRAG already extracted. **No summary is rewritten and no LLM is called.**

### ③ Graceful truncation → repairs L3

GraphRAG truncates like cutting a list with scissors: once the budget is reached, everything after is gone. RGI uses two tiers instead:

1. **Full descriptions** until about 80% of the budget.
2. **Compact one-line facts** (`SOURCE — relation — TARGET`, about 10–15 tokens each) for the rest.

RGI first reserves room for everything GraphRAG's own summary input would have kept; bridge records and extra compact facts only use what is left. **By construction, RGI's summary inputs never contain fewer relationships than GraphRAG's at any level.** Some become compact rather than full.

This changes what goes *into* each summary, so it runs inside the indexing pipeline, making the same one LLM call per community that GraphRAG already makes. It adds no calls.

### ④ Residual store and residual retrieval → catches everything else

Whatever still doesn't fit goes into the **residual store**, attached to the community or communities it touches. At query time, after global search selects its summaries, RGI adds the residual facts attached to those communities that best match the question.

These facts **replace the lowest-ranked context, so the total token count stays exactly the same.** This token-exact swap is already implemented and tested.

### ⑤ Coverage certificate → nothing is silently discarded

At build time, RGI checks that at every level:

> **relationships in summary input ∪ bridge records ∪ residual store = all relationships in the graph**

The check is a set difference with zero LLM calls. **If anything is unaccounted for, the build fails.** GraphRAG today discards information without any record. RGI makes loss visible, bounded and auditable.

*One caveat:* being included in a summary's *input* doesn't guarantee the LLM mentions it in the summary *text*. RGI can also send a relationship to the residual store when its two entities don't both appear in the written summary, a cheap string check. Our recoverability experiment (E5) measures how large this gap really is.

### ⑥ Extension: soft membership for multi-topic entities (L1)

Entities flagged as multi-topic get a one-line pointer in the summaries of their secondary communities, so their other roles aren't invisible. This is a stretch goal for the final review.

## 5. What makes RGI different

| Approach | When it acts | What it changes | What RGI adds |
|:--|:--|:--|:--|
| GraphRAG (Edge et al., 2024) | Index time | Writes community summaries | Records and repairs what those summaries lose |
| LightRAG | Query time | Retrieves entities and relationships directly; no community layer | Keeps GraphRAG's dataset-level community structure |
| HiRAG · LeanRAG | Query time | Bridge layers between communities | Bridges chosen from an **exact, audited loss set**, built into the index |
| Deep GraphRAG | Query time | Filters across communities | Restores *content*, not just which summaries get read |

Three properties together set RGI apart:

1. **Measured, not heuristic.** Every repair is chosen from the exact loss set, and every relationship is accounted for.
2. **A drop-in addition.** GraphRAG's summaries and global search keep working unchanged, and bridge records and the residual store are built from GraphRAG's own output files. Only graceful truncation touches the pipeline, by swapping one function.
3. **Budget-neutral by design.** Residuals replace context rather than adding to it, so any gain comes from *better content*, not *more tokens*.

*Before the final review we will complete a detailed related-work comparison against HiRAG, LeanRAG and Deep GraphRAG.*

## 6. What it costs

| | GraphRAG | RGI |
|:--|:--|:--|
| LLM calls to build the index | Baseline | **+0** |
| Summaries regenerated after indexing | — | **None** (graceful truncation runs inside the normal build) |
| Extra storage | — | Residual facts, about 10–15 tokens each, proportional to the loss |
| Tokens per query | Baseline | **Same** (token-exact swap) |
| Extra query-time work | — | One lookup of residuals for the selected communities |

For scale, GraphRAG-Bench reports about **331,000 tokens per global-search query** on its Novel corpus. RGI adds none.

## 7. How we will prove it

**Kill criteria, written down before any data.** The thresholds below were committed to git before an index existed, so they can't be tuned to fit the results. If any gate fires, the problem isn't worth solving and we stop.

| Gate | Question | Stop if |
|:--|:--|:--|
| **G1** | Do summaries already paraphrase the "lost" cross-community relationships? | Recoverability > 70% |
| **G2** | Do real questions actually need the lost information? | Fewer than 10% of questions need it |
| **G3** | Are wrong answers caused by the index rather than retrieval or generation? | Index-caused share < 15% of failures |
| **G4** | Does restoring the lost facts *cause* better answers? | 95% confidence interval includes zero |

**The causal test.** For each question whose gold evidence was lost, we compare two injections at an **identical token count**:

- **Oracle:** the actual lost evidence.
- **Placebo:** random lost facts of the same size.

This isolates *content* from *context length*. A plain before/after comparison can't.

**Setup**

- **Data:** GraphRAG-Bench Novel (2,010 questions with gold evidence triples), replicated on GraphRAG-Bench Medical. We exclude HotpotQA, MuSiQue and 2WikiMultihopQA because their graphs have almost no community structure to lose.
- **Compared:** GraphRAG, RGI, RGI with placebo residuals, and LightRAG.
- **Measured:** relationship retention (a full count of the graph), evidence coverage, retrieval of gold evidence, answer correctness (paired questions with bootstrap confidence intervals and McNemar's test), index-build LLM calls, and tokens per query.
- **Ablations:** bridge allowance (6%, 12%, 24%), the full-description cutoff, and the salience ranking signal.

**Target for a strong result (set in advance):** Oracle beats Placebo by more than 5 accuracy points at equal tokens.

## 8. Where we are

| Done (Review 2) | Next (final review) |
|:--|:--|
| Measurement toolkit: 9 modules and 10 experiment scripts (E0–E9), 166 passing tests | Run E0–E9 on the real Novel index and record each gate decision |
| Kill criteria and evidence-linking parameters committed before any data | Build RGI: bridge records, graceful truncation, residual store, coverage certificate |
| Token-exact context swap implemented and tested | Head-to-head evaluation against GraphRAG, placebo and LightRAG |
| Loss mechanisms confirmed in GraphRAG's own source code | Replicate on Medical and run ablations |
| **GraphRAG X-Ray** interactive prototype (runs on simulated data) | Connect X-Ray to the real index |

## 9. Risks and limits

- **Summaries may already carry the cross-community facts in paraphrase.** Gate G1 measures this *before* we build anything.
- **Earlier evidence against the hypothesis.** Edge et al. (Experiment 2) found no significant difference in aggregate answer quality between GraphRAG global search and a summarisation baseline that has no community partition at all. Our claim is narrower and measured per fact: we expect gains on **fact-retrieval and multi-hop questions whose evidence crosses communities**, not on broad sensemaking questions. We will report results by question type.
- **Residuals could crowd out useful context.** The placebo arm and the token-exact swap measure this directly.
- **The salience ranking may miss the facts that matter.** We will test allowance sizes and ranking signals, and report the retention-versus-budget curve.
- **Overlap with query-time bridging methods.** RGI's distinction is index-time repair driven by an audited loss set. The related-work comparison will be completed before the final review.

---

### Closing line

> **GraphRAG forgets before you ask. RGI remembers — at the same token budget, with zero extra LLM calls, and it can prove it.**

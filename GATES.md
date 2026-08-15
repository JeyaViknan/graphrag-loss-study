# GATES — frozen abort thresholds

**Frozen:** 2026-08-15, before any index was built, any corpus downloaded, or any
measurement taken. This repository contained no data of any kind at the time of
this commit. Git history is the proof: the commit that introduces this file
precedes every commit that produces a number.

**Source of authority:** `CONTEXT.md` §3 (kill thresholds) and
`KNOWLEDGE_BASE.md` §C (strength markers). Where this file and those documents
disagree, those documents win and this file is in error.

**This file is write-once.** It is never edited after commit. Not to clarify a
definition, not to fix a typo, not to add a caveat. A threshold that moves after
data exists is not a threshold. If an amendment is genuinely unavoidable, it
lands as a *new commit that explicitly names the gate being changed and states
that the paper's framing is being changed with it* — never as a silent edit, and
never without the user's written override in the session log.

---

## The four kill gates

| Gate | Experiment | Metric | **Kill if** |
|:--|:--|:--|:--|
| **G1** | E5 | Cross-edge recoverability via NLI | **> 0.70** |
| **G2** | E6 | P(Y(q) ∩ L ≠ ∅) | **< 0.10** |
| **G3** | E8 | Category (i) index-absent share of failures | **< 0.15** |
| **G4** | E9 | (Oracle − Placebo) accuracy delta, 95% CI | **includes zero** |

A gate fires on the **point estimate** for G1–G3 and on the **interval** for G4.
A gate that fires is a hard stop: the current framing is dead, subsequent
experiments do not run, and the result is written up as a null. Per `CONTEXT.md`
§12, a clean null with all gates fired is a successful week. The failure mode is
not a null result; it is a null result rationalized into a marginal one.

---

## Precise definitions — fixed now so they cannot be renegotiated later

These exist to remove every degree of freedom that could be used, after seeing
data, to argue a fired gate did not really fire.

### G1 — E5 recoverability (kill if > 0.70)

- **Sample:** 300 edges drawn from `cache/E_cross_perm.parquet`, stratified by
  `relationships.weight` quartile, exactly 75 per quartile.
- **Premise:** the passages describing `u` and `v` extracted from the community
  reports of `u`'s community and `v`'s community, concatenated.
- **Hypothesis:** `relationships[e].description`.
- **Metric:** fraction of the 300 classified ENTAILED (not NEUTRAL, not
  CONTRADICTED), reported overall and per stratum with bootstrap CI.
- **Precondition:** the NLI classifier is unusable until two human annotators
  label 100 items and Cohen's κ ≥ 0.7 (`CONTEXT.md` §8, `KNOWLEDGE_BASE.md` §D.6).
  The 300-edge run does not start before calibration passes.
- **Reading:** recoverability > 0.70 means the community summaries already carry
  the cross-edge content. L2 would then be bookkeeping, not loss.

### G2 — E6 gold intersection (kill if < 0.10)

- **Metric:** the fraction of benchmark questions for which the gold element set
  `Y(q)` intersects the loss set `L`.
- **`L` for this gate is the hard loss only — L2 ∪ L3.** L1 is excluded by
  construction: per `CONTEXT.md` §2, L1 does not satisfy
  `supp(R(q, I)) ∩ L = ∅`, because global search maps over all summaries and a
  misassigned entity is still read, merely in the wrong framing. Including L1
  here would inflate the gate with a loss that retrieval can still reach.
- **Precondition:** gold-sentence unlink rate < 15%. Above that, the linking is
  too lossy for the gate to mean anything and E6 is reported as inconclusive
  rather than as a pass or a fail.
- **Reading:** below 0.10, the discarded information is essentially never what a
  question needed. The loss would be real but irrelevant.

### G3 — E8 failure attribution (kill if < 0.15)

- **Metric:** share of *failed* questions assigned category (i) index-absent
  under `KNOWLEDGE_BASE.md` §H.4, where a failure satisfying more than one
  category is assigned the earliest applying category in the pipeline.
- **Precondition:** two annotators independently label the first 50 failures and
  Cohen's κ ≥ 0.7 (`CONTEXT.md` §8, `KNOWLEDGE_BASE.md` §D.7). Below 0.7 the
  automated classifier is not used: either every failure is labelled by hand or
  the experiment is dropped. Low-agreement labels are not automated.
- **Reading:** below 0.15, indexing is not what is breaking these questions, and
  repairing the index is not the highest-value intervention.

### G4 — E9 oracle vs. placebo (kill if the 95% CI includes zero)

- **Metric:** paired accuracy difference (Oracle correct) − (Placebo correct)
  across the same questions, with a 95% question-paired bootstrap CI over
  ≥1000 resamples. Reported alongside McNemar and Cohen's h.
- **Comparator:** the placebo arm, never a no-injection baseline. Per
  `CONTEXT.md` §9, E9 without E9b is invalid — an uncontrolled injection
  confounds the added information with the added tokens.
- **Preconditions, in this order and no other:**
  1. **E9a** — `inject_at_constant_budget` passes
     `len(tokenize(ctx_new)) == len(tokenize(ctx_base))` on 50 random examples.
     Token count is the contract; character length is logged as a diagnostic
     only. If this assertion fails, E9 is invalid and reports no number.
  2. **E9b** — placebo arm built and run.
  3. **E9c** — oracle arm built and run.
  Reversing this order invalidates the causal test (`CONTEXT.md` §6).
- **Reading:** a CI containing zero means restoring the discarded elements does
  not change answers. The loss would be real, queried, and causally inert.

---

## Strength markers — NOT gates

From `KNOWLEDGE_BASE.md` §C. These do not stop the week. They calibrate how
strongly the paper can be framed if the gates all pass. They are recorded here so
that "strong" cannot be redefined after the numbers arrive.

| Metric | Weak | Strong |
|:--|:--|:--|
| G1 recoverability on high-weight edges | — | < 0.40 |
| G2 P(Y(q) ∩ L ≠ ∅) | — | > 0.25 |
| G3 category (i) share | — | plurality of failures |
| G4 (Oracle − Placebo) | — | > 5 accuracy points |
| E1 weighted E_cross fraction at operating level | > 8% | > 25% |
| E4 leaf communities overflowing at 8k | > 20% | persists at 16k |
| E3 multi-topic rate among evidence-appearing entities | > 15% | + non-trivial partial correlation vs. degree |

---

## Standing constraints frozen at the same time

- **Forbidden corpora:** HotpotQA, MuSiQue, 2WikiMultihopQA — under any framing.
  Mean degree 0.60–0.65 and mean component size 2.1–2.3 (GraphRAG-Bench Table 13)
  mean there is no community structure to lose, so a null there is uninformative
  (`CONTEXT.md` §5, `KNOWLEDGE_BASE.md` §B.2).
- **E4 is conditional on E4-pre.** If the shipped summarization code diverges
  materially from Edge et al. §3.1.5, L3 is dropped from the study entirely and
  that drop is recorded. A wrong truncation number is worse than none
  (`CONTEXT.md` §6).
- **E1 carries no p-value.** It is a census of every edge in the graph, not a
  hypothesis test (`KNOWLEDGE_BASE.md` §D.4).
- **Degree confound.** Every multi-topic or centrality-adjacent metric reports
  partial correlation controlling for `entities.degree`. If the metric loses its
  variance under that control, the claim is dropped (`KNOWLEDGE_BASE.md` §D.5).
- **Counter-evidence that must appear in every writeup.** Edge et al.
  Experiment 2 found no significant difference between GraphRAG global search and
  TS, and TS has zero L1 and zero L2 by construction. This is prior evidence in
  the primary source that partition loss does not affect aggregate answer
  quality. Every results document states it and explains what element-level
  measurement adds that aggregate answer-quality metrics miss
  (`CONTEXT.md` §10, `KNOWLEDGE_BASE.md` §F.1).

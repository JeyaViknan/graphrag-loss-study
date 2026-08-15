# HANDOVER — GraphRAG indexing-loss study

**Written:** 2026-08-15. **Status:** tooling complete and tested; **no experiment
has been run against real data.** No index exists, no LLM call has been made, and
`results/`, `reports/`, `figs/` and `cache/` are empty by design.

Everything below is what a person needs to run the week once API access is
resolved.

---

## 1. What exists

| | |
|:--|:--|
| Package | `src/graphrag_loss/` — 9 modules, all implemented |
| Scripts | `scripts/` — 10 CLIs, E0 through E9 |
| Tests | `tests/` — **166 tests, all passing** on synthetic fixtures |
| Fixtures | `tests/fixtures/` — synthetic index; no test touches real data |
| Frozen thresholds | `GATES.md` (+ Appendix A), committed before any data existed |
| Corpus | `data/graphrag_bench/` — 2,010 questions, 20 novels, MIT |
| Environment | `.venv` (Python 3.11.5), `requirements.lock.txt` (153 pins) |

Verified end-to-end on the synthetic index: E0.5 passes GATE 0, E1 recovers the
known cross-edge set exactly, E9a is 50/50 token-exact, and every precondition
guard blocks with exit code 2.

---

## 2. Prerequisites checklist

- [ ] **Billing resolved.** Free-tier Gemini cannot run this week — see §7.
- [ ] **`.env`** at project root with `GEMINI_API_KEY`. *(Present already;
      gitignored.)*
- [ ] **`settings.yaml`** at the graphrag root — see the config block below.
- [ ] **NLI model downloaded.** `cross-encoder/nli-deberta-v3-base`, ~400 MB, is
      **not** yet fetched. First `05_recoverability.py` run downloads it.
- [ ] **Two annotators available.** Adithya DS and Aatreye. Both E5 and E8 block
      on their labels; see §4.
- [ ] **Corpus present** at `data/graphrag_bench/novel.json` and
      `novel_questions.json`. *(Present already.)*

### settings.yaml — Gemini through LiteLLM

graphrag composes the litellm model id as `f"{model_provider}/{model}"`
(`graphrag_llm/completion/completion_factory.py:82`), so `model_provider: gemini`
plus `model: gemini-2.5-flash` yields `gemini/gemini-2.5-flash` — the exact id
verified present in litellm 1.92.0's model map.

```yaml
completion_models:
  default_completion_model:
    model_provider: gemini
    model: gemini-2.5-flash
    auth_method: api_key
    api_key: ${GEMINI_API_KEY}
    retry:
      type: exponential_backoff
      max_retries: 10
    rate_limit:
      type: sliding_window
      period_in_seconds: 60
      requests_per_period: 10      # raise to your tier's actual RPM

embedding_models:
  default_embedding_model:
    model_provider: gemini
    model: gemini-embedding-001
    auth_method: api_key
    api_key: ${GEMINI_API_KEY}
    retry:
      type: exponential_backoff
      max_retries: 10
```

**Two warnings on this config.**

1. `gemini-embedding-001` has `max_input_tokens: 2048`. Text units at the
   default 1200-token chunk size fit, but community-report `full_content`
   routinely exceeds 2048 and will error rather than truncate.
   `gemini-embedding-2` has an 8192 cap and the same 3072 dimensions.
2. `requests_per_period: 10` matches free-tier RPM. Raise it to your real limit
   or indexing will be needlessly slow. Retry-with-backoff converts an **RPM**
   limit into slowness but an **RPD** limit into a multi-day stall — no retry
   policy can spend quota you do not have.

---

## 3. Command sequence

Run from the project root with `.venv/bin/python`. `--frozen-dir` is `output/`
throughout. Every script writes `results/<name>.csv` and `reports/<name>.md`.

```bash
# E0 — index and freeze. Once. Everything downstream is keyed to its manifest hash.
scripts/00_index.sh --root .

# E0.5 — GATE 0. Nothing proceeds until this exits 0.
.venv/bin/python scripts/01_verify_schema.py --frozen-dir output

# E1 — headline number. Day 1 morning; determines the paper's framing.
.venv/bin/python scripts/02_cross_edges.py --frozen-dir output

# E4-pre — MANUAL. See §5. Produces reports/summarization_semantics.md.

# E3 and E4 — parallel. E4 refuses to run without the E4-pre writeup.
.venv/bin/python scripts/03_multitopic.py --frozen-dir output
.venv/bin/python scripts/04_truncation_replay.py --frozen-dir output

# E5 — GATE G1. Two phases; the second blocks below kappa 0.70.
.venv/bin/python scripts/05_recoverability.py --frozen-dir output --phase calibrate
#   ... two humans fill cache/e5_calibration_sheet.csv ...
.venv/bin/python scripts/05_recoverability.py --frozen-dir output --phase run

# E6 — GATE G2.
.venv/bin/python scripts/06_gold_links.py --frozen-dir output \
    --questions data/graphrag_bench/novel_questions.json --level <operating_level>

# E7 — query harness. The expensive one.
.venv/bin/python scripts/07_query.py --frozen-dir output --root . \
    --questions data/graphrag_bench/novel_questions.json --n-questions 125

# E8 — GATE G3. Two phases; the second blocks below kappa 0.70.
.venv/bin/python scripts/08_attribution.py --frozen-dir output --phase annotate --level <L>
#   ... two humans fill cache/e8_annotation_sheet.csv ...
.venv/bin/python scripts/08_attribution.py --frozen-dir output --phase run --level <L>

# E9 — GATE G4. Order is enforced by the script: a, then b, then c.
.venv/bin/python scripts/09_inject.py --frozen-dir output --phase a
.venv/bin/python scripts/09_inject.py --frozen-dir output --phase b
.venv/bin/python scripts/09_inject.py --frozen-dir output --phase c

# Finally: write results/SUMMARY.md (<=500 words, four gate decisions,
# one number per experiment, and the Edge et al. Exp 2 reconciliation).
```

Run `.venv/bin/python -m pytest tests/ -q` at the end of every experiment day.
If a test fails, stop and fix before proceeding — do not wrap it in try/except.

### Exit codes

`0` = passed. `2` = gate fired, precondition unmet, or integrity violation.
Anything non-zero means **stop and read the report**.

---

## 4. If a gate fires

A fired gate is a hard stop. Per `CONTEXT.md` §9 no subsequent experiment runs
without an explicit override that acknowledges the framing is changing. Per §12
a clean null with all gates fired is a *successful* week — it saves five months.
The failure mode is not a null result; it is a null rationalised into a marginal
one.

| Gate | Fires when | What it means | Do |
|:--|:--|:--|:--|
| **GATE 0** | any integrity violation | the index is not what the study assumes | Stop. Fix the index or the assumption. Every downstream number is void. |
| **G1** | entailment > 0.70 | L2 is bookkeeping — summaries already carry the cross-edge content | Stop. The L2 half of the hypothesis is dead. L3 may still stand; ask before continuing on L3 alone. |
| **G2** | P(Y ∩ L ≠ ∅) < 0.10 | the loss is real but never queried | Stop. Report the null. E1's census is still a publishable measurement on its own terms. |
| **G3** | category (i) < 0.15 | indexing is not the bottleneck | Stop. E7/E8 stand as a negative result about where failures come from. |
| **G4** | (Oracle − Placebo) CI includes zero | the loss is real, queried, and causally inert | Stop. This is the strongest null available and it is worth writing up. |

**Also stop on these non-gate blocks**, which are not failures of the hypothesis
but of the measurement:

- **E5/E8 κ < 0.70** — annotators disagree. Sharpen the category definitions and
  re-annotate, or label everything by hand. Do not automate low-agreement labels.
- **E6 unlink rate > 15%** — G2 is reported *inconclusive*, neither pass nor
  fail. Do not lower the threshold to fix it; it is frozen in `GATES.md` A.2.
- **E9a not 50/50 token-exact** — E9 is invalid. Fix `injection.py`; do not run
  phases b or c.
- **E7 context not byte-reproducible** — E8 and E9 both replay that context.
  Abort rather than log something unreplayable.

---

## 5. Known open questions

1. **E4-pre is not done.** It is a manual source read, deliberately not a script.
   Read `.venv/lib/python3.11/site-packages/graphrag/index/operations/summarize_communities/`
   and write `reports/summarization_semantics.md` answering: sort key, tokenizer,
   default `max_input_length`, and whether higher-level substitution matches
   Edge et al. §3.1.5. **If it diverges materially, drop L3 from the study and
   record the drop.** `04_truncation_replay.py` refuses to run until that file
   exists.

   Partial observations already made, which the writeup should confirm and
   extend:
   - sort key: `edges.sort(key=lambda x: (-combined_degree, id))` —
     `graph_context/sort_context.py:83`
   - admission: elements appended until `num_tokens(context) > max_context_tokens`
   - tokenizer: `o200k_base` (`graphrag/config/defaults.py:39`)
   - config default: `max_input_length = 8000`; `context_builder` default 16000

   The §3.1.5 substitution question is **not** answered yet, and it is the one
   that decides whether L3 survives.

2. **`transformers` resolved to 5.15.0**, a major version.
   `cross-encoder/nli-deberta-v3-base` is an older checkpoint and has **not**
   been verified to load under it — doing so needs a ~400 MB download. If it
   breaks, pin transformers to 4.x; if that conflicts with graphrag's stack,
   split into `.venv` (pipeline) and `.venv-analysis`.

3. **Correctness is substring containment** in E8 and E9. It will miscount
   paraphrased correct answers as failures, inflating the failure denominator in
   G3. It is used because E8 and E9 must apply an identical rule or G3 and G4
   become incomparable. Upgrading to an LLM judge means changing both together.

4. **E9 needs ≥100 questions with `Y(q) ∩ L ≠ ∅`.** If E6 returns a low
   intersection rate, E9 may be unrunnable even with G2 passing. The script
   blocks and says so.

5. **The operating level is not yet chosen.** E6, E8 and E9 all take `--level`.
   Pick it from E1's per-level table and record the choice before E6 runs.

6. **`SUMMARY.md` is not templated.** It is deliberately hand-written: ≤500
   words, four gate decisions with numbers, one headline per experiment, an
   explicit strong/conditional/no-paper verdict, and the Edge et al. Exp 2
   reconciliation.

---

## 6. KB / CONTEXT divergences observed in graphrag 3.1.1

Standing rule: detect at runtime, log loudly, continue if benign, abort if an
integrity invariant breaks. **The KB constants have not been edited.** Update
`KNOWLEDGE_BASE.md` and `CONTEXT.md` after the week, not during it.

| # | Documented | Observed in 3.1.1 | Severity | Handling |
|:--|:--|:--|:--|:--|
| 1 | `text_units.relationships_ids` (plural-s), KB §A.3 / CONTEXT §4 | `relationship_ids` — the typo is **fixed**; the plural spelling appears **zero times** in the package (`data_model/schemas.py`) | **High** — CONTEXT's E0.5 spec would abort on every valid 3.1.1 index | `detect_relationship_ids_column()` accepts either; E0.5 reports the divergence and continues |
| 2 | `documents` has `metadata`, KB §A | `creation_date` + `raw_data`; no `metadata` | Low | Not required by any experiment |
| 3 | — | every file carries `human_readable_id` | Low | Recorded as an extra column |
| 4 | — | `communities` adds `period`; `text_units` adds `covariate_ids` | Low | Recorded |
| 5 | Gold `evidence` is sentence-level and matchable by substring, KB §H.3 | Sentences are **abstractive restatements**: 0.1% exact substring, 5.4% at n-gram ≥85 | **High** — E6 as specified is not runnable | Switched to `evidence_triple` (`GATES.md` Appendix A), decided and frozen before any E6 run |
| 6 | `relationships.source/target` implicitly entity ids | Entity **names** (`data_model/relationship.py`); `communities.entity_ids` holds **ids** | **High** — comparing without mapping silently passes every integrity check | `verify_intra_community_edges()` takes `entities` and maps names→ids explicitly |
| 7 | Tokenizer unspecified beyond "must match", KB §G | `ENCODING_MODEL = "o200k_base"`, not cl100k | Medium | Frozen in `GATES.md`; used by E4 and E9 |

Divergence 6 is the one that would have been most dangerous: it produces no
error, just a verification that passes vacuously. It was caught by smoke-testing
against the synthetic fixture, which is why the fixture mirrors the real schema
rather than a convenient simplification.

---

## 7. Cost and time

Corpus: `novel.json` is 4.85 MB ≈ **~1.1M tokens** ≈ **~1,000 text units** at the
default 1200-token chunking.

| Script | LLM calls | Notes |
|:--|--:|:--|
| E0 index | 3,000–5,500 | extraction (+gleanings), description summarisation, community reports |
| E0.5, E1, E3, E4 | **0** | pure index analysis; E3 embeds locally |
| E5 | 0 | NLI runs locally on CPU |
| E6 | 0 | fuzzy matching only |
| E7 | 2,500–4,000 | 125 questions × global search map-reduce |
| E9b + E9c | 200 | one regeneration per question per arm, ~100 questions each |
| **Total** | **~6,000–10,000** | ≈ **150M tokens**, dominated by E7 |

**Wall-clock on a paid tier.** At 1,000 RPM the LLM work is on the order of a
few hours end to end, and the binding constraint becomes TPM rather than RPM:
at 331k tokens/query (KB §B.3), E7's ~41M tokens need ~41 minutes at 1M TPM.
Budget **half a day** for E0 plus E7, and treat the human labelling steps (E5
calibration, E8 annotation) as the real schedule risk — they are serial, they
need two people, and both gate their experiment.

**On free tier this is not runnable.** At 250 RPD the index build alone is
12–22 days; at 1,500 RPD, 2–4 days, with E7 and E9 on top. Verify your actual
quota at <https://aistudio.google.com/rate-limit> before starting.

Local-only costs: E3 embeds ~1,000 text units with MiniLM (minutes on CPU); E5
runs 300 NLI pairs plus 100 calibration pairs on DeBERTa-v3 (minutes on CPU,
after a ~400 MB one-time download).

---

## 8. Reading the stdout

Every script prints one summary line. What to look for:

| Script | Line | Read it as |
|:--|:--|:--|
| `01` | `GATE 0 passed — N communities … 0 violations` | proceed; a `[SPELLING DIVERGENCE: …]` suffix is expected on 3.1.1 and is benign |
| `02` | `HEADLINE: E_cross_perm = X% weighted, E_cross_level(ℓ) = Y% weighted` | **the framing decision.** Large `perm` → permanent exclusion. Small `perm`, large `level` → the hierarchy relocates loss rather than removing it. KB §C markers: >8% weak, >25% strong |
| `03` | `multi-topic rate = X% …, corr with degree = r` | `[UNUSABLE — multi-topic ≈ degree]` means the metric rediscovered degree and cannot support an L1 claim |
| `04` | `leaf overflow at 8k = X%` | >20% is the weak marker; strong if it persists at 16k |
| `05` | `GATE G1 …` then `entailment = X% …, κ(humans) = k` | >70% kills L2. Check κ ≥ 0.7 first — below that the entailment number is not evidence |
| `06` | `GATE G2 …` then `P(Y ∩ L ≠ ∅) = X%, unlink = U%` | <10% kills. `E6 INCONCLUSIVE` means U > 15% and the gate did not evaluate |
| `07` | `N questions logged …, context byte-reproducibility asserted` | if it aborts, E8 and E9 cannot proceed |
| `08` | `GATE G3 …` then `category (i) = X% of N failures, κ = k` | <15% kills. κ gates the automation, as in E5 |
| `09a` | `50/50 token-exact — receipt at …` | anything less invalidates E9 |
| `09c` | `GATE G4 …` then `Δ = X points [lo, hi], McNemar p, h` | a CI containing zero kills |

---

## 9. Design decisions worth knowing before you change anything

- **`L` for G2 and E9 is L2 ∪ L3 only.** L1 is excluded because it does not
  satisfy `supp(R(q,I)) ∩ L = ∅` (CONTEXT §2) — global search reads every
  summary, so a misassigned entity is still seen, just framed wrongly. Adding L1
  would inflate the gate with a loss retrieval can reach.
- **E9's comparator is the placebo arm, never a no-injection baseline.** Without
  it the oracle arm's advantage is confounded with simply having more tokens.
- **E1 carries no p-value or CI.** It is a census (KB §D.4).
- **`report.edge_et_al_caveat()` is appended to every report unconditionally.**
  Edge et al. Exp 2 found no significant difference between global search and TS,
  and TS has zero L1 and L2 by construction. It is prior evidence in the primary
  source cutting against this hypothesis, and it must be reconciled in every
  writeup (CONTEXT §10, KB §F.1).
- **Nothing here designs an algorithm.** If the numbers look good, that is a
  finding, not a licence to start building — CONTEXT §9 requires an explicit
  override first.

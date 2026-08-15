#!/usr/bin/env python
"""E9 — causal test by token-exact injection. **GATE G4.**

Build order is enforced by this script and is not negotiable
(``CONTEXT.md`` §6, §9):

* ``--phase a`` — displacement mechanism. Verifies
  ``len(tokenize(new)) == len(tokenize(base))`` on 50 random examples drawn from
  the real logged contexts. Writes a receipt; b and c refuse to run without it.
* ``--phase b`` — placebo arm. Injects random non-gold elements from ``L``,
  token-matched to what the oracle arm will inject.
* ``--phase c`` — oracle arm. Injects the actual ``Y(q) ∩ L``, then compares
  against the placebo arm.

The comparator is the placebo arm, never a no-injection baseline. Without it,
the oracle arm's advantage is confounded with simply having more tokens of
anything, and E9 answers no causal question at all.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from graphrag_loss import injection, io as gio, report, stats  # noqa: E402

EXPERIMENT = "E9"
NAME = Path(__file__).stem
N_MECHANISM_CASES = 50
MIN_QUESTIONS = 100
RECEIPT = "e9a_mechanism_receipt.json"


def _load_outputs(path: Path) -> pd.DataFrame:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return pd.DataFrame(rows)


def _eligible(outputs: pd.DataFrame, gold_links: pd.DataFrame) -> pd.DataFrame:
    """Questions whose gold evidence intersects L — the only ones E9 can test."""
    merged = outputs.merge(gold_links, on="question_id", how="inner")
    return merged[merged["intersection_size"] > 0].reset_index(drop=True)


def _phase_a(args, stamp, outputs) -> int:
    tokenizer = injection.get_tokenizer(args.tokenizer)
    rng = random.Random(args.seed)
    contexts = [c for c in outputs["context"].astype(str) if c.strip()]
    if not contexts:
        print("E9a FAILED — no non-empty contexts in query_outputs.jsonl")
        return 2

    failures: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    for case in range(N_MECHANISM_CASES):
        base = rng.choice(contexts)
        n_tokens = injection.token_len(base, tokenizer)
        insertion_budget = max(1, int(n_tokens * rng.uniform(0.02, 0.20)))
        filler = rng.choice(contexts)
        insertion = tokenizer.decode(tokenizer.encode(filler)[:insertion_budget])
        try:
            result = injection.inject_with_report(base, [insertion], tokenizer)
            ok = result.new_tokens == result.base_tokens
            rows.append(
                {
                    "case": case, "base_tokens": result.base_tokens, "new_tokens": result.new_tokens,
                    "base_chars": result.base_chars, "new_chars": result.new_chars,
                    "inserted_tokens": result.inserted_tokens,
                    "n_dropped": len(result.dropped_piece_ids),
                    "n_truncated": len(result.truncated_piece_ids), "exact": ok,
                }
            )
            if not ok:
                failures.append({"case": case, "base": result.base_tokens, "new": result.new_tokens})
        except injection.InjectionError as exc:
            failures.append({"case": case, "error": str(exc)})

    results = pd.DataFrame(rows)
    gio.write_result_csv(results, args.results_dir / f"{NAME}.csv", stamp)

    if failures:
        print(f"E9a FAILED — {len(failures)} of {N_MECHANISM_CASES} cases not token-exact: {failures[:5]}")
        print("E9 is invalid. Do not run phase b or c.")
        return 2

    receipt = args.cache_dir / RECEIPT
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            {"cases": N_MECHANISM_CASES, "tokenizer": args.tokenizer,
             "manifest_hash": stamp.manifest_hash, "timestamp_utc": stamp.timestamp_utc},
            indent=2,
        ),
        encoding="utf-8",
    )
    report.write_report(
        args.reports_dir / f"{NAME}.md",
        title="E9a — Displacement mechanism",
        experiment="E9a", stamp=stamp,
        setup=f"{N_MECHANISM_CASES} random cases drawn from the real logged contexts, tokenizer `{args.tokenizer}`.",
        method=(
            "`inject_at_constant_budget` places the insertion at the front, re-admits "
            "base pieces in priority order until the budget is exhausted, truncates the "
            "first piece that does not fit whole, and drops the rest. Exactness is then "
            "verified by re-encoding the assembled string."
        ),
        numbers=(
            f"- Cases: **{N_MECHANISM_CASES}**\n"
            f"- Token-exact: **{int(results['exact'].sum())}/{N_MECHANISM_CASES}**\n"
            f"- Mean pieces dropped: {results['n_dropped'].mean():.2f}, truncated: {results['n_truncated'].mean():.2f}\n"
            f"- Character length varies by design (diagnostic only): mean Δ = "
            f"{(results['new_chars'] - results['base_chars']).mean():.1f}"
        ),
        gate=None,
        caveats="Character length is not asserted; only token count is the contract.",
        next_steps="E9b — `--phase b` (placebo arm). The oracle arm must not run first.",
    )
    print(f"E9a: {N_MECHANISM_CASES}/{N_MECHANISM_CASES} token-exact — receipt at {receipt}")
    return 0


def _regenerate(question: str, context: str, model: str) -> str:
    """Re-run generation against a modified context.

    Uses the same LLM as E7 through litellm, with the injected context supplied
    verbatim so the only thing that differs between arms is its content.
    """
    import litellm

    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": "Answer the question using only the provided context."},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
        ],
        num_retries=8,
    )
    return str(response.choices[0].message.content)


def _correct(answer: str, gold: str) -> bool:
    """Same substring rule as E8 — the two gates must stay comparable."""
    gold = str(gold).strip().lower()
    return bool(gold and gold in str(answer).strip().lower())


def _phase_arm(args, stamp, eligible, *, arm: str) -> int:
    tokenizer = injection.get_tokenizer(args.tokenizer)
    entities = gio.load_entities(args.frozen_dir)
    relationships = gio.load_relationships(args.frozen_dir)
    loss_pool = sorted(
        {rid for ids in eligible["in_L2_ids"] for rid in ids}
        | {rid for ids in eligible["in_L3_ids"] for rid in ids}
    )

    rows = []
    for _, row in eligible.iterrows():
        oracle_ids = list(row["in_L2_ids"]) + list(row["in_L3_ids"])
        oracle_text = injection.render_elements(entities, relationships, oracle_ids)
        budget = sum(injection.token_len(t, tokenizer) for t in oracle_text)
        if budget == 0:
            continue

        if arm == "oracle":
            insertions = oracle_text
        else:
            insertions = injection.sample_placebo_elements(
                loss_pool, target_tokens=budget, exclude_ids=oracle_ids,
                entities=entities, relationships=relationships,
                tokenizer=tokenizer, seed=args.seed,
            )
        if not insertions:
            continue

        try:
            new_context = injection.inject_at_constant_budget(str(row["context"]), insertions, tokenizer)
        except injection.InjectionError as exc:
            print(f"E9{'c' if arm == 'oracle' else 'b'} FAILED on {row['question_id']}: {exc}")
            return 2

        answer = _regenerate(str(row["question"]), new_context, args.llm_model)
        rows.append(
            {
                "question_id": row["question_id"],
                "arm": arm,
                "correct": _correct(answer, row.get("gold_answer", "")),
                "baseline_correct": _correct(row.get("answer", ""), row.get("gold_answer", "")),
                "injected_tokens": budget,
                "answer": answer,
            }
        )

    out = pd.DataFrame(rows)
    path = args.cache_dir / f"e9{'c' if arm == 'oracle' else 'b'}_{arm}.parquet"
    gio.write_cache(out, path, stamp)
    print(f"E9{'c' if arm == 'oracle' else 'b'}: {len(out)} questions, "
          f"accuracy = {100 * out['correct'].mean():.1f}% -> {path}")
    return 0 if arm == "placebo" else _final_analysis(args, stamp, out)


def _final_analysis(args, stamp, oracle: pd.DataFrame) -> int:
    placebo, placebo_meta = gio.read_cache(args.cache_dir / "e9b_placebo.parquet")
    gio.assert_same_index([stamp, placebo_meta])

    merged = oracle.merge(placebo, on="question_id", suffixes=("_oracle", "_placebo"))
    if merged.empty:
        print("E9c FAILED — no paired questions between the oracle and placebo arms.")
        return 2

    o = merged["correct_oracle"].to_numpy(dtype=bool)
    p = merged["correct_placebo"].to_numpy(dtype=bool)
    delta = stats.paired_bootstrap_diff(o.astype(float), p.astype(float), seed=args.seed)
    mcnemar = stats.mcnemar_test(o, p)
    h = stats.cohens_h(float(o.mean()), float(p.mean()))

    results = pd.DataFrame(
        [
            {"quantity": "accuracy_oracle", "value": float(o.mean()), "ci_low": float("nan"),
             "ci_high": float("nan"), "n": len(o), "method": "point"},
            {"quantity": "accuracy_placebo", "value": float(p.mean()), "ci_low": float("nan"),
             "ci_high": float("nan"), "n": len(p), "method": "point"},
            {"quantity": "delta_oracle_minus_placebo", "value": delta.value, "ci_low": delta.ci_low,
             "ci_high": delta.ci_high, "n": delta.n, "method": delta.method},
            {"quantity": "cohens_h", "value": h, "ci_low": float("nan"), "ci_high": float("nan"),
             "n": len(o), "method": "cohens-h"},
            {"quantity": "mcnemar_p", "value": mcnemar.p_value, "ci_low": float("nan"),
             "ci_high": float("nan"), "n": len(o), "method": mcnemar.method},
        ]
    )
    gio.write_result_csv(results, args.results_dir / f"{NAME}.csv", stamp)

    includes_zero = bool(delta.ci_low <= 0.0 <= delta.ci_high)
    gate = report.GateDecision(
        gate="G4", metric="(Oracle − Placebo) accuracy delta, 95% CI",
        value=delta.value, threshold=0.0, fired=includes_zero,
        rule="LOSS NOT CAUSAL — restoring the discarded elements does not change answers",
    )

    report.write_report(
        args.reports_dir / f"{NAME}.md",
        title="E9 — Oracle vs. placebo injection",
        experiment=EXPERIMENT, stamp=stamp,
        setup=f"{len(merged)} paired questions with Y(q) ∩ L ≠ ∅. Model `{args.llm_model}`.",
        method=(
            "Both arms inject at token-exact constant budget (E9a verified). The placebo "
            "arm injects random non-gold elements from L matched to the oracle arm's token "
            "count; the oracle arm injects the actual Y(q) ∩ L. Paired bootstrap on the "
            "difference, McNemar on discordant pairs, Cohen's h for effect size."
        ),
        numbers="\n".join(
            [
                f"- Oracle accuracy: **{100 * o.mean():.1f}%**",
                f"- Placebo accuracy: **{100 * p.mean():.1f}%**",
                f"- Δ (Oracle − Placebo): {report.format_estimate(delta, pct=True)}",
                f"- McNemar: b={mcnemar.b}, c={mcnemar.c}, p={mcnemar.p_value:.4g} ({mcnemar.method})",
                f"- Cohen's h: {h:.3f}",
            ]
        ),
        gate=gate,
        caveats=(
            "The comparator is the placebo arm, never a no-injection baseline (CONTEXT §9). "
            "Correctness uses the same substring rule as E8. Only questions whose gold "
            "evidence actually intersects L are testable, so this estimates the effect "
            "where the loss bites, not an average over all questions."
        ),
        next_steps="Write `results/SUMMARY.md`." if not gate.fired else "Stop. G4 fired.",
    )

    print(gate.stdout_line())
    print(
        f"E9: Δ = {100 * delta.value:.1f} points "
        f"[{100 * delta.ci_low:.1f}, {100 * delta.ci_high:.1f}] (n={delta.n}), "
        f"McNemar p={mcnemar.p_value:.4g}, h={h:.3f}"
    )
    return 2 if gate.fired else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--repo-dir", type=Path, default=Path("."))
    parser.add_argument("--phase", choices=["a", "b", "c"], required=True)
    parser.add_argument("--tokenizer", default="o200k_base")
    parser.add_argument("--llm-model", default="gemini/gemini-2.5-flash")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    gio.require_inputs([args.cache_dir / "query_outputs.jsonl"], experiment=EXPERIMENT)
    stamp = gio.make_run_stamp(
        args.frozen_dir, experiment=EXPERIMENT, script=NAME,
        repo_dir=args.repo_dir, llm_model=args.llm_model,
    )
    outputs = _load_outputs(args.cache_dir / "query_outputs.jsonl")

    if args.phase == "a":
        return _phase_a(args, stamp, outputs)

    if not (args.cache_dir / RECEIPT).exists():
        print(
            f"E9{args.phase} BLOCKED — {args.cache_dir / RECEIPT} not found. Phase a must "
            f"pass first: without a verified token-exact mechanism the causal comparison "
            f"is invalid (CONTEXT §6)."
        )
        return 2

    gio.require_inputs([args.cache_dir / "gold_links.parquet"], experiment=EXPERIMENT)
    gold_links, gold_meta = gio.read_cache(args.cache_dir / "gold_links.parquet")
    gio.assert_same_index([stamp, gold_meta])
    eligible = _eligible(outputs, gold_links)

    if len(eligible) < MIN_QUESTIONS:
        print(
            f"E9{args.phase} BLOCKED — only {len(eligible)} questions have Y(q) ∩ L ≠ ∅; "
            f"the design requires ≥{MIN_QUESTIONS}."
        )
        return 2

    if args.phase == "b":
        return _phase_arm(args, stamp, eligible, arm="placebo")

    if not (args.cache_dir / "e9b_placebo.parquet").exists():
        print(
            "E9c BLOCKED — the placebo arm has not run. E9 without E9b is invalid "
            "(CONTEXT §9): the oracle arm must be compared against a token-matched "
            "placebo, not against a no-injection baseline."
        )
        return 2
    return _phase_arm(args, stamp, eligible, arm="oracle")


if __name__ == "__main__":
    raise SystemExit(main())

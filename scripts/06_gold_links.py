#!/usr/bin/env python
"""E6 — gold evidence linking and intersection with L. **GATE G2.**

Resolves each question's gold evidence to index elements, then asks how often
those elements fall inside the loss set. If the discarded information is
essentially never what a question needed, the loss is real but irrelevant and
G2 fires below 0.10.

``L`` here is **L2 ∪ L3 only**. L1 is excluded by construction: per
``CONTEXT.md`` §2 it does not satisfy ``supp(R(q, I)) ∩ L = ∅``, because global
search maps over every summary and a misassigned entity is still read. Counting
L1 would inflate the gate with a loss retrieval can still reach.

Linking parameters are frozen in ``GATES.md`` Appendix A and are not exposed as
tunable flags — ``--threshold`` exists only for the ablation strategy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from graphrag_loss import io as gio  # noqa: E402
from graphrag_loss import linking, loss, report, stats  # noqa: E402

EXPERIMENT = "E6"
NAME = Path(__file__).stem
G2_KILL_THRESHOLD = 0.10
UNLINK_PRECONDITION = 0.15


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-dir", type=Path, required=True)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--repo-dir", type=Path, default=Path("."))
    parser.add_argument("--strategy", choices=[s.value for s in linking.LinkStrategy],
                        default=linking.LinkStrategy.TRIPLE.value)
    parser.add_argument("--threshold", type=float, default=85.0,
                        help="frozen at 85 for TRIPLE (GATES A.2); adjustable only for ablation")
    parser.add_argument("--level", type=int, default=None, help="operating level for L3")
    args = parser.parse_args()

    gio.require_inputs([args.cache_dir / "E_cross_perm.parquet"], experiment=EXPERIMENT)
    stamp = gio.make_run_stamp(
        args.frozen_dir, experiment=EXPERIMENT, script=NAME,
        repo_dir=args.repo_dir, corpus_path=args.questions,
    )

    strategy = linking.LinkStrategy(args.strategy)
    if strategy is linking.LinkStrategy.TRIPLE and args.threshold != 85.0:
        print(
            f"E6 BLOCKED — threshold {args.threshold} differs from the frozen 85.0 for "
            f"LinkStrategy.TRIPLE (GATES.md Appendix A.2). Re-tuning after seeing "
            f"results is exactly what the freeze prevents."
        )
        return 2

    cfg = linking.LinkConfig(strategy=strategy, threshold=args.threshold)
    questions = linking.load_questions(args.questions)
    links = linking.build_gold_links(args.frozen_dir, questions, cfg)

    loss_set = loss.build_loss_set(
        cross_edges=args.cache_dir / "E_cross_perm.parquet",
        dropped=args.cache_dir / "L3_dropped.parquet",
        multitopic=None,  # L1 is deliberately excluded from the gate's L
        level=args.level,
    )

    per_question: list[dict[str, object]] = []
    for qid, group in links.groupby("question_id", sort=True):
        gold: set[str] = set()
        for _, row in group.iterrows():
            gold |= {str(x) for x in gio.as_list(row["entity_ids"])}
            gold |= {str(x) for x in gio.as_list(row["relationship_ids"])}
        split = loss.intersect(gold, loss_set)
        per_question.append(
            {
                "question_id": qid,
                "gold_element_ids": sorted(gold),
                "gold_size": len(gold),
                "in_L2_ids": sorted(split["in_L2"]),
                "in_L3_ids": sorted(split["in_L3"]),
                "intersection_size": len(split["in_L_hard"]),
                "n_evidence_items": len(group),
                "n_unlinked_items": int((~group["linked"]).sum()),
            }
        )
    gold_links = pd.DataFrame(per_question)
    gio.write_cache(gold_links, args.cache_dir / "gold_links.parquet", stamp)

    unlink = linking.unlink_rate(links)
    inconclusive = bool(unlink.value > UNLINK_PRECONDITION)

    linked_questions = gold_links[gold_links["gold_size"] > 0]
    hits = (linked_questions["intersection_size"] > 0).to_numpy(dtype=bool)
    p_intersect = stats.bootstrap_proportion(hits)

    severity_values = (
        linked_questions.loc[linked_questions["intersection_size"] > 0, "intersection_size"]
        / linked_questions.loc[linked_questions["intersection_size"] > 0, "gold_size"]
    )
    severity = stats.bootstrap_mean(severity_values.to_numpy(dtype=float))

    results = pd.DataFrame(
        [
            {"quantity": "unlink_rate", "value": unlink.value, "ci_low": unlink.ci_low,
             "ci_high": unlink.ci_high, "n": unlink.n, "method": unlink.method},
            {"quantity": "P(Y_intersect_L_nonempty)", "value": p_intersect.value,
             "ci_low": p_intersect.ci_low, "ci_high": p_intersect.ci_high,
             "n": p_intersect.n, "method": p_intersect.method},
            {"quantity": "mean_severity_given_intersection", "value": severity.value,
             "ci_low": severity.ci_low, "ci_high": severity.ci_high,
             "n": severity.n, "method": severity.method},
        ]
    )
    gio.write_result_csv(results, args.results_dir / f"{NAME}.csv", stamp)

    gate = report.GateDecision(
        gate="G2", metric="P(Y(q) ∩ L ≠ ∅)",
        value=p_intersect.value, threshold=G2_KILL_THRESHOLD,
        fired=bool(p_intersect.value < G2_KILL_THRESHOLD) and not inconclusive,
        rule="LOSS NEVER QUERIED — gold evidence essentially never falls in L",
    )

    numbers = [
        report.estimates_table(
            {
                "Unlink rate": unlink,
                "P(Y(q) ∩ L ≠ ∅)": p_intersect,
                "Mean severity |Y∩L|/|Y| given intersection": severity,
            },
            pct=True,
        ),
        "",
        f"- Questions with resolvable gold evidence: {len(linked_questions)} of {len(gold_links)}",
        f"- L2 size: {len(loss_set.l2_relationship_ids)} relationships",
        f"- L3 size: {len(loss_set.l3_element_ids)} elements",
    ]
    if inconclusive:
        numbers += [
            "",
            f"> ⚠ **INCONCLUSIVE.** Unlink rate {100 * unlink.value:.1f}% exceeds the "
            f"{100 * UNLINK_PRECONDITION:.0f}% precondition. Per GATES.md §G2 the linking "
            f"is too lossy for the gate to mean anything; G2 is reported as neither pass "
            f"nor fail.",
        ]

    report.write_report(
        args.reports_dir / f"{NAME}.md",
        title="E6 — Gold evidence linking",
        experiment=EXPERIMENT, stamp=stamp,
        setup=(
            f"Questions `{args.questions}` ({len(questions)} total). Strategy "
            f"`{cfg.strategy.value}`, scorer `{cfg.scorer}`, threshold {cfg.threshold} "
            f"— frozen in GATES.md Appendix A before this ran."
        ),
        method=(
            "Each `evidence_triple` is parsed to (head, relation, tail); head and tail "
            "are matched against `entities.title` and **both** must clear the threshold. "
            "Relationships with both endpoints among the resolved entities are collected. "
            "The union across a question's evidence forms Y(q), which is then intersected "
            "with L = L2 ∪ L3."
        ),
        numbers="\n".join(numbers),
        gate=None if inconclusive else gate,
        caveats=(
            "Gold `evidence` sentences in this corpus are abstractive restatements, not "
            "extracts — 0.1% appear verbatim in their source novel — so KB §H.3's "
            "substring formulation does not apply and the triple route is used instead "
            "(GATES.md A.1). L1 is excluded from L for this gate by construction "
            "(CONTEXT §2)."
        ),
        next_steps="E7 — `scripts/07_query.py`." if not gate.fired else "Stop. G2 fired.",
    )

    if inconclusive:
        print(f"E6 INCONCLUSIVE — unlink rate {100 * unlink.value:.1f}% > {100 * UNLINK_PRECONDITION:.0f}%")
        return 2
    print(gate.stdout_line())
    print(
        f"E6: P(Y ∩ L ≠ ∅) = {100 * p_intersect.value:.1f}% "
        f"[{100 * p_intersect.ci_low:.1f}, {100 * p_intersect.ci_high:.1f}] (n={p_intersect.n}), "
        f"unlink = {100 * unlink.value:.1f}%, mean severity = {severity.value:.3f}"
    )
    return 2 if gate.fired else 0


if __name__ == "__main__":
    raise SystemExit(main())

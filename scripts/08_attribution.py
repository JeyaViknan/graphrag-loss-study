#!/usr/bin/env python
"""E8 — failure attribution. **GATE G3.**

Every failed question is assigned exactly one of KB §H.4's categories, earliest
stage in the pipeline winning: (i) index-absent, (ii) not-selected, (iii)
not-used. If indexing is not where these questions break, repairing the index is
not the highest-value intervention and G3 fires below a 15% share for (i).

Two phases, order enforced:

1. ``--phase annotate`` writes a blank 50-item sheet for two annotators, with
   the automated category withheld so they are not anchored by the classifier
   whose reliability they are establishing.
2. ``--phase run`` computes Cohen's κ and **refuses to report automated labels
   below κ = 0.70** (KB §D.7). Below that floor the options are manual labelling
   of everything or dropping the experiment — not automation with a caveat.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from graphrag_loss import attribution, io as gio, report  # noqa: E402

EXPERIMENT = "E8"
NAME = Path(__file__).stem
G3_KILL_THRESHOLD = 0.15


def _load_outputs(path: Path) -> pd.DataFrame:
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return pd.DataFrame(rows)


def _is_failure(row: pd.Series) -> bool:
    """Substring-containment correctness, the same rule E9 uses.

    Deliberately crude and deliberately identical across E8 and E9: a
    sophisticated judge that differed between the two would make G3 and G4
    incomparable.
    """
    gold = str(row.get("gold_answer", "")).strip().lower()
    answer = str(row.get("answer", "")).strip().lower()
    return not (gold and gold in answer)


def _pie(shares: dict[str, float], path: Path) -> Path | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    labels = [f"({k}) {attribution.FailureCategory(k).label}" for k in shares]
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.pie(list(shares.values()), labels=labels, autopct="%1.1f%%",
           colors=["#E45756", "#F58518", "#4C78A8"])
    ax.set_title("Failure attribution")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--figs-dir", type=Path, default=Path("figs"))
    parser.add_argument("--repo-dir", type=Path, default=Path("."))
    parser.add_argument("--phase", choices=["annotate", "run"], required=True)
    parser.add_argument("--annotation-sheet", type=Path, default=Path("cache/e8_annotation_sheet.csv"))
    parser.add_argument("--level", type=int, required=True, help="operating level")
    args = parser.parse_args()

    gio.require_inputs(
        [args.cache_dir / "query_outputs.jsonl", args.cache_dir / "gold_links.parquet"],
        experiment=EXPERIMENT,
    )
    stamp = gio.make_run_stamp(
        args.frozen_dir, experiment=EXPERIMENT, script=NAME, repo_dir=args.repo_dir
    )

    outputs = _load_outputs(args.cache_dir / "query_outputs.jsonl")
    gold_links, gold_meta = gio.read_cache(args.cache_dir / "gold_links.parquet")
    gio.assert_same_index([stamp, gold_meta])

    outputs["failed"] = outputs.apply(_is_failure, axis=1)
    failures = outputs[outputs["failed"]].merge(gold_links, on="question_id", how="left")

    if failures.empty:
        print("E8: no failed questions — nothing to attribute.")
        return 0

    if args.phase == "annotate":
        sheet = failures.assign(context_preview=failures["context"].astype(str).str[:1500])
        path = attribution.write_annotation_sheet(sheet, args.annotation_sheet, n=50)
        print(
            f"E8 annotation sheet written to {path} ({min(50, len(failures))} of "
            f"{len(failures)} failures). Two annotators must fill label_a and label_b "
            f"with i / ii / iii. Cohen's κ must reach {attribution.KAPPA_FLOOR} before "
            f"--phase run will report automated labels."
        )
        return 0

    if not args.annotation_sheet.exists():
        print(f"E8 BLOCKED — {args.annotation_sheet} not found. Run --phase annotate first.")
        return 2

    annotations = attribution.read_annotations(args.annotation_sheet)
    kappa = attribution.annotator_agreement(annotations["label_a"], annotations["label_b"])
    if kappa.value < attribution.KAPPA_FLOOR:
        report.write_report(
            args.reports_dir / f"{NAME}.md",
            title="E8 — Failure attribution (BLOCKED at agreement)",
            experiment=EXPERIMENT, stamp=stamp,
            setup=f"{len(annotations)} double-labelled failures.",
            method="Two annotators, three categories, Cohen's κ (KB §D.7).",
            numbers=f"κ = {report.format_estimate(kappa)} — below the {attribution.KAPPA_FLOOR} floor.",
            gate=None,
            caveats=(
                "Per KB §D.7, low-agreement labels are not automated. Either label every "
                "failure by hand or drop E8. No category distribution is reported here, "
                "because one computed from an unreliable rule set would not be evidence."
            ),
            next_steps="Sharpen the category definitions and re-annotate, or drop E8.",
        )
        print(f"E8 BLOCKED — κ = {kappa.value:.3f} < {attribution.KAPPA_FLOOR}")
        return 2

    all_summary = attribution.summary_elements(args.frozen_dir, level=args.level)
    inputs = [
        attribution.AttributionInput(
            question_id=str(row["question_id"]),
            gold_element_ids=frozenset(str(x) for x in (row.get("gold_element_ids") or [])),
            context_community_ids=frozenset(str(x) for x in (row.get("community_ids") or [])),
            context_element_ids=attribution.reachable_elements(
                args.frozen_dir, row.get("community_ids") or [], level=args.level
            ),
        )
        for _, row in failures.iterrows()
    ]
    labelled = attribution.classify_all(inputs, all_summary_elements=all_summary)
    shares = attribution.category_shares(labelled["category"])
    counts = labelled["category"].value_counts().to_dict()

    results = pd.DataFrame(
        [
            {"quantity": f"share_category_{k}", "value": e.value, "ci_low": e.ci_low,
             "ci_high": e.ci_high, "n": e.n, "method": e.method}
            for k, e in shares.items()
        ]
        + [{"quantity": "kappa_annotators", "value": kappa.value, "ci_low": kappa.ci_low,
            "ci_high": kappa.ci_high, "n": kappa.n, "method": kappa.method}]
    )
    gio.write_result_csv(results, args.results_dir / f"{NAME}.csv", stamp)

    fig = _pie({k: e.value for k, e in shares.items()}, args.figs_dir / f"{NAME}_pie.png")

    cat_i = shares[attribution.FailureCategory.INDEX_ABSENT.value]
    gate = report.GateDecision(
        gate="G3", metric="category (i) index-absent share of failures",
        value=cat_i.value, threshold=G3_KILL_THRESHOLD,
        fired=bool(cat_i.value < G3_KILL_THRESHOLD),
        rule="INDEXING NOT THE BOTTLENECK",
    )

    numbers = [
        f"- Failures: **{len(failures)}** of {len(outputs)} questions",
        "",
        report.estimates_table(
            {f"({k}) {attribution.FailureCategory(k).label}": e for k, e in shares.items()}, pct=True
        ),
        "",
        f"Counts: {counts}",
        "",
        f"Inter-annotator κ: {report.format_estimate(kappa)} (floor {attribution.KAPPA_FLOOR}).",
    ]
    if fig:
        numbers += ["", f"![failure attribution]({fig.as_posix()})"]

    report.write_report(
        args.reports_dir / f"{NAME}.md",
        title="E8 — Failure attribution",
        experiment=EXPERIMENT, stamp=stamp,
        setup=f"Operating level {args.level}; {len(failures)} failures from `query_outputs.jsonl`.",
        method=(
            "KB §H.4, earliest applicable stage wins. (i) some gold element is in no "
            "summary at the operating level; (ii) all are in some summary but not in the "
            "assembled context; (iii) all are represented in the context but the answer "
            "does not reflect them. Correctness uses the same substring rule as E9 so "
            "that G3 and G4 remain comparable."
        ),
        numbers="\n".join(numbers),
        gate=gate,
        caveats=(
            "Substring-containment correctness is crude and will miscount paraphrased "
            "correct answers as failures, inflating the denominator. It is used because "
            "E9 must apply the identical rule; a judge model would have to be introduced "
            "to both arms simultaneously or not at all."
        ),
        next_steps="E9a — `scripts/09_inject.py --phase a`." if not gate.fired else "Stop. G3 fired.",
    )

    print(gate.stdout_line())
    print(
        f"E8: category (i) = {100 * cat_i.value:.1f}% "
        f"[{100 * cat_i.ci_low:.1f}, {100 * cat_i.ci_high:.1f}] of {len(failures)} failures, "
        f"κ = {kappa.value:.3f}"
    )
    return 2 if gate.fired else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""E5 — cross-edge recoverability via NLI. **GATE G1.**

For a stratified sample of cross-edges, the passages describing the two
endpoints in their respective community reports form the premise and the
relationship description is the hypothesis. If the summaries already entail the
relationship, L2 is bookkeeping rather than loss — and above 0.70 entailment,
G1 fires and the framing is dead.

Two phases, and the order is enforced by this script:

1. ``--phase calibrate`` writes a blank 100-item sheet for two human
   annotators. Nothing else runs.
2. ``--phase run`` reads the completed sheet, computes Cohen's κ, and **refuses
   to proceed unless κ ≥ 0.70** (KB §D.6). Model output on out-of-domain text is
   not evidence until it has been calibrated against humans.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from graphrag_loss import io as gio  # noqa: E402
from graphrag_loss import loss, nli, report, schema as S, stats  # noqa: E402

EXPERIMENT = "E5"
NAME = Path(__file__).stem
G1_KILL_THRESHOLD = 0.70
N_PER_STRATUM = 75


def _build_items(frozen_dir: Path, edge_ids: list[str]) -> pd.DataFrame:
    """Assemble (premise, hypothesis) pairs for a set of cross-edges."""
    index = gio.load_index(frozen_dir)
    id_by_title = dict(zip(index.entities[S.Entities.TITLE], index.entities[S.Entities.ID], strict=True))
    e2c = {
        level: dict(
            zip(
                loss.entity_to_community(index.communities, level)["entity_id"],
                loss.entity_to_community(index.communities, level)[S.Communities.COMMUNITY],
                strict=True,
            )
        )
        for level in index.levels()
    }
    leaf = min(e2c)
    rel = index.relationships.set_index(S.Relationships.ID)

    rows = []
    for rid in edge_ids:
        if rid not in rel.index:
            continue
        r = rel.loc[rid]
        title_u, title_v = str(r[S.Relationships.SOURCE]), str(r[S.Relationships.TARGET])
        cu = e2c[leaf].get(id_by_title.get(title_u))
        cv = e2c[leaf].get(id_by_title.get(title_v))
        rows.append(
            {
                "relationship_id": rid,
                "weight": float(r[S.Relationships.WEIGHT]),
                "premise": nli.build_premise(index.community_reports, cu, cv, title_u, title_v),
                "hypothesis": str(r[S.Relationships.DESCRIPTION]),
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--repo-dir", type=Path, default=Path("."))
    parser.add_argument("--phase", choices=["calibrate", "run"], required=True)
    parser.add_argument("--calibration-sheet", type=Path, default=Path("cache/e5_calibration_sheet.csv"))
    parser.add_argument("--nli-model", default="cross-encoder/nli-deberta-v3-base")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--n-per-stratum", type=int, default=N_PER_STRATUM)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    gio.require_inputs([args.cache_dir / "E_cross_perm.parquet"], experiment=EXPERIMENT)
    stamp = gio.make_run_stamp(
        args.frozen_dir, experiment=EXPERIMENT, script=NAME,
        repo_dir=args.repo_dir, nli_model=args.nli_model,
    )

    cross, _meta = gio.read_cache(args.cache_dir / "E_cross_perm.parquet")
    relationships = gio.load_relationships(args.frozen_dir)
    weights = relationships.set_index(S.Relationships.ID)[S.Relationships.WEIGHT]
    frame = pd.DataFrame({"relationship_id": cross["relationship_id"].astype(str)})
    frame["weight"] = frame["relationship_id"].map(weights.astype(float))
    frame = frame.dropna(subset=["weight"])
    frame["stratum"] = stats.weight_quartiles(frame["weight"])

    sample = stats.stratified_sample(
        frame, strata_col="stratum", n_per_stratum=args.n_per_stratum, seed=args.seed
    )
    items = _build_items(args.frozen_dir, sample["relationship_id"].tolist())
    items = items.merge(sample[["relationship_id", "stratum"]], on="relationship_id", how="left")

    if args.phase == "calibrate":
        path = nli.write_calibration_sheet(items, args.calibration_sheet, n=100, seed=args.seed)
        print(
            f"E5 calibration sheet written to {path} ({min(100, len(items))} items). "
            f"Two annotators must fill label_a and label_b with "
            f"ENTAILED / NEUTRAL / CONTRADICTED. Cohen's κ must reach {nli.KAPPA_FLOOR} "
            f"before --phase run will proceed."
        )
        return 0

    if not args.calibration_sheet.exists():
        print(f"E5 BLOCKED — {args.calibration_sheet} not found. Run --phase calibrate first.")
        return 2

    labelled = nli.read_human_labels(args.calibration_sheet)
    if labelled.empty:
        print(f"E5 BLOCKED — {args.calibration_sheet} has no completed rows.")
        return 2

    classifier = nli.NLIClassifier(nli.NLIConfig(model_name=args.nli_model, device=args.device))
    cal_preds = classifier.classify_batch(
        list(zip(labelled["premise"].astype(str), labelled["hypothesis"].astype(str), strict=True))
    )
    calibration = nli.calibrate(labelled["label_a"], labelled["label_b"], [p.label for p in cal_preds])

    if not calibration.passed:
        report.write_report(
            args.reports_dir / f"{NAME}.md",
            title="E5 — Recoverability (BLOCKED at calibration)",
            experiment=EXPERIMENT, stamp=stamp,
            setup=f"NLI `{args.nli_model}`; {calibration.n} human-labelled items.",
            method="Two annotators, three-way labels, Cohen's κ (KB §D.6).",
            numbers=calibration.summary(),
            gate=None,
            caveats=(
                f"κ = {calibration.kappa_humans.value:.3f} is below the {nli.KAPPA_FLOOR} floor. "
                "Per KB §D.6 the NLI is unusable here: recalibrate with clearer guidelines "
                "or drop E5. No entailment rate is reported, because an uncalibrated one "
                "would be a number without evidential value."
            ),
            next_steps="Recalibrate or drop E5. Do not run the 300-edge sample.",
        )
        print(f"E5 BLOCKED — {calibration.summary()}")
        return 2

    preds = classifier.classify_batch(
        list(zip(items["premise"].astype(str), items["hypothesis"].astype(str), strict=True))
    )
    items = items.assign(nli_label=[p.label.value for p in preds])

    overall = nli.entailment_rate(items["nli_label"])
    per_stratum = nli.entailment_rate(items["nli_label"], strata=items["stratum"])
    high_weight = nli.entailment_rate(items.loc[items["stratum"] == "Q4", "nli_label"])

    results = pd.DataFrame(
        [
            {"quantity": "entailment_rate_overall", "value": overall.value, "ci_low": overall.ci_low,
             "ci_high": overall.ci_high, "n": overall.n, "method": overall.method},
            *[
                {"quantity": f"entailment_rate_{q}", "value": e.value, "ci_low": e.ci_low,
                 "ci_high": e.ci_high, "n": e.n, "method": e.method}
                for q, e in per_stratum.items()
            ],
            {"quantity": "kappa_humans", "value": calibration.kappa_humans.value,
             "ci_low": calibration.kappa_humans.ci_low, "ci_high": calibration.kappa_humans.ci_high,
             "n": calibration.n, "method": calibration.kappa_humans.method},
        ]
    )
    gio.write_result_csv(results, args.results_dir / f"{NAME}.csv", stamp)

    gate = report.GateDecision(
        gate="G1", metric="cross-edge recoverability (entailment rate)",
        value=overall.value, threshold=G1_KILL_THRESHOLD,
        fired=bool(overall.value > G1_KILL_THRESHOLD),
        rule="L2 IS BOOKKEEPING — summaries already entail the cross-edge content",
    )

    report.write_report(
        args.reports_dir / f"{NAME}.md",
        title="E5 — Cross-edge recoverability",
        experiment=EXPERIMENT, stamp=stamp,
        setup=(
            f"{len(items)} cross-edges from `E_cross_perm`, stratified by weight quartile "
            f"({args.n_per_stratum} per stratum). NLI `{args.nli_model}` on {args.device}, "
            f"independent of the pipeline LLM (KB §G)."
        ),
        method=(
            "Premise = passages naming each endpoint, extracted from the two endpoints' "
            "community reports and concatenated. Hypothesis = the relationship "
            "description. Label ENTAILED / NEUTRAL / CONTRADICTED. Calibrated first "
            "against two human annotators on 100 items."
        ),
        numbers="\n".join(
            [
                report.estimates_table({"Entailment rate (overall)": overall}, pct=True),
                "", "### By weight stratum", "",
                report.estimates_table({str(q): e for q, e in per_stratum.items()}, pct=True),
                "", f"High-weight (Q4) rate: {report.format_estimate(high_weight, pct=True)} "
                    f"— KB §C strength marker is < 40%.",
                "", "### Calibration", "", calibration.summary(),
            ]
        ),
        gate=gate,
        caveats=(
            "Premise construction is windowed around each endpoint's name rather than "
            "using the whole report. Handing over the full report would let unrelated "
            "content entail the hypothesis and inflate recoverability — the direction "
            "that would wrongly fire G1."
        ),
        next_steps="E6 — `scripts/06_gold_links.py` [G2]." if not gate.fired else "Stop. G1 fired.",
    )

    print(gate.stdout_line())
    print(
        f"E5: entailment = {100 * overall.value:.1f}% "
        f"[{100 * overall.ci_low:.1f}, {100 * overall.ci_high:.1f}] (n={overall.n}), "
        f"κ(humans) = {calibration.kappa_humans.value:.3f}"
    )
    return 2 if gate.fired else 0


if __name__ == "__main__":
    raise SystemExit(main())

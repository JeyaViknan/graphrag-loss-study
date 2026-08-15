#!/usr/bin/env python
"""E1 — cross-edge census. The headline number; run first on Day 1.

Reports ``E_cross_perm`` and ``E_cross_level(ℓ)`` for every ℓ, each as a raw
count, a fraction of |E|, and a weight-adjusted fraction. Both quantities matter
because the paper's framing depends on which is large (KB §A.2): a large
``E_cross_perm`` supports permanent exclusion, while a large
``E_cross_level(ℓ)`` with a small ``E_cross_perm`` supports an operating-level
trade-off in which the hierarchy relocates the loss rather than eliminating it.

No p-value is reported. E1 counts every edge in the graph; there is no sampling
distribution (KB §D.4), so intervals are degenerate by construction.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from graphrag_loss import io as gio  # noqa: E402
from graphrag_loss import loss, report  # noqa: E402

EXPERIMENT = "E1"
NAME = Path(__file__).stem


def _figure(per_level: dict, path: Path) -> Path | None:
    """Stacked bar of weighted cross-edge fraction per level — the L2/L3 figure."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    levels = sorted(per_level)
    cross = [per_level[x].weight_fraction.value * 100 for x in levels]
    intra = [100 - c for c in cross]

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(levels, intra, label="within a community (summarised)", color="#4C78A8")
    ax.bar(levels, cross, bottom=intra, label="cross-community (L2)", color="#E45756")
    ax.set_xlabel("community level")
    ax.set_ylabel("share of total edge weight (%)")
    ax.set_title("Weighted cross-edge fraction by level")
    ax.set_xticks(levels)
    ax.legend(loc="lower right", fontsize=8)
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
    parser.add_argument(
        "--operating-level",
        type=int,
        default=None,
        help="level quoted in the headline; defaults to the deepest level present",
    )
    args = parser.parse_args()

    stamp = gio.make_run_stamp(
        args.frozen_dir, experiment=EXPERIMENT, script=NAME, repo_dir=args.repo_dir
    )

    perm, per_level = loss.cross_edge_census(args.frozen_dir)
    operating = args.operating_level if args.operating_level is not None else max(per_level)
    if operating not in per_level:
        print(f"E1 FAILED: level {operating} not present; levels are {sorted(per_level)}")
        return 2

    rows = [
        {
            "scope": stat.scope,
            "level": None if stat is perm else level,
            "count": int(stat.count.value),
            "n_edges_total": stat.count.n,
            "fraction_of_E": stat.fraction_of_E.value,
            "weight_fraction": stat.weight_fraction.value,
            "method": stat.count.method,
        }
        for level, stat in [(None, perm), *sorted(per_level.items())]
    ]
    results = pd.DataFrame(rows)
    gio.write_result_csv(results, args.results_dir / f"{NAME}.csv", stamp)

    # Downstream experiments consume these two artifacts.
    gio.write_cache(
        pd.DataFrame({"relationship_id": sorted(perm.edge_ids)}),
        args.cache_dir / "E_cross_perm.parquet",
        stamp,
    )
    gio.write_cache(
        pd.DataFrame(
            [
                {"level": level, "relationship_id": rid}
                for level, stat in sorted(per_level.items())
                for rid in sorted(stat.edge_ids)
            ]
        ),
        args.cache_dir / "E_cross_level.parquet",
        stamp,
    )

    fig_path = _figure(per_level, args.figs_dir / f"{NAME}_weight_by_level.png")

    numbers = [
        report.estimates_table(
            {
                "E_cross_perm — count": perm.count,
                "E_cross_perm — fraction of |E|": perm.fraction_of_E,
                "E_cross_perm — weighted fraction": perm.weight_fraction,
            }
        ),
        "",
        "### Per level",
        "",
        results.to_markdown(index=False),
        "",
        f"Operating level for the headline: **{operating}**.",
    ]
    if fig_path:
        numbers += ["", f"![weighted cross-edge fraction by level]({fig_path.as_posix()})"]

    aux = perm.weight_fraction.value * 100
    op_w = per_level[operating].weight_fraction.value * 100
    strength = (
        "strong (>25% weighted at the operating level)"
        if op_w > 25
        else "weak (>8% weighted)" if op_w > 8 else "below the weak marker (<8% weighted)"
    )

    report.write_report(
        args.reports_dir / f"{NAME}.md",
        title="E1 — Cross-edge census",
        experiment=EXPERIMENT,
        stamp=stamp,
        setup=f"Frozen index at `{args.frozen_dir}` (manifest `{stamp.manifest_hash[:12]}`).",
        method=(
            "`E_cross = set(relationships.id) − ⋃ communities.relationship_ids`, "
            "evaluated per level and across all levels (KB §A.1, §A.2). "
            "`communities.relationship_ids` holds wholly-internal edges only, which "
            "E0.5 verified empirically before this experiment ran. Zero LLM calls."
        ),
        numbers="\n".join(numbers),
        gate=None,
        caveats=(
            f"No p-value and no confidence interval: this is a census of all "
            f"{perm.count.n} edges, not a sample (KB §D.4). Against the auxiliary "
            f"markers in KB §C, the operating-level weighted fraction is {strength}. "
            "Weight-adjusted fractions are reported alongside raw counts because a "
            "cross-edge census dominated by weight-1 edges would overstate the loss."
        ),
        next_steps="E3 (`03_multitopic.py`) and E4 (`04_truncation_replay.py`), the latter only if E4-pre passed.",
    )

    print(
        report.headline(
            f"E_cross_perm = {aux:.1f}% weighted "
            f"({int(perm.count.value)}/{perm.count.n} edges), "
            f"E_cross_level({operating}) = {op_w:.1f}% weighted"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

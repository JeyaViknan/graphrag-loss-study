#!/usr/bin/env python
"""E4 — truncation replay. Conditional on E4-pre.

Replays the shipped prioritisation and truncation offline at several
``max_input_length`` values and records what would be dropped. Observed in the
installed graphrag 3.1.1:

* sort key — ``edges.sort(key=lambda x: (-combined_degree, id))`` in
  ``summarize_communities/graph_context/sort_context.py``
* admission — elements are appended until ``num_tokens(context) >
  max_context_tokens``
* tokenizer — ``o200k_base`` (``graphrag/config/defaults.py``)
* config default — ``max_input_length = 8000``

**This script refuses to run until E4-pre is signed off.** ``CONTEXT.md`` §6 is
explicit that if the shipped code diverges materially from Edge et al. §3.1.5,
L3 is dropped from the week entirely — a wrong truncation number is worse than
none. E4-pre is a manual source read producing
``reports/summarization_semantics.md``; pass ``--e4-pre-report`` pointing at it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from graphrag_loss import io as gio  # noqa: E402
from graphrag_loss import loss, report  # noqa: E402

EXPERIMENT = "E4"
NAME = Path(__file__).stem
DEFAULT_BUDGETS = (4000, 8000, 16000)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--repo-dir", type=Path, default=Path("."))
    parser.add_argument(
        "--e4-pre-report",
        type=Path,
        default=Path("reports/summarization_semantics.md"),
        help="E4-pre writeup; E4 refuses to run without it (CONTEXT §6)",
    )
    parser.add_argument("--budgets", type=int, nargs="+", default=list(DEFAULT_BUDGETS))
    parser.add_argument("--tokenizer", default="o200k_base")
    args = parser.parse_args()

    if not args.e4_pre_report.exists():
        print(
            f"E4 BLOCKED — {args.e4_pre_report} not found. E4 is conditional on E4-pre "
            f"(CONTEXT §6): read graphrag/index/operations/summarize_communities/ and "
            f"record the sort key, tokenizer, default max_input_length, and whether "
            f"higher-level substitution matches Edge et al. §3.1.5. If it diverges "
            f"materially, drop L3 from the study and note the drop in GATES.md."
        )
        return 2

    stamp = gio.make_run_stamp(
        args.frozen_dir, experiment=EXPERIMENT, script=NAME, repo_dir=args.repo_dir
    )

    per_budget: list[pd.DataFrame] = []
    dropped_frames: list[pd.DataFrame] = []
    for budget in args.budgets:
        cfg = loss.TruncationConfig(max_input_length=budget, tokenizer_name=args.tokenizer)
        per_budget.append(loss.replay_truncation(args.frozen_dir, cfg))
        dropped_frames.append(loss.dropped_elements(args.frozen_dir, cfg))

    replay = pd.concat(per_budget, ignore_index=True)
    dropped = pd.concat(dropped_frames, ignore_index=True)
    gio.write_cache(dropped, args.cache_dir / "L3_dropped.parquet", stamp)

    leaf_level = int(replay["level"].min())
    rows = []
    for budget in args.budgets:
        at_budget = replay[replay["max_input_length"] == budget]
        leaves = at_budget[at_budget["level"] == leaf_level]
        drop_at_budget = dropped[dropped["max_input_length"] == budget]
        retention = loss.bottom_quartile_retention(drop_at_budget)
        rows.append(
            {
                "max_input_length": budget,
                "n_communities": len(at_budget),
                "n_leaf_communities": len(leaves),
                "n_leaf_overflowing": int(leaves["overflowed"].sum()),
                "leaf_overflow_rate": float(leaves["overflowed"].mean()) if len(leaves) else float("nan"),
                "n_elements": int(at_budget["n_elements"].sum()),
                "n_admitted": int(at_budget["n_admitted"].sum()),
                "n_dropped": int(at_budget["n_dropped"].sum()),
                "bottom_quartile_retention": retention.value,
                "bottom_quartile_retention_ci_low": retention.ci_low,
                "bottom_quartile_retention_ci_high": retention.ci_high,
            }
        )
    results = pd.DataFrame(rows)
    gio.write_result_csv(results, args.results_dir / f"{NAME}.csv", stamp)

    at_8k = results[results["max_input_length"] == 8000]
    overflow_8k = float(at_8k["leaf_overflow_rate"].iloc[0]) if len(at_8k) else float("nan")
    persists_16k = bool(
        len(results[results["max_input_length"] == 16000])
        and float(results[results["max_input_length"] == 16000]["leaf_overflow_rate"].iloc[0]) > 0.20
    )

    report.write_report(
        args.reports_dir / f"{NAME}.md",
        title="E4 — Truncation replay",
        experiment=EXPERIMENT,
        stamp=stamp,
        setup=(
            f"Frozen index `{args.frozen_dir}` (manifest `{stamp.manifest_hash[:12]}`). "
            f"Budgets {args.budgets}, tokenizer `{args.tokenizer}`. "
            f"E4-pre signed off at `{args.e4_pre_report}`. Leaf level = {leaf_level}."
        ),
        method=(
            "Offline replay of the shipped prioritisation: elements sorted by "
            "`(-combined_degree, id)` and admitted until the running token count would "
            "exceed the budget. Element rendering approximates the shipped context "
            "string, so absolute token counts are indicative; the admitted/dropped "
            "*ordering* is exact because it depends only on the sort key."
        ),
        numbers="\n".join([results.to_markdown(index=False), "",
                           f"Leaf overflow at 8k: **{100 * overflow_8k:.1f}%** "
                           f"(KB §C weak marker >20%; strong if it persists at 16k — "
                           f"{'persists' if persists_16k else 'does not persist'})."]),
        gate=None,
        caveats=(
            "L3 is measured only where the shipped code was verified by E4-pre. The "
            "replay reconstructs the context string rather than reading it from the "
            "pipeline, so token totals carry reconstruction error; conclusions are drawn "
            "from overflow *rates* and from which elements are dropped, not from exact "
            "token counts. Higher levels substitute sub-community summaries — that is "
            "compression, not deletion, and is not counted as L3."
        ),
        next_steps="E5 — `scripts/05_recoverability.py` [G1].",
    )

    print(
        f"E4: leaf overflow at 8k = {100 * overflow_8k:.1f}%, "
        f"total dropped elements = {int(results['n_dropped'].sum())} across budgets {args.budgets}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

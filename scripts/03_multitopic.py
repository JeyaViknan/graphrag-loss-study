#!/usr/bin/env python
"""E3 — multi-topic entity rate, provenance-based.

An entity is multi-topic when the text units it was extracted from disagree:
pairwise cosine similarity variance above τ *and* at least two clusters
(KB §H.2). Neighbour community assignment is deliberately not consulted —
defining the loss in terms of the partition whose damage is being measured is
circular, and ``CONTEXT.md`` §9 rules it out.

The degree confound is the live risk here (KB §D.5). Highly-connected entities
appear in more text units and so have more opportunity to look multi-topic. The
script therefore reports the rate per degree quartile and the partial
correlation controlling for degree, and marks the result **unusable** if that
partial correlation exceeds 0.85 — at which point the metric has rediscovered
degree and any reviewer will say so.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from graphrag_loss import io as gio  # noqa: E402
from graphrag_loss import loss, report, stats  # noqa: E402

EXPERIMENT = "E3"
NAME = Path(__file__).stem
DEGREE_COLLAPSE_THRESHOLD = 0.85


def _embedder(model_name: str, device: str):
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name, device=device)

    def embed(texts: list[str]) -> np.ndarray:
        return np.asarray(model.encode(texts, show_progress_bar=False, convert_to_numpy=True))

    return embed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--repo-dir", type=Path, default=Path("."))
    parser.add_argument("--embedding-model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--tau-variance", type=float, default=0.02)
    parser.add_argument("--min-clusters", type=int, default=2)
    parser.add_argument("--distance-threshold", type=float, default=0.5)
    args = parser.parse_args()

    stamp = gio.make_run_stamp(
        args.frozen_dir, experiment=EXPERIMENT, script=NAME, repo_dir=args.repo_dir
    )

    cfg = loss.MultiTopicConfig(
        tau_variance=args.tau_variance,
        min_clusters=args.min_clusters,
        distance_threshold=args.distance_threshold,
        embedding_model=args.embedding_model,
    )
    labels = loss.multitopic_labels(args.frozen_dir, cfg, embed_fn=_embedder(args.embedding_model, args.device))
    gio.write_cache(labels, args.cache_dir / "L1_multitopic.parquet", stamp)

    overall = loss.multitopic_rate(labels)
    by_quartile = loss.multitopic_rate(labels, by_degree_quartile=True)

    evaluable = labels[labels["n_text_units"] >= cfg.min_text_units]
    partial = stats.partial_correlation(
        evaluable["is_multitopic"].astype(float).to_numpy(),
        evaluable["sim_variance"].fillna(0.0).to_numpy(),
        evaluable["degree"].astype(float).to_numpy(),
    )
    degree_corr = stats.partial_correlation(
        labels["is_multitopic"].astype(float).to_numpy(),
        labels["degree"].astype(float).to_numpy(),
        np.ones(len(labels)),
    )
    unusable = bool(abs(degree_corr.value) > DEGREE_COLLAPSE_THRESHOLD)

    results = pd.DataFrame(
        [
            {"quantity": "multitopic_rate_overall", "value": overall.value,
             "ci_low": overall.ci_low, "ci_high": overall.ci_high, "n": overall.n, "method": overall.method},
            *[
                {"quantity": f"multitopic_rate_degree_{q}", "value": e.value,
                 "ci_low": e.ci_low, "ci_high": e.ci_high, "n": e.n, "method": e.method}
                for q, e in by_quartile.items()
            ],
            {"quantity": "corr_multitopic_vs_degree", "value": degree_corr.value,
             "ci_low": degree_corr.ci_low, "ci_high": degree_corr.ci_high,
             "n": degree_corr.n, "method": degree_corr.method},
            {"quantity": "partial_corr_multitopic_vs_variance_controlling_degree", "value": partial.value,
             "ci_low": partial.ci_low, "ci_high": partial.ci_high, "n": partial.n, "method": partial.method},
        ]
    )
    gio.write_result_csv(results, args.results_dir / f"{NAME}.csv", stamp)

    numbers = [
        report.estimates_table({"Multi-topic rate (overall)": overall}, pct=True),
        "",
        "### By degree quartile",
        "",
        report.estimates_table({f"degree {q}": e for q, e in by_quartile.items()}, pct=True),
        "",
        "### Degree confound (KB §D.5)",
        "",
        f"- Correlation of multi-topic label with degree: {report.format_estimate(degree_corr)}",
        f"- Partial correlation of label with similarity variance, controlling degree: "
        f"{report.format_estimate(partial)}",
        "",
        f"- Entities with < {cfg.min_text_units} text units (not evaluable): "
        f"{int((labels['n_text_units'] < cfg.min_text_units).sum())} of {len(labels)}",
    ]
    if unusable:
        numbers += [
            "",
            f"> ⚠ **UNUSABLE FOR THE PAPER.** The multi-topic label correlates with degree at "
            f"{degree_corr.value:.3f}, above the {DEGREE_COLLAPSE_THRESHOLD} collapse threshold. "
            f"The metric has rediscovered degree and cannot support an independent L1 claim.",
        ]

    report.write_report(
        args.reports_dir / f"{NAME}.md",
        title="E3 — Multi-topic entities (provenance-based)",
        experiment=EXPERIMENT,
        stamp=stamp,
        setup=(
            f"Frozen index `{args.frozen_dir}` (manifest `{stamp.manifest_hash[:12]}`). "
            f"Embeddings: `{args.embedding_model}` on {args.device}, local and independent "
            f"of the pipeline LLM. τ={cfg.tau_variance}, min_clusters={cfg.min_clusters}, "
            f"agglomerative distance threshold {cfg.distance_threshold}."
        ),
        method=(
            "For each entity, embed the text units named in its `text_unit_ids`, take the "
            "pairwise cosine similarity distribution, and label multi-topic when the "
            "variance exceeds τ and the units span ≥ 2 clusters (KB §H.2). Neighbour "
            "community assignment is not used — that would be circular."
        ),
        numbers="\n".join(numbers),
        gate=None,
        caveats=(
            "L1 is a *soft* loss. Per CONTEXT §2 it does not satisfy "
            "`supp(R(q,I)) ∩ L = ∅`: global search maps over every summary, so a "
            "misassigned entity is still read, merely in the wrong framing. L1 is "
            "therefore excluded from the hard loss set that E6 intersects and E9 injects."
            + (" This result is marked unusable; see above." if unusable else "")
        ),
        next_steps="E5 — `scripts/05_recoverability.py` [G1].",
    )

    flag = " [UNUSABLE — multi-topic ≈ degree]" if unusable else ""
    print(
        f"E3: multi-topic rate = {100 * overall.value:.1f}% "
        f"[{100 * overall.ci_low:.1f}, {100 * overall.ci_high:.1f}] (n={overall.n}), "
        f"corr with degree = {degree_corr.value:.3f}{flag}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

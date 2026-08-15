#!/usr/bin/env python
"""E0.5 — schema verification. This is GATE 0; nothing proceeds until it passes.

Two classes of check, deliberately treated differently:

**Hard aborts (exit 2) — integrity invariants.** Every relationship listed in a
community's ``relationship_ids`` must have both endpoints inside that
community's ``entity_ids``, and every entity must belong to exactly one
community per level. E1's entire set-difference formulation (KB §A.1) rests on
the first; KB §I asserts the second. If either fails the index is not what the
study assumes and no downstream number means anything.

**Reported divergences (exit 0) — version drift.** ``CONTEXT.md``'s E0.5 spec
asks for an abort when ``text_units`` lacks the plural-s ``relationships_ids``
spelling. graphrag 3.1.1 emits the singular spelling on a perfectly valid index,
so that abort would fire on every current build — the tripwire now detects the
*current* schema as stale. Divergences are therefore logged loudly here and in
``HANDOVER.md`` rather than aborting, and the KB constants are left untouched.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from graphrag_loss import io as gio  # noqa: E402
from graphrag_loss import loss, report, schema as S  # noqa: E402

EXPERIMENT = "E0.5"
NAME = Path(__file__).stem


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-dir", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--repo-dir", type=Path, default=Path("."))
    args = parser.parse_args()

    stamp = gio.make_run_stamp(
        args.frozen_dir, experiment=EXPERIMENT, script=NAME, repo_dir=args.repo_dir
    )

    index = gio.load_index(args.frozen_dir, validate=True)
    levels = index.levels()

    # --- divergences (reported, never fatal) ---------------------------------
    divergences = [S.diff_schema(gio.load_frame(args.frozen_dir, f), f) for f in S.ALL_FILES]
    tu_spelling = index.text_unit_relationship_column()
    kb_expected = S.relationship_ids_column(S.TEXT_UNITS_FILE)
    spelling_diverges = tu_spelling != kb_expected

    # --- integrity checks (hard aborts) --------------------------------------
    rows: list[dict[str, object]] = []
    edge_violations: list[tuple[object, str, str, str]] = []
    membership_violations: dict[int, list[str]] = {}

    for level in levels:
        at_level = index.communities[index.communities[S.Communities.LEVEL] == level]
        checked = sum(len(gio.as_list(r)) for r in at_level[S.Communities.RELATIONSHIP_IDS])
        v_edges = loss.verify_intra_community_edges(
            index.communities, index.relationships, index.entities, level=level
        )
        v_members = loss.assert_single_membership(index.communities, level)
        edge_violations.extend(v_edges)
        membership_violations[level] = v_members
        rows.append(
            {
                "level": level,
                "n_communities": len(at_level),
                "n_relationships_checked": checked,
                "n_edge_violations": len(v_edges),
                "n_multi_membership_entities": len(v_members),
            }
        )

    results = pd.DataFrame(rows)
    gio.write_result_csv(results, args.results_dir / f"{NAME}.csv", stamp)

    failed = bool(edge_violations) or any(membership_violations.values())

    numbers = [
        f"- Levels present: `{levels}`",
        f"- Total communities: {len(index.communities)}",
        f"- Total relationships: {len(index.relationships)}",
        f"- Total entities: {len(index.entities)}",
        "",
        results.to_markdown(index=False),
        "",
        "### Schema divergences observed",
        "",
    ]
    for d in divergences:
        numbers.append(f"- {d.describe()}")
    numbers.append("")
    if spelling_diverges:
        numbers.append(
            f"**⚠ Relationship-ids spelling divergence.** `text_units` uses "
            f"`{tu_spelling}`; KB §A.3 and CONTEXT §4 document `{kb_expected}`. "
            f"Reported, not aborted, and the KB is left unmodified — see HANDOVER.md."
        )
    else:
        numbers.append(f"`text_units` uses `{tu_spelling}`, matching KB §A.3.")

    if failed:
        numbers.append("")
        numbers.append("### ⛔ Integrity violations")
        for community, rid, reason, detail in edge_violations[:50]:
            numbers.append(f"- community `{community}` relationship `{rid}`: {reason} {detail}")
        for level, entities in membership_violations.items():
            if entities:
                numbers.append(f"- level {level}: entities in >1 community: {entities[:20]}")

    gate = report.GateDecision(
        gate="0",
        metric="index integrity (wholly-internal edges, single membership)",
        value=float(len(edge_violations) + sum(len(v) for v in membership_violations.values())),
        threshold=0.0,
        fired=failed,
        rule="any integrity violation halts the study",
    )

    report.write_report(
        args.reports_dir / f"{NAME}.md",
        title="E0.5 — Schema verification",
        experiment=EXPERIMENT,
        stamp=stamp,
        setup=(
            f"Frozen index at `{args.frozen_dir}` (manifest `{stamp.manifest_hash[:12]}`), "
            f"graphrag {stamp.graphrag_version}."
        ),
        method=(
            "For every community at every level, each id in `relationship_ids` is "
            "resolved and both endpoints checked against that community's `entity_ids`. "
            "Endpoints are entity *names* and `entity_ids` are entity *ids*, so the "
            "comparison goes through the `entities` name-to-id mapping. Separately, "
            "every entity is checked to belong to exactly one community per level "
            "(KB §I). Column-name divergences are recorded but are not fatal."
        ),
        numbers="\n".join(numbers),
        gate=gate,
        caveats=(
            "The plural-s tripwire specified in CONTEXT §4 is intentionally not an "
            "abort here; see the divergence note above and HANDOVER.md."
        ),
        next_steps="E1 — `scripts/02_cross_edges.py` (headline number, run first)."
        if not failed
        else "Stop. Fix the index or the assumption before any experiment runs.",
    )

    if failed:
        print(f"GATE 0 FAILED — {len(edge_violations)} edge violations, "
              f"{sum(len(v) for v in membership_violations.values())} membership violations")
        return 2

    spelling_note = " [SPELLING DIVERGENCE: %s]" % tu_spelling if spelling_diverges else ""
    print(
        f"GATE 0 passed — {len(index.communities)} communities across levels {levels}, "
        f"{results['n_relationships_checked'].sum()} relationships checked, 0 violations{spelling_note}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

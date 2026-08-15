"""Three-way failure classifier for E8.

``KNOWLEDGE_BASE.md`` §H.4 defines the categories for a wrong answer to
question ``q`` with gold evidence ``Y(q)`` and retrieved context ``C(q)``:

* **(i) Index-absent** — some ``y ∈ Y(q)`` is in no community summary reachable
  from ``C(q)`` at the operating level.
* **(ii) Not-selected** — every ``y`` is in some summary, but not in the
  summaries assembled into ``C(q)``.
* **(iii) Not-used** — ``Y(q)`` is represented in ``C(q)``, but the answer does
  not reflect it.

A failure may satisfy more than one; the **earliest stage in the pipeline
wins**. That ordering is not arbitrary — a fact that never entered the index
cannot also be meaningfully described as "not selected", and counting it twice
would let the same failure inflate two categories.

G3 fires when category (i) falls below 15% of failures. ``KNOWLEDGE_BASE.md``
§D.7 requires two annotators on 50 failures with κ ≥ 0.7 before these automated
labels are trusted.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pandas as pd

from . import io, schema as S
from .stats import Estimate, bootstrap_proportion, cohens_kappa

__all__ = [
    "FailureCategory",
    "AttributionInput",
    "KAPPA_FLOOR",
    "summary_elements",
    "reachable_elements",
    "classify_failure",
    "classify_all",
    "write_annotation_sheet",
    "read_annotations",
    "annotator_agreement",
    "category_shares",
]

KAPPA_FLOOR = 0.70


class FailureCategory(str, Enum):
    INDEX_ABSENT = "i"
    NOT_SELECTED = "ii"
    NOT_USED = "iii"

    @property
    def label(self) -> str:
        return {
            FailureCategory.INDEX_ABSENT: "index-absent",
            FailureCategory.NOT_SELECTED: "not-selected",
            FailureCategory.NOT_USED: "not-used",
        }[self]


@dataclass(frozen=True)
class AttributionInput:
    """Everything needed to categorise one failed question."""

    question_id: str
    gold_element_ids: frozenset[str]
    context_community_ids: frozenset[str]
    context_element_ids: frozenset[str]


def summary_elements(frozen_dir: Path, *, level: int) -> frozenset[str]:
    """Every element represented in *any* community summary at ``level``.

    An element outside this set never reached a summary, so no retrieval policy
    operating over summaries could surface it — that is category (i).
    """
    communities = io.load_communities(frozen_dir)
    at_level = communities[communities[S.Communities.LEVEL] == level]
    out: set[str] = set()
    for _, row in at_level.iterrows():
        out.update(str(x) for x in io.as_list(row[S.Communities.ENTITY_IDS]))
        out.update(str(x) for x in io.as_list(row[S.Communities.RELATIONSHIP_IDS]))
    return frozenset(out)


def reachable_elements(
    frozen_dir: Path, community_ids: Sequence[object], *, level: int
) -> frozenset[str]:
    """Elements carried by the specific communities assembled into a context."""
    communities = io.load_communities(frozen_dir)
    wanted = {str(c) for c in community_ids}
    at_level = communities[communities[S.Communities.LEVEL] == level]
    rows = at_level[at_level[S.Communities.COMMUNITY].astype(str).isin(wanted)]
    out: set[str] = set()
    for _, row in rows.iterrows():
        out.update(str(x) for x in io.as_list(row[S.Communities.ENTITY_IDS]))
        out.update(str(x) for x in io.as_list(row[S.Communities.RELATIONSHIP_IDS]))
    return frozenset(out)


def classify_failure(
    inp: AttributionInput, *, all_summary_elements: frozenset[str]
) -> FailureCategory:
    """Assign the earliest applicable category (KB §H.4)."""
    gold = inp.gold_element_ids
    if not gold:
        # No resolvable gold evidence: cannot be blamed on the index.
        return FailureCategory.NOT_USED
    if gold - all_summary_elements:
        return FailureCategory.INDEX_ABSENT
    if gold - inp.context_element_ids:
        return FailureCategory.NOT_SELECTED
    return FailureCategory.NOT_USED


def classify_all(
    inputs: Sequence[AttributionInput], *, all_summary_elements: frozenset[str]
) -> pd.DataFrame:
    """Categorise a batch of failures, keeping the evidence for each decision."""
    rows: list[dict[str, object]] = []
    for inp in inputs:
        category = classify_failure(inp, all_summary_elements=all_summary_elements)
        gold = inp.gold_element_ids
        rows.append(
            {
                "question_id": inp.question_id,
                "category": category.value,
                "category_label": category.label,
                "gold_size": len(gold),
                "n_absent_from_all_summaries": len(gold - all_summary_elements),
                "n_absent_from_context": len(gold - inp.context_element_ids),
                "n_context_communities": len(inp.context_community_ids),
            }
        )
    return pd.DataFrame(rows)


def write_annotation_sheet(
    failures: pd.DataFrame, path: Path, *, n: int = 50, seed: int = 0
) -> Path:
    """Emit a blank sheet for two independent annotators.

    The automated category is deliberately excluded so annotators are not
    anchored by the classifier whose reliability they are establishing.
    """
    sample = failures.sample(n=min(n, len(failures)), random_state=seed).reset_index(drop=True)
    keep = [c for c in ("question_id", "question", "answer", "gold_answer", "context_preview") if c in sample.columns]
    sheet = sample[keep].copy() if keep else sample[["question_id"]].copy()
    sheet["label_a"] = ""
    sheet["label_b"] = ""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.to_csv(path, index=False)
    return path


def read_annotations(path: Path) -> pd.DataFrame:
    """Read a completed annotation sheet, validating the category vocabulary."""
    df = pd.read_csv(path)
    for col in ("label_a", "label_b"):
        if col not in df.columns:
            msg = f"{path}: annotation sheet missing column {col!r}"
            raise ValueError(msg)
    labelled = df.dropna(subset=["label_a", "label_b"])
    valid = {c.value for c in FailureCategory}
    seen = {str(x).strip().lower() for x in labelled["label_a"]} | {
        str(x).strip().lower() for x in labelled["label_b"]
    }
    unknown = seen - valid
    if unknown:
        msg = f"{path}: unrecognised categories {sorted(unknown)}; expected {sorted(valid)}"
        raise ValueError(msg)
    return labelled


def annotator_agreement(a: Sequence[str], b: Sequence[str]) -> Estimate:
    """Cohen's κ between two annotators over the three categories."""
    categories = [c.value for c in FailureCategory]
    return cohens_kappa(
        [str(x).strip().lower() for x in a],
        [str(x).strip().lower() for x in b],
        categories=categories,
    )


def category_shares(labels: Sequence[str] | pd.Series) -> dict[str, Estimate]:
    """Bootstrap CI on each category's share of failures."""
    values = [str(x).strip().lower() for x in labels]
    return {
        c.value: bootstrap_proportion([v == c.value for v in values])
        for c in FailureCategory
    }

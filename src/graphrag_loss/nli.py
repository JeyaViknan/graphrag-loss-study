"""Calibrated NLI wrapper for E5 recoverability.

E5 asks whether a cross-community edge's content is *recoverable* from the
community summaries that survive indexing: the passages describing ``u`` and
``v`` form the premise, the relationship description is the hypothesis, and the
question is whether the premise entails it.

``KNOWLEDGE_BASE.md`` §D.6 makes calibration a precondition, not a nicety: NLI
output on out-of-domain text is worthless without it. Two humans label 100
items, Cohen's κ between them must reach 0.7, and only then does the 300-edge
run proceed. :func:`calibrate` computes that, and the classifier deliberately
offers no way to skip it — the scripts check :attr:`CalibrationResult.passed`.

Per KB §G the NLI model must be independent of the pipeline LLM, so that E5's
judgment is not the same model grading its own summaries.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pandas as pd

from . import schema as S
from .stats import Estimate, bootstrap_proportion, cohens_kappa

__all__ = [
    "NLILabel",
    "NLIConfig",
    "NLIPrediction",
    "CalibrationResult",
    "NLIClassifier",
    "extract_passages",
    "build_premise",
    "write_calibration_sheet",
    "read_human_labels",
    "calibrate",
    "entailment_rate",
]

KAPPA_FLOOR = 0.70


class NLILabel(str, Enum):
    ENTAILED = "ENTAILED"
    NEUTRAL = "NEUTRAL"
    CONTRADICTED = "CONTRADICTED"


@dataclass(frozen=True)
class NLIConfig:
    model_name: str = "cross-encoder/nli-deberta-v3-base"
    batch_size: int = 16
    device: str = "cpu"
    max_length: int = 512


@dataclass(frozen=True)
class NLIPrediction:
    label: NLILabel
    scores: dict[NLILabel, float]
    premise_chars: int
    hypothesis_chars: int


@dataclass(frozen=True)
class CalibrationResult:
    """Outcome of the human calibration step that gates E5 at scale."""

    kappa_humans: Estimate
    nli_vs_human_a: Estimate
    nli_vs_human_b: Estimate
    n: int

    @property
    def passed(self) -> bool:
        return bool(self.kappa_humans.value >= KAPPA_FLOOR)

    def summary(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return (
            f"calibration {verdict}: kappa(humans)={self.kappa_humans.value:.3f} "
            f"(floor {KAPPA_FLOOR}), n={self.n}, "
            f"NLI-vs-A={self.nli_vs_human_a.value:.3f}, "
            f"NLI-vs-B={self.nli_vs_human_b.value:.3f}"
        )


class NLIClassifier:
    """Cross-encoder NLI, loaded lazily so imports stay cheap.

    Label mapping is read from the model's own ``id2label`` rather than assumed
    positionally: cross-encoder NLI checkpoints do not agree on ordering, and a
    silently transposed mapping would invert E5's headline number.
    """

    def __init__(self, cfg: NLIConfig) -> None:
        self.cfg = cfg
        self._model = None
        self._label_map: dict[int, NLILabel] = {}

    def load(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(self.cfg.model_name, max_length=self.cfg.max_length, device=self.cfg.device)
        raw = getattr(getattr(self._model, "config", None), "id2label", None) or {}
        self._label_map = {int(i): _canonical_label(str(name)) for i, name in raw.items()}
        if not self._label_map:
            # Documented default for the cross-encoder/nli-* family.
            self._label_map = {
                0: NLILabel.CONTRADICTED,
                1: NLILabel.ENTAILED,
                2: NLILabel.NEUTRAL,
            }

    def classify(self, premise: str, hypothesis: str) -> NLIPrediction:
        return self.classify_batch([(premise, hypothesis)])[0]

    def classify_batch(self, pairs: Sequence[tuple[str, str]]) -> list[NLIPrediction]:
        self.load()
        assert self._model is not None
        import numpy as np

        raw = self._model.predict(list(pairs), batch_size=self.cfg.batch_size, apply_softmax=True)
        arr = np.atleast_2d(np.asarray(raw, dtype=float))
        out: list[NLIPrediction] = []
        for (premise, hypothesis), row in zip(pairs, arr, strict=True):
            scores = {self._label_map.get(i, NLILabel.NEUTRAL): float(v) for i, v in enumerate(row)}
            label = max(scores, key=lambda k: scores[k])
            out.append(
                NLIPrediction(
                    label=label,
                    scores=scores,
                    premise_chars=len(premise),
                    hypothesis_chars=len(hypothesis),
                )
            )
        return out


def _canonical_label(name: str) -> NLILabel:
    lowered = name.lower()
    if "entail" in lowered:
        return NLILabel.ENTAILED
    if "contra" in lowered:
        return NLILabel.CONTRADICTED
    return NLILabel.NEUTRAL


def extract_passages(full_content: str, entity_title: str, *, window_chars: int = 400) -> list[str]:
    """Passages of a community report that mention ``entity_title``.

    Falls back to an empty list rather than the whole report: handing the entire
    report to the NLI model as premise would let unrelated content entail the
    hypothesis and inflate recoverability, which is the direction that would
    wrongly fire G1.
    """
    if not full_content or not entity_title:
        return []
    text = str(full_content)
    out: list[str] = []
    for m in re.finditer(re.escape(str(entity_title)), text, flags=re.IGNORECASE):
        start = max(0, m.start() - window_chars // 2)
        end = min(len(text), m.end() + window_chars // 2)
        out.append(text[start:end].strip())
    return out


def build_premise(
    reports: pd.DataFrame,
    community_u: object,
    community_v: object,
    title_u: str,
    title_v: str,
    *,
    window_chars: int = 400,
    max_passages: int = 4,
) -> str:
    """Concatenate the passages describing ``u`` and ``v`` from their reports."""
    parts: list[str] = []
    for community, title in ((community_u, title_u), (community_v, title_v)):
        row = reports[reports[S.CommunityReports.COMMUNITY] == community]
        if row.empty:
            continue
        content = str(row.iloc[0][S.CommunityReports.FULL_CONTENT])
        parts.extend(extract_passages(content, title, window_chars=window_chars)[:max_passages])
    return "\n\n".join(parts)


def write_calibration_sheet(
    items: pd.DataFrame, path: Path, *, n: int = 100, seed: int = 0
) -> Path:
    """Emit a blank labelling sheet for two human annotators.

    Columns ``label_a`` and ``label_b`` are left empty on purpose. Any NLI
    prediction is withheld from the sheet so the annotators are not anchored by
    the model they are calibrating.
    """
    sample = items.sample(n=min(n, len(items)), random_state=seed).reset_index(drop=True)
    sheet = pd.DataFrame(
        {
            "item_id": sample.get("relationship_id", pd.Series(range(len(sample)))),
            "premise": sample["premise"],
            "hypothesis": sample["hypothesis"],
            "label_a": "",
            "label_b": "",
        }
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.to_csv(path, index=False)
    return path


def read_human_labels(path: Path) -> pd.DataFrame:
    """Read a completed calibration sheet, validating the label vocabulary."""
    df = pd.read_csv(path)
    for col in ("label_a", "label_b"):
        if col not in df.columns:
            msg = f"{path}: calibration sheet missing column {col!r}"
            raise ValueError(msg)
    valid = {label.value for label in NLILabel}
    labelled = df.dropna(subset=["label_a", "label_b"])
    bad = set(labelled["label_a"]) | set(labelled["label_b"])
    unknown = {str(x).strip().upper() for x in bad} - valid
    if unknown:
        msg = f"{path}: unrecognised labels {sorted(unknown)}; expected {sorted(valid)}"
        raise ValueError(msg)
    return labelled


def calibrate(
    human_a: Sequence[str], human_b: Sequence[str], nli_preds: Sequence[NLILabel]
) -> CalibrationResult:
    """Compute inter-human κ and NLI–human agreement."""
    a = [str(x).strip().upper() for x in human_a]
    b = [str(x).strip().upper() for x in human_b]
    m = [p.value if isinstance(p, NLILabel) else str(p).strip().upper() for p in nli_preds]
    categories = [label.value for label in NLILabel]
    return CalibrationResult(
        kappa_humans=cohens_kappa(a, b, categories=categories),
        nli_vs_human_a=bootstrap_proportion([x == y for x, y in zip(m, a, strict=True)]),
        nli_vs_human_b=bootstrap_proportion([x == y for x, y in zip(m, b, strict=True)]),
        n=len(a),
    )


def entailment_rate(
    preds: Sequence[NLILabel] | pd.Series, *, strata: Sequence[str] | None = None
) -> Estimate | dict[str, Estimate]:
    """Share classified ENTAILED, overall or per stratum.

    G1 fires above 0.70: the summaries would already carry the cross-edge
    content, making L2 bookkeeping rather than loss.
    """
    labels = [p.value if isinstance(p, NLILabel) else str(p) for p in preds]
    hits = [label == NLILabel.ENTAILED.value for label in labels]
    if strata is None:
        return bootstrap_proportion(hits)
    frame = pd.DataFrame({"hit": hits, "stratum": list(strata)})
    return {
        str(name): bootstrap_proportion(group["hit"].to_numpy(dtype=bool))
        for name, group in frame.groupby("stratum", sort=True)
    }

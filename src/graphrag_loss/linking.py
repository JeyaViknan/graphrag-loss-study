"""Link benchmark gold evidence to GraphRAG index elements (E6).

``KNOWLEDGE_BASE.md`` §H.3 specifies sentence-level linking: find the text unit
containing the gold sentence, then collect ``u.entity_ids ∪ u.relationship_ids``.
That formulation assumes gold sentences are *extracts*.

On GraphRAG-Bench Novel they are not. Measured against their source novels,
0.1% of gold ``evidence`` sentences appear as exact substrings and 5.4% reach
character-n-gram ``partial_ratio`` >= 85 against text-unit-sized windows — they
are abstractive restatements. The dataset also ships ``evidence_triple``, a
``(head, relation, tail)`` form that maps directly onto the entities and
relationships E6 needs to intersect with ``L``.

``LinkStrategy.TRIPLE`` is therefore the frozen E6 default (``GATES.md``
Appendix A), with ``token_set_ratio >= 85`` against ``entities.title``.
``LinkStrategy.SENTENCE_FUZZY`` remains implemented for a later ablation and is
not run in E6.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

from . import io, schema as S
from .stats import Estimate, bootstrap_proportion

__all__ = [
    "LinkStrategy",
    "LinkConfig",
    "GoldLink",
    "normalize_text",
    "load_questions",
    "load_corpus",
    "parse_triple",
    "link_sentence",
    "link_triple",
    "elements_for_text_unit",
    "build_gold_links",
    "unlink_rate",
]

_SCORERS = {
    "token_set_ratio": fuzz.token_set_ratio,
    "partial_ratio": fuzz.partial_ratio,
    "ratio": fuzz.ratio,
    "token_sort_ratio": fuzz.token_sort_ratio,
}


class LinkStrategy(str, Enum):
    SENTENCE_FUZZY = "sentence_fuzzy"
    TRIPLE = "triple"


@dataclass(frozen=True)
class LinkConfig:
    """Frozen in ``GATES.md`` Appendix A before any E6 run.

    Re-tuning ``threshold`` after seeing an unfavourable unlink rate is exactly
    the researcher degree of freedom the gate discipline exists to remove.
    """

    strategy: LinkStrategy = LinkStrategy.TRIPLE
    threshold: float = 85.0
    scorer: str = "token_set_ratio"
    normalize: bool = True
    restrict_to_source_document: bool = True

    def scorer_fn(self):
        try:
            return _SCORERS[self.scorer]
        except KeyError:
            msg = f"unknown scorer {self.scorer!r}; available: {sorted(_SCORERS)}"
            raise ValueError(msg) from None


@dataclass(frozen=True)
class GoldLink:
    """One gold evidence item resolved (or not) to index elements."""

    question_id: str
    evidence_index: int
    linked: bool
    text_unit_id: str | None
    score: float
    entity_ids: frozenset[str]
    relationship_ids: frozenset[str]


_PUNCT = re.compile(r"[^\w\s]")
_SPACE = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    return _SPACE.sub(" ", _PUNCT.sub(" ", str(s).lower())).strip()


def load_questions(path: Path) -> pd.DataFrame:
    """Load GraphRAG-Bench questions as a frame.

    Expected fields: ``id, source, question, answer, question_type, evidence,
    evidence_triple``.
    """
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    df = pd.DataFrame(records)
    required = {"id", "question", "evidence"}
    missing = required - set(df.columns)
    if missing:
        msg = f"{path}: questions file missing fields {sorted(missing)}"
        raise ValueError(msg)
    return df


def load_corpus(path: Path) -> dict[str, str]:
    """Load the corpus as ``{corpus_name: context}``."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    return {r["corpus_name"]: r["context"] for r in records}


_TRIPLE_RE = re.compile(r"^\s*\(?\s*(.+?)\s*,\s*(.+?)\s*,\s*(.+?)\s*\)?\s*\.?\s*$")


def parse_triple(raw: str) -> tuple[str, str, str] | None:
    """Parse ``"(head, relation, tail)."`` into its three parts.

    Returns ``None`` when the string does not have exactly three
    comma-separated parts, so malformed triples count as unlinked rather than
    being silently coerced into a match.
    """
    text = str(raw).strip()
    if text.startswith("(") and text.rstrip(".").endswith(")"):
        text = text.rstrip(".").strip()[1:-1]
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 3 or not all(parts):
        m = _TRIPLE_RE.match(str(raw))
        if not m:
            return None
        parts = [m.group(1).strip(), m.group(2).strip(), m.group(3).strip()]
        if not all(parts):
            return None
    return parts[0], parts[1], parts[2]


def elements_for_text_unit(
    text_units: pd.DataFrame, text_unit_id: str, *, rel_col: str
) -> tuple[frozenset[str], frozenset[str]]:
    """Collect ``entity_ids`` and relationship ids for one text unit.

    ``rel_col`` must come from :func:`schema.detect_relationship_ids_column` —
    the spelling differs between graphrag versions (KB §A.3).
    """
    row = text_units[text_units[S.TextUnits.ID] == text_unit_id]
    if row.empty:
        return frozenset(), frozenset()
    r = row.iloc[0]
    ents = frozenset(str(x) for x in (r[S.TextUnits.ENTITY_IDS] or []))
    rels = frozenset(str(x) for x in (r.get(rel_col) or []))
    return ents, rels


def link_sentence(
    sentence: str,
    text_units: pd.DataFrame,
    cfg: LinkConfig,
    *,
    document_id: str | None = None,
) -> tuple[str | None, float]:
    """Best-matching text unit for a gold sentence, or ``(None, score)``.

    Not used in E6 — retained for ablation (``GATES.md`` Appendix A.1).
    """
    candidates = text_units
    if document_id is not None and S.TextUnits.DOCUMENT_ID in text_units.columns:
        scoped = text_units[text_units[S.TextUnits.DOCUMENT_ID] == document_id]
        if not scoped.empty:
            candidates = scoped
    if candidates.empty:
        return None, 0.0

    needle = normalize_text(sentence) if cfg.normalize else str(sentence)
    haystack = (
        [normalize_text(t) for t in candidates[S.TextUnits.TEXT]]
        if cfg.normalize
        else [str(t) for t in candidates[S.TextUnits.TEXT]]
    )
    match = process.extractOne(needle, haystack, scorer=cfg.scorer_fn())
    if match is None:
        return None, 0.0
    _text, score, idx = match
    if score < cfg.threshold:
        return None, float(score)
    return str(candidates.iloc[idx][S.TextUnits.ID]), float(score)


def link_triple(
    triple: tuple[str, str, str],
    entities: pd.DataFrame,
    relationships: pd.DataFrame,
    cfg: LinkConfig,
    *,
    candidate_entities: pd.DataFrame | None = None,
) -> tuple[frozenset[str], frozenset[str], float]:
    """Resolve a gold triple to entity and relationship ids.

    Both head and tail must clear ``cfg.threshold`` against ``entities.title``
    (``GATES.md`` A.2). A triple resolving only one endpoint counts as unlinked:
    a half-matched triple identifies no relationship, and admitting it would
    inflate the linked set with elements the gold evidence did not name.

    Returns ``(entity_ids, relationship_ids, min_endpoint_score)``.
    """
    head, _relation, tail = triple
    pool = entities if candidate_entities is None else candidate_entities
    if pool.empty:
        return frozenset(), frozenset(), 0.0

    titles = [normalize_text(t) for t in pool[S.Entities.TITLE]] if cfg.normalize else [
        str(t) for t in pool[S.Entities.TITLE]
    ]
    scorer = cfg.scorer_fn()

    resolved: list[str] = []
    scores: list[float] = []
    for surface in (head, tail):
        needle = normalize_text(surface) if cfg.normalize else str(surface)
        match = process.extractOne(needle, titles, scorer=scorer)
        if match is None:
            return frozenset(), frozenset(), 0.0
        _t, score, idx = match
        scores.append(float(score))
        if score < cfg.threshold:
            return frozenset(), frozenset(), float(min(scores))
        resolved.append(str(pool.iloc[idx][S.Entities.ID]))

    entity_ids = frozenset(resolved)
    titles_by_id = entities.set_index(S.Entities.ID)[S.Entities.TITLE].to_dict()
    endpoints = {titles_by_id.get(e, e) for e in resolved} | entity_ids

    src = relationships[S.Relationships.SOURCE].astype(str)
    tgt = relationships[S.Relationships.TARGET].astype(str)
    hit = relationships[
        (src.isin({str(x) for x in endpoints}) & tgt.isin({str(x) for x in endpoints}))
    ]
    relationship_ids = frozenset(str(x) for x in hit[S.Relationships.ID])
    return entity_ids, relationship_ids, float(min(scores))


def build_gold_links(
    frozen_dir: Path, questions: pd.DataFrame, cfg: LinkConfig
) -> pd.DataFrame:
    """Resolve every question's gold evidence to index elements.

    One row per gold evidence item. ``build_gold_links`` does not intersect with
    ``L`` — that is the caller's job in ``06_gold_links.py``, which knows which
    loss components are in scope for the gate.
    """
    entities = io.load_entities(frozen_dir)
    relationships = io.load_relationships(frozen_dir)
    text_units = io.load_text_units(frozen_dir)
    rel_col = S.detect_relationship_ids_column(text_units, S.TEXT_UNITS_FILE)

    rows: list[dict[str, object]] = []
    for _, q in questions.iterrows():
        qid = str(q["id"])
        if cfg.strategy is LinkStrategy.TRIPLE:
            items = list(q.get("evidence_triple") or [])
        else:
            items = list(q.get("evidence") or [])

        for i, item in enumerate(items):
            if cfg.strategy is LinkStrategy.TRIPLE:
                parsed = parse_triple(item)
                if parsed is None:
                    rows.append(_unlinked_row(qid, i, item, 0.0))
                    continue
                ents, rels, score = link_triple(parsed, entities, relationships, cfg)
                linked = bool(ents)
                rows.append(
                    {
                        "question_id": qid,
                        "evidence_index": i,
                        "evidence": str(item),
                        "linked": linked,
                        "text_unit_id": None,
                        "score": score,
                        "entity_ids": sorted(ents),
                        "relationship_ids": sorted(rels),
                    }
                )
            else:
                tu_id, score = link_sentence(str(item), text_units, cfg)
                if tu_id is None:
                    rows.append(_unlinked_row(qid, i, item, score))
                    continue
                ents, rels = elements_for_text_unit(text_units, tu_id, rel_col=rel_col)
                rows.append(
                    {
                        "question_id": qid,
                        "evidence_index": i,
                        "evidence": str(item),
                        "linked": True,
                        "text_unit_id": tu_id,
                        "score": score,
                        "entity_ids": sorted(ents),
                        "relationship_ids": sorted(rels),
                    }
                )
    return pd.DataFrame(rows)


def _unlinked_row(qid: str, i: int, item: object, score: float) -> dict[str, object]:
    return {
        "question_id": qid,
        "evidence_index": i,
        "evidence": str(item),
        "linked": False,
        "text_unit_id": None,
        "score": float(score),
        "entity_ids": [],
        "relationship_ids": [],
    }


def unlink_rate(links: pd.DataFrame) -> Estimate:
    """Share of gold evidence items that resolved to no element.

    G2's precondition: above 15%, E6 is reported inconclusive rather than as a
    gate pass or fail (``GATES.md`` §G2).
    """
    if links.empty:
        return Estimate(float("nan"), float("nan"), float("nan"), 0, "bootstrap-percentile")
    return bootstrap_proportion((~links["linked"]).to_numpy(dtype=bool))

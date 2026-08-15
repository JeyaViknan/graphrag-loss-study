"""L1, L2 and L3 computation against a frozen GraphRAG index.

The hypothesis under test (``CONTEXT.md`` §2) is that index construction
discards information before any query is asked, through three losses:

* **L1 (soft)** — multi-topic entities filed under one community only.
* **L2 (hard)** — relationships whose endpoints fall in different communities,
  which therefore appear in no community summary.
* **L3 (hard, tail)** — elements dropped when a leaf community's summarisation
  context exceeds the token budget.

L2 needs zero LLM calls: ``communities.relationship_ids`` holds wholly-internal
edges only, so the cross-edge set is a set difference (KB §A.1). Two distinct
quantities must both be reported, because the paper's framing depends on which
is large (KB §A.2):

* ``E_cross_perm``   — edges never wholly-within any community at any level.
* ``E_cross_level(ℓ)`` — edges not wholly-within any community at level ℓ.

Public entry points that read the index take ``frozen_dir``; the pure helpers
take already-loaded frames so they can be unit-tested on synthetic fixtures.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import io, schema as S
from .stats import Estimate, census

__all__ = [
    "entity_to_community",
    "assert_single_membership",
    "verify_intra_community_edges",
    "intra_relationship_ids",
    "cross_edges_at_level",
    "cross_edges_permanent",
    "CrossEdgeStat",
    "cross_edge_census",
    "weight_fraction",
    "MultiTopicConfig",
    "entity_text_unit_texts",
    "multitopic_labels",
    "multitopic_rate",
    "TruncationConfig",
    "replay_truncation",
    "dropped_elements",
    "bottom_quartile_retention",
    "LossSet",
    "build_loss_set",
    "intersect",
]


# --------------------------------------------------------------------------
# Shared membership helpers
# --------------------------------------------------------------------------


def entity_to_community(communities: pd.DataFrame, level: int) -> pd.DataFrame:
    """Explode ``communities.entity_ids`` into ``(entity_id, community)`` rows.

    ``entities.parquet`` has no ``community`` column (KB §A.3); this is the only
    way to recover membership.
    """
    at_level = communities[communities[S.Communities.LEVEL] == level]
    exploded = at_level.explode(S.Communities.ENTITY_IDS)
    out = exploded[[S.Communities.ENTITY_IDS, S.Communities.COMMUNITY]].rename(
        columns={S.Communities.ENTITY_IDS: "entity_id"}
    )
    return out.dropna(subset=["entity_id"]).reset_index(drop=True)


def assert_single_membership(communities: pd.DataFrame, level: int) -> list[str]:
    """Return entity ids appearing in more than one community at ``level``.

    On a valid GraphRAG output an entity appears in exactly one community per
    level (KB §I). A non-empty return is an integrity violation and E0.5 aborts.
    """
    e2c = entity_to_community(communities, level)
    counts = e2c.groupby("entity_id")[S.Communities.COMMUNITY].nunique()
    return sorted(str(x) for x in counts[counts > 1].index)


def verify_intra_community_edges(
    communities: pd.DataFrame,
    relationships: pd.DataFrame,
    entities: pd.DataFrame,
    *,
    level: int | None = None,
) -> list[tuple[object, str, str, str]]:
    """Check that every listed relationship is wholly inside its community.

    This is the empirical verification KB §A.1 demands before E1 relies on the
    set-difference formulation, and it is the hard abort in E0.5.

    The two frames speak different domains: ``relationships.source``/``target``
    hold entity *names* (``graphrag/data_model/relationship.py``) while
    ``communities.entity_ids`` holds entity *ids*. ``entities`` supplies the
    name-to-id mapping; comparing without it silently passes everything.

    Returns ``(community, relationship_id, reason, detail)`` violations — empty
    on a healthy index.
    """
    rel_index = relationships.set_index(S.Relationships.ID)
    src = rel_index[S.Relationships.SOURCE].to_dict()
    tgt = rel_index[S.Relationships.TARGET].to_dict()
    id_by_title = {
        str(t): str(i)
        for t, i in zip(entities[S.Entities.TITLE], entities[S.Entities.ID], strict=True)
    }

    rows = communities if level is None else communities[communities[S.Communities.LEVEL] == level]
    violations: list[tuple[object, str, str, str]] = []
    for _, row in rows.iterrows():
        member = {str(e) for e in (row[S.Communities.ENTITY_IDS] or [])}
        for rid in row[S.Communities.RELATIONSHIP_IDS] or []:
            if rid not in src:
                violations.append((row[S.Communities.COMMUNITY], str(rid), "unknown-relationship-id", ""))
                continue
            for endpoint, role in ((src[rid], "source"), (tgt[rid], "target")):
                entity_id = id_by_title.get(str(endpoint))
                if entity_id is None:
                    violations.append(
                        (row[S.Communities.COMMUNITY], str(rid), f"{role}-not-in-entities", str(endpoint))
                    )
                elif entity_id not in member:
                    violations.append(
                        (
                            row[S.Communities.COMMUNITY],
                            str(rid),
                            f"{role}-outside-entity_ids",
                            str(endpoint),
                        )
                    )
    return violations


# --------------------------------------------------------------------------
# L2 — cross-community edges
# --------------------------------------------------------------------------


def intra_relationship_ids(communities: pd.DataFrame, level: int | None = None) -> set[str]:
    """Union of ``communities.relationship_ids``; ``level=None`` spans all levels."""
    rows = communities if level is None else communities[communities[S.Communities.LEVEL] == level]
    out: set[str] = set()
    for rids in rows[S.Communities.RELATIONSHIP_IDS]:
        if rids is not None:
            out.update(rids)
    return out


def cross_edges_at_level(
    communities: pd.DataFrame, relationships: pd.DataFrame, level: int
) -> set[str]:
    """``E_cross_level(ℓ)`` — edges not wholly-within any community at ``level``."""
    return set(relationships[S.Relationships.ID]) - intra_relationship_ids(communities, level)


def cross_edges_permanent(communities: pd.DataFrame, relationships: pd.DataFrame) -> set[str]:
    """``E_cross_perm`` — edges never wholly-within any community at any level.

    A leaf-level cross-edge may still sit inside a shared parent, so this is
    strictly a subset of every ``E_cross_level(ℓ)`` (KB §A.2).
    """
    return set(relationships[S.Relationships.ID]) - intra_relationship_ids(communities, None)


def weight_fraction(relationships: pd.DataFrame, edge_ids: Iterable[str]) -> Estimate:
    """Share of total edge weight carried by ``edge_ids``.

    A census, not a sample: every edge in the graph is counted (KB §D.4).
    """
    ids = set(edge_ids)
    w = relationships[S.Relationships.WEIGHT].astype(float)
    total = float(w.sum())
    if total == 0:
        return census(float("nan"), len(relationships))
    selected = float(w[relationships[S.Relationships.ID].isin(ids)].sum())
    return census(selected / total, len(relationships))


@dataclass(frozen=True)
class CrossEdgeStat:
    """One scope's cross-edge census: raw count, share of |E|, weighted share."""

    scope: str
    edge_ids: frozenset[str]
    count: Estimate
    fraction_of_E: Estimate
    weight_fraction: Estimate

    def headline(self) -> str:
        return (
            f"{self.scope}: {int(self.count.value)} edges "
            f"({100 * self.fraction_of_E.value:.1f}% of |E|, "
            f"{100 * self.weight_fraction.value:.1f}% weighted)"
        )


def _stat(scope: str, edge_ids: set[str], relationships: pd.DataFrame) -> CrossEdgeStat:
    n_edges = len(relationships)
    return CrossEdgeStat(
        scope=scope,
        edge_ids=frozenset(edge_ids),
        count=census(len(edge_ids), n_edges),
        fraction_of_E=census(len(edge_ids) / n_edges if n_edges else float("nan"), n_edges),
        weight_fraction=weight_fraction(relationships, edge_ids),
    )


def cross_edge_census(frozen_dir: Path) -> tuple[CrossEdgeStat, dict[int, CrossEdgeStat]]:
    """E1 entry point. Returns ``(perm, {level: stat})``."""
    communities = io.load_communities(frozen_dir)
    relationships = io.load_relationships(frozen_dir)
    perm = _stat("E_cross_perm", cross_edges_permanent(communities, relationships), relationships)
    per_level = {
        int(lvl): _stat(
            f"E_cross_level({int(lvl)})",
            cross_edges_at_level(communities, relationships, int(lvl)),
            relationships,
        )
        for lvl in sorted(communities[S.Communities.LEVEL].unique())
    }
    return perm, per_level


# --------------------------------------------------------------------------
# L1 — multi-topic entities, provenance-based
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MultiTopicConfig:
    """Thresholds for the provenance-based multi-topic label (KB §H.2).

    Deliberately does *not* consult neighbour community assignment: doing so
    would define the loss in terms of the partition whose damage is being
    measured, which ``CONTEXT.md`` §9 rules out as circular.
    """

    tau_variance: float = 0.02
    min_clusters: int = 2
    min_text_units: int = 2
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    cluster_method: str = "agglomerative"
    distance_threshold: float = 0.5


def entity_text_unit_texts(
    entities: pd.DataFrame, text_units: pd.DataFrame, entity_id: str
) -> list[str]:
    """Texts of the units an entity was extracted from."""
    row = entities[entities[S.Entities.ID] == entity_id]
    if row.empty:
        return []
    ids = row.iloc[0][S.Entities.TEXT_UNIT_IDS] or []
    lookup = text_units.set_index(S.TextUnits.ID)[S.TextUnits.TEXT]
    return [str(lookup[i]) for i in ids if i in lookup.index]


def _pairwise_cosine(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = vectors / norms
    sim = unit @ unit.T
    iu = np.triu_indices(len(vectors), k=1)
    return sim[iu]


def _cluster_count(vectors: np.ndarray, cfg: MultiTopicConfig) -> int:
    from sklearn.cluster import AgglomerativeClustering

    if len(vectors) < 2:
        return 1
    model = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=cfg.distance_threshold,
        metric="cosine",
        linkage="average",
    )
    return int(len(set(model.fit_predict(vectors))))


def multitopic_labels(
    frozen_dir: Path,
    cfg: MultiTopicConfig,
    *,
    embed_fn: Callable[[list[str]], np.ndarray],
) -> pd.DataFrame:
    """E3. Label each entity multi-topic from its own text-unit provenance.

    An entity is multi-topic when the pairwise cosine similarities among its
    source text units have variance above ``tau_variance`` **and** those units
    span at least ``min_clusters`` clusters (KB §H.2).
    """
    entities = io.load_entities(frozen_dir)
    text_units = io.load_text_units(frozen_dir)
    lookup = text_units.set_index(S.TextUnits.ID)[S.TextUnits.TEXT]

    rows: list[dict[str, object]] = []
    for _, ent in entities.iterrows():
        tu_ids = [i for i in (ent[S.Entities.TEXT_UNIT_IDS] or []) if i in lookup.index]
        n_units = len(tu_ids)
        if n_units < cfg.min_text_units:
            rows.append(
                {
                    "entity_id": ent[S.Entities.ID],
                    "title": ent[S.Entities.TITLE],
                    "degree": ent[S.Entities.DEGREE],
                    "n_text_units": n_units,
                    "sim_variance": float("nan"),
                    "sim_mean": float("nan"),
                    "n_clusters": 1,
                    "is_multitopic": False,
                }
            )
            continue
        vectors = np.asarray(embed_fn([str(lookup[i]) for i in tu_ids]), dtype=float)
        sims = _pairwise_cosine(vectors)
        variance = float(np.var(sims)) if sims.size else float("nan")
        n_clusters = _cluster_count(vectors, cfg)
        rows.append(
            {
                "entity_id": ent[S.Entities.ID],
                "title": ent[S.Entities.TITLE],
                "degree": ent[S.Entities.DEGREE],
                "n_text_units": n_units,
                "sim_variance": variance,
                "sim_mean": float(np.mean(sims)) if sims.size else float("nan"),
                "n_clusters": n_clusters,
                "is_multitopic": bool(variance > cfg.tau_variance and n_clusters >= cfg.min_clusters),
            }
        )
    return pd.DataFrame(rows)


def multitopic_rate(
    labels: pd.DataFrame, *, by_degree_quartile: bool = False
) -> Estimate | dict[str, Estimate]:
    """Multi-topic rate overall, or split by degree quartile."""
    from .stats import bootstrap_proportion, weight_quartiles

    if not by_degree_quartile:
        return bootstrap_proportion(labels["is_multitopic"].to_numpy(dtype=bool))
    quartile = weight_quartiles(labels["degree"])
    return {
        str(q): bootstrap_proportion(
            labels.loc[quartile == q, "is_multitopic"].to_numpy(dtype=bool)
        )
        for q in sorted(set(quartile.dropna()))
    }


# --------------------------------------------------------------------------
# L3 — truncation replay
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TruncationConfig:
    """Replay parameters, taken from the shipped code by E4-pre — not invented.

    Observed in graphrag 3.1.1:
    ``summarize_communities/graph_context/sort_context.py`` sorts edges by
    ``(-combined_degree, id)``, and admits elements until
    ``num_tokens(context) > max_context_tokens``. The default encoding is
    ``o200k_base`` (``graphrag/config/defaults.py``).
    """

    max_input_length: int
    tokenizer_name: str = "o200k_base"
    sort_key: str = "-combined_degree,id"


def _sorted_edges(relationships: pd.DataFrame, edge_ids: Sequence[str]) -> pd.DataFrame:
    sub = relationships[relationships[S.Relationships.ID].isin(set(edge_ids))].copy()
    degree_col = (
        S.Relationships.COMBINED_DEGREE
        if S.Relationships.COMBINED_DEGREE in sub.columns
        else S.Relationships.WEIGHT
    )
    sub["_sort_degree"] = sub[degree_col].astype(float)
    return sub.sort_values(
        by=["_sort_degree", S.Relationships.ID], ascending=[False, True]
    ).drop(columns="_sort_degree")


def replay_truncation(frozen_dir: Path, cfg: TruncationConfig) -> pd.DataFrame:
    """E4. Replay prioritisation + truncation offline for every community."""
    from .injection import get_tokenizer, token_len

    communities = io.load_communities(frozen_dir)
    relationships = io.load_relationships(frozen_dir)
    tokenizer = get_tokenizer(cfg.tokenizer_name)

    rows: list[dict[str, object]] = []
    for _, com in communities.iterrows():
        rids = list(com[S.Communities.RELATIONSHIP_IDS] or [])
        ordered = _sorted_edges(relationships, rids)
        used = 0
        admitted = 0
        for _, edge in ordered.iterrows():
            piece = f"{edge[S.Relationships.SOURCE]},{edge[S.Relationships.TARGET]},{edge[S.Relationships.DESCRIPTION]}\n"
            cost = token_len(piece, tokenizer)
            if used + cost > cfg.max_input_length:
                break
            used += cost
            admitted += 1
        rows.append(
            {
                "community": com[S.Communities.COMMUNITY],
                "level": com[S.Communities.LEVEL],
                "max_input_length": cfg.max_input_length,
                "n_elements": len(ordered),
                "n_admitted": admitted,
                "n_dropped": len(ordered) - admitted,
                "context_tokens": used,
                "overflowed": bool(admitted < len(ordered)),
            }
        )
    return pd.DataFrame(rows)


def dropped_elements(frozen_dir: Path, cfg: TruncationConfig) -> pd.DataFrame:
    """Per-element record of what truncation discarded, with degree attached."""
    from .injection import get_tokenizer, token_len

    communities = io.load_communities(frozen_dir)
    relationships = io.load_relationships(frozen_dir)
    tokenizer = get_tokenizer(cfg.tokenizer_name)

    rows: list[dict[str, object]] = []
    for _, com in communities.iterrows():
        rids = list(com[S.Communities.RELATIONSHIP_IDS] or [])
        ordered = _sorted_edges(relationships, rids)
        used = 0
        admitted = True
        for rank, (_, edge) in enumerate(ordered.iterrows()):
            piece = f"{edge[S.Relationships.SOURCE]},{edge[S.Relationships.TARGET]},{edge[S.Relationships.DESCRIPTION]}\n"
            cost = token_len(piece, tokenizer)
            if admitted and used + cost > cfg.max_input_length:
                admitted = False
            if admitted:
                used += cost
            rows.append(
                {
                    "element_id": edge[S.Relationships.ID],
                    "element_kind": "relationship",
                    "community": com[S.Communities.COMMUNITY],
                    "level": com[S.Communities.LEVEL],
                    "rank": rank,
                    "combined_degree": edge.get(S.Relationships.COMBINED_DEGREE, float("nan")),
                    "weight": edge[S.Relationships.WEIGHT],
                    "max_input_length": cfg.max_input_length,
                    "dropped": not admitted,
                }
            )
    return pd.DataFrame(rows)


def bottom_quartile_retention(dropped: pd.DataFrame) -> Estimate:
    """Retention rate among the lowest-degree quartile of elements.

    L3's claimed bias is against low-degree elements; this is the number that
    tests it.
    """
    from .stats import bootstrap_proportion, weight_quartiles

    if dropped.empty:
        return Estimate(float("nan"), float("nan"), float("nan"), 0, "bootstrap-percentile")
    quartile = weight_quartiles(dropped["combined_degree"].fillna(0.0))
    bottom = dropped.loc[quartile == "Q1"]
    return bootstrap_proportion((~bottom["dropped"]).to_numpy(dtype=bool))


# --------------------------------------------------------------------------
# The loss set L
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LossSet:
    """``L = L1 ∪ L2 ∪ L3`` (KB §H.1), with L1 tracked separately.

    L1 is kept apart deliberately. ``CONTEXT.md`` §2 notes that L1 does **not**
    satisfy ``supp(R(q, I)) ∩ L = ∅``: global search maps over all summaries, so
    a misassigned entity is still read, just in the wrong framing. Only L2 and
    L3 are unreachable by any retrieval policy, so only :meth:`hard` is
    intersected against gold evidence in E6 and injected in E9.
    """

    l1_entity_ids: frozenset[str]
    l2_relationship_ids: frozenset[str]
    l3_element_ids: frozenset[str]
    level: int | None
    scope: str

    def hard(self) -> frozenset[str]:
        """L2 ∪ L3 — the index-time loss no retrieval policy can reach."""
        return self.l2_relationship_ids | self.l3_element_ids

    def all_elements(self) -> frozenset[str]:
        return self.l1_entity_ids | self.hard()


def build_loss_set(
    *,
    cross_edges: Path,
    dropped: Path | None = None,
    multitopic: Path | None = None,
    level: int | None = None,
) -> LossSet:
    """Assemble ``L`` from cached experiment outputs."""
    cross_df, _ = io.read_cache(Path(cross_edges))
    l2 = frozenset(cross_df["relationship_id"].astype(str))

    l3: frozenset[str] = frozenset()
    if dropped is not None and Path(dropped).exists():
        drop_df, _ = io.read_cache(Path(dropped))
        l3 = frozenset(drop_df.loc[drop_df["dropped"], "element_id"].astype(str))

    l1: frozenset[str] = frozenset()
    if multitopic is not None and Path(multitopic).exists():
        mt_df, _ = io.read_cache(Path(multitopic))
        l1 = frozenset(mt_df.loc[mt_df["is_multitopic"], "entity_id"].astype(str))

    return LossSet(
        l1_entity_ids=l1,
        l2_relationship_ids=l2,
        l3_element_ids=l3,
        level=level,
        scope="perm" if level is None else f"level:{level}",
    )


def intersect(element_ids: Iterable[str], loss: LossSet) -> dict[str, frozenset[str]]:
    """Split ``element_ids`` by which component of ``L`` they fall in."""
    ids = frozenset(str(e) for e in element_ids)
    return {
        "in_L1": ids & loss.l1_entity_ids,
        "in_L2": ids & loss.l2_relationship_ids,
        "in_L3": ids & loss.l3_element_ids,
        "in_L_hard": ids & loss.hard(),
    }

"""Synthetic GraphRAG index fixtures mirroring the real output schema.

Every test that needs an index uses these, never real data. The graph is small
enough that its cross-edge sets can be written down by hand, which is what makes
``test_loss.py`` a real regression test rather than a tautology.

Topology
--------
Ten entities in five leaf communities (level 0), grouped into two communities at
level 1::

    level 0:  c0{e1,e2}  c1{e3,e4}  c2{e5,e6}  c3{e7,e8}  c4{e9,e10}
    level 1:  c10{e1..e4}            c11{e5..e10}

Nine relationships::

    r1 e1-e2   intra c0,  intra c10
    r2 e3-e4   intra c1,  intra c10
    r3 e5-e6   intra c2,  intra c11
    r4 e7-e8   intra c3,  intra c11
    r5 e9-e10  intra c4,  intra c11
    r6 e2-e3   CROSS at level 0, intra c10
    r7 e4-e5   CROSS at level 0, CROSS at level 1   -> permanent
    r8 e6-e7   CROSS at level 0, intra c11
    r9 e1-e9   CROSS at level 0, CROSS at level 1   -> permanent

So the expected answers, which the tests assert exactly:

* ``E_cross_level(0) == {r6, r7, r8, r9}``
* ``E_cross_level(1) == {r7, r9}``
* ``E_cross_perm     == {r7, r9}``
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

__all__ = [
    "EXPECTED_CROSS_LEVEL_0",
    "EXPECTED_CROSS_LEVEL_1",
    "EXPECTED_CROSS_PERM",
    "build_entities",
    "build_relationships",
    "build_communities",
    "build_community_reports",
    "build_text_units",
    "build_documents",
    "write_fixture_index",
]

EXPECTED_CROSS_LEVEL_0 = frozenset({"r6", "r7", "r8", "r9"})
EXPECTED_CROSS_LEVEL_1 = frozenset({"r7", "r9"})
EXPECTED_CROSS_PERM = frozenset({"r7", "r9"})

_ENTITY_TITLES = {
    "e1": "ALICE",
    "e2": "BOB",
    "e3": "CAROL",
    "e4": "DAVE",
    "e5": "ERIN",
    "e6": "FRANK",
    "e7": "GRACE",
    "e8": "HEIDI",
    "e9": "IVAN",
    "e10": "JUDY",
}

_EDGES = {
    "r1": ("e1", "e2"),
    "r2": ("e3", "e4"),
    "r3": ("e5", "e6"),
    "r4": ("e7", "e8"),
    "r5": ("e9", "e10"),
    "r6": ("e2", "e3"),
    "r7": ("e4", "e5"),
    "r8": ("e6", "e7"),
    "r9": ("e1", "e9"),
}

_LEVEL_0 = {
    0: ["e1", "e2"],
    1: ["e3", "e4"],
    2: ["e5", "e6"],
    3: ["e7", "e8"],
    4: ["e9", "e10"],
}
_LEVEL_1 = {
    10: ["e1", "e2", "e3", "e4"],
    11: ["e5", "e6", "e7", "e8", "e9", "e10"],
}
_PARENT = {0: 10, 1: 10, 2: 11, 3: 11, 4: 11}


def _intra(members: list[str]) -> list[str]:
    """Relationship ids with both endpoints inside ``members``."""
    member_set = set(members)
    return [rid for rid, (u, v) in _EDGES.items() if u in member_set and v in member_set]


def build_entities() -> pd.DataFrame:
    degree = {e: 0 for e in _ENTITY_TITLES}
    for u, v in _EDGES.values():
        degree[u] += 1
        degree[v] += 1
    return pd.DataFrame(
        [
            {
                "id": eid,
                "human_readable_id": i,
                "title": title,
                "type": "PERSON",
                "description": f"{title} is a person appearing in the synthetic fixture graph.",
                "text_unit_ids": [f"t{i % 5 + 1}", f"t{(i + 2) % 5 + 1}"],
                "frequency": 2,
                "degree": degree[eid],
            }
            for i, (eid, title) in enumerate(_ENTITY_TITLES.items())
        ]
    )


def build_relationships() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": rid,
                "human_readable_id": i,
                # graphrag stores entity *names* here, not ids: see
                # graphrag/data_model/relationship.py ("The source entity name")
                # and create_communities.py, which joins relationships to
                # communities on left_on="source", right_on="title".
                "source": _ENTITY_TITLES[u],
                "target": _ENTITY_TITLES[v],
                "description": f"{_ENTITY_TITLES[u]} is connected to {_ENTITY_TITLES[v]}.",
                "weight": float(i + 1),
                "combined_degree": float(10 - i),
                "text_unit_ids": [f"t{i % 5 + 1}"],
            }
            for i, (rid, (u, v)) in enumerate(_EDGES.items())
        ]
    )


def build_communities() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for cid, members in _LEVEL_0.items():
        rows.append(
            {
                "id": f"c{cid}",
                "human_readable_id": cid,
                "community": cid,
                "parent": _PARENT[cid],
                "children": [],
                "level": 0,
                "title": f"Community {cid}",
                "entity_ids": members,
                "relationship_ids": _intra(members),
                "text_unit_ids": [f"t{cid + 1}"],
                "period": "2026-08-15",
                "size": len(members),
            }
        )
    for cid, members in _LEVEL_1.items():
        rows.append(
            {
                "id": f"c{cid}",
                "human_readable_id": cid,
                "community": cid,
                "parent": -1,
                "children": [k for k, v in _PARENT.items() if v == cid],
                "level": 1,
                "title": f"Community {cid}",
                "entity_ids": members,
                "relationship_ids": _intra(members),
                "text_unit_ids": [f"t{(cid % 5) + 1}"],
                "period": "2026-08-15",
                "size": len(members),
            }
        )
    return pd.DataFrame(rows)


def build_community_reports() -> pd.DataFrame:
    communities = build_communities()
    rows = []
    for _, c in communities.iterrows():
        titles = [_ENTITY_TITLES[e] for e in c["entity_ids"]]
        body = " ".join(f"{t} is described in this community report." for t in titles)
        rows.append(
            {
                "id": f"report_{c['community']}",
                "human_readable_id": int(c["community"]),
                "community": c["community"],
                "level": c["level"],
                "parent": c["parent"],
                "children": c["children"],
                "title": f"Report for {c['title']}",
                "summary": f"Summary of {c['title']}.",
                "full_content": f"# {c['title']}\n\n{body}",
                "rank": 5.0,
                "rating_explanation": "synthetic",
                "findings": [],
                "full_content_json": "{}",
                "period": "2026-08-15",
                "size": int(c["size"]),
            }
        )
    return pd.DataFrame(rows)


def build_text_units(*, plural_s: bool = False) -> pd.DataFrame:
    """Synthetic ``text_units``.

    ``plural_s=True`` emits the legacy ``relationships_ids`` spelling documented
    in KB §A.3; the default emits the ``relationship_ids`` spelling that
    graphrag 3.1.1 actually writes. Tests exercise both so the detector cannot
    regress in either direction.
    """
    rel_col = "relationships_ids" if plural_s else "relationship_ids"
    rows = []
    for i in range(1, 6):
        ents = [f"e{2 * i - 1}", f"e{2 * i}"]
        rows.append(
            {
                "id": f"t{i}",
                "human_readable_id": i,
                "text": (
                    f"{_ENTITY_TITLES[ents[0]]} met {_ENTITY_TITLES[ents[1]]} in chapter {i}. "
                    f"They discussed the events of the synthetic fixture at length."
                ),
                "n_tokens": 24,
                "document_id": "d1",
                "entity_ids": ents,
                rel_col: [f"r{i}"],
                "covariate_ids": [],
            }
        )
    return pd.DataFrame(rows)


def build_documents() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": "d1",
                "human_readable_id": 0,
                "title": "Synthetic Novel",
                "text": "A synthetic document used only in tests.",
                "text_unit_ids": [f"t{i}" for i in range(1, 6)],
                "creation_date": "2026-08-15",
                "raw_data": None,
            }
        ]
    )


def write_fixture_index(target: Path, *, plural_s: bool = False) -> Path:
    """Materialise a complete synthetic index into ``target``.

    Also writes ``MANIFEST.sha256`` so loaders exercise the real verification
    path rather than a special-cased test branch.
    """
    from graphrag_loss import io as gio

    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    build_entities().to_parquet(target / "entities.parquet", index=False)
    build_relationships().to_parquet(target / "relationships.parquet", index=False)
    build_communities().to_parquet(target / "communities.parquet", index=False)
    build_community_reports().to_parquet(target / "community_reports.parquet", index=False)
    build_text_units(plural_s=plural_s).to_parquet(target / "text_units.parquet", index=False)
    build_documents().to_parquet(target / "documents.parquet", index=False)
    gio.write_manifest(target)
    return target

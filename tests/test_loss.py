"""L2 cross-edge computation against a hand-checkable synthetic index.

The fixture's five leaf communities and nine relationships were chosen so the
cross-edge sets can be written down by hand (see ``tests/fixtures``). These
tests assert the **exact** sets, not counts or bounds — a census that returns
the right cardinality with the wrong members would still be wrong.
"""

from __future__ import annotations

import pytest

from graphrag_loss import io as gio
from graphrag_loss import loss

from .fixtures import (
    EXPECTED_CROSS_LEVEL_0,
    EXPECTED_CROSS_LEVEL_1,
    EXPECTED_CROSS_PERM,
    build_communities,
    build_entities,
    build_relationships,
)


def test_cross_edges_at_level_0_is_exactly_the_known_set():
    got = loss.cross_edges_at_level(build_communities(), build_relationships(), 0)
    assert got == set(EXPECTED_CROSS_LEVEL_0)


def test_cross_edges_at_level_1_is_exactly_the_known_set():
    got = loss.cross_edges_at_level(build_communities(), build_relationships(), 1)
    assert got == set(EXPECTED_CROSS_LEVEL_1)


def test_cross_edges_permanent_is_exactly_the_known_set():
    got = loss.cross_edges_permanent(build_communities(), build_relationships())
    assert got == set(EXPECTED_CROSS_PERM)


def test_census_returns_the_known_set(frozen_dir):
    perm, per_level = loss.cross_edge_census(frozen_dir)
    assert set(perm.edge_ids) == set(EXPECTED_CROSS_PERM)
    assert set(per_level[0].edge_ids) == set(EXPECTED_CROSS_LEVEL_0)
    assert set(per_level[1].edge_ids) == set(EXPECTED_CROSS_LEVEL_1)


def test_permanent_is_a_subset_of_every_level():
    """KB §A.2: a leaf cross-edge may still sit inside a shared parent."""
    communities, relationships = build_communities(), build_relationships()
    perm = loss.cross_edges_permanent(communities, relationships)
    for level in (0, 1):
        assert perm <= loss.cross_edges_at_level(communities, relationships, level)


def test_hierarchy_relocates_loss_rather_than_removing_it():
    """CONTEXT §2: L2 shrinks going up the hierarchy but does not vanish."""
    communities, relationships = build_communities(), build_relationships()
    leaf = loss.cross_edges_at_level(communities, relationships, 0)
    root = loss.cross_edges_at_level(communities, relationships, 1)
    assert len(root) < len(leaf)
    assert len(root) > 0


def test_census_reports_no_confidence_interval(frozen_dir):
    """KB §D.4: E1 enumerates every edge, so the interval is degenerate."""
    perm, _ = loss.cross_edge_census(frozen_dir)
    for estimate in (perm.count, perm.fraction_of_E, perm.weight_fraction):
        assert estimate.method == "census"
        assert estimate.ci_low == estimate.value == estimate.ci_high


def test_fraction_and_weight_fraction_are_consistent(frozen_dir):
    perm, _ = loss.cross_edge_census(frozen_dir)
    relationships = gio.load_relationships(frozen_dir)
    assert perm.count.value == len(EXPECTED_CROSS_PERM)
    assert perm.fraction_of_E.value == pytest.approx(len(EXPECTED_CROSS_PERM) / len(relationships))

    total = relationships["weight"].sum()
    expected = relationships[relationships["id"].isin(EXPECTED_CROSS_PERM)]["weight"].sum() / total
    assert perm.weight_fraction.value == pytest.approx(expected)


def test_intra_relationship_ids_unions_across_levels():
    communities = build_communities()
    at_0 = loss.intra_relationship_ids(communities, 0)
    at_1 = loss.intra_relationship_ids(communities, 1)
    everywhere = loss.intra_relationship_ids(communities, None)
    assert everywhere == at_0 | at_1


def test_entity_to_community_recovers_membership():
    e2c = loss.entity_to_community(build_communities(), 0)
    mapping = dict(zip(e2c["entity_id"], e2c["community"], strict=True))
    assert mapping["e1"] == 0
    assert mapping["e9"] == 4
    assert len(mapping) == 10


def test_single_membership_holds_on_a_valid_index():
    """KB §I: exactly one community per entity per level. E0.5 aborts if not."""
    for level in (0, 1):
        assert loss.assert_single_membership(build_communities(), level) == []


def test_single_membership_violation_is_detected():
    communities = build_communities().copy()
    row = communities.index[communities["community"] == 1][0]
    communities.at[row, "entity_ids"] = ["e1", "e3", "e4"]  # e1 now in c0 and c1
    assert loss.assert_single_membership(communities, 0) == ["e1"]


def test_listed_relationships_are_wholly_internal():
    """KB §A.1's semantics, verified empirically before E1 relies on it."""
    violations = loss.verify_intra_community_edges(
        build_communities(), build_relationships(), build_entities()
    )
    assert violations == []


def test_endpoint_outside_entity_ids_is_flagged():
    communities = build_communities().copy()
    row = communities.index[communities["community"] == 0][0]
    communities.at[row, "relationship_ids"] = ["r1", "r7"]  # r7 = e4-e5, outside c0
    violations = loss.verify_intra_community_edges(
        communities, build_relationships(), build_entities()
    )
    assert violations
    assert all(v[1] == "r7" for v in violations)


def test_loss_set_keeps_l1_separate_from_hard_loss():
    """CONTEXT §2: L1 is still readable by global search, so it is not hard loss."""
    loss_set = loss.LossSet(
        l1_entity_ids=frozenset({"e1"}),
        l2_relationship_ids=frozenset({"r7", "r9"}),
        l3_element_ids=frozenset({"r3"}),
        level=None,
        scope="perm",
    )
    assert loss_set.hard() == {"r7", "r9", "r3"}
    assert "e1" not in loss_set.hard()
    assert "e1" in loss_set.all_elements()


def test_intersect_splits_by_loss_component():
    loss_set = loss.LossSet(
        l1_entity_ids=frozenset({"e1"}),
        l2_relationship_ids=frozenset({"r7"}),
        l3_element_ids=frozenset({"r3"}),
        level=None,
        scope="perm",
    )
    got = loss.intersect(["e1", "r7", "r3", "r1"], loss_set)
    assert got["in_L1"] == {"e1"}
    assert got["in_L2"] == {"r7"}
    assert got["in_L3"] == {"r3"}
    assert got["in_L_hard"] == {"r7", "r3"}

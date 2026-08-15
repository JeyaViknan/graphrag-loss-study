"""Gold-evidence linking (E6).

Covers both strategies. ``TRIPLE`` is the frozen E6 default (``GATES.md``
Appendix A); ``SENTENCE_FUZZY`` is retained for ablation and is tested here so
it cannot rot silently.
"""

from __future__ import annotations

import pandas as pd
import pytest

from graphrag_loss import io as gio
from graphrag_loss import linking
from graphrag_loss import schema as S

from .fixtures import build_entities, build_relationships, build_text_units

CFG_TRIPLE = linking.LinkConfig(strategy=linking.LinkStrategy.TRIPLE, threshold=85.0)
CFG_SENTENCE = linking.LinkConfig(strategy=linking.LinkStrategy.SENTENCE_FUZZY, threshold=60.0)


def test_frozen_defaults_match_gates_appendix_a():
    cfg = linking.LinkConfig()
    assert cfg.strategy is linking.LinkStrategy.TRIPLE
    assert cfg.threshold == 85.0
    assert cfg.scorer == "token_set_ratio"


def test_normalize_strips_punctuation_and_case():
    assert linking.normalize_text("Erica  Vagans, (the plant)!") == "erica vagans the plant"


@pytest.mark.parametrize(
    "raw",
    [
        "(alice, knows, bob)",
        "(alice, knows, bob).",
        "alice, knows, bob",
        "  ( ALICE , knows , BOB ) . ",
    ],
)
def test_parse_triple_accepts_the_shipped_forms(raw):
    parsed = linking.parse_triple(raw)
    assert parsed is not None
    head, relation, tail = parsed
    assert head.strip().lower() == "alice"
    assert relation.strip() == "knows"
    assert tail.strip().lower() == "bob"


@pytest.mark.parametrize("raw", ["alice knows bob", "(alice, knows)", "", "(a, b, c, d)"])
def test_malformed_triples_return_none(raw):
    assert linking.parse_triple(raw) is None


def test_text_unit_lookup_finds_its_known_elements():
    """A text unit with known entities and relationships resolves to exactly them."""
    text_units = build_text_units(plural_s=False)
    rel_col = S.detect_relationship_ids_column(text_units, S.TEXT_UNITS_FILE)
    ents, rels = linking.elements_for_text_unit(text_units, "t1", rel_col=rel_col)
    assert ents == {"e1", "e2"}
    assert rels == {"r1"}


def test_text_unit_lookup_works_under_plural_s_spelling():
    text_units = build_text_units(plural_s=True)
    rel_col = S.detect_relationship_ids_column(text_units, S.TEXT_UNITS_FILE)
    ents, rels = linking.elements_for_text_unit(text_units, "t3", rel_col=rel_col)
    assert ents == {"e5", "e6"}
    assert rels == {"r3"}


def test_unknown_text_unit_yields_empty_sets():
    text_units = build_text_units()
    ents, rels = linking.elements_for_text_unit(text_units, "does-not-exist", rel_col="relationship_ids")
    assert ents == frozenset()
    assert rels == frozenset()


def test_triple_links_both_endpoints_and_finds_the_relationship():
    entities, relationships = build_entities(), build_relationships()
    ents, rels, score = linking.link_triple(("ALICE", "is connected to", "BOB"), entities, relationships, CFG_TRIPLE)
    assert ents == {"e1", "e2"}
    assert rels == {"r1"}
    assert score >= 85.0


def test_triple_matching_is_case_and_punctuation_insensitive():
    entities, relationships = build_entities(), build_relationships()
    ents, _rels, _score = linking.link_triple(("alice.", "knows", "  bob "), entities, relationships, CFG_TRIPLE)
    assert ents == {"e1", "e2"}


def test_triple_with_one_unmatched_endpoint_counts_as_unlinked():
    """GATES A.2: a half-matched triple identifies no relationship."""
    entities, relationships = build_entities(), build_relationships()
    ents, rels, _score = linking.link_triple(
        ("ALICE", "knows", "ZZZZZZ_NOT_AN_ENTITY"), entities, relationships, CFG_TRIPLE
    )
    assert ents == frozenset()
    assert rels == frozenset()


def test_triple_for_a_cross_edge_resolves_to_that_relationship():
    """r7 (e4-e5) is a permanent cross-edge; E6 must be able to reach it."""
    entities, relationships = build_entities(), build_relationships()
    _ents, rels, _score = linking.link_triple(("DAVE", "is connected to", "ERIN"), entities, relationships, CFG_TRIPLE)
    assert rels == {"r7"}


def test_build_gold_links_over_triples(frozen_dir):
    questions = pd.DataFrame(
        [
            {"id": "q1", "evidence": ["irrelevant"], "evidence_triple": ["(ALICE, is connected to, BOB)"]},
            {"id": "q2", "evidence": ["irrelevant"], "evidence_triple": ["(DAVE, is connected to, ERIN)"]},
            {"id": "q3", "evidence": ["irrelevant"], "evidence_triple": ["(NOBODY, verb, NOTHING)"]},
        ]
    )
    links = linking.build_gold_links(frozen_dir, questions, CFG_TRIPLE)
    assert len(links) == 3
    by_q = links.set_index("question_id")
    assert by_q.loc["q1", "linked"]
    assert by_q.loc["q2", "relationship_ids"] == ["r7"]
    assert not by_q.loc["q3", "linked"]


def test_unlink_rate_matches_the_links_frame(frozen_dir):
    questions = pd.DataFrame(
        [
            {"id": f"q{i}", "evidence": [], "evidence_triple": ["(ALICE, is connected to, BOB)"]}
            for i in range(3)
        ]
        + [{"id": "q_bad", "evidence": [], "evidence_triple": ["(NOBODY, verb, NOTHING)"]}]
    )
    links = linking.build_gold_links(frozen_dir, questions, CFG_TRIPLE)
    rate = linking.unlink_rate(links)
    assert rate.value == pytest.approx(0.25)
    assert rate.n == 4


def test_sentence_strategy_still_finds_a_known_text_unit():
    text_units = build_text_units()
    tu_id, score = linking.link_sentence("ALICE met BOB in chapter 1", text_units, CFG_SENTENCE)
    assert tu_id == "t1"
    assert score >= CFG_SENTENCE.threshold


def test_sentence_below_threshold_is_unlinked():
    text_units = build_text_units()
    cfg = linking.LinkConfig(strategy=linking.LinkStrategy.SENTENCE_FUZZY, threshold=99.0)
    tu_id, _score = linking.link_sentence("completely unrelated content here", text_units, cfg)
    assert tu_id is None


def test_unknown_scorer_is_rejected():
    with pytest.raises(ValueError, match="unknown scorer"):
        linking.LinkConfig(scorer="not_a_scorer").scorer_fn()


def test_gold_links_carry_no_loss_intersection(frozen_dir):
    """Intersecting with L is the script's job, not the linker's."""
    questions = pd.DataFrame([{"id": "q1", "evidence": [], "evidence_triple": ["(ALICE, is connected to, BOB)"]}])
    links = linking.build_gold_links(frozen_dir, questions, CFG_TRIPLE)
    assert "in_L2_ids" not in links.columns
    assert set(links.columns) >= {"question_id", "linked", "entity_ids", "relationship_ids", "score"}

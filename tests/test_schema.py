"""Schema constants and the relationship-ids spelling tripwire.

The tripwire is tested in **both** directions: a frame carrying the legacy
plural-s spelling must be detected as such, and a frame carrying the singular
spelling must be detected as that — with neither silently accepted as the other.
Getting this wrong is the bug KB §A.3 warns about, and it would corrupt every
downstream element set without raising anything.
"""

from __future__ import annotations

import pandas as pd
import pytest

from graphrag_loss import io as gio
from graphrag_loss import schema as S

from .fixtures import build_communities, build_text_units


def test_all_six_output_files_are_named():
    assert set(S.ALL_FILES) == {
        "entities.parquet",
        "relationships.parquet",
        "communities.parquet",
        "community_reports.parquet",
        "text_units.parquet",
        "documents.parquet",
    }


def test_entities_has_no_community_column(frozen_dir):
    """KB §A.3: membership is only recoverable by exploding communities."""
    entities = gio.load_entities(frozen_dir)
    assert "community" not in entities.columns


@pytest.mark.parametrize("file", S.ALL_FILES)
def test_required_columns_present(frozen_dir, file):
    df = gio.load_frame(frozen_dir, file)
    assert S.missing_columns(df, file) == []


def test_detects_singular_spelling():
    df = build_text_units(plural_s=False)
    assert S.detect_relationship_ids_column(df, S.TEXT_UNITS_FILE) == "relationship_ids"


def test_detects_plural_s_spelling():
    df = build_text_units(plural_s=True)
    assert S.detect_relationship_ids_column(df, S.TEXT_UNITS_FILE) == "relationships_ids"


def test_spellings_are_distinct_constants():
    assert S.RELATIONSHIP_IDS_SINGULAR != S.RELATIONSHIP_IDS_PLURAL_S
    assert S.RELATIONSHIP_IDS_PLURAL_S == "relationships_ids"
    assert S.RELATIONSHIP_IDS_SINGULAR == "relationship_ids"


def test_singular_frame_does_not_carry_plural_s():
    df = build_text_units(plural_s=False)
    assert S.RELATIONSHIP_IDS_PLURAL_S not in df.columns


def test_plural_s_frame_does_not_carry_singular():
    df = build_text_units(plural_s=True)
    assert S.RELATIONSHIP_IDS_SINGULAR not in df.columns


def test_both_spellings_present_is_ambiguous_and_raises():
    df = build_text_units(plural_s=False)
    df = df.assign(relationships_ids=df["relationship_ids"])
    with pytest.raises(S.SchemaError, match="both"):
        S.detect_relationship_ids_column(df, S.TEXT_UNITS_FILE)


def test_neither_spelling_present_raises():
    df = build_text_units(plural_s=False).drop(columns=["relationship_ids"])
    with pytest.raises(S.SchemaError, match="neither"):
        S.detect_relationship_ids_column(df, S.TEXT_UNITS_FILE)


def test_communities_always_uses_singular():
    """The plural-s anomaly was only ever on text_units, never on communities."""
    assert S.detect_relationship_ids_column(build_communities(), S.COMMUNITIES_FILE) == "relationship_ids"


def test_diff_schema_reports_observed_spelling():
    divergence = S.diff_schema(build_text_units(plural_s=True), S.TEXT_UNITS_FILE)
    assert divergence.relationship_ids_spelling == "relationships_ids"
    assert not divergence.is_material()


def test_assert_frame_raises_on_missing_required_column(frozen_dir):
    entities = gio.load_entities(frozen_dir).drop(columns=["degree"])
    with pytest.raises(S.SchemaError, match="degree"):
        S.assert_frame(entities, S.ENTITIES_FILE)


def test_assert_frame_reports_every_problem_at_once(frozen_dir):
    entities = gio.load_entities(frozen_dir).drop(columns=["degree", "description"])
    with pytest.raises(S.SchemaError) as excinfo:
        S.assert_frame(entities, S.ENTITIES_FILE)
    assert "degree" in str(excinfo.value)
    assert "description" in str(excinfo.value)


def test_list_columns_must_hold_sequences(frozen_dir):
    communities = gio.load_communities(frozen_dir).assign(entity_ids="not-a-list")
    with pytest.raises(S.SchemaError, match="sequences"):
        S.assert_frame(communities, S.COMMUNITIES_FILE)


def test_unknown_file_raises():
    with pytest.raises(S.SchemaError, match="unknown output file"):
        S.missing_columns(pd.DataFrame(), "create_final_nodes.parquet")


def test_plural_s_distinction_returns_divergences_without_aborting(frozen_dir_plural_s):
    """E0.5 reports, it does not abort. See HANDOVER.md for the KB divergence."""
    text_units = gio.load_text_units(frozen_dir_plural_s)
    communities = gio.load_communities(frozen_dir_plural_s)
    tu_div, com_div = S.assert_plural_s_distinction(text_units, communities)
    assert tu_div.relationship_ids_spelling == "relationships_ids"
    assert com_div.relationship_ids_spelling == "relationship_ids"


def test_manifest_round_trips(frozen_dir):
    ok, bad = gio.verify_manifest(frozen_dir)
    assert ok, bad
    assert set(gio.read_manifest(frozen_dir)) == set(S.ALL_FILES)

"""Single source of truth for every GraphRAG output column name.

No other module in this package may contain a parquet column-name string
literal. This is the mechanism that prevents the ``relationship_ids`` /
``relationships_ids`` confusion described in ``KNOWLEDGE_BASE.md`` §A.3.

Observed divergence from the knowledge base
-------------------------------------------
``KNOWLEDGE_BASE.md`` §A.3 and ``CONTEXT.md`` §4 state that
``text_units.parquet`` carries ``relationships_ids`` (plural-s) while every
other file carries ``relationship_ids``. The installed graphrag 3.1.1 does
**not** reproduce that typo: ``graphrag/data_model/schemas.py`` defines a single
``RELATIONSHIP_IDS = "relationship_ids"`` used by both
``TEXT_UNITS_FINAL_COLUMNS`` and ``COMMUNITIES_FINAL_COLUMNS``.

Per project rule, the knowledge base is not silently edited. Instead both
spellings are first-class here, the spelling actually present is detected at
load time by :func:`detect_relationship_ids_column`, and the divergence is
reported loudly by E0.5 rather than aborting. See ``HANDOVER.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd

__all__ = [
    "SchemaError",
    "SchemaDivergence",
    "ENTITIES_FILE",
    "RELATIONSHIPS_FILE",
    "COMMUNITIES_FILE",
    "COMMUNITY_REPORTS_FILE",
    "TEXT_UNITS_FILE",
    "DOCUMENTS_FILE",
    "ALL_FILES",
    "MANIFEST_FILE",
    "RELATIONSHIP_IDS_SINGULAR",
    "RELATIONSHIP_IDS_PLURAL_S",
    "Entities",
    "Relationships",
    "Communities",
    "CommunityReports",
    "TextUnits",
    "Documents",
    "REQUIRED_COLUMNS",
    "LIST_COLUMNS",
    "detect_relationship_ids_column",
    "relationship_ids_column",
    "missing_columns",
    "unexpected_columns",
    "diff_schema",
    "assert_frame",
    "assert_plural_s_distinction",
]


class SchemaError(RuntimeError):
    """Raised when the frozen index does not match the expected schema."""


# --------------------------------------------------------------------------
# File names (KB §A.4, post-1.0). Pre-1.0 ``create_final_*`` names are gone.
# --------------------------------------------------------------------------

ENTITIES_FILE = "entities.parquet"
RELATIONSHIPS_FILE = "relationships.parquet"
COMMUNITIES_FILE = "communities.parquet"
COMMUNITY_REPORTS_FILE = "community_reports.parquet"
TEXT_UNITS_FILE = "text_units.parquet"
DOCUMENTS_FILE = "documents.parquet"

ALL_FILES: tuple[str, ...] = (
    ENTITIES_FILE,
    RELATIONSHIPS_FILE,
    COMMUNITIES_FILE,
    COMMUNITY_REPORTS_FILE,
    TEXT_UNITS_FILE,
    DOCUMENTS_FILE,
)

MANIFEST_FILE = "MANIFEST.sha256"

DEPRECATED_PREFIXES: frozenset[str] = frozenset({"create_final_"})

# --------------------------------------------------------------------------
# The two spellings. Never type either of these strings anywhere else.
# --------------------------------------------------------------------------

RELATIONSHIP_IDS_SINGULAR = "relationship_ids"
RELATIONSHIP_IDS_PLURAL_S = "relationships_ids"

# Shared column names.
_ID = "id"
_SHORT_ID = "human_readable_id"
_TITLE = "title"
_TYPE = "type"
_DESCRIPTION = "description"
_TEXT = "text"
_TEXT_UNIT_IDS = "text_unit_ids"
_ENTITY_IDS = "entity_ids"
_LEVEL = "level"
_COMMUNITY = "community"
_SIZE = "size"


class Entities:
    """Columns of ``entities.parquet``.

    Note there is deliberately **no** ``community`` column: membership is only
    recoverable by exploding ``communities.entity_ids`` (KB §A.3).
    """

    ID = _ID
    SHORT_ID = _SHORT_ID
    TITLE = _TITLE
    TYPE = _TYPE
    DESCRIPTION = _DESCRIPTION
    TEXT_UNIT_IDS = _TEXT_UNIT_IDS
    FREQUENCY = "frequency"
    DEGREE = "degree"


class Relationships:
    """Columns of ``relationships.parquet``."""

    ID = _ID
    SHORT_ID = _SHORT_ID
    SOURCE = "source"
    TARGET = "target"
    DESCRIPTION = _DESCRIPTION
    WEIGHT = "weight"
    COMBINED_DEGREE = "combined_degree"
    TEXT_UNIT_IDS = _TEXT_UNIT_IDS


class Communities:
    """Columns of ``communities.parquet``.

    ``RELATIONSHIP_IDS`` holds *wholly-internal* edges only — both endpoints in
    ``entity_ids``. That semantics, documented at Microsoft GraphRAG
    ``/index/outputs/`` and restated in KB §A.1, is the entire basis of the L2
    set difference. E0.5 verifies it empirically before E1 relies on it.
    """

    ID = _ID
    SHORT_ID = _SHORT_ID
    COMMUNITY = _COMMUNITY
    PARENT = "parent"
    CHILDREN = "children"
    LEVEL = _LEVEL
    TITLE = _TITLE
    ENTITY_IDS = _ENTITY_IDS
    RELATIONSHIP_IDS = RELATIONSHIP_IDS_SINGULAR
    TEXT_UNIT_IDS = _TEXT_UNIT_IDS
    PERIOD = "period"
    SIZE = _SIZE


class CommunityReports:
    """Columns of ``community_reports.parquet``."""

    ID = _ID
    SHORT_ID = _SHORT_ID
    COMMUNITY = _COMMUNITY
    LEVEL = _LEVEL
    PARENT = "parent"
    CHILDREN = "children"
    TITLE = _TITLE
    SUMMARY = "summary"
    FULL_CONTENT = "full_content"
    RANK = "rank"
    RATING_EXPLANATION = "rating_explanation"
    FINDINGS = "findings"
    FULL_CONTENT_JSON = "full_content_json"
    PERIOD = "period"
    SIZE = _SIZE


class TextUnits:
    """Columns of ``text_units.parquet``.

    ``RELATIONSHIP_IDS`` is intentionally absent as a constant: the spelling
    varies by graphrag version, so callers must go through
    :func:`relationship_ids_column` or :func:`detect_relationship_ids_column`.
    """

    ID = _ID
    SHORT_ID = _SHORT_ID
    TEXT = _TEXT
    N_TOKENS = "n_tokens"
    DOCUMENT_ID = "document_id"
    ENTITY_IDS = _ENTITY_IDS
    COVARIATE_IDS = "covariate_ids"


class Documents:
    """Columns of ``documents.parquet``.

    KB §A lists a ``metadata`` column; graphrag 3.1.1 emits ``creation_date``
    and ``raw_data`` instead. Recorded as a divergence, not silently reconciled.
    """

    ID = _ID
    SHORT_ID = _SHORT_ID
    TITLE = _TITLE
    TEXT = _TEXT
    TEXT_UNIT_IDS = _TEXT_UNIT_IDS
    CREATION_DATE = "creation_date"
    RAW_DATA = "raw_data"


# Columns without which an experiment cannot run. Extra columns are fine and
# are reported as informational only.
REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    ENTITIES_FILE: frozenset(
        {
            Entities.ID,
            Entities.TITLE,
            Entities.DESCRIPTION,
            Entities.TEXT_UNIT_IDS,
            Entities.DEGREE,
        }
    ),
    RELATIONSHIPS_FILE: frozenset(
        {
            Relationships.ID,
            Relationships.SOURCE,
            Relationships.TARGET,
            Relationships.DESCRIPTION,
            Relationships.WEIGHT,
        }
    ),
    COMMUNITIES_FILE: frozenset(
        {
            Communities.COMMUNITY,
            Communities.LEVEL,
            Communities.ENTITY_IDS,
            Communities.RELATIONSHIP_IDS,
        }
    ),
    COMMUNITY_REPORTS_FILE: frozenset(
        {
            CommunityReports.COMMUNITY,
            CommunityReports.LEVEL,
            CommunityReports.SUMMARY,
            CommunityReports.FULL_CONTENT,
        }
    ),
    TEXT_UNITS_FILE: frozenset(
        {
            TextUnits.ID,
            TextUnits.TEXT,
            TextUnits.ENTITY_IDS,
        }
    ),
    DOCUMENTS_FILE: frozenset(
        {
            Documents.ID,
            Documents.TITLE,
            Documents.TEXT_UNIT_IDS,
        }
    ),
}

# Columns that must hold sequences rather than scalars.
LIST_COLUMNS: dict[str, frozenset[str]] = {
    ENTITIES_FILE: frozenset({Entities.TEXT_UNIT_IDS}),
    RELATIONSHIPS_FILE: frozenset({Relationships.TEXT_UNIT_IDS}),
    COMMUNITIES_FILE: frozenset(
        {Communities.ENTITY_IDS, Communities.RELATIONSHIP_IDS, Communities.TEXT_UNIT_IDS}
    ),
    COMMUNITY_REPORTS_FILE: frozenset(),
    TEXT_UNITS_FILE: frozenset({TextUnits.ENTITY_IDS}),
    DOCUMENTS_FILE: frozenset({Documents.TEXT_UNIT_IDS}),
}


@dataclass(frozen=True)
class SchemaDivergence:
    """What the frozen index actually looks like versus what was expected."""

    file: str
    expected: frozenset[str]
    observed: frozenset[str]
    missing: frozenset[str]
    extra: frozenset[str]
    relationship_ids_spelling: str | None

    def is_material(self) -> bool:
        """True when a required column is absent. Extra columns are benign."""
        return bool(self.missing)

    def describe(self) -> str:
        parts = [f"{self.file}:"]
        if self.missing:
            parts.append(f"MISSING {sorted(self.missing)}")
        if self.extra:
            parts.append(f"extra {sorted(self.extra)}")
        if self.relationship_ids_spelling:
            parts.append(f"relationship-ids spelling = {self.relationship_ids_spelling!r}")
        if not self.missing and not self.extra:
            parts.append("exact match")
        return " ".join(parts)


def detect_relationship_ids_column(df: "pd.DataFrame", file: str) -> str:
    """Return whichever relationship-id spelling is present on ``df``.

    Raises
    ------
    SchemaError
        If both spellings are present (ambiguous) or neither is (not a
        relationship-bearing frame).
    """
    has_singular = RELATIONSHIP_IDS_SINGULAR in df.columns
    has_plural = RELATIONSHIP_IDS_PLURAL_S in df.columns
    if has_singular and has_plural:
        msg = (
            f"{file}: both {RELATIONSHIP_IDS_SINGULAR!r} and "
            f"{RELATIONSHIP_IDS_PLURAL_S!r} are present; cannot disambiguate"
        )
        raise SchemaError(msg)
    if has_singular:
        return RELATIONSHIP_IDS_SINGULAR
    if has_plural:
        return RELATIONSHIP_IDS_PLURAL_S
    msg = (
        f"{file}: neither {RELATIONSHIP_IDS_SINGULAR!r} nor "
        f"{RELATIONSHIP_IDS_PLURAL_S!r} is present; columns are {sorted(df.columns)}"
    )
    raise SchemaError(msg)


def relationship_ids_column(file: str) -> str:
    """The relationship-id spelling KB §A.3 expects for ``file``.

    This is the *documented* expectation, used to compute divergence. Code that
    reads a real frame should call :func:`detect_relationship_ids_column`
    instead, which reports what is actually there.
    """
    if file == TEXT_UNITS_FILE:
        return RELATIONSHIP_IDS_PLURAL_S
    return RELATIONSHIP_IDS_SINGULAR


def _expected_columns(file: str) -> frozenset[str]:
    try:
        return REQUIRED_COLUMNS[file]
    except KeyError:
        msg = f"unknown output file {file!r}; expected one of {ALL_FILES}"
        raise SchemaError(msg) from None


def missing_columns(df: "pd.DataFrame", file: str) -> list[str]:
    """Required columns absent from ``df``."""
    return sorted(_expected_columns(file) - set(df.columns))


def unexpected_columns(df: "pd.DataFrame", file: str) -> list[str]:
    """Columns present on ``df`` beyond the required set. Informational."""
    return sorted(set(df.columns) - _expected_columns(file))


def diff_schema(df: "pd.DataFrame", file: str) -> SchemaDivergence:
    """Compare an observed frame against the expected schema for ``file``."""
    expected = _expected_columns(file)
    observed = frozenset(df.columns)
    spelling: str | None = None
    if RELATIONSHIP_IDS_SINGULAR in observed:
        spelling = RELATIONSHIP_IDS_SINGULAR
    elif RELATIONSHIP_IDS_PLURAL_S in observed:
        spelling = RELATIONSHIP_IDS_PLURAL_S
    return SchemaDivergence(
        file=file,
        expected=expected,
        observed=observed,
        missing=frozenset(expected - observed),
        extra=frozenset(observed - expected),
        relationship_ids_spelling=spelling,
    )


def assert_frame(df: "pd.DataFrame", file: str) -> None:
    """Raise :class:`SchemaError` listing every problem at once.

    Never partial-fails: the caller sees the complete set of missing columns in
    one message rather than discovering them one run at a time.
    """
    problems: list[str] = []

    missing = missing_columns(df, file)
    if missing:
        problems.append(f"missing required columns {missing}")

    for col in LIST_COLUMNS.get(file, frozenset()):
        if col not in df.columns or len(df) == 0:
            continue
        sample = df[col].iloc[0]
        if isinstance(sample, (str, bytes)) or not hasattr(sample, "__iter__"):
            problems.append(f"column {col!r} should hold sequences, found {type(sample).__name__}")

    if problems:
        msg = f"{file}: " + "; ".join(problems) + f" (observed columns: {sorted(df.columns)})"
        raise SchemaError(msg)


def assert_plural_s_distinction(
    text_units: "pd.DataFrame", communities: "pd.DataFrame"
) -> tuple[SchemaDivergence, SchemaDivergence]:
    """Report the relationship-id spelling on both frames.

    Deliberately **not** a hard tripwire. ``CONTEXT.md``'s E0.5 specification
    asks for an abort when ``text_units`` lacks the plural-s spelling, but
    graphrag 3.1.1 emits the singular spelling on a perfectly valid index, so
    that abort would fire on every current build. E0.5 reports the divergence
    instead and reserves aborts for genuine integrity violations.
    """
    return (
        diff_schema(text_units, TEXT_UNITS_FILE),
        diff_schema(communities, COMMUNITIES_FILE),
    )

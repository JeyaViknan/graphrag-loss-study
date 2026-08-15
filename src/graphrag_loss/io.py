"""Parquet loaders, manifest hashing, and the run-provenance contract.

Two rules from the build spec are enforced structurally here:

1. Every function that reads the frozen index takes an explicit
   ``frozen_dir: Path``. There is no global state and no default path, so a
   result is reproducible by passing the same directory six months from now.
2. Every result CSV carries a :class:`RunStamp` header — git commit, index
   manifest hash, corpus hash, timestamp, model strings, library versions. If
   the index changes underneath an experiment, the mismatch is visible in the
   artifact rather than inferred.

Frames are loaded under pandas 3 copy-on-write semantics and are never mutated
in place by this package.
"""

from __future__ import annotations

import csv
import hashlib
import platform
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from . import schema as S

__all__ = [
    "as_list",
    "RunStamp",
    "FrozenIndex",
    "load_frame",
    "load_entities",
    "load_relationships",
    "load_communities",
    "load_community_reports",
    "load_text_units",
    "load_documents",
    "load_index",
    "sha256_file",
    "write_manifest",
    "read_manifest",
    "manifest_hash",
    "verify_manifest",
    "git_commit",
    "make_run_stamp",
    "write_result_csv",
    "read_result_csv",
    "write_cache",
    "read_cache",
    "require_inputs",
    "assert_same_index",
]

_HEADER_PREFIX = "# "


def as_list(value: object) -> list:
    """Normalise a parquet list-column cell to a plain list.

    pyarrow hands back ``numpy.ndarray`` for list columns, and ``value or []``
    raises ``ValueError: truth value of an array … is ambiguous`` on any array
    with more than one element. Every read of a list column goes through here so
    that idiom never appears in the codebase.
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if hasattr(value, "tolist"):  # numpy array / pandas array
        return list(value.tolist())
    if isinstance(value, float) and value != value:  # NaN
        return []
    return list(value)


@dataclass(frozen=True)
class RunStamp:
    """Provenance for one experiment run, written into every artifact."""

    experiment: str
    script: str
    git_commit: str
    git_dirty: bool
    manifest_hash: str
    corpus_sha256: str | None
    timestamp_utc: str
    llm_model: str | None
    nli_model: str | None
    python_version: str
    graphrag_version: str

    def as_header_lines(self) -> list[str]:
        return [f"{_HEADER_PREFIX}{k}: {v}" for k, v in asdict(self).items()]


@dataclass(frozen=True)
class FrozenIndex:
    """All six output parquets plus the manifest hash that identifies them."""

    frozen_dir: Path
    manifest_hash: str
    entities: pd.DataFrame
    relationships: pd.DataFrame
    communities: pd.DataFrame
    community_reports: pd.DataFrame
    text_units: pd.DataFrame
    documents: pd.DataFrame

    def levels(self) -> list[int]:
        """Sorted distinct community levels present in the index."""
        return sorted(int(x) for x in self.communities[S.Communities.LEVEL].unique())

    def max_level(self) -> int:
        return max(self.levels())

    def text_unit_relationship_column(self) -> str:
        """Whichever relationship-id spelling ``text_units`` actually uses."""
        return S.detect_relationship_ids_column(self.text_units, S.TEXT_UNITS_FILE)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_frame(frozen_dir: Path, file: str, *, validate: bool = True) -> pd.DataFrame:
    """Read one output parquet from ``frozen_dir``."""
    path = Path(frozen_dir) / file
    if not path.exists():
        msg = (
            f"{path} does not exist. Run scripts/00_index.sh first, and check that "
            f"--frozen-dir points at the directory holding {', '.join(S.ALL_FILES)}."
        )
        raise FileNotFoundError(msg)
    df = pd.read_parquet(path)
    if validate:
        S.assert_frame(df, file)
    return df


def load_entities(frozen_dir: Path, *, validate: bool = True) -> pd.DataFrame:
    return load_frame(frozen_dir, S.ENTITIES_FILE, validate=validate)


def load_relationships(frozen_dir: Path, *, validate: bool = True) -> pd.DataFrame:
    return load_frame(frozen_dir, S.RELATIONSHIPS_FILE, validate=validate)


def load_communities(frozen_dir: Path, *, validate: bool = True) -> pd.DataFrame:
    return load_frame(frozen_dir, S.COMMUNITIES_FILE, validate=validate)


def load_community_reports(frozen_dir: Path, *, validate: bool = True) -> pd.DataFrame:
    return load_frame(frozen_dir, S.COMMUNITY_REPORTS_FILE, validate=validate)


def load_text_units(frozen_dir: Path, *, validate: bool = True) -> pd.DataFrame:
    return load_frame(frozen_dir, S.TEXT_UNITS_FILE, validate=validate)


def load_documents(frozen_dir: Path, *, validate: bool = True) -> pd.DataFrame:
    return load_frame(frozen_dir, S.DOCUMENTS_FILE, validate=validate)


def load_index(
    frozen_dir: Path, *, validate: bool = True, check_manifest: bool = True
) -> FrozenIndex:
    """Load the whole frozen index in one call."""
    frozen_dir = Path(frozen_dir)
    if check_manifest and (frozen_dir / S.MANIFEST_FILE).exists():
        ok, bad = verify_manifest(frozen_dir)
        if not ok:
            msg = (
                f"frozen index at {frozen_dir} does not match {S.MANIFEST_FILE}: "
                f"{bad}. The index changed after it was frozen; results computed "
                f"against it are not comparable to earlier ones."
            )
            raise RuntimeError(msg)
    return FrozenIndex(
        frozen_dir=frozen_dir,
        manifest_hash=manifest_hash(frozen_dir),
        entities=load_entities(frozen_dir, validate=validate),
        relationships=load_relationships(frozen_dir, validate=validate),
        communities=load_communities(frozen_dir, validate=validate),
        community_reports=load_community_reports(frozen_dir, validate=validate),
        text_units=load_text_units(frozen_dir, validate=validate),
        documents=load_documents(frozen_dir, validate=validate),
    )


# --------------------------------------------------------------------------
# Manifest and provenance
# --------------------------------------------------------------------------


def sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def write_manifest(frozen_dir: Path) -> Path:
    """Hash all six parquets into ``MANIFEST.sha256``. Run once, at E0."""
    frozen_dir = Path(frozen_dir)
    lines = []
    for name in S.ALL_FILES:
        path = frozen_dir / name
        if not path.exists():
            msg = f"cannot write manifest: {path} is missing"
            raise FileNotFoundError(msg)
        lines.append(f"{sha256_file(path)}  {name}")
    out = frozen_dir / S.MANIFEST_FILE
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def read_manifest(frozen_dir: Path) -> dict[str, str]:
    path = Path(frozen_dir) / S.MANIFEST_FILE
    if not path.exists():
        msg = f"{path} not found; run scripts/00_index.sh to generate it"
        raise FileNotFoundError(msg)
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        out[name.strip()] = digest.strip()
    return out


def manifest_hash(frozen_dir: Path) -> str:
    """Hash of the manifest itself — a single identifier for the whole index."""
    path = Path(frozen_dir) / S.MANIFEST_FILE
    if not path.exists():
        return "NO-MANIFEST"
    return sha256_file(path)


def verify_manifest(frozen_dir: Path) -> tuple[bool, list[str]]:
    """Recompute every hash. Returns ``(ok, mismatched_or_missing_files)``."""
    frozen_dir = Path(frozen_dir)
    expected = read_manifest(frozen_dir)
    bad: list[str] = []
    for name, digest in expected.items():
        path = frozen_dir / name
        if not path.exists():
            bad.append(f"{name} (missing)")
        elif sha256_file(path) != digest:
            bad.append(f"{name} (hash mismatch)")
    return (not bad), bad


def git_commit(repo_dir: Path) -> tuple[str, bool]:
    """Return ``(short_sha, dirty)`` for the repository containing ``repo_dir``."""
    try:
        sha = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(repo_dir), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "UNKNOWN", False
    return sha, bool(status)


def _graphrag_version() -> str:
    try:
        from importlib.metadata import version

        return version("graphrag")
    except Exception:  # noqa: BLE001 - version reporting must never break a run
        return "UNKNOWN"


def make_run_stamp(
    frozen_dir: Path,
    *,
    experiment: str,
    script: str,
    repo_dir: Path | None = None,
    corpus_path: Path | None = None,
    llm_model: str | None = None,
    nli_model: str | None = None,
) -> RunStamp:
    sha, dirty = git_commit(repo_dir or Path.cwd())
    return RunStamp(
        experiment=experiment,
        script=script,
        git_commit=sha,
        git_dirty=dirty,
        manifest_hash=manifest_hash(frozen_dir),
        corpus_sha256=sha256_file(corpus_path) if corpus_path and Path(corpus_path).exists() else None,
        timestamp_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        llm_model=llm_model,
        nli_model=nli_model,
        python_version=platform.python_version(),
        graphrag_version=_graphrag_version(),
    )


# --------------------------------------------------------------------------
# Experiment I/O contract
# --------------------------------------------------------------------------


def write_result_csv(df: pd.DataFrame, path: Path, stamp: RunStamp) -> Path:
    """Write a results CSV prefixed with ``# key: value`` provenance lines."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        for line in stamp.as_header_lines():
            fh.write(line + "\n")
        df.to_csv(fh, index=False, quoting=csv.QUOTE_MINIMAL)
    return path


def read_result_csv(path: Path) -> tuple[pd.DataFrame, RunStamp]:
    """Inverse of :func:`write_result_csv`."""
    path = Path(path)
    meta: dict[str, str] = {}
    skip = 0
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.startswith(_HEADER_PREFIX):
                break
            skip += 1
            key, _, value = line[len(_HEADER_PREFIX) :].strip().partition(": ")
            meta[key] = value
    df = pd.read_csv(path, skiprows=skip)
    stamp = RunStamp(
        experiment=meta.get("experiment", ""),
        script=meta.get("script", ""),
        git_commit=meta.get("git_commit", ""),
        git_dirty=meta.get("git_dirty", "False") == "True",
        manifest_hash=meta.get("manifest_hash", ""),
        corpus_sha256=meta.get("corpus_sha256") or None,
        timestamp_utc=meta.get("timestamp_utc", ""),
        llm_model=meta.get("llm_model") or None,
        nli_model=meta.get("nli_model") or None,
        python_version=meta.get("python_version", ""),
        graphrag_version=meta.get("graphrag_version", ""),
    )
    return df, stamp


def write_cache(df: pd.DataFrame, path: Path, stamp: RunStamp) -> Path:
    """Write an intermediate artifact as parquet with provenance metadata."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    meta = {k.encode(): str(v).encode() for k, v in asdict(stamp).items()}
    table = table.replace_schema_metadata({**(table.schema.metadata or {}), **meta})
    pq.write_table(table, path)
    return path


def read_cache(path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    """Read a cache artifact and its provenance metadata."""
    import pyarrow.parquet as pq

    path = Path(path)
    if not path.exists():
        msg = f"{path} not found; the experiment that produces it has not run"
        raise FileNotFoundError(msg)
    table = pq.read_table(path)
    raw = table.schema.metadata or {}
    meta = {
        k.decode(): v.decode()
        for k, v in raw.items()
        if not k.decode().startswith("pandas")
    }
    return table.to_pandas(), meta


_PRODUCER = {
    "E_cross_perm.parquet": "scripts/02_cross_edges.py",
    "E_cross_level.parquet": "scripts/02_cross_edges.py",
    "L1_multitopic.parquet": "scripts/03_multitopic.py",
    "L3_dropped.parquet": "scripts/04_truncation_replay.py",
    "gold_links.parquet": "scripts/06_gold_links.py",
    "query_outputs.jsonl": "scripts/07_query.py",
}


def require_inputs(paths: Sequence[Path], *, experiment: str) -> None:
    """Assert that upstream artifacts exist, naming the script that makes them."""
    missing = [Path(p) for p in paths if not Path(p).exists()]
    if not missing:
        return
    lines = [f"{experiment} cannot run — missing upstream artifacts:"]
    for p in missing:
        producer = _PRODUCER.get(p.name, "an earlier experiment")
        lines.append(f"  {p}  (produced by {producer})")
    raise FileNotFoundError("\n".join(lines))


def assert_same_index(stamps: Sequence[RunStamp | dict[str, str]]) -> None:
    """Assert every upstream artifact was computed against the same index."""
    hashes = set()
    for s in stamps:
        h = s.manifest_hash if isinstance(s, RunStamp) else s.get("manifest_hash", "")
        if h:
            hashes.add(h)
    if len(hashes) > 1:
        msg = (
            "upstream artifacts were computed against different frozen indexes "
            f"(manifest hashes: {sorted(hashes)}). Re-run the earlier experiments "
            "against the current index before continuing."
        )
        raise RuntimeError(msg)

"""Measurement tooling for the GraphRAG indexing-loss study.

This package is instrumentation, not an algorithm. Per ``CONTEXT.md`` §1 and §9
the week's work is to *measure* whether GraphRAG's index construction
irreversibly discards information before any query is asked — not to design a
retrieval method, an index, a benchmark, or an evaluation framework.

Layout:

* :mod:`schema`      — every column-name constant, plus the version-divergence detector.
* :mod:`io`          — parquet loaders, manifest hashing, run provenance.
* :mod:`stats`       — the ``Estimate`` contract, bootstrap, McNemar, κ, partial correlation.
* :mod:`loss`        — L1 / L2 / L3 computation and the loss set ``L``.
* :mod:`linking`     — gold evidence to index elements (E6).
* :mod:`nli`         — calibrated NLI wrapper (E5).
* :mod:`injection`   — token-exact displacement (E9).
* :mod:`attribution` — three-way failure classifier (E8).
* :mod:`report`      — markdown report writer.

Every function that reads the frozen index takes an explicit ``frozen_dir``.
Every headline number is an :class:`~graphrag_loss.stats.Estimate`, never a bare
float — a number without an interval is not reportable in this project.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = [
    "attribution",
    "injection",
    "io",
    "linking",
    "loss",
    "nli",
    "report",
    "schema",
    "stats",
]

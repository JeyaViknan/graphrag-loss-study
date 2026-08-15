"""Markdown report writer, one per experiment.

Every report carries the same six sections — **Setup, Method, Numbers, Gate
decision, Caveats, Next** — so that six months from now the reports can be read
side by side without re-deriving each experiment's conventions.

:func:`edge_et_al_caveat` is appended to the Caveats section unconditionally.
``CONTEXT.md`` §10 and ``KNOWLEDGE_BASE.md`` §F.1 both require that Edge et al.
Experiment 2 stay visible in every writeup: it found no significant difference
between GraphRAG global search and TS, and TS has zero L1 and zero L2 by
construction, so it is prior evidence *in the primary source* cutting against
this study's hypothesis. Making it structural rather than optional is the point
— a caveat that can be forgotten will be.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .io import RunStamp
from .stats import Estimate

__all__ = [
    "GateDecision",
    "format_estimate",
    "estimates_table",
    "gate_banner",
    "edge_et_al_caveat",
    "render_report",
    "write_report",
    "headline",
]


@dataclass(frozen=True)
class GateDecision:
    """A gate evaluated against its frozen threshold."""

    gate: str
    metric: str
    value: float
    threshold: float
    fired: bool
    rule: str
    stop_the_week: bool = True

    def stdout_line(self) -> str:
        if self.fired:
            return f"GATE {self.gate} FAILED — {self.rule}"
        return f"GATE {self.gate} passed — {self.metric} = {self.value:.4g} ({self.rule})"


def format_estimate(e: Estimate, *, pct: bool = False, digits: int = 3) -> str:
    """Render an estimate as ``value [lo, hi] (n=…, method)``."""
    scale = 100.0 if pct else 1.0
    suffix = "%" if pct else ""
    if e.method == "census":
        return f"{e.value * scale:.{digits}f}{suffix} (census, n={e.n})"
    return (
        f"{e.value * scale:.{digits}f}{suffix} "
        f"[{e.ci_low * scale:.{digits}f}, {e.ci_high * scale:.{digits}f}] "
        f"(n={e.n}, {e.method})"
    )


def estimates_table(rows: Mapping[str, Estimate], *, pct: bool = False) -> str:
    """Markdown table of named estimates."""
    lines = ["| Quantity | Value | 95% CI | n | Method |", "|:--|--:|:--|--:|:--|"]
    scale = 100.0 if pct else 1.0
    suffix = "%" if pct else ""
    for name, e in rows.items():
        ci = "—" if e.method == "census" else f"[{e.ci_low * scale:.3f}, {e.ci_high * scale:.3f}]"
        lines.append(f"| {name} | {e.value * scale:.3f}{suffix} | {ci} | {e.n} | {e.method} |")
    return "\n".join(lines)


def gate_banner(d: GateDecision) -> str:
    if d.fired:
        body = [
            f"## ⛔ GATE {d.gate} FAILED",
            "",
            f"- **Metric:** {d.metric}",
            f"- **Observed:** {d.value:.4g}",
            f"- **Kill threshold:** {d.threshold:.4g}",
            f"- **Rule:** {d.rule}",
            "",
        ]
        if d.stop_the_week:
            body.append(
                "**Stop.** Per `CONTEXT.md` §9 no subsequent experiment runs until the "
                "user decides whether to override or pivot. A fired gate is not "
                "renegotiated into a marginal result."
            )
        return "\n".join(body)
    return "\n".join(
        [
            f"## ✅ GATE {d.gate} passed",
            "",
            f"- **Metric:** {d.metric}",
            f"- **Observed:** {d.value:.4g}",
            f"- **Kill threshold:** {d.threshold:.4g}",
            f"- **Rule:** {d.rule}",
        ]
    )


def edge_et_al_caveat() -> str:
    """Mandatory counter-evidence paragraph (CONTEXT §10, KB §F.1)."""
    return (
        "**Counter-evidence (mandatory, `CONTEXT.md` §10 / KB §F.1).** Edge et al. "
        "Experiment 2 compared GraphRAG global search against TS — map-reduce "
        "summarisation over the raw source, with no partition and therefore zero L1 "
        "and zero L2 by construction — and found no statistically significant "
        "difference, either among global search conditions or between global search "
        "and TS. That is prior evidence, in this study's own primary source, that "
        "partition loss does not move aggregate answer quality. This study measures at "
        "the element level rather than the aggregate-answer level, and the claim it can "
        "support is correspondingly narrower: that specific elements are irrecoverably "
        "absent from the index, not that their absence degrades end-to-end answer "
        "quality in a way Experiment 2 would have detected. Any writeup that omits this "
        "reconciliation will be rejected in review."
    )


def headline(text: str) -> str:
    """Format the single stdout line that carries an experiment's headline."""
    return f"HEADLINE: {text}"


def _section(title: str, body: str) -> str:
    return f"## {title}\n\n{body.strip()}\n"


def render_report(
    *,
    title: str,
    experiment: str,
    stamp: RunStamp,
    setup: str,
    method: str,
    numbers: str,
    gate: GateDecision | None = None,
    caveats: str = "",
    next_steps: str = "",
) -> str:
    """Assemble the standard six-section report."""
    provenance = "\n".join(
        f"- `{k}`: {v}"
        for k, v in (
            ("experiment", stamp.experiment),
            ("script", stamp.script),
            ("git_commit", f"{stamp.git_commit}{' (DIRTY)' if stamp.git_dirty else ''}"),
            ("manifest_hash", stamp.manifest_hash),
            ("corpus_sha256", stamp.corpus_sha256 or "—"),
            ("timestamp_utc", stamp.timestamp_utc),
            ("llm_model", stamp.llm_model or "—"),
            ("nli_model", stamp.nli_model or "—"),
            ("graphrag", stamp.graphrag_version),
            ("python", stamp.python_version),
        )
    )

    parts = [f"# {title}", "", f"**Experiment:** {experiment}", "", "### Provenance", "", provenance, ""]
    parts.append(_section("Setup", setup))
    parts.append(_section("Method", method))
    parts.append(_section("Numbers", numbers))
    if gate is not None:
        parts.append(gate_banner(gate) + "\n")
    else:
        parts.append(_section("Gate decision", "Not applicable to this experiment."))

    caveat_body = (caveats.strip() + "\n\n" if caveats.strip() else "") + edge_et_al_caveat()
    parts.append(_section("Caveats", caveat_body))
    parts.append(_section("Next", next_steps or "—"))
    return "\n".join(parts)


def write_report(path: Path, **kwargs: object) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(**kwargs), encoding="utf-8")  # type: ignore[arg-type]
    return path

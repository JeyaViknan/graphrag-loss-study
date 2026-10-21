"""Shared helpers for the slide verification scripts.

Each slide script recomputes the numbers on one slide directly from the raw result
files of the census (paper/results/*.csv), using the same definitions as
paper/experiments/analyze.py, and prints them next to the values on the slide.

With --fresh, the experiments themselves are run again first, through GraphRAG
3.1.1's own indexing code, into a temporary folder, and the numbers are recomputed
from that fresh output instead. The saved results are never touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "paper" / "results"
EXPERIMENTS = ROOT / "paper" / "experiments"
MAIN = "rgi_f0.8_b0.12_m2"          # RGI with its default parameters f = 0.8, b = 0.12, m = 2

COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
GREEN, RED, DIM, BOLD, RESET = (("\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m") if COLOR else ("",) * 5)


def pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}"


def boot_mean(values: np.ndarray, B: int = 10000, seed: int = 20260815) -> tuple[float, float]:
    """95% bootstrap interval of the mean; same resampling and seed as analyze.py."""
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(B, len(values)))
    m = values[idx].mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def _run(cmd: list[str]) -> None:
    print(f"{DIM}$ {' '.join(str(c) for c in cmd)}{RESET}", flush=True)
    t0 = time.time()
    subprocess.run([str(c) for c in cmd], check=True, cwd=ROOT)
    print(f"{DIM}  finished in {time.time() - t0:.0f} s{RESET}\n", flush=True)


def results_dir(slide: int, title: str, runs: list[tuple[str, list[str]]]) -> Path:
    """Parse --fresh; when given, run the listed experiments into a temporary folder.

    runs: (subfolder, arguments for an experiment script) pairs, e.g.
          ("", ["census_rgi.py", "--no-ablations"]) or ("chunk600", ["census_rgi.py", "--chunk-size", "600"]).
    """
    ap = argparse.ArgumentParser(description=f"Verify the numbers on slide {slide}: {title}")
    ap.add_argument("--fresh", action="store_true",
                    help="re-run the experiments from the raw novels first (takes a few minutes; no LLM calls)")
    args = ap.parse_args()
    print(f"\n{BOLD}Slide {slide} · {title}{RESET}")
    if not args.fresh:
        return RESULTS
    out = Path(tempfile.mkdtemp(prefix=f"rgi_slide{slide}_"))
    print(f"Re-running the experiments into {out}\n")
    for sub, cmd in runs:
        script, rest = cmd[0], cmd[1:]
        _run([sys.executable, EXPERIMENTS / script, *rest, "--out", out / sub if sub else out])
    return out


def provenance(res: Path, files: list[str]) -> None:
    meta = json.loads((res / "census.json").read_text())
    where = "saved census run" if res == RESULTS else "fresh run, just now"
    print(f"Source: {res.relative_to(ROOT) if res.is_relative_to(ROOT) else res}  ({where})")
    print(f"GraphRAG {meta['graphrag']} · {meta['novels']} novels of GraphRAG-Bench Novel · "
          f"{meta['encoding']} tokens · budget B = {meta['budget']:,} · LLM calls: {meta['llm_calls']} · "
          f"census runtime {meta['runtime_s']:.0f} s")
    for f in files:
        p = res / f
        digest = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        rows = sum(1 for _ in p.open()) - 1 if p.suffix == ".csv" else None
        print(f"{DIM}  {f:<26} {'' if rows is None else f'{rows:>6,} rows'}   sha256 {digest}…{RESET}")


class Checks:
    """Collects (label, value on the slide, recomputed value) rows and prints them."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str, str]] = []

    def section(self, name: str, how: str = "") -> None:
        self.rows.append(("section", name, how, ""))

    def add(self, label: str, shown: str, computed: str) -> None:
        self.rows.append(("row", label, shown, computed))

    def claim(self, label: str, holds: bool, detail: str) -> None:
        """A statement on the slide that is checked as true or false rather than as a number."""
        self.rows.append(("claim", label, "holds" if holds else "FAILS", detail))

    def report(self) -> int:
        width = max(len(r[1]) for r in self.rows if r[0] != "section") + 2
        ok = bad = 0
        for kind, a, b, c in self.rows:
            if kind == "section":
                print(f"\n{BOLD}{a}{RESET}")
                if b:
                    print(f"{DIM}  {b}{RESET}")
                print(f"{DIM}  {'':<{width}}{'on slide':>12}{'recomputed':>13}{RESET}")
                continue
            if kind == "claim":
                holds = b == "holds"
                ok += holds
                bad += not holds
                mark = f"{GREEN}✓ holds{RESET}" if holds else f"{RED}✗ fails{RESET}"
                print(f"  {a:<{width}}{'':>12}{'':>13}   {mark}  {DIM}{c}{RESET}")
                continue
            match = b == c
            ok += match
            bad += not match
            mark = f"{GREEN}✓{RESET}" if match else f"{RED}✗ differs{RESET}"
            print(f"  {a:<{width}}{b:>12}{c:>13}   {mark}")
        total = ok + bad
        colour = GREEN if not bad else RED
        print(f"\n{colour}{BOLD}{ok} of {total} checks pass: "
              f"{'every' if not bad else 'not every'} number and claim on the slide matches the recomputed results.{RESET}\n")
        return 0 if not bad else 1

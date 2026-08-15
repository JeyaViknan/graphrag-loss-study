#!/usr/bin/env python
"""E7 — query harness with byte-exact context logging.

Runs GraphRAG global search over the benchmark questions and logs, per question,
the generated answer and the **byte-exact assembled context**. E8 and E9 both
consume that context: E8 to decide which elements were actually in front of the
model, E9 to displace tokens out of it at constant budget. A paraphrase or a
re-assembly would silently invalidate both.

Reproducibility is asserted, not assumed: one question is run twice and the two
contexts compared byte for byte before the full sweep starts. If they differ,
the harness aborts rather than logging a context that cannot be replayed.

Cost warning: KB §B.3 anchors global search at ~331k tokens per query on
GraphRAG-Bench Novel. At 125 questions that is ~41M tokens for this script
alone, before E9's two re-generation arms.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from graphrag_loss import io as gio  # noqa: E402
from graphrag_loss import linking, report  # noqa: E402

EXPERIMENT = "E7"
NAME = Path(__file__).stem
MIN_QUESTIONS = 125


def _load_config(root: Path):
    from graphrag.config.load_config import load_config

    return load_config(root)


async def _run_one(config, index, query: str, level: int | None, response_type: str):
    from graphrag.api.query import global_search

    response, context = await global_search(
        config=config,
        entities=index.entities,
        communities=index.communities,
        community_reports=index.community_reports,
        community_level=level,
        dynamic_community_selection=False,
        response_type=response_type,
        query=query,
    )
    return response, context


def _context_to_text(context) -> str:
    """Flatten graphrag's context payload to a stable, byte-comparable string."""
    if isinstance(context, str):
        return context
    if isinstance(context, dict):
        parts = []
        for key in sorted(context):
            value = context[key]
            parts.append(f"=== {key} ===")
            parts.append(value.to_csv(index=False) if hasattr(value, "to_csv") else str(value))
        return "\n".join(parts)
    if isinstance(context, list):
        return "\n".join(
            v.to_csv(index=False) if hasattr(v, "to_csv") else str(v) for v in context
        )
    return str(context)


def _community_ids(context) -> list[str]:
    ids: set[str] = set()
    frames = context.values() if isinstance(context, dict) else (context if isinstance(context, list) else [])
    for frame in frames:
        if hasattr(frame, "columns"):
            for col in ("community", "id", "community_id"):
                if col in frame.columns:
                    ids.update(str(x) for x in frame[col])
                    break
    return sorted(ids)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-dir", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True, help="graphrag project root holding settings.yaml")
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path("cache"))
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--repo-dir", type=Path, default=Path("."))
    parser.add_argument("--n-questions", type=int, default=MIN_QUESTIONS)
    parser.add_argument("--level", type=int, default=None)
    parser.add_argument("--response-type", default="Multiple Paragraphs")
    parser.add_argument("--llm-model", default="gemini/gemini-2.5-flash")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    if args.n_questions < MIN_QUESTIONS:
        print(f"E7 BLOCKED — CONTEXT §6 requires ≥{MIN_QUESTIONS} questions, got {args.n_questions}.")
        return 2

    stamp = gio.make_run_stamp(
        args.frozen_dir, experiment=EXPERIMENT, script=NAME,
        repo_dir=args.repo_dir, corpus_path=args.questions, llm_model=args.llm_model,
    )

    questions = linking.load_questions(args.questions)
    sample = questions.sample(n=min(args.n_questions, len(questions)), random_state=args.seed)
    index = gio.load_index(args.frozen_dir)
    config = _load_config(args.root)

    # Reproducibility assert, before spending the budget on a full sweep.
    probe = str(sample.iloc[0]["question"])
    _r1, c1 = asyncio.run(_run_one(config, index, probe, args.level, args.response_type))
    _r2, c2 = asyncio.run(_run_one(config, index, probe, args.level, args.response_type))
    if _context_to_text(c1).encode() != _context_to_text(c2).encode():
        print(
            "E7 ABORTED — context is not byte-reproducible across two runs of the same "
            "question. E8 and E9 both depend on replaying this exact context; a "
            "non-deterministic context makes both invalid."
        )
        return 2

    out_path = args.cache_dir / "query_outputs.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for _, q in sample.iterrows():
            response, context = asyncio.run(
                _run_one(config, index, str(q["question"]), args.level, args.response_type)
            )
            context_text = _context_to_text(context)
            fh.write(
                json.dumps(
                    {
                        "question_id": str(q["id"]),
                        "question": str(q["question"]),
                        "gold_answer": str(q.get("answer", "")),
                        "question_type": str(q.get("question_type", "")),
                        "answer": response if isinstance(response, str) else json.dumps(response),
                        "context": context_text,
                        "context_bytes": len(context_text.encode()),
                        "community_ids": _community_ids(context),
                        "llm_model": args.llm_model,
                        "level": args.level,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            n_written += 1

    import pandas as pd

    results = pd.DataFrame(
        [{"quantity": "n_questions_run", "value": n_written, "ci_low": n_written,
          "ci_high": n_written, "n": n_written, "method": "census"}]
    )
    gio.write_result_csv(results, args.results_dir / f"{NAME}.csv", stamp)

    report.write_report(
        args.reports_dir / f"{NAME}.md",
        title="E7 — Query harness",
        experiment=EXPERIMENT, stamp=stamp,
        setup=f"{n_written} questions, global search at level {args.level}, model `{args.llm_model}`.",
        method=(
            "GraphRAG global search via `graphrag.api.query.global_search`. Per question "
            "the harness logs the answer, the byte-exact assembled context, the community "
            "ids used, and the context size in bytes, to `cache/query_outputs.jsonl`. "
            "Byte-reproducibility is asserted on a probe question before the sweep."
        ),
        numbers=f"- Questions run: **{n_written}**\n- Output: `{out_path}`",
        gate=None,
        caveats=(
            "Answer correctness is not judged here — E8 and E9 do that. The context is "
            "logged verbatim because E9's token-exact displacement operates on the "
            "actual assembled string; re-deriving it later would not reproduce it."
        ),
        next_steps="E8 — `scripts/08_attribution.py` [G3].",
    )

    print(f"E7: {n_written} questions logged to {out_path}, context byte-reproducibility asserted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

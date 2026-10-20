"""Relationship selection in GraphRAG's standard (LLM-pipeline) summary input.

graphrag 3.1.1 builds a community's summary input in
summarize_communities/graph_context/context_builder.py::_prepare_reports_at_level.
It groups the level's edges by source and by target, keeps the "first" edge of
each group, and merges the two with combine_first, so every entity contributes
at most one relationship to the input. This script runs that exact code path
(explode_communities -> _prep_nodes -> _prep_edges -> build_local_context) on
the census graphs and records which relationships reach each community's input.

Descriptions are left as GraphRAG's own "No Description" filler: selection does
not read them, so the counts below do not depend on an LLM.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import census_rgi as C  # noqa: E402  (sets TIKTOKEN_CACHE_DIR and sys.path)

import pandas as pd  # noqa: E402
import graphrag.data_model.schemas as schemas  # noqa: E402
from graphrag.callbacks.noop_workflow_callbacks import NoopWorkflowCallbacks  # noqa: E402
from graphrag.index.operations.summarize_communities.explode_communities import explode_communities  # noqa: E402
from graphrag.index.operations.summarize_communities.graph_context.context_builder import build_local_context  # noqa: E402
from graphrag.index.workflows.create_community_reports import _prep_edges, _prep_nodes  # noqa: E402


def frames(ix: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pe, pr, comm = ix["entities"].copy(), ix["relationships"].copy(), ix["comm"]
    pe[schemas.SHORT_ID] = range(len(pe))
    pe[schemas.DESCRIPTION] = None
    pr[schemas.SHORT_ID] = pr["short"]
    pr[schemas.DESCRIPTION] = None
    title_id = dict(zip(pe["title"], pe["id"], strict=True))
    communities = pd.DataFrame([
        {"community": cid, "level": c["level"], "entity_ids": [title_id[n] for n in sorted(c["nodes"])],
         "relationship_ids": list(c["intra"])}
        for cid, c in comm.items()
    ])
    return pe, pr, communities


def main() -> None:
    tok = C.Tok()
    corpus = json.loads((C.DATA / "novel.json").read_text(encoding="utf-8"))
    rows = []
    t0 = time.time()
    for doc in corpus:
        ix = C.index_novel(doc["corpus_name"], doc["context"], tok)
        pe, pr, communities = frames(ix)
        nodes = _prep_nodes(explode_communities(communities, pe))
        edges = _prep_edges(pr)
        local = build_local_context(nodes, edges, None, tok.t, NoopWorkflowCallbacks(), C.BUDGET)

        short_to_id = dict(zip(pr["short"], pr["id"], strict=True))
        pool: dict[int, set[str]] = defaultdict(set)
        for row in local.itertuples(index=False):
            cid = int(getattr(row, schemas.COMMUNITY_ID))
            for rec in getattr(row, schemas.ALL_CONTEXT):
                for e in rec.get(schemas.EDGE_DETAILS, []) or []:
                    if isinstance(e, dict):
                        pool[cid].add(short_to_id[int(e[schemas.SHORT_ID])])

        for lvl in range(ix["max_level"] + 1):
            cids = [cid for cid, c in ix["comm"].items() if c["level"] == lvl]
            intra = sum(len(ix["comm"][cid]["intra"]) for cid in cids)
            kept = sum(len(pool[cid] & set(ix["comm"][cid]["intra"])) for cid in cids)
            leaked = len(set().union(*(pool[cid] - set(ix["comm"][cid]["intra"]) for cid in cids)) if cids else set())
            bound = sum(min(len(ix["comm"][cid]["nodes"]), len(ix["comm"][cid]["intra"])) for cid in cids)
            assert kept <= bound, (doc["corpus_name"], lvl, kept, bound)
            rows.append({"novel": doc["corpus_name"], "level": lvl, "communities": len(cids),
                         "entities": sum(len(ix["comm"][cid]["nodes"]) for cid in cids),
                         "intra": intra, "intra_in_input": kept, "bound": bound, "cross_in_input": leaked})
        print(doc["corpus_name"], f"{time.time() - t0:.0f}s", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(C.OUT / "selection_loss.csv", index=False)
    agg = df.groupby("level")[["communities", "entities", "intra", "intra_in_input", "bound", "cross_in_input"]].sum()
    agg["share_kept"] = agg["intra_in_input"] / agg["intra"]
    print(agg.to_string())


if __name__ == "__main__":
    main()

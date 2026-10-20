"""Index-time loss census and Residual Graph Indexing on GraphRAG-Bench Novel.

Each of the 20 novels is indexed separately with the GraphRAG 3.1.1 "fast"
pipeline at its shipped defaults. Every stage except noun-phrase extraction
calls GraphRAG's own code:

  chunking            graphrag_chunking TokenChunker (1200 tokens, 100 overlap, o200k_base)
  extraction          ProperNounExtractor below (GraphRAG's default extractor needs NLTK
                      data that could not be fetched on this machine)
  edges               graphrag _extract_edges: per-text-unit co-occurrence, PMI weights
  pruning             graphrag prune_graph with PruneGraphDefaults
  communities         graphrag cluster_graph (hierarchical Leiden, ClusterGraphDefaults)
  summary input       GraphRAG's text-unit context: degree-sorted passages rendered by
                      get_context_string and cut at the first one that overflows 8,000 tokens
  level selection     GraphRAG's global-search roll-up (deepest community at level <= l)

No LLM is called anywhere. Output: paper/results/*.csv and census.json.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import platform
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(ROOT / ".cache" / "tiktoken"))
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402
import graphrag  # noqa: E402
import tiktoken  # noqa: E402
from graphrag.config.defaults import (  # noqa: E402
    ChunkingDefaults,
    ClusterGraphDefaults,
    CommunityReportDefaults,
    PruneGraphDefaults,
)
from graphrag.index.operations.build_noun_graph.build_noun_graph import _extract_edges  # noqa: E402
from graphrag.index.operations.build_noun_graph.np_extractors.stop_words import EN_STOP_WORDS  # noqa: E402
from graphrag.index.operations.cluster_graph import cluster_graph  # noqa: E402
from graphrag.index.operations.prune_graph import prune_graph  # noqa: E402
from graphrag.index.operations.summarize_communities.text_unit_context.sort_context import (  # noqa: E402
    get_context_string,
    sort_context,
)
from graphrag_chunking.chunker_factory import create_chunker  # noqa: E402
from graphrag_chunking.chunking_config import ChunkingConfig  # noqa: E402
from graphrag_llm.tokenizer.tiktoken_tokenizer import TiktokenTokenizer  # noqa: E402

from graphrag_loss.linking import LinkConfig, link_triple, parse_triple  # noqa: E402

DATA = ROOT / "data" / "graphrag_bench"
OUT = ROOT / "paper" / "results"

CHUNK = ChunkingDefaults()
PRUNE = PruneGraphDefaults()
CLUSTER = ClusterGraphDefaults()
BUDGET = CommunityReportDefaults().max_input_length  # 8000


# ---------------------------------------------------------------- extraction
class ProperNounExtractor:
    """Deterministic proper-noun phrase extractor.

    Stands in for GraphRAG's default TextBlob extractor, keeping its output
    contract: upper-cased phrases, tokens filtered by EN_STOP_WORDS, tokens
    restricted to [A-Za-z0-9-] and at most 15 characters. A capitalised word
    that also occurs in lower case somewhere in the same novel is treated as
    an ordinary word ("The", "Well", "Then"), so it cannot stand alone as an
    entity and is trimmed from the start of a sentence-initial phrase.
    """

    ABBR = re.compile(r"\b(Mr|Mrs|Ms|Messrs|Dr|St|Mme|Mlle|Mons|Col|Capt|Gen|Lieut|Lt|Rev|Prof|Sr|Jr|Hon|Esq)\.")
    SENT = re.compile(r"(?<=[.!?;:])[\"'’”)\]]*\s+|\n\s*\n")
    WORD = re.compile(r"[A-Za-z][A-Za-z0-9'’\-]*")
    LOWER = re.compile(r"\b[a-z][a-z'’\-]*\b")
    VALID = re.compile(r"^[a-zA-Z0-9\-]+$")
    ROMAN = re.compile(r"^[IVXLCDM]+$")
    POSSESSIVE = re.compile(r"['’]s$")
    CONNECT = frozenset({"of", "de", "du", "la", "le", "van", "von", "di", "da", "del"})
    HEADINGS = frozenset({"CHAPTER", "BOOK", "PART", "VOLUME", "CONTENTS", "PREFACE", "END", "FINIS"})

    def __init__(self, novel_text: str, max_word_length: int = 15, exclude: list[str] = EN_STOP_WORDS):
        self.lower_vocab = {w.replace("’", "'") for w in self.LOWER.findall(novel_text)}
        self.exclude = {w.upper() for w in exclude}
        self.max_word_length = max_word_length

    def __str__(self) -> str:
        return f"proper_noun_v1_{self.max_word_length}"

    def _common(self, w: str) -> bool:
        return w.lower().replace("’", "'") in self.lower_vocab

    def _phrase(self, words: list[str], sentence_initial: bool) -> str | None:
        words = [self.POSSESSIVE.sub("", w) for w in words]
        if sentence_initial and words and self._common(words[0]):
            words = words[1:]
        while words and words[0].lower() in self.CONNECT:
            words.pop(0)
        while words and words[-1].lower() in self.CONNECT:
            words.pop()
        if not words or (len(words) == 1 and self._common(words[0])):
            return None
        tokens = [w for w in words if w.upper() not in self.exclude]
        if not tokens:
            return None
        if not all(self.VALID.match(t) and len(t) <= self.max_word_length for t in tokens):
            return None
        if all(t.upper() in self.HEADINGS or self.ROMAN.match(t.upper()) for t in tokens):
            return None
        phrase = " ".join(tokens).upper()
        return phrase if len(phrase) >= 2 else None

    def extract(self, text: str) -> list[str]:
        text = self.ABBR.sub(r"\1", text)
        found: set[str] = set()
        for sent in self.SENT.split(text):
            toks = [(m.group(), m.start(), m.end()) for m in self.WORD.finditer(sent)]
            run: list[int] = []

            def flush() -> None:
                if run:
                    p = self._phrase([toks[i][0] for i in run], sentence_initial=run[0] == 0)
                    if p:
                        found.add(p)

            for k, (w, s, e) in enumerate(toks):
                adjacent = k > 0 and sent[toks[k - 1][2]:s].strip() == ""
                if w[0].isupper():
                    if run and adjacent:
                        run.append(k)
                    else:
                        flush()
                        run = [k]
                elif (w in self.CONNECT and run and adjacent and k + 1 < len(toks)
                      and toks[k + 1][0][0].isupper() and sent[e:toks[k + 1][1]].strip() == ""):
                    run.append(k)
                else:
                    flush()
                    run = []
            flush()
        return sorted(found)


# ---------------------------------------------------------------- tokens
class Tok:
    def __init__(self) -> None:
        self.t = TiktokenTokenizer(encoding_name=CHUNK.encoding_model)
        self.enc = tiktoken.get_encoding(CHUNK.encoding_model)

    def n(self, s: str) -> int:
        return len(self.enc.encode(s, disallowed_special=()))


# ---------------------------------------------------------------- indexing
def index_novel(name: str, text: str, tok: Tok, chunk_size: int = CHUNK.size) -> dict:
    chunker = create_chunker(
        ChunkingConfig(type=CHUNK.type, size=chunk_size, overlap=CHUNK.overlap, encoding_model=CHUNK.encoding_model),
        tok.t.encode, tok.t.decode,
    )
    chunks = [c.text for c in chunker.chunk(text)]
    tu_ids = [f"tu{i}" for i in range(len(chunks))]
    tu_text = dict(zip(tu_ids, chunks, strict=True))
    tu_short = {t: i for i, t in enumerate(tu_ids)}

    ex = ProperNounExtractor(text)
    title_to_ids: dict[str, list[str]] = defaultdict(list)
    for tid, chunk in zip(tu_ids, chunks, strict=True):
        for phrase in ex.extract(chunk):
            title_to_ids[phrase].append(tid)
    title_to_ids = dict(title_to_ids)
    nodes = pd.DataFrame(
        [{"title": t, "frequency": len(ids), "text_unit_ids": ids} for t, ids in title_to_ids.items()],
        columns=["title", "frequency", "text_unit_ids"],
    )
    edges = _extract_edges(title_to_ids, nodes_df=nodes, normalize_edge_weights=True)

    raw_deg = Counter(edges["source"]) + Counter(edges["target"])
    ego = max(raw_deg, key=lambda t: raw_deg[t]) if raw_deg else None

    entities = nodes.assign(type="NOUN PHRASE", description="")
    rels = edges.assign(description="")
    pe, pr = prune_graph(entities, rels, **dataclasses.asdict(PRUNE))
    pr = pr.reset_index(drop=True)
    pe = pe.reset_index(drop=True)
    pr["id"] = [f"r{i}" for i in range(len(pr))]
    pr["short"] = range(len(pr))
    deg = Counter(pr["source"]) + Counter(pr["target"])
    pr["combined_degree"] = [deg[s] + deg[t] for s, t in zip(pr["source"], pr["target"], strict=True)]
    pr["n_units"] = pr["text_unit_ids"].map(len)
    pe["id"] = [f"e{i}" for i in range(len(pe))]
    pe["degree"] = pe["title"].map(lambda t: deg.get(t, 0))

    clusters = cluster_graph(pr[["source", "target", "weight"]], CLUSTER.max_cluster_size, CLUSTER.use_lcc, seed=CLUSTER.seed)
    comm = {}
    for level, cid, parent, members in clusters:
        comm[int(cid)] = {"level": int(level), "parent": int(parent), "nodes": set(members)}
    children: dict[int, list[int]] = defaultdict(list)
    for cid, c in comm.items():
        if c["parent"] != -1:
            children[c["parent"]].append(cid)
    max_level = max(c["level"] for c in comm.values())

    # intra-community relationships and their text units, exactly as create_communities aggregates them
    rel_units = dict(zip(pr["id"], pr["text_unit_ids"].map(set), strict=True))
    for lvl in range(max_level + 1):
        at = {n: cid for cid, c in comm.items() if c["level"] == lvl for n in c["nodes"]}
        for rid, s, t in zip(pr["id"], pr["source"], pr["target"], strict=True):
            cs, ct = at.get(s), at.get(t)
            if cs is not None and cs == ct:
                comm[cs].setdefault("intra", []).append(rid)
    node_units = dict(zip(pe["title"], pe["text_unit_ids"].map(set), strict=True))
    for cid, c in comm.items():
        c.setdefault("intra", [])
        units = set()
        for rid in c["intra"]:
            units |= rel_units[rid]
        # prep_text_units: a passage's priority is the summed degree of this community's entities in it
        recs = []
        for u in sorted(units, key=tu_short.get):
            d = sum(deg.get(n, 0) for n in c["nodes"] if u in node_units.get(n, ()))
            recs.append({"id": tu_short[u], "text": tu_text[u], "entity_degree": d, "_tu": u})
        recs.sort(key=lambda r: r["entity_degree"], reverse=True)  # stable, as in sort_context
        c["records"] = recs
        c["children"] = children.get(cid, [])

    # global-search roll-up: each entity reads the report of its max-id community at level <= l
    rollup = {}
    for lvl in range(max_level + 1):
        best: dict[str, int] = {}
        for cid, c in comm.items():
            if c["level"] <= lvl:
                for n in c["nodes"]:
                    if n not in best or cid > best[n]:
                        best[n] = cid
        rollup[lvl] = best
        # the max-id rule must coincide with "deepest community": verify instead of assuming
        for n, cid in best.items():
            deeper = [k for k, c in comm.items() if n in c["nodes"] and c["level"] <= lvl]
            assert comm[cid]["level"] == max(comm[k]["level"] for k in deeper), (name, n)

    return {
        "name": name, "chunks": len(chunks), "chunk_tokens": [tok.n(c) for c in chunks],
        "raw_entities": len(nodes), "raw_relationships": len(edges), "ego": ego,
        "entities": pe, "relationships": pr, "comm": comm, "max_level": max_level,
        "rollup": rollup, "rel_units": rel_units,
    }


# ---------------------------------------------------------------- summary inputs
class Contexts:
    """Exact token accounting for GraphRAG's text-unit summary input of one community."""

    def __init__(self, tok: Tok):
        self.tok = tok
        self.cache: dict[tuple, int] = {}

    def tokens(self, key: tuple, records: list[dict], k: int) -> int:
        ck = key + (k,)
        if ck not in self.cache:
            self.cache[ck] = self.tok.n(get_context_string([_strip(r) for r in records[:k]]))
        return self.cache[ck]

    def admit(self, key: tuple, records: list[dict], budget: int) -> int:
        """Number of leading passages GraphRAG keeps: it stops at the first that overflows."""
        n = len(records)
        if n == 0:
            return 0
        if self.tokens(key, records, n) <= budget:
            return n
        lo, hi = 0, n  # tokens(lo) <= budget < tokens(hi); tokens(0) is treated as 0
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.tokens(key, records, mid) <= budget:
                lo = mid
            else:
                hi = mid
        assert lo > 0, "a single passage exceeds the budget; GraphRAG would then keep everything"
        return lo


def _strip(r: dict) -> dict:
    return {"id": r["id"], "text": r["text"], "entity_degree": r["entity_degree"]}


def line(src: str, tgt: str, k: int) -> str:
    return f"{src},{tgt},{k}"


FACTS_HDR = "\n\n-----FACTS-----\nsource,target,shared_passages\n"
BRIDGE_HDR = "\n\n-----CONNECTIONS-----\nsource,target,shared_passages\n"


@dataclasses.dataclass(frozen=True)
class RGIConfig:
    full_cut: float = 0.8
    bridge_share: float = 0.12
    bridge_min_units: int = 2

    def tag(self) -> str:
        return f"f{self.full_cut:g}_b{self.bridge_share:g}_m{self.bridge_min_units}"


def exposure(ix: dict, sel: dict, admitted: dict[int, set[str]], explicit: set[str]) -> dict[str, str]:
    """Strongest form in which each relationship's evidence reaches a selected summary input.

    scope:    an explicit record or a supporting passage in its own community's input
    endpoint: a supporting passage sits in the input of a community holding one endpoint
    elsewhere: a supporting passage sits only in inputs of communities holding neither endpoint
    absent:   no record and no supporting passage in any selected input
    """
    every = set().union(*admitted.values()) if admitted else set()
    out = {}
    for rid, src, tgt in zip(ix["relationships"]["id"], ix["relationships"]["source"], ix["relationships"]["target"], strict=True):
        if rid in explicit:
            out[rid] = "scope"
            continue
        units = ix["rel_units"][rid]
        cs, ct = sel.get(src), sel.get(tgt)
        near = admitted.get(cs, set()) | admitted.get(ct, set())
        out[rid] = "endpoint" if units & near else "elsewhere" if units & every else "absent"
    return out


def evaluate_level(ix: dict, lvl: int, budget: int, rgi: RGIConfig | None, ctx: Contexts, tok: Tok) -> dict:
    """Status of every relationship at operating level ``lvl`` under GraphRAG, or under RGI when ``rgi`` is set."""
    pr, comm, rel_units = ix["relationships"], ix["comm"], ix["rel_units"]
    sel = ix["rollup"][min(lvl, ix["max_level"])]
    selected = sorted(set(sel.values()))
    rid_rows = {r.id: r for r in pr.itertuples(index=False)}
    prio = {r.id: (-r.combined_degree, r.short) for r in pr.itertuples(index=False)}

    # 1. GraphRAG's own summary input for every selected community
    base = {}
    for cid in selected:
        c = comm[cid]
        recs, key = c["records"], (ix["name"], cid)
        if not recs:
            base[cid] = ("fits", 0, 0)
            continue
        full = ctx.tokens(key, recs, len(recs))
        if full <= budget:
            base[cid] = ("fits", len(recs), full)
        elif not c["children"]:
            k = ctx.admit(key, recs, budget)
            base[cid] = ("trimmed", k, ctx.tokens(key, recs, k))
        else:
            base[cid] = ("second_order", 0, budget)  # built from sub-community reports

    def covered_by(cid: int, k: int) -> set[str]:
        units = {r["_tu"] for r in comm[cid]["records"][:k]}
        return {rid for rid in comm[cid]["intra"] if rel_units[rid] & units}

    status: dict[str, str] = {}
    boundary_of: dict[int, list[str]] = defaultdict(list)
    for rid, s, t in zip(pr["id"], pr["source"], pr["target"], strict=True):
        cs, ct = sel.get(s), sel.get(t)
        if cs is None or ct is None:
            status[rid] = "outside"
        elif cs != ct:
            status[rid] = "boundary"
            boundary_of[cs].append(rid)
            boundary_of[ct].append(rid)
        else:
            mode = base[cs][0]
            status[rid] = {"fits": "covered", "trimmed": None, "second_order": "indirect"}[mode]
    for cid in selected:
        mode, k, _ = base[cid]
        if mode == "trimmed":
            keep = covered_by(cid, k)
            for rid in comm[cid]["intra"]:
                status[rid] = "covered" if rid in keep else "budget"

    inputs = {cid: {"mode": base[cid][0], "tokens": base[cid][2], "passages": base[cid][1]} for cid in selected}
    admitted = {cid: {r["_tu"] for r in comm[cid]["records"][:base[cid][1]]} for cid in selected}
    if rgi is None:
        expo = exposure(ix, sel, admitted, {rid for rid, st in status.items() if st == "covered"})
        return {"status": status, "inputs": inputs, "selected": selected, "exposure": expo}

    # 2. RGI: same passages, then bridge records and compact facts inside the same budget
    rstatus = dict(status)
    how: dict[str, str] = {rid: "passage" for rid, s in status.items() if s == "covered"}
    fallback = 0
    rinputs = {}
    radmitted: dict[int, set[str]] = {}
    bridged: set[str] = set()
    for cid in selected:
        c, (mode, k_base, base_tokens) = comm[cid], base[cid]
        recs, key = c["records"], (ix["name"], cid)
        facts: list[str] = []
        if mode == "fits":
            k, used = k_base, base_tokens
            pending: list[str] = []
        elif mode == "trimmed":
            k = ctx.admit(key, recs, int(budget * rgi.full_cut)) if rgi.full_cut < 1 else k_base
            k = min(k, k_base)
            used = ctx.tokens(key, recs, k)
            have = covered_by(cid, k)
            base_cov = covered_by(cid, k_base)
            reserved = sorted(base_cov - have, key=prio.get)  # monotonicity: what GraphRAG kept comes first
            rest = sorted(set(c["intra"]) - base_cov, key=prio.get)
            cost = (tok.n(FACTS_HDR) if reserved else 0) + sum(tok.n(line(rid_rows[r].source, rid_rows[r].target, rid_rows[r].n_units)) + 1 for r in reserved)
            if used + cost > budget:
                fallback += 1
                k, used, reserved = k_base, base_tokens, []
                have = base_cov
            for r in reserved:
                facts.append(r)
            pending = rest
        else:  # second_order: sub-community reports fill full_cut * budget, the tail is ours
            k, used = 0, int(budget * rgi.full_cut)
            pending = sorted(c["intra"], key=prio.get)

        def fits(extra_lines: list[str], hdr_needed: bool, cur: int) -> int:
            return cur + (tok.n(FACTS_HDR) if hdr_needed else 0) + sum(tok.n(x) + 1 for x in extra_lines)

        used_f = fits([line(rid_rows[r].source, rid_rows[r].target, rid_rows[r].n_units) for r in facts], bool(facts), used)

        # bridge records: boundary relationships of this community, GraphRAG's edge priority
        bridges: list[str] = []
        allowance = min(budget * rgi.bridge_share, budget - used_f)
        spent = 0
        if allowance > 0:
            cands = sorted((r for r in boundary_of.get(cid, []) if rid_rows[r].n_units >= rgi.bridge_min_units), key=prio.get)
            hdr = tok.n(BRIDGE_HDR)
            for r in cands:
                cost = tok.n(line(rid_rows[r].source, rid_rows[r].target, rid_rows[r].n_units)) + 1 + (0 if bridges else hdr)
                if spent + cost > allowance:
                    break
                bridges.append(r)
                spent += cost
        used_b = used_f + spent

        # compact facts for what is still missing, in priority order, up to the budget
        if mode != "fits":
            hdr_cost = 0 if facts else tok.n(FACTS_HDR)
            for r in pending:
                cost = tok.n(line(rid_rows[r].source, rid_rows[r].target, rid_rows[r].n_units)) + 1 + hdr_cost
                if used_b + cost > budget:
                    break
                facts.append(r)
                used_b += cost
                hdr_cost = 0

        # exact check of the rendered input; drop trailing facts if BPE merges pushed it over
        def render() -> str:
            body = get_context_string([_strip(r) for r in recs[:k]]) if k else ""
            if bridges:
                body += BRIDGE_HDR + "\n".join(line(rid_rows[r].source, rid_rows[r].target, rid_rows[r].n_units) for r in bridges)
            if facts:
                body += FACTS_HDR + "\n".join(line(rid_rows[r].source, rid_rows[r].target, rid_rows[r].n_units) for r in facts)
            return body

        sub = int(budget * rgi.full_cut) if mode == "second_order" else 0
        total = tok.n(render()) + sub
        while total > budget and facts:
            facts.pop()
            total = tok.n(render()) + sub
        assert total <= budget, (ix["name"], cid, total)

        have = covered_by(cid, k) if mode != "second_order" else set()
        for rid in c["intra"]:
            if rid in have:
                rstatus[rid], how[rid] = "covered", "passage"
        for rid in facts:
            rstatus[rid], how[rid] = "covered", "compact"
        bridged.update(bridges)
        rinputs[cid] = {"mode": mode, "tokens": total, "passages": k, "facts": len(facts), "bridges": len(bridges)}
        radmitted[cid] = {r["_tu"] for r in recs[:k]}

    for rid in bridged:
        if rstatus[rid] == "boundary":
            rstatus[rid], how[rid] = "covered", "bridge"

    # residual store: everything the summaries still do not carry, keyed by the communities it touches
    residual = {rid for rid, s in rstatus.items() if s != "covered"}
    certificate = (set(how) | residual) == set(pr["id"]) and not (set(how) & residual)
    regressions = sum(1 for rid, s in status.items() if s == "covered" and rstatus[rid] != "covered")
    expo = exposure(ix, sel, radmitted, {rid for rid, st in rstatus.items() if st == "covered"})
    base_expo = exposure(ix, sel, admitted, {rid for rid, st in status.items() if st == "covered"})
    rank = {"scope": 3, "endpoint": 2, "elsewhere": 1, "absent": 0}
    expo_regressions = sum(1 for rid in expo if rank[expo[rid]] < rank[base_expo[rid]])
    return {"status": rstatus, "how": how, "inputs": rinputs, "selected": selected, "fallback": fallback,
            "certificate": certificate, "regressions": regressions, "residual": len(residual),
            "exposure": expo, "exposure_regressions": expo_regressions}


# ---------------------------------------------------------------- gold evidence
def link_gold(ix: dict, questions: list[dict]) -> list[dict]:
    cfg = LinkConfig()
    ents = ix["entities"][["id", "title"]]
    rels = ix["relationships"][["id", "source", "target"]]
    rows = []
    for q in questions:
        for j, raw in enumerate(q.get("evidence_triple") or []):
            tr = parse_triple(raw)
            if tr is None:
                rows.append({"qid": q["id"], "j": j, "parsed": False, "linked": False, "score": 0.0, "rel_ids": []})
                continue
            eids, rids, score = link_triple(tr, ents, rels, cfg)
            rows.append({"qid": q["id"], "j": j, "parsed": True, "linked": score >= cfg.threshold and len(eids) >= 1,
                         "two_entities": len(eids) == 2, "score": score, "rel_ids": sorted(rids)})
    return rows


# ---------------------------------------------------------------- driver
LEVELS = [0, 1, 2, 3]
BUDGETS = [4000, 8000, 16000, 32000]
MAIN = RGIConfig()
ABLATIONS = (
    [RGIConfig(bridge_share=b) for b in (0.0, 0.06, 0.24)]
    + [RGIConfig(full_cut=f) for f in (0.6, 1.0)]
    + [RGIConfig(bridge_min_units=m) for m in (1, 3)]
)


def summarize(ix: dict, lvl: int, budget: int, method: str, res: dict) -> dict:
    st = Counter(res["status"].values())
    how = Counter(res.get("how", {}).values()) if "how" in res else Counter()
    modes = Counter(v["mode"] for v in res["inputs"].values())
    toks = [v["tokens"] for v in res["inputs"].values()]
    return {
        "novel": ix["name"], "level": lvl, "budget": budget, "method": method,
        "relationships": len(res["status"]), "covered": st["covered"], "boundary": st["boundary"],
        "budget_lost": st["budget"], "indirect": st["indirect"], "outside": st["outside"],
        "via_passage": how.get("passage", st["covered"] if method == "graphrag" else 0),
        "via_compact": how.get("compact", 0), "via_bridge": how.get("bridge", 0),
        "communities": len(res["selected"]), "fits": modes["fits"], "trimmed": modes["trimmed"],
        "second_order": modes["second_order"], "max_tokens": max(toks) if toks else 0,
        "mean_tokens": sum(toks) / len(toks) if toks else 0,
        "passages": sum(v["passages"] for v in res["inputs"].values()),
        "facts": sum(v.get("facts", 0) for v in res["inputs"].values()),
        "bridges": sum(v.get("bridges", 0) for v in res["inputs"].values()),
        "fallback": res.get("fallback", 0), "regressions": res.get("regressions", 0),
        "expo_scope": Counter(res["exposure"].values())["scope"], "expo_endpoint": Counter(res["exposure"].values())["endpoint"],
        "expo_elsewhere": Counter(res["exposure"].values())["elsewhere"], "expo_absent": Counter(res["exposure"].values())["absent"],
        "expo_regressions": res.get("exposure_regressions", 0),
        "certificate": res.get("certificate", None), "residual": res.get("residual", None),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--novels", type=int, default=None, help="limit for a smoke run")
    ap.add_argument("--chunk-size", type=int, default=CHUNK.size, help="sensitivity runs only; the default is GraphRAG's")
    ap.add_argument("--no-ablations", action="store_true")
    args = ap.parse_args()
    out = OUT if args.chunk_size == CHUNK.size else OUT / f"chunk{args.chunk_size}"
    t0 = time.time()
    tok = Tok()
    ctx = Contexts(tok)
    corpus = json.loads((DATA / "novel.json").read_text(encoding="utf-8"))
    questions = json.loads((DATA / "novel_questions.json").read_text(encoding="utf-8"))
    by_src = defaultdict(list)
    for q in questions:
        by_src[q["source"]].append(q)
    if args.novels:
        corpus = corpus[: args.novels]

    graph_rows, level_rows, triple_rows, qrows = [], [], [], []
    verified = 0
    for doc in corpus:
        name, text = doc["corpus_name"], doc["context"]
        ts = time.time()
        ix = index_novel(name, text, tok, args.chunk_size)

        # the binary-search admission must equal GraphRAG's own sort_context on real communities
        for cid, c in list(ix["comm"].items())[:12]:
            recs = c["records"]
            if not recs or ctx.tokens((name, cid), recs, len(recs)) <= BUDGET:
                continue
            k = ctx.admit((name, cid), recs, BUDGET)
            mine = get_context_string([_strip(r) for r in recs[:k]])
            theirs = sort_context([_strip(r) for r in recs], tok.t, max_context_tokens=BUDGET)
            assert mine == theirs, (name, cid)
            verified += 1

        pe, pr, comm = ix["entities"], ix["relationships"], ix["comm"]
        lvl_counts = Counter(c["level"] for c in comm.values())
        in_comm = set().union(*(c["nodes"] for c in comm.values()))
        graph_rows.append({
            "novel": name, "chars": len(text), "text_units": ix["chunks"], "tokens": sum(ix["chunk_tokens"]),
            "raw_entities": ix["raw_entities"], "raw_relationships": ix["raw_relationships"],
            "entities": len(pe), "relationships": len(pr), "ego_removed": ix["ego"],
            "mean_degree": 2 * len(pr) / max(1, len(pe)), "in_communities": len(in_comm),
            "max_level": ix["max_level"], **{f"communities_l{lv}": lvl_counts.get(lv, 0) for lv in range(5)},
        })

        gold = link_gold(ix, by_src[name])
        for g in gold:
            g["novel"] = name
        triple_rows.extend({k: v for k, v in g.items() if k != "rel_ids"} | {"n_rel": len(g["rel_ids"])} for g in gold)
        gold_rel = defaultdict(set)
        for g in gold:
            gold_rel[g["qid"]].update(g["rel_ids"])

        for lvl in LEVELS:
            for budget in BUDGETS:
                base = evaluate_level(ix, lvl, budget, None, ctx, tok)
                level_rows.append(summarize(ix, lvl, budget, "graphrag", base))
                main = evaluate_level(ix, lvl, budget, MAIN, ctx, tok)
                level_rows.append(summarize(ix, lvl, budget, "rgi_" + MAIN.tag(), main))
                assert main["certificate"], (name, lvl, budget)
                if budget == BUDGET:
                    for q in by_src[name]:
                        ys = gold_rel.get(q["id"], set())
                        if not ys:
                            continue
                        qrows.append({
                            "qid": q["id"], "novel": name, "type": q["question_type"], "level": lvl,
                            "n_gold": len(ys),
                            "base_covered": sum(base["status"][r] == "covered" for r in ys),
                            "rgi_covered": sum(main["status"][r] == "covered" for r in ys),
                            "base_boundary": sum(base["status"][r] == "boundary" for r in ys),
                            "base_budget": sum(base["status"][r] == "budget" for r in ys),
                            "base_indirect": sum(base["status"][r] == "indirect" for r in ys),
                            "base_outside": sum(base["status"][r] == "outside" for r in ys),
                            "base_endpoint": sum(base["exposure"][r] in ("scope", "endpoint") for r in ys),
                            "rgi_endpoint": sum(main["exposure"][r] in ("scope", "endpoint") for r in ys),
                            "base_any": sum(base["exposure"][r] != "absent" for r in ys),
                            "rgi_any": sum(main["exposure"][r] != "absent" for r in ys),
                        })
                    for cfg in ([] if args.no_ablations else ABLATIONS):
                        res = evaluate_level(ix, lvl, budget, cfg, ctx, tok)
                        assert res["certificate"], (name, lvl, cfg)
                        level_rows.append(summarize(ix, lvl, budget, "rgi_" + cfg.tag(), res))
        print(f"{name}: {ix['chunks']} units, {len(pe)} entities, {len(pr)} relationships, "
              f"levels 0-{ix['max_level']}, {len(comm)} communities, {time.time() - ts:.1f}s", flush=True)

    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(graph_rows).to_csv(out / "graph_stats.csv", index=False)
    pd.DataFrame(level_rows).to_csv(out / "level_census.csv", index=False)
    pd.DataFrame(triple_rows).to_csv(out / "gold_triples.csv", index=False)
    pd.DataFrame(qrows).to_csv(out / "gold_questions.csv", index=False)
    meta = {
        "graphrag": graphrag.__version__ if hasattr(graphrag, "__version__") else "3.1.1",
        "tiktoken": tiktoken.__version__, "pandas": pd.__version__, "python": platform.python_version(),
        "encoding": CHUNK.encoding_model, "chunk_size": args.chunk_size, "chunk_overlap": CHUNK.overlap,
        "prune": dataclasses.asdict(PRUNE), "cluster": dataclasses.asdict(CLUSTER), "budget": BUDGET,
        "rgi_main": dataclasses.asdict(MAIN), "ablations": [dataclasses.asdict(a) for a in ABLATIONS],
        "levels": LEVELS, "budgets": BUDGETS, "link": dataclasses.asdict(LinkConfig()),
        "sort_context_equivalence_checks": verified, "novels": len(corpus),
        "runtime_s": round(time.time() - t0, 1), "llm_calls": 0,
    }
    (out / "census.json").write_text(json.dumps(meta, indent=2, default=str))
    print(json.dumps(meta, indent=2, default=str))


if __name__ == "__main__":
    main()

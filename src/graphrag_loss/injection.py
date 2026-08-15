"""Token-exact displacement for E9.

This is the load-bearing module of the causal experiment. ``CONTEXT.md`` §6 and
§9 make two demands that together define the contract:

* Injection happens **at constant token budget** — the oracle arm must not win
  simply by being given a longer context than the placebo arm.
* The oracle arm is compared against a **placebo arm**, never against a
  no-injection baseline. E9 without E9b is invalid.

So :func:`inject_at_constant_budget` removes tokens from the lowest-priority
context pieces to make room for the insertions, and asserts that the result has
*exactly* the same token count as the input. Token count is the contract;
character length is recorded as a diagnostic only.

Exactness is non-trivial because tokenisation is not compositional: slicing a
token list, decoding it, and re-encoding the result can shift the count at
boundaries. The assembly therefore fits by binary search, then closes any
residual gap one token at a time, and finally re-encodes the assembled string to
verify. If exactness cannot be reached the function raises rather than returning
a context that is merely close.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import pandas as pd

from . import schema as S

__all__ = [
    "InjectionError",
    "Tokenizer",
    "TiktokenTokenizer",
    "get_tokenizer",
    "token_len",
    "ContextPiece",
    "InjectionResult",
    "parse_context",
    "render_context",
    "inject_at_constant_budget",
    "inject_with_report",
    "render_elements",
    "sample_placebo_elements",
]

DEFAULT_DELIMITER = "\n\n"
_MAX_PAD_STEPS = 4096


class InjectionError(RuntimeError):
    """Raised when a token-exact context cannot be produced."""


@runtime_checkable
class Tokenizer(Protocol):
    """Minimal encode/decode surface. Matches tiktoken's ``Encoding``."""

    def encode(self, text: str) -> list[int]: ...

    def decode(self, tokens: list[int]) -> str: ...


class TiktokenTokenizer:
    """tiktoken wrapper.

    Defaults to ``o200k_base``, the ``ENCODING_MODEL`` observed in the installed
    graphrag 3.1.1 (``graphrag/config/defaults.py``). KB §G requires the study's
    tokenizer to match the pipeline's; changing this changes every token number.
    """

    def __init__(self, encoding_name: str = "o200k_base") -> None:
        import tiktoken

        self.encoding_name = encoding_name
        self._enc = tiktoken.get_encoding(encoding_name)

    def encode(self, text: str) -> list[int]:
        return self._enc.encode(text, disallowed_special=())

    def decode(self, tokens: list[int]) -> str:
        return self._enc.decode(tokens)


def get_tokenizer(name: str = "o200k_base") -> Tokenizer:
    return TiktokenTokenizer(name)


def token_len(text: str, tokenizer: Tokenizer) -> int:
    return len(tokenizer.encode(text))


@dataclass(frozen=True)
class ContextPiece:
    """One assembled unit of the query context.

    ``rank`` is priority order as GraphRAG assembled it: 0 is highest priority,
    and displacement consumes from the highest rank number downward.
    """

    piece_id: str
    text: str
    rank: int
    token_count: int


@dataclass(frozen=True)
class InjectionResult:
    """Outcome of one injection, including the evidence that it was exact."""

    context: str
    base_tokens: int
    new_tokens: int
    base_chars: int
    new_chars: int
    inserted_tokens: int
    dropped_piece_ids: tuple[str, ...]
    truncated_piece_ids: tuple[str, ...]

    @property
    def is_token_exact(self) -> bool:
        return self.base_tokens == self.new_tokens


def parse_context(
    ctx: str, *, delimiter: str = DEFAULT_DELIMITER, tokenizer: Tokenizer | None = None
) -> list[ContextPiece]:
    """Split an assembled context into ranked pieces."""
    tok = tokenizer or get_tokenizer()
    parts = [p for p in ctx.split(delimiter) if p != ""]
    return [
        ContextPiece(piece_id=f"piece_{i:04d}", text=p, rank=i, token_count=token_len(p, tok))
        for i, p in enumerate(parts)
    ]


def render_context(pieces: Sequence[ContextPiece], *, delimiter: str = DEFAULT_DELIMITER) -> str:
    return delimiter.join(p.text for p in pieces)


def _slice_tokens(text: str, k: int, tokenizer: Tokenizer) -> str:
    ids = tokenizer.encode(text)
    k = max(0, min(k, len(ids)))
    return tokenizer.decode(ids[:k])


def _largest_fitting_slice(
    prefix: str, piece_text: str, target: int, tokenizer: Tokenizer, delimiter: str
) -> tuple[str, int, int]:
    """Binary-search the longest prefix of ``piece_text`` that still fits.

    Returns ``(assembled_text, total_tokens, tokens_taken_from_piece)``.
    """
    ids = tokenizer.encode(piece_text)
    lo, hi = 0, len(ids)
    best_text, best_total, best_k = prefix, token_len(prefix, tokenizer), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = prefix + delimiter + tokenizer.decode(ids[:mid]) if mid > 0 else prefix
        total = token_len(cand, tokenizer)
        if total <= target:
            best_text, best_total, best_k = cand, total, mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best_text, best_total, best_k


def _pad_to_exact(
    text: str, target: int, tokenizer: Tokenizer, filler: str
) -> str:
    """Grow ``text`` to exactly ``target`` tokens using ``filler`` material.

    Appends one filler token at a time. Each step raises the count by roughly
    one, so the loop closes any residual gap left by boundary effects. Falls
    back to spaces once the filler is exhausted.
    """
    current = token_len(text, tokenizer)
    if current == target:
        return text
    if current > target:
        msg = f"cannot pad: text already has {current} tokens, target is {target}"
        raise InjectionError(msg)

    filler_ids = tokenizer.encode(filler) if filler else []
    take = 0
    steps = 0
    out = text
    while current < target and steps < _MAX_PAD_STEPS:
        take += 1
        if take <= len(filler_ids):
            candidate = text + tokenizer.decode(filler_ids[:take])
        else:
            candidate = text + " " * (take - len(filler_ids))
        new_count = token_len(candidate, tokenizer)
        if new_count <= target:
            out, current = candidate, new_count
        steps += 1
        if current == target:
            return out
    if current != target:
        msg = f"failed to reach token-exact budget: got {current}, target {target}"
        raise InjectionError(msg)
    return out


def inject_with_report(
    base_context: str,
    insertions: Sequence[str],
    tokenizer: Tokenizer,
    *,
    delimiter: str = DEFAULT_DELIMITER,
) -> InjectionResult:
    """Inject ``insertions`` while holding the token budget exactly constant.

    Insertions are placed at the front (highest priority); base pieces are then
    re-admitted in their original priority order until the budget is exhausted.
    The first piece that does not fit whole is truncated, and everything after
    it is dropped.
    """
    target = token_len(base_context, tokenizer)
    pieces = parse_context(base_context, delimiter=delimiter, tokenizer=tokenizer)

    insert_block = delimiter.join(t for t in insertions if t)
    inserted_tokens = token_len(insert_block, tokenizer) if insert_block else 0
    if inserted_tokens > target:
        msg = (
            f"insertions need {inserted_tokens} tokens but the base context is only "
            f"{target}; cannot inject at constant budget"
        )
        raise InjectionError(msg)

    assembled = insert_block
    dropped: list[str] = []
    truncated: list[str] = []
    leftover = ""

    for piece in pieces:
        current = token_len(assembled, tokenizer)
        if current >= target:
            dropped.append(piece.piece_id)
            continue
        whole = assembled + delimiter + piece.text if assembled else piece.text
        if token_len(whole, tokenizer) <= target:
            assembled = whole
            continue
        prefix = assembled if assembled else ""
        fitted, _total, k = _largest_fitting_slice(prefix, piece.text, target, tokenizer, delimiter)
        if k > 0:
            assembled = fitted
            truncated.append(piece.piece_id)
            leftover = _slice_tokens(piece.text, k + 64, tokenizer)[len(_slice_tokens(piece.text, k, tokenizer)) :]
        else:
            dropped.append(piece.piece_id)
            if not leftover:
                leftover = piece.text

    assembled = _pad_to_exact(assembled, target, tokenizer, leftover or " ")

    result = InjectionResult(
        context=assembled,
        base_tokens=target,
        new_tokens=token_len(assembled, tokenizer),
        base_chars=len(base_context),
        new_chars=len(assembled),
        inserted_tokens=inserted_tokens,
        dropped_piece_ids=tuple(dropped),
        truncated_piece_ids=tuple(truncated),
    )
    if not result.is_token_exact:
        msg = (
            f"token-exact contract violated: base={result.base_tokens} "
            f"new={result.new_tokens}. E9 is invalid under this result."
        )
        raise InjectionError(msg)
    return result


def inject_at_constant_budget(
    base_context: str,
    insertions: Sequence[str],
    tokenizer: Tokenizer,
    *,
    delimiter: str = DEFAULT_DELIMITER,
) -> str:
    """Return a new context with the same token count as ``base_context``.

    The correctness contract, asserted here and regression-tested in
    ``tests/test_injection.py``::

        len(tokenize(new_ctx)) == len(tokenize(base_ctx))
    """
    result = inject_with_report(base_context, insertions, tokenizer, delimiter=delimiter)
    assert result.new_tokens == result.base_tokens, (  # noqa: S101 - the contract
        f"token-exact contract violated: {result.new_tokens} != {result.base_tokens}"
    )
    return result.context


def render_elements(
    entities: pd.DataFrame, relationships: pd.DataFrame, element_ids: Sequence[str]
) -> list[str]:
    """Render loss-set elements as injectable text.

    Relationships render as ``source -- target: description``; entities as
    ``title: description``. Ids that match neither are skipped rather than
    rendered as placeholders, so an unresolvable id cannot silently become
    injected filler.
    """
    ids = set(str(e) for e in element_ids)
    out: list[str] = []

    rel = relationships[relationships[S.Relationships.ID].astype(str).isin(ids)]
    for _, r in rel.iterrows():
        out.append(
            f"{r[S.Relationships.SOURCE]} -- {r[S.Relationships.TARGET]}: "
            f"{r[S.Relationships.DESCRIPTION]}"
        )

    ent = entities[entities[S.Entities.ID].astype(str).isin(ids)]
    for _, e in ent.iterrows():
        out.append(f"{e[S.Entities.TITLE]}: {e[S.Entities.DESCRIPTION]}")

    return out


def sample_placebo_elements(
    loss_element_ids: Sequence[str],
    *,
    target_tokens: int,
    exclude_ids: Sequence[str],
    entities: pd.DataFrame,
    relationships: pd.DataFrame,
    tokenizer: Tokenizer,
    seed: int = 0,
) -> list[str]:
    """Sample non-gold elements from ``L`` matching a token budget.

    The placebo arm holds constant everything the oracle arm changes except the
    one thing under test: whether the injected elements are the ones the
    question actually needed. Sampling stops at the first element that would
    overshoot ``target_tokens``, so the placebo block never exceeds the oracle
    block it is matched against.
    """
    excluded = set(str(e) for e in exclude_ids)
    pool = [str(e) for e in loss_element_ids if str(e) not in excluded]
    rng = random.Random(seed)
    rng.shuffle(pool)

    chosen: list[str] = []
    used = 0
    for element_id in pool:
        rendered = render_elements(entities, relationships, [element_id])
        if not rendered:
            continue
        cost = token_len(rendered[0], tokenizer)
        if used + cost > target_tokens:
            continue
        chosen.append(rendered[0])
        used += cost
        if used >= target_tokens:
            break
    return chosen

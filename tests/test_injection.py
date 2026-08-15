"""Token-exact displacement — the load-bearing test of the project.

If ``len(tokenize(ctx_new)) == len(tokenize(ctx_base))`` does not hold, E9's
oracle arm may beat the placebo arm merely by carrying a longer context, and the
causal claim collapses. ``CONTEXT.md`` §6 makes the assertion programmatic and
non-negotiable, and the build spec requires 50 random examples to pass before
E9b and E9c may run.

Token count is the contract. Character length is a diagnostic only, recorded on
:class:`InjectionResult` but never asserted (per the E9a decision).
"""

from __future__ import annotations

import random
import string

import pytest

from graphrag_loss.injection import (
    InjectionError,
    get_tokenizer,
    inject_at_constant_budget,
    inject_with_report,
    parse_context,
    render_elements,
    sample_placebo_elements,
    token_len,
)

from .fixtures import build_entities, build_relationships

N_RANDOM_CASES = 50


@pytest.fixture(scope="module")
def tokenizer():
    return get_tokenizer("o200k_base")


def _words(rng: random.Random, n: int) -> str:
    return " ".join(
        "".join(rng.choices(string.ascii_lowercase, k=rng.randint(2, 10))) for _ in range(n)
    )


def _random_case(rng: random.Random) -> tuple[str, list[str]]:
    base = "\n\n".join(f"[piece {i}] {_words(rng, rng.randint(20, 120))}" for i in range(rng.randint(3, 12)))
    insertions = [_words(rng, rng.randint(5, 40)) for _ in range(rng.randint(1, 5))]
    return base, insertions


@pytest.mark.parametrize("case", range(N_RANDOM_CASES))
def test_injection_is_token_exact_on_random_cases(case, tokenizer):
    """THE contract. 50 random examples, every one exact."""
    rng = random.Random(1000 + case)
    base, insertions = _random_case(rng)

    new_ctx = inject_at_constant_budget(base, insertions, tokenizer)

    assert len(tokenizer.encode(new_ctx)) == len(tokenizer.encode(base))


def test_all_fifty_cases_pass_as_a_batch(tokenizer):
    """Restates the contract as a single all-or-nothing check, as E9a demands."""
    failures = []
    for case in range(N_RANDOM_CASES):
        rng = random.Random(2000 + case)
        base, insertions = _random_case(rng)
        result = inject_with_report(base, insertions, tokenizer)
        if result.new_tokens != result.base_tokens:
            failures.append((case, result.base_tokens, result.new_tokens))
    assert failures == [], f"token-exactness failed on {len(failures)} of {N_RANDOM_CASES} cases: {failures}"


@pytest.mark.parametrize("case", range(10))
def test_token_exact_with_unicode_and_punctuation(case, tokenizer):
    """Boundary merges around non-ASCII text are where naive slicing breaks."""
    rng = random.Random(3000 + case)
    alphabet = "abcdefgh éüñ 中文 🎯 \t.,;—"
    base = "\n\n".join("".join(rng.choices(alphabet, k=rng.randint(40, 200))) for _ in range(rng.randint(2, 6)))
    insertions = ["".join(rng.choices(alphabet, k=rng.randint(10, 60)))]

    result = inject_with_report(base, insertions, tokenizer)

    assert result.new_tokens == result.base_tokens


@pytest.mark.parametrize("fraction", [0.05, 0.25, 0.5, 0.75, 0.95])
def test_token_exact_across_insertion_sizes(fraction, tokenizer):
    rng = random.Random(4242)
    base = "\n\n".join(f"[{i}] {_words(rng, 60)}" for i in range(8))
    budget = token_len(base, tokenizer)
    insertion = _words(rng, 400)
    ids = tokenizer.encode(insertion)
    insertion = tokenizer.decode(ids[: max(1, int(budget * fraction))])

    result = inject_with_report(base, [insertion], tokenizer)

    assert result.new_tokens == result.base_tokens


def test_insertions_larger_than_budget_raise_rather_than_truncate(tokenizer):
    """Never return a short context: a silent truncation would invalidate E9."""
    with pytest.raises(InjectionError, match="cannot inject at constant budget"):
        inject_with_report("a very short base context", ["padding " * 500], tokenizer)


def test_insertions_appear_in_the_new_context(tokenizer):
    rng = random.Random(11)
    base = "\n\n".join(f"[{i}] {_words(rng, 80)}" for i in range(6))
    marker = "UNIQUEMARKERTOKENSTRING"

    result = inject_with_report(base, [marker], tokenizer)

    assert marker in result.context


def test_displacement_drops_or_truncates_lowest_priority_pieces(tokenizer):
    rng = random.Random(12)
    base = "\n\n".join(f"[{i}] {_words(rng, 80)}" for i in range(6))
    pieces = parse_context(base, tokenizer=tokenizer)

    result = inject_with_report(base, [_words(rng, 60)], tokenizer)

    touched = set(result.dropped_piece_ids) | set(result.truncated_piece_ids)
    assert touched, "injection must displace something to stay at constant budget"
    highest_touched_rank = min(int(p.removeprefix("piece_")) for p in touched)
    assert highest_touched_rank > 0, "the highest-priority piece should survive"
    assert highest_touched_rank <= pieces[-1].rank


def test_character_length_is_diagnostic_not_asserted(tokenizer):
    """Char length is logged; only token count is the contract."""
    rng = random.Random(13)
    base = "\n\n".join(f"[{i}] {_words(rng, 80)}" for i in range(6))

    result = inject_with_report(base, ["short insertion"], tokenizer)

    assert result.base_chars > 0
    assert result.new_chars > 0
    assert result.is_token_exact


def test_empty_insertions_still_produce_an_exact_context(tokenizer):
    rng = random.Random(14)
    base = "\n\n".join(f"[{i}] {_words(rng, 40)}" for i in range(4))

    result = inject_with_report(base, [], tokenizer)

    assert result.new_tokens == result.base_tokens


def test_render_elements_renders_relationships_and_entities():
    entities, relationships = build_entities(), build_relationships()
    rendered = render_elements(entities, relationships, ["r7", "e1"])
    assert any("DAVE -- ERIN" in r for r in rendered)
    assert any(r.startswith("ALICE:") for r in rendered)


def test_render_elements_skips_unresolvable_ids():
    """An unresolvable id must not become injected filler."""
    entities, relationships = build_entities(), build_relationships()
    assert render_elements(entities, relationships, ["not-an-id"]) == []


def test_placebo_sampling_excludes_the_oracle_elements(tokenizer):
    entities, relationships = build_entities(), build_relationships()
    oracle = ["r7", "r9"]
    oracle_text = render_elements(entities, relationships, oracle)
    budget = sum(token_len(t, tokenizer) for t in oracle_text)

    placebo = sample_placebo_elements(
        [f"r{i}" for i in range(1, 10)],
        target_tokens=budget,
        exclude_ids=oracle,
        entities=entities,
        relationships=relationships,
        tokenizer=tokenizer,
        seed=0,
    )

    assert placebo
    assert all("DAVE -- ERIN" not in p for p in placebo)
    assert all("ALICE -- IVAN" not in p for p in placebo)
    assert sum(token_len(p, tokenizer) for p in placebo) <= budget


def test_placebo_is_deterministic_under_a_fixed_seed(tokenizer):
    entities, relationships = build_entities(), build_relationships()
    kwargs = {
        "target_tokens": 60,
        "exclude_ids": ["r7"],
        "entities": entities,
        "relationships": relationships,
        "tokenizer": tokenizer,
        "seed": 7,
    }
    pool = [f"r{i}" for i in range(1, 10)]
    assert sample_placebo_elements(pool, **kwargs) == sample_placebo_elements(pool, **kwargs)

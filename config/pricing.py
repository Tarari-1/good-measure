"""gpt-6-luna prices (US dollars per 1,000,000 tokens), from the course slides.

How tokens are billed. PydanticAI's RequestUsage (checked against
pydantic_ai.models.openai._map_usage and the openai ResponseUsage type):
  input_tokens        = the API's input_tokens: ALL input tokens, cached ones included
  cache_read_tokens   = input_tokens_details.cached_tokens       (a subset of input_tokens)
  cache_write_tokens  = input_tokens_details.cache_write_tokens  (a subset of input_tokens)
So: uncached = input - cached - cache_write, billed at the input rate; the cached and
cache-write parts are billed at their own rates instead.
"""

from __future__ import annotations

PRICES_ARE_PLACEHOLDERS = False
SOURCE = "course slides (gpt-6-luna)"

INPUT_PER_MTOK = 0.10  # uncached input
CACHED_INPUT_PER_MTOK = 0.01  # cached input (cache read)
CACHE_WRITE_PER_MTOK = 0.125  # input written to the cache
OUTPUT_PER_MTOK = 0.50  # output (includes any reasoning tokens)


def cost_usd(input_tokens: int, cached_input_tokens: int, output_tokens: int, cache_write_tokens: int = 0) -> float:
    """Cost of one usage record. cached and cache_write are parts of input_tokens, not additions to it."""
    uncached = max(input_tokens - cached_input_tokens - cache_write_tokens, 0)
    return round(
        (uncached * INPUT_PER_MTOK + cached_input_tokens * CACHED_INPUT_PER_MTOK
         + cache_write_tokens * CACHE_WRITE_PER_MTOK + output_tokens * OUTPUT_PER_MTOK) / 1_000_000,
        8,
    )


def as_dict() -> dict:
    return {
        "placeholders": PRICES_ARE_PLACEHOLDERS,
        "source": SOURCE,
        "input_per_mtok": INPUT_PER_MTOK,
        "cached_input_per_mtok": CACHED_INPUT_PER_MTOK,
        "cache_write_per_mtok": CACHE_WRITE_PER_MTOK,
        "output_per_mtok": OUTPUT_PER_MTOK,
        "currency": "USD",
        "cached_is_subset_of_input": True,
    }

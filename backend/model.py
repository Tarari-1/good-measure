"""The one model. Every agent in Good Measure uses SHARED_MODEL from this module.

MODEL_NAME is defined here and nowhere else; scripts/check_models.py fails the build
if any other model name appears anywhere in the project.
"""

from __future__ import annotations

import os
from functools import lru_cache

from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from config import settings  # noqa: F401  (loads .env: repo first, then one folder up)
from tracker import audit

MODEL_NAME = "gpt-6-luna"  # the only model any agent may use
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"
PORTKEY_PROVIDER = "openai"

audit.set_pinned_model(MODEL_NAME)


@lru_cache(maxsize=1)
def shared_model() -> OpenAIResponsesModel:
    """The single model object every agent uses (Portkey gateway, pinned model).

    Built lazily (and once) so tests and the API can start without a key.
    """
    api_key = os.getenv("PORTKEY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is not set. Put it in .env (this folder or the one above).")
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-provider": PORTKEY_PROVIDER},
    )
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))

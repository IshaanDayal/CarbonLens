"""
openai client implementation.

this module provides a lazy, synchronous openai client.
NO async code is executed at import time.
NO background tasks.
safe for django startup.
"""

import logging
from typing import Optional
from django.conf import settings

logger = logging.getLogger(__name__)

# global singleton client
_openai_client = None


def get_openai_client():
    """
    lazily create and return a synchronous openai client.

    returns:
        OpenAI client instance or None if api key not configured
    """
    # global _openai_client

    # if _openai_client is not None:
    #     return _openai_client

    # api_key = getattr(settings, "OPENAI_API_KEY", None)
    # if not api_key:
    #     logger.warning("OPENAI_API_KEY not set, openai disabled")
    #     return None

    # try:
    #     from openai import OpenAI

    #     _openai_client = OpenAI(api_key=api_key)
    #     logger.info("openai client initialized (lazy, sync)")
    #     return _openai_client

    # except Exception as e:
    #     logger.error(
    #         f"failed to initialize openai client: {str(e)}",
    #         exc_info=True,
    #     )
        # return None

    """
    openai is disabled.
    return None unconditionally.
    """
    logger.info("openai client disabled — using gemini instead")
    return None



def is_llm_available() -> bool:
    """
    check if openai is available.
    """
    # return get_openai_client() is not None
    """
    openai is not available by design.
    """
    return False
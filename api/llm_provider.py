"""
LLM provider abstraction.

Gemini is the active provider.
ALL calls are async.
NO coroutine may escape this layer.
"""

import logging
from typing import Dict, Optional, Any

from .gemini_client import _gemini_client

logger = logging.getLogger(__name__)


class LLMProvider:
    """
    Async LLM provider wrapper.
    """

    def __init__(self, gemini_client=None):
        # use existing singleton if not explicitly provided
        self.gemini = gemini_client or _gemini_client

    def is_available(self) -> bool:
        return self.gemini is not None

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        response_format: Optional[Dict] = None,
        temperature: float = 0.1,
        max_tokens: int = 512,
    ) -> Dict[str, Any]:
        """
        Generate a response using Gemini.

        GUARANTEES:
        - async end-to-end
        - always awaited
        - always returns a dict
        """

        try:
            # IMPORTANT: your gemini client is already async
            response = await self.gemini.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            if not isinstance(response, dict):
                raise TypeError("gemini returned non-dict")

            return {
                "success": True,
                "response": response,
            }

        except Exception as e:
            logger.error("llm generation failed", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }


# default provider singleton
default_llm_provider = LLMProvider()

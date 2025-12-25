"""
CarbonLens API package.
This package provides the API endpoints and business logic for the CarbonLens application.
"""
from .llm_provider import LLMProvider, default_llm_provider

# Export the default LLM provider for easy access
__all__ = ['LLMProvider', 'default_llm_provider']
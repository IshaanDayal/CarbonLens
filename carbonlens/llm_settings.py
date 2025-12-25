"""
LLM Provider Settings for CarbonLens.
This module provides default settings for LLM providers.
"""
from django.conf import settings

# Default LLM provider (can be 'openai' or 'gemini')
DEFAULT_LLM_PROVIDER = getattr(settings, 'DEFAULT_LLM_PROVIDER', 'gemini')

# Provider-specific settings
LLM_PROVIDERS = {
    'openai': {
        'api_key': getattr(settings, 'OPENAI_API_KEY', ''),
        'model': 'gpt-4',
    },
    'gemini': {
        'api_key': getattr(settings, 'GEMINI_API_KEY', ''),
        'model': 'gemini-pro',
    }
}

# Update default provider if the selected one is not available
if DEFAULT_LLM_PROVIDER == 'openai' and not LLM_PROVIDERS['openai']['api_key']:
    DEFAULT_LLM_PROVIDER = 'gemini'
elif DEFAULT_LLM_PROVIDER == 'gemini' and not LLM_PROVIDERS['gemini']['api_key']:
    # prefer gemini if available, otherwise leave blank
    DEFAULT_LLM_PROVIDER = 'openai' if LLM_PROVIDERS['openai']['api_key'] else ''

# Note: do not raise on missing keys here; provider availability is checked at runtime.

"""
Logging configuration for CarbonLens.
"""
import logging
import os
from django.conf import settings

def setup_logging():
    """Configure logging for the application."""
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Set specific loggers
    logging.getLogger('django').setLevel(logging.INFO)
    logging.getLogger('api').setLevel(logging.DEBUG)


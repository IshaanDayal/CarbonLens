"""
Layer 3: Validation & Normalization Layer

Validates structured intent extracted by the LLM.
This layer is deterministic and contains NO LLM logic.
"""

import logging
from typing import Dict

from .schema import QueryIntent

logger = logging.getLogger(__name__)


class ValidationLayer:
    """
    Validates and normalizes QueryIntent objects.
    """

    def validate_intent(self, intent: QueryIntent) -> Dict:
        """
        Validate extracted intent.

        Returns a dict with:
        - success: bool
        - normalized_intent: dict (if success)
        - errors: list[str] (if failure)
        - needs_clarification: bool
        - clarification_question: str | None
        """

        # ---------- type safety ----------
        if intent is None:
            return {
                "success": False,
                "errors": ["intent is null"],
                "needs_clarification": True,
                "clarification_question": "could you clarify your request?",
            }

        if not isinstance(intent, QueryIntent):
            return {
                "success": False,
                "errors": ["invalid intent type"],
                "needs_clarification": True,
                "clarification_question": "i couldn't understand that request. please rephrase.",
            }

        # ---------- greetings / small talk ----------
        # If greeting flag set but the intent contains data tokens, prefer data intent
        if intent.is_greeting:
            if any([intent.country, intent.gas, intent.metric, getattr(intent, 'metrics', None), intent.year_filter]):
                # fall through to normal validation — treat as data query
                pass
            else:
                return {
                    "success": True,
                    "normalized_intent": {
                        "type": "greeting"
                    },
                }

        if intent.is_small_talk:
            return {
                "success": True,
                "normalized_intent": {
                    "type": "small_talk"
                },
            }

        # ---------- explanatory / why/how questions ----------
        # If the user is asking for an explanation, do not require country/gas/metric.
        if getattr(intent, 'is_explanatory', False):
            normalized = {
                "country": intent.country,
                "gas": intent.gas,
                "sector": intent.sector or "total",
                "metric": intent.metric,
                "year_filter": intent.year_filter,
            }

            return {
                "success": True,
                "normalized_intent": normalized,
            }

        # ---------- clarification handling ----------
        # Only trigger clarification when country or gas is missing, or metric cannot be inferred
        if intent.needs_clarification:
            return {
                "success": False,
                "errors": ["needs clarification"],
                "needs_clarification": True,
                "clarification_question": intent.clarification_question
                or "could you clarify your request?",
            }

        # Required fields for a computation: country and gas are required for a data query; metric may be inferred
        missing = []
        if intent.country is None:
            missing.append("country")
        if intent.gas is None:
            missing.append("gas")

        # Only ask for clarification if this looks explicitly computation-oriented
        if missing and intent.needs_clarification:
            return {
                "success": False,
                "errors": [f"missing required fields: {missing}"],
                "needs_clarification": True,
                "clarification_question": (
                    f"please specify the following: {', '.join(missing)}."
                ),
            }

        # ---------- normalization ----------
        # Determine low confidence: missing critical pieces (country or gas) or missing metric information
        missing = [k for k in (['country', 'gas'] if True else []) if getattr(intent, k) is None]
        low_confidence = False
        if missing:
            low_confidence = True

        # If metric(s) were provided by intent, keep them; otherwise do not default to 'average' automatically
        normalized = {
            "country": intent.country,
            "gas": intent.gas,
            # sector is NOT mandatory; default to 'total' when missing
            "sector": intent.sector or "total",
            # keep metric(s) if present; do not assume average
            "metric": intent.metric if intent.metric else None,
            "metrics": getattr(intent, 'metrics', None),
            "year_filter": intent.year_filter,
            "low_confidence": low_confidence,
        }

        return {
            "success": True,
            "normalized_intent": normalized,
        }

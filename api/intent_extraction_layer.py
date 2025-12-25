"""
Layer 2: Intent Extraction Layer

LLM is used ONLY to extract structured intent.
LLM must NEVER compute numbers, write pandas/SQL, or infer columns.
"""

import json
import logging
from typing import Optional

import pandas as pd

from .llm_provider import LLMProvider, default_llm_provider
from .schema import QueryIntent, get_schema_metadata

logger = logging.getLogger(__name__)


class IntentExtractionLayer:
    """Extracts structured intent from natural language using LLM."""

    def __init__(self, df: pd.DataFrame, llm_provider: Optional[LLMProvider] = None):
        self.df = df
        self.llm = llm_provider or default_llm_provider

    def is_available(self) -> bool:
        return self.llm is not None and self.llm.is_available()

    async def extract_intent(self, user_query: str) -> QueryIntent:
        """
        Extract structured intent from user query.

        ALWAYS returns a QueryIntent instance.
        NEVER returns a coroutine.
        """

        # If LLM is not available, fall back to lightweight deterministic heuristics
        schema_metadata = get_schema_metadata(self.df)
        if not self.is_available():
            uq = user_query.lower()
            intent_dict = {}

            # infer country
            for c in schema_metadata.get('countries', [])[:200]:
                if c and c.lower() in uq:
                    intent_dict['country'] = c
                    break

            # infer gas
            for g in schema_metadata.get('gases', []):
                if g and g.lower() in uq:
                    intent_dict['gas'] = g
                    break
            if 'carbon dioxide' in uq or 'co₂' in uq or 'co2' in uq:
                intent_dict.setdefault('gas', 'co2')

            # infer metric
            # infer metric(s) from common phrases
            metric_map = {
                'average': 'average', 'avg': 'average', 'mean': 'average',
                'sum': 'sum', 'total': 'sum',
                'median': 'median',
                'max': 'max', 'maximum': 'max', 'highest': 'max',
                'min': 'min', 'minimum': 'min', 'lowest': 'min',
                'std': 'std', 'standard deviation': 'std', 'spread': 'std',
                'variance': 'variance', 'variation': 'variance',
                'trend': 'trend', 'over time': 'trend',
                'change': 'change', 'growth': 'change', 'increase': 'change',
                'range': 'range', 'difference': 'range'
            }
            detected_metrics = []
            for phrase, m in metric_map.items():
                if phrase in uq and m not in detected_metrics:
                    detected_metrics.append(m)
            if detected_metrics:
                # if multiple detected, store as metrics list
                intent_dict['metrics'] = detected_metrics
                # also set single metric to first for compatibility
                intent_dict['metric'] = detected_metrics[0]

            # default sector
            if not intent_dict.get('sector') and intent_dict.get('gas') and intent_dict.get('gas').lower() == 'co2':
                intent_dict['sector'] = 'total'

            # parse simple year references (last year, last N years, from X to Y, between X and Y, single year)
            import re
            year_range = None
            yrmax = schema_metadata.get('year_range', {}).get('max') if schema_metadata.get('year_range') else None
            m = re.search(r'from\s+(\d{4})\s+to\s+(\d{4})', uq)
            if not m:
                m = re.search(r'between\s+(\d{4})\s+and\s+(\d{4})', uq)
            if m:
                y1 = int(m.group(1)); y2 = int(m.group(2))
                intent_dict['year_filter'] = {'year_min': min(y1, y2), 'year_max': max(y1, y2)}
            else:
                m2 = re.search(r'last\s+(\d+)\s+years?', uq)
                if m2 and yrmax:
                    n = int(m2.group(1))
                    intent_dict['year_filter'] = {'year_min': max(yrmax - n + 1, 0), 'year_max': yrmax}
                elif 'last year' in uq and yrmax:
                    intent_dict['year_filter'] = {'year': yrmax}
                else:
                    # explicit year like 2019
                    m3 = re.search(r'\b(19|20)\d{2}\b', uq)
                    if m3:
                        intent_dict['year_filter'] = {'year': int(m3.group(0))}

            # conversation flags
            # detect explanatory vs data-driven queries
            compute_kw = ['average', 'avg', 'mean', 'sum', 'total', 'trend', 'compare', 'versus', 'vs', 'per capita', 'rate', 'highest', 'lowest', 'max', 'min', 'median', 'std', 'variance', 'change', 'range']
            explain_kw = ['why', 'how', 'cause', 'causes', 'explain', 'reason', 'because', 'impact', 'affect', 'describe', 'what are', 'what is', 'tell me about', 'types of', 'define']
            # If the utterance contains explicit explainers and is not computation-focused, mark explanatory
            is_explanatory = any(w in uq for w in explain_kw) and not any(w in uq for w in compute_kw)
            # Also treat general 'what is/what are/tell me about' as explanatory when not mentioning country/gas/metric
            general_question_phrases = ['what are', 'what is', 'tell me about', 'describe', 'types of']
            is_general = any(p in uq for p in general_question_phrases) and not any(tok in uq for tok in ['co2', 'methane', 'n2o'] + compute_kw)
            intent_dict.setdefault('is_explanatory', bool(is_explanatory or is_general))
            intent_dict.setdefault('is_small_talk', False)

            # greeting detection: strict and only if the whole utterance is a short greeting and no data tokens present
            import re as _re
            greeting_re = _re.compile(r'^(hi|hello|hey|good morning|good afternoon|good evening)[\.!?\s]*$')
            has_data_tokens = bool(intent_dict.get('country') or intent_dict.get('gas') or intent_dict.get('metric') or intent_dict.get('metrics') or intent_dict.get('year_filter'))
            intent_dict.setdefault('is_greeting', bool(greeting_re.match(uq.strip()) and not has_data_tokens))

            # only ask for clarification when user is explicitly asking for a computation and required fields are missing
            needs_clar = any(w in uq for w in compute_kw) and (not intent_dict.get('country') or not intent_dict.get('gas'))
            intent_dict.setdefault('needs_clarification', bool(needs_clar))

            return QueryIntent(**intent_dict)

        schema_metadata = get_schema_metadata(self.df)

        system_prompt = """you are an intent extraction system for an emissions data chatbot.
    your ONLY job is to extract structured intent and output JSON.

    CRITICAL RULES:
    1. output ONLY valid JSON conforming to the QueryIntent schema
    2. NEVER compute numbers or write pandas/sql
    3. NEVER invent fields or enum values
    4. cement is a SECTOR, not a gas
    5. "co2 cement" => gas=co2 AND sector=cement
    6. do not force "total" to be explicitly stated; infer when appropriate
    7. if ambiguous, set fields to null
    8. greetings => is_greeting=true
    9. non-data chat => is_small_talk=true
    """

        user_prompt = f"""
Available values:

User query: "{user_query}"

Return ONLY the JSON object.
"""

        try:
            # 🔥 CRITICAL: this MUST be awaited
            llm_response = await self.llm.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=500,
            )

            if not isinstance(llm_response, dict):
                raise TypeError("llm.generate did not return a dict")

            if not llm_response.get("success"):
                raise RuntimeError(llm_response.get("error", "llm generation failed"))

            content = llm_response.get("response")

            if content is None:
                raise ValueError("empty llm response")

            if isinstance(content, str):
                content = (
                    content.strip()
                    .removeprefix("```json")
                    .removesuffix("```")
                    .strip()
                )
                intent_dict = json.loads(content)
            elif isinstance(content, dict):
                intent_dict = content
            else:
                raise TypeError("invalid llm response type")

            # --- Heuristic normalization (safe, deterministic) ---
            # Ensure intent contains country/gas/sector/metric when clearly present in the text
            uq = user_query.lower()

            # infer country if missing by scanning schema countries
            if not intent_dict.get('country'):
                for c in schema_metadata.get('countries', [])[:200]:
                    if c and c.lower() in uq:
                        intent_dict['country'] = c
                        break

            # infer gas if missing by scanning known gases
            if not intent_dict.get('gas'):
                for g in schema_metadata.get('gases', []):
                    if g and g.lower() in uq:
                        intent_dict['gas'] = g
                        break
                # common aliases
                if not intent_dict.get('gas'):
                    if 'carbon dioxide' in uq or 'co₂' in uq or 'co2' in uq:
                        intent_dict['gas'] = 'co2'

            # infer metric if missing
            if not intent_dict.get('metric'):
                metric_map = {
                    'average': 'average', 'avg': 'average', 'mean': 'average',
                    'sum': 'sum', 'total': 'sum',
                    'median': 'median',
                    'max': 'max', 'maximum': 'max', 'highest': 'max',
                    'min': 'min', 'minimum': 'min', 'lowest': 'min',
                    'std': 'std', 'standard deviation': 'std', 'spread': 'std',
                    'variance': 'variance', 'variation': 'variance',
                    'trend': 'trend', 'over time': 'trend',
                    'change': 'change', 'growth': 'change', 'increase': 'change',
                    'range': 'range', 'difference': 'range'
                }
                detected_metrics = []
                for phrase, m in metric_map.items():
                    if phrase in uq and m not in detected_metrics:
                        detected_metrics.append(m)
                if detected_metrics:
                    intent_dict['metrics'] = detected_metrics
                    intent_dict['metric'] = detected_metrics[0]

            # default sector to total for common total gases (e.g., co2) when not specified
            if not intent_dict.get('sector'):
                gas_val = intent_dict.get('gas')
                if gas_val and isinstance(gas_val, str) and gas_val.lower() == 'co2':
                    intent_dict['sector'] = 'total'

            # parse year references similar to offline heuristics
            import re
            yrmax = schema_metadata.get('year_range', {}).get('max') if schema_metadata.get('year_range') else None
            m = re.search(r'from\s+(\d{4})\s+to\s+(\d{4})', uq)
            if not m:
                m = re.search(r'between\s+(\d{4})\s+and\s+(\d{4})', uq)
            if m:
                y1 = int(m.group(1)); y2 = int(m.group(2))
                intent_dict.setdefault('year_filter', {})['year_min'] = min(y1, y2)
                intent_dict.setdefault('year_filter', {})['year_max'] = max(y1, y2)
            else:
                m2 = re.search(r'last\s+(\d+)\s+years?', uq)
                if m2 and yrmax:
                    n = int(m2.group(1))
                    intent_dict.setdefault('year_filter', {})['year_min'] = max(yrmax - n + 1, 0)
                    intent_dict.setdefault('year_filter', {})['year_max'] = yrmax
                elif 'last year' in uq and yrmax:
                    intent_dict.setdefault('year_filter', {})['year'] = yrmax
                else:
                    m3 = re.search(r'\b(19|20)\d{2}\b', uq)
                    if m3:
                        intent_dict.setdefault('year_filter', {})['year'] = int(m3.group(0))

            # Determine conversational flags strictly: greeting only if short greeting and no data tokens
            compute_kw = ['average', 'avg', 'mean', 'sum', 'total', 'trend', 'compare', 'versus', 'vs', 'per capita', 'rate', 'highest', 'lowest', 'max', 'min', 'median', 'std', 'variance', 'change', 'range']
            explain_kw = ['why', 'how', 'cause', 'causes', 'explain', 'reason', 'because', 'impact', 'affect']
            is_explanatory = any(w in uq for w in explain_kw) and not any(w in uq for w in compute_kw)
            intent_dict.setdefault('is_explanatory', is_explanatory)

            import re as _re
            greeting_re = _re.compile(r'^(hi|hello|hey|good morning|good afternoon|good evening)[\.!?\s]*$')
            has_data_tokens = bool(intent_dict.get('country') or intent_dict.get('gas') or intent_dict.get('metric') or intent_dict.get('metrics') or intent_dict.get('year_filter'))
            intent_dict.setdefault('is_greeting', bool(greeting_re.match(uq.strip()) and not has_data_tokens))

            # Only ask for clarification when it's clearly a computation intent and required fields missing
            needs_clar = any(w in uq for w in compute_kw) and (not intent_dict.get('country') or not intent_dict.get('gas'))
            intent_dict.setdefault('needs_clarification', bool(needs_clar))
            intent_dict.setdefault('clarification_question', None)

            return QueryIntent(**intent_dict)

        except json.JSONDecodeError as e:
            logger.error("json decode error from llm", exc_info=e)
            return QueryIntent(
                needs_clarification=True,
                clarification_question=(
                    "i couldn't parse that request. could you rephrase it?"
                ),
            )

        except Exception as e:
            logger.error("intent extraction error", exc_info=e)
            return QueryIntent(
                needs_clarification=True,
                clarification_question=(
                    "something went wrong while processing your query. please try again."
                ),
            )

"""
Layer 1: Conversation Layer
Handles greetings, small talk, clarifications, and polite refusals.
NEVER touches data logic.
"""
from typing import Optional
from .schema import QueryIntent
import logging
from .gemini_client import is_gemini_available, generate_with_gemini, ExternalModelError
from .llm_provider import default_llm_provider
import json

logger = logging.getLogger(__name__)


class ConversationLayer:
    """Handles all conversational aspects without data logic."""
    
    def __init__(self):
        self.greeting_sent = False
        # memory for short conversation state
        self.last_intent = None
        self.last_result = None
    
    def handle_greeting(self, intent: QueryIntent) -> Optional[str]:
        """Handle greeting intent."""
        if intent.is_greeting or not self.greeting_sent:
            self.greeting_sent = True
            return (
                "Hello! I'm CarbonLens, your emissions data assistant. "
                "I can help you explore CO2 emissions data by country, sector, and time period. "
                "What would you like to know?"
            )
        return None
    
    def handle_small_talk(self, intent: QueryIntent) -> Optional[str]:
        """Handle non-data related conversation."""
        if intent.is_small_talk:
            return (
                "I can chat about climate topics and help with emissions data. "
                "If you want a quick data look, ask for a country or comparison — otherwise feel free to ask why something might be happening."
            )
        return None
    
    def handle_clarification_request(self, intent: QueryIntent) -> Optional[str]:
        """Handle clarification requests."""
        if intent.needs_clarification and intent.clarification_question:
            return intent.clarification_question
        return None
    
    def handle_polite_refusal(self, intent: QueryIntent) -> Optional[str]:
        """Politely refuse questions unrelated to emissions data."""
        if intent.is_small_talk and not any([
            intent.country, intent.gas, intent.sector, intent.metric, intent.year_filter
        ]):
            return (
                "I can only answer questions about emissions data from the dataset. "
                "Please ask about CO2 emissions by country, sector, or time period."
            )
        return None
    
    
    def format_final_answer(
        self, 
        execution_result,
        intent: QueryIntent
    ) -> str:
        """
        Format the final answer from execution results.
        Restates exactly what was computed, no extrapolation.
        """
        if execution_result.error:
            return f"I encountered an error: {execution_result.error}"
        
        if execution_result.record_count == 0:
            filters = execution_result.applied_filters
            filter_str = ", ".join([f"{k}={v}" for k, v in filters.items()])
            return (
                f"I couldn't find any records matching {filter_str}. "
                "This question may go beyond the dataset — I can explain generally if you'd like."
            )
        
        # Build answer from actual computed value
        # Friendly, explanatory phrasing
        metric_str = intent.metric.value if intent.metric else None
        gas_str = intent.gas.value if intent.gas else "emissions"
        sector_str = intent.sector.value if intent.sector else "total"
        country_str = intent.country if intent.country else "this country"

        value = execution_result.value
        unit = execution_result.unit or ""

        # If multiple metrics computed, build a friendly multi-metric summary
        if getattr(execution_result, 'values', None):
            vals = execution_result.values or {}
            # Build a friendly descriptor for the time window if present
            tf = execution_result.applied_filters.get('year_range') if execution_result.applied_filters else None
            year_phrase = ''
            if tf:
                year_phrase = f" between {tf}"  # already formatted as 'min-max'
            elif execution_result.applied_filters and execution_result.applied_filters.get('year'):
                year_phrase = f" in {execution_result.applied_filters.get('year')}"

            # Compose metric phrases
            metric_phrases = []
            label_map = {
                'max': 'maximum', 'min': 'minimum', 'average': 'average', 'median': 'median',
                'std': 'standard deviation', 'variance': 'variance', 'change': 'absolute change',
                'change_pct': 'percent change', 'range': 'range', 'trend': 'trend (slope per year)'
            }
            for k, v in vals.items():
                if v is None:
                    continue
                label = label_map.get(k, k)
                metric_phrases.append(f"{label} = {v:,.2f} {execution_result.unit or ''}".strip())

            if metric_phrases:
                intro = f"{country_str.capitalize()}'s {sector_str} {gas_str} emissions{year_phrase}:"
                body = "; ".join(metric_phrases)
                answer = f"{intro} {body}."
            else:
                answer = (
                    f"I computed the requested metrics but they are not available for the selected filters."
                )

        else:
            # Single-value fallback
            if metric_str:
                answer = (
                    f"According to the dataset, {country_str}'s {sector_str} {gas_str} emissions ({metric_str}) are about {value:,.2f} {unit}. "
                    f"This provides a data-backed view alongside background factors that usually drive these levels."
                )
            else:
                answer = (
                    f"The dataset shows {value:,.2f} {unit} of {gas_str} emissions in the {sector_str} sector for {country_str}. "
                    "If you'd like, I can compute averages, trends, or compare with other countries."
                )

        # Store in-memory last result for conversational follow-ups
        self.last_intent = intent
        self.last_result = execution_result

        return answer

    async def generate_expert_explanation(self, user_query: str, intent: QueryIntent) -> str:
        """
        Generate a conservative, non-hallucinating expert-style explanation when the dataset
        cannot answer. This is used when an LLM is unavailable; it provides general domain
        knowledge without inventing dataset values.
        """
        uq = (user_query or '').lower()

        # Note: prefer calling Gemini for explanatory responses. If Gemini fails,
        # we'll fall back to a high-quality canned response below.

        # Basic patterns
        if any(w in uq for w in ['why', 'how', 'cause', 'causes', 'explain', 'reason']):
            gas = (intent.gas.value if getattr(intent, 'gas', None) else 'emissions')
            country = intent.country or 'the country'

            parts = [f"{country.capitalize()}'s {gas} emissions can be driven by several structural factors."]
            parts.append("Common drivers include the energy mix (reliance on coal and fossil fuels), industrial activity, agricultural practices, and land-use change.")
            parts.append("Economic growth and population size also influence total emissions; per-capita emissions depend on energy efficiency and consumption patterns.")
            parts.append("I don't have matching rows in the dataset to compute precise numbers for this query, but these factors are commonly cited in the literature.")
            return ' '.join(parts)

        # If user asked for statistical metric but dataset missing, explain limitation
        if any(w in uq for w in ['std', 'standard deviation', 'variance', 'min', 'max', 'median', 'average', 'mean', 'trend', 'change', 'range']):
            gas = (intent.gas.value if getattr(intent, 'gas', None) else 'emissions')
            country = intent.country or 'the selected country'
            return (
                f"I can't compute that metric because the dataset doesn't have matching records for {country} and {gas}. "
                "Generally, to analyze variation over time you need multiple years of data; if you'd like, I can explain typical patterns and what drives variability."
            )

        # Generic fallback
        # Try LLM-driven expert explanation first (if available). Keep it conservative and
        # do not invent dataset-specific numeric values — label as general knowledge.
        try:
            if is_gemini_available():
                system_prompt = (
                    "You are an expert in greenhouse gas emissions and climate policy. "
                    "Answer the user's question as an emissions expert, clearly labeling any statements as general knowledge and NOT as dataset-derived numbers. "
                    "Be concise and helpful (2-3 short paragraphs). If the user requests dataset-specific numbers, say you don't have the dataset available here."
                )
                # NOTE: If Gemini returns no usable text, `generate_with_gemini` will raise
                # `ExternalModelError`. We intentionally *do not* swallow that exception
                # here — it must surface up to the view so the request can return HTTP 502.
                res = await generate_with_gemini(user_query, system_prompt)
                if res and res.get('success') and res.get('response'):
                    explanation = res.get('response')
                    if isinstance(explanation, dict):
                        explanation = json.dumps(explanation)
                    return (
                        "Here is an expert explanation (general knowledge, not dataset values): " + str(explanation)
                    )
        except ExternalModelError:
            # Propagate to caller (view) so it can return a 502 Bad Gateway.
            raise
        except Exception:
            logger.exception("gemini expert explanation failed")

        return (
            "I don't have matching data to compute that exactly. Generally, emissions are affected by energy sources, industrial structure, agriculture, and policy; "
            "if you'd like an explanation on any of these drivers, ask 'why' or 'how' followed by the country or sector."
        )


# Put underspecification helper at module level so views can gate LLM calls.
def is_underspecified(intent: QueryIntent) -> bool:
    """
    Return True when the intent lacks the minimal structured information required
    for deterministic analytical execution or LLM-driven analysis.

    See docstring above in the module for details.
    """
    if not intent:
        return True

    has_country = bool(getattr(intent, 'country', None))

    yf = getattr(intent, 'year_filter', None)
    has_year = False
    if yf:
        if getattr(yf, 'year', None) is not None:
            has_year = True
        if getattr(yf, 'year_min', None) is not None or getattr(yf, 'year_max', None) is not None:
            has_year = True

    has_metric = bool(getattr(intent, 'metric', None)) or bool(getattr(intent, 'metrics', None))
    has_sector = bool(getattr(intent, 'sector', None))

    return not any([has_country, has_year, has_metric, has_sector])


# System prompts for routing
SYSTEM_PROMPT_PANDAS = (
    "You are an assistant that converts a user's natural language data request into a JSON object describing a "
    "pandas-safe filter and a minimal execution plan. DO NOT execute any code or invent numeric results. "
    "Return ONLY a JSON object with the following keys: \n"
    "- pandas_query: a string suitable for pandas.DataFrame.query() that filters the OWID dataset (use columns like country, year, and gas/sector columns).\n"
    "- filters: a dict of explicit filter key/values (country, year, year_min, year_max, gas, sector, metric).\n"
    "- intent: a minimal intent object with keys country, gas, sector, metric, year_filter (year or year_min/year_max).\n"
    "CRITICAL: do not compute aggregates, do not call external systems, and do not return any numbers from the dataset."
)

SYSTEM_PROMPT_EXPERT = (
    "You are an expert in greenhouse gas emissions, atmospheric gases, and environmental science. "
    "Answer the user's question as a cautious domain expert. Label any general-knowledge statements as not dataset-derived and do not invent dataset numbers. "
    "Be concise (2-3 short paragraphs) and prioritize references to well-known drivers, mechanisms, and caveats."
)


class PromptRoutingError(Exception):
    """Raised when routing or LLM generation fails."""


    
async def route_user_query(user_query: str, intent: QueryIntent) -> dict:
    """
    Decide whether a user's query is a data/CSV query or a general expert question,
    then call the appropriate system prompt via the default LLM provider.

    Returns a dict with keys: success (bool), query_type ('data'|'expert'), response (str|dict), error (opt).
    """
    # Determine query type: prefer intent flags; fall back to underspecification check
    try:
        if intent and getattr(intent, 'is_explanatory', False):
            query_type = 'expert'
        elif is_underspecified(intent):
            # underspecified -> expert explanation / clarification
            query_type = 'expert'
        else:
            query_type = 'data'

        provider = default_llm_provider
        if not provider or not provider.is_available():
            return {"success": False, "error": "LLM provider not available", "query_type": query_type}

        if query_type == 'data':
            # Ask LLM to produce a pandas query JSON object
            res = await provider.generate(
                prompt=user_query,
                system_prompt=SYSTEM_PROMPT_PANDAS,
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=600,
            )
            if not res.get('success'):
                return {"success": False, "error": res.get('error'), "query_type": query_type}

            return {"success": True, "query_type": query_type, "response": res.get('response')}

        else:
            # Expert response
            res = await provider.generate(
                prompt=user_query,
                system_prompt=SYSTEM_PROMPT_EXPERT,
                response_format=None,
                temperature=0.2,
                max_tokens=512,
            )
            if not res.get('success'):
                return {"success": False, "error": res.get('error'), "query_type": query_type}

            return {"success": True, "query_type": query_type, "response": res.get('response')}

    except ExternalModelError:
        # propagate external model errors for caller to handle
        raise
    except Exception as e:
        logger.exception("route_user_query failed")
        return {"success": False, "error": str(e), "query_type": 'expert'}


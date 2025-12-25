"""
Google Gemini service for intelligent query processing and analytics.

NOTE: This service is currently commented out. We're using OpenAI instead.
See openai_service.py for the active implementation.
"""
import logging
from typing import Dict, Generator
import json
import datetime

import pandas as pd
# import google.generativeai as genai  # COMMENTED OUT - Using OpenAI instead
from django.conf import settings

logger = logging.getLogger(__name__)


# -------------------------------------------------
# json-safe serialization (timestamps, pandas, etc)
# -------------------------------------------------
def json_safe(obj):
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    return obj


# ============================================================================
# GEMINI SERVICE - COMMENTED OUT (Using OpenAI instead)
# ============================================================================
# To re-enable Gemini, uncomment the code below and comment out OpenAI in views.py
# ============================================================================

class GeminiService:
    """Service for interacting with Google Gemini.
    
    NOTE: Currently disabled. Using OpenAI service instead.
    """

    def __init__(self):
        # COMMENTED OUT - Using OpenAI instead
        logger.warning("Gemini service is disabled. Using OpenAI service instead.")
        self.api_key = None  # settings.GEMINI_API_KEY
        self.model = None
        
        # if not self.api_key:
        #     logger.warning("GEMINI_API_KEY not set, Gemini features disabled")
        #     return
        # 
        # try:
        #     genai.configure(api_key=self.api_key)
        #     self.model = genai.GenerativeModel("models/gemini-flash-latest")
        #     logger.info("Gemini service initialized successfully")
        # except Exception as e:
        #     logger.error(f"Failed to initialize Gemini: {str(e)}")
        #     self.model = None

    def is_available(self) -> bool:
        return False  # Always return False since Gemini is disabled

    # -------------------------------------------------
    # query generation
    # -------------------------------------------------
    def generate_query(self, user_query: str, db_schema: Dict) -> Dict:
        if not self.is_available():
            return {"success": False, "error": "Gemini service not available"}

        try:
            safe_schema = json_safe(db_schema)

            schema_info = f"""
Database Schema:
- Columns: {', '.join(safe_schema.get('columns', [])[:50])}
- Countries: {', '.join(safe_schema.get('countries', [])[:30])}
- Years: {safe_schema.get('years', [])[:10]}

Sample data:
{json.dumps(safe_schema.get('sample_data', {}), indent=2)[:500]}
"""

            prompt = f"""
You are an expert data analyst converting natural language into pandas DataFrame.query() strings.

RULES (VERY IMPORTANT):
1. Output ONLY a pandas query string
2. Use == for equality, & for AND, | for OR
3. ALL string literals MUST use DOUBLE QUOTES
4. NEVER leave quotes unclosed
5. Use exact column names
6. For year filters: year.dt.year == YYYY
7. Do NOT include explanations
8. If unsure, return True

{schema_info}

User Query:
{user_query}

Query:
"""

            response = self.model.generate_content(prompt)
            pandas_query = response.text.strip()

            # cleanup
            pandas_query = pandas_query.replace("```python", "").replace("```", "")
            pandas_query = pandas_query.strip().strip("`")

            return {
                "success": True,
                "query": pandas_query,
                "method": "gemini",
            }

        except Exception as e:
            logger.error(f"Gemini query generation error: {str(e)}")
            return {"success": False, "error": str(e)}

    # -------------------------------------------------
    # analysis response
    # -------------------------------------------------
    def analyze_and_respond(
        self, user_query: str, query_results: Dict, db_schema: Dict
    ) -> str:
        if not self.is_available():
            return self._default_response(query_results)

        try:
            safe_results = json_safe(query_results)

            summary = f"""
Records: {len(safe_results.get('data', []))}
Statistics:
{json.dumps(safe_results.get('statistics', {}), indent=2)}

Summary:
{safe_results.get('summary', '')}
"""

            prompt = f"""
User asked:
"{user_query}"

Results:
{summary}

Respond clearly and concisely (max 2–3 paragraphs).
"""

            response = self.model.generate_content(prompt)
            return response.text.strip()

        except Exception as e:
            logger.error(f"Gemini analysis error: {str(e)}")
            return self._default_response(query_results)

    # -------------------------------------------------
    # graph suggestion
    # -------------------------------------------------
    def suggest_graph_type(self, user_query: str, query_results: Dict) -> str:
        if not self.is_available():
            return "bar"

        try:
            safe_results = json_safe(query_results)
            sample = safe_results.get("data", [{}])

            prompt = f"""
Query: {user_query}
Records: {len(sample)}
Sample row keys: {list(sample[0].keys()) if sample else []}

Respond with ONE word:
line | bar | pie | scatter
"""

            response = self.model.generate_content(prompt)
            graph = response.text.strip().lower()

            return graph if graph in {"line", "bar", "pie", "scatter"} else "bar"

        except Exception as e:
            logger.error(f"Graph suggestion error: {str(e)}")
            return "bar"

    # -------------------------------------------------
    # news keywords
    # -------------------------------------------------
    def extract_news_keywords(self, user_query: str, query_results: Dict) -> str:
        if not self.is_available():
            return user_query

        try:
            safe_results = json_safe(query_results)

            prompt = f"""
Query: {user_query}
Summary: {safe_results.get('summary', '')}

Return 2–3 comma-separated keywords only.
"""

            response = self.model.generate_content(prompt)
            return response.text.strip() or user_query

        except Exception as e:
            logger.error(f"Keyword extraction error: {str(e)}")
            return user_query

    # -------------------------------------------------
    # streaming response
    # -------------------------------------------------
    def stream_response(
        self, user_query: str, query_results: Dict, db_schema: Dict
    ) -> Generator[str, None, None]:
        if not self.is_available():
            yield self._default_response(query_results)
            return

        try:
            safe_results = json_safe(query_results)

            prompt = f"""
User asked:
"{user_query}"

Results:
{json.dumps(safe_results, indent=2)[:1500]}

Respond conversationally and concisely.
"""

            response = self.model.generate_content(prompt, stream=True)
            for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            logger.error(f"Streaming error: {str(e)}")
            yield self._default_response(query_results)

    # -------------------------------------------------
    # fallback
    # -------------------------------------------------
    def _default_response(self, query_results: Dict) -> str:
        summary = query_results.get("summary", "query executed successfully.")
        records = len(query_results.get("data", []))

        if records == 0:
            return f"no matching data found. {summary}"

        return f"{summary} (based on {records} records)"

    def greet_user(self) -> str:
        if not self.is_available():
            return "hello. i’m carbonlens. how can i help you explore emissions data today?"

        try:
            response = self.model.generate_content(
                "greet the user warmly as a co2 emissions data assistant (2–3 sentences)."
            )
            return response.text.strip()

        except Exception:
            return "hello. i’m carbonlens. how can i help you explore emissions data today?"


# -------------------------------------------------
# global singleton
# -------------------------------------------------
_gemini_service = None


def get_gemini_service():
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service

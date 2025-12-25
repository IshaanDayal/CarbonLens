"""
API views using the four-layer architecture.
Schema-grounded, tool-driven data agent.
"""

import logging
from functools import wraps

from asgiref.sync import async_to_sync
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ParseError

from .database import get_database
from .conversation_layer import ConversationLayer, is_underspecified
from .intent_extraction_layer import IntentExtractionLayer
from .gemini_client import ExternalModelError
from .validation_layer import ValidationLayer
from .execution_layer import ExecutionLayer
from .schema import QueryIntent
from .conversation_layer import ConversationLayer
from .news_scraper import get_news_scraper

logger = logging.getLogger(__name__)


def async_to_sync_view(view_func):
    """Decorator to run async view logic inside DRF."""
    @wraps(view_func)
    def _wrapped(self, request, *args, **kwargs):
        return async_to_sync(view_func)(self, request, *args, **kwargs)
    return _wrapped


class HealthView(APIView):
    def get(self, request):
        try:
            db = get_database()
            return Response(
                {
                    "status": "healthy",
                    "database_loaded": bool(db and db.df is not None and not db.df.empty),
                    "data_rows": len(db.df) if db and db.df is not None else 0,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"status": "unhealthy", "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class QueryView(APIView):
    """
    Main query endpoint.
    Async intent extraction + sync validation/execution.
    """

    @async_to_sync_view
    async def post(self, request):
        try:
            try:
                user_query = (request.data or {}).get("query", "").strip()
            except ParseError as pe:
                # Malformed JSON body — do not crash the server
                try:
                    raw = request.body.decode('utf-8', errors='replace')
                    logger.debug(f"malformed json body: {raw}")
                except Exception:
                    logger.debug("malformed json body and couldn't decode raw body")
                return Response({"success": False, "error": "invalid json body"}, status=status.HTTP_400_BAD_REQUEST)
            if not user_query:
                return Response(
                    {"success": False, "error": "query is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            db = get_database()
            if not db or db.df is None or db.df.empty:
                return Response(
                    {"success": False, "error": "database not loaded"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            # initialize layers and load lightweight conversation memory from session
            conversation = ConversationLayer()
            # restore last_intent from session if available (keeps short-term context)
            try:
                mem = request.session.get('conversation_memory')
                if mem and isinstance(mem, dict):
                    # mem expected to be a serialized QueryIntent-like dict
                    last_intent_data = mem.get('last_intent')
                    if last_intent_data:
                        conversation.last_intent = QueryIntent(**last_intent_data)
                    # last_result stored minimally (value and applied_filters)
                    conversation.last_result = mem.get('last_result')
            except Exception:
                logger.debug('no conversation memory found or failed to load')
            intent_extractor = IntentExtractionLayer(db.df)
            validator = ValidationLayer()
            executor = ExecutionLayer(db.df)

            logger.info(f"extracting intent: {user_query}")

            # ---- intent extraction (async)
            intent: QueryIntent = await intent_extractor.extract_intent(user_query)

            # If this looks like an explanatory follow-up (e.g., "why is that"), reuse previous intent fields
            try:
                if getattr(intent, 'is_explanatory', False) and conversation.last_intent:
                    # Fill missing context from last intent to make follow-ups natural
                    if not intent.country and getattr(conversation.last_intent, 'country', None):
                        intent.country = conversation.last_intent.country
                    if not intent.gas and getattr(conversation.last_intent, 'gas', None):
                        intent.gas = conversation.last_intent.gas
                    if not intent.sector and getattr(conversation.last_intent, 'sector', None):
                        intent.sector = conversation.last_intent.sector
            except Exception:
                logger.debug('failed to merge follow-up context')

            # ---- greetings / small talk
            if intent.is_greeting:
                text = conversation.handle_greeting(intent)
                return Response(
                    {
                        "success": True,
                        "type": "greeting",
                        "response": text,
                        "summary": text,
                        "data": [],
                        "statistics": {},
                    }
                )

            if intent.is_small_talk:
                text = conversation.handle_small_talk(intent)
                return Response(
                    {
                        "success": True,
                        "type": "small_talk",
                        "response": text,
                        "summary": text,
                        "data": [],
                        "statistics": {},
                    }
                )

            # ---- explanatory / general knowledge requests
            # Prefer LLM for 'tell me about', 'what is', 'why' style queries.
            # Handle explanatory intents first so queries like "tell me about emissions"
            # are answered by the expert system prompt even when they lack dataset filters.
            if getattr(intent, 'is_explanatory', False):
                # Use internal expert explanation (Gemini-backed)
                try:
                    explanation_text = await conversation.generate_expert_explanation(user_query, intent)
                except ExternalModelError:
                    logger.error("external model (Gemini) returned no text for explanatory request", exc_info=True)
                    return Response({"success": False, "error": "external model failure: no response from Gemini"}, status=status.HTTP_502_BAD_GATEWAY)

                return Response({
                    "success": True,
                    "type": "explanatory",
                    "response": explanation_text,
                    "summary": explanation_text,
                    "data": [],
                    "statistics": {},
                })

            # Gate underspecified intents: ask for clarification when the user is requesting dataset computations
            if is_underspecified(intent):
                question = (
                    "I need a bit more detail to answer. Please specify at least one of: "
                    "a country, a year or year range, an aggregation metric (e.g. sum, average, standard deviation), or a sector."
                )
                return Response(
                    {
                        "success": True,
                        "type": "clarification",
                        "needs_clarification": True,
                        "response": question,
                        "summary": question,
                        "data": [],
                        "statistics": {},
                    }
                )

            # ---- validation
            validation = validator.validate_intent(intent)

            if not validation.get("success"):
                if validation.get("needs_clarification"):
                    question = validation.get("clarification_question")
                    return Response(
                        {
                            "success": True,
                            "type": "clarification",
                            "needs_clarification": True,
                            "response": question,
                            "summary": question,
                            "data": [],
                            "statistics": {},
                        }
                    )

                return Response(
                    {
                        "success": False,
                        "error": "; ".join(validation.get("errors", [])),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            normalized = validation["normalized_intent"]

            # Convert normalized dict back into QueryIntent to satisfy ExecutionLayer and ConversationLayer contracts
            try:
                qi = QueryIntent(**normalized)
            except Exception as e:
                logger.error("failed to construct QueryIntent from normalized intent", exc_info=e)
                return Response({"success": False, "error": "invalid normalized intent"}, status=status.HTTP_400_BAD_REQUEST)

            # ---- execution
            result = executor.execute(qi)
            # Determine whether to use dataset answer or fallback to LLM expert mode
            low_confidence_flag = bool(normalized.get('low_confidence'))

            # If execution failed or returned no rows, prepare LLM fallback
            def llm_fallback_response(reason_text: str):
                # OpenAI removed; use internal expert explanation synchronously
                try:
                    explanation_text = async_to_sync(ConversationLayer().generate_expert_explanation)(user_query, qi)
                except ExternalModelError:
                    logger.error("external model (Gemini) returned no text during llm fallback", exc_info=True)
                    return Response({"success": False, "error": "external model failure: no response from Gemini"}, status=status.HTTP_502_BAD_GATEWAY)

                return Response({
                    "success": True,
                    "type": "data",
                    "response": explanation_text,
                    "summary": explanation_text,
                    "data": [],
                    "statistics": {},
                })

            # If execution raised an error
            if getattr(result, 'error', None):
                # Try LLM if available, otherwise use internal expert generator
                try:
                    explanation_text = await conversation.generate_expert_explanation(user_query, qi)
                except ExternalModelError:
                    logger.error("external model (Gemini) returned no text during execution error fallback", exc_info=True)
                    return Response({"success": False, "error": "external model failure: no response from Gemini"}, status=status.HTTP_502_BAD_GATEWAY)
                return Response({
                    "success": True,
                    "type": "data",
                    "response": explanation_text,
                    "summary": explanation_text,
                    "data": [],
                    "statistics": {},
                })

            # If low confidence intent: try dataset if it produced useful metrics, otherwise fallback to LLM
            if low_confidence_flag:
                # if dataset has rows and at least one computed metric, return dataset answer but mark low_confidence
                values = getattr(result, 'values', {}) or {}
                has_computed = any(v is not None for v in values.values())
                if result.record_count > 0 and has_computed:
                    final_answer = conversation.format_final_answer(result, qi)
                    response_payload = {
                        "success": True,
                        "type": "data",
                        "response": final_answer,
                        "summary": final_answer,
                        "value": getattr(result, "value", None),
                        "values": getattr(result, "values", {}),
                        "unit": getattr(result, "unit", None),
                        "record_count": getattr(result, "record_count", 0),
                        "applied_filters": getattr(result, "applied_filters", {}),
                        "statistics": {},
                        "data": [],
                        "low_confidence": True,
                    }
                    return Response(response_payload)
                else:
                    # prefer LLM if available; otherwise use internal expert explanation
                    try:
                        explanation_text = await conversation.generate_expert_explanation(user_query, qi)
                    except ExternalModelError:
                        logger.error("external model (Gemini) returned no text during low-confidence fallback", exc_info=True)
                        return Response({"success": False, "error": "external model failure: no response from Gemini"}, status=status.HTTP_502_BAD_GATEWAY)
                    return Response({
                        "success": True,
                        "type": "data",
                        "response": explanation_text,
                        "summary": explanation_text,
                        "data": [],
                        "statistics": {},
                    })

            # If some requested metrics were incomputable, fallback to LLM expert explanation
            incomputable = getattr(result, 'incomputable_metrics', None) or []
            if incomputable:
                try:
                    explanation_text = await conversation.generate_expert_explanation(user_query, qi)
                except ExternalModelError:
                    logger.error("external model (Gemini) returned no text during incomputable-metrics fallback", exc_info=True)
                    return Response({"success": False, "error": "external model failure: no response from Gemini"}, status=status.HTTP_502_BAD_GATEWAY)
                return Response({
                    "success": True,
                    "type": "data",
                    "response": explanation_text,
                    "summary": explanation_text,
                    "data": [],
                    "statistics": {},
                })

            # If no rows found, fallback (already handled above for low_confidence)
            if getattr(result, "record_count", 0) == 0:
                try:
                    explanation_text = await conversation.generate_expert_explanation(user_query, qi)
                except ExternalModelError:
                    logger.error("external model (Gemini) returned no text during no-rows fallback", exc_info=True)
                    return Response({"success": False, "error": "external model failure: no response from Gemini"}, status=status.HTTP_502_BAD_GATEWAY)
                return Response({
                    "success": True,
                    "type": "data",
                    "response": explanation_text,
                    "summary": explanation_text,
                    "data": [],
                    "statistics": {},
                })

            # Use ConversationLayer to format final answer from execution result
            final_answer = conversation.format_final_answer(result, qi)

            # persist lightweight conversation memory for follow-ups
            try:
                request.session['conversation_memory'] = {
                    'last_intent': qi.model_dump() if hasattr(qi, 'model_dump') else {},
                    'last_result': {
                        'value': getattr(result, 'value', None),
                        'applied_filters': getattr(result, 'applied_filters', {}),
                        'record_count': getattr(result, 'record_count', 0),
                    }
                }
                request.session.save()
            except Exception:
                logger.debug('failed to save conversation memory to session')

            response_payload = {
                "success": True,
                "type": "data",
                "response": final_answer,
                "summary": final_answer,
                "value": getattr(result, "value", None),
                "values": getattr(result, "values", {}) ,
                "unit": getattr(result, "unit", None),
                "record_count": getattr(result, "record_count", 0),
                "applied_filters": getattr(result, "applied_filters", {}),
                "statistics": {},
                "data": [],
            }

            if getattr(result, "error", None):
                response_payload["success"] = False
                response_payload["error"] = result.error

            return Response(response_payload)

        except Exception as e:
            logger.error("query view error", exc_info=True)
            return Response(
                {"success": False, "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GreetView(APIView):
    def get(self, request):
        conversation = ConversationLayer()
        intent = QueryIntent(is_greeting=True)
        greeting = conversation.handle_greeting(intent)

        return Response(
            {
                "success": True,
                "greeting": greeting or "hello, i’m carbonlens — your emissions data assistant.",
            },
            status=status.HTTP_200_OK,
        )


class NewsView(APIView):
    """Endpoint to fetch news articles related to keywords using scraper fallbacks."""

    def post(self, request):
        try:
            data = request.data or {}
            keywords = (data.get('keywords') or '').strip()
            max_results = int(data.get('max_results') or 5)
            if not keywords:
                return Response({"success": False, "error": "keywords are required"}, status=status.HTTP_400_BAD_REQUEST)

            scraper = get_news_scraper()
            articles = scraper.scrape_news(keywords, max_results=max_results)
            if not articles:
                # direct search fallback
                articles = scraper._fetch_from_search(keywords, max_results)

            return Response({"success": True, "articles": articles}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("news fetch failed")
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

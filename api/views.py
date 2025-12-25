"""
API views for CarbonLens.
"""
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import JsonResponse, StreamingHttpResponse
from rest_framework import status
from django.conf import settings
import pandas as pd
import numpy as np
import math
import json

from .database import get_database
from .query_converter import get_query_converter
from .news_scraper import get_news_scraper
from .intent_extraction_layer import IntentExtractionLayer
from .validation_layer import ValidationLayer
from .execution_layer import ExecutionLayer
from .schema import QueryIntent
# from .gemini_service import get_gemini_service  # COMMENTED OUT
# from .openai_service import get_openai_service  # DISABLED - use llm_client instead
from .llm_client import is_llm_available
from .conversation_layer import ConversationLayer
from .json_utils import json_safe

logger = logging.getLogger(__name__)


# Use json_utils.json_safe instead
def clean(obj):
    """Legacy clean function - use json_utils.json_safe for new code."""
    return json_safe(obj)


class HealthView(APIView):
    """Health check endpoint."""
    
    def get(self, request):
        """Return API health status."""
        try:
            db = get_database()
            return Response({
                'status': 'healthy',
                'database_loaded': not db.df.empty if db.df is not None else False,
                'data_rows': len(db.df) if db.df is not None else 0,
                'openai_available': is_llm_available()
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'status': 'unhealthy',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GreetView(APIView):
    """Get greeting message from OpenAI."""
    
    def get(self, request):
        """Return greeting message."""
        try:
            conversation = ConversationLayer()
            intent = QueryIntent(is_greeting=True)
            greeting = conversation.handle_greeting(intent)
            return Response({
                'greeting': greeting,
                'success': True
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Greet view error: {str(e)}")
            return Response({
                'greeting': "Hello! I'm CarbonLens, your emissions data assistant. How can I help you explore CO2 emissions data today?",
                'success': True
            }, status=status.HTTP_200_OK)


class QueryView(APIView):
    """Handle natural language queries with Gemini integration."""

    def _calculate_statistics(self, df: pd.DataFrame, query_text: str) -> dict:
        stats = {}
        query_lower = query_text.lower()
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

        def safe_number(x):
            if x is None or pd.isna(x) or math.isinf(x):
                return None
            return float(x)

        if 'average' in query_lower or 'avg' in query_lower or 'mean' in query_lower:
            for col in numeric_cols:
                if 'co2' in col.lower() or 'emission' in col.lower():
                    stats['average'] = {
                        'column': col,
                        'value': safe_number(df[col].mean())
                    }
                    break

        if 'total' in query_lower or 'sum' in query_lower:
            for col in numeric_cols:
                if 'co2' in col.lower() or 'emission' in col.lower():
                    stats['total'] = {
                        'column': col,
                        'value': safe_number(df[col].sum())
                    }
                    break

        if 'maximum' in query_lower or 'max' in query_lower or 'highest' in query_lower:
            for col in numeric_cols:
                if 'co2' in col.lower() or 'emission' in col.lower():
                    stats['maximum'] = {
                        'column': col,
                        'value': safe_number(df[col].max())
                    }
                    break

        if 'minimum' in query_lower or 'min' in query_lower or 'lowest' in query_lower:
            for col in numeric_cols:
                if 'co2' in col.lower() or 'emission' in col.lower():
                    stats['minimum'] = {
                        'column': col,
                        'value': safe_number(df[col].min())
                    }
                    break

        summary_parts = []
        for k, v in stats.items():
            if v['value'] is not None:
                summary_parts.append(f"{k.capitalize()} {v['column']}: {v['value']:.2f}")

        summary = ' | '.join(summary_parts) if summary_parts else f"Found {len(df)} records."

        return {
            'statistics': stats,
            'summary': summary
        }
    
    def post(self, request):
        try:
            query_text = request.data.get('query', '').strip()
            
            if not query_text:
                return JsonResponse({
                    'error': 'Query is required',
                    'success': False
                }, status=400)
            
            db = get_database()
            if db.df is None or db.df.empty:
                return JsonResponse({
                    'error': 'Database not loaded. Please ensure OWID data file is available.',
                    'success': False
                }, status=503)
            
            schema = {
                'columns': db.get_columns(),
                'countries': db.get_countries(),
                'years': db.get_years(),
                'sample_data': db.get_sample_data(3)
            }

            # --- Prefer deterministic 4-layer path: intent extraction -> validation -> execution ---
            try:
                import asyncio

                intent_layer = IntentExtractionLayer(db.df)
                raw_intent = asyncio.run(intent_layer.extract_intent(query_text))

                validator = ValidationLayer()
                vres = validator.validate_intent(raw_intent)

                if vres.get('needs_clarification'):
                    return JsonResponse({
                        'success': False,
                        'needs_clarification': True,
                        'clarification_question': vres.get('clarification_question')
                    }, status=200)

                if vres.get('success') and vres.get('normalized_intent'):
                    # Execute deterministically using ExecutionLayer
                    normalized = vres['normalized_intent']
                    # Build QueryIntent model (pydantic will coerce enums)
                    qi = QueryIntent(**normalized)
                    exec_layer = ExecutionLayer(db.df)
                    exec_result = exec_layer.execute(qi)

                    # If no rows, follow LLM fallback rules (handled below similarly)
                    if exec_result.record_count == 0:
                        explanation_text = 'the dataset does not contain this information.'
                        try:
                            # Use internal ConversationLayer for conservative expert explanations
                            import asyncio
                            conv = ConversationLayer()
                            explanation_text = asyncio.run(conv.generate_expert_explanation(query_text, QueryIntent()))
                        except Exception:
                            # fall back to default explanation_text
                            pass

                        return JsonResponse({
                            'data': [],
                            'summary': 'No data found matching your query.',
                            'query_used': str(normalized),
                            'success': True,
                            'response': explanation_text,
                            'llm_fallback': True
                        }, status=200)

                    # Prepare payload from exec_result
                    payload = {
                        'data': [],
                        'summary': f"{exec_result.value} {exec_result.unit}" if exec_result.value is not None else '',
                        'statistics': {},
                        'query_used': str(normalized),
                        'response': f"{exec_result.value} {exec_result.unit}" if exec_result.value is not None else 'No numeric result',
                        'graph_type': 'bar',
                        'news_keywords': f"{query_text} {normalized.get('country')} {normalized.get('gas')} {normalized.get('sector')}",
                        'success': True,
                        'value': exec_result.value,
                        'unit': exec_result.unit,
                        'record_count': exec_result.record_count,
                        'applied_filters': exec_result.applied_filters,
                    }

                    # leave 'data' empty for aggregated numeric responses
                    payload['data'] = []

                    return JsonResponse(clean(payload), status=200, safe=False, json_dumps_params={"allow_nan": False})

            except Exception:
                # If intent extraction path fails, fall back to existing converter path
                logger.exception('Intent-extraction path failed; falling back to converter')
            
            # Use OpenAI for query conversion with fallback
            # Use rule-based converter (OpenAI removed)
            converter = get_query_converter()
            conversion_result = converter.convert_natural_language_to_query(query_text, schema)
            
            if not conversion_result or not conversion_result.get('success'):
                return JsonResponse({
                    'error': f'Failed to convert query: {conversion_result.get("error", "Unknown error") if conversion_result else "Service unavailable"}',
                    'success': False
                }, status=400)
            
            pandas_query = conversion_result.get('query', 'True')
            
            # Additional validation: ensure query is safe
            if not pandas_query or not isinstance(pandas_query, str):
                logger.warning(f"Invalid query type: {type(pandas_query)}, using fallback")
                pandas_query = 'True'
            
            # Execute query with error handling
            try:
                result_df = db.execute_query(pandas_query)
            except Exception as e:
                logger.error(f"Query execution error: {str(e)}, query: {pandas_query}")
                return JsonResponse({
                    'error': f'Query execution failed: {str(e)}. Please try rephrasing your question.',
                    'query_used': str(pandas_query),
                    'success': False
                }, status=400)
            
            if result_df.empty:
                # DETECT no rows and return conservative expert explanation
                explanation_text = 'the dataset does not contain this information.'
                try:
                    import asyncio
                    conv = ConversationLayer()
                    explanation_text = asyncio.run(conv.generate_expert_explanation(query_text, QueryIntent()))
                except Exception:
                    pass

                return JsonResponse({
                    'data': [],
                    'summary': 'No data found matching your query.',
                    'query_used': str(pandas_query),
                    'success': True,
                    'response': explanation_text,
                }, status=200)
            
            result_data = (
                result_df
                .replace([np.inf, -np.inf], np.nan)
                .where(pd.notnull(result_df), None)
                .to_dict('records')
            )
            
            stats = self._calculate_statistics(result_df, query_text)
            
            query_results = {
                'data': result_data,
                'summary': stats.get('summary', ''),
                'statistics': stats.get('statistics', {}),
                'query_used': str(pandas_query),
                'success': True
            }
            
            # Generate intelligent response using OpenAI with fallback
            response_text = query_results['summary']
            graph_type = 'bar'
            news_keywords = query_text
            
            # OpenAI removed — keep deterministic summary and basic defaults
            response_text = query_results['summary']
            graph_type = 'bar'
            news_keywords = query_text
            
            payload = {
                'data': clean(result_data),
                'summary': stats.get('summary', ''),
                'statistics': clean(stats.get('statistics', {})),
                'query_used': str(pandas_query),
                'response': response_text,
                'graph_type': graph_type,
                'news_keywords': news_keywords,
                'success': True
            }
            
            return JsonResponse(
                clean(payload),
                status=200,
                safe=False,
                json_dumps_params={"allow_nan": False},
            )
                 
        except Exception as e:
            logger.error(f"Query view error: {str(e)}")
            return JsonResponse({
                'error': f'Internal server error: {str(e)}',
                'success': False
            }, status=500)


class StreamQueryView(APIView):
    """Stream query response using OpenAI."""
    
    def post(self, request):
        """Stream query response."""
        try:
            query_text = request.data.get('query', '').strip()
            
            if not query_text:
                return Response({'error': 'Query is required'}, status=400)
            
            db = get_database()
            if db.df is None or db.df.empty:
                return Response({'error': 'Database not loaded'}, status=503)
            
            schema = {
                'columns': db.get_columns(),
                'countries': db.get_countries(),
                'years': db.get_years(),
                'sample_data': db.get_sample_data(3)
            }
            
            # Get query results first using OpenAI with fallback
            # Use rule-based converter directly (OpenAI removed)
            converter = get_query_converter()
            conversion_result = converter.convert_natural_language_to_query(query_text, schema)
            
            if not conversion_result or not conversion_result.get('success'):
                return Response({'error': 'Failed to convert query'}, status=400)
            
            pandas_query = conversion_result.get('query', 'True')
            
            # Execute query with error handling
            try:
                result_df = db.execute_query(pandas_query)
            except Exception as e:
                logger.error(f"Query execution error in stream: {str(e)}")
                return Response({'error': f'Query execution failed: {str(e)}'}, status=400)
            
            if result_df.empty:
                query_results = {
                    'data': [],
                    'summary': 'No data found',
                    'statistics': {}
                }
            else:
                result_data = (
                    result_df
                    .replace([np.inf, -np.inf], np.nan)
                    .where(pd.notnull(result_df), None)
                    .to_dict('records')
                )
                
                stats = QueryView()._calculate_statistics(result_df, query_text)
                query_results = {
                    'data': result_data,
                    'summary': stats.get('summary', ''),
                    'statistics': stats.get('statistics', {})
                }
            
            # Stream response
            def generate():
                # Simple streaming: emit the summary first, then final payload
                try:
                    yield f"data: {json.dumps({'chunk': query_results.get('summary', 'Query executed.')})}\n\n"
                except Exception:
                    yield f"data: {json.dumps({'chunk': 'Query executed.'})}\n\n"
                
                # Send final data
                yield f"data: {json.dumps({'done': True, 'data': clean(query_results.get('data', [])), 'statistics': clean(query_results.get('statistics', {}))})}\n\n"
            
            response = StreamingHttpResponse(generate(), content_type='text/event-stream')
            response['Cache-Control'] = 'no-cache'
            response['X-Accel-Buffering'] = 'no'
            return response
            
        except Exception as e:
            logger.error(f"Stream query error: {str(e)}")
            return Response({'error': str(e)}, status=500)


class NewsView(APIView):
    """Handle news scraping requests."""
    
    def post(self, request):
        """
        Scrape news related to query keywords.
        
        Expected request body:
        {
            "keywords": "China CO2 emissions",
            "max_results": 5
        }
        """
        try:
            keywords = request.data.get('keywords', '')
            max_results = request.data.get('max_results', 5)
            
            if not keywords:
                return Response({
                    'error': 'Keywords are required',
                    'success': False
                }, status=status.HTTP_400_BAD_REQUEST)
            
            scraper = get_news_scraper()
            articles = scraper.scrape_news(keywords, max_results)
            # Normalize article fields to frontend expectations (link, source_id, pubDate)
            normalized = []
            for a in articles:
                link = a.get('url') or a.get('link') or a.get('href')
                if not link:
                    continue
                normalized.append({
                    'title': a.get('title') or a.get('headline') or '',
                    'source_id': a.get('source') or a.get('source_id') or '',
                    'pubDate': a.get('published_at') or a.get('publishedAt') or a.get('pubDate') or '',
                    'link': link,
                    'description': a.get('description') or a.get('summary') or '',
                    'content': a.get('content') or a.get('description') or ''
                })
            articles = normalized
            
            return Response({
                'articles': articles,
                'count': len(articles),
                'success': True
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"News view error: {str(e)}")
            return Response({
                'error': f'Internal server error: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

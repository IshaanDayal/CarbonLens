"""
Natural language to SQL/pandas query converter.
NOTE: This is a legacy fallback. The refactored system uses intent_extraction_layer.
"""
import re
import logging
from typing import Dict, Optional
# from openai import OpenAI  # DISABLED - use llm_client.get_openai_client() instead
from django.conf import settings
import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import Keyword, DML
from .llm_client import get_openai_client, is_llm_available

logger = logging.getLogger(__name__)


class QueryConverter:
    """Converts natural language queries to pandas-compatible queries.
    
    NOTE: This is legacy code. The refactored system uses IntentExtractionLayer.
    Kept for backward compatibility only.
    """
    
    def __init__(self):
        """Initialize the query converter."""
        # DISABLED: Use centralized client from llm_client module
        # self.openai_client = None
        # if settings.OPENAI_API_KEY:
        #     try:
        #         self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        #     except Exception as e:
        #         logger.warning(f"OpenAI client initialization failed: {str(e)}")
        pass
    
    def _validate_sql_security(self, sql_query: str) -> bool:
        """
        Validate that SQL query only contains SELECT statements.
        
        Args:
            sql_query: SQL query string
            
        Returns:
            True if query is safe (only SELECT), False otherwise
        """
        try:
            parsed = sqlparse.parse(sql_query)
            for statement in parsed:
                # Check if statement is a DML statement
                token_list = statement.tokens
                for token in token_list:
                    if token.ttype is DML:
                        # Only allow SELECT statements
                        if token.value.upper() != 'SELECT':
                            logger.warning(f"Non-SELECT DML detected: {token.value}")
                            return False
            return True
        except Exception as e:
            logger.error(f"SQL validation error: {str(e)}")
            return False
    
    def _convert_to_pandas_query(self, sql_query: str, db_schema: Dict) -> str:
        """
        Convert SQL-like query to pandas query string.
        
        Args:
            sql_query: SQL query string
            db_schema: Database schema information
            
        Returns:
            Pandas-compatible query string
        """
        # Basic SQL to pandas conversion
        # This is a simplified version - in production, use a proper SQL parser
        
        # Remove SQL-specific syntax
        query = sql_query.upper()
        
        # Extract WHERE clause
        if 'WHERE' in query:
            where_part = query.split('WHERE')[1].split('ORDER BY')[0].split('LIMIT')[0].strip()
            # Convert SQL operators to Python
            where_part = where_part.replace(' AND ', ' & ')
            where_part = where_part.replace(' OR ', ' | ')
            where_part = where_part.replace(' = ', ' == ')
            where_part = where_part.replace("'", '"')
            return where_part
        
        return ""
    
    def convert_natural_language_to_query(self, 
                                         natural_language_query: str,
                                         db_schema: Optional[Dict] = None) -> Dict[str, any]:
        """
        Convert natural language query to pandas query.
        
        Args:
            natural_language_query: User's natural language query
            db_schema: Database schema information
            
        Returns:
            Dictionary with 'query', 'sql_query', and 'success' keys
        """
        if not db_schema:
            db_schema = {
                'columns': [],
                'sample_data': {},
                'countries': [],
                'years': []
            }
        
        # Try OpenAI conversion if available (using centralized client)
        if is_llm_available():
            try:
                return self._convert_with_openai(natural_language_query, db_schema)
            except Exception as e:
                logger.error(f"OpenAI conversion failed: {str(e)}")
        
        # Fallback to rule-based conversion
        return self._convert_with_rules(natural_language_query, db_schema)
    
    def _convert_with_openai(self, query: str, db_schema: Dict) -> Dict[str, any]:
        """Convert using OpenAI API."""
        client = get_openai_client()
        if not client:
            return {"success": False, "error": "OpenAI client not available"}
        
        try:
            schema_info = f"""
Available columns: {', '.join(db_schema.get('columns', []))}
Available countries: {', '.join(db_schema.get('countries', [])[:20])}
Available years: {db_schema.get('years', [])[:5] if db_schema.get('years') else []}
"""
            
            prompt = f"""You are a SQL query generator for CO2 emissions data. 
Convert the following natural language query to a pandas DataFrame query string.

Database schema:
{schema_info}

Rules:
1. Only generate SELECT-like queries (no DELETE, UPDATE, INSERT, DROP)
2. Return a pandas query string that can be used with DataFrame.query()
3. Use Python syntax (== for equality, & for AND, | for OR)
4. Handle country names case-insensitively
5. For aggregations like "average", "mean", use appropriate pandas operations

User query: {query}

Return ONLY the pandas query string, nothing else. Example format:
country == "China" & year >= 2010

Query:"""
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that converts natural language to pandas DataFrame queries for CO2 emissions data."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            pandas_query = response.choices[0].message.content.strip()
            
            # Clean up the response
            pandas_query = re.sub(r'^query[:]?\s*', '', pandas_query, flags=re.IGNORECASE)
            pandas_query = pandas_query.strip('`"\'')
            
            return {
                'query': pandas_query,
                'sql_query': None,
                'success': True,
                'method': 'openai'
            }
            
        except Exception as e:
            logger.error(f"OpenAI conversion error: {str(e)}")
            raise
    
    def _convert_with_rules(self, query: str, db_schema: Dict) -> Dict[str, any]:
        """Convert using rule-based approach."""
        query_lower = query.lower()
        conditions = []
        
        # Extract country
        countries = db_schema.get('countries', [])
        for country in countries:
            if country.lower() in query_lower:
                conditions.append(f'country == "{country}"')
                break
        
        # Extract year range
        year_pattern = r'\b(19|20)\d{2}\b'
        years = re.findall(year_pattern, query)
        if years:
            year = int(''.join(years[0]))
            conditions.append(f'year.dt.year == {year}')
        
        # Extract metric (CO2, emissions, etc.)
        if 'average' in query_lower or 'avg' in query_lower or 'mean' in query_lower:
            # This will be handled in post-processing
            pass
        
        # Extract comparison operators
        if 'greater than' in query_lower or 'more than' in query_lower or '>' in query:
            # Extract number
            numbers = re.findall(r'\d+', query)
            if numbers:
                conditions.append(f'co2 > {numbers[0]}')
        
        if 'less than' in query_lower or 'fewer than' in query_lower or '<' in query:
            numbers = re.findall(r'\d+', query)
            if numbers:
                conditions.append(f'co2 < {numbers[0]}')
        
        pandas_query = ' & '.join(conditions) if conditions else 'True'
        
        return {
            'query': pandas_query,
            'sql_query': None,
            'success': True,
            'method': 'rule-based'
        }


# Global instance
_converter_instance = None


def get_query_converter():
    """Get or create the global query converter instance."""
    global _converter_instance
    if _converter_instance is None:
        _converter_instance = QueryConverter()
    return _converter_instance


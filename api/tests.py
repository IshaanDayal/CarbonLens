"""
Tests for CarbonLens API.
"""
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from .database import OWIDDatabase
from .query_converter import QueryConverter


class HealthCheckTest(TestCase):
    """Test health check endpoint."""
    
    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
    
    def test_health_endpoint(self):
        """Test health check endpoint returns 200."""
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('status', response.data)


class QueryEndpointTest(TestCase):
    """Test query endpoint."""
    
    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
    
    def test_query_missing_query(self):
        """Test query endpoint with missing query parameter."""
        response = self.client.post('/api/query/', {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_query_with_query(self):
        """Test query endpoint with valid query."""
        response = self.client.post('/api/query/', {
            'query': 'What is the average CO2 level of China?'
        })
        # Should return 200 or 503 (if data not loaded)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE])


class NewsEndpointTest(TestCase):
    """Test news endpoint."""
    
    def setUp(self):
        """Set up test client."""
        self.client = APIClient()
    
    def test_news_missing_keywords(self):
        """Test news endpoint with missing keywords."""
        response = self.client.post('/api/news/', {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_news_with_keywords(self):
        """Test news endpoint with valid keywords."""
        response = self.client.post('/api/news/', {
            'keywords': 'China CO2',
            'max_results': 5
        })
        # Should return 200 (even if no articles found)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class DatabaseTest(TestCase):
    """Test database handler."""
    
    def test_database_initialization(self):
        """Test database can be initialized."""
        db = OWIDDatabase()
        self.assertIsNotNone(db)
        self.assertIsNotNone(db.df)
    
    def test_get_columns(self):
        """Test getting columns."""
        db = OWIDDatabase()
        columns = db.get_columns()
        self.assertIsInstance(columns, list)


class QueryConverterTest(TestCase):
    """Test query converter."""
    
    def test_converter_initialization(self):
        """Test converter can be initialized."""
        converter = QueryConverter()
        self.assertIsNotNone(converter)
    
    def test_rule_based_conversion(self):
        """Test rule-based query conversion."""
        converter = QueryConverter()
        schema = {
            'columns': ['country', 'year', 'co2'],
            'countries': ['China', 'USA'],
            'years': [2020, 2021]
        }
        result = converter._convert_with_rules('Show me China data', schema)
        self.assertIsNotNone(result)
        self.assertIn('query', result)


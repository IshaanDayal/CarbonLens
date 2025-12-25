"""
Unit tests for refactored four-layer architecture.
"""
from django.test import TestCase
import pandas as pd
from .schema import QueryIntent, Gas, Sector, Metric, ValidationResult
from .validation_layer import ValidationLayer
from .execution_layer import ExecutionLayer
from .conversation_layer import ConversationLayer


class TestValidationLayer(TestCase):
    """Test intent validation and normalization."""
    
    def setUp(self):
        """Create test dataframe."""
        self.df = pd.DataFrame({
            'country': ['China', 'United States', 'India'],
            'year': [2020, 2020, 2020],
            'co2': [1000, 500, 300],
            'cement_co2': [100, 50, 30],
        })
        self.validator = ValidationLayer(self.df)
    
    def test_country_validation(self):
        """Test country validation."""
        intent = QueryIntent(country="China", gas=Gas.CO2, sector=Sector.TOTAL, metric=Metric.SUM)
        result = self.validator.validate(intent)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.normalized_intent.country, "China")
    
    def test_invalid_country(self):
        """Test invalid country triggers clarification."""
        intent = QueryIntent(country="FakeCountry", gas=Gas.CO2, sector=Sector.TOTAL, metric=Metric.SUM)
        result = self.validator.validate(intent)
        self.assertFalse(result.is_valid)
        self.assertTrue(result.clarification_needed)
    
    def test_missing_country(self):
        """Test missing country triggers clarification."""
        intent = QueryIntent(gas=Gas.CO2, sector=Sector.TOTAL, metric=Metric.SUM)
        result = self.validator.validate(intent)
        self.assertFalse(result.is_valid)
        self.assertTrue(result.clarification_needed)
    
    def test_cement_as_sector(self):
        """Test that cement is treated as sector, not gas."""
        intent = QueryIntent(
            country="China",
            gas=Gas.CO2,
            sector=Sector.CEMENT,  # cement is a sector
            metric=Metric.SUM
        )
        result = self.validator.validate(intent)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.normalized_intent.sector, Sector.CEMENT)
        self.assertEqual(result.normalized_intent.gas, Gas.CO2)


class TestExecutionLayer(TestCase):
    """Test deterministic query execution."""
    
    def setUp(self):
        """Create test dataframe."""
        self.df = pd.DataFrame({
            'country': ['China', 'United States', 'India', 'China'],
            'year': [2020, 2020, 2020, 2021],
            'co2': [1000, 500, 300, 1100],
            'cement_co2': [100, 50, 30, 110],
        })
        self.executor = ExecutionLayer(self.df)
    
    def test_sum_aggregation(self):
        """Test sum metric."""
        intent = QueryIntent(
            country="China",
            gas=Gas.CO2,
            sector=Sector.TOTAL,
            metric=Metric.SUM
        )
        result = self.executor.execute(intent)
        self.assertIsNotNone(result.value)
        self.assertEqual(result.value, 2100.0)  # 1000 + 1100
    
    def test_average_aggregation(self):
        """Test average metric."""
        intent = QueryIntent(
            country="China",
            gas=Gas.CO2,
            sector=Sector.TOTAL,
            metric=Metric.AVERAGE
        )
        result = self.executor.execute(intent)
        self.assertIsNotNone(result.value)
        self.assertEqual(result.value, 1050.0)  # (1000 + 1100) / 2
    
    def test_cement_sector(self):
        """Test cement sector column mapping."""
        intent = QueryIntent(
            country="China",
            gas=Gas.CO2,
            sector=Sector.CEMENT,
            metric=Metric.SUM
        )
        result = self.executor.execute(intent)
        # Should find cement_co2 column
        self.assertIsNotNone(result.value)
    
    def test_year_filter(self):
        """Test year filtering."""
        from .schema import YearFilter
        intent = QueryIntent(
            country="China",
            gas=Gas.CO2,
            sector=Sector.TOTAL,
            metric=Metric.SUM,
            year_filter=YearFilter(year=2020)
        )
        result = self.executor.execute(intent)
        self.assertEqual(result.value, 1000.0)  # Only 2020 data


class TestGasSectorDisambiguation(TestCase):
    """Test gas/sector disambiguation, especially co2 vs co2 cement."""
    
    def setUp(self):
        """Create test dataframe with both total and cement columns."""
        self.df = pd.DataFrame({
            'country': ['China', 'China'],
            'year': [2020, 2020],
            'co2': [1000, 1000],  # Total CO2
            'cement_co2': [100, 100],  # CO2 from cement sector
        })
        self.validator = ValidationLayer(self.df)
        self.executor = ExecutionLayer(self.df)
    
    def test_co2_total_vs_cement(self):
        """Test distinction between total CO2 and cement CO2."""
        # Total CO2
        intent_total = QueryIntent(
            country="China",
            gas=Gas.CO2,
            sector=Sector.TOTAL,
            metric=Metric.SUM
        )
        result_total = self.executor.execute(intent_total)
        
        # Cement CO2
        intent_cement = QueryIntent(
            country="China",
            gas=Gas.CO2,
            sector=Sector.CEMENT,
            metric=Metric.SUM
        )
        result_cement = self.executor.execute(intent_cement)
        
        # Should be different values
        self.assertNotEqual(result_total.value, result_cement.value)
        self.assertEqual(result_total.value, 1000.0)
        self.assertEqual(result_cement.value, 100.0)


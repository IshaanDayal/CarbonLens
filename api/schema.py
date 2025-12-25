"""
Schema definitions for emissions data queries.
Centralized enums and validation rules.
"""
from enum import Enum
from typing import Optional, List, Union, Dict
from pydantic import BaseModel, Field, field_validator
import logging
import pandas as pd


logger = logging.getLogger(__name__)


class Gas(str, Enum):
    """Emission gas types."""
    CO2 = "co2"
    METHANE = "methane"
    N2O = "n2o"
    # Add more as needed from dataset


class Sector(str, Enum):
    """Emission sectors. NOTE: cement is a SECTOR, not a gas."""
    TOTAL = "total"
    CEMENT = "cement"
    TRANSPORT = "transport"
    ENERGY = "energy"
    AGRICULTURE = "agriculture"
    # Add more as needed from dataset


class Metric(str, Enum):
    """Aggregation metrics."""
    SUM = "sum"
    AVERAGE = "average"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
    STD = "std"
    VARIANCE = "variance"
    RANGE = "range"
    CHANGE = "change"
    TREND = "trend"


class YearFilter(BaseModel):
    """Year filter specification."""
    year: Optional[int] = None
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    
    @field_validator('year', 'year_min', 'year_max')
    @classmethod
    def validate_year(cls, v):
        if v is not None and (v < 1800 or v > 2100):
            raise ValueError("Year must be between 1800 and 2100")
        return v


class QueryIntent(BaseModel):
    """
    Structured intent extracted from user query.
    This is the ONLY schema the LLM should output.
    """
    country: Optional[str] = Field(None, description="Country name (must match CSV exactly)")
    gas: Optional[Gas] = Field(None, description="Gas type: co2, methane, n2o")
    sector: Optional[Sector] = Field(None, description="Sector: total, cement, transport, energy, agriculture")
    metric: Optional[Metric] = Field(None, description="Aggregation: sum, average, median, min, max")
    metrics: Optional[List[Metric]] = Field(None, description="Optional list of metrics to compute")
    year_filter: Optional[YearFilter] = Field(None, description="Year filter")
    
    # Conversation flags
    is_greeting: bool = Field(False, description="True if user is greeting")
    is_small_talk: bool = Field(False, description="True if non-data related chat")
    is_explanatory: bool = Field(False, description="True if user asks for explanations or causes (why/how)")
    low_confidence: bool = Field(False, description="True if intent is low confidence and should fallback to LLM when needed")
    needs_clarification: bool = Field(False, description="True if query is ambiguous")
    clarification_question: Optional[str] = Field(None, description="Question to ask user for clarification")
    
    @field_validator('sector')
    @classmethod
    def validate_sector_not_gas(cls, v, info):
        """Ensure cement is treated as sector, not gas."""
        if v == Sector.CEMENT and info.data.get('gas') == Gas.CO2:
            # This is valid: co2 from cement sector
            pass
        return v
    
    def model_dump(self, **kwargs):
        """Override to ensure JSON-safe serialization."""
        from .json_utils import json_safe
        data = super().model_dump(**kwargs)
        return json_safe(data)


class ValidationResult(BaseModel):
    """Result of intent validation."""
    is_valid: bool
    normalized_intent: Optional[QueryIntent] = None
    errors: List[str] = Field(default_factory=list)
    clarification_needed: bool = False
    clarification_message: Optional[str] = None


class ExecutionResult(BaseModel):
    """Result of deterministic query execution."""
    value: Optional[float] = None
    values: Optional[Dict[str, float]] = None
    unit: Optional[str] = None
    applied_filters: dict = Field(default_factory=dict)
    record_count: int = 0
    incomputable_metrics: Optional[List[str]] = None
    error: Optional[str] = None


# # Schema metadata for LLM
# def get_schema_metadata(df) -> dict:
#     """
#     Generate schema metadata from dataframe.
#     Used to show LLM available values.
#     """
#     metadata = {
#         "countries": sorted(df['country'].unique().tolist()) if 'country' in df.columns else [],
#         "gases": [g.value for g in Gas],
#         "sectors": [s.value for s in Sector],
#         "metrics": [m.value for m in Metric],
#         "year_range": {
#             "min": int(df['year'].min()) if 'year' in df.columns else None,
#             "max": int(df['year'].max()) if 'year' in df.columns else None,
#         } if 'year' in df.columns else None,
#     }
#     return metadata


def get_schema_metadata(df) -> dict:
    """
    Generate schema metadata from dataframe.
    Used to show LLM available values.
    """

    year_min = None
    year_max = None

    if 'year' in df.columns and not df['year'].empty:
        y_min = df['year'].min()
        y_max = df['year'].max()

        # handle pandas Timestamp or datetime
        if isinstance(y_min, pd.Timestamp):
            year_min = y_min.year
        else:
            year_min = int(y_min)

        if isinstance(y_max, pd.Timestamp):
            year_max = y_max.year
        else:
            year_max = int(y_max)

    metadata = {
        "countries": (
            sorted(df['country'].dropna().unique().tolist())
            if 'country' in df.columns else []
        ),
        "gases": [g.value for g in Gas],
        "sectors": [s.value for s in Sector],
        "metrics": [m.value for m in Metric],
        "year_range": {
            "min": year_min,
            "max": year_max,
        } if year_min is not None else None,
    }

    return metadata
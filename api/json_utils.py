"""
JSON serialization utilities.
Ensures pandas Timestamp, datetime, numpy types are always JSON-safe.
"""
import json
import datetime
import pandas as pd
import numpy as np
from typing import Any


def json_safe(obj: Any) -> Any:
    """
    Convert objects to JSON-safe primitives.
    Handles pandas Timestamp, datetime, numpy types, NaN, infinity.
    """
    if obj is None:
        return None
    
    # Pandas Timestamp
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    
    # Datetime objects
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    
    # Numpy types
    if isinstance(obj, (np.integer, np.floating)):
        if pd.isna(obj) or (isinstance(obj, np.floating) and (np.isinf(obj) or np.isnan(obj))):
            return None
        return float(obj) if isinstance(obj, np.floating) else int(obj)
    
    # Python float/int with NaN/inf
    if isinstance(obj, (int, float)):
        if pd.isna(obj) or (isinstance(obj, float) and (obj == float('inf') or obj == float('-inf') or obj != obj)):
            return None
        return obj
    
    # Dict
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    
    # List/tuple
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    
    # Pandas Series
    if isinstance(obj, pd.Series):
        return json_safe(obj.tolist())
    
    # Pandas DataFrame
    if isinstance(obj, pd.DataFrame):
        return json_safe(obj.to_dict('records'))
    
    # Try to convert to string if all else fails
    try:
        return str(obj)
    except:
        return None


def safe_json_response(data: dict, status: int = 200) -> dict:
    """
    Prepare data for JSON response, ensuring all values are JSON-safe.
    """
    return json_safe(data)


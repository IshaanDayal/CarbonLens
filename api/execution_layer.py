"""
Layer 4: Deterministic Execution Layer
Loads CSV into pandas, applies validated filters, performs aggregation.
NO LLM involvement.
"""
import logging
from typing import Dict, Optional
import pandas as pd
import numpy as np
from .schema import QueryIntent, ExecutionResult, Gas, Sector, Metric

logger = logging.getLogger(__name__)


class ExecutionLayer:
    """Deterministic query execution with no LLM involvement."""
    
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self._prepare_dataframe()
    
    def _prepare_dataframe(self):
        """Prepare dataframe for querying."""
        # Ensure year is numeric if present
        if 'year' in self.df.columns:
            if pd.api.types.is_datetime64_any_dtype(self.df['year']):
                self.df['year'] = self.df['year'].dt.year
            self.df['year'] = pd.to_numeric(self.df['year'], errors='coerce')
    
    def execute(self, intent: QueryIntent) -> ExecutionResult:
        """
        Execute validated query intent deterministically.
        Returns numeric result with metadata.
        """
        try:
            # Start with full dataframe
            result_df = self.df.copy()
            applied_filters = {}
            
            # Apply country filter
            if intent.country:
                result_df = result_df[result_df['country'] == intent.country]
                applied_filters['country'] = intent.country
                logger.info(f"Applied country filter: {intent.country}")
            
            # Apply year filter
            if intent.year_filter:
                if intent.year_filter.year:
                    result_df = result_df[result_df['year'] == intent.year_filter.year]
                    applied_filters['year'] = intent.year_filter.year
                elif intent.year_filter.year_min and intent.year_filter.year_max:
                    result_df = result_df[
                        (result_df['year'] >= intent.year_filter.year_min) &
                        (result_df['year'] <= intent.year_filter.year_max)
                    ]
                    applied_filters['year_range'] = f"{intent.year_filter.year_min}-{intent.year_filter.year_max}"
                elif intent.year_filter.year_min:
                    result_df = result_df[result_df['year'] >= intent.year_filter.year_min]
                    applied_filters['year_min'] = intent.year_filter.year_min
                elif intent.year_filter.year_max:
                    result_df = result_df[result_df['year'] <= intent.year_filter.year_max]
                    applied_filters['year_max'] = intent.year_filter.year_max
            
            # Select appropriate column based on gas and sector
            column_name = self._get_column_name(intent.gas, intent.sector)
            
            if not column_name or column_name not in result_df.columns:
                return ExecutionResult(
                    error=f"Column '{column_name}' not found in dataset",
                    applied_filters=applied_filters,
                    record_count=len(result_df)
                )
            
            # Extract the column
            values = result_df[column_name].dropna()
            
            if len(values) == 0:
                return ExecutionResult(
                    value=None,
                    applied_filters=applied_filters,
                    record_count=0,
                    error="No data available for the specified filters"
                )
            
            # Determine unit
            unit = self._get_unit(column_name)

            # Decide which metrics to compute: prefer intent.metrics (list), else single metric
            metrics_to_compute = None
            if getattr(intent, 'metrics', None):
                metrics_to_compute = list(intent.metrics)
            elif intent.metric:
                metrics_to_compute = [intent.metric]
            else:
                metrics_to_compute = [Metric.SUM]

            results = {}
            incomputable = []
            # For time-based metrics (trend/change) we need year aggregation
            year_series = None
            if 'year' in result_df.columns:
                year_series = result_df['year']

            # If values are tied to years, create a year->value mapping for trend/change
            if year_series is not None and len(values) > 0:
                # align years and values
                series_df = result_df[[column_name, 'year']].dropna(subset=[column_name, 'year']).copy()
                # aggregate by year (mean) for time-series metrics
                ts = series_df.groupby('year')[column_name].mean().sort_index()
            else:
                ts = None

            for m in metrics_to_compute:
                # normalize enum to string
                metric_name = m.value if isinstance(m, Metric) else str(m)
                try:
                    if metric_name == Metric.SUM.value:
                        v = values.sum()
                    elif metric_name == Metric.AVERAGE.value:
                        v = values.mean()
                    elif metric_name == Metric.MEDIAN.value:
                        v = values.median()
                    elif metric_name == Metric.MIN.value:
                        v = values.min()
                    elif metric_name == Metric.MAX.value:
                        v = values.max()
                    elif metric_name == 'std':
                        v = float(values.std(ddof=0))
                    elif metric_name == 'variance':
                        v = float(values.var(ddof=0))
                    elif metric_name == 'range':
                        v = float(values.max() - values.min())
                    elif metric_name == 'change':
                        if ts is not None and len(ts) >= 2:
                            first = float(ts.iloc[0])
                            last = float(ts.iloc[-1])
                            v = float(last - first)
                            # also store percent change
                            try:
                                pct = (last - first) / first * 100 if first != 0 else None
                            except Exception:
                                pct = None
                            if pct is not None:
                                results[f"{metric_name}_pct"] = pct
                        else:
                            v = None
                    elif metric_name == 'trend':
                        # compute linear slope (value change per year)
                        if ts is not None and len(ts) >= 2:
                            yrs = ts.index.to_numpy()
                            vals = ts.to_numpy()
                            # simple linear fit
                            coeffs = np.polyfit(yrs.astype(float), vals.astype(float), 1)
                            slope = float(coeffs[0])
                            v = slope
                        else:
                            v = None
                    else:
                        # fallback to sum for unknown
                        v = values.sum()
                except Exception as e:
                    logger.debug(f"metric computation failed for {metric_name}: {e}")
                    v = None

                if v is None or (isinstance(v, float) and pd.isna(v)):
                    results[metric_name] = None
                    incomputable.append(metric_name)
                else:
                    results[metric_name] = float(v)

            logger.info(
                f"Executed query metrics: {results} of {column_name}, records={len(values)}, filters={applied_filters}"
            )

            # Prepare ExecutionResult
            exec_result = ExecutionResult(
                value=None,
                values=results,
                unit=unit,
                applied_filters=applied_filters,
                record_count=len(values),
                incomputable_metrics=incomputable if incomputable else None
            )

            # maintain single-value compatibility when only one metric requested
            if len(results) == 1:
                single_val = next(iter(results.values()))
                exec_result.value = float(single_val) if single_val is not None else None

            return exec_result
            
        except Exception as e:
            logger.error(f"Execution error: {str(e)}")
            return ExecutionResult(
                error=f"Execution failed: {str(e)}",
                applied_filters=applied_filters if 'applied_filters' in locals() else {}
            )
    
    def _get_column_name(self, gas: Optional[Gas], sector: Optional[Sector]) -> Optional[str]:
        """
        Map gas + sector to actual column name in dataframe.
        Deterministic mapping, no LLM.
        Uses actual OWID dataset column naming conventions.
        """
        if not gas:
            return None
        
        gas_str = gas.value.lower()
        
        # OWID dataset column patterns
        # For total emissions: "co2", "co2_per_capita", "methane", etc.
        # For sector-specific: "cement_co2", "coal_co2", "oil_co2", "gas_co2", etc.
        
        if sector == Sector.TOTAL or sector is None:
            # Total emissions - try exact gas name first
            for col in self.df.columns:
                if col.lower() == gas_str:
                    return col
            # Try with common suffixes
            for suffix in ['', '_emissions', '_per_capita']:
                candidate = f"{gas_str}{suffix}"
                for col in self.df.columns:
                    if col.lower() == candidate.lower():
                        return col
        
        elif sector == Sector.CEMENT:
            # Cement sector - OWID uses "cement_co2"
            candidates = ['cement_co2', 'cement_co2_per_capita']
            for candidate in candidates:
                for col in self.df.columns:
                    if col.lower() == candidate.lower():
                        return col
            # Also try pattern matching
            for col in self.df.columns:
                if 'cement' in col.lower() and gas_str in col.lower():
                    return col
        
        elif sector == Sector.TRANSPORT:
            # Transport sector
            for col in self.df.columns:
                if 'transport' in col.lower() and gas_str in col.lower():
                    return col
        
        elif sector == Sector.ENERGY:
            # Energy sector
            for col in self.df.columns:
                if 'energy' in col.lower() and gas_str in col.lower():
                    return col
        
        elif sector == Sector.AGRICULTURE:
            # Agriculture sector
            for col in self.df.columns:
                if 'agriculture' in col.lower() or 'agricultural' in col.lower():
                    if gas_str in col.lower():
                        return col
        
        # Fallback: find any column with gas name (for total only)
        if sector == Sector.TOTAL or sector is None:
            for col in self.df.columns:
                col_lower = col.lower()
                # Match exact gas name, not as substring (avoid matching "cement_co2" when looking for "co2")
                if col_lower == gas_str or col_lower.startswith(f"{gas_str}_") or col_lower.endswith(f"_{gas_str}"):
                    # But exclude sector-specific columns
                    if 'cement' not in col_lower and 'coal' not in col_lower and 'oil' not in col_lower and 'gas' not in col_lower:
                        return col
        
        return None
    
    def _apply_metric(self, values: pd.Series, metric: Metric) -> float:
        """Apply aggregation metric deterministically."""
        if metric == Metric.SUM:
            return values.sum()
        elif metric == Metric.AVERAGE:
            return values.mean()
        elif metric == Metric.MEDIAN:
            return values.median()
        elif metric == Metric.MIN:
            return values.min()
        elif metric == Metric.MAX:
            return values.max()
        else:
            return values.sum()  # Default to sum
    
    def _get_unit(self, column_name: str) -> str:
        """Determine unit from column name."""
        if 'per_capita' in column_name.lower():
            return "tonnes per capita"
        elif 'co2' in column_name.lower():
            return "million tonnes"
        else:
            return "tonnes"


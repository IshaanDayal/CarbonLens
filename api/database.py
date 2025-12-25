"""
Database handler for OWID CO2 data.
"""
import pandas as pd
import os
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class OWIDDatabase:
    """Handler for Our World in Data CO2 dataset."""
    
    def __init__(self, data_path=None):
        """
        Initialize the database handler.
        
        Args:
            data_path: Path to the OWID CO2 data CSV file
        """
        self.data_path = data_path or settings.OWID_DATA_PATH
        self.df = None
        self._load_data()
    
    def _load_data(self):
        """Load the OWID CO2 data from CSV."""
        try:
            if not os.path.exists(self.data_path):
                logger.warning(f"Data file not found at {self.data_path}. Please download it.")
                # Create empty dataframe with expected structure
                self.df = pd.DataFrame()
                return
            
            logger.info(f"Loading data from {self.data_path}")
            self.df = pd.read_csv(self.data_path)
            logger.info(f"Loaded {len(self.df)} rows of data")
            
            # Ensure date column is datetime
            if 'year' in self.df.columns:
                self.df['year'] = pd.to_datetime(self.df['year'], format='%Y', errors='coerce')
            
        except Exception as e:
            logger.error(f"Error loading data: {str(e)}")
            self.df = pd.DataFrame()
    
    def execute_query(self, query: str) -> pd.DataFrame:
        """
        Execute a pandas query on the dataframe with robust error handling.
        
        Args:
            query: Pandas query string
            
        Returns:
            DataFrame with query results
            
        Raises:
            ValueError: If query execution fails
        """
        try:
            if self.df.empty:
                logger.warning("Attempted to query empty dataframe")
                return pd.DataFrame()
            
            if not query or not isinstance(query, str):
                logger.warning(f"Invalid query type: {type(query)}, using fallback")
                return self.df.copy()
            
            query = query.strip()
            
            # Handle 'True' query (return all data)
            if query.lower() in ['true', '']:
                return self.df.copy()
            
            # Validate query syntax before execution
            # Check for common issues
            if query.count('"') % 2 != 0:
                logger.warning(f"Unclosed double quotes in query: {query}")
                # Try to fix by adding closing quote
                query = query + '"'
            
            if query.count("'") % 2 != 0:
                logger.warning(f"Unclosed single quotes in query: {query}")
                # Try to fix by adding closing quote
                query = query + "'"
            
            # Execute query with error handling
            try:
                result = self.df.query(query)
                return result
            except pd.errors.UndefinedVariableError as e:
                logger.error(f"Undefined variable in query: {str(e)}, query: {query}")
                raise ValueError(f"Query contains undefined column or variable. Please check column names. Error: {str(e)}")
            except SyntaxError as e:
                logger.error(f"Syntax error in query: {str(e)}, query: {query}")
                raise ValueError(f"Query syntax error: {str(e)}. Please try rephrasing your question.")
            except Exception as e:
                # Catch other pandas query errors
                error_msg = str(e)
                if 'boolean label' in error_msg.lower():
                    # Common error: boolean label issue
                    logger.error(f"Boolean label error in query: {query}")
                    raise ValueError("Query format error. Please try rephrasing your question.")
                elif 'name' in error_msg.lower() and 'is not defined' in error_msg.lower():
                    logger.error(f"Name error in query: {error_msg}, query: {query}")
                    raise ValueError(f"Column or variable not found. Please check your query. Error: {error_msg}")
                else:
                    logger.error(f"Query execution error: {error_msg}, query: {query}")
                    raise ValueError(f"Query execution failed: {error_msg}")
            
        except ValueError:
            # Re-raise ValueError as-is (already formatted)
            raise
        except Exception as e:
            logger.error(f"Unexpected error executing query: {str(e)}, query: {query}")
            raise ValueError(f"Unexpected error executing query: {str(e)}")
    
    def get_columns(self) -> list:
        """Get list of available columns in the dataset."""
        if self.df is None or self.df.empty:
            return []
        return list(self.df.columns)
    
    def get_sample_data(self, n=5) -> dict:
        """Get sample data for understanding the structure."""
        if self.df is None or self.df.empty:
            return {}
        return self.df.head(n).to_dict('records')
    
    def get_countries(self) -> list:
        """Get list of unique countries in the dataset."""
        if self.df is None or self.df.empty:
            return []
        if 'country' in self.df.columns:
            return sorted(self.df['country'].unique().tolist())
        return []
    
    def get_years(self) -> list:
        """Get range of years in the dataset."""
        if self.df is None or self.df.empty:
            return []
        if 'year' in self.df.columns:
            years = self.df['year'].dropna().unique()
            return sorted([int(y.year) if hasattr(y, 'year') else int(y) for y in years])
        return []


# Global instance
_db_instance = None


def get_database():
    """Get or create the global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = OWIDDatabase()
    return _db_instance


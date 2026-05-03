import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path
from datetime import date
import logging

logger = logging.getLogger(__name__)

def load_options_ohlcv(
    underlying: str,
    start: date,
    end: date,
    data_dir: Path = Path("data/offline/options_ohlcv"),
    columns: list[str] | None = None
) -> pd.DataFrame:
    """
    Reads Parquet partitions covering [start, end] for the given underlying.
    Returns a DataFrame with columns matching the Parquet schema.
    Filters to the exact date range after reading.
    Returns empty DataFrame if no data found.
    """
    if not data_dir.exists():
        return pd.DataFrame()
        
    # Discover partitions
    partitions_to_read = []
    
    # Iterate through year directories
    for year_dir in data_dir.iterdir():
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
            
        year = int(year_dir.name)
        if year < start.year or year > end.year:
            continue
            
        # Iterate through month directories
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir() or not month_dir.name.isdigit():
                continue
                
            month = int(month_dir.name)
            
            # Check if this month overlaps with the [start, end] window
            # A month overlaps if (year, month) is between (start.year, start.month) and (end.year, end.month)
            if year == start.year and month < start.month:
                continue
            if year == end.year and month > end.month:
                continue
                
            parquet_file = month_dir / f"nifty_{year}_{month:02d}.parquet"
            if parquet_file.exists():
                partitions_to_read.append(parquet_file)
                
    if not partitions_to_read:
        return pd.DataFrame()
        
    try:
        # Read all discovered partitions
        dataset = pq.ParquetDataset(partitions_to_read)
        table = dataset.read(columns=columns)
        
        # Convert to pandas
        df = table.to_pandas()
        
        # Filter by exact date range and underlying
        mask = (df['trade_date'] >= start) & (df['trade_date'] <= end) & (df['underlying'] == underlying)
        filtered_df = df[mask]
        
        return filtered_df
    except Exception as e:
        logger.error(f"Error loading Parquet partitions: {e}")
        return pd.DataFrame()

"""
Utility functions for input/output operations such as robust CSV parsing.
"""
from io import StringIO
import csv
import pandas as pd
import streamlit as st

__all__ = ["robust_read_csv"]

def robust_read_csv(csv_text: str, has_header: bool = True) -> pd.DataFrame:
    """
    Read CSV text into a pandas DataFrame with extra error handling for malformed CSV content.
    
    Tries pandas read_csv first, then falls back to a manual CSV parsing if needed.
    """
    csv_text_stripped = csv_text.strip()
    if not csv_text_stripped:
        return pd.DataFrame()
    try:
        df = pd.read_csv(StringIO(csv_text_stripped), header=0 if has_header else None, on_bad_lines='skip', engine='python')
        return df
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except (pd.errors.ParserError, csv.Error) as err:
        st.warning(f"Pandas/CSV ParserError, attempting manual fallback: {err}. Content snippet: '{csv_text_stripped[:200]}'")
        lines = csv_text_stripped.splitlines()
        if not lines:
            return pd.DataFrame()
        try:
            try:
                dialect = csv.Sniffer().sniff(lines[0] if lines else csv_text_stripped, delimiters=",;\t|")
                reader = csv.reader(lines, dialect=dialect)
            except csv.Error:
                reader = csv.reader(lines)
            all_rows = list(reader)
        except Exception as reader_err:
            st.warning(f"CSV reader failed during fallback: {reader_err}")
            return pd.DataFrame()
        if not all_rows:
            return pd.DataFrame()
        header_row = []
        data_rows = []
        if has_header:
            header_row = all_rows[0] if all_rows else []
            data_rows = all_rows[1:] if len(all_rows) > 1 else []
        else:
            header_row = [f"col_{i}" for i in range(len(all_rows[0]))] if all_rows and all_rows[0] else []
            data_rows = all_rows
        if not header_row and data_rows:
            header_row = [f"col_{i}" for i in range(len(data_rows[0]))] if data_rows and data_rows[0] else []
        col_count = len(header_row)
        if col_count == 0:
            return pd.DataFrame(data_rows, columns=header_row) if data_rows else pd.DataFrame()
        fixed_rows = []
        for row in data_rows:
            if not row:
                continue
            if len(row) == col_count:
                fixed_rows.append(row)
            elif len(row) > col_count:
                merged_last = ",".join(row[col_count-1:])
                fixed_rows.append(row[:col_count-1] + [merged_last])
            else:
                fixed_rows.append(row + [""] * (col_count - len(row)))
        try:
            if fixed_rows:
                return pd.DataFrame(fixed_rows, columns=header_row)
            else:
                return pd.DataFrame(columns=header_row) if header_row else pd.DataFrame()
        except Exception as final_err:
            st.warning(f"Could not fully repair CSV after manual parsing: {final_err}")
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Robust CSV reading failed with unexpected error: {e}. CSV Text: {csv_text_stripped[:200]}")
        return pd.DataFrame()
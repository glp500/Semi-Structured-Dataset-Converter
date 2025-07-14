"""
Transformation logic for converting between JSON structures, DataFrames, and CSV text.
"""
import re
import json
from typing import List, Dict
from pandas import DataFrame
from utils.io import robust_read_csv

__all__ = ["merge_json_fragments", "parse_tables_from_csv"]

def merge_json_fragments(json_fragments: List[str]) -> str:
    """
    Merge multiple JSON fragment strings into a single JSON string.
    
    If multiple parts are provided (from processing PDF in chunks), each part is parsed and 
    merged into one JSON object. In case of conflicts, later keys override earlier ones.
    Non-dictionary JSON fragments are skipped with a warning.
    
    :param json_fragments: List of JSON strings.
    :return: A single merged JSON string (pretty-printed).
    """
    if not json_fragments:
        return ""
    if len(json_fragments) == 1:
        return json_fragments[0]
    merged_data: Dict = {}
    for frag in json_fragments:
        try:
            data = json.loads(frag)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            merged_data.update(data)
        else:
            continue
    try:
        return json.dumps(merged_data, indent=2)
    except Exception as e:
        return str(merged_data)

def parse_tables_from_csv(csv_response_text: str) -> Dict[str, DataFrame]:
    """
    Parse the combined CSV tables text returned by the LLM into DataFrame objects.
    
    The input text is expected to contain multiple tables delimited by 
    markers "=== START OF TABLE: [TableName] ===" and "=== END OF TABLE: [TableName] ===".
    Extracts each table's CSV content and uses robust_read_csv to parse into DataFrame.
    
    :param csv_response_text: The raw text output containing all tables.
    :return: A dictionary mapping table name to DataFrame for each parsed table.
    """
    tables: Dict[str, DataFrame] = {}
    pattern = re.compile(r"=== START OF TABLE: (.*?) ===\n(.*?)\n=== END OF TABLE: \1 ===", re.DOTALL)
    matches = pattern.findall(csv_response_text)
    for table_name, table_csv in matches:
        df = robust_read_csv(table_csv)
        if not df.empty:
            tables[table_name.strip()] = df
        else:
            tables[table_name.strip()] = df
    return tables
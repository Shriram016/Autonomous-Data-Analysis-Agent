import json
import os
from typing import Any, Dict

from src.core.planner import PlanStep
from src.prompts.planner_prompt import condense_schema


# ---------------------------------------------------------------------------
# System Prompt — versioned (same pattern as planner_prompt.py)
# ---------------------------------------------------------------------------

ACTIVE_VERSION = "v1"

_VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "versions")
_prompt_file = os.path.join(_VERSIONS_DIR, f"{ACTIVE_VERSION}_param_fixer_prompt.txt")

with open(_prompt_file, "r", encoding="utf-8") as _f:
    SYSTEM_PROMPT = _f.read()


# ---------------------------------------------------------------------------
# Per-Tool Parameter Specs — condensed, one entry per tool
# ---------------------------------------------------------------------------

TOOL_PARAM_SPECS: Dict[str, str] = {
    "date_filter": """date_filter — Filters rows within a lookback window ending at end_date.
- col_name (str): date column
- time_period (str): e.g. "3M", "10D", "1Y"
- end_date (str, optional): "YYYY-MM-DD". Defaults to column max date.""",

    "filter_by_condition": """filter_by_condition — Filters rows by a column value.
- col_name (str): column to filter
- col_type (str): "object" or "numeric"
- val_to_filter (any): exact literal value from the data — never "max", "min", or any computed value
- operator (str): "==", "!=", ">", ">=", "<", "<=". Use "==" for object columns.""",

    "extract_date_part": """extract_date_part — Extracts a date part into a new column.
- col_name (str): existing date column
- part (str): "month" (-> "January"), "year" (-> 2017), "quarter" (-> "Q1"), "day" (-> 15)
- new_col_name (str): name for the new column""",

    "column_arithmetic": """column_arithmetic — Arithmetic between two columns -> new column.
- col1, col2 (str): existing columns. For datetime subtraction, use original datetime columns only — never extract_date_part outputs.
- operation (str): "+", "-", "*", "/". Datetime columns: only "-".
- new_col_name (str): name for the result column
- is_datetime (bool): true if both columns are datetime (result = integer days). Default: false.""",

    "groupby_aggregate": """groupby_aggregate — Groups by one or more columns and aggregates.
- group_col (str or list): column(s) to group by
- agg_col (dict): {"column": "operation"}. Operations: sum/mean/count/min/max/median/std (numeric), count (object/datetime).
- Output column name = "{agg_col}_{operation}" e.g. {"Sales": "sum"} -> "Sales_sum". The group column name never appears in the output column name.""",

    "sort": """sort — Sorts by one or more columns.
- sort_col (dict): {"column": "asc"} or {"column": "desc"}""",

    "top_n": """top_n — Returns the first N rows. Always apply sort before top_n.
- N (int): number of rows > 0""",

    "select_columns": """select_columns — Keeps only specified columns, drops all others.
- col_list (list of str): columns to keep""",

    "rename_column": """rename_column — Renames columns via a mapping.
- rename_map (dict): {"old_name": "new_name"}""",

    "aggregate_column": """aggregate_column — Computes a single aggregate over an entire column — no grouping. Returns a 1-row DataFrame.
- col_name (str): column to aggregate. Must be numeric and exist in the DataFrame.
- operation (str): "sum", "mean", "min", "max", "count". Use "count" to count rows (works on any dtype).
- new_col_name (str): name for the result column. Convention: {col}_{op}, e.g. "Sales_sum".""",
}


# ---------------------------------------------------------------------------
# User Prompt Builder
# ---------------------------------------------------------------------------

def build_user_prompt(
    step: PlanStep,
    error_context: Dict[str, Any],
    query: str,
    schema: Dict[str, Any],
) -> str:
    """
    Assembles the runtime user prompt for the Param Fixer LLM.

    Args:
        step          : The PlanStep that failed.
        error_context : Dict with "message" (error/critic reason) and optionally
                         "current_columns" (dict of column -> dtype for the
                         DataFrame this step reads from).
        query         : Original user query.
        schema        : Full schema dict from Schema Generator's result field.

    Returns:
        Formatted user prompt string to send to the Param Fixer LLM.
    """
    tool_spec = TOOL_PARAM_SPECS.get(step.tool, f"{step.tool} — (no spec available)")
    current_columns = error_context.get("current_columns", {})
    condensed_schema = condense_schema(schema)

    return f"""Query: {query}

Failed step:
- tool: {step.tool}
- parameters: {json.dumps(step.parameters, indent=2)}

Error:
{error_context.get("message", "Unknown error.")}

Tool spec ({step.tool}):
{tool_spec}

Current available columns (DataFrame this step reads from):
{json.dumps(current_columns, indent=2)}

Original dataset schema (condensed, for context):
{json.dumps(condensed_schema, indent=2)}

Return the corrected "parameters" JSON now."""

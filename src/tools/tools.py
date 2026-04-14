# Central aggregator — import all tools and expose TOOL_REGISTRY.
#
# The Executor looks up tools by name using TOOL_REGISTRY:
#   tool_fn = TOOL_REGISTRY[step["tool"]]
#   result  = tool_fn(**step["parameters"])

from src.tools.date_filter import date_filter
from src.tools.filter_by_condition import filter_by_condition
from src.tools.extract_date_part import extract_date_part
from src.tools.column_arithmetic import column_arithmetic
from src.tools.groupby_aggregate import groupby_aggregate
from src.tools.sort import sort
from src.tools.top_n import top_n
from src.tools.select_columns import select_columns
from src.tools.rename_column import rename_column
from src.tools.aggregate_column import aggregate_column

TOOL_REGISTRY = {
    "date_filter": date_filter,
    "filter_by_condition": filter_by_condition,
    "extract_date_part": extract_date_part,
    "column_arithmetic": column_arithmetic,
    "groupby_aggregate": groupby_aggregate,
    "sort": sort,
    "top_n": top_n,
    "select_columns": select_columns,
    "rename_column": rename_column,
    "aggregate_column": aggregate_column,
}

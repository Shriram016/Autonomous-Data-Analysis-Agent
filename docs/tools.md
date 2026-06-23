# Tool Layer Reference

All tools live in `src/tools/`. Every tool accepts a DataFrame as its first argument and returns:

```python
{"status": "success|error", "message": str, "result": DataFrame | None}
```

The LLM selects tools and specifies parameters — it never writes pandas code directly.

---

## Tool Registry

Tools are registered in `src/tools/tools.py` as `TOOL_REGISTRY: dict[str, Callable]`. The Executor looks up each tool by name at runtime.

---

## Tools

### `date_filter`
Filter rows within a lookback window ending at a given date.

| Parameter | Type | Description |
|---|---|---|
| `df` | DataFrame | Input data |
| `col_name` | str | Date column to filter on |
| `time_period` | str | Lookback window — e.g. `"3M"`, `"1Y"`, `"6M"` |
| `end_date` | str | End of the window — `"YYYY-MM-DD"` |

**Note:** Not suitable for fixed calendar periods (e.g. Q1). Use `extract_date_part` → `filter_by_condition` for those.

---

### `filter_by_condition`
Filter rows by a single column value.

| Parameter | Type | Description |
|---|---|---|
| `df` | DataFrame | Input data |
| `col_name` | str | Column to filter on |
| `col_type` | str | `"object"` or `"numeric"` |
| `val_to_filter` | any | Value to compare against |
| `operator` | str | `"=="`, `"!="`, `">"`, `">="`, `"<"`, `"<="` |

---

### `extract_date_part`
Extract a date component into a new column.

| Parameter | Type | Description |
|---|---|---|
| `df` | DataFrame | Input data |
| `col_name` | str | Source datetime column |
| `part` | str | `"month"`, `"year"`, `"quarter"`, `"day"` |
| `new_col_name` | str | Name for the new column |

**Common pattern — quarter filtering:**
```
extract_date_part(part="quarter", new_col_name="quarter") → filter_by_condition(col_name="quarter", val_to_filter=1)
```

---

### `column_arithmetic`
Arithmetic between two columns; supports datetime subtraction (result = days).

| Parameter | Type | Description |
|---|---|---|
| `df` | DataFrame | Input data |
| `col1` | str | First column |
| `col2` | str | Second column |
| `operation` | str | `"+"`, `"-"`, `"*"`, `"/"` |
| `new_col_name` | str | Name for the result column |
| `is_datetime` | bool | Set `True` for date subtraction — result is days elapsed |

---

### `groupby_aggregate`
Group by one or more columns and aggregate. Combined into a single tool because `groupby` alone returns an unusable GroupBy object.

| Parameter | Type | Description |
|---|---|---|
| `df` | DataFrame | Input data |
| `group_col` | str or list[str] | Column(s) to group by |
| `agg_col` | dict | `{"col_name": "agg_func"}` — supports `sum`, `mean`, `count`, `min`, `max`, `median`, `std` |

**Example:**
```json
{"group_col": "Category", "agg_col": {"Sales": "sum", "Profit": "mean"}}
```

Output column names follow the pattern `{col}_{func}` (e.g. `Sales_sum`).

---

### `aggregate_column`
Single aggregate value over the whole dataset — no grouping. Returns a 1-row result.

| Parameter | Type | Description |
|---|---|---|
| `df` | DataFrame | Input data |
| `col_name` | str | Column to aggregate |
| `operation` | str | `"sum"`, `"mean"`, `"count"`, `"min"`, `"max"` |
| `new_col_name` | str | Name for the result column (e.g. `"Sales_sum"`) |

---

### `sort`
Sort by one or more columns.

| Parameter | Type | Description |
|---|---|---|
| `df` | DataFrame | Input data |
| `sort_col` | dict | `{"col_name": "asc|desc"}` |

**Example:**
```json
{"sort_col": {"Sales_sum": "desc", "Customer Name": "asc"}}
```

---

### `top_n`
Return the first N rows. Always apply `sort` before `top_n` — this tool does not sort.

| Parameter | Type | Description |
|---|---|---|
| `df` | DataFrame | Input data |
| `N` | int | Number of rows to return |

---

### `select_columns`
Keep only specified columns, drop the rest.

| Parameter | Type | Description |
|---|---|---|
| `df` | DataFrame | Input data |
| `col_list` | list[str] | Columns to keep |

---

### `rename_column`
Rename columns via a mapping.

| Parameter | Type | Description |
|---|---|---|
| `df` | DataFrame | Input data |
| `rename_map` | dict | `{"old_name": "new_name"}` |

---

## Tool Ordering Constraints

| Pattern | Why |
|---|---|
| `sort` must precede `top_n` | `top_n` takes the first N rows as-is — unsorted input gives wrong results |
| `groupby_aggregate` must precede `sort` on aggregated columns | Aggregated column names (`Sales_sum`) don't exist until after groupby |
| `extract_date_part` must precede `filter_by_condition` on date parts | The part column doesn't exist until extracted |

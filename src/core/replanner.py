from typing import Any, Dict


def replan(
    planner_output: Dict[str, Any],
    error_context: Dict[str, Any],
    query: str,
    schema: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Placeholder — not yet implemented.

    Will call the Planner LLM with the original query, schema, and error context
    to generate a completely new plan from scratch. Currently returns an error,
    so the Loop Controller will fall through to returning a partial result.

    Args:
        planner_output : The original planner output dict that failed.
        error_context  : Dict with "failed_step", "message", and "trace" so far.
        query          : Original user query.
        schema         : Condensed schema dict from Schema Generator.

    Returns:
        {"status": "success", "plan": [...]}  once implemented.
        {"status": "error",   "message": ...} currently (stub).
    """
    return {
        "status": "error",
        "message": "Replanner not yet implemented.",
    }

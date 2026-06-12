import json
import os
from typing import Any, Dict

from src.core.planner import PlanStep
from src.prompts.planner_prompt import SYSTEM_PROMPT as PLANNER_SYSTEM_PROMPT, condense_schema


# ---------------------------------------------------------------------------
# System Prompt — versioned header, prepended to the Planner's existing
# tool-catalog/rules prompt so the two never drift out of sync.
# ---------------------------------------------------------------------------

ACTIVE_VERSION = "v1"

_VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "versions")
_prompt_file = os.path.join(_VERSIONS_DIR, f"{ACTIVE_VERSION}_replanner_prompt.txt")

with open(_prompt_file, "r", encoding="utf-8") as _f:
    _REPLANNER_HEADER = _f.read()

SYSTEM_PROMPT = _REPLANNER_HEADER + PLANNER_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# User Prompt Builder
# ---------------------------------------------------------------------------

def build_user_prompt(
    query: str,
    schema: Dict[str, Any],
    error_context: Dict[str, Any],
) -> str:
    """
    Assembles the runtime user prompt for the Replanner LLM.

    Args:
        query         : Original user query.
        schema        : Full schema dict from Schema Generator's result field.
        error_context : Dict with "failed_step" (PlanStep), "message"
                         (error/critic reason), and "trace" (list of trace
                         records for every step attempted so far).

    Returns:
        Formatted user prompt string to send to the Replanner LLM.
    """
    condensed_schema = condense_schema(schema)

    failed_step: PlanStep = error_context["failed_step"]
    failed_step_summary = {
        "step": failed_step.step,
        "tool": failed_step.tool,
        "parameters": failed_step.parameters,
    }

    return f"""Query: {query}

Schema:
{json.dumps(condensed_schema, indent=2)}

Execution trace so far (every step attempted, in order):
{json.dumps(error_context.get("trace", []), indent=2, default=str)}

Step that ultimately failed:
{json.dumps(failed_step_summary, indent=2)}

Error/critic message for that step:
{error_context.get("message", "Unknown error.")}

Return a completely new JSON plan now, starting from "original_df" at step 1."""

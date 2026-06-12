import inspect
from typing import Any, Dict, List, Optional, Tuple

from groq import Groq, APIConnectionError, APIStatusError, APITimeoutError
from pydantic import BaseModel, ValidationError

from src.config import GROQ_API_KEY, PLANNER_MODEL, PLANNER_TEMPERATURE, PLANNER_MAX_TOKENS, PLANNER_TIMEOUT_SECONDS
from src.prompts.planner_prompt import SYSTEM_PROMPT, build_user_prompt
from src.tools.tools import TOOL_REGISTRY


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class PlanStep(BaseModel):
    step: int
    tool: str
    parameters: dict
    input: str
    output: str


class PlanResponse(BaseModel):
    status: str
    plan: Optional[List[PlanStep]] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Shared Parameter Validator
# ---------------------------------------------------------------------------

def validate_tool_parameters(tool_name: str, parameters: dict) -> Tuple[bool, str]:
    """
    Validates a parameters dict against a tool's actual function signature.

    Checks:
    - All required parameters are present
    - No unknown parameters are present

    Args:
        tool_name  : Name of the tool (must exist in TOOL_REGISTRY).
        parameters : The parameters dict to validate (excluding "df").

    Returns:
        (True, "")          if valid
        (False, reason_str) if invalid — reason describes missing/unknown params
    """
    tool_fn = TOOL_REGISTRY[tool_name]
    sig = inspect.signature(tool_fn)

    required_params = {
        name for name, param in sig.parameters.items()
        if param.default is inspect.Parameter.empty and name != "df"
    }
    all_params = {name for name in sig.parameters if name != "df"}
    provided_params = set(parameters.keys())

    missing = required_params - provided_params
    if missing:
        return False, f"Missing required parameters: {sorted(missing)}."

    extra = provided_params - all_params
    if extra:
        return False, (
            f"Unknown parameters: {sorted(extra)}. Accepted parameters: {sorted(all_params)}."
        )

    return True, ""


# ---------------------------------------------------------------------------
# Plan Validator (business logic checks — structure handled by Pydantic)
# ---------------------------------------------------------------------------

def _validate_plan(plan: List[PlanStep]) -> Tuple[bool, str]:
    """
    Validates business logic of the parsed plan after Pydantic structural validation.

    Checks:
    - Plan is non-empty
    - Every tool name exists in TOOL_REGISTRY
    - Every step's parameters match the tool's actual function signature (no missing, no unknown)
    - Step numbers are sequential starting from 1
    - State store input/output chain is unbroken

    Returns:
        (True, "")           if all checks pass
        (False, reason_str)  if any check fails
    """
    if not plan or len(plan) == 0:
        return False, "Plan must be a non-empty list of steps."

    # Mutual exclusion: aggregate_column collapses to 1 row — groupby_aggregate on that is always wrong
    tools_used = [step.tool for step in plan]
    if "aggregate_column" in tools_used and "groupby_aggregate" in tools_used:
        return False, (
            "Your plan uses both aggregate_column and groupby_aggregate — these two tools can never appear together. "
            "Choose exactly one based on what the query needs:\n"
            "- If the result should have one row per group (per year, per category, per region, which X had the highest Y, etc.) "
            "→ use groupby_aggregate only. Remove aggregate_column entirely.\n"
            "- If the result is a single overall number with no grouping dimension "
            "→ use aggregate_column only. Remove groupby_aggregate entirely.\n"
            "Rebuild the full correct plan using only one of these tools."
        )

    for i, step in enumerate(plan):

        # Tool name check
        if step.tool not in TOOL_REGISTRY:
            return False, (
                f"Step {i + 1} references unknown tool '{step.tool}'. "
                f"Allowed tools: {', '.join(sorted(TOOL_REGISTRY.keys()))}."
            )

        # Parameter validation — check against actual tool function signature
        is_valid_params, param_reason = validate_tool_parameters(step.tool, step.parameters)
        if not is_valid_params:
            return False, f"Step {i + 1} ({step.tool}): {param_reason}"

        # Sequential step number check
        expected_step_num = i + 1
        if step.step != expected_step_num:
            return False, (
                f"Step numbers must be sequential starting from 1. "
                f"Expected step {expected_step_num}, got {step.step}."
            )

        # State store chaining check
        if i == 0:
            if step.input != "original_df":
                return False, (
                    f"Step 1 must read from 'original_df', got '{step.input}'."
                )
        else:
            expected_input = plan[i - 1].output
            if step.input != expected_input:
                return False, (
                    f"Step {i + 1} reads from '{step.input}' but "
                    f"step {i} wrote to '{expected_input}'. Broken state store chain."
                )

    return True, ""


# ---------------------------------------------------------------------------
# Groq API Call
# ---------------------------------------------------------------------------

def _call_groq(
    user_prompt: str,
    logger=None,
    run_id: Optional[str] = None,
    error_context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calls the Groq API with the system prompt and user prompt.
    Retries once on any failure (API error or parse/validation error).

    Logs the prompt sent and raw LLM response if a logger is provided.

    Returns a PlanResponse-compatible dict on success,
    or {"status": "error", "message": "..."} on failure.
    """
    if not GROQ_API_KEY:
        return {
            "status": "error",
            "message": "GROQ_API_KEY is not set. Add it to your .env file before running the planner."
        }

    client = Groq(api_key=GROQ_API_KEY)
    last_error: Dict[str, Any] = {}

    # If a prior validation failure is provided, append it to the user prompt so the LLM can self-correct
    effective_prompt = (
        f"{user_prompt}\n\n"
        f"IMPORTANT — Your previous plan was rejected for this reason:\n"
        f"{error_context}\n"
        f"Fix this issue and return a corrected plan."
    ) if error_context else user_prompt

    # Log the prompt being sent to the LLM
    if logger and run_id:
        from src.utils.logger import log_event
        import logging as _logging
        log_event(logger, run_id, "llm_prompt_sent", {
            "model":            PLANNER_MODEL,
            "system_prompt":    SYSTEM_PROMPT,
            "user_prompt":      effective_prompt,
            "validation_retry": error_context is not None,
        }, level=_logging.DEBUG)

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=PLANNER_MODEL,
                temperature=PLANNER_TEMPERATURE,
                max_tokens=PLANNER_MAX_TOKENS,
                response_format={"type": "json_object"},
                timeout=PLANNER_TIMEOUT_SECONDS,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": effective_prompt},
                ],
            )
            raw = response.choices[0].message.content

            # Log raw LLM response
            if logger and run_id:
                from src.utils.logger import log_event
                import logging as _logging
                log_event(logger, run_id, "llm_response_received", {
                    "raw_response": raw,
                }, level=_logging.DEBUG)

            try:
                parsed = PlanResponse.model_validate_json(raw)
                return {"status": "success", "data": parsed}
            except ValidationError as e:
                last_error = {
                    "status": "error",
                    "message": f"LLM response failed Pydantic validation: {str(e)}. Raw response: {raw[:200]}"
                }
                continue

        except APITimeoutError:
            last_error = {
                "status": "error",
                "message": f"Groq API timed out after {PLANNER_TIMEOUT_SECONDS}s. No response received."
            }
            continue

        except APIConnectionError as e:
            last_error = {"status": "error", "message": f"Groq API connection failed: {str(e)}"}
            continue

        except APIStatusError as e:
            last_error = {"status": "error", "message": f"Groq API error {e.status_code}: {e.message}"}
            continue

        except Exception as e:
            last_error = {"status": "error", "message": f"Unexpected error calling Groq API: {str(e)}"}
            continue

    return last_error or {"status": "error", "message": "Groq API failed after retry."}


# ---------------------------------------------------------------------------
# Main Planner Function
# ---------------------------------------------------------------------------

def plan(
    query: str,
    schema: Dict[str, Any],
    logger=None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Converts a natural language query into a structured JSON execution plan.

    Args:
        query   : Natural language query from the user.
        schema  : Full schema dict from Schema Generator's result field.
        logger  : Optional logger instance for prompt/response logging.
        run_id  : Optional run identifier passed to logger.

    Returns one of:
        {"status": "success",    "plan": List[PlanStep]}
        {"status": "unsolvable", "reason": str}
        {"status": "error",      "message": str}
    """
    try:
        # Build the user prompt with condensed schema
        user_prompt = build_user_prompt(query, schema)

        # Call Groq API (with one retry on any failure)
        result = _call_groq(user_prompt, logger=logger, run_id=run_id)

        # If API or Pydantic validation failed, return error immediately
        if result.get("status") == "error":
            return result

        # Extract PlanResponse object from the success wrapper dict
        parsed: PlanResponse = result["data"]

        # LLM determined query is unsolvable with available tools
        if parsed.status == "unsolvable":
            reason = parsed.reason or "No reason provided."
            return {"status": "unsolvable", "reason": reason}

        # LLM returned a plan — log it before validation runs
        if parsed.status == "success":
            if logger and run_id:
                from src.utils.logger import log_event
                log_event(logger, run_id, "llm_plan_received", {
                    "attempt":      1,
                    "step_count":   len(parsed.plan),
                    "tools":        [s.tool for s in parsed.plan],
                    "plan":         [{"step": s.step, "tool": s.tool, "parameters": s.parameters} for s in parsed.plan],
                })

            is_valid, reason = _validate_plan(parsed.plan)
            if is_valid:
                return {"status": "success", "plan": parsed.plan}

            # Log why validation failed before retrying
            if logger and run_id:
                from src.utils.logger import log_event
                log_event(logger, run_id, "plan_validation_failed", {
                    "reason":        reason,
                    "retrying":      True,
                })

            # Validation failed — retry once with the error reason injected into the prompt
            retry_result = _call_groq(user_prompt, logger=logger, run_id=run_id, error_context=reason)
            if retry_result.get("status") == "error":
                return retry_result

            retry_parsed: PlanResponse = retry_result["data"]

            if retry_parsed.status == "unsolvable":
                return {"status": "unsolvable", "reason": retry_parsed.reason or "No reason provided."}

            if retry_parsed.status == "success":
                if logger and run_id:
                    from src.utils.logger import log_event
                    log_event(logger, run_id, "llm_plan_received", {
                        "attempt":    2,
                        "step_count": len(retry_parsed.plan),
                        "tools":      [s.tool for s in retry_parsed.plan],
                        "plan":       [{"step": s.step, "tool": s.tool, "parameters": s.parameters} for s in retry_parsed.plan],
                    })

                is_valid2, reason2 = _validate_plan(retry_parsed.plan)
                if not is_valid2:
                    if logger and run_id:
                        from src.utils.logger import log_event
                        log_event(logger, run_id, "plan_validation_failed", {
                            "reason":   reason2,
                            "retrying": False,
                        })
                    return {"status": "error", "message": f"Plan validation failed after retry: {reason2}"}
                return {"status": "success", "plan": retry_parsed.plan}

            return {"status": "error", "message": f"LLM returned unexpected status '{retry_parsed.status}' on retry."}

        # LLM returned an unexpected status value
        return {
            "status": "error",
            "message": (
                f"LLM returned an unexpected status '{parsed.status}'. "
                f"Expected 'success' or 'unsolvable'."
            )
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected error in planner: {str(e)}"
        }

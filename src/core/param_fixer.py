from typing import Any, Dict, Optional

from groq import Groq, APIConnectionError, APIStatusError, APITimeoutError
from pydantic import BaseModel, ValidationError

from src.config import (
    GROQ_API_KEY,
    PARAM_FIXER_MODEL,
    PARAM_FIXER_TEMPERATURE,
    PARAM_FIXER_MAX_TOKENS,
    PARAM_FIXER_TIMEOUT_SECONDS,
)
from src.core.planner import PlanStep, validate_tool_parameters
from src.prompts.param_fixer_prompt import SYSTEM_PROMPT, build_user_prompt


# ---------------------------------------------------------------------------
# Pydantic Model
# ---------------------------------------------------------------------------

class ParamFixResponse(BaseModel):
    parameters: dict


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
    Calls the Groq API with the param-fixer system prompt and user prompt.

    Logs the prompt sent and raw LLM response if a logger is provided.

    Returns a ParamFixResponse-compatible dict on success,
    or {"status": "error", "message": "..."} on failure.
    """
    if not GROQ_API_KEY:
        return {
            "status": "error",
            "message": "GROQ_API_KEY is not set. Add it to your .env file before running the param fixer."
        }

    client = Groq(api_key=GROQ_API_KEY)

    # If a prior validation failure is provided, append it so the LLM can self-correct
    effective_prompt = (
        f"{user_prompt}\n\n"
        f"IMPORTANT — Your previous correction was rejected for this reason:\n"
        f"{error_context}\n"
        f"Fix this issue and return corrected parameters."
    ) if error_context else user_prompt

    if logger and run_id:
        from src.utils.logger import log_event
        import logging as _logging
        log_event(logger, run_id, "llm_prompt_sent", {
            "model":            PARAM_FIXER_MODEL,
            "system_prompt":    SYSTEM_PROMPT,
            "user_prompt":      effective_prompt,
            "validation_retry": error_context is not None,
        }, level=_logging.DEBUG)

    try:
        response = client.chat.completions.create(
            model=PARAM_FIXER_MODEL,
            temperature=PARAM_FIXER_TEMPERATURE,
            max_tokens=PARAM_FIXER_MAX_TOKENS,
            response_format={"type": "json_object"},
            reasoning_effort="low",
            timeout=PARAM_FIXER_TIMEOUT_SECONDS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": effective_prompt},
            ],
        )
        raw = response.choices[0].message.content

        if logger and run_id:
            from src.utils.logger import log_event
            import logging as _logging
            log_event(logger, run_id, "llm_response_received", {
                "raw_response": raw,
            }, level=_logging.DEBUG)

        try:
            parsed = ParamFixResponse.model_validate_json(raw)
            return {"status": "success", "data": parsed}
        except ValidationError as e:
            return {
                "status": "error",
                "message": f"LLM response failed Pydantic validation: {str(e)}. Raw response: {raw[:200]}"
            }

    except APITimeoutError:
        return {
            "status": "error",
            "message": f"Groq API timed out after {PARAM_FIXER_TIMEOUT_SECONDS}s. No response received."
        }

    except APIConnectionError as e:
        return {"status": "error", "message": f"Groq API connection failed: {str(e)}"}

    except APIStatusError as e:
        return {"status": "error", "message": f"Groq API error {e.status_code}: {e.message}"}

    except Exception as e:
        return {"status": "error", "message": f"Unexpected error calling Groq API: {str(e)}"}


# ---------------------------------------------------------------------------
# Main Param Fixer Function
# ---------------------------------------------------------------------------

def fix_params(
    step: PlanStep,
    error_context: Dict[str, Any],
    query: str,
    schema: Dict[str, Any],
    logger=None,
    run_id: Optional[str] = None,
) -> PlanStep:
    """
    Uses an LLM to diagnose a failed step and return a corrected PlanStep
    with fixed parameters.

    Only the "parameters" field is ever changed — step/tool/input/output are
    preserved so the state-store chain stays intact.

    Falls back to returning the step UNCHANGED if:
    - GROQ_API_KEY is not set, or the Groq API call fails, or
    - the corrected parameters are still invalid after one retry.

    This graceful degradation lets the existing retry-exhaustion ->
    replanner flow handle persistent failures.

    Args:
        step          : The PlanStep that failed.
        error_context : Dict with "message" (error string) and optionally
                         "current_columns" (dict of column -> dtype for the
                         DataFrame this step reads from).
        query         : Original user query.
        schema        : Full schema dict from Schema Generator's result field.
        logger        : Optional logger instance for prompt/response logging.
        run_id        : Optional run identifier passed to logger.

    Returns:
        A PlanStep with corrected parameters, or the original step unchanged
        if the fix could not be applied.
    """
    from src.utils.logger import log_event

    try:
        user_prompt = build_user_prompt(step, error_context, query, schema)

        result = _call_groq(user_prompt, logger=logger, run_id=run_id)

        if result["status"] == "error":
            if logger and run_id:
                log_event(logger, run_id, "param_fixer_llm_failed", {"message": result["message"]})
            return step

        parsed: ParamFixResponse = result["data"]
        is_valid, reason = validate_tool_parameters(step.tool, parsed.parameters)
        if is_valid:
            return step.model_copy(update={"parameters": parsed.parameters})

        if logger and run_id:
            log_event(logger, run_id, "param_fixer_validation_failed", {"reason": reason, "retrying": True})

        # Validation failed — retry once with the error reason injected into the prompt
        retry_result = _call_groq(user_prompt, logger=logger, run_id=run_id, error_context=reason)
        if retry_result["status"] == "error":
            if logger and run_id:
                log_event(logger, run_id, "param_fixer_llm_failed", {"message": retry_result["message"]})
            return step

        retry_parsed: ParamFixResponse = retry_result["data"]
        is_valid2, reason2 = validate_tool_parameters(step.tool, retry_parsed.parameters)
        if is_valid2:
            return step.model_copy(update={"parameters": retry_parsed.parameters})

        if logger and run_id:
            log_event(logger, run_id, "param_fixer_validation_failed", {"reason": reason2, "retrying": False})
        return step

    except Exception as e:
        if logger and run_id:
            log_event(logger, run_id, "param_fixer_llm_failed", {
                "message": f"Unexpected error in param fixer: {str(e)}"
            })
        return step

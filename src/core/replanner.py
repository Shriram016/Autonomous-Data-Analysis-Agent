from typing import Any, Dict, Optional

from groq import Groq, APIConnectionError, APIStatusError, APITimeoutError
from pydantic import ValidationError

from src.config import (
    GROQ_API_KEY,
    REPLANNER_MODEL,
    REPLANNER_TEMPERATURE,
    REPLANNER_MAX_TOKENS,
    REPLANNER_TIMEOUT_SECONDS,
)
from src.core.planner import PlanResponse, _validate_plan
from src.prompts.replanner_prompt import SYSTEM_PROMPT, build_user_prompt


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
    Calls the Groq API with the replanner system prompt and user prompt.

    Logs the prompt sent and raw LLM response if a logger is provided.

    Returns a PlanResponse-compatible dict on success,
    or {"status": "error", "message": "..."} on failure.
    """
    if not GROQ_API_KEY:
        return {
            "status": "error",
            "message": "GROQ_API_KEY is not set. Add it to your .env file before running the replanner."
        }

    client = Groq(api_key=GROQ_API_KEY)

    # If a prior validation failure is provided, append it so the LLM can self-correct
    effective_prompt = (
        f"{user_prompt}\n\n"
        f"IMPORTANT — Your previous replan was rejected for this reason:\n"
        f"{error_context}\n"
        f"Fix this issue and return a corrected plan."
    ) if error_context else user_prompt

    if logger and run_id:
        from src.utils.logger import log_event
        import logging as _logging
        log_event(logger, run_id, "llm_prompt_sent", {
            "model":            REPLANNER_MODEL,
            "system_prompt":    SYSTEM_PROMPT,
            "user_prompt":      effective_prompt,
            "validation_retry": error_context is not None,
        }, level=_logging.DEBUG)

    try:
        response = client.chat.completions.create(
            model=REPLANNER_MODEL,
            temperature=REPLANNER_TEMPERATURE,
            max_tokens=REPLANNER_MAX_TOKENS,
            response_format={"type": "json_object"},
            timeout=REPLANNER_TIMEOUT_SECONDS,
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
            parsed = PlanResponse.model_validate_json(raw)
            return {"status": "success", "data": parsed}
        except ValidationError as e:
            return {
                "status": "error",
                "message": f"LLM response failed Pydantic validation: {str(e)}. Raw response: {raw[:200]}"
            }

    except APITimeoutError:
        return {
            "status": "error",
            "message": f"Groq API timed out after {REPLANNER_TIMEOUT_SECONDS}s. No response received."
        }

    except APIConnectionError as e:
        return {"status": "error", "message": f"Groq API connection failed: {str(e)}"}

    except APIStatusError as e:
        return {"status": "error", "message": f"Groq API error {e.status_code}: {e.message}"}

    except Exception as e:
        return {"status": "error", "message": f"Unexpected error calling Groq API: {str(e)}"}


# ---------------------------------------------------------------------------
# Main Replanner Function
# ---------------------------------------------------------------------------

def replan(
    planner_output: Dict[str, Any],
    error_context: Dict[str, Any],
    query: str,
    schema: Dict[str, Any],
    logger=None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Uses an LLM to generate a completely new plan from scratch after the
    original plan could not be completed.

    Args:
        planner_output : The original planner output dict that failed (unused —
                          the full execution trace in error_context supersedes it).
        error_context   : Dict with "failed_step" (PlanStep), "message"
                           (error/critic reason), and "trace" (list of trace
                           records for every step attempted so far).
        query           : Original user query.
        schema          : Full schema dict from Schema Generator's result field.
        logger          : Optional logger instance for prompt/response logging.
        run_id          : Optional run identifier passed to logger.

    Returns:
        {"status": "success",    "plan": List[PlanStep]}
        {"status": "unsolvable", "message": str}
        {"status": "error",      "message": str}
    """
    from src.utils.logger import log_event

    try:
        user_prompt = build_user_prompt(query, schema, error_context)

        result = _call_groq(user_prompt, logger=logger, run_id=run_id)

        if result["status"] == "error":
            if logger and run_id:
                log_event(logger, run_id, "replanner_llm_failed", {"message": result["message"]})
            return result

        parsed: PlanResponse = result["data"]

        if parsed.status == "unsolvable":
            reason = parsed.reason or "No reason provided."
            return {"status": "unsolvable", "message": reason}

        if parsed.status != "success":
            return {
                "status": "error",
                "message": f"LLM returned an unexpected status '{parsed.status}'. Expected 'success' or 'unsolvable'."
            }

        is_valid, reason = _validate_plan(parsed.plan)
        if is_valid:
            return {"status": "success", "plan": parsed.plan}

        if logger and run_id:
            log_event(logger, run_id, "replanner_validation_failed", {"reason": reason, "retrying": True})

        # Validation failed — retry once with the error reason injected into the prompt
        retry_result = _call_groq(user_prompt, logger=logger, run_id=run_id, error_context=reason)
        if retry_result["status"] == "error":
            if logger and run_id:
                log_event(logger, run_id, "replanner_llm_failed", {"message": retry_result["message"]})
            return retry_result

        retry_parsed: PlanResponse = retry_result["data"]

        if retry_parsed.status == "unsolvable":
            return {"status": "unsolvable", "message": retry_parsed.reason or "No reason provided."}

        if retry_parsed.status != "success":
            return {
                "status": "error",
                "message": f"LLM returned an unexpected status '{retry_parsed.status}' on retry."
            }

        is_valid2, reason2 = _validate_plan(retry_parsed.plan)
        if is_valid2:
            return {"status": "success", "plan": retry_parsed.plan}

        if logger and run_id:
            log_event(logger, run_id, "replanner_validation_failed", {"reason": reason2, "retrying": False})
        return {"status": "error", "message": f"Plan validation failed after retry: {reason2}"}

    except Exception as e:
        msg = f"Unexpected error in replanner: {str(e)}"
        if logger and run_id:
            log_event(logger, run_id, "replanner_llm_failed", {"message": msg})
        return {"status": "error", "message": msg}

from typing import Any, Dict, Optional

import pandas as pd
from groq import Groq, APIConnectionError, APIStatusError, APITimeoutError

from src.config import GROQ_API_KEY, ANSWER_MODEL, PLANNER_TIMEOUT_SECONDS
from src.utils.langfuse_helper import llm_generation


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """
You are a data analyst assistant. You will be given a user's question and the
computed result data that answers it.

Your job is to write a clear, concise answer in 2-3 sentences that:
- Directly answers the user's question
- Uses the exact numbers from the result data
- Is written in plain English for a business audience

Rules:
- Do NOT say "based on the data" or "according to the results" — just state the answer directly
- Do NOT mention technical terms like DataFrame, columns, rows, or pipeline
- Do NOT add commentary beyond what the data shows
- Round numbers sensibly (e.g. $17,512.88 not $17512.878000)
- If the result has multiple rows, summarise the key insight (e.g. highest, lowest, trend)
"""


# ---------------------------------------------------------------------------
# DataFrame Formatter
# ---------------------------------------------------------------------------

def _format_df(df: pd.DataFrame) -> str:
    """
    Converts the final DataFrame to a readable string for the LLM.
    Uses to_string() — safe since post-aggregation DFs are always small.
    """
    return df.to_string(index=False)


# ---------------------------------------------------------------------------
# Main Function
# ---------------------------------------------------------------------------

def generate_answer(
    query: str,
    final_df: pd.DataFrame,
    logger=None,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates a natural language answer from the query and result DataFrame.

    Sends the query + formatted DataFrame to the LLM and returns a plain
    English description suitable for display in the UI.

    Does NOT retry on failure — if the LLM call fails, the pipeline
    continues and returns answer=None. The DataFrame is always the source
    of truth.

    Args:
        query      : Original natural language query from the user.
        final_df   : Final output DataFrame from the executor.
        logger     : Optional logger instance.
        run_id     : Run identifier for logging.
        session_id : Optional session identifier passed to Langfuse.

    Returns:
        {"status": "success", "answer": str}
        {"status": "error",   "message": str}
    """
    if not GROQ_API_KEY:
        return {
            "status": "error",
            "message": "GROQ_API_KEY is not set.",
        }

    if final_df is None or final_df.empty:
        return {
            "status": "error",
            "message": "No result data to generate an answer from.",
        }

    user_prompt = f"""Question: {query}

Result data:
{_format_df(final_df)}

Write a 2-3 sentence answer."""

    if logger and run_id:
        from src.utils.logger import log_event
        log_event(logger, run_id, "answer_gen_started", {"query": query})

    client = Groq(api_key=GROQ_API_KEY)

    model_params = {"temperature": 0.3, "max_tokens": 256}
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    try:
        with llm_generation(
            name="answer_gen",
            model=ANSWER_MODEL,
            model_params=model_params,
            input_messages=messages,
            run_id=run_id,
            session_id=session_id,
        ) as gen:
            response = client.chat.completions.create(
                model=ANSWER_MODEL,
                timeout=PLANNER_TIMEOUT_SECONDS,
                messages=messages,
                **model_params,
            )
            answer = response.choices[0].message.content.strip()
            gen.output(answer)
            gen.usage(response.usage.prompt_tokens, response.usage.completion_tokens, response.usage.total_tokens)

        if logger and run_id:
            from src.utils.logger import log_event
            log_event(logger, run_id, "answer_gen_completed", {"answer": answer})

        return {"status": "success", "answer": answer}

    except APITimeoutError:
        msg = f"Answer generator timed out after {PLANNER_TIMEOUT_SECONDS}s."
    except APIConnectionError as e:
        msg = f"Answer generator connection failed: {str(e)}"
    except APIStatusError as e:
        msg = f"Answer generator API error {e.status_code}: {e.message}"
    except Exception as e:
        msg = f"Answer generator unexpected error: {type(e).__name__}: {str(e)}"

    if logger and run_id:
        from src.utils.logger import log_event
        log_event(logger, run_id, "answer_gen_failed", {"message": msg})

    return {"status": "error", "message": msg}

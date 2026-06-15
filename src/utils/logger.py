import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Log verbosity controls
# ---------------------------------------------------------------------------

# Set to True to include full system prompt and user prompt in the log file.
# Useful for debugging prompt changes; kept False by default to keep logs readable.
LOG_LLM_PROMPTS: bool = False


# ---------------------------------------------------------------------------
# Console Formatter — compact, no timestamp
# ---------------------------------------------------------------------------

class _ConsoleFormatter(logging.Formatter):
    """
    [run_id] EVENT_TYPE  -> detail
    """
    def format(self, record: logging.LogRecord) -> str:
        run_id  = getattr(record, "run_id", "unknown")
        event   = getattr(record, "event", "log").upper().replace("_", " ")
        payload = getattr(record, "payload", {})
        detail  = _summarise(event.lower().replace(" ", "_"), payload)
        return f"[{run_id}] {event:<22} -> {detail}"


# ---------------------------------------------------------------------------
# File Formatter — timestamped, expanded detail for key events
# ---------------------------------------------------------------------------

class _FileFormatter(logging.Formatter):
    """
    Writes timestamped plain-text lines to the .log file.
    Key events (plan, errors) get expanded multi-line output.
    """
    def format(self, record: logging.LogRecord) -> str:
        run_id   = getattr(record, "run_id", "unknown")
        event    = getattr(record, "event", "log")
        payload  = getattr(record, "payload", {})
        ts       = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        label    = event.upper().replace("_", " ")
        detail   = _summarise(event, payload)

        lines = [f"{ts}  [{run_id}] {label:<22} -> {detail}"]

        # Expand plan steps
        if event == "plan_generated":
            for s in payload.get("steps", []):
                lines.append(f"             step {s['step']}: {s['tool']}")
                for k, v in s.get("parameters", {}).items():
                    lines.append(f"                  {k}: {v}")

        # Expand LLM prompt (file only — too long for console)
        if event == "llm_prompt_sent" and LOG_LLM_PROMPTS:
            lines.append(f"             model: {payload.get('model', '?')}")
            lines.append(f"             --- SYSTEM PROMPT ---")
            for line in payload.get("system_prompt", "").splitlines():
                lines.append(f"             {line}")
            lines.append(f"             --- END SYSTEM PROMPT ---")
            lines.append(f"             --- USER PROMPT ---")
            for line in payload.get("user_prompt", "").splitlines():
                lines.append(f"             {line}")
            lines.append(f"             --- END USER PROMPT ---")

        # Expand raw LLM response
        if event == "llm_response_received" and LOG_LLM_PROMPTS:
            lines.append(f"             --- LLM RESPONSE ---")
            for line in payload.get("raw_response", "").splitlines():
                lines.append(f"             {line}")
            lines.append(f"             --- END RESPONSE ---")

        # Expand LLM reasoning — always shown when present (short, useful for debugging)
        if event == "llm_response_received" and payload.get("reasoning"):
            lines.append(f"             --- REASONING ---")
            for line in payload["reasoning"].splitlines():
                lines.append(f"             {line}")
            lines.append(f"             --- END REASONING ---")

        # Expand planner completed — show full plan in file
        if event == "planner_completed":
            for s in payload.get("steps", []):
                lines.append(f"             step {s['step']}: {s['tool']}")
                for k, v in s.get("parameters", {}).items():
                    lines.append(f"                  {k}: {v}")

        # Expand tool call started — full params on separate lines (file only)
        if event == "tool_call_started":
            for k, v in payload.get("parameters", {}).items():
                lines.append(f"               {k}: {v}")

        # Expand error detail
        if event in (
            "pipeline_error", "pipeline_crash",
            "planner_failed", "schema_gen_failed", "data_loader_failed",
            # "loop_controller_failed",  # V1 loop_controller.py superseded by graph.py (V2)
            "replanner_failed",
        ):
            msg = payload.get("message", "")
            if msg:
                lines.append(f"             ERROR: {msg}")

        # Expand answer generator completed — full answer in file
        if event == "answer_gen_completed":
            lines.append(f"             --- ANSWER ---")
            for line in payload.get("answer", "").splitlines():
                lines.append(f"             {line}")
            lines.append(f"             --- END ANSWER ---")

        # Expand final result — show preview rows (file only)
        if event == "final_result":
            lines.append(f"             columns: {', '.join(payload.get('columns', []))}")
            for i, row in enumerate(payload.get("preview", [])):
                lines.append(f"             row {i+1}: {row}")

        # Expand step error
        if event == "step_executed" and payload.get("status") == "error":
            msg = payload.get("message", "")
            if msg:
                lines.append(f"             ERROR: {msg}")

        # Expand execute_step_node failure
        if event == "execute_step_failed":
            msg = payload.get("message", "")
            if msg:
                lines.append(f"             ERROR: {msg}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Shared Summary Builder
# ---------------------------------------------------------------------------

def _summarise(event: str, payload: Dict[str, Any]) -> str:
    # LLM internals
    if event == "llm_prompt_sent":
        return f'model={payload.get("model", "?")} | sending prompt to LLM'
    if event == "llm_response_received":
        return f'received {len(payload.get("raw_response", ""))} chars from LLM'

    # Query
    if event == "query_received":
        return f'"{payload.get("query", "")}" | session={payload.get("session_id", "?")}'

    # Data Loader
    if event == "data_loader_started":
        return payload.get("path", "?")
    if event == "data_loader_completed":
        return f'{payload.get("rows", "?")} rows x {payload.get("cols", "?")} cols'
    if event == "data_loader_failed":
        return payload.get("message", "unknown error")

    # Schema Generator
    if event == "schema_gen_started":
        return f'{payload.get("rows", "?")} rows x {payload.get("cols", "?")} cols'
    if event == "schema_gen_completed":
        return f'{payload.get("column_count", "?")} columns'
    if event == "schema_gen_failed":
        return payload.get("message", "unknown error")

    # Planner
    if event == "planner_started":
        return f'"{payload.get("query", "")}"'
    if event == "planner_completed":
        return f'{payload.get("step_count", "?")} steps | {payload.get("plan_summary", "")}'
    if event == "planner_failed":
        return payload.get("message", "unknown error")
    if event == "planner_unsolvable":
        return payload.get("reason", "no reason provided")

    # Loop Controller (V1 — superseded by graph.py / nodes.py in V2)
    # if event == "loop_controller_started":
    #     return f'{payload.get("step_count", "?")} steps | max {payload.get("max_executions", "?")} executions'
    # if event == "loop_controller_completed":
    #     return f'success | {payload.get("total_executions", "?")} executions'
    # if event == "loop_controller_failed":
    #     return payload.get("message", "unknown error")

    # Tool call lifecycle
    if event == "tool_call_started":
        tool   = payload.get("tool", "?")
        step   = payload.get("step", "?")
        shape  = payload.get("input_shape")
        shape_s = f"{shape[0]} rows x {shape[1]} cols" if shape else "?"
        params = ", ".join(f"{k}={v}" for k, v in payload.get("parameters", {}).items())
        return f"step {step} | {tool} | input: {shape_s} | params: {params}"
    if event == "tool_call_completed":
        tool    = payload.get("tool", "?")
        step    = payload.get("step", "?")
        status  = payload.get("status", "?").upper()
        shape   = payload.get("output_shape")
        shape_s = f"{shape[0]} rows x {shape[1]} cols" if shape else "no output"
        return f"step {step} | {tool} | {status} | output: {shape_s}"

    # Execute Step Node (V2)
    if event == "execute_step_started":
        step   = payload.get("step", "?")
        tool   = payload.get("tool", "?")
        params = ", ".join(f"{k}={v}" for k, v in payload.get("parameters", {}).items())
        return f"step {step} | {tool} | params: {params}"
    if event == "execute_step_completed":
        step    = payload.get("step", "?")
        tool    = payload.get("tool", "?")
        shape   = payload.get("output_shape")
        shape_s = f"{shape[0]} rows x {shape[1]} cols" if shape else "no output"
        return f"step {step} | {tool} | SUCCESS | output: {shape_s}"
    if event == "execute_step_failed":
        step = payload.get("step", "?")
        tool = payload.get("tool", "?")
        return f"step {step} | {tool} | FAIL | {payload.get('message', 'unknown error')}"

    # Param Fixer / Replanner Nodes (V2)
    if event == "param_fixer_started":
        return f"step {payload.get('step', '?')} | {payload.get('tool', '?')} | error: {payload.get('message', '')}"
    if event == "param_fixer_completed":
        params = ", ".join(f"{k}={v}" for k, v in payload.get("parameters", {}).items())
        return f"step {payload.get('step', '?')} | {payload.get('tool', '?')} | new params: {params}"
    if event == "param_fixer_validation_failed":
        retrying = "retrying" if payload.get("retrying") else "giving up"
        return f"{payload.get('reason', 'unknown error')} | {retrying}"
    if event == "param_fixer_llm_failed":
        return payload.get("message", "unknown error")
    if event == "replanner_started":
        return f"failed step {payload.get('failed_step', '?')} | {payload.get('tool', '?')} | error: {payload.get('message', '')}"
    if event == "replanner_completed":
        return f"{payload.get('step_count', '?')} steps | {payload.get('plan_summary', '')}"
    if event == "replanner_failed":
        return payload.get("message", "unknown error")
    if event == "replanner_validation_failed":
        retrying = "retrying" if payload.get("retrying") else "giving up"
        return f"{payload.get('reason', 'unknown error')} | {retrying}"
    if event == "replanner_llm_failed":
        return payload.get("message", "unknown error")

    # Step execution
    if event == "step_executed":
        step    = payload.get("step", "?")
        tool    = payload.get("tool", "?")
        status  = payload.get("status", "?").upper()
        critic  = payload.get("critic", "?")
        shape   = payload.get("output_shape")
        shape_s = f"{shape[0]} rows x {shape[1]} cols" if shape else "no output"
        return f"step {step} | {tool} | {status} | critic: {critic} | {shape_s}"

    # Answer generator
    if event == "answer_gen_started":
        return f'generating answer for: "{payload.get("query", "")}"'
    if event == "answer_gen_completed":
        answer = payload.get("answer", "")
        return answer[:120] + "..." if len(answer) > 120 else answer
    if event == "answer_gen_failed":
        return payload.get("message", "unknown error")

    # Final result
    if event == "final_result":
        shape = payload.get("shape")
        cols  = payload.get("columns", [])
        shape_s = f"{shape[0]} rows x {shape[1]} cols" if shape else "?"
        return f"{shape_s} | columns: {', '.join(cols)}"

    # Pipeline outcome
    if event == "pipeline_complete":
        return (
            f'status=success | '
            f'executions={payload.get("total_executions")} | '
            f'steps={payload.get("steps_in_plan")}'
        )
    if event == "pipeline_error":
        return payload.get("message", "unknown error")
    if event == "pipeline_crash":
        return payload.get("message", "unknown error")

    return str(payload)


# ---------------------------------------------------------------------------
# Logger Factory
# ---------------------------------------------------------------------------

def get_logger(run_id: str) -> logging.Logger:
    """
    Returns a logger configured for a single pipeline run.

    Handlers:
        - Console              : compact pretty-printed, no timestamp, INFO level
        - logs/run_<id>.log    : timestamped plain text, expanded detail, DEBUG level
    """
    logger = logging.getLogger(f"adaa.{run_id}")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(_ConsoleFormatter())
    logger.addHandler(console_handler)

    # Plain text .log file handler
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    log_path = LOGS_DIR / f"run_{timestamp}.log"
    file_handler = logging.FileHandler(str(log_path), mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_FileFormatter())
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger


# ---------------------------------------------------------------------------
# Log Helper
# ---------------------------------------------------------------------------

def log_event(
    logger: logging.Logger,
    run_id: str,
    event: str,
    payload: Optional[Dict[str, Any]] = None,
    level: int = logging.INFO,
) -> None:
    extra = {"run_id": run_id, "event": event, "payload": payload or {}}
    logger.log(level, event, extra=extra)

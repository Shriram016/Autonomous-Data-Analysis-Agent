"""
Langfuse observability helper — V2 §3.

Provides a singleton Langfuse client and a context manager for wrapping a
single LLM ("generation") call so it appears as a nested observation under
the graph-level trace started in src/core/pipeline.py.

Everything here is a no-op when LANGFUSE_ENABLED is False (no API keys
configured) — callers don't need to branch on that themselves.
"""

from contextlib import contextmanager, nullcontext
from typing import Any, Dict, List, Optional

from src.config import LANGFUSE_ENABLED, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST


_client = None


def get_langfuse_client():
    """
    Returns a singleton Langfuse client, or None if LANGFUSE_ENABLED is False.
    """
    global _client
    if not LANGFUSE_ENABLED:
        return None
    if _client is None:
        from langfuse import Langfuse
        _client = Langfuse(
            public_key=LANGFUSE_PUBLIC_KEY,
            secret_key=LANGFUSE_SECRET_KEY,
            host=LANGFUSE_HOST,
        )
    return _client


def trace_id_for_run(run_id: str) -> Optional[str]:
    """
    Deterministic 32-hex-char Langfuse trace ID derived from `run_id`, so the
    same run always maps to the same Langfuse trace. Returns None if Langfuse
    is disabled.
    """
    client = get_langfuse_client()
    if client is None:
        return None
    return client.create_trace_id(seed=run_id)


# ---------------------------------------------------------------------------
# Generation wrappers
# ---------------------------------------------------------------------------

class _NoOpGeneration:
    def output(self, *args, **kwargs) -> None:
        pass

    def usage(self, *args, **kwargs) -> None:
        pass

    def metadata(self, *args, **kwargs) -> None:
        pass

    def error(self, *args, **kwargs) -> None:
        pass


class _Generation:
    def __init__(self, observation, initial_metadata: Dict[str, Any]):
        self._observation = observation
        self._metadata = dict(initial_metadata)

    def output(self, text: str) -> None:
        self._observation.update(output=text)

    def usage(self, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
        self._observation.update(usage_details={
            "input": prompt_tokens,
            "output": completion_tokens,
            "total": total_tokens,
        })

    def metadata(self, extra: Dict[str, Any]) -> None:
        self._metadata.update(extra)
        self._observation.update(metadata=self._metadata)

    def error(self, message: str) -> None:
        self._observation.update(level="ERROR", status_message=message)


class _NoOpSpan:
    def error(self, *args, **kwargs) -> None:
        pass


class _Span:
    def __init__(self, observation):
        self._observation = observation

    def error(self, message: str) -> None:
        self._observation.update(level="ERROR", status_message=message)


@contextmanager
def graph_trace(run_id: Optional[str], session_id: Optional[str]):
    """
    Context manager for the graph-level Langfuse trace wrapping one
    run_pipeline() call.

    Yields a list of callbacks to pass as `config["callbacks"]` to
    `graph.invoke()` — empty when LANGFUSE_ENABLED is False, so `config` is
    unchanged from today.

    When enabled: opens a root span with `trace_id = create_trace_id(seed=run_id)`
    and propagates `session_id` to it and every nested observation — the
    per-node spans LangGraph emits via the CallbackHandler, and the
    per-LLM-call generations from `llm_generation()`.
    """
    client = get_langfuse_client()
    if client is None:
        yield []
        return

    from langfuse import propagate_attributes
    from langfuse.langchain import CallbackHandler

    trace_context = {"trace_id": client.create_trace_id(seed=run_id)} if run_id else None
    session_ctx = propagate_attributes(session_id=session_id) if session_id else nullcontext()

    with session_ctx:
        with client.start_as_current_observation(
            as_type="span",
            name="pipeline_run",
            trace_context=trace_context,
            metadata={"run_id": run_id},
        ) as pipeline_obs:
            try:
                yield [CallbackHandler()]
            except Exception as e:
                pipeline_obs.update(level="ERROR", status_message=str(e))
                raise


@contextmanager
def llm_generation(
    name: str,
    model: str,
    model_params: Dict[str, Any],
    input_messages: List[Dict[str, str]],
    run_id: Optional[str],
    session_id: Optional[str],
    extra_metadata: Optional[Dict[str, Any]] = None,
):
    """
    Wraps a single Groq `chat.completions.create()` call as a Langfuse
    "generation" observation.

    Usage:
        with llm_generation(
            name="planner", model=PLANNER_MODEL,
            model_params={"temperature": 0.0, "max_tokens": 2048},
            input_messages=[{"role": "system", "content": ...}, {"role": "user", "content": ...}],
            run_id=run_id, session_id=session_id,
        ) as gen:
            response = client.chat.completions.create(...)
            gen.output(response.choices[0].message.content)
            gen.usage(response.usage.prompt_tokens, response.usage.completion_tokens, response.usage.total_tokens)

    On exception, the observation is marked `level="ERROR"` before re-raising.
    No-op (yields a stub with the same `.output()`/`.usage()` interface) when
    LANGFUSE_ENABLED is False.
    """
    client = get_langfuse_client()
    if client is None:
        yield _NoOpGeneration()
        return

    from langfuse import propagate_attributes

    metadata: Dict[str, Any] = {"run_id": run_id}
    if session_id:
        metadata["session_id"] = session_id
    if extra_metadata:
        metadata.update(extra_metadata)

    obs_kwargs: Dict[str, Any] = dict(
        as_type="generation",
        name=name,
        model=model,
        model_parameters=model_params,
        input=input_messages,
        metadata=metadata,
    )
    if run_id:
        obs_kwargs["trace_context"] = {"trace_id": client.create_trace_id(seed=run_id)}

    session_ctx = propagate_attributes(session_id=session_id) if session_id else nullcontext()

    with session_ctx:
        with client.start_as_current_observation(**obs_kwargs) as observation:
            try:
                yield _Generation(observation, metadata)
            except Exception as e:
                observation.update(level="ERROR", status_message=str(e))
                raise


@contextmanager
def tool_span(
    name: str,
    input_data: Dict[str, Any],
    run_id: Optional[str],
    session_id: Optional[str],
):
    """
    Wraps a single tool execution as a Langfuse "span" observation.

    Usage:
        with tool_span(name="tool:aggregate_column", input_data={...},
                       run_id=run_id, session_id=session_id) as span:
            result = _run_step(step, state_store, ...)
            if result["status"] == "error":
                span.error(result["message"])

    Unhandled exceptions are marked level="ERROR" automatically before
    re-raising. No-op when LANGFUSE_ENABLED is False.
    """
    client = get_langfuse_client()
    if client is None:
        yield _NoOpSpan()
        return

    from langfuse import propagate_attributes

    metadata: Dict[str, Any] = {"run_id": run_id}
    if session_id:
        metadata["session_id"] = session_id

    obs_kwargs: Dict[str, Any] = dict(
        as_type="span",
        name=name,
        input=input_data,
        metadata=metadata,
    )
    if run_id:
        obs_kwargs["trace_context"] = {"trace_id": client.create_trace_id(seed=run_id)}

    session_ctx = propagate_attributes(session_id=session_id) if session_id else nullcontext()

    with session_ctx:
        with client.start_as_current_observation(**obs_kwargs) as observation:
            try:
                yield _Span(observation)
            except Exception as e:
                observation.update(level="ERROR", status_message=str(e))
                raise

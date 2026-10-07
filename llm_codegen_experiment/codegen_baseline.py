"""
llm_codegen_experiment/codegen_baseline.py -- Part D, system 2: the "LLM writes pandas code" baseline.

This is the common "chat with your CSV" approach, built ONLY to compare against ADAA's
constrained-tools design (see docs/v2-polish-plan.md, Part D). It is not part of the agent.

    question (+ the last 3 earlier questions) + the same condensed schema ADAA's planner sees
        -> ONE LLM call (same model and settings as the ADAA planner) writes pandas code
        -> static safety check -> run in a restricted subprocess (timeout)
        -> `result` (DataFrame / Series / number) becomes the final table

Deliberately simple: a single LLM call, no retry, no critic, no answer-writing step.

SECURITY NOTE: this is a *restricted exec*, not a real sandbox. It combines (1) a static AST check that
rejects imports, dunder/underscore attributes, file/network/eval calls; (2) a whitelist of builtins and
only `pd`, `np` and `df` in scope; (3) a separate process with a timeout. That is adequate for an
experiment on a public dataset run by us. It is NOT safe for untrusted users: Python introspection
escapes are hard to rule out completely and there is no memory limit on Windows. That gap is exactly
what ADAA's constrained tools avoid, and the write-up should say so.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import io
import json
import multiprocessing
import os
import re
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

SYSTEM_PROMPT = """You are a data analyst. Write Python (pandas) code that answers the user's question about a DataFrame named `df`.

Rules:
- `pd` (pandas) and `np` (numpy) are already imported. Do not import anything.
- The data is the DataFrame `df`. Its columns and types are described in the schema below. Do not read or write files, use the network, or call eval, exec or open.
- Store the final answer in a variable named `result`: a pandas DataFrame (preferred), a Series, or a single number.
- The answer must be ONE table (or one number). If the question asks for two or more separate results that cannot form one table (for example, a total plus a separate ranking, or two different breakdowns), do not write code. Reply with exactly one line: REFUSE: <short reason>.
- If earlier questions are shown, use them to resolve follow-ups such as "what about 2015?".
- Otherwise return only the code, inside one ```python block. No explanation."""

CODEGEN_VERSION = "2026-10-07-v2"   # v2: adds the one-table contract and the REFUSE option
HISTORY_WINDOW = 3          # same as ADAA: the last 3 earlier questions
SANDBOX_TIMEOUT_S = 30.0

# ---------------------------------------------------------------------------
# Static safety check
# ---------------------------------------------------------------------------

_DENY_NAMES = {
    "exec", "eval", "compile", "open", "input", "__import__", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "breakpoint", "help", "exit", "quit", "memoryview",
    "type", "super", "classmethod", "staticmethod", "property",
}
_DENY_ATTRS = {
    # file / network input and output
    "read_csv", "read_excel", "read_json", "read_pickle", "read_sql", "read_sql_query", "read_sql_table",
    "read_parquet", "read_html", "read_clipboard", "read_hdf", "read_feather", "read_table", "read_fwf",
    "read_stata", "read_sas", "read_spss", "read_orc", "read_xml", "read_gbq",
    "to_csv", "to_excel", "to_json", "to_pickle", "to_sql", "to_parquet", "to_html", "to_clipboard",
    "to_hdf", "to_feather", "to_stata", "to_latex", "to_markdown", "to_xml", "to_orc", "to_gbq",
    "load", "loads", "save", "savez", "savetxt", "fromfile", "tofile", "genfromtxt", "loadtxt", "memmap",
    # code evaluation
    "eval", "query", "exec",
    # modules that give access to the rest of Python
    "io", "compat", "util", "testing", "lib", "ctypeslib", "f2py", "distutils", "os", "sys",
    "subprocess", "builtins", "importlib", "ctypes", "pickle", "shutil", "pathlib", "system", "popen",
    "environ", "getenv", "urlopen", "style",
}
_DENY_NODES = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.Global, ast.Nonlocal,
               ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)


_QUERY_CHARS = re.compile(r"^[\w\s<>=!&|()~,.+\-*/%\[\]]*$")


def safe_query_string(expr: str) -> bool:
    """
    `df.query("...")` evaluates its string, so it is only allowed when the string is plainly safe:
    column names (also in backticks), quoted values, numbers, comparison and boolean operators.
    No `@` variable access, no dunder names, no attribute/method access, no function calls.
    """
    s = re.sub(r"`[^`]*`", " COL ", expr)                     # backticked column names
    s = re.sub(r"'[^']*'|\"[^\"]*\"", " STR ", s)            # quoted values are data, not code
    if "@" in s or "__" in s:
        return False
    if re.search(r"\.\s*[A-Za-z_]", s):                       # Sales.abs(), a.b
        return False
    s = re.sub(r"\b(and|or|not|in)\b", " ~ ", s)             # keywords may be followed by "(" ("~" stops "Year in (" looking like a call)
    if re.search(r"\w\s*\(", s):                             # a function call such as abs(x)
        return False
    return bool(_QUERY_CHARS.match(s))


def _approved_query_calls(tree: ast.AST) -> set:
    """Attribute nodes of `x.query("<safe literal>")` calls with no extra arguments."""
    approved = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "query"
                and len(node.args) == 1 and not node.keywords
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
                and safe_query_string(node.args[0].value)):
            approved.add(id(node.func))
    return approved


def check_code(code: str) -> Optional[str]:
    """Return a reason string if the code must not be run, or None if it passes the static check."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"syntax error: {e.msg} (line {e.lineno})"
    approved_query = _approved_query_calls(tree)
    for node in ast.walk(tree):
        if isinstance(node, _DENY_NODES):
            return f"not allowed: {type(node).__name__}"
        if isinstance(node, ast.Name) and node.id in _DENY_NAMES:
            return f"not allowed: name '{node.id}'"
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                return f"not allowed: attribute '{node.attr}' (private or dunder)"
            if node.attr in _DENY_ATTRS and id(node) not in approved_query:
                return f"not allowed: attribute '{node.attr}'"
    return None


# ---------------------------------------------------------------------------
# Restricted execution (separate process, timeout)
# ---------------------------------------------------------------------------

_SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float", "frozenset", "int",
    "isinstance", "iter", "len", "list", "map", "max", "min", "next", "pow", "print", "range", "repr",
    "reversed", "round", "set", "slice", "sorted", "str", "sum", "tuple", "zip", "chr", "ord",
    "Exception", "ValueError", "KeyError", "TypeError", "IndexError", "ZeroDivisionError", "ArithmeticError",
]


def _safe_builtins() -> Dict[str, Any]:
    return {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES}


def normalize_result(res: Any) -> pd.DataFrame:
    """Turn the generated code's `result` into a DataFrame the eval comparator understands."""
    if isinstance(res, pd.DataFrame):
        df = res
    elif isinstance(res, pd.Series):
        df = res.rename(res.name if res.name is not None else "value").to_frame()
    elif isinstance(res, (bool, int, float, str, np.integer, np.floating, np.bool_)):
        return pd.DataFrame({"result": [res.item() if hasattr(res, "item") else res]})
    else:
        raise TypeError(f"`result` must be a DataFrame, Series or number, got {type(res).__name__}")
    if isinstance(df.index, pd.MultiIndex) or df.index.name is not None:
        df = df.reset_index()  # group keys live in the index after groupby; keep them as columns
    return df.reset_index(drop=True)


def _child(conn, code: str, df: pd.DataFrame) -> None:
    """Runs in the sandbox process. Sends ("ok", DataFrame, stdout) or ("error", message, stdout)."""
    out = io.StringIO()
    try:
        namespace = {"pd": pd, "np": np, "df": df, "__builtins__": _safe_builtins()}
        with contextlib.redirect_stdout(out):
            exec(compile(code, "<generated>", "exec"), namespace)  # noqa: S102 - restricted by design
        if "result" not in namespace:
            raise NameError("the code did not assign a variable named `result`")
        conn.send(("ok", normalize_result(namespace["result"]), out.getvalue()[:2000]))
    except BaseException as e:  # noqa: BLE001
        conn.send(("error", f"{type(e).__name__}: {e}"[:500], out.getvalue()[:2000]))
    finally:
        conn.close()


def run_sandboxed(code: str, df: pd.DataFrame, timeout_s: float = SANDBOX_TIMEOUT_S) -> Dict[str, Any]:
    """
    Check the code, then run it in a separate process with a timeout.
    Returns {"status": "ok"|"blocked"|"error"|"timeout", "result": DataFrame|None, "message": str, "stdout": str}.
    """
    reason = check_code(code)
    if reason:
        return {"status": "blocked", "result": None, "message": reason, "stdout": ""}

    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child, args=(child, code, df.copy()), daemon=True)
    proc.start()
    child.close()
    try:
        if parent.poll(timeout_s):
            kind, payload, stdout = parent.recv()
            return {"status": kind, "result": payload if kind == "ok" else None,
                    "message": "" if kind == "ok" else payload, "stdout": stdout}
        return {"status": "timeout", "result": None, "message": f"timed out after {timeout_s:.0f}s", "stdout": ""}
    except EOFError:
        return {"status": "error", "result": None, "message": "sandbox process died without a result", "stdout": ""}
    finally:
        if proc.is_alive():
            proc.terminate()
        proc.join(timeout=5)
        parent.close()


# ---------------------------------------------------------------------------
# Prompt, LLM call, code extraction
# ---------------------------------------------------------------------------

_CODE_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(text: str) -> str:
    """The first fenced code block; if there is no fence, the whole reply."""
    m = _CODE_FENCE.search(text or "")
    return (m.group(1) if m else (text or "")).strip()


_REFUSE = re.compile(r"^\s*REFUSE\s*:\s*(.*)", re.IGNORECASE | re.DOTALL)


def extract_refusal(text: str) -> Optional[str]:
    """If the reply is a refusal (`REFUSE: <reason>` at the start), return the reason; otherwise None."""
    m = _REFUSE.match(text or "")
    if not m:
        return None
    return (m.group(1).strip().splitlines() or [""])[0].strip() or "no reason given"


def build_user_prompt(query: str, schema: Dict[str, Any], previous_questions: Optional[List[str]] = None) -> str:
    """Same information ADAA's planner gets: the question, earlier questions, the condensed schema."""
    from src.prompts.planner_prompt import condense_schema
    parts = [f"Question: {query}"]
    if previous_questions:
        numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(previous_questions, start=1))
        parts.append(f"Previous questions in this session (most recent last):\n{numbered}")
    parts.append("Schema of `df`:\n" + json.dumps(condense_schema(schema), indent=2))
    parts.append("Write the code now.")
    return "\n\n".join(parts)


def _call_llm(user_prompt: str, run_id: str) -> Tuple[Optional[str], Optional[str]]:
    """One Groq call with the same model and settings as the ADAA planner. Returns (text, error)."""
    from groq import Groq
    from src.config import GROQ_API_KEY, PLANNER_MODEL, PLANNER_TEMPERATURE, PLANNER_MAX_TOKENS, PLANNER_TIMEOUT_SECONDS
    from src.utils.langfuse_helper import llm_generation

    if not GROQ_API_KEY:
        return None, "GROQ_API_KEY is not set"
    params = {"temperature": PLANNER_TEMPERATURE, "max_tokens": PLANNER_MAX_TOKENS, "reasoning_effort": "low"}
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
    try:
        client = Groq(api_key=GROQ_API_KEY)
        with llm_generation(name="codegen", model=PLANNER_MODEL, model_params=params, input_messages=messages,
                            run_id=run_id, session_id=None) as gen:
            resp = client.chat.completions.create(model=PLANNER_MODEL, timeout=PLANNER_TIMEOUT_SECONDS,
                                                  messages=messages, **params)
            text = resp.choices[0].message.content or ""
            gen.output(text)
            gen.usage(resp.usage.prompt_tokens, resp.usage.completion_tokens, resp.usage.total_tokens)
            if not text.strip():
                gen.error(f"empty reply (finish_reason={resp.choices[0].finish_reason})")
                return None, f"empty reply (finish_reason={resp.choices[0].finish_reason})"
        return text, None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:200]}"


# ---------------------------------------------------------------------------
# Pipeline-compatible entry point (the eval harness calls this instead of run_pipeline)
# ---------------------------------------------------------------------------

_DF: Optional[pd.DataFrame] = None
_SCHEMA: Optional[Dict[str, Any]] = None
_HISTORY: Dict[str, List[str]] = {}


def _load() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    global _DF, _SCHEMA
    if _DF is None:
        from src.utils.data_loader import load_dataset, DATE_COLUMNS
        from src.core.schema_gen import generate_schema
        _DF = load_dataset()
        _SCHEMA = generate_schema(_DF, required_date_columns=DATE_COLUMNS)["result"]
    return _DF, _SCHEMA


def run_codegen(query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Answer `query` the code-writing way. Returns a dict shaped like run_pipeline's result so the existing
    eval harness (compare, metrics, records) works unchanged. The generated code is kept in `plan` as a
    single pseudo-step `generated_code`.
    """
    from src.utils.langfuse_helper import pop_llm_calls
    run_id = f"codegen-{uuid.uuid4().hex[:8]}"
    df, schema = _load()
    previous = list(_HISTORY.get(session_id, [])) if session_id else []
    if session_id:
        _HISTORY[session_id] = (previous + [query])[-HISTORY_WINDOW:]
        previous = previous[-HISTORY_WINDOW:]

    start = time.perf_counter()
    text, err = _call_llm(build_user_prompt(query, schema, previous), run_id)
    reason = extract_refusal(text) if text else None
    if reason is not None:       # the model declined: recorded like ADAA's "unsolvable"; no code is run
        return {
            "run_id": run_id, "status": "unsolvable", "query": query, "message": reason,
            "final_df": None, "answer": None, "plan": [],
            "trace": [{"step": 1, "tool": "generated_code", "status": "refused", "message": reason,
                       "critic": None, "sandbox_status": "refused",
                       "duration_s": round(time.perf_counter() - start, 3)}],
            "events": [], "total_executions": 0, "llm_calls": pop_llm_calls(run_id), "session_id": session_id,
            "sandbox_status": "refused",
        }
    code = extract_code(text) if text else ""
    sandbox = ({"status": "error", "result": None, "message": err or "no code returned", "stdout": ""}
               if not code else run_sandboxed(code, df))
    llm_calls = pop_llm_calls(run_id)

    ok = sandbox["status"] == "ok"
    return {
        "run_id": run_id, "status": "success" if ok else "error", "query": query,
        "message": "" if ok else f"{sandbox['status']}: {sandbox['message']}",
        "final_df": sandbox["result"], "answer": None,
        "plan": [{"step": 1, "tool": "generated_code", "parameters": {"code": code},
                  "input": "df", "output": "result"}],
        "trace": [{"step": 1, "tool": "generated_code", "status": "success" if ok else "error",
                   "message": sandbox["message"], "critic": None, "sandbox_status": sandbox["status"],
                   "duration_s": round(time.perf_counter() - start, 3)}],
        "events": [], "total_executions": 1, "llm_calls": llm_calls, "session_id": session_id,
        "sandbox_status": sandbox["status"],
    }

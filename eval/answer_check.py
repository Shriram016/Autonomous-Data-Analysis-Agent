"""
answer_check.py -- Automatic check that the numbers in an answer come from the result table.

Catches answer-generator hallucination of VALUES (e.g. "$763K" when the table says
$286K). It does NOT check wording ("increase" vs "decrease") and cannot tell whether
the planner built the right table; that is a planner failure, not an answer failure.

Every number in the answer is classified as:
    excused     appears in the user's question (e.g. "top 5", "2016")
    supported   matches a value in the table, allowing for rounding / $ / % / K / M
    derived     equals a simple difference, sum, ratio, share or percent change of
                table values, or a column total / mean / min / max / row count
    unsupported anything else  -> the answer is flagged
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

_NUM_RE = re.compile(
    r"""(?<![A-Za-z0-9.,])
        (?P<sign>-)?
        (?P<cur>\$)?
        (?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
        (?P<suffix>\s?(?:%|percent|[KMBk](?![A-Za-z])|thousand|million|billion))?
        (?![A-Za-z0-9])""",
    re.VERBOSE,
)

_SCALES = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_MAX_GROUPS = 30  # roll-up (group-by) sums are computed for text columns with at most this many groups
_MAX_PAIR_VALUES = 40  # pairwise derived values are computed on at most this many distinct values


def extract_numbers(text: str) -> List[Dict[str, Any]]:
    """Return numbers found in text: raw string, real value, decimals written, percent flag."""
    found = []
    for m in _NUM_RE.finditer(text or ""):
        num = m.group("num")
        decimals = len(num.split(".")[1]) if "." in num else 0
        suffix = (m.group("suffix") or "").strip().lower()
        is_pct = suffix in ("%", "percent")
        scale = _SCALES.get(suffix, 1.0)
        value = float(num.replace(",", "")) * scale
        if m.group("sign"):
            value = -value
        found.append({
            "raw": m.group(0).strip(),
            "value": value,
            "decimals": decimals,
            "scale": scale,
            "is_percent": is_pct,
        })
    return found


def _tolerance(n: Dict[str, Any]) -> float:
    """One unit in the last written digit (covers rounding and truncation)."""
    return (10 ** -n["decimals"]) * n["scale"] + 1e-9


def _table_values(table: pd.DataFrame) -> np.ndarray:
    vals: List[float] = []
    for col in table.columns:
        s = table[col]
        if pd.api.types.is_bool_dtype(s):
            continue
        if pd.api.types.is_numeric_dtype(s):
            vals.extend(s.dropna().astype(float).tolist())
        else:  # text cells such as "2017" or "2017-03-05": pick out any numbers inside
            for cell in s.dropna().astype(str):
                vals.extend(n["value"] for n in extract_numbers(cell))
    return np.array(vals, dtype=float)


def _derived_values(table: pd.DataFrame, base: np.ndarray) -> np.ndarray:
    out: List[float] = [float(len(table))]
    for col in table.columns:
        s = table[col]
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            s = s.dropna().astype(float)
            if len(s):
                out.extend([s.sum(), s.mean(), s.min(), s.max()])
    num_cols = [c for c in table.columns
                if pd.api.types.is_numeric_dtype(table[c]) and not pd.api.types.is_bool_dtype(table[c])]
    for gcol in table.columns:
        if gcol in num_cols or table[gcol].nunique() > _MAX_GROUPS or len(num_cols) == 0:
            continue
        for ncol in num_cols:  # roll-ups, e.g. total per Ship Mode across Regions
            out.extend(table.groupby(gcol)[ncol].sum().dropna().astype(float).tolist())
    distinct = np.unique(base)[:_MAX_PAIR_VALUES]
    if len(distinct) >= 2:
        a = distinct[:, None]
        b = distinct[None, :]
        with np.errstate(divide="ignore", invalid="ignore"):
            grids = [a + b, np.abs(a - b), a / b, (b - a) / np.abs(a) * 100, a / b * 100]
        for g in grids:
            out.extend(g[np.isfinite(g)].ravel().tolist())
    return np.array(out, dtype=float)


def _pair_values(nums: List[float]) -> np.ndarray:
    """sum / difference / ratio / percent change / share of every pair of numbers."""
    if len(nums) < 2:
        return np.array([], dtype=float)
    a = np.array(nums, dtype=float)[:, None]
    b = np.array(nums, dtype=float)[None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        grids = [a + b, np.abs(a - b), a / b, (b - a) / np.abs(a) * 100, a / b * 100]
    return np.concatenate([g[np.isfinite(g)].ravel() for g in grids])


def _close(target: float, pool: np.ndarray, tol: float) -> bool:
    return pool.size > 0 and bool(np.any(np.abs(np.abs(pool) - abs(target)) <= tol))


def check_answer(
    answer: Optional[str],
    query: str,
    table: Optional[pd.DataFrame],
    answer_is_fallback: bool = False,
) -> Dict[str, Any]:
    """
    Verify that every number in `answer` is supported by `table`.

    verdict: "pass" | "fail" | "no_numbers" | "n/a"
    "n/a" means nothing to check: no answer, no table, or the answer is the
    deterministic fallback (built from the table, not written by an LLM).
    """
    empty = {"verdict": "n/a", "numbers_checked": 0, "supported": [], "derived": [],
             "excused": [], "unsupported": []}
    if answer:
        answer = _THINK_BLOCK.sub("", answer)
        if "<think>" in answer.lower():  # unclosed reasoning trace: cannot separate it from the answer
            return {**empty, "note": "answer contains an unclosed <think> reasoning trace"}
    if not answer or table is None or table.empty or answer_is_fallback:
        return empty

    base = _table_values(table)
    derived_pool = _derived_values(table, base)
    query_vals = [n["value"] for n in extract_numbers(query)]

    result = {"supported": [], "derived": [], "excused": [], "unsupported": []}
    pending = []
    for n in extract_numbers(answer):
        tol = _tolerance(n)
        # A percent can be written as 20.4% while the table holds 0.204
        direct = base * 100 if n["is_percent"] else base
        if any(abs(abs(n["value"]) - abs(q)) < 1e-9 for q in query_vals):
            result["excused"].append(n["raw"])
        elif _close(n["value"], base, tol) or (n["is_percent"] and _close(n["value"], direct, tol)):
            result["supported"].append(n["raw"])
        elif _close(n["value"], derived_pool, tol / 2):  # tighter: derived pool is large
            result["derived"].append(n["raw"])
        else:
            pending.append(n)

    # Second pass: the LLM often computes a difference/ratio from numbers it already
    # wrote (rounded), e.g. 733,215 - 609,206 = 124,009. Accept those exactly.
    supported_vals = [n["value"] for n in extract_numbers(answer) if n["raw"] in result["supported"]]
    answer_pool = _pair_values(supported_vals)
    for n in pending:
        if _close(n["value"], answer_pool, _tolerance(n)):
            result["derived"].append(n["raw"])
        else:
            result["unsupported"].append(n["raw"])

    checked = sum(len(result[k]) for k in ("supported", "derived", "unsupported"))
    if checked == 0:
        verdict = "no_numbers"
    else:
        verdict = "fail" if result["unsupported"] else "pass"
    return {"verdict": verdict, "numbers_checked": checked, **result}

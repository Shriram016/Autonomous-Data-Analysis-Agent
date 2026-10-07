"""Offline tests for the code-writing baseline (llm_codegen_experiment/codegen_baseline.py).

The sandbox tests run real subprocesses (about half a second each). No LLM is ever called.
"""

import os

import pandas as pd
import pytest

from llm_codegen_experiment import codegen_baseline as cb
from src.core.schema_gen import generate_schema


@pytest.fixture
def df():
    return pd.DataFrame({
        "Category": ["A", "A", "B", "B"], "Sales": [1.0, 2.0, 3.0, 4.0],
        "Order Date": pd.to_datetime(["2023-01-01", "2023-02-01", "2024-01-01", "2024-02-01"]),
    })


# ---------------------------------------------------------------- code extraction
def test_extract_code_takes_the_first_fenced_block_or_the_whole_reply():
    assert cb.extract_code("Here:\n```python\nresult = 1\n```\nand\n```python\nresult = 2\n```") == "result = 1"
    assert cb.extract_code("```\nresult = 3\n```") == "result = 3"
    assert cb.extract_code("result = 4") == "result = 4"
    assert cb.extract_code("") == ""


# ---------------------------------------------------------------- static safety check
@pytest.mark.parametrize("code,fragment", [
    ("import os", "Import"),
    ("from os import system", "ImportFrom"),
    ("__import__('os')", "__import__"),
    ("open('secrets.txt')", "'open'"),
    ("eval('1+1')", "'eval'"),
    ("exec('x=1')", "'exec'"),
    ("getattr(df, 'to_csv')", "'getattr'"),
    ("x = df.__class__", "__class__"),
    ("x = ().__class__.__bases__[0].__subclasses__()", "private or dunder"),
    ("x = (lambda: 0).__globals__", "__globals__"),
    ("pd.read_csv('a.csv')", "read_csv"),
    ("pd.read_pickle('a.pkl')", "read_pickle"),
    ("df.to_csv('out.csv')", "to_csv"),
    ("df.to_pickle('out.pkl')", "to_pickle"),
    ("np.load('a.npy')", "'load'"),
    ("np.lib.npyio", "'lib'"),
    ("pd.io.common", "'io'"),
    ("df.query('@x')", "'query'"),
    ("pd.eval('1')", "'eval'"),
    ("vars(df)", "'vars'"),
    ("type(df)", "'type'"),
    ("class A: pass", "ClassDef"),
    ("breakpoint()", "'breakpoint'"),
])
def test_dangerous_code_is_rejected_before_it_runs(code, fragment):
    reason = cb.check_code(code)
    assert reason and fragment in reason


def test_normal_pandas_code_passes_the_check():
    ok = "result = df[df['Category'] == 'A'].groupby('Category', as_index=False)['Sales'].sum()"
    assert cb.check_code(ok) is None
    assert cb.check_code("df['y'] = df['Order Date'].dt.year\nresult = df.groupby('y')['Sales'].mean()") is None
    assert cb.check_code("x = np.round(df['Sales'].sum(), 2)\nresult = float(x)") is None
    assert "syntax error" in cb.check_code("result = (")


# ---------------------------------------------------------------- sandbox execution (real subprocesses)
def test_sandbox_runs_good_code_and_returns_a_dataframe(df):
    r = cb.run_sandboxed("result = df.groupby('Category')['Sales'].sum()", df)
    assert r["status"] == "ok"
    assert r["result"].to_dict("records") == [{"Category": "A", "Sales": 3.0}, {"Category": "B", "Sales": 7.0}]


def test_sandbox_does_not_change_the_callers_dataframe(df):
    before = df.copy(deep=True)
    cb.run_sandboxed("df['Sales'] = 0\nresult = df['Sales'].sum()", df)
    pd.testing.assert_frame_equal(df, before)


def test_blocked_code_never_starts_a_process_and_writes_no_file(df, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = cb.run_sandboxed("df.to_csv('leak.csv')\nresult = 1", df)
    assert r["status"] == "blocked" and "to_csv" in r["message"]
    assert not os.path.exists(tmp_path / "leak.csv")


def test_names_that_are_not_provided_fail_at_runtime(df):
    r = cb.run_sandboxed("result = os.listdir('.')", df)         # `os` is not in the sandbox namespace
    assert r["status"] == "error" and "NameError" in r["message"]
    r = cb.run_sandboxed("result = __builtins__['open']('x')", df)  # open is not a whitelisted builtin
    assert r["status"] in ("blocked", "error")


def test_code_errors_and_missing_result_are_reported(df):
    assert "KeyError" in cb.run_sandboxed("result = df['Nope'].sum()", df)["message"]
    r = cb.run_sandboxed("x = 1", df)
    assert r["status"] == "error" and "result" in r["message"]


def test_an_endless_loop_is_stopped_by_the_timeout(df):
    r = cb.run_sandboxed("while True:\n    pass", df, timeout_s=2)
    assert r["status"] == "timeout"


@pytest.mark.parametrize("res,expected", [
    ("df['Sales'].sum()", [{"result": 10.0}]),
    ("int(len(df))", [{"result": 4}]),
    ("df.groupby('Category')['Sales'].sum()", [{"Category": "A", "Sales": 3.0}, {"Category": "B", "Sales": 7.0}]),
    ("df['Sales'].head(2)", [{"Sales": 1.0}, {"Sales": 2.0}]),
])
def test_results_are_normalised_to_a_dataframe(df, res, expected):
    out = cb.normalize_result(eval(res, {"df": df}))  # noqa: S307 - test-only, trusted literals
    assert out.to_dict("records") == expected


def test_a_result_of_the_wrong_type_is_an_error(df):
    r = cb.run_sandboxed("result = {'a': 1}", df)
    assert r["status"] == "error" and "must be a DataFrame" in r["message"]


# ---------------------------------------------------------------- run_codegen (LLM faked)
@pytest.fixture
def fake_llm(df, monkeypatch):
    schema = generate_schema(df, required_date_columns=["Order Date"])["result"]
    monkeypatch.setattr(cb, "_load", lambda: (df, schema))
    cb._HISTORY.clear()
    prompts, replies = [], []

    def fake(user_prompt, run_id):
        prompts.append(user_prompt)
        return (replies.pop(0) if replies else "```python\nresult = df['Sales'].sum()\n```"), None

    monkeypatch.setattr(cb, "_call_llm", fake)
    return prompts, replies


def test_run_codegen_returns_a_pipeline_shaped_result(fake_llm):
    out = cb.run_codegen("What is the total sales?")
    assert out["status"] == "success" and out["final_df"].to_dict("records") == [{"result": 10.0}]
    assert out["plan"][0]["tool"] == "generated_code" and "df['Sales'].sum()" in out["plan"][0]["parameters"]["code"]
    assert out["answer"] is None and out["total_executions"] == 1 and out["sandbox_status"] == "ok"


def test_run_codegen_reports_blocked_code_as_an_error_with_the_code_kept(fake_llm):
    prompts, replies = fake_llm
    replies.append("```python\nimport os\nresult = 1\n```")
    out = cb.run_codegen("q")
    assert out["status"] == "error" and out["sandbox_status"] == "blocked"
    assert out["final_df"] is None and "import os" in out["plan"][0]["parameters"]["code"]


def test_run_codegen_reports_an_llm_failure(df, monkeypatch):
    monkeypatch.setattr(cb, "_load", lambda: (df, generate_schema(df, required_date_columns=["Order Date"])["result"]))
    monkeypatch.setattr(cb, "_call_llm", lambda p, r: (None, "APITimeoutError: slow"))
    out = cb.run_codegen("q")
    assert out["status"] == "error" and "APITimeoutError" in out["message"]


def test_prompt_has_schema_and_earlier_questions_with_a_three_question_window(fake_llm):
    prompts, _ = fake_llm
    for i in range(1, 6):
        cb.run_codegen(f"question {i}", session_id="s1")
    assert "Previous questions" not in prompts[0] and "Schema of `df`" in prompts[0]
    last = prompts[4]
    assert "1. question 2" in last and "3. question 4" in last and "question 1" not in last  # window of 3
    cb.run_codegen("fresh", session_id="s2")
    assert "Previous questions" not in prompts[5]                                          # sessions are separate


def test_single_turn_calls_without_a_session_keep_no_history(fake_llm):
    prompts, _ = fake_llm
    cb.run_codegen("a")
    cb.run_codegen("b")
    assert "Previous questions" not in prompts[1] and cb._HISTORY == {}


# ---------------------------------------------------------------- df.query: allowed only for plainly safe strings
@pytest.mark.parametrize("code", [
    "result = df.query(\"Category == 'A' and Sales > 1\")",
    "result = df.query('`Order Date` >= \"2024-01-01\"')",
    "result = df.query('Sales in (1.0, 4.0)')",
    "result = df.query('not (Sales > 3) or Category == \"B\"')",
    "result = df.select_dtypes(include=object)",
])
def test_safe_query_strings_and_object_dtype_are_allowed(code):
    assert cb.check_code(code) is None


@pytest.mark.parametrize("code", [
    "df.query('@x')",                              # variable access
    "df.query('Sales.abs() > 1')",                 # method access
    "df.query('abs(Sales) > 1')",                  # function call
    "df.query(\"__import__('os')\")",              # dunder
    "df.query(q)",                                 # not a literal string
    "df.query('Sales > 1', engine='python')",      # extra arguments
    "f = df.query",                                # query used without a plain call
    "df.eval('Sales + 1')",                        # eval stays blocked
    "pd.eval('1 + 1')",
])
def test_unsafe_query_forms_and_eval_stay_blocked(code):
    reason = cb.check_code(code)
    assert reason and ("'query'" in reason or "'eval'" in reason or "__" in reason or "name" in reason)


def test_an_allowed_query_really_runs_in_the_sandbox(df):
    r = cb.run_sandboxed("result = df.query(\"Category == 'A' and Sales > 1\")", df)
    assert r["status"] == "ok" and r["result"]["Sales"].tolist() == [2.0]


# ---------------------------------------------------------------- the REFUSE option (same one-table contract as ADAA)
def test_prompt_states_the_one_table_contract_and_the_refuse_option():
    assert "ONE table" in cb.SYSTEM_PROMPT and "REFUSE: <short reason>" in cb.SYSTEM_PROMPT


@pytest.mark.parametrize("reply,reason", [
    ("REFUSE: needs two separate results", "needs two separate results"),
    ("  refuse :  a total plus a ranking  ", "a total plus a ranking"),
    ("REFUSE: two breakdowns\nbecause one table cannot hold both", "two breakdowns"),
    ("REFUSE:", "no reason given"),
])
def test_refusal_replies_are_recognised(reply, reason):
    assert cb.extract_refusal(reply) == reason


@pytest.mark.parametrize("reply", [
    "```python\nresult = 1\n```",
    "result = df['Sales'].sum()",
    "Here is the code:\n```python\nresult = 1  # REFUSE: no\n```",   # REFUSE only counts at the start
    "",
])
def test_normal_replies_are_not_refusals(reply):
    assert cb.extract_refusal(reply) is None


def test_run_codegen_records_a_refusal_as_unsolvable_and_runs_no_code(fake_llm):
    prompts, replies = fake_llm
    replies.append("REFUSE: the question needs two separate results")
    out = cb.run_codegen("Show total profit and also which states are most profitable.")
    assert out["status"] == "unsolvable" and out["message"] == "the question needs two separate results"
    assert out["final_df"] is None and out["plan"] == [] and out["sandbox_status"] == "refused"
    assert out["total_executions"] == 0

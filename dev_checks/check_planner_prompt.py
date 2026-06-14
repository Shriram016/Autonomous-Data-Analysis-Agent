"""
check_planner_prompt.py — Standalone smoke test for build_user_prompt()
(src/prompts/planner_prompt.py), specifically the new `recent_questions`
context block (V2 session memory, Step 3).

Run from the project root:

    python dev_checks/check_planner_prompt.py
"""

from pathlib import Path
import sys

# Allow running this script directly regardless of working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.prompts.planner_prompt import build_user_prompt


_FAKE_SCHEMA = {
    "Order Date": {"dtype": "datetime64[ns]", "min": "2021-01-01", "max": "2024-12-31"},
    "Sales": {"dtype": "float64", "min": 0.44, "max": 22638.48, "median": 54.49},
}


def main():
    # Case 1: no recent_questions (None) — block must be absent
    prompt_none = build_user_prompt("What about 2024?", _FAKE_SCHEMA, None)
    assert "Previous questions" not in prompt_none
    assert prompt_none.startswith("Query: What about 2024?")
    print("Case 1 (recent_questions=None):\n" + prompt_none + "\n")

    # Case 2: empty list — block must be absent
    prompt_empty = build_user_prompt("What about 2024?", _FAKE_SCHEMA, [])
    assert "Previous questions" not in prompt_empty
    print("Case 2 (recent_questions=[]): OK — no block added\n")

    # Case 3: non-empty — block must be present, numbered, oldest first
    recent = ["What were total sales in 2023?", "And for Furniture?"]
    prompt_with = build_user_prompt("What about 2024?", _FAKE_SCHEMA, recent)
    assert "Previous questions in this session (most recent last):" in prompt_with
    assert "1. What were total sales in 2023?" in prompt_with
    assert "2. And for Furniture?" in prompt_with
    print("Case 3 (recent_questions=2 items):\n" + prompt_with + "\n")

    print("PASS")


if __name__ == "__main__":
    main()

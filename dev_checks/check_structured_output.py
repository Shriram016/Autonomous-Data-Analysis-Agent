"""
check_structured_output.py — Evaluates the proposed fix for the qwen3-32b
`json_validate_failed` (empty failed_generation) bug seen in the planner.

Root cause (established earlier): qwen3-32b is a reasoning model that emits
<think> traces by default. With response_format=json_object and no
reasoning_format set, those traces can consume the whole max_tokens budget,
leaving `content` empty — Groq's server then rejects the empty content as
invalid JSON (json_validate_failed, failed_generation: '').

Proposed fix: set reasoning_format="parsed" (keeps max_tokens=1024 unchanged),
which routes <think> reasoning into a separate `reasoning` field and leaves
`content` as clean JSON.

This script re-runs the real planner prompt for ALL 5 queries from
run_tests.py against qwen/qwen3-32b with reasoning_format="parsed" and
reports whether each produces a valid, Pydantic-validated plan.

Run from the project root:

    python dev_checks/check_structured_output.py
"""

from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from groq import Groq, APIStatusError
from pydantic import ValidationError

from src.config import GROQ_API_KEY, PLANNER_MODEL, PLANNER_TEMPERATURE, PLANNER_MAX_TOKENS
from src.core.planner import PlanResponse, _validate_plan
from src.utils.data_loader import load_dataset
from src.core.schema_gen import generate_schema
from src.prompts.planner_prompt import SYSTEM_PROMPT, build_user_prompt


# Retry query 3 alone — gpt-oss-20b failed this one with json_validate_failed
# (same as qwen3-32b). Check if it's consistent or also non-deterministic.
QUERIES = [
    {
        "id": 3,
        "query": "How long does shipping take? Are certain product categories shipped faster?",
    },
]

# Testing: does simply swapping PLANNER_MODEL -> openai/gpt-oss-20b, with
# EVERYTHING ELSE unchanged (json_object mode, no reasoning_format,
# max_tokens=1024), just work?
TEST_MODEL = "openai/gpt-oss-20b"


def check_query(client: Groq, schema, query: str, max_tokens: int) -> bool:
    print(f"=== Query: {query!r} ===")
    user_prompt = build_user_prompt(query, schema)

    try:
        raw_response = client.chat.completions.with_raw_response.create(
            model=TEST_MODEL,
            temperature=PLANNER_TEMPERATURE,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            reasoning_effort="low",
            timeout=60,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        print("--- rate limit headers ---")
        for header in (
            "x-ratelimit-limit-requests",
            "x-ratelimit-remaining-requests",
            "x-ratelimit-reset-requests",
            "x-ratelimit-limit-tokens",
            "x-ratelimit-remaining-tokens",
            "x-ratelimit-reset-tokens",
        ):
            print(f"{header}: {raw_response.headers.get(header)}")

        response = raw_response.parse()
        message = response.choices[0].message
        content = message.content or ""
        reasoning = getattr(message, "reasoning", None)
        finish_reason = response.choices[0].finish_reason

        print(f"API call: OK | finish_reason={finish_reason} | content length: {len(content)} chars")
        print(f"--- reasoning ({len(reasoning) if reasoning else 0} chars) ---")
        print(reasoning)
        print(f"--- content ({len(content)} chars) ---")
        print(content)
        print("--- end ---")

        if not content.strip():
            print("RESULT: FAIL — empty content\n")
            return False

        try:
            parsed = PlanResponse.model_validate_json(content)
        except ValidationError as e:
            print(f"RESULT: FAIL — Pydantic validation error: {e}\n")
            return False

        if parsed.status == "unsolvable":
            print(f"RESULT: status=unsolvable — {parsed.reason}\n")
            return False

        is_valid, reason = _validate_plan(parsed.plan)
        if not is_valid:
            print(f"RESULT: FAIL — plan validation: {reason}\n")
            return False

        tools = " -> ".join(s.tool for s in parsed.plan)
        print(f"RESULT: PASS — plan: {tools}\n")
        return True

    except APIStatusError as e:
        print(f"RESULT: FAIL — Groq API error {e.status_code}: {e.message}\n")
        return False

    except Exception as e:
        print(f"RESULT: FAIL — Unexpected error: {e}\n")
        return False


def main():
    if not GROQ_API_KEY:
        print("GROQ_API_KEY is not set. Add it to your .env file before running this script.")
        return

    client = Groq(api_key=GROQ_API_KEY)
    df = load_dataset()
    schema = generate_schema(df)["result"]

    max_tokens = 2048
    num_runs = 2
    results = []
    for i in range(num_runs):
        print(f"\n##### Run {i + 1}/{num_runs} #####")
        results.extend(check_query(client, schema, q["query"], max_tokens) for q in QUERIES)
        if i < num_runs - 1:
            print("--- sleeping 70s to let TPM window reset ---")
            time.sleep(70)

    passed = sum(results)
    print(f"=== {passed}/{len(results)} runs produced a valid plan with model={TEST_MODEL}, reasoning_effort='low', max_tokens={max_tokens} ===")


if __name__ == "__main__":
    main()

"""The number guardrail: every number in the answer text must come from the data (§0 M1.3).

The answer LLM may only copy numbers the code gave it (agent/facts.py). This check finds
every number in its text and looks it up in the allowed list: the formatted result, the
code-computed facts, and the question itself (years, dates). Any number not found means the
LLM calculated, rounded or invented it. This module only FINDS such numbers; the answer
node decides what to do (show the template answer, log the failure).

Numbers are compared in a plain form — no "R$", no "%", no thousands commas — so
"R$ 2,136,258.96" and "2,136,258.96" match. Otherwise the match is exact: "2.1 million"
for 2,136,258.96 fails, because rounding is not allowed.

Known limits: a real number next to the wrong label is not caught (the table below the
answer shows the truth), and numbers written as words ("twenty") are not seen.
"""

import re
from collections.abc import Iterable

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_in(text: str) -> list[str]:
    """Every number in the text, in plain form: '2,136,258.96' → '2136258.96'."""
    return [match.replace(",", "") for match in NUMBER.findall(text) if match.strip(",")]


def unknown_numbers(answer: str, allowed: Iterable[str]) -> list[str]:
    """The numbers in `answer` that appear in none of the `allowed` strings. Empty = pass."""
    known = {number for text in allowed for number in numbers_in(text)}
    return [number for number in numbers_in(answer) if number not in known]

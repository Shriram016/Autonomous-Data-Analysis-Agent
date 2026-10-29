"""What the translate LLM call returns for one review: the English text only (§0 M3, 2026-10-29).

Tags were dropped: the tables already hold the facts most tags repeated (order dates and
status, the star score). The answer is still structured output, so complete() checks it
against ReviewTranslation and retries once; check_translation then checks the text itself.
"""

import re

from pydantic import BaseModel, ConfigDict

from adaa.agent.prompts import Prompt, load_prompt
from adaa.llm.adapters.base import Adapter, Message
from adaa.llm.complete import complete
from adaa.llm.types import LlmResult


class ReviewTranslation(BaseModel):
    """The LLM's answer for one review."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text_en: str


def load_review_prompt() -> Prompt:
    """prompts/review_translate.md."""
    return load_prompt("review_translate", {})


def translate_one(
    text_pt: str, prompt: Prompt, adapter: Adapter | None = None
) -> LlmResult[ReviewTranslation]:
    """One review → its translation, as one normal call (spot checks, redoing failures).

    The full run sends this same request (system prompt, review as the user message, schema)
    through the Batch API. complete() checks the answer against ReviewTranslation and retries
    once with the errors; it raises LlmError when there is still no valid answer.
    """
    messages = [
        Message(role="system", content=prompt.text),
        Message(role="user", content=text_pt),
    ]
    return complete("review_translate", messages, ReviewTranslation, adapter=adapter)


# Common Portuguese review words that never belong in an English translation. Names (the
# anonymised "lannister") are not here, and words that are also English ("com") are left out.
PORTUGUESE_WORDS = frozenset(
    {
        "não",
        "nao",
        "produto",
        "entrega",
        "chegou",
        "recebi",
        "muito",
        "ainda",
        "prazo",
        "pedido",
        "loja",
        "comprei",
        "veio",
        "recomendo",
        "ótimo",
        "otimo",
        "péssimo",
        "pessimo",
        "antes",
        "atrasou",
        "também",
        "tambem",
        "obrigado",
        "obrigada",
        "gostei",
        "bem",
        "está",
        "esta",
        "mais",
    }
)
MIN_CHARS_FOR_LENGTH = 20  # "bom" → "good" or "👍" → "thumbs up": too short to compare
LENGTH_RATIO = (0.4, 2.5)  # English length / Portuguese length outside this: a part is lost


def check_translation(text_pt: str, answer: ReviewTranslation) -> list[str]:
    """What the schema can't see, as it needs the original. Empty list = the answer is good.

    A failed review gets no row (complete, good rows only), so the next run finds it again.
    """
    text_en = answer.text_en.strip()
    if not text_en:
        return ["empty translation"]
    problems = []
    words = set(re.findall(r"\w+", text_en.lower()))
    if len(left := sorted(words & PORTUGUESE_WORDS)) >= 2:
        problems.append(f"still Portuguese: {', '.join(left)}")
    if len(text_pt) > MIN_CHARS_FOR_LENGTH:
        ratio = len(text_en) / len(text_pt)
        low, high = LENGTH_RATIO
        if not low <= ratio <= high:
            problems.append(f"odd length: {ratio:.2f}× the original")
    return problems

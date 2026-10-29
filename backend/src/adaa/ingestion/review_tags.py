"""What the translate + tag LLM call returns for one review: tag list v1 (§0 M3, 2026-10-28).

Every heading is required. "The text does not say" is `not_mentioned`, never an empty field,
so a missing answer can't be mistaken for "nothing to say". `delivery`, `price` and `tone`
take one value (their values exclude each other); `product` and `service` take a list (their
values can be true together), and there `not_mentioned` must stand alone.

The meanings are shown to the LLM in the prompt, so each value has exactly one sense.
"""

import re
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adaa.agent.prompts import Prompt, load_prompt
from adaa.llm.adapters.base import Adapter, Message
from adaa.llm.complete import complete
from adaa.llm.types import LlmResult

TAG_LIST_VERSION = "v1"
LISTS = ("product", "service")  # the headings that take a list

Delivery = Literal["fast", "on_time", "late", "not_delivered", "delivery_failed", "not_mentioned"]
Product = Literal[
    "good",
    "damaged_or_defective",
    "wrong_item",
    "missing_items",
    "not_as_described",
    "bad_quality",
    "other",
    "not_mentioned",
]
Service = Literal[
    "good_service",
    "seller_no_response",
    "tracking_problem",
    "refund_or_return",
    "invoice_problem",
    "other",
    "not_mentioned",
]
Price = Literal["good_value", "too_expensive", "freight_too_high", "not_mentioned"]
Tone = Literal["positive", "neutral", "negative", "mixed"]  # every text has a tone

MEANINGS: dict[str, dict[str, str]] = {
    "delivery": {
        "fast": "arrived early or quicker than expected",
        "on_time": "arrived within the promised time",
        "late": "arrived after the promised date",
        "not_delivered": "has not arrived (yet)",
        "delivery_failed": "no delivery attempt, or the customer had to collect it",
        "not_mentioned": "the text says nothing about delivery",
    },
    "product": {
        "good": "the product is good or as expected",
        "damaged_or_defective": "arrived broken, or does not work",
        "wrong_item": "a different product, colour or size came",
        "missing_items": "only part of the order came",
        "not_as_described": "differs from the photo or the description",
        "bad_quality": "works, but the quality is poor",
        "other": "another point about the product",
        "not_mentioned": "the text says nothing about the product",
    },
    "service": {
        "good_service": "praise for the seller or the store's service",
        "seller_no_response": "the seller or store does not answer",
        "tracking_problem": "tracking is missing or does not work",
        "refund_or_return": "about a refund, a return or a cancellation",
        "invoice_problem": "about the invoice or other paperwork",
        "other": "another point about the service",
        "not_mentioned": "the text says nothing about the service",
    },
    "price": {
        "good_value": "good price or worth the money",
        "too_expensive": "the product costs too much",
        "freight_too_high": "the shipping cost is too high",
        "not_mentioned": "the text says nothing about price",
    },
    "tone": {
        "positive": "the customer is happy",
        "neutral": "neither happy nor unhappy, or only facts",
        "negative": "the customer is unhappy",
        "mixed": "both happy and unhappy points",
    },
}


class ReviewTags(BaseModel):
    """The LLM's answer for one review: the translation and the 5 headings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text_en: str
    delivery: Delivery
    product: list[Product] = Field(min_length=1)
    service: list[Service] = Field(min_length=1)
    price: Price
    tone: Tone

    @model_validator(mode="after")
    def lists_are_clean(self) -> "ReviewTags":
        for heading in LISTS:
            values: list[str] = getattr(self, heading)
            if len(set(values)) != len(values):
                raise ValueError(f"{heading}: a value is repeated: {values}")
            if "not_mentioned" in values and len(values) > 1:
                raise ValueError(f"{heading}: not_mentioned must stand alone: {values}")
        return self


def check_meanings() -> None:
    """Every allowed value has a meaning and every meaning is an allowed value (a test runs it)."""
    types = {
        "delivery": Delivery,
        "product": Product,
        "service": Service,
        "price": Price,
        "tone": Tone,
    }
    for heading, kind in types.items():
        if set(get_args(kind)) != set(MEANINGS[heading]):
            raise ValueError(f"{heading}: the values and MEANINGS differ")


def tag_list_text() -> str:
    """The prompt's tag list, written from MEANINGS: the prompt can't drift from the schema."""
    blocks = []
    for heading, values in MEANINGS.items():
        kind = "a list" if heading in LISTS else "one value"
        lines = [f"`{heading}` ({kind}):"] + [f"- `{v}`: {m}" for v, m in values.items()]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def load_review_prompt() -> Prompt:
    """prompts/review_tag.md with the tag list filled in."""
    return load_prompt("review_tag", {"tag_list": tag_list_text()})


def tag_one(text_pt: str, prompt: Prompt, adapter: Adapter | None = None) -> LlmResult[ReviewTags]:
    """One review → its translation + tags, as one normal call (the gold set, redoing failures).

    The full run sends this same request (system prompt, review as the user message, schema)
    through the Batch API. complete() checks the answer against ReviewTags and retries once
    with the errors; it raises LlmError when there is still no valid answer.
    """
    messages = [
        Message(role="system", content=prompt.text),
        Message(role="user", content=text_pt),
    ]
    return complete("review_tag", messages, ReviewTags, adapter=adapter)


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


def check_translation(text_pt: str, tags: ReviewTags) -> list[str]:
    """What the schema can't see, as it needs the original. Empty list = the answer is good.

    A failed review gets no row (complete, good rows only), so the next run finds it again.
    """
    text_en = tags.text_en.strip()
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

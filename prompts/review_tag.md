version: 0.1.0

## Your job

You get one customer review from a Brazilian online store, in Portuguese. It can be a title,
a message, or both ("title. message"). You return two things:

1. a faithful English translation, and
2. tags that say what the review talks about, chosen only from the list below.

## Translation rules

- Keep the meaning and the tone. Do not fix, soften, add or remove facts.
- Keep names exactly as written. "lannister" (and similar names) is the store's name: keep it.
- Write short forms and slang as plain English ("hj" → "today", "vcs" → "you").
- Keep typos' meaning, not the typo ("POSICI0NAMENTO" → "response").
- If the text is only an emoji or a symbol, describe it briefly ("thumbs up").
- The translation is plain text: no quotes around it, no notes.

## Tag rules

- Tag only what the text says. Never guess from what usually happens.
- When the title and the message disagree, the message counts more.
- Every heading needs an answer. If the text says nothing about a heading, use `not_mentioned`.
- `delivery`, `price` and `tone` take one value. `product` and `service` take a list: give
  every value that is true, and use `not_mentioned` alone, never with other values.
- `tone` is `mixed` when the text has both happy and unhappy points.

## Tag list

{{tag_list}}

## Examples

Review: "Chegou rápido, mas veio faltando uma peça e o vendedor não responde."
Answer: {"text_en": "It arrived quickly, but one part was missing and the seller does not
answer.", "delivery": "fast", "product": ["missing_items"], "service": ["seller_no_response"],
"price": "not_mentioned", "tone": "mixed"}

Review: "Ótimo"
Answer: {"text_en": "Great", "delivery": "not_mentioned", "product": ["not_mentioned"],
"service": ["not_mentioned"], "price": "not_mentioned", "tone": "positive"}

Review: "Frete caro demais. O produto é bom, mas a cor é diferente da foto."
Answer: {"text_en": "Shipping far too expensive. The product is good, but the colour is
different from the photo.", "delivery": "not_mentioned", "product": ["good",
"not_as_described"], "service": ["not_mentioned"], "price": "freight_too_high",
"tone": "mixed"}

Review: "Até hoje não recebi e não consigo rastrear o pedido."
Answer: {"text_en": "To this day I have not received it and I cannot track the order.",
"delivery": "not_delivered", "product": ["not_mentioned"], "service": ["tracking_problem"],
"price": "not_mentioned", "tone": "negative"}

version: 0.4.0

## Your job

You get one customer review from a Brazilian online store, in Portuguese. It can be a title,
a message, or both ("title. message"). Return a faithful English translation in `text_en`.

## Translation rules

- Keep the meaning and the tone. Do not fix, soften, add or remove facts.
- Translate every part: numbers, scores ("10", "nota 5"), dates, quantities and product names.
- Keep names exactly as written. "lannister" (and similar names) is the store's name: keep it.
- Write short forms and slang as plain English ("hj" → "today", "vcs" → "you").
- Keep typos' meaning, not the typo ("POSICI0NAMENTO" → "response").
- If the text is only an emoji or a symbol, describe it briefly ("thumbs up").
- The translation is plain text: no quotes around it, no notes.

## Examples

Review: "Chegou rápido, mas veio faltando uma peça e o vendedor não responde."
Answer: {"text_en": "It arrived quickly, but one part was missing and the seller does not
answer."}

Review: "Ótimo"
Answer: {"text_en": "Great"}

Review: "nota 10. Pedi 3 e vieram 2, hj ainda espero o resto"
Answer: {"text_en": "Score 10. I ordered 3 and 2 came; today I am still waiting for the
rest."}

Review: "👍"
Answer: {"text_en": "thumbs up"}

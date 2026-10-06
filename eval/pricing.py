"""
pricing.py -- USD per 1M tokens, used by the eval to turn token counts into cost.

Cost is computed here (not in the agent) so prices can be corrected without
touching pipeline code. Update PRICES_AS_OF when you re-check.

verified=True  : read from Groq's model docs page on PRICES_AS_OF.
verified=False : not listed publicly on that page; value is a best-known
                 figure. Confirm in the Groq console before quoting cost.
"""

PRICES_AS_OF = "2026-10-06"

# model -> (input $/1M tokens, output $/1M tokens, verified)
PRICES = {
    "openai/gpt-oss-20b": (0.075, 0.30, True),
    "llama-3.1-8b-instant": (0.05, 0.08, False),
}


def call_cost(model, input_tokens, output_tokens):
    """Returns (cost_usd, verified). Unknown model or missing tokens -> (0.0, False)."""
    if model not in PRICES or input_tokens is None or output_tokens is None:
        return 0.0, model in PRICES  # failed attempt with no tokens costs nothing known
    p_in, p_out, verified = PRICES[model]
    return (input_tokens * p_in + output_tokens * p_out) / 1_000_000, verified

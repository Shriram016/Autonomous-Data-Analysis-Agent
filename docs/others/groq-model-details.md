# Groq Model Details

Reference notes gathered while investigating why `PLANNER_MODEL` (`openai/gpt-oss-20b`)
hit its daily token quota during the Step 7 multi-turn eval run, and whether a
different model would let us (a) avoid reasoning-model `<think>` overhead and/or
(b) pass an actual JSON schema via `response_format: json_schema`.

Rate-limit columns ("TPM remaining", "Daily requests remaining") were captured via
small 1-token test calls on **2026-06-14** — they're a snapshot, not a static limit,
and will drift with usage. TPM/daily-request *limits* and json_schema support are
account/model-level facts and should stay accurate.

---

## All 16 models on this Groq account

Fetched via `dev_checks/check_list_models.py` → `GET https://api.groq.com/openai/v1/models`.

### Chat-completion-capable models (10) — candidates for Planner/Replanner/Param Fixer/Answer Generator

| Model | TPM limit | TPM remaining (snapshot) | Daily request limit | Daily requests remaining (snapshot) | TPD (tokens/day) | Reasoning model? | `response_format: json_schema` support | `strict` levels supported | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `openai/gpt-oss-20b` | 8,000 | 7,927 | 1,000 | 982 | **200,000** (confirmed exhausted, ~197,800-198,000 used) | **Yes** (`<think>` traces) | ✅ | `true` or `false` | Current `PLANNER_MODEL`/`REPLANNER_MODEL`/`PARAM_FIXER_MODEL`. TPD is the blocker for the multi-turn eval. |
| `openai/gpt-oss-120b` | 8,000 | 7,927 | 1,000 | 999 | unknown (fresh/unused) | **Yes** (`<think>` traces) | ✅ | `true` or `false` | Same family as current, bigger model, fresh daily pool. `strict: true` = guaranteed schema compliance. |
| `openai/gpt-oss-safeguard-20b` | 8,000 | 7,927 | 1,000 | 999 | unknown (fresh/unused) | **Yes** | ✅ | `false` only | Safety-tuned variant, not intended for general planning. |
| `meta-llama/llama-4-scout-17b-16e-instruct` | 30,000 | 29,988 | 1,000 | 999 | unknown (fresh/unused) | **No** | ✅ | `false` only | Largest TPM headroom, fresh daily pool, modern MoE. Only non-reasoning model that supports `json_schema`. |
| `llama-3.3-70b-versatile` | 12,000 | 11,963 | 1,000 | 999 | unknown (fresh/unused) | No | ❌ (`json_object` only) | n/a | Already a commented-out fallback in `config.py`. Not in Groq's structured-outputs supported list. |
| `llama-3.1-8b-instant` | 6,000 | 5,963 | 14,400 | 14,399 | unknown (lightly used today) | No | ❌ (`json_object` only) | n/a | Current `ANSWER_MODEL` — chosen specifically to avoid `<think>` traces. |
| `qwen/qwen3-32b` | 6,000 | 5,990 | 1,000 | 999 | unknown (fresh/unused) | **Yes** (hybrid think/non-think mode) | ❌ (`json_object` only) | n/a | Smaller TPM, reasoning model. |
| `allam-2-7b` | 6,000 | 5,991 | 7,000 | 6,999 | unknown (fresh/unused) | No | ❌ (`json_object` only) | n/a | Arabic-focused, not a great fit for this dataset/prompts. |
| `groq/compound` | 70,000 | 69,994 | 250 | 249 | unknown (fresh/unused) | Yes (agentic, internal reasoning + tools) | ❌ (`json_object` only) | n/a | Agentic system (web search/tools) — not a plain LLM, risky for a deterministic planner. |
| `groq/compound-mini` | 70,000 | 69,994 | 250 | 249 | unknown (fresh/unused) | Yes (agentic, internal reasoning + tools) | ❌ (`json_object` only) | n/a | Same caveat as `groq/compound`. |

### Non-chat models (6) — excluded, not candidates

| Model | Type | Why excluded |
|---|---|---|
| `whisper-large-v3` | Speech-to-text | Audio transcription model |
| `whisper-large-v3-turbo` | Speech-to-text | Audio transcription model |
| `canopylabs/orpheus-v1-english` | Text-to-speech | TTS model |
| `canopylabs/orpheus-arabic-saudi` | Text-to-speech | TTS model |
| `meta-llama/llama-prompt-guard-2-22m` | Classifier | Prompt-injection/jailbreak detector, not generative |
| `meta-llama/llama-prompt-guard-2-86m` | Classifier | Same — detector, not generative |

---

## Groq Structured Outputs (`response_format: json_schema`) — support summary

| Support level | Models | Behavior |
|---|---|---|
| **`strict: true`** (constrained decoding — guaranteed schema-compliant) | `openai/gpt-oss-20b`, `openai/gpt-oss-120b` | Output is *guaranteed* to match the supplied JSON schema |
| **`strict: false`** (best-effort, default for `json_schema`) | `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `openai/gpt-oss-safeguard-20b`, `meta-llama/llama-4-scout-17b-16e-instruct` | Attempts schema compliance, may occasionally deviate/error |
| **JSON Object Mode only** (`json_object` — valid JSON syntax, no shape enforcement) | All other models — `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `qwen/qwen3-32b`, `allam-2-7b`, `groq/compound`, `groq/compound-mini` | Valid JSON guaranteed, but keys/types are not — relies on prompt instructions only |

**Caveat from Groq docs:** Streaming and tool use are not currently supported together with Structured Outputs.

**`strict: true` requirement:** every object in the schema needs `additionalProperties: false` and a fixed set of properties. Our `PlanStep.parameters` is a plain `dict` (shape varies per tool), so `model_json_schema()` would emit `parameters: {"type": "object"}` with no fixed properties — likely incompatible with `strict: true` without restructuring `parameters` into a per-tool discriminated union (9 Pydantic models combined via `anyOf`).

Source: [Structured Outputs - Groq Docs](https://console.groq.com/docs/structured-outputs)

---

## Current production LLM call configuration (as of this investigation)

Read directly from source (`src/core/planner.py`, `src/core/replanner.py`, `src/core/param_fixer.py`, `src/core/answer_generator.py`):

| Component | Model (`config.py`) | `response_format` | `strict` | `schema` passed to LLM | Pydantic response model (post-hoc validation) |
|---|---|---|---|---|---|
| **Planner** ([planner.py:197-202](../src/core/planner.py)) | `openai/gpt-oss-20b` | `{"type": "json_object"}` | not set | none — only the system prompt's hand-written description of the JSON shape | `PlanResponse` |
| **Replanner** ([replanner.py:63-68](../src/core/replanner.py)) | `openai/gpt-oss-20b` | `{"type": "json_object"}` | not set | none | `PlanResponse` (reused from planner) |
| **Param Fixer** ([param_fixer.py:70-81](../src/core/param_fixer.py)) | `openai/gpt-oss-20b` | `{"type": "json_object"}` | not set | none | `ParamFixResponse` (`{"parameters": dict}`) |
| **Answer Generator** ([answer_generator.py:99-108](../src/core/answer_generator.py)) | `llama-3.1-8b-instant` | *(no `response_format` at all)* | n/a | n/a — free text output | none |

**Flow for the 3 JSON-mode components (Planner, Replanner, Param Fixer):**
1. Call Groq with `response_format={"type": "json_object"}` — no schema sent to the LLM, just "return valid JSON".
2. Get raw JSON string: `raw = response.choices[0].message.content`.
3. **After the fact**, validate: `PlanResponse.model_validate_json(raw)` / `ParamFixResponse.model_validate_json(raw)`.
4. On `ValidationError`: Planner retries up to 2 attempts (error appended to prompt as `error_context`); Param Fixer returns an error for the caller to handle.

The Pydantic models today are a **post-hoc safety net only** — they don't guide generation.

---

## Proposed change (discussed, not yet implemented)

Switch to `response_format={"type": "json_schema", "json_schema": {"name": ..., "strict": False, "schema": <PydanticModel>.model_json_schema()}}` for Planner/Replanner/Param Fixer:
- Additive, not a replacement — `model_validate_json(raw)` and the existing retry-on-`ValidationError` loop stay exactly as-is as the final safety net.
- Gives the model the actual schema up front → fewer malformed responses in the first place.
- `strict: false` (best-effort) is the only viable option given `PlanStep.parameters: dict` (see `strict: true` requirement above).

**Model choice conflict found:**

| Requirement | `llama-3.3-70b-versatile` | `meta-llama/llama-4-scout-17b-16e-instruct` |
|---|---|---|
| Non-reasoning model | ✅ Yes | ✅ Yes |
| Supports `response_format: json_schema` | ❌ No (`json_object` only) | ✅ Yes (`strict: false`, best-effort) |

`meta-llama/llama-4-scout-17b-16e-instruct` is the only model in the candidate set that is **both** non-reasoning **and** supports `json_schema` — it satisfies both proposed changes (#1 pass actual schema, #2 move off a reasoning model). `openai/gpt-oss-120b` is the alternative if staying on a reasoning model is acceptable (same family as current, `strict: true` available, fresh daily quota).

**Existing dev_checks script found as a starting template:** [dev_checks/check_structured_output.py](../dev_checks/check_structured_output.py) — currently scoped to testing `gpt-oss-20b`/`qwen3-32b` for an empty-content/`<think>`-truncation bug on the Planner only. Would need adapting/extending to cover all 3 components with the new model + schema before any production code change. **Not yet adapted — production code unchanged.**

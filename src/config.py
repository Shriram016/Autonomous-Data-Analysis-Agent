import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# Groq API
# ---------------------------------------------------------------------------
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# ---------------------------------------------------------------------------
# Planner LLM settings
# ---------------------------------------------------------------------------
# PLANNER_MODEL: str = "llama-3.1-8b-instant"
PLANNER_MODEL: str = "qwen/qwen3-32b"
# PLANNER_MODEL: str = "llama-3.3-70b-versatile"
PLANNER_TEMPERATURE: float = 0.0
PLANNER_MAX_TOKENS: int = 1024
PLANNER_TIMEOUT_SECONDS: int = 90   # Abort LLM call if no response within this time

# ---------------------------------------------------------------------------
# Param Fixer LLM settings
# ---------------------------------------------------------------------------
PARAM_FIXER_MODEL: str = "qwen/qwen3-32b"
PARAM_FIXER_TEMPERATURE: float = 0.0
PARAM_FIXER_MAX_TOKENS: int = 1024
PARAM_FIXER_TIMEOUT_SECONDS: int = 90

# ---------------------------------------------------------------------------
# Answer Generator LLM settings
# ---------------------------------------------------------------------------
# Small non-reasoning instruct model — avoids <think> reasoning traces
# leaking into the user-facing answer (qwen3 emits these by default).
ANSWER_MODEL: str = "llama-3.1-8b-instant"

# ---------------------------------------------------------------------------
# Loop Controller limits
# ---------------------------------------------------------------------------
MAX_RETRIES_PER_STEP: int = 2       # Max retry attempts per failed step
MAX_REPLAN_ATTEMPTS: int = 1        # Max number of replanning attempts
MAX_TOTAL_STEPS: int = 10           # Hard cap on total steps across entire execution

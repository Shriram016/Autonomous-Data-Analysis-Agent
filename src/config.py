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
PLANNER_MODEL: str = "openai/gpt-oss-20b"
# PLANNER_MODEL: str = "llama-3.3-70b-versatile"
PLANNER_TEMPERATURE: float = 0.0
PLANNER_MAX_TOKENS: int = 2048
PLANNER_TIMEOUT_SECONDS: int = 90   # Abort LLM call if no response within this time

# ---------------------------------------------------------------------------
# Param Fixer LLM settings
# ---------------------------------------------------------------------------
PARAM_FIXER_MODEL: str = "openai/gpt-oss-20b"
PARAM_FIXER_TEMPERATURE: float = 0.0
PARAM_FIXER_MAX_TOKENS: int = 2048
PARAM_FIXER_TIMEOUT_SECONDS: int = 90

# ---------------------------------------------------------------------------
# Replanner LLM settings
# ---------------------------------------------------------------------------
REPLANNER_MODEL: str = "openai/gpt-oss-20b"
REPLANNER_TEMPERATURE: float = 0.0
REPLANNER_MAX_TOKENS: int = 2048
REPLANNER_TIMEOUT_SECONDS: int = 90

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

# ---------------------------------------------------------------------------
# LangGraph checkpointing
# ---------------------------------------------------------------------------
CHECKPOINT_DB_PATH: str = "checkpoints/adaa.sqlite"

# ---------------------------------------------------------------------------
# LangGraph execution
# ---------------------------------------------------------------------------
GRAPH_RECURSION_LIMIT: int = 20    # Backstop against runaway graph loops (see max_executions for the real cap)

# ---------------------------------------------------------------------------
# Langfuse Observability
# ---------------------------------------------------------------------------
LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
LANGFUSE_ENABLED: bool = bool(LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY)

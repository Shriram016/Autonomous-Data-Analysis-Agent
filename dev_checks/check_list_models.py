"""
check_list_models.py — Lists all models available to this Groq account.

Equivalent to:
    curl -X GET "https://api.groq.com/openai/v1/models" \
         -H "Authorization: Bearer $GROQ_API_KEY" \
         -H "Content-Type: application/json"

Run from the project root:

    python dev_checks/check_list_models.py
"""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests

from src.config import GROQ_API_KEY

response = requests.get(
    "https://api.groq.com/openai/v1/models",
    headers={
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    },
)

response.raise_for_status()
data = response.json()

for model in data.get("data", []):
    print(model["id"])

"""Write the API's OpenAPI description to frontend/openapi.json (§0 M1.6, generated types).

The page's TypeScript types are generated from this file, so the Pydantic models stay the one
source of truth. Built from the code, so the API does not need to be running.

Run from backend/:  uv run python -m adaa.api.openapi
Then in frontend/:  npm run types
"""

import json

from adaa.api.app import app
from adaa.settings import REPO_ROOT

TARGET = REPO_ROOT / "frontend" / "openapi.json"


def main() -> None:
    TARGET.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()

from typing import Any, Dict, Optional

import pandas as pd


def _error_response(message: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "message": message,
        "result": None
    }


def _success_response(message: str, result: pd.DataFrame) -> Dict[str, Any]:
    return {
        "status": "success",
        "message": message,
        "result": result
    }

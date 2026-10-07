"""Fixtures for the llm_codegen_experiment tests. Everything runs offline: no LLM, no network, no API keys."""

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def no_network_llm(monkeypatch):
    """Safety net: any test that accidentally reaches a real Groq client fails loudly."""
    import groq

    def boom(*a, **k):
        raise RuntimeError("Test tried to call the real Groq API. Mock it.")

    monkeypatch.setattr(groq, "Groq", boom)

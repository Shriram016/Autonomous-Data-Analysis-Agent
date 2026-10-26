"""Load and check the LLM settings (config/llm.yaml).

One file decides which model each job uses, its thinking level, its limits and the
model's price (ADR 0009). This module reads it into typed objects and refuses to load if
a value is wrong or a name points nowhere: a job naming an unknown model, or a model
naming an unknown provider. The API key is NOT read here; the adapter reads it from
.env at call time, so the settings load (and tests run) without a key.
"""

from datetime import date
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from adaa.settings import REPO_ROOT

CONFIG_FILE = REPO_ROOT / "config" / "llm.yaml"

# "anthropic": chat models through llm.complete. "jev": a classifier that picks one choice
# (the router only, agent/router.py); it never fills a form. "openai_compatible" joins
# when the fallback is built.
Adapter = Literal["anthropic", "jev"]
Thinking = Literal["disabled", "low", "medium", "high"]


class LlmConfigError(Exception):
    """config/llm.yaml is wrong; the LLM settings do not load."""


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)  # a typo in a key is an error


class Provider(Strict):
    adapter: Adapter
    api_key_env: str


class Price(Strict):
    input: float  # USD per 1M input tokens
    output: float  # USD per 1M output tokens (thinking tokens use this price too)


class Model(Strict):
    provider: str
    price_per_million: Price
    price_checked: date


class Job(Strict):
    model: str
    timeout_seconds: PositiveInt
    # Chat-model settings. A Jev job leaves them out: a classifier has no thinking, and
    # its answer is one choice. check() makes every anthropic job set max_tokens.
    thinking: Thinking = "disabled"
    max_tokens: PositiveInt | None = None
    max_attempts: Literal[1, 2] = 1  # 2 = one retry with the errors; never more (§0 M1.3)
    max_rows: PositiveInt | None = None  # only jobs that read data rows set it


class Router(Strict):
    order: list[str] = Field(min_length=1)  # job names; first = primary, then fallbacks


class JobSettings(Strict):
    """Everything an adapter needs for one job, with the names already resolved."""

    job: str
    model_name: str
    model: Model
    provider: Provider
    settings: Job


class LlmConfig(Strict):
    version: str
    providers: dict[str, Provider]
    models: dict[str, Model]
    jobs: dict[str, Job]
    router: Router

    def job_settings(self, job: str) -> JobSettings:
        if job not in self.jobs:
            raise LlmConfigError(f"No LLM job called '{job}'. Known jobs: {sorted(self.jobs)}")
        settings = self.jobs[job]
        model = self.models[settings.model]
        return JobSettings(
            job=job,
            model_name=settings.model,
            model=model,
            provider=self.providers[model.provider],
            settings=settings,
        )


def check(config: LlmConfig) -> None:
    problems: list[str] = []
    for name, job in config.jobs.items():
        if job.model not in config.models:
            problems.append(f"job '{name}' uses unknown model '{job.model}'")
    for name, model in config.models.items():
        if model.provider not in config.providers:
            problems.append(f"model '{name}' uses unknown provider '{model.provider}'")
    if not problems:  # the names resolve, so each job's adapter is known
        for name, job in config.jobs.items():
            adapter = config.providers[config.models[job.model].provider].adapter
            if adapter == "anthropic" and job.max_tokens is None:
                problems.append(f"job '{name}' needs max_tokens (a chat model)")
    for name in config.router.order:
        if name not in config.jobs:
            problems.append(f"router uses unknown job '{name}'")
    if problems:
        raise LlmConfigError("LLM config not loaded:\n- " + "\n- ".join(problems))


def load(path: Path = CONFIG_FILE) -> LlmConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    try:
        config = LlmConfig.model_validate(raw)
    except ValueError as e:  # pydantic's ValidationError: a missing field or a bad value
        raise LlmConfigError(f"LLM config not loaded:\n{e}") from e
    check(config)
    return config


@cache
def get_config() -> LlmConfig:
    """The real config, loaded once per process."""
    return load()

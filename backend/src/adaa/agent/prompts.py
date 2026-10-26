"""Load the versioned prompt files (prompts/*.md) and fill them (§0 M1.3, Prompt).

A prompt file starts with `version: x.y.z`, raised by hand when the meaning changes. The
fingerprint (SHA-256 of the file) changes with any edit at all, so each answer can record
exactly which prompt produced it. Placeholders are `{{name}}`: `$` (as in R$) and the
single braces of JSON examples stay plain text. Filling is strict: a missing value is an
error, so a prompt never goes out with a `{{name}}` left in it.

The lists of metrics and dimensions come from the semantic layer, and the lists of real
values from the data (values.py), so nothing is written twice: a new metric in
metrics.yaml appears in the prompt by itself.
"""

import hashlib
import re
import string
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from adaa.agent.values import ValueCatalogue
from adaa.semantic_layer.definitions import SemanticLayer
from adaa.settings import REPO_ROOT

PROMPTS_DIR = REPO_ROOT / "prompts"
VERSION_LINE = re.compile(r"\Aversion: (\d+\.\d+\.\d+)\n")


class PromptError(Exception):
    """A prompt file is wrong, or a placeholder has no value."""


class PromptTemplate(string.Template):
    """string.Template with `{{name}}` placeholders instead of `$name`."""

    delimiter = "{{"
    pattern = r"""
        \{\{(?:
          (?P<escaped>(?!))                   |  # no escape form needed
          (?P<named>[a-z_][a-z0-9_]*)\}\}     |
          (?P<braced>(?!))                    |
          (?P<invalid>(?!))
        )
    """  # type: ignore[assignment]


class Prompt(BaseModel):
    """A filled prompt, with what each answer records about it."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    fingerprint: str
    text: str


def load_prompt(name: str, values: dict[str, str], prompts_dir: Path = PROMPTS_DIR) -> Prompt:
    raw = (prompts_dir / f"{name}.md").read_text(encoding="utf-8")
    found = VERSION_LINE.match(raw)
    if not found:
        raise PromptError(f"prompts/{name}.md must start with a line 'version: x.y.z'")
    body = raw[found.end() :].lstrip("\n")
    try:
        text = PromptTemplate(body).substitute(values)
    except KeyError as e:
        raise PromptError(f"prompts/{name}.md needs a value for {{{{{e.args[0]}}}}}") from e
    return Prompt(
        name=name,
        version=found.group(1),
        fingerprint=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        text=text,
    )


def metric_lines(layer: SemanticLayer) -> str:
    """One line per metric, with the dimensions it allows (the compiler's own rules)."""
    lines = []
    for name, metric in layer.metrics.items():
        allowed = [d for d in layer.dimensions if layer.allows(name, d)]
        lines.append(
            f"- `{name}` ({', '.join(metric.terms)}): {metric.description}"
            f" Dimensions allowed: {', '.join(allowed)}."
        )
    return "\n".join(lines)


def dimension_lines(layer: SemanticLayer) -> str:
    return "\n".join(
        f"- `{name}` ({', '.join(d.terms)}): {d.label}" for name, d in layer.dimensions.items()
    )


def semantic_values(
    layer: SemanticLayer, catalogue: ValueCatalogue, data_as_of: date
) -> dict[str, str]:
    """The agent prompt's placeholder values, built from the semantic layer and the data."""
    # Only the defaults that change how the form is filled. The others (thin months, one
    # customer = one person, "best customers") are about the answer, which shows them.
    status = layer.defaults["default_status_filter"].shown_in_answer.removesuffix(".")
    defaults = [
        f"- {status}, unless the question names an order status.",
        f"- {layer.defaults['default_period'].shown_in_answer}",
    ]
    return {
        "metrics": metric_lines(layer),
        "dimensions": dimension_lines(layer),
        "defaults": "\n".join(defaults),
        "values": catalogue.prompt_text(),
        "data_as_of": data_as_of.isoformat(),
    }

"""
run_experiment.py -- run the code-writing system through ADAA's full-eval harness.

It swaps the pipeline the harness calls (`run_pipeline`) for `run_codegen`, then runs
eval/run_full_eval.py unchanged, so records, scoring against ground truth, crash-safe saving,
manifest, preflight, --resume and --dry-run all behave exactly as for ADAA. Results go in
llm_codegen_experiment/results/full_<timestamp>/ with `system: codegen` added to the manifest.

Usage (from the project root; every option of eval/run_full_eval.py works):
    python llm_codegen_experiment/run_experiment.py --dry-run
    python llm_codegen_experiment/run_experiment.py --ids Q01,Q06 --yes
    python llm_codegen_experiment/run_experiment.py --repeats 3
    python llm_codegen_experiment/run_experiment.py --resume llm_codegen_experiment/results/full_<timestamp>

Note: the harness marks the 10 compound cases (Q38-Q47, correct behaviour = refuse) as failures for this
system because it has no way to refuse. The comparison step reports those 10 separately.
"""

import hashlib
import json
import os
import sys
from typing import List, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import eval.run_eval as single_mod                       # noqa: E402
import eval.run_full_eval as harness                     # noqa: E402
import eval.run_multiturn_eval as multi_mod              # noqa: E402
from llm_codegen_experiment import codegen_baseline as cb  # noqa: E402
from llm_codegen_experiment.codegen_baseline import run_codegen  # noqa: E402

RESULTS_DIR = os.path.join(_ROOT, "llm_codegen_experiment", "results")


def _file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def _newest_run_dir(out_dir: str, before: set) -> Optional[str]:
    after = {d for d in os.listdir(out_dir) if d.startswith("full_")} if os.path.isdir(out_dir) else set()
    new = sorted(after - before)
    return os.path.join(out_dir, new[-1]) if new else None


def _stamp_manifest(run_dir: str) -> None:
    """Record which system produced this folder and exactly which code and prompt it used."""
    path = os.path.join(run_dir, "manifest.json")
    if not os.path.exists(path):
        return
    manifest = json.load(open(path, encoding="utf-8"))
    manifest["system"] = "codegen"
    manifest["codegen"] = {
        "version": cb.CODEGEN_VERSION,
        "history_window": cb.HISTORY_WINDOW,
        "sandbox_timeout_s": cb.SANDBOX_TIMEOUT_S,
        "code_sha256_16": _file_hash(cb.__file__),
        "system_prompt_sha256_16": hashlib.sha256(cb.SYSTEM_PROMPT.encode()).hexdigest()[:16],
        "note": "one LLM call writes pandas code (planner's model and settings), static check, restricted "
                "subprocess; no retry, no critic, no answer-writing step",
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--out-dir" not in args:
        args += ["--out-dir", RESULTS_DIR]
    out_dir = args[args.index("--out-dir") + 1]
    resuming = "--resume" in args
    before = {d for d in os.listdir(out_dir) if d.startswith("full_")} if os.path.isdir(out_dir) else set()

    # Swap the pipeline the harness calls; always put the originals back.
    original = (single_mod.run_pipeline, multi_mod.run_pipeline)
    single_mod.run_pipeline = run_codegen
    multi_mod.run_pipeline = run_codegen
    try:
        code = harness.main(args)
    finally:
        single_mod.run_pipeline, multi_mod.run_pipeline = original

    run_dir = args[args.index("--resume") + 1] if resuming else _newest_run_dir(out_dir, before)
    if run_dir:
        _stamp_manifest(os.path.abspath(run_dir))
    return code


if __name__ == "__main__":      # required: the sandbox uses 'spawn', which re-imports this script
    sys.exit(main())

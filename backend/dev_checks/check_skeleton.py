"""M0.1 check: the skeleton installs, imports and loads settings.

Run from backend/:  uv run python dev_checks/check_skeleton.py
"""

import sys

import adaa
from adaa.settings import REPO_ROOT, get_settings


def main() -> None:
    print(f"Python:       {sys.version.split()[0]}  ({sys.executable})")
    print(f"adaa package: {adaa.__version__}")
    print(f".env looked up at: {REPO_ROOT / '.env'}")
    settings = get_settings()
    print(f"Settings OK:  app_env={settings.app_env}, log_level={settings.log_level}")

    assert sys.version_info[:2] == (3, 12), "expected Python 3.12 from uv"
    print("M0.1 skeleton check passed.")


if __name__ == "__main__":
    main()

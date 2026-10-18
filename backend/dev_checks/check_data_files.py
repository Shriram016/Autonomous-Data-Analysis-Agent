"""M0.3 check: the 9 Olist files are present and match manifest.json.

Run from backend/ after prepare_olist:  uv run python dev_checks/check_data_files.py
"""

import hashlib
import json

from adaa.ingestion.prepare_olist import EXPECTED_FILES, RAW_DIR


def main() -> None:
    olist_dir = RAW_DIR / "olist"
    manifest = json.loads((olist_dir / "manifest.json").read_text())
    assert set(manifest) == set(EXPECTED_FILES), "manifest lists the wrong files"

    total = 0
    for name, info in manifest.items():
        digest = hashlib.sha256((olist_dir / name).read_bytes()).hexdigest()
        assert digest == info["sha256"], f"{name} changed since the manifest was written"
        total += info["rows"]
        print(f"OK  {name:42} {info['rows']:>9,} rows")
    print(f"All 9 files match the manifest ({total:,} rows in total).")
    print("M0.3 data files check passed.")


if __name__ == "__main__":
    main()

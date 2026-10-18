"""Prepare the raw Olist files: extract the Kaggle ZIP, verify, fingerprint.

The ZIP is downloaded by hand from Kaggle into ``data/raw/`` (the licence stops us committing
the data). This script extracts the 9 expected CSVs into ``data/raw/olist/``, checks each file's
columns, counts rows, and writes ``manifest.json`` with a SHA-256 fingerprint per file so every
machine can prove it has the same data.

Run from backend/:  uv run python -m adaa.ingestion.prepare_olist [path/to/archive.zip]
"""

import csv
import hashlib
import json
import sys
import zipfile
from pathlib import Path

from adaa.settings import REPO_ROOT

RAW_DIR = REPO_ROOT / "data" / "raw"

# File name → exact header row we expect (Olist's own spelling, typos included).
EXPECTED_FILES: dict[str, list[str]] = {
    "olist_customers_dataset.csv": [
        "customer_id",
        "customer_unique_id",
        "customer_zip_code_prefix",
        "customer_city",
        "customer_state",
    ],
    "olist_geolocation_dataset.csv": [
        "geolocation_zip_code_prefix",
        "geolocation_lat",
        "geolocation_lng",
        "geolocation_city",
        "geolocation_state",
    ],
    "olist_order_items_dataset.csv": [
        "order_id",
        "order_item_id",
        "product_id",
        "seller_id",
        "shipping_limit_date",
        "price",
        "freight_value",
    ],
    "olist_order_payments_dataset.csv": [
        "order_id",
        "payment_sequential",
        "payment_type",
        "payment_installments",
        "payment_value",
    ],
    "olist_order_reviews_dataset.csv": [
        "review_id",
        "order_id",
        "review_score",
        "review_comment_title",
        "review_comment_message",
        "review_creation_date",
        "review_answer_timestamp",
    ],
    "olist_orders_dataset.csv": [
        "order_id",
        "customer_id",
        "order_status",
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "olist_products_dataset.csv": [
        "product_id",
        "product_category_name",
        "product_name_lenght",
        "product_description_lenght",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ],
    "olist_sellers_dataset.csv": [
        "seller_id",
        "seller_zip_code_prefix",
        "seller_city",
        "seller_state",
    ],
    "product_category_name_translation.csv": [
        "product_category_name",
        "product_category_name_english",
    ],
}


class OlistFileError(Exception):
    """The ZIP or a file in it is not what we expect."""


def find_zip(raw_dir: Path) -> Path:
    zips = sorted(raw_dir.glob("*.zip"))
    if len(zips) != 1:
        raise OlistFileError(
            f"Expected exactly one .zip in {raw_dir}, found {len(zips)}. "
            "Download the dataset from Kaggle and put the ZIP there."
        )
    return zips[0]


def extract(zip_path: Path, out_dir: Path) -> None:
    """Extract only the expected CSVs, wherever they sit inside the ZIP."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        members = {Path(name).name: name for name in archive.namelist()}
        missing = sorted(set(EXPECTED_FILES) - set(members))
        if missing:
            raise OlistFileError(f"ZIP is missing: {', '.join(missing)}")
        for file_name in EXPECTED_FILES:
            (out_dir / file_name).write_bytes(archive.read(members[file_name]))


def describe(path: Path, expected_header: list[str]) -> dict[str, object]:
    """Check the header, count rows (a quoted review can span lines), fingerprint the file."""
    # utf-8-sig drops the byte-order mark some Olist files start with.
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        if header != expected_header:
            raise OlistFileError(f"{path.name}: header {header} != expected {expected_header}")
        rows = sum(1 for _ in reader)
    return {
        "rows": rows,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def prepare(zip_path: Path | None = None, raw_dir: Path = RAW_DIR) -> dict[str, dict[str, object]]:
    zip_path = zip_path or find_zip(raw_dir)
    out_dir = raw_dir / "olist"
    extract(zip_path, out_dir)
    manifest = {name: describe(out_dir / name, header) for name, header in EXPECTED_FILES.items()}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    zip_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    manifest = prepare(zip_arg)
    for name, info in manifest.items():
        print(f"{name:42} {info['rows']:>9,} rows")
    print(f"Wrote {RAW_DIR / 'olist' / 'manifest.json'}")


if __name__ == "__main__":
    main()

import json
import zipfile
from pathlib import Path

import pytest

from adaa.ingestion.prepare_olist import EXPECTED_FILES, OlistFileError, prepare

REVIEWS = "olist_order_reviews_dataset.csv"


def make_zip(tmp_path: Path, skip: str | None = None, bad_header: str | None = None) -> Path:
    """A tiny fake Olist ZIP: right file names, right headers, one data row each."""
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for name, header in EXPECTED_FILES.items():
            if name == skip:
                continue
            cols = ["wrong"] + header[1:] if name == bad_header else header
            row = ",".join("x" for _ in header)
            if name == REVIEWS:  # a review comment spanning two lines, like the real data
                row = 'r1,o1,5,,"great\nproduct",2018-01-01,2018-01-02'
            archive.writestr(f"nested/{name}", ",".join(cols) + "\n" + row + "\n")
    return zip_path


def test_extracts_counts_and_fingerprints(tmp_path: Path) -> None:
    manifest = prepare(make_zip(tmp_path), raw_dir=tmp_path)

    assert set(manifest) == set(EXPECTED_FILES)
    assert manifest[REVIEWS]["rows"] == 1  # the two-line review counts as one row
    assert len(str(manifest[REVIEWS]["sha256"])) == 64
    saved = json.loads((tmp_path / "olist" / "manifest.json").read_text())
    assert saved == manifest


def test_missing_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(OlistFileError, match="olist_sellers_dataset.csv"):
        prepare(make_zip(tmp_path, skip="olist_sellers_dataset.csv"), raw_dir=tmp_path)


def test_unexpected_header_is_reported(tmp_path: Path) -> None:
    with pytest.raises(OlistFileError, match="olist_orders_dataset.csv"):
        prepare(make_zip(tmp_path, bad_header="olist_orders_dataset.csv"), raw_dir=tmp_path)


def test_no_zip_gives_clear_instruction(tmp_path: Path) -> None:
    with pytest.raises(OlistFileError, match="Download the dataset from Kaggle"):
        prepare(raw_dir=tmp_path)

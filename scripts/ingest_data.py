"""Ingest raw datasets into the processed store.

Usage:
    python scripts/ingest_data.py --sample          # use data/sample/
    python scripts/ingest_data.py --full            # use data/raw/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.ingestion import Ingester


def main():
    ap = argparse.ArgumentParser(description="Ingest PharmGuard datasets.")
    ap.add_argument("--sample", action="store_true", help="Ingest from data/sample/")
    ap.add_argument("--full", action="store_true", help="Ingest from data/raw/")
    args = ap.parse_args()

    if not (args.sample or args.full):
        ap.error("Specify --sample or --full.")

    ing = Ingester()

    if args.sample:
        print("Ingesting from data/sample/ ...")
        report = ing.ingest_sample()
    else:
        print("Ingesting from data/raw/ ...")
        report = ing.ingest_full()

    print("\n=== Ingestion report ===")
    print(json.dumps(report, indent=2))

    if not report:
        print(
            "\nNo datasets ingested. For --full mode, place dataset files in data/raw/.\n"
            "See docs/DATASETS.md for filenames and download links."
        )


if __name__ == "__main__":
    main()

"""Ingest datasets into the processed store.

Usage:
    python scripts/ingest_data.py --sample                       # synthetic sample -> data/processed/
    python scripts/ingest_data.py --full --profile public        # real data -> data/profiles/public/processed/
    python scripts/ingest_data.py --full --profile research      # + TWOSIDES (local evaluation only)

Real data must be fetched first: python scripts/fetch_data.py [--with-twosides].
Point the app at a real build with PHARMGUARD_DATA_DIR=data/profiles/<profile>.
"""
from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.ingestion import Ingester  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Ingest PharmGuard datasets.")
    ap.add_argument("--sample", action="store_true", help="Ingest the synthetic sample from data/sample/")
    ap.add_argument("--full", action="store_true", help="Ingest real data from --raw-dir")
    ap.add_argument("--profile", choices=["public", "research"], default="public")
    ap.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--out-dir", default=None, help="Default: data/profiles/<profile>")
    ap.add_argument("--drugbank-csv", default=None, help="Optional DrugBank vocabulary CSV (CC0)")
    args = ap.parse_args()
    if not (args.sample or args.full):
        ap.error("Specify --sample or --full.")

    t0 = time.perf_counter()
    if args.sample:
        print("Ingesting from data/sample/ ...")
        report = Ingester().ingest_sample()
    else:
        from src.data.real_ingest import ingest_real
        out = Path(args.out_dir or ROOT / "data" / "profiles" / args.profile)
        print(f"Ingesting real data ({args.profile} profile) from {args.raw_dir} -> {out}/processed ...")
        report = ingest_real(Path(args.raw_dir), out, args.profile, args.drugbank_csv)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mb = peak / (1 << 20) if sys.platform == "darwin" else peak / 1024
    print("\n=== Ingestion report ===")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWall time {time.perf_counter() - t0:.1f}s, peak memory {peak_mb:.0f} MB")


if __name__ == "__main__":
    main()

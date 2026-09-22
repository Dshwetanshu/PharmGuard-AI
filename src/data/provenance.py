"""Data provenance: what was ingested, recorded at ingest and stated in every report.

The report footer is generated from this record, never hand-written, so a
report can't claim a data source that wasn't loaded.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

PROVENANCE_FILE = "provenance.json"


def write_provenance(processed_dir: Path, mode: str, report: dict) -> Path:
    """Record what an ingestion run produced. mode is "sample" or "full"."""
    interactions = report.get("interactions") or {}
    data = {
        "mode": mode,
        # The CSVs in data/sample/ are hand-written synthetic records.
        "synthetic": mode == "sample",
        "interaction_records": int(interactions.get("rows", 0)),
        "interactions_by_source": {k: int(v) for k, v in (interactions.get("by_source") or {}).items()},
    }
    path = Path(processed_dir) / PROVENANCE_FILE
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return path


def read_provenance(processed_dir: Path) -> Optional[dict]:
    path = Path(processed_dir) / PROVENANCE_FILE
    return json.loads(path.read_text()) if path.exists() else None


def provenance_line(processed_dir: Path) -> str:
    data = read_provenance(processed_dir)
    if data is None:
        return "Data: no ingestion record found; data provenance unknown."
    n = data["interaction_records"]
    if data.get("synthetic"):
        return f"Data: synthetic sample dataset ({n} interaction records), not real clinical data."
    sources = ", ".join(f"{k} {v}" for k, v in sorted(data["interactions_by_source"].items())) or "no sources"
    return f"Data: {n} interaction records ingested from data/raw ({sources})."

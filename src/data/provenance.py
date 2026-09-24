"""Data provenance: what was ingested, recorded at ingest and stated in every report.

The report footer is generated from this record, never hand-written, so a
report can't claim a data source that wasn't loaded.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Dict, Optional

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


SOURCE_LABELS = {
    "ddinter": "DDInter 2.0",
    "sider": "SIDER 4.1",
    "rxnorm": "RxNorm Current Prescribable",
    "drugbank": "DrugBank vocabulary",
    "twosides": "TWOSIDES (research only; not for redistribution)",
}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def processed_file_hashes(processed_dir: Path) -> Dict[str, str]:
    """sha256 of every file in the build except provenance.json itself. Recorded in
    provenance so a downloaded copy of the build can be verified file by file."""
    return {p.name: file_sha256(p) for p in sorted(Path(processed_dir).iterdir())
            if p.is_file() and p.name != PROVENANCE_FILE}


def write_real_provenance(processed_dir: Path, profile: str, manifest: Dict, report: Dict) -> Path:
    """Record a real-data build: per source URL, version, license, download date, sha256,
    row counts, filters and unmatched counts, plus the profile and vocabulary stats."""
    used = ["rxnorm", "ddinter", "sider"] + (["twosides"] if profile == "research" else [])
    if report["vocabulary"].get("drugbank") == "merged":
        used.insert(1, "drugbank")
    sources = {}
    for key in used:
        m = manifest.get(key, {})
        sources[key] = {
            "title": m.get("title"), "version": m.get("version"), "license": m.get("license"),
            "homepage": m.get("homepage"),
            "files": [{k: f.get(k) for k in ("name", "url", "sha256", "bytes", "downloaded_at")}
                      for f in m.get("files", [])] or "no manifest entry (files not fetched by fetch_data.py)",
            **report.get("sources", {}).get(key, {}),
        }
    data = {
        "mode": "full", "profile": profile, "synthetic": False, "built_at": dt.date.today().isoformat(),
        "interaction_records": int(report["interactions"]["rows"]),
        "interactions_by_source": {k: int(v) for k, v in report["interactions"]["by_source"].items()},
        "side_effect_records": int(report["side_effects"]["rows"]),
        "vocabulary": {k: v for k, v in report["vocabulary"].items()},
        "vocabulary_version": manifest.get("rxnorm", {}).get("version"),
        "join_integrity_issues": len(report["join_integrity"]["issues"]),
        "sources": sources,
        "source_order": used,
        "not_for_redistribution": profile == "research",
        "processed_files": processed_file_hashes(processed_dir),
    }
    path = Path(processed_dir) / PROVENANCE_FILE
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n")
    return path


def read_provenance(processed_dir: Path) -> Optional[dict]:
    path = Path(processed_dir) / PROVENANCE_FILE
    return json.loads(path.read_text()) if path.exists() else None


def data_stamp(processed_dir: Path) -> Dict[str, Optional[str]]:
    """Which build a result came from: profile, data line and sha256 of provenance.json."""
    path = Path(processed_dir) / PROVENANCE_FILE
    data = read_provenance(processed_dir)
    profile = None
    if data is not None:
        profile = data.get("profile") or ("sample" if data.get("synthetic") else data.get("mode"))
    return {"profile": profile, "data": provenance_line(processed_dir),
            "provenance_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None}


def provenance_line(processed_dir: Path) -> str:
    data = read_provenance(processed_dir)
    if data is None:
        return "Data: no ingestion record found; data provenance unknown."
    n = data["interaction_records"]
    if data.get("mode") == "full":
        labels = []
        for key in data.get("source_order", sorted(data["sources"])):
            label = SOURCE_LABELS.get(key, key)
            version = data["sources"][key].get("version")
            labels.append(f"{label} {version}" if key == "rxnorm" and version else label)
        return (f"Data: {data['profile']} build from " + ", ".join(labels)
                + f"; {n:,} interaction records; not synthetic.")
    if data.get("synthetic"):
        return f"Data: synthetic sample dataset ({n} interaction records), not real clinical data."
    sources = ", ".join(f"{k} {v}" for k, v in sorted(data["interactions_by_source"].items())) or "no sources"
    return f"Data: {n} interaction records ingested from data/raw ({sources})."

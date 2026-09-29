"""Verify data/validation/reference_interactions.csv automatically against FDA labeling (openFDA).

For every row: fetch each drug's current label (cached in data/cache/openfda_labels/), look for the
other drug in its Boxed Warning, Contraindications, Warnings/Precautions and Drug Interactions,
classify the wording heuristically (src/evaluation/label_evidence.py) and decide:
- settled interaction: verified_source / verified_on filled, min_severity from the label wording;
- settled negative control: neither label names the other drug (weak evidence);
- unclear: left unverified (so the scorer skips it) and listed in notes/reference_unclear.md.
Full evidence goes to data/validation/label_evidence.json. drugscom_severity is never touched.

    python scripts/verify_reference_labels.py
"""
from __future__ import annotations

import csv
import datetime
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from src.data.canonical import build_alias_map  # noqa: E402
from src.evaluation.label_evidence import (  # noqa: E402
    AS_SEVERITY, CLASS_TEXT, LABEL_ENDPOINT, choose_label, decide, pair_evidence,
)
from src.evaluation.reference_set import COLUMNS  # noqa: E402
from src.retrieval.faers_retriever import OpenFdaCounts  # noqa: E402

CSV_PATH = ROOT / "data" / "validation" / "reference_interactions.csv"
EVIDENCE = ROOT / "data" / "validation" / "label_evidence.json"
UNCLEAR = ROOT / "notes" / "reference_unclear.md"
ALIAS_KINDS = {"RXNORM:IN", "RXNORM:PIN", "RXNORM:BN", "RXNORM:SY", "DRUGSATFDA:BRAND", "MTHSPL:SU", "REVIEWED_ALIAS"}


def fetch_all(client: OpenFdaCounts, drug: str, max_labels: int = 500):
    out, skip, total = [], 0, None
    while total is None or (skip < total and skip < max_labels):
        url = LABEL_ENDPOINT + "?" + urlencode({"search": f'openfda.generic_name:"{drug}"', "limit": "100",
                                                "skip": str(skip)})
        payload = client.get(url) or {}
        total = ((payload.get("meta") or {}).get("results") or {}).get("total", 0)
        out += payload.get("results") or []
        skip += 100
    return out, total


def main() -> int:
    vocab = pd.read_parquet(ROOT / "data" / "profiles" / "public" / "processed" / "drug_vocabulary.parquet")
    to_canonical = build_alias_map(vocab).get
    aliases = vocab[vocab.kind.isin(ALIAS_KINDS)].groupby("generic_name").name_lower.apply(list).to_dict()
    with CSV_PATH.open(newline="") as f:
        rows = list(csv.DictReader(f))
    client = OpenFdaCounts(cache_dir=ROOT / "data" / "cache" / "openfda_labels", timeout_s=60)
    drugs = sorted({r[k] for r in rows for k in ("drug_a", "drug_b")})
    labels, totals = {}, {}
    for d in drugs:
        results, totals[d] = fetch_all(client, d)
        labels[d] = choose_label(d, results, to_canonical)
    today = datetime.date.today().isoformat()
    evidence, unclear = [], []
    for r in rows:
        a, b = r["drug_a"], r["drug_b"]
        ev = pair_evidence(a, b, labels, aliases)
        ref, reason = decide(r["expected"], ev)
        hint = r["notes"].split(" | label:")[0]
        r["verified_source"], r["verified_on"] = "", ""
        if ref == "interaction":
            m = ev.best
            r["verified_source"] = f"openFDA label: {m.label_drug} set_id {m.set_id} v{m.version} ({m.section})"
            r["verified_on"] = today
            if r["min_severity"] and r["min_severity"] != AS_SEVERITY[ev.klass]:
                hint += f" | hypothesis min_severity {r['min_severity']}"
            r["min_severity"] = AS_SEVERITY[ev.klass]
            r["notes"] = f"{hint} | label: {CLASS_TEXT[ev.klass]} — \"{m.snippet}\""
        elif ref == "none_weak":
            la, lb = ev.labels_found[a], ev.labels_found[b]
            r["verified_source"] = (f"openFDA labels: {a} set_id {la['set_id']} v{la['version']}; "
                                    f"{b} set_id {lb['set_id']} v{lb['version']} (neither names the other)")
            r["verified_on"] = today
            r["notes"] = f"{hint} | label: not mentioned in either label (weak evidence of no interaction)"
        else:
            r["notes"] = hint
            unclear.append((r, reason, ev))
        evidence.append({"row": {k: r[k] for k in ("drug_a", "drug_b", "expected")}, "reference": ref,
                         "reason": reason, "evidence": ev.to_dict()})
    with CSV_PATH.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    EVIDENCE.write_text(json.dumps({"fetched_on": today, "method": "src/evaluation/label_evidence.py (heuristic wording classes)",
                                    "labels": {d: (l.__dict__ | {"sections": sorted(l.sections)}) if l else None
                                               for d, l in labels.items()},
                                    "label_counts": totals, "pairs": evidence}, indent=1, default=str) + "\n")
    L = ["# Reference rows the FDA labels don't settle", "",
         f"Local notes. From `python scripts/verify_reference_labels.py` on {today}. These rows are excluded from "
         "scoring (the scorer counts them as unverified).", "",
         "| Pair | Expected | Why unclear | Strongest label wording found |", "|---|---|---|---|"]
    for r, reason, ev in unclear:
        L.append(f"| {r['drug_a']} + {r['drug_b']} | {r['expected']} | {reason} | "
                 + (f"{CLASS_TEXT[ev.klass]}: \"{ev.best.snippet}\"" if ev.best else "—") + " |")
    UNCLEAR.write_text("\n".join(L) + "\n")
    n = {k: sum(1 for e in evidence if e["reference"] == k) for k in ("interaction", "none_weak", "unclear")}
    print(f"{len(rows)} rows: {n}. openFDA calls: {client.network_calls}. Labels not found: "
          f"{[d for d, l in labels.items() if l is None]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

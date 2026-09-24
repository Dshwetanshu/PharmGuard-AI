"""Attribution notices come from provenance, and docs/DATASETS.md embeds the generated block."""
from __future__ import annotations

from pathlib import Path

from src.data.attribution import (
    DOC_END, DOC_START, NONCOMMERCIAL_NOTICE, RXNORM_STATEMENT, TWOSIDES_NOTICE, datasets_md_block,
    notices_for_provenance,
)

ROOT = Path(__file__).resolve().parent.parent


def _prov(order):
    return {"mode": "full", "profile": "x", "source_order": order,
            "sources": {k: ({"version": "2026-09-08"} if k == "rxnorm" else {}) for k in order}}


def test_public_build_notices():
    text = " ".join(n.text for n in notices_for_provenance(_prov(["rxnorm", "ddinter", "sider"])))
    assert "DDInter bulk download (ddinter2.scbdd.com, files dated 2024-05-21)" in text
    assert "doi:10.1093/nar/gkae726" in text and "doi:10.1093/nar/gkab880" in text and "CC BY-NC-SA 4.0" in text
    assert "DDInter 2.0 data" not in text and "(DDInter 2.0" not in text
    assert "The SIDER database of drugs and side effects" in text and "doi:10.1093/nar/gkv1075" in text
    assert RXNORM_STATEMENT in text and "release 2026-09-08" in text
    assert "Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)" in text
    assert NONCOMMERCIAL_NOTICE in text
    assert "TWOSIDES" not in text


def test_research_build_adds_the_twosides_notice():
    notices = notices_for_provenance(_prov(["rxnorm", "ddinter", "sider", "twosides"]))
    assert any(TWOSIDES_NOTICE in n.text for n in notices)
    assert TWOSIDES_NOTICE == "TWOSIDES: research use only, not for redistribution"


def test_sample_build_has_no_third_party_dataset_notices():
    keys = [n.key for n in notices_for_provenance({"mode": "sample", "synthetic": True})]
    assert keys == ["synthetic", "openfda"]


def test_datasets_doc_embeds_the_generated_block():
    doc = (ROOT / "docs" / "DATASETS.md").read_text()
    start, end = doc.index(DOC_START), doc.index(DOC_END) + len(DOC_END)
    assert doc[start:end] == datasets_md_block(), "regenerate the block with src.data.attribution.datasets_md_block()"

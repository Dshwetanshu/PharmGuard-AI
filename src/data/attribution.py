"""Attribution and license notices, generated from a build's provenance.

One place for every notice. The Streamlit app shows notices_for_dir(processed_dir);
docs/DATASETS.md embeds datasets_md_block(), and a test keeps the two in sync.
A notice is shown only for a source the build actually loaded (provenance
"source_order"), except openFDA, which is queried at runtime when the optional
FAERS lookup is on.

Citations checked against PubMed (PMID 39180399 and 26481350 on 2026-09-23, 34634800 on 2026-09-24).
The RxNorm statement is NLM's required wording for Current Prescribable Content.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from src.data.provenance import read_provenance
from src.data.sources import SOURCES


@dataclass(frozen=True)
class Notice:
    key: str
    title: str
    text: str


DDINTER_LABEL = "DDInter bulk download (ddinter2.scbdd.com, files dated 2024-05-21)"
# Both papers are cited: the files come from the DDInter 2.0 site, but their counts match the
# DDInter 1.0 paper's figures (docs/DATASETS.md), so we don't call the data "DDInter 2.0".
DDINTER2_CITATION = (
    "Tian Y, Yi J, Wang N, Wu C, Peng J, Liu S, Yang G, Cao D. DDInter 2.0: an enhanced drug "
    "interaction resource with expanded data coverage, new interaction types, and improved user "
    "interface. Nucleic Acids Research. 2025;53(D1):D1356-D1362. doi:10.1093/nar/gkae726"
)
DDINTER1_CITATION = (
    "Xiong G, Yang Z, Yi J, Wang N, Wang L, Zhu H, Wu C, Lu A, Chen X, Liu S, Hou T, Cao D. DDInter: an "
    "online drug-drug interaction database towards improving clinical decision-making and patient "
    "safety. Nucleic Acids Research. 2022;50(D1):D1200-D1207. doi:10.1093/nar/gkab880"
)
SIDER_CITATION = (
    "Kuhn M, Letunic I, Jensen LJ, Bork P. The SIDER database of drugs and side effects. "
    "Nucleic Acids Research. 2016;44(D1):D1075-D1079. doi:10.1093/nar/gkv1075"
)
RXNORM_STATEMENT = (
    "This product uses publicly available data courtesy of the U.S. National Library of Medicine (NLM), "
    "National Institutes of Health, Department of Health and Human Services; NLM is not responsible for "
    "the product and does not endorse or recommend this or any other product."
)
OPENFDA_CREDIT = "Data provided by the U.S. Food and Drug Administration (https://open.fda.gov)"
TWOSIDES_NOTICE = "TWOSIDES: research use only, not for redistribution"
NONCOMMERCIAL_NOTICE = (
    "This build contains data licensed CC BY-NC-SA 4.0 (DDInter, SIDER 4.1). Non-commercial use "
    "only; anything derived from that data must be shared under the same license, with the "
    "attributions above."
)
SYNTHETIC_NOTICE = ("Synthetic sample data: hand-written records for testing, not taken from any dataset "
                    "and not real clinical data.")


def notices_for(source_keys: Iterable[str], rxnorm_version: Optional[str] = None,
                synthetic: bool = False) -> List[Notice]:
    """Notices for a build that loaded `source_keys` (e.g. provenance["source_order"])."""
    keys = list(source_keys)
    out: List[Notice] = []
    if synthetic:
        out.append(Notice("synthetic", "Sample data", SYNTHETIC_NOTICE))
    if "ddinter" in keys:
        out.append(Notice("ddinter", "DDInter",
                          f"Interaction severities from the {DDINTER_LABEL}. Cite: {DDINTER2_CITATION}; and "
                          f"{DDINTER1_CITATION}. Licensed CC BY-NC-SA 4.0 "
                          "(https://creativecommons.org/licenses/by-nc-sa/4.0/). PharmGuard mapped drug names "
                          "to RxNorm and removed duplicates."))
    if "sider" in keys:
        out.append(Notice("sider", "SIDER 4.1",
                          f"{SIDER_CITATION}. Licensed CC BY-NC-SA 4.0 "
                          "(https://creativecommons.org/licenses/by-nc-sa/4.0/)."))
    if "rxnorm" in keys:
        version = rxnorm_version or SOURCES["rxnorm"].version
        out.append(Notice("rxnorm", "RxNorm",
                          f"{RXNORM_STATEMENT} Vocabulary: RxNorm Current Prescribable Content, release "
                          f"{version}; drug names may have changed since that release. NLM urges you to "
                          "consult with a qualified physician for medical advice."))
    if "drugbank" in keys:
        out.append(Notice("drugbank", "DrugBank vocabulary",
                          "Drug synonyms from the DrugBank Open Data vocabulary (CC0 1.0), https://go.drugbank.com."))
    out.append(Notice("openfda", "openFDA",
                      f"{OPENFDA_CREDIT}. Used only when the optional FAERS lookup is enabled; FAERS reports "
                      "are unvalidated, and the FDA does not endorse this product."))
    if "twosides" in keys:
        out.append(Notice("twosides", "TWOSIDES", TWOSIDES_NOTICE + " (no license stated by the publisher)."))
    if {"ddinter", "sider"} & set(keys):
        out.append(Notice("noncommercial", "Non-commercial use", NONCOMMERCIAL_NOTICE))
    return out


def notices_for_provenance(prov: Optional[dict]) -> List[Notice]:
    if prov is None:
        return notices_for([])
    if prov.get("mode") != "full":
        return notices_for([], synthetic=bool(prov.get("synthetic")))
    keys = prov.get("source_order") or sorted(prov.get("sources", {}))
    return notices_for(keys, (prov.get("sources", {}).get("rxnorm") or {}).get("version"))


def notices_for_dir(processed_dir: Path) -> List[Notice]:
    return notices_for_provenance(read_provenance(processed_dir))


def notices_markdown(notices: List[Notice]) -> str:
    return "\n".join(f"- **{n.title}.** {n.text}" for n in notices)


DOC_START, DOC_END = "<!-- attribution:start (generated by src/data/attribution.py) -->", "<!-- attribution:end -->"


def datasets_md_block() -> str:
    """The attribution block of docs/DATASETS.md: the public build, then what the research build adds."""
    public = notices_for(["rxnorm", "ddinter", "sider"])
    research_extra = [n for n in notices_for(["rxnorm", "ddinter", "sider", "twosides"])
                      if n.key not in {p.key for p in public}]
    return "\n".join([DOC_START, "", "Public build (and the Streamlit app on it):", "", notices_markdown(public), "",
                      "The research build adds:", "", notices_markdown(research_extra), "", DOC_END])

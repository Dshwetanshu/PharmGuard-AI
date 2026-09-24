"""Pinned real-data sources (docs/DATASETS.md, notes/REAL_DATA_PLAN.md).

Each file has a pinned URL and, once verified, a pinned sha256. scripts/fetch_data.py
downloads into data/raw/ (gitignored) and refuses a file whose hash doesn't match.
Nothing here is data; only where to get it and what it must hash to.

Profiles:
- "public": RxNorm Current Prescribable, DrugBank vocabulary (when available),
  DDInter 2.0, SIDER 4.1. Everything it builds may appear in the public demo.
- "research": public + TWOSIDES. TWOSIDES has no stated license, so it is for
  local evaluation only and must never enter the Hugging Face bundle, the demo
  or a commit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

PROFILES = ("public", "research")


@dataclass(frozen=True)
class SourceFile:
    url: str
    name: str                     # file name under data/raw/<source>/
    sha256: Optional[str] = None  # pinned after first verified download
    md5: Optional[str] = None     # publisher-provided checksum, if any


@dataclass(frozen=True)
class Source:
    key: str
    title: str
    version: str
    license: str
    homepage: str
    files: List[SourceFile] = field(default_factory=list)
    profiles: tuple = PROFILES
    note: str = ""


DDINTER_BASE = "https://ddinter2.scbdd.com/static/media/download"
SIDER_BASE = "https://sideeffects.embl.de/media/download"
# One file per ATC top-level group. The download page links only 8 of the 14 (A B D H L P R V);
# the other 6 (C G J M N S: cardiovascular, genito-urinary, anti-infectives, musculo-skeletal,
# nervous system, sensory organs) sit in the same directory with the same 2024-05-21 date.
# Without them, e.g. lisinopril + spironolactone and warfarin + aspirin are missing.
DDINTER_ATC_CODES = "ABCDGHJLMNPRSV"
# sha256 pinned from the verified downloads of 2026-09-23.
DDINTER_SHA256 = {
    "A": "a22ca451d2b755ca2331886f7e00540c86f555f9f55704a59a19c691251f52e0",
    "B": "76de5115a55587f0e822e1096b684fd3ddde058fbefcbb19896df58820ace130",
    "C": "0885978959af84e183cfc86c8bcb48536f690a4c7e951eff06607a5616883aeb",
    "D": "c0627ec39965dbe27829e4934cd20d71eb079f4e373287678737bba9423a306a",
    "G": "6a4d8d1eaac6da1ffc54bd23a625f9c5e28e3ca37bd26b3bca4d2cc26505fb99",
    "H": "f0f925f0ba1ee68c4668d3e7a6732719b34623b22a0f5d017f9090e59f63c88e",
    "J": "e5dbb8e5cb3179905b426ee4a2ee5c93756c38cdd54215a55c5b8255a5b14e04",
    "L": "f54f4486cc00344f8c86508c31c2ca3fad6d1d37ec3af5bcf609b4bbda5507ef",
    "M": "2a57eb78818803b4662116490023c20c8bbfe145e60c35680a0efb8ac635a0ad",
    "N": "854733ff382210b030bcece135113f01ca3f6924d3803feca2ff71c1d939c797",
    "P": "83f8c0edb20d09ef29b8500b48f9623e208379525688ade9e70a7df2d8749d55",
    "R": "1c39c3d4a6e41659b7a988538d7f363867592abc6f41a815de8746f6e2150574",
    "S": "c3888df996d97ebf1346b11a98df0b334cfa3c150a89a31150ffd354eebcbfe5",
    "V": "353973fb300453946aea95733e8fb52338e4b59426d2ce6ca318363d4f84f10a",
}

SOURCES: Dict[str, Source] = {
    "rxnorm": Source(
        "rxnorm", "RxNorm Current Prescribable Content", "2026-09-08",
        "Public domain (NLM; no UMLS license required for this subset)",
        "https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html",
        [SourceFile("https://download.nlm.nih.gov/rxnorm/RxNorm_full_prescribe_09082026.zip",
                    "RxNorm_full_prescribe_09082026.zip",
                    sha256="82cc1679aff08005c6715d68aaf4f6f00a12a14516e6be1c0c2c5950d586fbb4", md5="88bbe4cefabd8e71f58651c1c3188646")],
    ),
    "drugbank": Source(
        "drugbank", "DrugBank Vocabulary", "5.1.22",
        "CC0 1.0", "https://go.drugbank.com/releases/latest#open-data",
        [],   # downloads paused by DrugBank (checked 2026-09-23); pass a local file to ingest instead
        note="DrugBank has paused all downloads; the loader is ready for a manually obtained CSV.",
    ),
    "ddinter": Source(
        "ddinter", "DDInter 2.0", "bulk files dated 2024-05-21",
        "CC BY-NC-SA 4.0 (treated as; NAR article is CC BY-NC)", "https://ddinter2.scbdd.com/download/",
        [SourceFile(f"{DDINTER_BASE}/ddinter_downloads_code_{c}.csv", f"ddinter_downloads_code_{c}.csv",
                    sha256=DDINTER_SHA256.get(c)) for c in DDINTER_ATC_CODES],
    ),
    "sider": Source(
        "sider", "SIDER", "4.1",
        "CC BY-NC-SA 4.0", "http://sideeffects.embl.de/download/",
        [SourceFile(f"{SIDER_BASE}/meddra_all_se.tsv.gz", "meddra_all_se.tsv.gz",
                    sha256="119b2f5319a9398da83e5fe3419889010dbacf8d3eef590251b00c025e2b3f99"),
         SourceFile(f"{SIDER_BASE}/drug_names.tsv", "drug_names.tsv",
                    sha256="6427a3e3202c71a81dff97092957aacf0700b9c01f34b07e452a1ec47c92b007")],
    ),
    "twosides": Source(
        "twosides", "TWOSIDES (nSIDES)", "S3 object dated 2024-03-30",
        "No license stated (research use only; not redistributed)", "https://nsides.io/",
        [SourceFile("http://tatonettilab-resources.s3.us-west-1.amazonaws.com/nsides/TWOSIDES.csv.xz",
                    "TWOSIDES.csv.xz", sha256="791c3629ba76b33a9e88fb483f22995e1e92b1a568523432be78d653bbf81836")],
        profiles=("research",),
    ),
}


def sources_for(profile: str) -> List[Source]:
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {PROFILES}")
    return [s for s in SOURCES.values() if profile in s.profiles]

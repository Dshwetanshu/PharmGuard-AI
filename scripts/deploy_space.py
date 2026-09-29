"""Deploy PharmGuard to Hugging Face: a public dataset with the public build, and a Docker Space.

Usage:
    python scripts/deploy_space.py --dry-run                  # list every file, change nothing
    python scripts/deploy_space.py                            # dataset commit, Space variables, Space code
    python scripts/deploy_space.py --set-hops 1               # only update PHARMGUARD_TRUSTED_PROXY_HOPS

Uses the Hugging Face API (create_commit), not git, and the token from `hf auth login`.
The dataset commit is exactly the listed files; files already in the repo that aren't
listed are deleted in the same commit. The Space gets the dataset repo id, that commit's
sha (the pinned revision) and the sha256 of provenance.json as variables. The dataset is
public, so the Space needs no token.

Refuses to deploy if:
- the build's profile isn't "public", or it's synthetic or marked not for redistribution;
- its interactions contain any source other than DDInter;
- its files don't match their sha256 in provenance;
- any file to upload comes from the research build, TWOSIDES, notes/, .env*, data/raw or a build's
  review/ folder (Drugs@FDA collisions for a person to check), or matches a local-only pattern in
  .git/info/exclude.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.attribution import (  # noqa: E402
    DDINTER1_CITATION, DDINTER2_CITATION, DDINTER_LABEL, NONCOMMERCIAL_NOTICE, RXNORM_STATEMENT, SIDER_CITATION,
)
from src.data.sources import SOURCES  # noqa: E402
from src.data.provenance import PROVENANCE_FILE, file_sha256, provenance_line  # noqa: E402

BUILD = ROOT / "data" / "profiles" / "public" / "processed"
SPACE_FILES = ["Dockerfile", ".dockerignore", "requirements-api.lock", "LICENSE"]
SPACE_DIRS = ["api", "src"]
DISCLAIMER = ("PharmGuard is a decision-support prototype, not a substitute for professional medical judgment. "
              "It reports only what its loaded data contains; absence of data is not evidence of safety. "
              "Not for clinical use.")


@dataclass
class Upload:
    path_in_repo: str
    local: Optional[Path] = None      # file on disk
    content: Optional[bytes] = None   # generated file (cards)

    @property
    def size(self) -> int:
        return self.local.stat().st_size if self.local else len(self.content)


class Refused(SystemExit):
    pass


FORBIDDEN = ("research", "twosides", "notes/", ".env", "data/raw", "review/", "__pycache__", ".pyc")
LOCAL_EXCLUDE = ROOT / ".git" / "info" / "exclude"


def local_only_patterns(exclude_file: Path = LOCAL_EXCLUDE) -> List[str]:
    """Patterns in .git/info/exclude: files that exist only on this machine and are never published."""
    if not Path(exclude_file).exists():
        return []
    lines = (l.strip() for l in Path(exclude_file).read_text().splitlines())
    return [l.lower() for l in lines if l and not l.startswith("#")]


def _matches_local(path: str, pattern: str) -> bool:
    import fnmatch
    p = pattern.lstrip("/")
    if p.endswith("/"):
        return path.startswith(p) or f"/{p}" in f"/{path}"
    return any(fnmatch.fnmatch(part, p) for part in [path, path.rsplit("/", 1)[-1]])


def guard(uploads: List[Upload], what: str, exclude_file: Path = LOCAL_EXCLUDE) -> None:
    local = local_only_patterns(exclude_file)
    for u in uploads:
        names = [u.path_in_repo.lower()] + ([str(u.local).lower()] if u.local else [])
        for bad in FORBIDDEN:
            if any(bad in n for n in names):
                raise Refused(f"REFUSED: {what} file {u.path_in_repo!r} matches forbidden pattern {bad!r}")
        for pat in local:
            if _matches_local(u.path_in_repo.lower(), pat):
                raise Refused(f"REFUSED: {what} file {u.path_in_repo!r} matches local-only pattern {pat!r} "
                              "(.git/info/exclude)")


def check_build(build: Path) -> dict:
    prov = json.loads((build / PROVENANCE_FILE).read_text())
    if prov.get("profile") != "public":
        raise Refused(f"REFUSED: build profile is {prov.get('profile')!r}, not 'public'")
    if prov.get("synthetic") or prov.get("not_for_redistribution"):
        raise Refused("REFUSED: build is synthetic or marked not for redistribution")
    if "twosides" in (prov.get("source_order") or []) or "twosides" in (prov.get("sources") or {}):
        raise Refused("REFUSED: build lists TWOSIDES as a source")
    import pandas as pd
    sources = set(pd.read_parquet(build / "interactions.parquet", columns=["source"]).source)
    if sources != {"DDInter"}:
        raise Refused(f"REFUSED: interactions contain sources {sorted(sources)}; expected only DDInter")
    files = prov.get("processed_files") or {}
    on_disk = sorted(p.name for p in build.iterdir() if p.is_file() and p.name != PROVENANCE_FILE)
    if sorted(files) != on_disk:
        raise Refused(f"REFUSED: files on disk {on_disk} differ from provenance processed_files {sorted(files)}")
    for name, sha in files.items():
        if file_sha256(build / name) != sha:
            raise Refused(f"REFUSED: {name} does not match its sha256 in provenance")
    return prov


def _pct(x) -> str:
    return "—" if x is None else f"{x:.1%}"


def dataset_card(prov: dict, build: Path) -> str:
    dd, se, voc = prov["sources"]["ddinter"], prov["sources"]["sider"], prov["vocabulary"]
    rx = prov["sources"]["rxnorm"]
    tables = [("interactions.parquet", f"{prov['interaction_records']:,} curated drug-drug interaction records "
               "(canonical drug pair, severity Major/Moderate/Minor/Unknown, source DDInter, record_id)"),
              ("side_effects.parquet", f"{prov['side_effect_records']:,} drug to side-effect rows (SIDER 4.1, MedDRA PT)"),
              ("drug_vocabulary.parquet", f"{voc['rows']:,} name aliases to canonical RxNorm ingredient names"),
              ("combination_products.parquet", f"{voc['combination_products']:,} multi-ingredient product names and their ingredients"),
              ("unmatched_ddinter.csv", f"{dd['unmatched_names']:,} DDInter names not in the vocabulary (rows excluded)"),
              ("unmatched_sider.csv", f"{se['unmatched_names']:,} SIDER names not in the vocabulary (rows excluded)"),
              ("provenance.json", "sources, versions, licenses, file sha256s, filters, match rates")]
    rows = "\n".join(f"| `processed/{n}` | {(build / n).stat().st_size:,} | {d} |" for n, d in tables)
    return f"""---
license: cc-by-nc-sa-4.0
pretty_name: PharmGuard public build (DDInter, SIDER, RxNorm vocabulary)
tags:
- drug-drug-interactions
- pharmacology
- rxnorm
size_categories:
- 100K<n<1M
configs:
- config_name: interactions
  data_files: processed/interactions.parquet
- config_name: side_effects
  data_files: processed/side_effects.parquet
- config_name: drug_vocabulary
  data_files: processed/drug_vocabulary.parquet
- config_name: combination_products
  data_files: processed/combination_products.parquet
---

# PharmGuard public build

The processed data behind the PharmGuard demo: curated drug-drug interactions from the
{DDINTER_LABEL}, side effects from SIDER 4.1, and a drug-name vocabulary from RxNorm Current
Prescribable Content (release {rx.get('version')}), all keyed on RxNorm ingredient names.

**Not for clinical use.** This is a research and teaching dataset for a decision-support prototype.
It is not medical advice, not validated for patient care, and absence of a record is not evidence
that a combination is safe.

**Non-commercial.** {NONCOMMERCIAL_NOTICE}

## Files

| File | Bytes | Contents |
|---|---:|---|
{rows}

`provenance.json` records, per source, the download URL, version, license, download date and sha256,
plus row counts, filters, match rates, and the sha256 of every file here (`processed_files`).
PharmGuard's server checks those hashes, and the hash of `provenance.json` itself, at a pinned
revision before it serves anything.

## How it was built

`scripts/fetch_data.py` (sha256-pinned downloads), then `scripts/ingest_data.py --full --profile public`
in the PharmGuard repository, built {prov.get('built_at')}.

- **Vocabulary (RxNorm):** canonical name = the RxNorm ingredient (IN) name, lowercased. Aliases come
  from RXNREL relationships (salt forms, single-ingredient brands, FDA substance names, synonyms),
  plus {len(voc.get('salt_groups', {}))} reviewed salt groups and {len(voc.get('reviewed_aliases', {}))} reviewed
  INN aliases. Combination products are kept separately and never resolved to one ingredient.
- **DDInter:** the 14 ATC-group CSVs from ddinter2.scbdd.com, files dated 2024-05-21 (the download page
  links 8; the other 6 are in the same directory with the same date). De-duplicated on the DDInter ID
  pair, names mapped to RxNorm by exact alias, then de-duplicated on canonical pair + level.
  {dd['matched_names']:,} of {dd['distinct_names']:,} names matched ({_pct(dd.get('name_match_rate'))});
  {dd['rows_kept']:,} of {dd['rows_in']:,} unique pairs kept ({_pct(dd.get('row_retention'))}).
  The bulk files have no mechanism or event text.
- **SIDER 4.1:** MedDRA preferred terms only, names mapped to RxNorm, de-duplicated.
  {se['matched_names']:,} of {se['distinct_names']:,} names matched ({_pct(se.get('name_match_rate'))});
  {se['rows_kept']:,} of {se['rows_in']:,} rows kept.
- **Brand names (Drugs@FDA):** {voc.get('fda_brands_added', 0):,} brand names, including discontinued
  products such as Coumadin, added from the FDA's Drugs@FDA data files ({SOURCES['drugsatfda'].version}, public
  domain). A brand is added only when every product under it maps to the same single ingredient and the
  name is new. {voc.get('fda_collisions', 0)} collisions and {voc.get('fda_ambiguous', 0)} ambiguous names were not
  applied.
- Unmatched names are listed in the `unmatched_*.csv` files, not dropped silently. They are mostly
  drugs that aren't in RxNorm Current Prescribable (withdrawn or non-US) and route-qualified entries.

**About the DDInter version.** The files come from the DDInter 2.0 site, but their counts (234,981
unique pairs over 1,971 drugs) match the DDInter 1.0 paper's figures (236,834 records over 1,972 drugs),
not the 2.0 paper's (302,516 records over 2,310 drugs). The papers don't explain the difference, so
this build is described as the DDInter bulk download and both papers are cited.

## Attribution and licenses

- **DDInter** (CC BY-NC-SA 4.0, per https://ddinter2.scbdd.com/terms/). Cite: {DDINTER2_CITATION}; and
  {DDINTER1_CITATION}.
- **SIDER 4.1** (CC BY-NC-SA 4.0). Cite: {SIDER_CITATION}.
- **Drugs@FDA** (public domain, U.S. Food and Drug Administration): brand names. The FDA does not
  endorse this product.
- **RxNorm.** {RXNORM_STATEMENT} Vocabulary: RxNorm Current Prescribable Content, release
  {rx.get('version')}; drug names may have changed since. NLM urges you to consult with a qualified
  physician for medical advice.

This dataset is a derivative of CC BY-NC-SA 4.0 data and is shared under the same license.
It contains no TWOSIDES data and no patient data.
"""


def app_url(space_repo: str) -> str:
    """Direct app URL of a Space: https://<owner>-<name>.hf.space (lowercase; '_' and '.' -> '-')."""
    return "https://" + space_repo.replace("/", "-").replace("_", "-").replace(".", "-").lower() + ".hf.space"


def space_readme(dataset_repo: str, space_repo: str) -> str:
    url = app_url(space_repo)
    return f"""---
title: PharmGuard
emoji: 💊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Drug-interaction reports with a citation for every finding
---

# PharmGuard

Drug-interaction reports from curated sources, with a citation for every finding. PharmGuard is a
LangGraph state machine with deterministic planning and bounded LLM retry. **This demo runs in
deterministic mode**: reports come from a fixed template over the retrieved records, and no LLM
is called.

> **Disclaimer.** {DISCLAIMER}

Try it: [warfarin, aspirin, simvastatin, clarithromycin]({url}/?drugs=warfarin,aspirin,simvastatin,clarithromycin)
· [lisinopril, spironolactone]({url}/?drugs=lisinopril,spironolactone) · [API docs]({url}/docs)
· [health]({url}/health)

## Data

The Space downloads the [public build](https://huggingface.co/datasets/{dataset_repo}) at a pinned
revision and checks every file's sha256 before serving. If the check fails, the server reports
why on `/health` and refuses to answer (HTTP 503).

| Source | License |
|---|---|
| {DDINTER_LABEL}; cite Tian et al. 2025 (DDInter 2.0) and Xiong et al. 2022 (DDInter 1.0) | CC BY-NC-SA 4.0 |
| SIDER 4.1 (Kuhn et al. 2016) | CC BY-NC-SA 4.0 |
| RxNorm Current Prescribable Content (U.S. National Library of Medicine) | public domain, NLM attribution |
| openFDA FAERS (only when a request asks for it) | CC0 |

| Drugs@FDA brand names (U.S. FDA) | public domain |

**Non-commercial use only.** The interaction and side-effect data are CC BY-NC-SA 4.0. The full
citations, NLM's RxNorm statement and the openFDA credit are on the page ("Data sources and
attribution") and in the dataset card.

## Limitations

- Each report starts with how every entry was read. Spelling matches are marked "check this", and
  names close to two drugs are not guessed.
- **Pairwise only.** Patterns involving three or more drugs at once (for example an NSAID + ACE
  inhibitor + diuretic, the "triple whammy") aren't flagged as a combination.
- **Supplements are thinly covered** (warfarin + ginkgo has no record). "No data" is not evidence of safety.
- **Severities are DDInter's grades** and can differ from other references. Pairs DDInter lists
  without a grade are shown separately; the data can't say whether they matter clinically.

## License

Code: MIT. The data has its own licenses: the interaction and side-effect data (DDInter,
SIDER) are CC BY-NC-SA 4.0 (non-commercial); RxNorm and Drugs@FDA are public domain, with the
attribution shown on the page.

## API

`POST /v1/check` with `{{"drugs": ["warfarin", "aspirin"]}}` (2 to 12 names). `GET /health` reports
the build and provenance hash. Requests are rate-limited per client.
"""


def dataset_uploads(build: Path, prov: dict) -> List[Upload]:
    files = [Upload(f"processed/{p.name}", local=p) for p in sorted(build.iterdir()) if p.is_file()]
    return files + [Upload("README.md", content=dataset_card(prov, build).encode())]


def space_uploads(dataset_repo: str, space_repo: str) -> List[Upload]:
    out = [Upload(f, local=ROOT / f) for f in SPACE_FILES]
    for d in SPACE_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc" and p.name != ".DS_Store":
                out.append(Upload(str(p.relative_to(ROOT)), local=p))
    return out + [Upload("README.md", content=space_readme(dataset_repo, space_repo).encode())]


def show(title: str, uploads: List[Upload]) -> None:
    print(f"\n{title}: {len(uploads)} files, {sum(u.size for u in uploads):,} bytes")
    for u in uploads:
        print(f"  {u.size:>12,}  {u.path_in_repo}" + ("   (generated)" if u.content is not None else ""))


def commit(api, repo_id: str, repo_type: str, uploads: List[Upload], message: str) -> str:
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete
    ops = [CommitOperationAdd(u.path_in_repo, str(u.local) if u.local else u.content) for u in uploads]
    wanted = {u.path_in_repo for u in uploads}
    existing = set(api.list_repo_files(repo_id, repo_type=repo_type))
    ops += [CommitOperationDelete(p) for p in sorted(existing - wanted) if p != ".gitattributes"]
    info = api.create_commit(repo_id, operations=ops, commit_message=message, repo_type=repo_type)
    return info.oid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--build", default=str(BUILD))
    ap.add_argument("--dataset", default=None, help="repo id (default <user>/pharmguard-public-build)")
    ap.add_argument("--space", default=None, help="repo id (default <user>/pharmguard)")
    ap.add_argument("--trusted-proxy-hops", type=int, default=1)
    ap.add_argument("--set-hops", type=int, default=None, help="only update PHARMGUARD_TRUSTED_PROXY_HOPS")
    args = ap.parse_args()

    from huggingface_hub import HfApi
    api = HfApi()
    user = api.whoami()["name"]
    dataset_repo = args.dataset or f"{user}/pharmguard-public-build"
    space_repo = args.space or f"{user}/pharmguard"

    if args.set_hops is not None:
        api.add_space_variable(space_repo, "PHARMGUARD_TRUSTED_PROXY_HOPS", str(args.set_hops))
        print(f"{space_repo}: PHARMGUARD_TRUSTED_PROXY_HOPS={args.set_hops} (the Space restarts)")
        return 0

    build = Path(args.build).resolve()
    prov = check_build(build)
    ds, sp = dataset_uploads(build, prov), space_uploads(dataset_repo, space_repo)
    guard(ds, "dataset")
    guard(sp, "Space")
    prov_sha = file_sha256(build / PROVENANCE_FILE)
    print(f"Account: {user}\nBuild: {build.relative_to(ROOT)}  ({provenance_line(build)})")
    print(f"provenance.json sha256: {prov_sha}")
    print("Checks passed: profile=public, not synthetic, redistributable, interactions only from DDInter, "
          "every file matches provenance, no forbidden paths.")
    show(f"Dataset https://huggingface.co/datasets/{dataset_repo} (public, license cc-by-nc-sa-4.0)", ds)
    show(f"Space https://huggingface.co/spaces/{space_repo} (public, Docker SDK, cpu-basic, app_port 7860)", sp)
    variables = {"PHARMGUARD_HF_DATASET": dataset_repo, "PHARMGUARD_HF_REVISION": "<sha of the new dataset commit>",
                 "PHARMGUARD_HF_PROVENANCE_SHA256": prov_sha,
                 "PHARMGUARD_TRUSTED_PROXY_HOPS": str(args.trusted_proxy_hops)}
    print("\nSpace variables:" + "".join(f"\n  {k}={v}" for k, v in variables.items()))
    print("Space secrets: none (the dataset is public).")
    if args.dry_run:
        print("\nDry run: nothing was created or uploaded.")
        return 0

    api.create_repo(dataset_repo, repo_type="dataset", private=False, exist_ok=True)
    revision = commit(api, dataset_repo, "dataset", ds, f"Public build {prov.get('built_at')} (provenance {prov_sha[:12]})")
    print(f"dataset commit: {revision}")
    api.create_repo(space_repo, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    variables["PHARMGUARD_HF_REVISION"] = revision
    for k, v in variables.items():
        api.add_space_variable(space_repo, k, v)
    code = commit(api, space_repo, "space", sp, f"PharmGuard API (dataset {dataset_repo}@{revision[:12]})")
    print(f"Space commit: {code}\nhttps://huggingface.co/spaces/{space_repo}\n{app_url(space_repo)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Refused as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)

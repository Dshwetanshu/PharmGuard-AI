# Datasets

PharmGuard runs on one of three data builds. Each build writes a `provenance.json`, and
every report ends with a data line generated from it, so a report can't claim a source
the build didn't load.

| Build | Sources | Where | Used by |
|---|---|---|---|
| **sample** | 85 hand-written synthetic interaction records (`data/sample/`) | `data/processed/` | tests, CI, `results/*.md` without a suffix |
| **public** | RxNorm Current Prescribable 2026-09-08 + Drugs@FDA brand names + the DDInter bulk download (ddinter2.scbdd.com, files dated 2024-05-21) + SIDER 4.1 (+ DrugBank vocabulary when available) | `data/profiles/public/processed/` | the demo; `results/*_public.*` |
| **research** | public + TWOSIDES | `data/profiles/research/processed/` | local evaluation only; aggregate numbers only are committed |

All raw and processed data is gitignored. Nothing below the sample is committed.

```bash
python scripts/fetch_data.py                    # RxNorm, DDInter, SIDER -> data/raw/ (sha256-pinned)
python scripts/fetch_data.py --with-twosides    # + TWOSIDES (research only, 388 MB)
python scripts/ingest_data.py --full --profile public
python scripts/ingest_data.py --full --profile research
PHARMGUARD_DATA_DIR=data/profiles/public streamlit run app/streamlit_app.py
```

`fetch_data.py` refuses a file whose sha256 doesn't match the pin in `src/data/sources.py`
and records URL, version, license, download date, size and sha256 per file in
`data/raw/MANIFEST.json`. Ingestion copies that into `provenance.json`, with row counts,
filters, match rates and unmatched names per source.

The numbers below come from the builds of 2026-09-23.

## Sources

### RxNorm Current Prescribable Content (vocabulary)

- **File:** `RxNorm_full_prescribe_09082026.zip` (release 2026-09-08). The Current
  Prescribable subset needs no UMLS license.
- **License:** public domain; NLM's attribution statement and a currency disclosure are required (below).
- **Role:** the canonical drug vocabulary. The canonical name of a drug is its RxNorm
  ingredient (TTY=IN) name, lowercased. Aliases, all following RXNREL relationships (no string rules):
  salt/precise forms (PIN `has_form` IN: warfarin sodium → warfarin), single-ingredient
  brands (BN `has_tradename` IN: Lipitor → atorvastatin), FDA substance names (MTHSPL SU:
  acetylsalicylic acid → aspirin) and RxNorm synonyms.
- **Reviewed exceptions** (`src/data/rxnorm.py`): 2 salt groups (lithium carbonate and lithium
  citrate → lithium, because the interaction sources name the moiety) and 21 reviewed aliases
  for INN or older names that the sources use (salbutamol → albuterol, valaciclovir →
  valacyclovir, leuprorelin → leuprolide, …).
- **Combination products** (3,247 names with the Drugs@FDA additions, e.g. Percocet, Bactrim)
  are not resolved to one ingredient. The report lists them as not analysed and names their
  ingredients.
- **Build:** 5,844 ingredients, 16,088 aliases (13,932 from RxNorm, 2,156 Drugs@FDA brands),
  6,772 UNII codes. 15 names that RxNorm attaches to different ingredients are dropped
  rather than guessed.
- **Spelling matches** (`src/data/normalizer.py`). A name with no exact alias is compared by
  plain Levenshtein similarity (0 to 100), and only against the 7,414 names of drugs that have
  records in the loaded interaction or side-effect tables. So an obscure substance such as
  coumarin or inulin can't capture a misspelling; before this, "Coumadin" matched coumarin.
  Exact and alias matching still use the whole vocabulary. The best drug is accepted only if
  it scores at least 85 and no other drug scores within 10 points of it (rivals below 75 don't
  count).
  - Two drugs both at 75 or more within 10 points: the input stays unresolved and the report
    lists both ("Celebyx": fosphenytoin (Cerebyx) 86, celecoxib (Celebrex) 80).
  - An input that is the first word of two or more drugs' names is ambiguous, and those drugs
    are listed: "insulin" lists specific insulins, while "insulin glargine" and "Lantus"
    resolve.
  - Every spelling match is shown in the report as "spelling match: check this".
  - Checked on 30 ordinary misspellings: 28 resolve. "atorvastin" (atorvastatin vs
    Avastin/bevacizumab) and "omeprazol" (omeprazole vs esomeprazole) come back ambiguous.

### Drugs@FDA (brand names, including discontinued products)

- **File:** `drugsatfda_20260924.zip` (FDA's Drugs@FDA data files, files dated 2026-09-23),
  sha256-pinned. FDA replaces the file weekly at the same URL, so a newer copy fails the pin
  until it is re-pinned deliberately.
- **License:** public domain (U.S. FDA).
- **Why:** RxNorm Current Prescribable leaves out discontinued products, so well-known brands
  such as Coumadin (warfarin) and Biaxin (clarithromycin) weren't recognized.
- **Rule** (`src/data/rxnorm.py`, `merge_fda_brands`): each product's active ingredients are
  mapped to the vocabulary by exact alias. A brand name is added only if every product under
  that name maps to the same single ingredient and the name isn't already in the vocabulary.
  Multi-ingredient brands go to the combination-products table.
- **Result** (8,376 names): 2,156 brands added, 1,454 combination products added, 3,329
  already known for the same drug. Not applied: 12 collisions (the name already means another
  drug), 57 ambiguous names (products map to different ingredients) and 1,368 names with an
  ingredient not in the vocabulary. The collisions and ambiguous names are listed for review in
  `data/profiles/<profile>/review/fda_brand_review.csv`, which is not published.
- **For reading user input only.** Source tables (DDInter, SIDER, TWOSIDES) are mapped with a
  separate alias table that leaves out Drugs@FDA brand aliases, except those reviewed in
  `REVIEWED_SOURCE_BRAND_ALIASES` (`src/data/rxnorm.py`). So a new Drugs@FDA release can't
  silently change what the data says; a test checks this. The reviewed list (2026-09-25) has six
  entries:
  - DDInter "esterified estrogens" → estrogens, esterified (usp);
  - SIDER "8-mop" → methoxsalen, "implanon" → etonogestrel, "ogen" → estropipate and
    "zoledronic" → zoledronic acid;
  - SIDER "optison" → perflutren. SIDER's Optison compound is PubChem CID 6432,
    perfluoropropane (= perflutren). Drugs@FDA lists the Optison product's ingredient as
    albumin human, which would have attached a contrast agent's side effects to albumin.

  SIDER "penicillin" stays unmatched: it covers two compounds, CID 2349 (benzylpenicillin
  without stereochemistry) and CID 4730 (phenoxymethylpenicillin, penicillin V), so it can't
  map to penicillin G alone. For user input, "Optison" still reads as Drugs@FDA lists it.

### DDInter bulk download (curated interactions)

The files come from the DDInter 2.0 site (ddinter2.scbdd.com), but their counts match the
DDInter 1.0 paper, not the 2.0 paper (see "Record counts vs the papers" below). So PharmGuard
calls this data "the DDInter bulk download (files dated 2024-05-21)", not "DDInter 2.0", and
cites both papers: Tian et al., NAR 2025 (DDInter 2.0; PMID 39180399) and Xiong et al., NAR 2022
(DDInter 1.0; PMID 34634800).

- **Files:** 14 CSVs `ddinter_downloads_code_{A,B,C,D,G,H,J,L,M,N,P,R,S,V}.csv`, one per ATC
  top-level group, dated 2024-05-21. The download page links only 8 of them (A B D H L P R V).
  The other 6 (C, G, J, M, N, S: cardiovascular, genito-urinary, anti-infectives,
  musculo-skeletal, nervous system, sensory organs) are in the same download directory with
  the same date. An earlier build used only the 8 linked files and missed, for example,
  lisinopril + spironolactone, warfarin + aspirin and lithium + thiazides.
- **License:** CC BY-NC-SA 4.0, as stated in the "Data licensing" section of
  https://ddinter2.scbdd.com/terms/ (checked 2026-09-24). The NAR article itself is CC BY-NC.
- **Links:** reports don't deep-link DDInter citations. The site's interaction pages use an
  internal ID that isn't in the bulk files. Its drug pages use an `internalID` whose relation
  to the files' `DDInterID` isn't documented, and checking would mean fetching those pages.
- **Columns:** `DDInterID_A, Drug_A, DDInterID_B, Drug_B, Level`. There is **no mechanism or
  event text** in the bulk files: that is web-only, and PharmGuard doesn't scrape it. Reports
  therefore show the curated severity and source, and no mechanism.
- **Processing:** de-duplicated on the DDInter ID pair across files (234,981 pairs), names
  mapped to RxNorm (exact alias), then de-duplicated on canonical pair + level (436 merged).
  Level outside Major/Moderate/Minor → "not graded".
- **Match:** 1,455 of 1,971 names (73.8%); 169,673 of 234,981 rows kept (72.2%). The unmatched
  names (`unmatched_ddinter.csv`) are mostly drugs withdrawn in or never marketed in the US
  (telithromycin, mesoridazine, sibutramine, rofecoxib, dextropropoxyphene, …), which the
  Current Prescribable subset leaves out, and route-qualified entries such as "doxepin (topical)".
- **Severity:** Major 27,677 · Moderate 95,333 · Minor 6,097 · not graded 40,566. Reports list
  the not-graded pairs under "Listed by DDInter without a severity grade". They are DDInter
  listings without a grade, and the loaded data can't say whether they matter clinically.
- **Record counts vs the papers** (checked 2026-09-24 against the DDInter 2.0 full text, PMC11701621). The
  paper reports 302,516 DDI records over 2,310 drugs (2,122 distinct) for DDInter 2.0. It
  doesn't define a "record" relative to a drug pair and doesn't describe the download files.
  Its own risk-level table sums to 303,658 (Minor 12,522, Moderate 195,776, Major 52,943,
  unknown 42,417). The 14 files have 507,655 rows: 272,674 exact duplicates (the same pair
  listed under more than one ATC group) and 234,981 unique DDInter-ID pairs, with no pair
  given two levels. They cover 1,971 drugs, with Major 39,082, Moderate 143,748, Minor 9,736
  and Unknown 42,415. These file counts are close to the paper's figures for **DDInter 1.0**
  (236,834 records over 1,972 drugs: Major 39,480, Moderate 145,132, Minor 9,805, unknown
  42,417), not its 2.0 figures. Why the files differ from the 2.0 counts is **unexplained**:
  the paper doesn't say, and we haven't verified it with the authors.

### SIDER 4.1 (side effects)

- **Files:** `meddra_all_se.tsv.gz`, `drug_names.tsv`.
- **License:** CC BY-NC-SA 4.0.
- **Processing:** MedDRA preferred terms (PT) only, names mapped to RxNorm, de-duplicated on
  drug + side effect.
- **Match:** 950 of 1,344 names (70.7%); 110,186 of 145,321 PT rows kept (75.8%). Unmatched
  names include truncated or generic SIDER names ("insulin", "mycophenolate", "retinoic") and
  development codes. They are listed, not aliased: an alias would need review.

### DrugBank vocabulary (paused)

The CC0 vocabulary CSV would add synonyms joined by UNII. DrugBank has paused all downloads
(checked 2026-09-23). The loader is ready: `ingest_data.py --full --drugbank-csv <file>` merges a
manually obtained copy. Neither current build includes it.

### TWOSIDES (research build only)

- **File:** `TWOSIDES.csv.xz` (S3 object dated 2024-03-30), 42,920,391 rows.
- **License:** none stated by the publisher. Research use only, not redistributed: TWOSIDES
  and anything built from it stay out of commits, the Hugging Face bundle and the demo.
- **Filters:** PRR ≥ 2 and at least 5 co-reports; 15 administrative MedDRA terms excluded
  ("drug ineffective", "off label use", …); the top 5 events per pair by PRR.
- **Match:** 1,309 of 1,682 names (77.8%); 465,048 rows kept (1.1%) over 115,995 pairs.
  Dropped: 28,036,229 with fewer than 5 co-reports, 9,145,035 below the PRR threshold,
  4,929,834 beyond the top 5 per pair, 293,278 with an unmatched drug, 50,390 administrative terms.
- **In reports:** TWOSIDES rows are statistical reporting signals, not curated interactions.
  They appear in their own section ("Statistical reporting signals (not graded for clinical
  severity)") with PRR and co-report count and never with a severity word. At most 3 per pair
  are shown; the rest are counted ("+N more not shown"). A PRR-derived tier is kept on the
  record for internal use and never shown.
- Ingest: 127 s, 904 MB peak memory (chunked, with per-chunk pruning).

### openFDA FAERS (runtime, optional)

`PHARMGUARD_FAERS_ENABLED=true` queries `api.fda.gov/drug/event.json` for pairs with no
curated record. Counts are shown in a separate "unvalidated" section and never as curated
evidence. openFDA data is CC0.

## Build totals

| | sample | public | research |
|---|---:|---:|---:|
| Interaction records | 85 | 169,673 (DDInter) | 634,721 (DDInter 169,673 + TWOSIDES 465,048) |
| Side-effect records | sample CSV | 110,186 | 110,186 |
| Join-integrity issues | — | 0 | 0 |

## Known gaps

- **No mechanism text.** DDInter's bulk files have none, and TWOSIDES and SIDER aren't
  mechanism sources. Any mechanism in an LLM report fails the checker.
- **Coverage.** Drugs missing from RxNorm Current Prescribable (withdrawn or non-US drugs) are
  excluded, and the excluded names are listed per source.
- **Ambiguous inputs** such as "insulin" stay unresolved; the report lists the candidates.
- **Pairwise only.** PharmGuard checks each pair of drugs on its own. A pattern that involves
  three or more drugs at once, such as an NSAID + ACE inhibitor + diuretic (the "triple
  whammy" for kidney injury), is not flagged as a combination; only its pairs are listed.
- **Supplements and herbals are thinly covered.** For example, warfarin + ginkgo has no record
  in the loaded data, so the report lists it as "no data", which is not evidence of safety.
- **Severity grades are DDInter's.** Other references can grade the same pair differently;
  PharmGuard reports the loaded source's grade and doesn't reconcile sources.
- **Hand labels.** END-02's labelled pair (insulin + metoprolol) can't be matched on real data,
  because "insulin" isn't a canonical name there. It is counted as a source gap.
- **No-data path.** On the public build, every pair in the original 48 evaluation cases has a
  DDInter record (98 of the 231 pairs are not graded), so those cases never exercise the
  no-data declaration. The checker's stress sets (random drug lists) do.
- **Lithium + thiazides** were a gap only in the 8-file DDInter build. With all 14 files,
  DDInter grades lithium + hydrochlorothiazide, chlorthalidone, indapamide, chlorothiazide
  and metolazone as Major.
- **Not used by any build:** WebMD and UCI reviews, ADE-Corpus-V2, the Kaggle medical
  datasets and Medicare Part D. Their loaders remain, but no build ingests them.

## Evaluation on the real builds

Each result file names its build and the sha256 of its `provenance.json`. The sample results
(no suffix) are the ones CI checks for staleness.

- `results/eval_public.json`: `PHARMGUARD_DATA_DIR=data/profiles/public python scripts/run_eval.py --skip-llm`
- `results/checker_validation_public.*`: `python scripts/validate_checker.py --profile public`
- `results/trajectory_public.*`: `python scripts/eval_trajectory.py --fault-suite --seeded-bugs --profile public`
- `results/*_research*`: the same scripts on the research build. Aggregate numbers only.

Hand-label misses are split into **source gaps** (the pair is in no loaded table) and
**pipeline misses** (it's in a table but wasn't retrieved).

## Attribution

The app shows these notices in the sidebar ("Data sources and attribution"). They are
generated from the build's provenance by `src/data/attribution.py`; a test keeps this block
in sync.

<!-- attribution:start (generated by src/data/attribution.py) -->

Public build (and the Streamlit app on it):

- **DDInter.** Interaction severities from the DDInter bulk download (ddinter2.scbdd.com, files dated 2024-05-21). Cite: Tian Y, Yi J, Wang N, Wu C, Peng J, Liu S, Yang G, Cao D. DDInter 2.0: an enhanced drug interaction resource with expanded data coverage, new interaction types, and improved user interface. Nucleic Acids Research. 2025;53(D1):D1356-D1362. doi:10.1093/nar/gkae726; and Xiong G, Yang Z, Yi J, Wang N, Wang L, Zhu H, Wu C, Lu A, Chen X, Liu S, Hou T, Cao D. DDInter: an online drug-drug interaction database towards improving clinical decision-making and patient safety. Nucleic Acids Research. 2022;50(D1):D1200-D1207. doi:10.1093/nar/gkab880. Licensed CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/). PharmGuard mapped drug names to RxNorm and removed duplicates.
- **SIDER 4.1.** Kuhn M, Letunic I, Jensen LJ, Bork P. The SIDER database of drugs and side effects. Nucleic Acids Research. 2016;44(D1):D1075-D1079. doi:10.1093/nar/gkv1075. Licensed CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/).
- **RxNorm.** This product uses publicly available data courtesy of the U.S. National Library of Medicine (NLM), National Institutes of Health, Department of Health and Human Services; NLM is not responsible for the product and does not endorse or recommend this or any other product. Vocabulary: RxNorm Current Prescribable Content, release 2026-09-08; drug names may have changed since that release. NLM urges you to consult with a qualified physician for medical advice.
- **Drugs@FDA.** Brand names, including discontinued products, from the Drugs@FDA data files (datdaf_20260924, files dated 2026-09-23), U.S. Food and Drug Administration; public domain. The FDA does not endorse this product.
- **openFDA.** Data provided by the U.S. Food and Drug Administration (https://open.fda.gov). Used only when the optional FAERS lookup is enabled; FAERS reports are unvalidated, and the FDA does not endorse this product.
- **Non-commercial use.** This build contains data licensed CC BY-NC-SA 4.0 (DDInter, SIDER 4.1). Non-commercial use only; anything derived from that data must be shared under the same license, with the attributions above.

The research build adds:

- **TWOSIDES.** TWOSIDES: research use only, not for redistribution (no license stated by the publisher).

<!-- attribution:end -->

## Privacy

PharmGuard stores no medication lists: input is processed in memory. Tracing is off by
default; when on, inputs and outputs are redacted unless `PHARMGUARD_TRACE_REDACT=false`
(docs/OBSERVABILITY.md).

# Pharmacist review protocol

A small, structured review of PharmGuard's reports by one licensed pharmacist. It is a usability and face-validity
check on 10 cases, not a clinical validation study: one reviewer and 10 cases can find problems, but can't estimate
error rates with any precision.

## What the reviewer gets

- `data/validation/pharmacist/cases.md`: 10 cases, each with the drug list exactly as typed and PharmGuard's full
  report for it (public build, deterministic mode, as on https://pharmguard.web.app).
- `data/validation/pharmacist/rubric.csv`: one row per case to fill in.
- This document.

Regenerate both files with `python scripts/export_pharmacist_cases.py`.

The cases were chosen to cover the report's parts:

| Case | Exercises |
|---|---|
| PR-01, PR-02, PR-03 | several Major findings (anticoagulant / statin / macrolide; hyperkalemia; serotonergic) |
| PR-04 | a 7-drug geriatric list with mixed grades and ungraded listings |
| PR-05 | mostly pairs DDInter lists without a severity grade |
| PR-06 | a discontinued brand (Coumadin), a brand (Diflucan) and the same drug entered twice |
| PR-07 | a misspelling between two look-alike brands (Celebyx), which must not be guessed |
| PR-08 | an ambiguous name (insulin) and a combination product (Percocet) |
| PR-09 | pairs with no curated interaction data |
| PR-10 | misspellings (metfromin, lisonopril) and a brand (Lasix) |

## What PharmGuard claims, and what it doesn't

Tell the reviewer before they start:
- Severity grades are DDInter's, copied as they are. PharmGuard doesn't grade anything itself.
- "Listed by DDInter without a severity grade" means DDInter lists the pair but gives it no grade.
- "No curated interaction data" means the loaded sources have no record of the pair. It is not a statement that
  the combination is safe.
- The bulk DDInter files have no mechanism text, so the reports don't give mechanisms or management advice.
- Checks are pairwise only; three-drug patterns (for example NSAID + ACE inhibitor + diuretic) aren't flagged as
  a combination.

## Rubric (one row per case)

| Column | Values | Meaning |
|---|---|---|
| `reviewer` | initials or a code | no names needed |
| `accuracy` | `accurate` / `partly accurate` / `inaccurate` | Is everything the report states correct, and are the drug names read correctly? *Partly accurate*: at least one statement is wrong or misleading, but the report is mostly right. *Inaccurate*: a clinically important error (a wrong grade on a serious interaction, a wrong drug, a missed Major interaction you would expect any reference to list). |
| `useful` | `y` / `n` | Would this report help a pharmacist check this list? |
| `would_recommend` | `y` / `n` | Would you recommend it as a first check, with its stated limits? |
| `missed_or_wrong` | free text | Interactions you expected but didn't see, grades you disagree with, misread names. |
| `comments` | free text | Anything else, including wording that could mislead a patient. |

Leave a cell blank rather than guess. Score each case against your own knowledge and whatever reference you
normally use; please name that reference in `comments` once.

## Procedure

1. Read this protocol. Time needed: about 45 to 60 minutes.
2. For each case, read the input and the report, then fill in the row. Don't look up PharmGuard's code, other
   cases' scores or any LLM output first.
3. Return `rubric.csv`. Then run `python scripts/score_pharmacist_review.py`, which writes
   `results/pharmacist_review.{json,md}`.

## Optional: blinded A/B of LLM vs template reports

Only once an LLM key is available: `python scripts/export_pharmacist_cases.py --ab --provider <provider>` writes
`cases_ab.md` with two reports per case, A and B, in a seeded random order (one is the template, one the LLM
report after the checker), and `rubric_ab.csv` with `accuracy_A/B`, `useful_A/B` and `preferred` (A, B or
none). The key goes to `data/cache/pharmacist_ab_key.json` and is not committed, so the reviewer can't see it.
Score with `python scripts/score_pharmacist_review.py --ab`. The reviewer should do the A/B only after the main
rubric, on a different day if possible.

## Reporting

`results/pharmacist_review.md` reports counts only: accuracy categories, the share useful and would-recommend,
and, for the A/B, per-arm accuracy and preferences. With one reviewer there is no inter-rater agreement, and the
results say so. Free-text comments stay in the rubric file.

## Consent and privacy

The cases are made-up medication lists, not patient data. Ask the reviewer whether they are happy to be
acknowledged by name, by role only ("a licensed pharmacist"), or not at all, and record that outside the repo.

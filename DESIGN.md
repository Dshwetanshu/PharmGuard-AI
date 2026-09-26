---
name: PharmGuard
version: 2
description: A well-typeset pharmacist's printout, not a SaaS dashboard. The answer comes first, the hierarchy is carried by type, hairline rules replace boxes, and colour always means something.
colors:
  paper: "#FFFFFF"
  ink: "#1A1D21"
  ink-2: "#4F5761"
  rule: "#D3D8DD"
  control: "#7A838D"
  accent: "#0B5470"
  accent-hover: "#083F55"
  severity: "#A61B1B"
  no-data: "#ECEEF0"
colors-dark:
  paper: "#121517"
  ink: "#E7E9EC"
  ink-2: "#A7AFB8"
  rule: "#2F363C"
  control: "#7F8994"
  accent: "#7CC4DE"
  severity-text: "#FF9185"
  severity-fill: "#B42318"
  no-data: "#22282D"
typography:
  serif: "Newsreader (subset, opsz 24, weights 400-500)"
  sans: "PharmGuard Sans (subset of IBM Plex Sans, weights 400-600)"
  mono: "PharmGuard Mono (subset of IBM Plex Mono)"
  sizes:
    fs-1: { size: 34px, line: 1.15, use: "the answer line" }
    fs-2: { size: 21px, line: 1.3, use: "headings" }
    fs-3: { size: 16px, line: 1.55, use: "body, controls" }
    fs-4: { size: 13.5px, line: 1.45, use: "notes, citations, grid words" }
  figures: tabular
radii: { controls: 3px, everything-else: 0 }
layout: { max-width: 1200px, form-column: 300px, breakpoint: 760px }
---

# PharmGuard design system

## Concept

PharmGuard's page is a pharmacist's printout: something you could hand across a counter.
- It opens with the answer, in one large line ("3 major interactions").
- Everything after it is ordered by what a reader needs next.
- Hierarchy comes from type, not boxes. There are no cards, tinted panels, pills, tiles, shadows or decorative icons.
- The same page prints as one clean sheet.

## Colour

Colour always means something. There are five roles and nothing else:
- **Ink on paper** for text. Secondary text (`ink-2`) is a lighter ink, never below AA.
- **Petrol accent** for actions and links only: the primary button, links, the print button, disclosure labels and the focus ring.
- **One severity scale**, a single red, with its strength shown by treatment:
  - Major: solid red cell, white word;
  - Moderate: red outline, red word;
  - Minor: ink word, one red step marked.

  Red wording is reserved for Moderate and Major.
- **Neutral** for the absence of a grade:
  - Not graded: a dashed neutral outline;
  - No curated data: a flat neutral grey.

  There is no green anywhere. Nothing may suggest a pair is "safe".
- The error state reuses the severity red, as a rule beside the message.

Every text/background pair passes WCAG AA in the light theme, the dark theme and print. A test reads the tokens from the stylesheet and checks them: `tests/test_api.py::test_colour_tokens_pass_aa_in_light_dark_and_print`.

## Typography

- **Headings: Newsreader**, a text serif designed for on-screen reading. A printout is a publication, which is the one case where the Taste Skill allows a serif, and the brief named one.
- **Body: PharmGuard Sans**, a subset of IBM Plex Sans. It has engineered, clinical-feeling letterforms and tabular figures by default.
- **Citations: PharmGuard Mono**, a subset of IBM Plex Mono, so a record ID reads like a record ID.
- **Four sizes only**, used as tokens (`--fs-1` to `--fs-4`). A test fails on any other `font-size`.
- **Weights:** serif 400 and 500; sans 400 and 600.
- **Counts use tabular figures.** Text is sentence case, with no all-caps labels and no eyebrows.

### Fonts: licenses and subsetting

All three fonts are SIL Open Font License 1.1, self-hosted as woff2 and subset by `scripts/subset_fonts.py`.
- **Character set:** Basic Latin and Latin-1 (drug names are ASCII), plus every character in the page, the report code and the attribution notices. It's saved to `api/static/fonts/charset.txt`. A test fails if the page text changes without a re-subset.
- **Renaming:** Newsreader's OFL has no Reserved Font Name, so it keeps its name. IBM Plex's OFL reserves "Plex", so the subsets are renamed "PharmGuard Sans" and "PharmGuard Mono".
- **Kept as published:** the copyright, trademark and license name records.
- **License files:** `fonts/OFL-Newsreader.txt` and `fonts/OFL-IBM-Plex.txt`.
- **Size:** 86 KB for all three together.

## Layout

- **Desktop:**
  - a 56px header with the logo mark, then the page title, the lede and the plain-language notice between two rules;
  - a 300px form column, a hairline, then the report.
- **Mobile (below 760px):** one column in this order: the form, then the report.
- **Report order:**
  1. The answer: the headline, "N pairs checked across N medicines", and the non-zero extras.
     The headline leads with what was found and never reassures. If nothing is graded, it names the ungraded listings, signals or no-data pairs ("No curated data for these 3 pairs"). "Absence of a record doesn't mean the combination is safe." goes directly under it.
  2. Alerts that change coverage: duplicates, unrecognized inputs, spelling matches to check.
  3. The pair grid.
  4. Interactions.
  5. The ungraded listings, collapsed.
  6. Statistical signals and FAERS, when present.
  7. No curated data.
  8. How your entries were read.
  9. The disclaimer and data line.
  10. Technical details.
- **Zero counts are never shown.**

## Components

- **Answer:**
  - the headline in the serif at `fs-1`;
  - the sub-line at `fs-3`;
  - "Checked against source records." when validation passed;
  - a "Print or save as PDF" button.
- **Alerts:** a 3px ink rule on the left and a bold label. There is no tinted box.
- **Pair grid (the signature element):** a lower-triangle `<table>` with the drugs, in the order entered, on both axes.
  - It has real `<th scope="col">` and `<th scope="row">` headers.
  - Each checked pair is one cell showing its status in words, with the three-step marker as a second cue.
  - A cell with a finding links to it. If the finding is in the collapsed section, the section opens first.
  - Narrow screens number both axes and show a key. Grids wider than three columns fall back to a list of pairs.
  - The grid is part of `report_structure` (`grid.drugs`, `grid.cells`). The parity test rebuilds every cell from the markdown alone and compares.
- **Interactions:** a hairline-divided list. Each row has the severity marker and word, the pair, and the citation in mono. "Severity grades from DDInter" is said once, in the section header.
- **Severity marker:** three steps (3 Major, 2 Moderate, 1 Minor, dashed for Not graded). It is decorative (`aria-hidden`); the word carries the meaning.
- **Entries:** one column, exceptions first, in the order entered.
  - exact matches are plain;
  - only exceptions are flagged: brand or alias ("Coumadin → warfarin (brand name, Drugs@FDA)"), spelling matches to check, not recognized with the reason, ambiguous, combination.
- **Data sources:** one short labelled line per source, from `Notice.short` in `src/data/attribution.py`.
  - The RxNorm line keeps NLM's required statement in full.
  - The full citations and licenses sit in a collapsed "Licenses and citations" section.
- **Buttons:**
  - primary: petrol fill;
  - quiet: petrol outline.

  Both are 3px radius, with labels on one line.
- **Focus:** a 2px petrol outline on every interactive element.
- **Loading:** flat blocks in the shape of the answer, the grid and the rows. The pulse stops under `prefers-reduced-motion`.
- **Error:** a red rule with "This list wasn't checked.", the server's message and the request ID.

## Print

"Print or save as PDF" gives one A4 sheet.
- **Kept:** a title line, the plain-language notice, the answer with the date and request ID, the alerts, the grid (colours forced), the interactions, the ungraded listings in full, the no-data pairs, entries (run inline), the disclaimer, the data line and the short source lines.
- **Collapsed sections:** a closed `<details>` prints closed, so a section that holds report content has an open print-only copy. A test checks that the print view holds every finding, listing and no-data pair.
- **Left out:** the header, the form, the examples, technical details and the full citations.

## Dark mode

Dark mode follows `prefers-color-scheme`. It swaps the same roles, and print always uses the light tokens.

## Do's and Don'ts

**Do**
- Escape every server or user string before it meets markup.
- Keep every safety item visible:
  - the notice;
  - the disclaimer;
  - every entry;
  - the duplicate notice;
  - unresolved reasons;
  - citations;
  - the data line;
  - the attribution.
- Put the answer first.
- Use the four sizes.

**Don't**
- Don't use cards, tinted rows, pills, stat tiles or decorative icons.
- Don't show zero counts.
- Don't use green.
- Don't use em or en dashes in page text.
- Don't make third-party requests, or use inline script or style.

## Known gaps

- Markdown (LLM) reports have no structure, so they show no grid. They render as ruled, styled markdown.
- The Taste Skill's Lighthouse and Core Web Vitals checks were not run.

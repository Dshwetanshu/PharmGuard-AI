---
name: PharmGuard
version: 1
description: A calm, airy clinical tool. Near-white canvas, white cards on hairline borders, light large headings over small precise UI text, one petrol accent. Severity is read from words and icons first, colour second.
colors:
  canvas: "#F7F8F8"
  surface: "#FFFFFF"
  surface-muted: "#F2F4F5"
  ink: "#16181D"
  ink-soft: "#2B3038"
  muted: "#5B616E"
  hairline: "rgba(11, 40, 56, 0.10)"
  hairline-strong: "#8A919E"
  accent: "#0B5470"
  accent-hover: "#083F55"
  accent-tint: "#E6F0F3"
  focus: "#0B5470"
  major: "#B42318"
  major-tint: "#FEF3F2"
  moderate: "#93370D"
  moderate-tint: "#FFFAEB"
  moderate-edge: "#FEDF89"
  minor: "#344054"
  minor-tint: "#F2F4F7"
  ungraded: "#475467"
  nodata: "#475467"
  callout-ink: "#7A2E0E"
  callout-tint: "#FFF7ED"
  callout-edge: "#FED7AA"
typography:
  family: "InterVariable, Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
  mono: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
  display: { size: 30px, line: 36px, weight: 300, tracking: -0.01em }
  title: { size: 22px, line: 28px, weight: 400 }
  section: { size: 15px, line: 22px, weight: 600 }
  body: { size: 15px, line: 23px, weight: 400 }
  ui: { size: 14px, line: 20px, weight: 500 }
  small: { size: 13px, line: 19px, weight: 400 }
  pill: { size: 12px, line: 16px, weight: 500 }
  count: { size: 28px, line: 32px, weight: 300 }
spacing: [4, 8, 12, 16, 20, 24, 32, 48, 64]
radii: { control: 6px, pill: 6px, chip: 999px, card: 12px, panel: 16px }
shadows:
  card: "0 1px 2px rgba(11, 40, 56, 0.05)"
  raised: "0 6px 16px -10px rgba(11, 40, 56, 0.28)"
  button: "0 1px 2px rgba(11, 40, 56, 0.12)"
layout:
  max-width: 1280px
  gutter: 32px
  gutter-mobile: 16px
  aside: 380px
  breakpoint: 900px
---

# PharmGuard design system

## Overview

PharmGuard is a working tool: you type medications and read a report. The page should feel
calm, quiet and exact. It takes its qualities from a class of modern clinical products: an
airy near-white canvas, white cards that barely lift off the page, thin tinted hairlines,
light-weight large headings over small precise UI text, and one restrained accent. It borrows
**qualities, not a brand**. PharmGuard has its own name, logo mark, accent colour and wording,
and nothing on the page should suggest it belongs to any other company or product.

There is no marketing on the page: no hero, no photography, no testimonials, no pricing. A short
header is followed directly by the checker.

## Colors

- **Canvas** `#F7F8F8` is the page background. **Surface** `#FFFFFF` is for cards, the input
  panel and the report. **Surface-muted** `#F2F4F5` is for inset areas such as technical
  details and zero tiles.
- **Ink** `#16181D` is for text. **Muted** `#5B616E` is for secondary text; it is 5.8:1 on
  canvas and 6.2:1 on white. There is no lighter text colour: every text colour passes WCAG AA
  (4.5:1) on every background it's used on.
- **Accent: PharmGuard petrol** `#0B5470` (8.3:1 on white). It is used for the primary button,
  links, focus rings, the logo lens and the "Checked against source records" mark. It is used
  sparingly: one primary action per view. **Accent-tint** `#E6F0F3` is for source pills and
  selected states.
- **Severity** colours only reinforce a word and an icon. They never carry meaning alone.
  | Severity | Treatment | Colours |
  |---|---|---|
  | Major | solid badge, white text, red edge on the row | `#B42318`; tint `#FEF3F2` |
  | Moderate | amber-tinted badge, brown text | `#93370D` on `#FFFAEB` |
  | Minor | slate badge | `#344054` on `#F2F4F7` |
  | Not graded | outline badge | `#475467` |
- **No curated data** is neutral grey with a dashed icon. **It is never green**, and neither is
  anything that might read as "safe". The palette contains no green.
- **Callout** (duplicate entries, the plain-language notice) uses a warm tint: `#7A2E0E` on
  `#FFF7ED` with a `#FED7AA` edge.
- **Borders**: hairline `rgba(11,40,56,.10)`, tinted with the accent's hue rather than plain
  grey. Form controls use `#8A919E` (3.2:1), which meets the non-text contrast minimum.

## Typography

- **Inter** (variable, weights 100–900), self-hosted from `/static/fonts/InterVariable.woff2`
  under the SIL Open Font License 1.1 (`/static/fonts/Inter-LICENSE.txt`). The fallback is the
  system stack. No font comes from a third party.
- Large text is **light (300)**: the page title (30px) and the summary counts (28px). Everything
  else is small and precise: body 15px, UI 14px at 500, meta 13px, pills 12px at 500.
- Section headings are 15px at 600 in sentence case. There are no all-caps labels, except that
  the pill source name may use small caps via `letter-spacing` only.
- Drug names are the most important text in a finding: 15px at 600, ink colour.
- Record IDs use tabular numerals (`font-variant-numeric: tabular-nums`).

## Layout

- Container: max 1280px, 32px gutters (16px on mobile).
- **Desktop (≥ 900px)**: two columns.
  - Left (380px, sticky): the checker panel with "Your medications", helper text, the FAERS
    option and the button. Once a report exists, "How your entries were read" sits underneath.
  - Right (fluid): the empty state, loading, error or report.
- **Mobile (< 900px)**: a single column in this order: checker, entries, report, footer. The
  layout works at 375px, with nothing wider than the viewport.
- Rhythm: 24px between cards, 16px inside small cards, 20–24px inside the report card.

## Elevation

Two levels only.
- **Card**: `0 1px 2px rgba(11,40,56,.05)` plus a hairline border. Used for most things.
- **Raised**: `0 6px 16px -10px rgba(11,40,56,.28)`. Used for the checker panel and the report
  card.

There are no heavy or grey-black shadows and no glows.

## Shapes

| Element | Radius |
|---|---|
| Controls (buttons, textarea) | 6px |
| Pills | 6px |
| Status chips | fully round |
| Cards | 12px |
| Panels (checker, report) | 16px |

Larger containers get larger radii.

## Components

- **Header**: the logo mark, "PharmGuard" and a short descriptor on the left; "Data sources"
  and "API" text links on the right. 64px tall with a hairline bottom border.
- **Logo**: an original mark of two overlapping outline circles with the shared lens filled in
  petrol (two medicines, and the place they meet). It is also the favicon.
- **Plain-language notice**: a callout-tinted strip above the checker. Its wording is fixed.
- **Buttons**: 40px tall, 6px radius, 14px at 500.
  - Primary: petrol fill with white text.
  - Secondary: white with a hairline-strong border.
  - Disabled: 60% opacity with a `not-allowed` cursor.
  - Examples are secondary buttons that link to `?drugs=`.
- **Textarea**: white, 1px `#8A919E` border, 6px radius, 12px padding, 15px text. It is
  labelled "Your medications" and has helper text via `aria-describedby`. When invalid, it gets
  a Major-red border and `aria-invalid`.
- **Focus**: a 2px petrol outline with a 2px offset on every interactive element. It is never
  removed.
- **Severity badge**: a 16px icon plus the word (Major, Moderate, Minor, Not graded), 12px at 600,
  6px radius. The icon shapes differ as well as the colours: octagon, triangle, circle-i,
  question.
- **Summary tiles**: a row of six small cards (Major, Moderate, Minor, Not graded, No curated
  data, Not recognized). Each has a light 28px count, a label and an icon. Tiles with a zero
  count are muted, and the Major tile is emphasised when its count is above zero. The summary
  sentence from the report sits under the tiles verbatim.
- **Finding row**: badge, then the drug pair (A + B) with condition and "Source mechanism" on a
  muted line below, then the source pill on the right. Major rows get a 3px red left edge and the
  red tint. On mobile the pill wraps under the text.
- **Source pill**: a document icon, the source name and the record ID, on the accent tint. It is
  12px, and the record ID is tabular.
- **Callout (duplicate notice)**: a warm tint with an icon and the notice text as given.
- **Entries list**: compact rows. Each has a status icon (check, magnifier "check this", cross,
  split capsule, question), the text as typed, an arrow, what it was read as, and the method in
  muted text. The status word is always shown.
- **Collapsed section**: `<details>` with the full heading, a count chip and a chevron, closed
  by default. Used for "Listed by DDInter without a severity grade".
- **Technical details**: a `<details>` disclosure at the foot of the report card. It holds a
  definition list of report source, automatic check, claims checked, time and request ID.
- **Checked mark**: a shield-check icon with "Checked against source records", shown only when
  validation passed.
- **Loading**: skeleton bars in the report area, the button text "Checking…", and an `aria-live`
  status message. The shimmer is disabled under `prefers-reduced-motion`.
- **Error**: a callout in the report area with the title "This list wasn't checked", the
  server's message and the request ID. `role="alert"`.
- **Footer**: the disclaimer and data line (shown once: here before a check, inside the report
  after one), the attribution notices (always visible), and links.

## Do's and Don'ts

**Do**
- Escape every server or user string before it meets markup; icons are fixed strings.
- Keep every safety item visible:
  - the plain-language notice;
  - the disclaimer;
  - every entry, including "check this";
  - the duplicate notice;
  - unresolved reasons;
  - citations;
  - the data line;
  - the attribution notices.
- Show severity with an icon and a word; make Major the most prominent.
- Keep one primary button per view.
- Use sentence case.

**Don't**
- Don't use green, or any colour that says "safe", for "no curated data".
- Don't use text lighter than `#5B616E`.
- Don't load fonts, scripts, images or anything else from another origin. Don't use inline
  scripts or styles (the CSP forbids them).
- Don't add clinical wording, reword report content or summarise findings in new words.
- Don't use hero imagery, decorative line art, gradients, photography or marketing sections.
- Don't use another company's colours, marks or phrasing.

## Responsive

- Below 900px: one column, and the checker panel is not sticky.
- Below 600px:
  - tiles wrap three per row;
  - finding rows stack (badge and pair, then details, then pill);
  - the header descriptor is hidden.
- Touch targets are at least 40px, and example buttons wrap.
- `prefers-reduced-motion`: no transitions and no shimmer.

## Known gaps

- There is no dark theme yet.
- Inter is the full variable font (344 KB), not subset.
- LLM reports have no structure, so they render as styled markdown. They get none of the
  tiles or rows.

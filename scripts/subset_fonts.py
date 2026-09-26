"""Subset the page's fonts to the characters it can show, as woff2 (a one-off build step).

Sources (SIL Open Font License 1.1), from github.com/google/fonts/tree/main/ofl, downloaded into --src:
  Newsreader[opsz,wght].ttf  (headings)   no Reserved Font Name: the subset keeps the name "Newsreader"
  IBMPlexSans[wdth,wght].ttf (body)       Reserved Font Name "Plex": the subset is renamed "PharmGuard Sans"
  IBMPlexMono-Regular.ttf    (citations)  Reserved Font Name "Plex": the subset is renamed "PharmGuard Mono"
The OFL requires renaming a modified version (a subset is one) when the license reserves the name.
Copyright and license name records are kept, and the license texts ship next to the fonts.

The character set is Basic Latin and Latin-1 (drug names are ASCII, see src/input_validation.py)
plus every other character that appears in the page, the report code and the attribution notices.
It is written to api/static/fonts/charset.txt, which tests/test_api.py checks the page against.

Needs fonttools and brotli (not in requirements.txt):
  pip install fonttools brotli
  python scripts/subset_fonts.py --src /path/to/downloaded/fonts
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "api" / "static" / "fonts"
TEXT_SOURCES = [ROOT / "api" / "static" / n for n in ("index.html", "app.js")] + [
    ROOT / "src" / "data" / "attribution.py", ROOT / "src" / "agents" / "report_structure.py",
    ROOT / "src" / "agents" / "generator.py", ROOT / "src" / "config.py"]

# (source file, output file, family name or None to keep it, axis pins/ranges for instancing)
FONTS = [
    ("Newsreader[opsz,wght].ttf", "newsreader-subset.woff2", None, {"opsz": 24, "wght": (400, 500)}),
    ("IBMPlexSans[wdth,wght].ttf", "pharmguard-sans.woff2", ("IBM Plex Sans", "PharmGuard Sans"),
     {"wdth": 100, "wght": (400, 600)}),
    ("IBMPlexMono-Regular.ttf", "pharmguard-mono.woff2", ("IBM Plex Mono", "PharmGuard Mono"), None),
]
KEEP_NAME_IDS = {0, 7, 13, 14}   # legal records kept as published: copyright, trademark, license, license URL


def charset() -> str:
    chars = {chr(c) for c in range(0x20, 0x7F)} | {chr(c) for c in range(0xA0, 0x100)}
    chars |= set("→←–—‘’“”…•−×≤≥")
    for path in TEXT_SOURCES:
        chars |= {ch for ch in path.read_text(encoding="utf-8") if ord(ch) >= 0x20}
    return "".join(sorted(chars))


def rename(font, old: str, new: str) -> None:
    table = font["name"]
    for rec in table.names:
        if rec.nameID in KEEP_NAME_IDS:
            continue
        text = rec.toUnicode()
        fixed = text.replace(old, new).replace(old.replace(" ", ""), new.replace(" ", ""))
        if fixed != text:
            rec.string = fixed
    leftover = [r.nameID for r in table.names if r.nameID not in KEEP_NAME_IDS and "Plex" in r.toUnicode()]
    if leftover:
        raise SystemExit(f"reserved name still present in name IDs {leftover}")


def main() -> None:
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, required=True, help="directory with the downloaded .ttf files")
    args = ap.parse_args()
    text = charset()
    (OUT / "charset.txt").write_text(text, encoding="utf-8")
    for src, out, names, axes in FONTS:
        font = TTFont(args.src / src)
        if axes:
            font = instancer.instantiateVariableFont(font, axes)
            buf = io.BytesIO()          # reload, so the subsetter sees fully compiled variation tables
            font.save(buf)
            buf.seek(0)
            font = TTFont(buf)
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["*"]
        opts.name_IDs = ["*"]
        opts.name_languages = ["*"]
        opts.notdef_outline = True
        sub = subset.Subsetter(opts)
        sub.populate(text=text)
        sub.subset(font)
        if names:
            rename(font, *names)
        font.flavor = "woff2"
        font.save(OUT / out)
        print(f"{out}: {(OUT / out).stat().st_size:,} bytes, {len(font.getBestCmap())} characters")


if __name__ == "__main__":
    main()

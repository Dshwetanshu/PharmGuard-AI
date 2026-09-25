"""Real drug vocabulary from RxNorm Current Prescribable Content (+ DrugBank synonyms by UNII).

Canonical key: the RxNorm ingredient (TTY=IN) name, lowercased. Aliases:
- IN names themselves
- precise ingredients / salt forms (PIN) -> IN via RXNREL "has_form"   (warfarin sodium -> warfarin)
- single-ingredient brands (BN) -> IN via RXNREL "has_tradename"      (Lipitor -> atorvastatin)
- FDA substance names (SAB=MTHSPL, TTY=SU), which share the IN/PIN RxCUI
                                                                        (ACETYLSALICYLIC ACID -> aspirin)
- RxNorm synonyms (SY, TMSY) attached to an IN/PIN/BN concept
Brands and multi-ingredient concepts (MIN) with more than one ingredient are
combination products: they go to a separate table so the normalizer can name
their ingredients instead of guessing one.

Names are never rewritten by string rules. The only exceptions are the reviewed
entries in SALT_GROUPS, where RxNorm keeps salts as separate ingredients but the
interaction sources name the moiety.
"""
from __future__ import annotations

import io
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

RXNCONSO = ["RXCUI", "LAT", "TS", "LUI", "STT", "SUI", "ISPREF", "RXAUI", "SAUI", "SCUI", "SDUI", "SAB", "TTY",
            "CODE", "STR", "SRL", "SUPPRESS", "CVF"]
RXNREL = ["RXCUI1", "RXAUI1", "STYPE1", "REL", "RXCUI2", "RXAUI2", "STYPE2", "RELA", "RUI", "SRUI", "SAB", "SL",
          "DIR", "RG", "SUPPRESS", "CVF"]

# Reviewed salt-to-moiety mappings (canonical ingredient name -> canonical name to use).
# Keep minimal: an entry is added only when the integrity report shows an interaction
# source naming the moiety while RxNorm models the salts as separate ingredients.
SALT_GROUPS: Dict[str, str] = {
    # RxNorm has IN lithium (6448), lithium carbonate (42351), lithium citrate (52105);
    # the interaction sources describe lithium the moiety.
    "lithium carbonate": "lithium",
    "lithium citrate": "lithium",
}


# Reviewed name aliases (source name -> US name already in the vocabulary). Only names
# the integrity report showed unmatched in a source (DDInter unless noted), whose target was
# verified in RxNorm Current Prescribable 2026-09-08. The target is resolved through
# the vocabulary at build time; an entry whose target is missing is reported, not applied.
REVIEWED_ALIASES: Dict[str, str] = {
    # INN (DDInter's naming) -> USAN/US name
    "salbutamol": "albuterol",
    "levosalbutamol": "levalbuterol",
    "valaciclovir": "valacyclovir",
    "norethisterone": "norethindrone",
    "etacrynic acid": "ethacrynic acid",
    "ursodeoxycholic acid": "ursodiol",
    "isoprenaline": "isoproterenol",
    "orciprenaline": "metaproterenol",
    "mepyramine": "pyrilamine",
    "calcipotriol": "calcipotriene",
    "cromoglicic acid": "cromolyn",
    "phylloquinone": "phytonadione",
    "somatotropin": "somatropin",
    "nicotinamide": "niacinamide",
    "clofedanol": "chlophedianol",
    "leuprorelin": "leuprolide",           # INN; surfaced by SIDER (568 rows)
    "deprenyl": "selegiline",              # older name; surfaced by SIDER (383 rows)
    "vitamin d3": "cholecalciferol",       # common name; surfaced by TWOSIDES (7,660 rows)
    # spelling / hydrate forms of the same substance
    "ethinylestradiol": "ethinyl estradiol",
    "ferrous sulfate anhydrous": "ferrous sulfate",
    "tetraferric tricitrate decahydrate": "ferric citrate",
}


def read_rrf(source: Path, table: str, columns: List[str], usecols: Optional[List[str]] = None) -> pd.DataFrame:
    """Read rrf/<table>.RRF from the release zip or an extracted directory."""
    source = Path(source)
    kw = dict(sep="|", header=None, names=columns + ["_"], dtype=str, na_filter=False,
              usecols=usecols or columns, quoting=3)
    if source.suffix == ".zip":
        with zipfile.ZipFile(source) as z:
            member = next(n for n in z.namelist() if n.endswith(f"{table}.RRF"))
            with z.open(member) as f:
                return pd.read_csv(io.TextIOWrapper(f, encoding="utf-8"), **kw)
    return pd.read_csv(source / "rrf" / f"{table}.RRF", **kw)


@dataclass
class RxNormVocabulary:
    aliases: pd.DataFrame            # name_lower, generic_name, rxcui, drugbank_id, kind
    combinations: pd.DataFrame       # name_lower, ingredients (" + "-joined), rxcui
    unii: Dict[str, str]             # UNII -> canonical generic name
    rxcui_to_generic: Dict[str, str]  # IN/PIN/BN rxcui -> canonical generic (single-ingredient only)
    stats: Dict[str, int] = field(default_factory=dict)


def build_rxnorm_vocabulary(source: Path, salt_groups: Optional[Dict[str, str]] = None) -> RxNormVocabulary:
    salt_groups = SALT_GROUPS if salt_groups is None else salt_groups
    c = read_rrf(source, "RXNCONSO", RXNCONSO, ["RXCUI", "LAT", "SAB", "TTY", "CODE", "STR", "SUPPRESS"])
    c = c[(c.LAT == "ENG") & ~c.SUPPRESS.isin(["Y", "O"]) & c.SAB.isin(["RXNORM", "MTHSPL"])]
    concept = c[c.SAB == "RXNORM"]
    in_name = {r: s.strip().lower() for r, s, t in zip(concept.RXCUI, concept.STR, concept.TTY) if t == "IN"}

    rel = read_rrf(source, "RXNREL", RXNREL, ["RXCUI1", "RXCUI2", "RELA", "SAB"])
    rel = rel[(rel.SAB == "RXNORM") & rel.RELA.isin(["has_form", "has_tradename", "part_of"])]
    to_in: Dict[str, Set[str]] = defaultdict(set)
    for a, b, rela in zip(rel.RXCUI1, rel.RXCUI2, rel.RELA):
        if b in in_name:                    # PIN has_form IN, BN has_tradename IN, MIN part_of IN
            to_in[a].add(b)
    for r in in_name:
        to_in[r] = {r}

    def generic_of(rx: str) -> str:
        name = in_name[rx]
        return salt_groups.get(name, name)

    # Candidate atoms: RxNorm names of IN/PIN/BN/MIN, RxNorm synonyms of those concepts,
    # and FDA substance names (MTHSPL SU) that share an IN/PIN RxCUI.
    keep = c[((c.SAB == "RXNORM") & c.TTY.isin(["IN", "PIN", "BN", "MIN", "SY", "TMSY"]))
             | ((c.SAB == "MTHSPL") & (c.TTY == "SU"))]
    keep = keep[keep.RXCUI.isin(to_in.keys())]
    names: Dict[str, Set[Tuple[str, ...]]] = defaultdict(set)   # name -> set of ingredient tuples
    origin: Dict[str, str] = {}
    for rx, sab, t, s in zip(keep.RXCUI, keep.SAB, keep.TTY, keep.STR):
        ins = tuple(sorted({generic_of(i) for i in to_in[rx]}))
        if not ins:
            continue
        n = s.strip().lower()
        names[n].add(ins)
        origin.setdefault(n, f"{sab}:{t}")

    alias_rows, combo_rows, ambiguous = [], [], 0
    canonical_rxcui: Dict[str, str] = {}      # canonical name -> RxCUI (the moiety's own IN wins)
    for rx, n in in_name.items():
        g = salt_groups.get(n, n)
        if g == n:
            canonical_rxcui[g] = rx
        else:
            canonical_rxcui.setdefault(g, rx)
    for n, ingredient_sets in names.items():
        if len(ingredient_sets) > 1:        # the same string names different things: don't guess
            ambiguous += 1
            continue
        (ins,) = ingredient_sets
        if len(ins) == 1:
            alias_rows.append({"name_lower": n, "generic_name": ins[0], "rxcui": canonical_rxcui.get(ins[0]),
                               "drugbank_id": None, "kind": origin[n]})
        else:
            combo_rows.append({"name_lower": n, "ingredients": " + ".join(ins), "rxcui": None})
    for g, rx in canonical_rxcui.items():   # canonical names always resolve to themselves
        alias_rows.append({"name_lower": g, "generic_name": g, "rxcui": rx, "drugbank_id": None,
                           "kind": "RXNORM:IN" if g in in_name.values() else "SALT_GROUP"})
    resolved = {r["name_lower"]: r for r in alias_rows}
    missing_targets = []
    for alias, target in REVIEWED_ALIASES.items():
        hit = resolved.get(target)
        if hit is None:
            missing_targets.append(alias)
        elif alias not in resolved:
            alias_rows.append({**hit, "name_lower": alias, "kind": "REVIEWED_ALIAS"})
    aliases = pd.DataFrame(alias_rows).drop_duplicates("name_lower", keep="last").reset_index(drop=True)
    combos = pd.DataFrame(combo_rows, columns=["name_lower", "ingredients", "rxcui"])

    unii: Dict[str, str] = {}
    su = c[(c.SAB == "MTHSPL") & (c.TTY == "SU") & (c.CODE != "")]
    for rx, code in zip(su.RXCUI, su.CODE):
        ins = {generic_of(i) for i in to_in.get(rx, ())}
        if len(ins) == 1:
            unii[code] = next(iter(ins))
    rxcui_to_generic = {rx: next(iter({generic_of(i) for i in ins}))
                        for rx, ins in to_in.items() if len({generic_of(i) for i in ins}) == 1}
    stats = {"ingredients": len(in_name), "aliases": len(aliases), "combination_products": len(combos),
             "ambiguous_names_dropped": ambiguous, "unii_codes": len(unii), "salt_group_entries": len(salt_groups),
             "reviewed_aliases": len(REVIEWED_ALIASES) - len(missing_targets),
             "reviewed_aliases_missing_target": len(missing_targets)}
    return RxNormVocabulary(aliases, combos, unii, rxcui_to_generic, stats)


def merge_drugbank_synonyms(vocab: RxNormVocabulary, drugbank: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
    """Add DrugBank common names and synonyms as aliases, linked to the RxNorm ingredient by UNII.

    `drugbank` is load_drugbank_vocabulary() output (needs a `unii` column). Existing
    RxNorm aliases always win; a DrugBank name that points elsewhere is counted, not applied.
    """
    aliases = vocab.aliases.copy()
    existing = dict(zip(aliases.name_lower, aliases.generic_name))
    added, conflicts, unlinked = [], 0, 0
    for _, r in drugbank.iterrows():
        g = vocab.unii.get(str(r.get("unii") or "").strip())
        if g is None:
            unlinked += 1
            continue
        for n in [r.get("generic_name")] + list(r.get("synonyms") or []):
            n = str(n or "").strip().lower()
            if not n:
                continue
            if n in existing:
                conflicts += existing[n] != g
                continue
            existing[n] = g
            added.append({"name_lower": n, "generic_name": g, "rxcui": None, "drugbank_id": r.get("drugbank_id"),
                          "kind": "DRUGBANK"})
    merged = pd.concat([aliases, pd.DataFrame(added, columns=aliases.columns)], ignore_index=True)
    return merged, {"drugbank_aliases_added": len(added), "drugbank_conflicts_skipped": int(conflicts),
                    "drugbank_rows_without_unii_link": unlinked}


def merge_fda_brands(aliases: pd.DataFrame, combinations: pd.DataFrame, products: pd.DataFrame
                     ) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, int], pd.DataFrame]:
    """Add Drugs@FDA brand names (including discontinued products) to the vocabulary.

    A brand's active ingredients are mapped through the existing aliases (exact match).
    - one ingredient, every product agrees, name not yet in the vocabulary -> alias
      (kind DRUGSATFDA:BRAND), e.g. Coumadin -> warfarin;
    - several ingredients, every product agrees, name new -> combination product;
    - the name is already in the vocabulary for the same drug -> nothing to do;
    - the name is already in the vocabulary for a different drug -> collision, not applied;
    - products under the same name map to different ingredients -> ambiguous, not applied;
    - some ingredient isn't in the vocabulary -> unmapped, not applied.
    Returns (aliases, combinations, stats, review) where review lists every collision and
    ambiguous name with its candidates, for a person to check.
    """
    alias = dict(zip(aliases.name_lower, aliases.generic_name))
    combos = dict(zip(combinations.name_lower, combinations.ingredients))
    by_name: Dict[str, Set[Tuple[str, ...]]] = defaultdict(set)
    unmapped: Set[str] = set()
    for name, ingredients in zip(products.drug_name, products.active_ingredient):
        n = str(name).strip().lower()
        parts = [p.strip().lower() for p in str(ingredients).split(";") if p.strip()]
        mapped = [alias.get(p) for p in parts]
        if not parts or any(m is None for m in mapped):
            unmapped.add(n)
            continue
        by_name[n].add(tuple(sorted(set(mapped))))

    added, added_combos, review = [], [], []
    stats = {"fda_brand_names": len(set(by_name) | unmapped), "fda_brands_added": 0,
             "fda_combinations_added": 0, "fda_already_known": 0, "fda_collisions": 0,
             "fda_ambiguous": 0, "fda_unmapped": 0}
    for n in sorted(set(by_name) | unmapped):
        sets = by_name.get(n, set())
        if n in unmapped:
            if sets:     # some products map, others don't: don't guess
                stats["fda_ambiguous"] += 1
                review.append({"name": n, "issue": "ambiguous",
                               "fda_ingredients": " | ".join(" + ".join(s) for s in sorted(sets)) + " | (unmapped)",
                               "vocabulary": alias.get(n) or combos.get(n) or ""})
            else:
                stats["fda_unmapped"] += 1
            continue
        if len(sets) > 1:
            stats["fda_ambiguous"] += 1
            review.append({"name": n, "issue": "ambiguous", "fda_ingredients": " | ".join(" + ".join(s) for s in sorted(sets)),
                           "vocabulary": alias.get(n) or combos.get(n) or ""})
            continue
        (ins,) = sets
        existing = alias.get(n)
        existing_combo = combos.get(n)
        if existing is not None or existing_combo is not None:
            same = (len(ins) == 1 and existing == ins[0]) or (existing_combo == " + ".join(ins))
            if same:
                stats["fda_already_known"] += 1
            else:
                stats["fda_collisions"] += 1
                review.append({"name": n, "issue": "collision", "fda_ingredients": " + ".join(ins),
                               "vocabulary": existing or f"combination: {existing_combo}"})
            continue
        if len(ins) == 1:
            hit = aliases[aliases.name_lower == ins[0]].iloc[0]
            added.append({"name_lower": n, "generic_name": ins[0], "rxcui": hit.get("rxcui"),
                          "drugbank_id": hit.get("drugbank_id"), "kind": "DRUGSATFDA:BRAND"})
        else:
            added_combos.append({"name_lower": n, "ingredients": " + ".join(ins), "rxcui": None})
    stats["fda_brands_added"], stats["fda_combinations_added"] = len(added), len(added_combos)
    aliases = pd.concat([aliases, pd.DataFrame(added, columns=aliases.columns)], ignore_index=True)
    combinations = pd.concat([combinations, pd.DataFrame(added_combos, columns=combinations.columns)],
                             ignore_index=True)
    return aliases, combinations, stats, pd.DataFrame(review, columns=["name", "issue", "fda_ingredients", "vocabulary"])

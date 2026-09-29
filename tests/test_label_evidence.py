"""FDA-label reference (src/evaluation/label_evidence.py): label choice, matching, heuristic classes."""
from __future__ import annotations

import pytest

from src.evaluation import label_evidence as E


def _label(drug, **sections):
    return E.Label(drug, f"set-{drug}", "3", "20260101", "NDA000001", drug.title(), sections)


@pytest.mark.parametrize("key,text,alias,expected", [
    # contraindications section: contraindicated whatever the wording
    ("contraindications", "Concomitant use of cyclosporine, danazol or gemfibrozil [see Drug Interactions (7.1)].",
     "gemfibrozil", "contraindicated"),
    # a neighbouring list item's advice is not attributed (HCTZ highlights)
    ("drug_interactions", "Cholestyramine and colestipol: Reduced absorption of thiazides (7.1) Lithium: Increased "
     "lithium concentrations and lithium toxicity (7.2) Antidiabetic drugs: Dosage adjustment may be required (7.3)",
     "lithium", "mentioned_without_guidance"),
    # "use with caution" in a table row is not "contraindicated" from elsewhere in the section
    ("drug_interactions", "Colchicine: contraindicated in renal impairment. Immunosuppressants: Cyclosporine "
     "Tacrolimus Use With Caution", "tacrolimus", "monitor_or_adjust"),
    ("warnings_and_cautions", "CYP2C19 inhibitors: Avoid concomitant use of omeprazole or esomeprazole.", "omeprazole",
     "avoid_or_not_recommended"),
    ("drug_interactions", "Reduce warfarin dose by one-third to one-half and monitor INR.", "warfarin", "monitor_or_adjust"),
    # PLR table: the drug is under Examples, the advice under Intervention
    ("drug_interactions", "Inhibitors of CYP2D6 Clinical Impact: The concomitant use may increase exposure. "
     "Intervention: If concomitant use is necessary, monitor patients closely for seizures and serotonin syndrome. "
     "Examples: Quinidine, fluoxetine, paroxetine, and bupropion", "fluoxetine", "monitor_or_adjust"),
    ("drug_interactions", "Trimethoprim can interfere with a serum methotrexate assay.", "trimethoprim",
     "mentioned_without_guidance"),
])
def test_classification_on_label_shapes(key, text, alias, expected):
    m = E.find_matches(_label("x", **{key: text}), "y", [alias])
    assert m and m[0].klass == expected, m


def test_whole_word_brand_and_salt_matching():
    lab = _label("amiodarone", drug_interactions="Warfarin sodium: reduce the dose. Coumadin users: monitor INR. "
                                                  "Nonwarfarinlike drugs: nothing.")
    m = E.find_matches(lab, "warfarin", ["warfarin", "warfarin sodium", "coumadin"])
    assert [x.alias for x in m] == ["warfarin sodium"] and m[0].klass == "monitor_or_adjust"
    assert E.find_matches(_label("a", drug_interactions="Hormonal contraceptives: may fail."), "ethinyl estradiol",
                          ["ethinyl estradiol"]) == []


def test_label_choice_prefers_single_ingredient_nda_then_latest():
    canon = {"warfarin sodium": "warfarin", "warfarin": "warfarin"}.get
    res = [
        {"set_id": "anda-new", "version": 9, "effective_time": "20260601",
         "openfda": {"generic_name": ["WARFARIN SODIUM"], "application_number": ["ANDA1"]}, "warnings": ["x"]},
        {"set_id": "nda-old", "version": 2, "effective_time": "20240101",
         "openfda": {"generic_name": ["WARFARIN SODIUM"], "application_number": ["NDA9"]}, "warnings": ["x"]},
        {"set_id": "combo", "version": 1, "effective_time": "20270101",
         "openfda": {"generic_name": ["WARFARIN AND ASPIRIN"], "application_number": ["NDA8"]}, "warnings": ["x"]},
    ]
    assert E.choose_label("warfarin", res, canon).set_id == "nda-old"
    assert E.choose_label("warfarin", res[:1], canon).set_id == "anda-new"
    assert E.choose_label("aspirin", res, canon) is None


def _ev(klass, found=("a", "b")):
    labels = {d: ({"set_id": "s", "version": "1", "effective_time": "", "application_number": "", "brand": ""}
                  if d in found else None) for d in ("a", "b")}
    best = E.Match("a", "b", "s", "1", "Warnings", "b", "…", klass) if klass != "not_mentioned" else None
    return E.PairEvidence(("a", "b"), klass, labels, best)


@pytest.mark.parametrize("expected,klass,found,ref", [
    ("interaction", "contraindicated", ("a", "b"), "interaction"),
    ("interaction", "monitor_or_adjust", ("a",), "interaction"),
    ("interaction", "mentioned_without_guidance", ("a", "b"), "unclear"),
    ("interaction", "not_mentioned", ("a", "b"), "unclear"),
    ("none", "not_mentioned", ("a", "b"), "none_weak"),
    ("none", "not_mentioned", ("a",), "unclear"),          # a missing label can't show absence
    ("none", "monitor_or_adjust", ("a", "b"), "unclear"),  # conflict with the row: not settled either way
])
def test_decision_rules(expected, klass, found, ref):
    assert E.decide(expected, _ev(klass, found))[0] == ref


def test_severity_comparison():
    s = E.severity_comparison([("contraindicated", "Major"), ("monitor_or_adjust", "Major"),
                               ("avoid_or_not_recommended", "Moderate"), ("monitor_or_adjust", None)])
    assert (s["pairs"], s["mapped_pairs"], s["mapped_agreement"], s["ddinter_lower_than_label"]) == (4, 3, 0.3333, 1)


def test_percent_dose_decrease_is_an_adjustment():
    text = ("The recommended dose of ELIQUIS should be decreased by 50% when coadministered with drugs that are combined "
            "P-gp and strong CYP3A4 inhibitors (e.g., ketoconazole, itraconazole, ritonavir).")
    assert E.find_matches(_label("apixaban", drug_interactions=text), "ketoconazole", ["ketoconazole"])[0].klass \
        == "monitor_or_adjust"

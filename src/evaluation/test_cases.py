"""Curated test cases for evaluation.

Each case has:
  - input_drugs: what the user types
  - description: human-readable context
  - known_interactions: ground-truth pairs expected to have data in TWOSIDES-like sources

Ground truth here is *partial and illustrative* — the real evaluation pipeline
recomputes ground truth programmatically by querying the loaded interaction
table for every pair in the input. These cases exist to drive the eval loop
with realistic, clinically-motivated inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class TestCase:
    __test__ = False  # not a pytest test class

    case_id: str
    description: str
    input_drugs: List[str]
    known_interaction_pairs: List[Tuple[str, str]] = field(default_factory=list)
    # Trajectory evaluation (src/evaluation/trajectory.py). Inputs not listed must
    # simply resolve; these pin down the edge cases (input -> expected canonical name).
    expected_resolved: Dict[str, str] = field(default_factory=dict)
    expected_unresolved: List[str] = field(default_factory=list)
    # Per-profile overrides ("sample", "public", "research"): input -> canonical name,
    # or None for "must stay unresolved". Used where the synthetic sample and the real
    # vocabulary legitimately differ (e.g. RxNorm has no plain "insulin").
    expected_by_profile: Dict[str, Dict[str, Optional[str]]] = field(default_factory=dict)

    def expectations(self, profile: str) -> Tuple[Dict[str, str], List[str]]:
        """(expected_resolved, expected_unresolved) for a build profile."""
        resolved, unresolved = dict(self.expected_resolved), list(self.expected_unresolved)
        for q, g in self.expected_by_profile.get(profile, {}).items():
            resolved.pop(q, None)
            if g is None:
                unresolved.append(q)
            else:
                resolved[q] = g
        return resolved, unresolved


# Hand labels suspected to be wrong (flagged for the user's review, NOT changed).
# The trajectory evaluation counts misses on these pairs separately.
SUSPECTED_LABEL_ERRORS: Dict[str, List[Tuple[str, str]]] = {
    # Empty since the 2026-09-29 review (docs/LABEL_CHANGES.md): EDG-03's label was removed.
}


TEST_CASES: List[TestCase] = [
    # ---------- Geriatric polypharmacy (proposal's canonical scenario) ----------
    TestCase(
        case_id="GER-01",
        description="72yo with cardiology + rheumatology overlap (proposal example)",
        input_drugs=["lisinopril", "spironolactone", "metformin", "atorvastatin",
                     "aspirin", "omeprazole", "sertraline"],
        known_interaction_pairs=[
            ("lisinopril", "spironolactone"),
            ("aspirin", "omeprazole"),
        ],
    ),
    TestCase(
        case_id="GER-02",
        description="Elderly HTN + DM2 + pain management",
        input_drugs=["lisinopril", "metformin", "ibuprofen", "aspirin",
                     "atorvastatin", "levothyroxine"],
        known_interaction_pairs=[("lisinopril", "ibuprofen")],
    ),
    TestCase(
        case_id="GER-03",
        description="Post-MI regimen with GI prophylaxis",
        input_drugs=["aspirin", "clopidogrel", "atorvastatin", "metoprolol",
                     "lisinopril", "omeprazole"],
        known_interaction_pairs=[("clopidogrel", "omeprazole")],
    ),
    TestCase(
        case_id="GER-04",
        description="AFib + HTN + hyperlipidemia",
        input_drugs=["warfarin", "digoxin", "amiodarone", "atorvastatin", "lisinopril"],
        known_interaction_pairs=[
            ("warfarin", "amiodarone"),
            ("digoxin", "amiodarone"),
        ],
    ),

    # ---------- Classic textbook interactions ----------
    TestCase("TXT-01", "Warfarin + NSAID bleeding risk",
             ["warfarin", "ibuprofen"], [("warfarin", "ibuprofen")]),
    TestCase("TXT-02", "MAOI + SSRI serotonin risk",
             ["sertraline", "phenelzine"], [("sertraline", "phenelzine")]),
    TestCase("TXT-03", "Statin + macrolide myopathy risk",
             ["simvastatin", "clarithromycin"], [("simvastatin", "clarithromycin")]),
    TestCase("TXT-04", "ACE + K-sparing diuretic hyperkalemia",
             ["lisinopril", "spironolactone"], [("lisinopril", "spironolactone")]),
    TestCase("TXT-05", "QT-prolonging combination",
             ["amiodarone", "ciprofloxacin"], [("amiodarone", "ciprofloxacin")]),
    TestCase("TXT-06", "Benzodiazepine + opioid respiratory depression",
             ["alprazolam", "oxycodone"], [("alprazolam", "oxycodone")]),
    TestCase("TXT-07", "MAOI + tyramine precaution meds",
             ["tramadol", "sertraline"], [("tramadol", "sertraline")]),
    TestCase("TXT-08", "Digoxin + diuretic",
             ["digoxin", "furosemide"], [("digoxin", "furosemide")]),
    TestCase("TXT-09", "Methotrexate + NSAID",
             ["methotrexate", "ibuprofen"], [("methotrexate", "ibuprofen")]),
    TestCase("TXT-10", "Theophylline + ciprofloxacin",
             ["theophylline", "ciprofloxacin"], [("theophylline", "ciprofloxacin")]),

    # ---------- Edge cases ----------
    TestCase("EDG-01", "Single drug (no pairs)", ["metformin"], []),
    TestCase("EDG-02", "Two drugs with no graded interaction in DDInter",
             ["acetaminophen", "levothyroxine"], []),
    TestCase("EDG-03", "Brand name input",
             ["Lipitor", "Prinivil"], [],
             expected_resolved={"Lipitor": "atorvastatin", "Prinivil": "lisinopril"}),
    TestCase("EDG-04", "Mixed case + whitespace",
             ["  METFORMIN  ", "Lisinopril", "aspirin"], [],
             expected_resolved={"  METFORMIN  ": "metformin", "Lisinopril": "lisinopril"}),
    TestCase("EDG-05", "Misspelling", ["metfromin", "lisonopril"], [],
             expected_resolved={"metfromin": "metformin", "lisonopril": "lisinopril"}),
    TestCase("EDG-06", "Unknown drug",
             ["lisinopril", "fictional_drug_xyz"], [],
             expected_resolved={"lisinopril": "lisinopril"}, expected_unresolved=["fictional_drug_xyz"]),
    TestCase("EDG-07", "Max-size list (12 drugs)",
             ["lisinopril", "metformin", "aspirin", "atorvastatin", "omeprazole",
              "sertraline", "amlodipine", "levothyroxine", "ibuprofen", "warfarin",
              "digoxin", "simvastatin"], []),

    # ---------- Mental health ----------
    TestCase("MH-01", "SSRI + NSAID bleeding",
             ["sertraline", "ibuprofen"], [("sertraline", "ibuprofen")]),
    TestCase("MH-02", "Lithium + thiazide",
             ["lithium", "hydrochlorothiazide"], [("lithium", "hydrochlorothiazide")],
             expected_resolved={"lithium": "lithium"}),
    TestCase("MH-03", "Antipsychotic combination",
             ["haloperidol", "quetiapine"], []),
    TestCase("MH-04", "Anxiety + sleep combination",
             ["alprazolam", "zolpidem", "trazodone"], []),
    TestCase("MH-05", "Bipolar regimen",
             ["lithium", "valproic acid", "quetiapine"], [],
             expected_resolved={"lithium": "lithium", "valproic acid": "valproate"}),

    # ---------- Cardiology ----------
    TestCase("CV-01", "Heart failure triple therapy",
             ["lisinopril", "carvedilol", "spironolactone", "furosemide"],
             [("lisinopril", "spironolactone")]),
    TestCase("CV-02", "Post-stent dual antiplatelet",
             ["aspirin", "clopidogrel", "atorvastatin"], []),
    TestCase("CV-03", "Warfarin + antibiotic",
             ["warfarin", "trimethoprim"], [("warfarin", "trimethoprim")]),
    TestCase("CV-04", "Beta-blocker + CCB",
             ["metoprolol", "verapamil"], [("metoprolol", "verapamil")]),
    TestCase("CV-05", "Statin + fibrate",
             ["atorvastatin", "gemfibrozil"], [("atorvastatin", "gemfibrozil")]),

    # ---------- Endocrine / Metabolic ----------
    TestCase("END-01", "Diabetes + thyroid",
             ["metformin", "levothyroxine"], []),
    TestCase("END-02", "Insulin + beta-blocker masking",
             ["insulin glargine", "metoprolol"], [("insulin glargine", "metoprolol")],
             # The synthetic sample has only a generic "insulin", so there this is a source gap.
             expected_by_profile={"sample": {"insulin glargine": None}}),
    TestCase("END-03", "Steroid + antidiabetic",
             ["prednisone", "metformin"], []),

    # ---------- Infectious disease ----------
    TestCase("ID-01", "Macrolide + QT-prolonging",
             ["azithromycin", "sotalol"], [("azithromycin", "sotalol")]),
    TestCase("ID-02", "Fluoroquinolone + antacid",
             ["ciprofloxacin", "calcium carbonate"], [("ciprofloxacin", "calcium carbonate")]),
    TestCase("ID-03", "TB regimen + OC",
             ["rifampin", "ethinyl estradiol"], [("rifampin", "ethinyl estradiol")]),
    TestCase("ID-04", "HIV regimen + statin",
             ["ritonavir", "simvastatin"], [("ritonavir", "simvastatin")]),

    # ---------- Oncology-adjacent ----------
    TestCase("ONC-01", "Methotrexate + PPI",
             ["methotrexate", "omeprazole"], [("methotrexate", "omeprazole")]),
    TestCase("ONC-02", "Tamoxifen + SSRI",
             ["tamoxifen", "paroxetine"], [("tamoxifen", "paroxetine")]),

    # ---------- Pain management ----------
    TestCase("PAIN-01", "Opioid + benzo + alcohol signal",
             ["oxycodone", "alprazolam"], [("oxycodone", "alprazolam")]),
    TestCase("PAIN-02", "Tramadol + SSRI",
             ["tramadol", "fluoxetine"], [("tramadol", "fluoxetine")]),
    TestCase("PAIN-03", "Chronic pain cocktail",
             ["gabapentin", "duloxetine", "oxycodone", "acetaminophen"], []),

    # ---------- Respiratory ----------
    TestCase("RSP-01", "Asthma + beta-blocker",
             ["albuterol", "propranolol"], [("albuterol", "propranolol")]),
    TestCase("RSP-02", "COPD + theophylline + cipro",
             ["theophylline", "ciprofloxacin", "albuterol"],
             [("theophylline", "ciprofloxacin")]),

    # ---------- GI ----------
    TestCase("GI-01", "PPI + clopidogrel",
             ["omeprazole", "clopidogrel"], [("omeprazole", "clopidogrel")]),
    TestCase("GI-02", "Antacid + iron",
             ["calcium carbonate", "ferrous sulfate"], []),

    # ---------- Realistic 10-drug geriatric profile ----------
    TestCase(
        case_id="REAL-01",
        description="Real-world 10-drug geriatric patient",
        input_drugs=["lisinopril", "metformin", "atorvastatin", "aspirin",
                     "omeprazole", "levothyroxine", "amlodipine", "warfarin",
                     "furosemide", "sertraline"],
        known_interaction_pairs=[
            ("warfarin", "aspirin"),
            ("sertraline", "aspirin"),
            ("sertraline", "warfarin"),
        ],
    ),

    # ---------- Brand names and look-alikes (blind trial, step 8b) ----------
    # Normalization expectations only: no known_interaction_pairs (labels await review).
    # The synthetic sample vocabulary lacks most of these brands, so on "sample" they
    # are expected to stay unresolved.
    TestCase("LA-01", "Discontinued brand (Coumadin) + brand (Diflucan)", ["Coumadin", "Diflucan"], [],
             expected_resolved={"Coumadin": "warfarin", "Diflucan": "fluconazole"},
             expected_by_profile={"sample": {"Diflucan": None}}),
    TestCase("LA-02", "Brand (Lanoxin) + amiodarone", ["Lanoxin", "amiodarone"], [],
             expected_resolved={"Lanoxin": "digoxin"}, expected_by_profile={"sample": {"Lanoxin": None}}),
    TestCase("LA-03", "Look-alike brand Celebrex + warfarin", ["Celebrex", "warfarin"], [],
             expected_resolved={"Celebrex": "celecoxib"}, expected_by_profile={"sample": {"Celebrex": None}}),
    TestCase("LA-04", "Look-alike brand Cerebyx + warfarin", ["Cerebyx", "warfarin"], [],
             expected_resolved={"Cerebyx": "fosphenytoin"}, expected_by_profile={"sample": {"Cerebyx": None}}),
    TestCase("LA-05", "Look-alike brand Klonopin + oxycodone", ["Klonopin", "oxycodone"], [],
             expected_resolved={"Klonopin": "clonazepam"}, expected_by_profile={"sample": {"Klonopin": None}}),
    TestCase("LA-06", "Same drug twice (Coumadin + warfarin) + Diflucan", ["Coumadin", "Diflucan", "warfarin"], [],
             expected_resolved={"Coumadin": "warfarin", "Diflucan": "fluconazole"},
             expected_by_profile={"sample": {"Diflucan": None}}),
    TestCase("LA-07", "Misspelling between two look-alikes (Celebyx)", ["Celebyx", "warfarin"], [],
             expected_unresolved=["Celebyx"]),
    TestCase("LA-08", "Discontinued brand Biaxin + simvastatin", ["Biaxin", "simvastatin"], [],
             expected_resolved={"Biaxin": "clarithromycin"}),
    TestCase("LA-09", "Ambiguous generic name (plain insulin)", ["insulin", "metoprolol"], [],
             # Real RxNorm has only specific insulins: "insulin" must stay ambiguous there.
             expected_by_profile={"public": {"insulin": None}, "research": {"insulin": None}}),
]

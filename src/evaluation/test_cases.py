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
from typing import List, Tuple


@dataclass
class TestCase:
    case_id: str
    description: str
    input_drugs: List[str]
    known_interaction_pairs: List[Tuple[str, str]] = field(default_factory=list)


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
    TestCase("EDG-02", "Two drugs with no known interaction",
             ["acetaminophen", "levothyroxine"], []),
    TestCase("EDG-03", "Brand name input",
             ["Lipitor", "Prinivil"], [("atorvastatin", "lisinopril")]),
    TestCase("EDG-04", "Mixed case + whitespace",
             ["  METFORMIN  ", "Lisinopril", "aspirin"], []),
    TestCase("EDG-05", "Misspelling", ["metfromin", "lisonopril"], []),
    TestCase("EDG-06", "Unknown drug",
             ["lisinopril", "fictional_drug_xyz"], []),
    TestCase("EDG-07", "Max-size list (12 drugs)",
             ["lisinopril", "metformin", "aspirin", "atorvastatin", "omeprazole",
              "sertraline", "amlodipine", "levothyroxine", "ibuprofen", "warfarin",
              "digoxin", "simvastatin"], []),

    # ---------- Mental health ----------
    TestCase("MH-01", "SSRI + NSAID bleeding",
             ["sertraline", "ibuprofen"], [("sertraline", "ibuprofen")]),
    TestCase("MH-02", "Lithium + thiazide",
             ["lithium", "hydrochlorothiazide"], [("lithium", "hydrochlorothiazide")]),
    TestCase("MH-03", "Antipsychotic combination",
             ["haloperidol", "quetiapine"], []),
    TestCase("MH-04", "Anxiety + sleep combination",
             ["alprazolam", "zolpidem", "trazodone"], []),
    TestCase("MH-05", "Bipolar regimen",
             ["lithium", "valproic acid", "quetiapine"], []),

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
             ["insulin", "metoprolol"], [("insulin", "metoprolol")]),
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
]

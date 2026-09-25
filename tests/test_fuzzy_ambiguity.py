"""Fuzzy matching must not guess between different drugs (real-vocabulary regression)."""
from __future__ import annotations

import pandas as pd

from src.config import Config
from src.data.normalizer import DrugNormalizer

# Names and scores mirror the real RxNorm vocabulary, where "insulin" matched
# "inulin" (a diagnostic agent) at 92 while several insulins scored 90.
VOCAB = pd.DataFrame(
    [(n, g, None, None) for n, g in [
        ("inulin", "inulin"), ("insulin glulisine, human", "insulin glulisine, human"),
        ("insulin detemir", "insulin detemir"), ("metformin", "metformin"), ("merbromin", "merbromin"),
        ("amoxicillin", "amoxicillin"), ("ampicillin", "ampicillin"),
    ]], columns=["name_lower", "generic_name", "rxcui", "drugbank_id"])


def _normalizer():
    cfg = Config()
    cfg.retrieval.rxnorm_api_enabled = False
    return DrugNormalizer(cfg).load_from_dataframe(VOCAB)


def test_ambiguous_fuzzy_match_stays_unresolved_and_lists_candidates():
    r = _normalizer().resolve("insulin")
    assert (r.resolved, r.generic_name, r.method) == (False, None, "fuzzy_ambiguous")
    # Real insulins are listed, never inulin (item 6 of the step 8b fixes).
    assert r.note == "ambiguous name; matching drugs: insulin detemir / insulin glulisine, human; enter the specific drug"


def test_clear_misspellings_still_resolve():
    n = _normalizer()
    assert (n.resolve("metfromin").generic_name, n.resolve("metfromin").method) == ("metformin", "fuzzy")
    assert n.resolve("amoxicilin").generic_name == "amoxicillin"

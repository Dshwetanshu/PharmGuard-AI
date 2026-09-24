"""Hand-label scoring: independent of the normalizer/table used for retrieval."""
from __future__ import annotations

from src.evaluation.hand_labels import score_hand_labels
from src.evaluation.test_cases import TEST_CASES, TestCase


def test_scorer_counts_hits_misses_and_unlabelled():
    cases = [
        TestCase("A", "", ["lithium", "hctz", "x"], [("lithium", "hctz"), ("x", "hctz")]),
        TestCase("B", "", ["p", "q"], []),
    ]
    retrieved = {"A": {("hctz", "lithium carbonate")}, "B": {("p", "q")}}
    alias = {"lithium": "lithium carbonate"}
    r = score_hand_labels(cases, lambda drugs: retrieved["A" if "x" in drugs else "B"], alias)
    assert (r["labelled_pairs"], r["retrieved_pairs"], r["hits"]) == (2, 2, 1)
    assert (r["recall"], r["precision_lower_bound"]) == (0.5, 0.5)
    assert r["missed"] == [("A", ["hctz", "x"])]
    assert r["unlabelled_retrieved"] == [("B", ["p", "q"])]


def test_lithium_label_is_hit_on_sample_data(sample_pipeline):
    import pandas as pd
    from src.data.canonical import build_alias_map

    vocab = pd.read_parquet(sample_pipeline.cfg.paths.processed_dir / "drug_vocabulary.parquet")
    mh02 = [c for c in TEST_CASES if c.case_id == "MH-02"]

    def retrieve(drugs):
        plan = sample_pipeline.planner.plan(sample_pipeline.normalizer.resolve_many(drugs))
        return set(sample_pipeline.retriever.execute(plan).interactions)

    r = score_hand_labels(mh02, retrieve, build_alias_map(vocab))
    assert r["missed"] == [] and r["hits"] == 1


def test_eval_output_has_no_hard_coded_metrics():
    # completeness_flagging was `1.0 if all(True for _ in cases)`: a constant, not a measurement.
    from src.evaluation.metrics import AggregateMetrics

    out = AggregateMetrics().as_dict()
    assert "completeness_flagging" not in out
    assert "1.0 by construction" in out["note"]


def test_misses_are_split_into_source_gaps_and_pipeline_misses():
    import pandas as pd
    from src.evaluation.hand_labels import pair_sources

    table = pd.DataFrame({"drug_a_name": ["Warfarin", "lithium"], "drug_b_name": ["aspirin", "ibuprofen"],
                          "source": ["DDInter", "DDInter"]})
    sources = pair_sources(table)
    assert sources == {("aspirin", "warfarin"): ["DDInter"], ("ibuprofen", "lithium"): ["DDInter"]}

    class C:
        def __init__(self, cid, drugs, pairs):
            self.case_id, self.input_drugs, self.known_interaction_pairs = cid, drugs, pairs

    cases = [C("A", ["warfarin", "aspirin"], [("warfarin", "aspirin")]),          # in a table, not retrieved
             C("B", ["lithium", "hctz"], [("lithium", "hydrochlorothiazide")])]   # in no table
    out = score_hand_labels(cases, lambda drugs: set(), {"hctz": "hydrochlorothiazide"}, sources)
    assert (out["source_gaps"], out["pipeline_misses"]) == (1, 1)
    assert out["missed_source_gap"] == [("B", ["hydrochlorothiazide", "lithium"])]
    assert out["missed_pipeline"] == [("A", ["aspirin", "warfarin"], ["DDInter"])]
    assert out["pipeline_recall"] == 0.0

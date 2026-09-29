"""FAERS disproportionality: hand-computed 2x2 tables, thresholds, confounding, and the openFDA client (no network)."""
from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from src.retrieval.faers_retriever import FaersRetriever, OpenFdaCounts
from src.retrieval.faers_stats import PairEventCounts, Thresholds, assess, chi2_yates, prr, ror_ci, two_by_two

# N = 10,000 reports; 100 list both drugs, 20 of them with the event; 200 reports have the event.
#            E      not E
#   A&B      20       80
#   rest    180    9,720
CLEAN = PairEventCounts(total=10_000, n_a=1_000, n_b=500, n_ab=100, n_e=200, n_ae=40, n_be=30, n_abe=20)


def test_two_by_two_cells():
    assert two_by_two(CLEAN) == (20, 80, 180, 9_720)


def test_prr_ror_ci_and_yates_chi2_by_hand():
    # PRR = (20/100) / (180/9900) = 11
    assert prr(20, 80, 180, 9_720) == pytest.approx(11.0)
    # ROR = 20*9720 / (80*180) = 13.5; SE(ln ROR) = sqrt(1/20 + 1/80 + 1/180 + 1/9720) = 0.26107
    ror, lo, hi = ror_ci(20, 80, 180, 9_720)
    assert ror == pytest.approx(13.5) and lo == pytest.approx(8.0930, abs=1e-3) and hi == pytest.approx(22.5195, abs=1e-3)
    # Yates: 10000 * (|194400 - 14400| - 5000)^2 / (100 * 9900 * 200 * 9800) = 157.828
    assert chi2_yates(20, 80, 180, 9_720) == pytest.approx(157.828, abs=1e-3)


def test_zero_cells_give_no_ratio():
    assert ror_ci(0, 10, 5, 100) == (None, None, None)
    assert prr(3, 7, 0, 100) is None
    assert chi2_yates(0, 0, 5, 100) is None


def test_inconsistent_counts_are_rejected():
    with pytest.raises(ValueError):
        two_by_two(PairEventCounts(total=100, n_a=10, n_b=10, n_ab=5, n_e=3, n_ae=3, n_be=3, n_abe=6))


def test_clean_signal_is_surfaced():
    s = assess("rhabdomyolysis", CLEAN, names=("a", "b"))
    assert s.surfaced and s.reasons == []
    assert (s.prr, s.ror, s.ror_ci_low, s.chi2) == (11.0, 13.5, 8.093, 157.83)
    # pair rate 20/100 = 0.2; a without b: (40-20)/(1000-100) = 0.0222; b without a: (30-20)/(500-100) = 0.025
    assert (s.pair_rate, s.rate_a_without_b, s.rate_b_without_a) == (0.2, 0.02222, 0.025)


def test_signal_explained_by_one_drug_is_suppressed():
    # a's own event rate without b is (200-20)/900 = 0.2, the same as the pair's: a explains it.
    confounded = PairEventCounts(total=10_000, n_a=1_000, n_b=500, n_ab=100, n_e=400, n_ae=200, n_be=30, n_abe=20)
    s = assess("nausea", confounded, names=("amiodarone", "zzz"))
    assert not s.surfaced
    assert s.prr >= 2 and s.chi2 >= 4 and s.ror_ci_low > 1      # passes Evans and the ROR bound
    assert s.reasons == ["explained by amiodarone alone (pair rate < 2 x its rate without the other drug)"]


@pytest.mark.parametrize("counts,reason", [
    (PairEventCounts(10_000, 1_000, 500, 100, 200, 22, 12, 2), "fewer than 3 reports"),
    (PairEventCounts(10_000, 1_000, 500, 100, 1_500, 25, 15, 15), "PRR below 2"),
    (PairEventCounts(10_000, 1_000, 500, 5, 2_500, 300, 200, 3), "ROR lower 95% bound not above 1"),   # ROR 4.5, CI low 0.75
])
def test_weak_signals_are_suppressed_with_a_reason(counts, reason):
    s = assess("event", counts)
    assert not s.surfaced and reason in s.reasons


def test_thresholds_are_configurable():
    lenient = Thresholds(min_reports=2)
    assert "fewer than 3 reports" not in assess("e", PairEventCounts(10_000, 1_000, 500, 100, 200, 22, 12, 2),
                                                lenient).reasons


# ---------- openFDA client and retriever, with a fake fetcher ----------

A, B = 'patient.drug.medicinalproduct:"drug-a"', 'patient.drug.medicinalproduct:"drug-b"'
EV = lambda t: f'patient.reaction.reactionmeddrapt.exact:"{t}"'


def fake_openfda(totals, top):
    """fetch(url) answering count and total queries from dicts; None (a 404) for anything unknown."""
    calls = []

    def fetch(url):
        calls.append(url)
        q = parse_qs(urlsplit(url).query)
        search = q.get("search", [""])[0]
        if "count" in q:
            return {"results": [{"term": t, "count": n} for t, n in top]} if search == f"{A} AND {B}" else None
        assert q["limit"] == ["1"]
        n = totals.get(search)
        return None if n is None else {"meta": {"results": {"total": n}}, "results": []}
    return fetch, calls


def _totals(event, n_e, n_ae, n_be):
    return {"": 10_000, A: 1_000, B: 500, f"{A} AND {B}": 100, EV(event): n_e,
            f"{A} AND {EV(event)}": n_ae, f"{B} AND {EV(event)}": n_be}


def test_retriever_surfaces_one_signal_and_suppresses_a_confounded_one(tmp_path):
    totals = {**_totals("RHABDOMYOLYSIS", 200, 40, 30), **_totals("NAUSEA", 400, 200, 30)}
    fetch, calls = fake_openfda(totals, [("RHABDOMYOLYSIS", 20), ("NAUSEA", 20)])
    r = FaersRetriever(enabled=True, counts=OpenFdaCounts(fetch=fetch, cache_dir=tmp_path, min_interval=0))
    out = r.assess_pair("drug-b", "drug-a")
    assert out.pair == ("drug-a", "drug-b") and out.checked_events == 2
    assert [s.condition for s in out.surfaced] == ["rhabdomyolysis"]
    assert out.surfaced[0].prr == 11.0 and out.surfaced[0].report_count == 20
    assert [s.event for s in out.suppressed] == ["nausea"]
    assert "explained by drug-a alone" in out.suppressed[0].reasons[0]
    # 1 top-events query + N + n(A) + n(B) + n(A and B) + 3 per event
    assert len(calls) == 1 + 4 + 3 * 2
    # "A without B" is computed, never queried with NOT
    assert not any("NOT" in parse_qs(urlsplit(u).query).get("search", [""])[0] for u in calls)


def test_404_counts_as_zero_and_the_disk_cache_is_reused(tmp_path):
    fetch, calls = fake_openfda({"": 10_000}, [])
    c = OpenFdaCounts(fetch=fetch, cache_dir=tmp_path, min_interval=0)
    assert c.total(A) == 0 and c.total() == 10_000
    again = OpenFdaCounts(fetch=lambda url: pytest.fail("cache miss"), cache_dir=tmp_path, min_interval=0)
    assert again.total(A) == 0 and again.total() == 10_000
    assert all(json.loads(p.read_text())["url"].startswith("https://api.fda.gov/") for p in tmp_path.iterdir())


def test_no_co_reports_means_no_signal_and_no_further_calls():
    fetch, calls = fake_openfda({}, [])
    r = FaersRetriever(enabled=True, counts=OpenFdaCounts(fetch=fetch, min_interval=0))
    out = r.assess_pair("drug-a", "drug-b")
    assert out.surfaced == [] and out.suppressed == [] and len(calls) == 1


def test_network_errors_are_swallowed():
    def boom(url):
        raise OSError("down")
    out = FaersRetriever(enabled=True, counts=OpenFdaCounts(fetch=boom, min_interval=0)).assess_pair("x", "y")
    assert out.surfaced == [] and out.error == "OSError"


def test_disabled_retriever_makes_no_calls():
    out = FaersRetriever(enabled=False, counts=OpenFdaCounts(fetch=lambda u: pytest.fail("called"))).assess_pair("x", "y")
    assert out.surfaced == [] and out.checked_events == 0


# ---------- in the report ----------

class AssessingFaers:
    """A FAERS component with statistics: one surfaced signal and one suppressed event per pair."""
    enabled = True

    def __init__(self, surfaced=True):
        self.surfaced = surfaced

    def assess_pair(self, a, b):
        from src.retrieval.faers_retriever import FaersAssessment, FaersRecord
        pair = tuple(sorted((a, b)))
        s = assess("nausea", PairEventCounts(10_000, 1_000, 500, 100, 400, 200, 30, 20), names=pair)
        rec = FaersRecord("FAERS-0123456789", *pair, "rhabdomyolysis", 20, prr=11.0, ror=13.5,
                          ror_ci_low=8.093, ror_ci_high=22.519, chi2=157.83)
        return FaersAssessment(pair, [rec] if self.surfaced else [], [s], 2)

    def retrieve_pair(self, a, b):
        return self.assess_pair(a, b).surfaced


@pytest.fixture(scope="module")
def faers_graph(test_data_dir, sample_ingest_report):
    from dataclasses import replace
    from src.graph import PharmGuardGraph, Settings, build_components
    s = Settings(data_dir=test_data_dir, mode="deterministic", faers_enabled=True)
    return lambda faers: PharmGuardGraph(s, replace(build_components(s), faers=faers))


def test_report_shows_statistics_and_the_suppressed_count(faers_graph):
    s = faers_graph(AssessingFaers()).run(["metformin", "levothyroxine"])
    r = s["report"]
    assert ("- **levothyroxine + metformin** — rhabdomyolysis: 20 reports; PRR 11.00, ROR 13.50 "
            "(95% CI 8.09–22.52), chi-square 157.8 [FAERS:FAERS-0123456789]") in r
    assert "1 co-reported event checked in FAERS was suppressed" in r
    assert "## FAERS Spontaneous Reports (unvalidated)" in r and s["final_validation"]["passed"]
    assert s["retrieval"]["no_data_pairs"] == [["levothyroxine", "metformin"]]      # still no curated data
    assert s["report_structure"]["faers"]["suppressed"] == 1
    assert s["trajectory"][[t["node"] for t in s["trajectory"]].index("faers")]["detail"]["suppressed_signals"] == 1


def test_only_suppressed_signals_still_say_so(faers_graph):
    s = faers_graph(AssessingFaers(surfaced=False)).run(["metformin", "levothyroxine"])
    assert "1 co-reported event checked in FAERS was suppressed" in s["report"]
    assert "[FAERS:" not in s["report"] and s["final_validation"]["passed"]


def test_checker_catches_a_wrong_prr_on_a_faers_line(faers_graph):
    from src.verification import Evidence, validate_report
    s = faers_graph(AssessingFaers()).run(["metformin", "levothyroxine"])
    bad = s["report"].replace("PRR 11.00", "PRR 31.00")
    ev = Evidence.from_dict(s["evidence"])
    assert validate_report(s["report"], ev).passed
    assert "NUMERIC_MISMATCH" in validate_report(bad, ev).codes()


def test_api_cap_counts_assessed_pairs():
    import time
    from api.service import _FAERS_BUDGET, CappedFaers, FaersBudget
    capped = CappedFaers(AssessingFaers())
    token = _FAERS_BUDGET.set(FaersBudget(max_pairs=1, budget_s=10))
    try:
        assert capped.assess_pair("a", "b").surfaced
        skipped = capped.assess_pair("c", "d")
        assert not skipped.surfaced and skipped.error == "SkippedByRequestCap"
        assert (_FAERS_BUDGET.get().consulted, _FAERS_BUDGET.get().skipped) == (1, 1)
    finally:
        _FAERS_BUDGET.reset(token)


def test_transient_openfda_errors_are_retried_then_raised(monkeypatch):
    import io
    from urllib.error import HTTPError
    from src.retrieval import faers_retriever

    codes = [500, 500, 200]

    class Resp(io.BytesIO):
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def urlopen(req, timeout):
        code = codes.pop(0)
        if code != 200:
            raise HTTPError(req.full_url, code, "err", {}, None)
        return Resp(b'{"meta": {"results": {"total": 7}}}')

    monkeypatch.setattr(faers_retriever.urllib_request, "urlopen", urlopen)
    waits = []
    c = OpenFdaCounts(min_interval=0, sleep=waits.append)
    assert c.total(A) == 7 and waits == [1.0, 2.0]
    codes[:] = [500, 500, 500]
    with pytest.raises(HTTPError):
        OpenFdaCounts(min_interval=0, sleep=waits.append).total(B)
    codes[:] = [400]
    with pytest.raises(HTTPError):
        OpenFdaCounts(min_interval=0, sleep=pytest.fail).total(B)      # not transient: no retry


def test_administrative_terms_are_not_signals():
    totals = _totals("RHABDOMYOLYSIS", 200, 40, 30)
    fetch, calls = fake_openfda(totals, [("DRUG INTERACTION", 90), ("DRUG INEFFECTIVE", 50), ("RHABDOMYOLYSIS", 20)])
    out = FaersRetriever(enabled=True, max_events=3, counts=OpenFdaCounts(fetch=fetch, min_interval=0)).assess_pair(
        "drug-a", "drug-b")
    assert [s.event for s in out.assessed] == ["rhabdomyolysis"]


def test_deadline_stops_further_calls():
    import time
    fetch, calls = fake_openfda(_totals("RHABDOMYOLYSIS", 200, 40, 30), [("RHABDOMYOLYSIS", 20)])
    past = time.monotonic() - 1
    r = FaersRetriever(enabled=True, counts=OpenFdaCounts(fetch=fetch, min_interval=0, deadline=lambda: past))
    out = r.assess_pair("drug-a", "drug-b")
    assert out.error == "TimeoutError" and calls == []
    # errors aren't cached: the same pair succeeds once there is time
    r.counts.deadline = lambda: None
    assert r.assess_pair("drug-a", "drug-b").surfaced


def test_caches_are_bounded():
    fetch, _ = fake_openfda({"": 1}, [])
    c = OpenFdaCounts(fetch=fetch, min_interval=0, max_items=3)
    for i in range(10):
        c.get(OpenFdaCounts.url(f"x{i}", limit=1))
    assert len(c._mem) == 3


def test_a_failed_faers_lookup_is_stated_in_the_report(faers_graph):
    from src.retrieval.faers_retriever import FaersAssessment

    class DownFaers:
        enabled = True

        def assess_pair(self, a, b):
            return FaersAssessment(tuple(sorted((a, b))), error="HTTPError")

    s = faers_graph(DownFaers()).run(["metformin", "levothyroxine"])
    assert "FAERS was not checked for 1 pair" in s["report"] and s["final_validation"]["passed"]
    assert s["retrieval"]["faers_failed"] == [["levothyroxine", "metformin"]]

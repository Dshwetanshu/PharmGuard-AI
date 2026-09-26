"""The structured report and the markdown report are the same report.

render_markdown(structure) + the footer must reproduce the finalized markdown exactly, and the
findings, notices, entries, unresolved inputs, no-data pairs and signals parsed back out of the
markdown must equal the structure's. Checked on every sample case, the FX fixture scenarios
and a FAERS case.
"""
from __future__ import annotations

import re
from dataclasses import replace

import pytest

from src.agents.report_structure import plural, render_markdown
from src.evaluation.test_cases import TEST_CASES
from src.retrieval.faers_retriever import FaersRecord

FINDING = re.compile(r"^- \*\*(.+?) \+ (.+?)\*\* — curated severity: (Major|Moderate|Minor|not graded) \((.+?)\).*"
                     r"\[([A-Za-z][A-Za-z0-9 _-]*):([A-Za-z0-9._-]+)\]$")


def parse(md: str):
    out = {"findings": [], "notices": [], "entries": [], "unresolved": [], "no_data": [], "signals": [], "faers": []}
    section = None
    for line in md.splitlines():
        if line.startswith("## ") or line.startswith("### "):
            section = line.lstrip("# ").strip()
            continue
        if line.startswith("> "):
            out["notices"].append(line[2:])
        if not line.startswith("- "):
            continue
        if section == "How your entries were read":
            out["entries"].append(line[2:])
        elif section == "Unresolved Inputs":
            out["unresolved"].append(line[2:])
        elif section == "No Curated Interaction Data":
            out["no_data"].append(line[2:])
        elif section and section.startswith("Statistical reporting signals"):
            out["signals"].append(line[2:])
        elif section and section.startswith("FAERS"):
            out["faers"].append(line[2:])
        else:
            m = FINDING.match(line)
            if m:
                out["findings"].append((m.group(1), m.group(2), m.group(3), f"{m.group(5)}:{m.group(6)}"))
    return out


def from_structure(s):
    f = [(x["pair"][0], x["pair"][1], x["severity"], x["citation"]["text"])
         for x in s["findings"] + s["ungraded"]["items"]]
    sig = [x["line"] for x in s["signals"]["items"]] + [h["line"] for h in s["signals"]["hidden"]]
    cov = s["coverage"]
    return {"findings": sorted(f), "notices": [n["text"] for n in s["entries"]["notices"]],
            "entries": [e["line"] for e in s["entries"]["items"]],
            "unresolved": [u["line"] for u in (cov["unresolved"] or {"items": []})["items"]],
            "no_data": [f"{a} + {b}" for a, b in (cov["no_data"] or {"pairs": []})["pairs"]],
            "signals": sorted(sig), "faers": [x["line"] for x in (s["faers"] or {"items": []})["items"]]}


def _check(state, generator):
    s = state["report_structure"]
    assert s is not None and s["version"] == 2
    md = state["report"]
    assert generator.finalize("\n".join(render_markdown(s))) == md          # the markdown is the structure
    p = parse(md)
    p["findings"], p["signals"] = sorted(p["findings"]), sorted(p["signals"])
    assert p == from_structure(s)
    assert s["disclaimer"] in md and s["data_line"] in md
    assert s["summary"]["graded"]["Major"] == sum(1 for x in s["findings"] if x["severity"] == "Major")
    assert grid_from_markdown(p, s["grid"]["drugs"]) == grid_cells(s)


RANK = ("Major", "Moderate", "Minor", "not graded")


def grid_from_markdown(p, drugs):
    """Each pair's status as read back from the markdown alone: the most severe finding,
    else a statistical signal, else a listed no-data pair."""
    out = {}
    for i in range(len(drugs)):
        for j in range(i):
            key = frozenset((drugs[i], drugs[j]))
            sev = [f[2] for f in p["findings"] if frozenset((f[0].lower(), f[1].lower())) == key]
            if sev:
                status = min(sev, key=RANK.index)
            elif any(frozenset(x.lower() for x in re.match(r"\*\*(.+?) \+ (.+?)\*\*", line).groups()) == key
                     for line in p["signals"]):
                status = "signals only"
            else:
                assert any(frozenset(x.split(" + ")) == key for x in p["no_data"]), key
                status = "no curated data"
            out[key] = status
    return out


def grid_cells(s):
    """The structure's grid, checked for shape: the lower triangle, each pair once, links to the right item."""
    g = s["grid"]
    drugs, cells = g["drugs"], g["cells"]
    assert len(cells) == len(drugs) * (len(drugs) - 1) // 2 == s["summary"]["pairs"]
    assert s["summary"]["medications"] == len(drugs)
    out = {}
    for c in cells:
        assert c["row"] > c["col"] and c["pair"] == [drugs[c["row"]], drugs[c["col"]]]
        key = frozenset(c["pair"])
        assert key not in out
        out[key] = c["status"]
        if c["ref"] is None:
            assert c["status"] == "no curated data"
        else:
            items = {"findings": s["findings"], "ungraded": s["ungraded"]["items"], "signals": s["signals"]["items"]}
            item = items[c["ref"]["section"]][c["ref"]["index"]]
            assert frozenset(x.lower() for x in item["pair"]) == key
    return out


@pytest.fixture(scope="module")
def graph(test_data_dir, sample_ingest_report):
    from src.graph import PharmGuardGraph, Settings
    return PharmGuardGraph(Settings(data_dir=test_data_dir, mode="deterministic"))


@pytest.mark.parametrize("case", TEST_CASES, ids=[c.case_id for c in TEST_CASES])
def test_structure_matches_markdown_for_every_case(graph, case):
    _check(graph.run(case.input_drugs), graph.components.generator)


def test_structure_matches_markdown_with_faers_signals_and_duplicates(graph):
    from src.graph import PharmGuardGraph

    class StubFaers:
        enabled = True

        def retrieve_pair(self, a, b):
            return [FaersRecord("FAERS-abc123", a, b, "nausea", 1, "Major")]

    g = PharmGuardGraph(replace(graph.settings, faers_enabled=True), replace(graph.components, faers=StubFaers()))
    s = g.run(["metformin", "levothyroxine", "Coumadin", "warfarin", "xyz123"])
    assert s["report_structure"]["faers"]["items"] and s["report_structure"]["entries"]["notices"]
    assert "1 report [FAERS:FAERS-abc123]" in s["report"]          # singular, no "(s)"
    _check(s, g.components.generator)


def test_structure_matches_markdown_on_checker_fixtures():
    from src.agents.generator import Generator
    from src.evaluation.checker_fixtures import CFG, PROVENANCE, SCENARIOS, build
    gen = Generator(CFG, provenance=PROVENANCE)
    for sc in SCENARIOS:                       # includes statistical signals and a hidden count
        plan, result = build(sc)
        md, structure = gen.deterministic_report(plan, result)
        _check({"report": md, "report_structure": structure}, gen)


def test_llm_reports_have_no_structure(test_data_dir, sample_ingest_report):
    from src.graph import PharmGuardGraph, Settings, build_components
    settings = Settings(data_dir=test_data_dir, mode="llm", llm_configured=True)

    class FakeLLM:
        last_usage = None

        def __init__(self, text):
            self.text = text

        def complete(self, system, messages, **kw):
            return self.text

    det = PharmGuardGraph(replace(settings, mode="deterministic")).run(["lisinopril", "spironolactone"])
    body = det["report"].split("\n---\n")[0]
    g = PharmGuardGraph(settings, build_components(settings, llm=FakeLLM(body)))
    s = g.run(["lisinopril", "spironolactone"])
    assert s["report_source"] == "llm" and s.get("report_structure") is None


def test_plurals():
    assert plural(1, "medication") == "1 medication" and plural(4, "medication") == "4 medications"
    assert plural(0, "listing") == "0 listings" and plural(1, "unique pair") == "1 unique pair"

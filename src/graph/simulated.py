"""A scripted, SIMULATED LLM for demos without an API key (demo.py --simulate-retry).

Not a model: it returns two fixed drafts built from the deterministic template.
Draft 1 adds a fabricated "via CYP3A4 inhibition" mechanism to the first finding
(which the checker rejects); draft 2 is the clean template text (which passes).
It exists only to make the retry path visible in a trace. Runs using it are
labelled "simulated LLM" in trace tags and metadata.
"""
from __future__ import annotations

from dataclasses import replace
from typing import List, Optional

from src.agents.generator import STATISTICAL_HEADING

SIMULATED_LABEL = "simulated LLM"
FABRICATION = " via CYP3A4 inhibition"
FINDING_HEADINGS = ("## Major Findings", "## Moderate Findings", "## Minor Findings", "## Severity Not Graded",
                    f"## {STATISTICAL_HEADING}")   # claim sections: curated findings and statistical signals


def inject_cyp3a4(report: str) -> Optional[str]:
    """Insert the fabrication before the citation of the first finding line, or None."""
    lines, in_findings = report.splitlines(), False
    for i, line in enumerate(lines):
        if line.startswith("## "):
            in_findings = line in FINDING_HEADINGS
        elif in_findings and line.startswith("- ") and " [" in line and "CYP3A4" not in line:
            j = line.find(" [")
            lines[i] = line[:j] + FABRICATION + line[j:]
            return "\n".join(lines)
    return None


class ScriptedLLM:
    """Returns the given drafts in order. last_usage stays None (no tokens are used)."""

    def __init__(self, drafts: List[str]):
        self.drafts, self.calls, self.last_usage = list(drafts), [], None

    def complete(self, system, messages, **kwargs):
        self.calls.append(messages)
        return self.drafts.pop(0)


def simulated_retry_graph(graph, drug_names: List[str]):
    """An LLM-mode copy of `graph` whose LLM is the scripted two-draft simulator.
    Raises ValueError if the drugs have no interaction record to fabricate on."""
    from src.agents.generator import Generator
    from src.graph.builder import PharmGuardGraph
    from src.observability import Tracing, suppress_tracing

    # Build the drafts from a deterministic run that produces no trace data at all
    # (the OTel instrumentors are process-wide, so a no-op backend alone isn't enough).
    helper = PharmGuardGraph(graph.settings.with_mode("deterministic"), graph.components, Tracing())
    with suppress_tracing():
        clean = helper.run(drug_names)["report"].split("\n---\n")[0]
    bad = inject_cyp3a4(clean)
    if bad is None:
        raise ValueError("--simulate-retry needs at least one interaction finding; try e.g. "
                         "lisinopril spironolactone aspirin")
    c = graph.components
    components = replace(c, generator=Generator(c.generator.cfg, llm=ScriptedLLM([bad, clean]),
                                                provenance=c.generator.provenance),
                         llm_available=True, llm_label=SIMULATED_LABEL)
    return PharmGuardGraph(graph.settings.with_mode("llm"), components, graph.tracing)

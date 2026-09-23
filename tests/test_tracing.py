"""Optional tracing: off by default, fails soft, one span per node, redaction, no effect on reports.

Offline: spans go to an in-memory OpenTelemetry exporter; LangSmith payloads are
captured from the client's HTTP session. Skipped if requirements-tracing.txt
isn't installed.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import replace

import pytest

pytest.importorskip("phoenix.otel")
pytest.importorskip("openinference.instrumentation.langchain")
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter  # noqa: E402

from src.agents.generator import Generator  # noqa: E402
from src.graph import PharmGuardGraph, Settings, build_components  # noqa: E402
from src.graph.simulated import SIMULATED_LABEL, simulated_retry_graph  # noqa: E402
from src.observability import Tracing, setup_tracing, teardown_tracing  # noqa: E402

DRUGS = ["lisinopril", "spironolactone", "aspirin"]
NAMES = ("lisinopril", "spironolactone", "aspirin", "hyperkalemia")


@pytest.fixture(scope="module")
def base(test_data_dir, sample_ingest_report):
    s = Settings(data_dir=test_data_dir, mode="deterministic")
    return s, build_components(s)


@pytest.fixture(scope="module")
def otel():
    exporter, tp = InMemorySpanExporter(), TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(exporter))
    yield tp, exporter
    teardown_tracing()


@pytest.fixture
def traced(base, otel):
    """Build a Phoenix-traced graph over the in-memory exporter."""
    settings, components = base
    tp, exporter = otel

    def make(redact=True, **overrides):
        exporter.clear()
        s = replace(settings, tracing="phoenix", trace_redact=redact, **overrides)
        tracing = setup_tracing(s, tracer_provider=tp)
        assert tracing.backend == "phoenix"
        return PharmGuardGraph(s, components, tracing), exporter

    yield make
    teardown_tracing()


def _spans(exporter):
    spans = exporter.get_finished_spans()
    return spans, {sp.context.span_id: sp for sp in spans}


def _all_text(spans) -> str:
    return json.dumps([{**dict(sp.attributes), "name": sp.name} for sp in spans], default=str).lower()


# ------------------------------------------------------------ off & fail-soft

def test_tracing_is_off_by_default(monkeypatch, caplog):
    monkeypatch.delenv("PHARMGUARD_TRACING", raising=False)
    s = Settings.from_env()
    assert (s.tracing, s.trace_redact) == ("none", True)
    with caplog.at_level(logging.WARNING, logger="pharmguard.tracing"):
        assert setup_tracing(s).backend == "none"
    assert caplog.records == []


def test_unknown_backend_warns_once(monkeypatch, caplog):
    monkeypatch.setenv("PHARMGUARD_TRACING", "datadog")
    with caplog.at_level(logging.WARNING, logger="pharmguard.tracing"):
        assert Settings.from_env().tracing == "none"
    assert len(caplog.records) == 1


@pytest.mark.parametrize("case", ["phoenix_missing_packages", "phoenix_unreachable",
                                  "langsmith_no_key", "langsmith_missing_packages"])
def test_fail_soft(case, base, monkeypatch, caplog):
    settings, components = base
    backend = case.split("_")[0]
    s = replace(settings, tracing=backend, langsmith_key_present=False,
                phoenix_endpoint="http://127.0.0.1:9")   # unreachable (and sockets are blocked in tests)
    with caplog.at_level(logging.WARNING, logger="pharmguard.tracing"), monkeypatch.context() as m:
        # Hide the package only during setup: langchain_core itself needs langsmith at run time.
        if case == "phoenix_missing_packages":
            m.setitem(sys.modules, "phoenix.otel", None)
        if case == "langsmith_missing_packages":
            m.setitem(sys.modules, "langsmith", None)
        tracing = setup_tracing(s)
    assert tracing.backend == "none" and len(caplog.records) == 1
    state = PharmGuardGraph(s, components, tracing).run(DRUGS)
    assert state["report_source"] == "deterministic"
    teardown_tracing()


def test_langsmith_env_flag_alone_does_not_trace(base, monkeypatch):
    """LANGSMITH_TRACING=true without PHARMGUARD_TRACING=langsmith must not send anything."""
    from langchain_core import tracers

    created = []
    monkeypatch.setattr(tracers.LangChainTracer, "__init__",
                        lambda self, *a, **k: created.append(1) or (_ for _ in ()).throw(AssertionError("traced")))
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "not-a-real-key")
    settings, components = base
    state = PharmGuardGraph(settings, components, Tracing()).run(DRUGS)
    assert state["report_source"] == "deterministic" and created == []


# ------------------------------------------------------------------- Phoenix

def test_one_span_per_node_with_attributes(traced):
    graph, exporter = traced()
    state = graph.run(DRUGS)
    spans, by_id = _spans(exporter)
    executed = [t["node"] for t in state["trajectory"]]
    node_spans = [sp for sp in spans if sp.name in executed]
    assert sorted(sp.name for sp in node_spans) == sorted(executed)          # exactly one per node
    for sp in node_spans:
        assert sp.attributes["openinference.span.kind"] == "CHAIN"
        assert "pharmguard.status" in sp.attributes and "pharmguard.ms" in sp.attributes
    root = next(sp for sp in spans if sp.name == "pharmguard.request")
    meta = json.loads(root.attributes["metadata"])
    assert meta["request_id"] == state["request_id"] and meta["n_drugs"] == 3
    assert meta["data_provenance"].startswith("Data: synthetic sample dataset")
    assert meta["report_source"] == "deterministic" and root.attributes["pharmguard.report_source"] == "deterministic"
    assert {"mode:deterministic", "pipeline:langgraph"} <= set(root.attributes["tag.tags"])
    graph_span = next(sp for sp in spans if sp.name == "pharmguard_graph")
    assert by_id[graph_span.parent.span_id].name == "pharmguard.request"


def test_fallback_and_findings_are_filterable(traced, base):
    graph, exporter = traced()
    bad = graph.with_mode("deterministic").run(DRUGS)["report"].split("\n---\n")[0].replace(
        "hyperkalemia (PRR=14.20)", "hyperkalemia via CYP3A4 inhibition (PRR=14.20)")

    class Bad:
        last_usage = None

        def complete(self, system, messages, **kw):
            return bad

    exporter.clear()   # drop the spans of the deterministic run used to build the bad draft
    c = replace(base[1], generator=Generator(base[1].generator.cfg, llm=Bad()), llm_available=True)
    state = PharmGuardGraph(graph.settings.with_mode("llm"), c, graph.tracing).run(DRUGS)
    assert state["report_source"] == "deterministic_fallback"
    spans, _ = _spans(exporter)
    root = next(sp for sp in spans if sp.name == "pharmguard.request")
    assert root.attributes["pharmguard.fallback_reason"] == "validation_failed"
    assert json.loads(root.attributes["pharmguard.finding_codes"]) == ["UNSUPPORTED_MECHANISM"]
    validates = [sp for sp in spans if sp.name == "validate"]
    assert len(validates) == 2
    assert all(json.loads(sp.attributes["pharmguard.finding_codes"]) == ["UNSUPPORTED_MECHANISM"] for sp in validates)


def test_rxnorm_http_call_is_a_child_span_of_normalize(traced, monkeypatch):
    from src.data import rxnorm_api

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"approximateGroup": {"candidate": []}}'

    monkeypatch.setattr(rxnorm_api.urllib_request, "urlopen", lambda req, timeout=None: Resp())
    graph, exporter = traced(rxnorm_enabled=True)
    graph = PharmGuardGraph(graph.settings, build_components(graph.settings), graph.tracing)
    graph.run(["lisinopril", "notarealdrugqq"])
    spans, by_id = _spans(exporter)
    http = [sp for sp in spans if sp.name == "rxnorm.http"]
    assert http and all(by_id[sp.parent.span_id].name == "normalize" for sp in http)
    assert http[0].attributes["url.path"] == "/REST/approximateTerm.json"
    assert http[0].attributes["http.response.status_code"] == 200
    assert "url.query" not in http[0].attributes            # the query contains the drug name


def test_redaction_hides_drug_names(traced):
    graph, exporter = traced(redact=True)
    graph.run(DRUGS)
    text = _all_text(exporter.get_finished_spans())
    assert not [n for n in NAMES if n in text]
    assert "__redacted__" in text                            # OpenInference masking is active

    graph, exporter = traced(redact=False)
    graph.run(DRUGS)
    text = _all_text(exporter.get_finished_spans())
    assert all(n in text for n in NAMES)                     # visible when redaction is off


def test_reports_are_byte_identical_with_tracing_on_and_off(traced, base):
    settings, components = base
    plain = PharmGuardGraph(settings, components, Tracing())
    for redact in (True, False):
        graph, _ = traced(redact=redact)
        for drugs in (DRUGS, ["metformin"], ["warfarin", "digoxin", "amiodarone", "atorvastatin", "lisinopril"]):
            assert graph.run(drugs)["report"] == plain.run(drugs)["report"]


def test_simulated_retry_is_labelled(traced):
    graph, exporter = traced()
    state = simulated_retry_graph(graph, DRUGS).run(DRUGS)
    assert state["report_source"] == "llm_retry" and state["llm_attempts"] == 2
    spans, _ = _spans(exporter)
    root = [sp for sp in spans if sp.name == "pharmguard.request"][-1]
    assert json.loads(root.attributes["metadata"])["llm"] == SIMULATED_LABEL
    assert f"llm:{SIMULATED_LABEL}" in root.attributes["tag.tags"]
    assert [sp.attributes["pharmguard.status"] for sp in spans if sp.name == "validate"] == ["fail", "pass"]


# ----------------------------------------------------------------- LangSmith

def test_langsmith_payloads_are_redacted(base, monkeypatch):
    """Capture what the LangSmith client would POST; no network."""
    from langsmith import Client

    import src.observability.tracing as tr

    settings, components = base
    sent = []

    class Resp:
        status_code, text, headers = 200, "{}", {}

        def json(self):
            return {}

        def raise_for_status(self):
            pass

    client = Client(api_key="test-not-real", api_url="http://langsmith.invalid", auto_batch_tracing=False,
                    hide_inputs=True, hide_outputs=True)
    monkeypatch.setattr(client.session, "request", lambda method, url, **kw: sent.append(kw) or Resp())
    tracing = tr.LangSmithTracing(client, redact=True, project="pharmguard-test")
    state = PharmGuardGraph(replace(settings, tracing="langsmith"), components, tracing).run(DRUGS)
    tracing.flush()
    from langchain_core.tracers.langchain import wait_for_all_tracers
    wait_for_all_tracers()
    bodies = " ".join((kw.get("data") or b"").decode("utf-8", "ignore") if isinstance(kw.get("data"), bytes)
                      else str(kw.get("data") or kw.get("json") or "") for kw in sent).lower()
    assert sent, "expected the client to send runs"
    assert not [n for n in NAMES if n in bodies]
    assert "pharmguard.request" in bodies and state["request_id"] in bodies
    assert "deterministic" in bodies                         # report_source in metadata


def test_anthropic_call_gets_an_llm_span_with_tokens_and_no_prompt(traced, monkeypatch):
    """The Anthropic SDK call (fake client, no network) is traced by PharmGuard's own LLM span
    because the OpenInference Anthropic instrumentor can't load against anthropic 1.x."""
    from types import SimpleNamespace

    from src.config import Config
    from src.llm import LLMClient

    graph, exporter = traced(redact=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-real")
    cfg = Config()
    cfg.llm.provider = "anthropic"
    client = LLMClient(cfg)

    class Msgs:
        def create(self, **kw):
            return SimpleNamespace(stop_reason="end_turn", usage=SimpleNamespace(input_tokens=900, output_tokens=120),
                                   content=[SimpleNamespace(type="text", text="lisinopril report")])

    client._client = SimpleNamespace(messages=Msgs())
    assert client.complete("sys", [{"role": "user", "content": "lisinopril + spironolactone"}]) == "lisinopril report"
    span = next(sp for sp in exporter.get_finished_spans() if sp.name == "llm.anthropic")
    a = span.attributes
    assert (a["openinference.span.kind"], a["llm.model_name"]) == ("LLM", "claude-sonnet-5")
    assert (a["llm.token_count.prompt"], a["llm.token_count.completion"], a["llm.token_count.total"]) == (900, 120, 1020)
    assert "lisinopril" not in _all_text([span])

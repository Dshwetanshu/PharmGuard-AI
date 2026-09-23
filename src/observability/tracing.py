"""Optional tracing for the PharmGuard graph: none (default), LangSmith or Phoenix.

Rules:
- One switch: Settings.tracing (PHARMGUARD_TRACING), read only in Settings.from_env().
- Fail soft: unknown backend, missing packages, missing credentials or an
  unreachable collector log ONE warning and the run continues untraced.
- Tracing never changes a report. Every tracing call is wrapped so its own
  errors are logged, never raised into the pipeline.
- Redaction (Settings.trace_redact, default on) uses each backend's built-in
  masking: OpenInference TraceConfig(hide_inputs, hide_outputs, hide_input_messages, ...)
  for Phoenix; langsmith.Client(hide_inputs=True, hide_outputs=True) for LangSmith.
  Our own attributes are limited to names, timings, statuses, counts and finding codes.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import socket
import uuid
from typing import Any, Callable, Dict, Iterator, List, Optional
from urllib.parse import urlparse

log = logging.getLogger("pharmguard.tracing")
_SUPPRESSED: contextvars.ContextVar = contextvars.ContextVar("pharmguard_tracing_suppressed", default=False)


@contextlib.contextmanager
def suppress_tracing() -> Iterator[None]:
    """Run a block without producing any trace data (our spans and OTel instrumentors)."""
    token = _SUPPRESSED.set(True)
    otel_token = None
    try:
        from opentelemetry import context as otel_context
        otel_token = otel_context.attach(otel_context.set_value(otel_context._SUPPRESS_INSTRUMENTATION_KEY, True))
    except Exception:
        pass
    try:
        with _langsmith_disabled():
            yield
    finally:
        if otel_token is not None:
            _safe(otel_context.detach, otel_token)
        _SUPPRESSED.reset(token)


def _langsmith_disabled():
    try:
        from langsmith import tracing_context
        return tracing_context(enabled=False)
    except Exception:
        return contextlib.nullcontext()

# Node-detail keys that are safe to record on spans even with redaction on
# (no drug names, no report text).
SAFE_DETAIL_KEYS = {
    "route", "attempt", "passed", "finding_codes", "findings", "error_class", "retryable",
    "with_feedback", "unique_drugs", "pairs", "expected_pairs", "patched", "pairs_with_records",
    "no_data_pairs", "records", "faers_consulted", "consulted_pairs", "pairs_with_signals", "reason",
    "report_source", "final_validation_passed", "resolved", "unresolved", "rxnorm_enabled", "model",
    "llm_attempts",
}


def _safe(fn: Callable, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # tracing must never break a run
        log.debug("tracing call failed: %s", exc)
        return None


def safe_node_attributes(detail: Dict[str, Any], redact: bool) -> Dict[str, Any]:
    out = {k: v for k, v in detail.items() if k in SAFE_DETAIL_KEYS}
    if "inputs" in detail:  # normalizer: counts per method, never the inputs themselves
        methods: Dict[str, int] = {}
        for i in detail["inputs"]:
            methods[i["method"]] = methods.get(i["method"], 0) + 1
        out["normalizer_methods"] = methods
    if "usage" in detail and detail["usage"]:
        out["usage"] = detail["usage"]
    if not redact:
        out["detail"] = detail
    return out


class Tracing:
    """No-op tracing (backend "none"). Subclasses implement the hooks."""

    backend = "none"

    def __init__(self, redact: bool = True, project: str = "pharmguard"):
        self.redact = redact
        self.project = project

    # -- per request (root run) -------------------------------------------
    @contextlib.contextmanager
    def request(self, run_name: str, tags: List[str], metadata: Dict[str, Any],
                inputs: Dict[str, Any]) -> Iterator["RequestHandle"]:
        # Block LangChain's env-driven auto tracing (LANGSMITH_TRACING=true) when this
        # backend isn't LangSmith, so nothing is sent to a hosted service by accident.
        with _langsmith_disabled():
            yield RequestHandle()

    def graph_config(self) -> Dict[str, Any]:
        return {}

    # -- per node ---------------------------------------------------------
    @contextlib.contextmanager
    def node(self, name: str) -> Iterator[Callable[[Dict[str, Any]], None]]:
        yield lambda attrs: None

    # -- HTTP child spans (RxNorm, FAERS) ---------------------------------
    @contextlib.contextmanager
    def http(self, name: str, url: str) -> Iterator[Callable[[Dict[str, Any]], None]]:
        yield lambda attrs: None

    # -- LLM SDK call (only where no SDK instrumentor/wrapper covers it) ---
    @contextlib.contextmanager
    def llm(self, provider: str, model: str, messages: List[Dict[str, Any]]) -> Iterator[Callable[..., None]]:
        yield lambda usage=None, output=None: None

    def wrap_llm_sdk(self, sdk_client: Any, provider: str) -> Any:
        return sdk_client

    def flush(self) -> None:
        pass


class RequestHandle:
    def finish(self, outcome: Dict[str, Any], outputs: Optional[Dict[str, Any]] = None) -> None:
        pass


# ------------------------------------------------------------------ Phoenix
class _PhoenixRequest(RequestHandle):
    def __init__(self, span, metadata: Dict[str, Any], redact: bool):
        self.span, self.metadata, self.redact = span, dict(metadata), redact

    def finish(self, outcome, outputs=None):
        def _do():
            self.metadata.update(outcome)
            self.span.set_attribute("metadata", json.dumps(self.metadata, sort_keys=True))
            for k, v in outcome.items():
                self.span.set_attribute(f"pharmguard.{k}", v if isinstance(v, (str, int, float, bool)) else json.dumps(v))
            if outputs and not self.redact:
                self.span.set_attribute("output.value", json.dumps(outputs))
        _safe(_do)


class PhoenixTracing(Tracing):
    backend = "phoenix"

    def __init__(self, tracer_provider, redact: bool = True, project: str = "pharmguard"):
        super().__init__(redact, project)
        from openinference.instrumentation import TraceConfig
        from openinference.instrumentation.langchain import LangChainInstrumentor

        self.tracer_provider = tracer_provider
        self.tracer = tracer_provider.get_tracer("pharmguard")
        config = TraceConfig(
            hide_inputs=redact, hide_outputs=redact, hide_input_messages=redact, hide_output_messages=redact,
            hide_input_text=redact, hide_output_text=redact, hide_prompts=redact, hide_choices=redact,
        )
        self._instrumentors = []
        self.instrumented_sdks = set()
        inst = LangChainInstrumentor()   # required: LangGraph node spans
        self._attach(inst, tracer_provider, config)
        for sdk, mod, cls in (("anthropic", "openinference.instrumentation.anthropic", "AnthropicInstrumentor"),
                              ("openai", "openinference.instrumentation.openai", "OpenAIInstrumentor")):
            # Optional and independent: a broken SDK instrumentor must not disable tracing.
            # (openinference-instrumentation-anthropic 2.1.5 imports anthropic._utils._transform,
            # which anthropic 1.x no longer has; those calls get PharmGuard's own LLM span.)
            try:
                self._attach(getattr(__import__(mod, fromlist=[cls]), cls)(), tracer_provider, config)
                self.instrumented_sdks.add(sdk)
            except Exception as exc:
                log.info("%s unavailable (%s); %s calls are recorded with PharmGuard's own LLM span",
                         cls, exc, sdk)

    def _attach(self, inst, tracer_provider, config) -> None:
        if inst.is_instrumented_by_opentelemetry:  # re-instrument so a new redaction config takes effect
            inst.uninstrument()
        inst.instrument(tracer_provider=tracer_provider, config=config)
        self._instrumentors.append(inst)

    def uninstrument(self) -> None:
        for inst in self._instrumentors:
            _safe(inst.uninstrument)

    @contextlib.contextmanager
    def request(self, run_name, tags, metadata, inputs):
        from openinference.instrumentation import using_attributes
        from opentelemetry import trace as trace_api

        if _SUPPRESSED.get():
            with super().request(run_name, tags, metadata, inputs) as h:
                yield h
            return
        span = None
        try:
            span = self.tracer.start_span(run_name, attributes={
                "openinference.span.kind": "CHAIN", "tag.tags": list(tags),
                "metadata": json.dumps(metadata, sort_keys=True), "session.id": metadata.get("request_id", ""),
                **({} if self.redact else {"input.value": json.dumps(inputs)}),
            })
        except Exception as exc:
            log.debug("could not start request span: %s", exc)
        if span is None:
            with super().request(run_name, tags, metadata, inputs) as h:
                yield h
            return
        with super().request(run_name, tags, metadata, inputs):  # also blocks LangSmith auto-tracing
            with trace_api.use_span(span, end_on_exit=True), \
                    using_attributes(session_id=metadata.get("request_id"), tags=list(tags), metadata=metadata):
                yield _PhoenixRequest(span, metadata, self.redact)

    @contextlib.contextmanager
    def node(self, name):
        from opentelemetry import trace as trace_api
        try:
            from openinference.instrumentation.langchain import get_current_span
            span = get_current_span()
        except Exception:
            span = None
        if span is None:
            yield lambda attrs: None
            return

        def record(attrs: Dict[str, Any]) -> None:
            for k, v in attrs.items():
                _safe(span.set_attribute, f"pharmguard.{k}",
                      v if isinstance(v, (str, int, float, bool)) else json.dumps(v, sort_keys=True))

        # Make the instrumentor's node span current so HTTP child spans nest under it.
        with trace_api.use_span(span, end_on_exit=False):
            yield record

    @contextlib.contextmanager
    def http(self, name, url):
        if _SUPPRESSED.get():
            yield lambda a: None
            return
        u = urlparse(url)
        attrs = {"openinference.span.kind": "TOOL", "http.request.method": "GET",
                 "server.address": u.hostname or "", "url.path": u.path}
        if not self.redact:
            attrs["url.query"] = u.query
        span_cm = _safe(self.tracer.start_as_current_span, name, attributes=attrs)
        if span_cm is None:
            yield lambda a: None
            return
        with span_cm as span:
            yield lambda a: [_safe(span.set_attribute, k, v) for k, v in a.items()]

    @contextlib.contextmanager
    def llm(self, provider, model, messages):
        if provider in self.instrumented_sdks or _SUPPRESSED.get():
            yield lambda usage=None, output=None: None
            return
        attrs = {"openinference.span.kind": "LLM", "llm.provider": provider, "llm.system": provider,
                 "llm.model_name": model}
        if not self.redact:
            attrs["input.value"] = json.dumps(messages)
        span_cm = _safe(self.tracer.start_as_current_span, f"llm.{provider}", attributes=attrs)
        if span_cm is None:
            yield lambda usage=None, output=None: None
            return

        with span_cm as span:
            def record(usage=None, output=None):
                if usage:
                    _safe(span.set_attribute, "llm.token_count.prompt", usage.get("input_tokens", 0))
                    _safe(span.set_attribute, "llm.token_count.completion", usage.get("output_tokens", 0))
                    _safe(span.set_attribute, "llm.token_count.total",
                          usage.get("input_tokens", 0) + usage.get("output_tokens", 0))
                if output is not None and not self.redact:
                    _safe(span.set_attribute, "output.value", output)
            yield record

    def flush(self):
        _safe(self.tracer_provider.force_flush)


# ---------------------------------------------------------------- LangSmith
class _LangSmithRequest(RequestHandle):
    def __init__(self, run_tree):
        self.rt = run_tree

    def finish(self, outcome, outputs=None):
        def _do():
            self.rt.metadata.update(outcome)
            self.rt.add_tags([f"report_source:{outcome.get('report_source')}"]
                             + [f"finding:{c}" for c in outcome.get("finding_codes", [])])
            self.rt.end(outputs=outputs or {"report_source": outcome.get("report_source")})
        _safe(_do)


class LangSmithTracing(Tracing):
    backend = "langsmith"

    def __init__(self, client, redact: bool = True, project: str = "pharmguard"):
        super().__init__(redact, project)
        self.client = client

    @contextlib.contextmanager
    def request(self, run_name, tags, metadata, inputs):
        from langsmith import trace, tracing_context
        if _SUPPRESSED.get():
            with super().request(run_name, tags, metadata, inputs) as h:
                yield h
            return
        try:
            cm = trace(run_name, run_type="chain", inputs=inputs, tags=list(tags), metadata=metadata,
                       client=self.client, project_name=self.project)
        except Exception as exc:
            log.debug("could not start LangSmith run: %s", exc)
            cm = None
        if cm is None:
            with super().request(run_name, tags, metadata, inputs) as h:
                yield h
            return
        with tracing_context(enabled=True, client=self.client, project_name=self.project), cm as rt:
            yield _LangSmithRequest(rt)

    def graph_config(self):
        from langchain_core.tracers import LangChainTracer
        # An explicit tracer so the redacting client is used for the LangGraph runs.
        tracer = _safe(LangChainTracer, client=self.client, project_name=self.project)
        return {"callbacks": [tracer]} if tracer else {}

    @contextlib.contextmanager
    def node(self, name):
        try:
            from langsmith.run_helpers import get_current_run_tree
            rt = get_current_run_tree()
        except Exception:
            rt = None
        yield (lambda attrs: _safe(rt.metadata.update, {f"pharmguard.{k}": v for k, v in attrs.items()})) \
            if rt is not None else (lambda attrs: None)

    @contextlib.contextmanager
    def http(self, name, url):
        from langsmith import trace
        if _SUPPRESSED.get():
            yield lambda a: None
            return
        u = urlparse(url)
        inputs = {"server": u.hostname, "path": u.path, **({} if self.redact else {"query": u.query})}
        cm = _safe(trace, name, run_type="tool", inputs=inputs, client=self.client, project_name=self.project)
        if cm is None:
            yield lambda a: None
            return
        with cm as rt:
            yield lambda a: _safe(rt.metadata.update, a)

    def wrap_llm_sdk(self, sdk_client, provider):
        from langsmith import wrappers
        wrap = {"anthropic": getattr(wrappers, "wrap_anthropic", None),
                "openai": getattr(wrappers, "wrap_openai", None)}.get(provider)
        if wrap is None:
            return sdk_client
        wrapped = _safe(wrap, sdk_client, tracing_extra={"client": self.client, "tags": ["pharmguard"]})
        return wrapped or sdk_client

    def flush(self):
        _safe(self.client.flush)


# -------------------------------------------------------------------- setup
_ACTIVE: Tracing = Tracing()


def active() -> Tracing:
    """The process-wide tracing backend (used by the RxNorm/FAERS HTTP spans)."""
    return _ACTIVE


def _collector_reachable(endpoint: str, timeout: float = 0.5) -> bool:
    u = urlparse(endpoint)
    try:
        with socket.create_connection((u.hostname or "localhost", u.port or (443 if u.scheme == "https" else 80)),
                                      timeout=timeout):
            return True
    except Exception:
        return False


def setup_tracing(settings, tracer_provider=None) -> Tracing:
    """Build the configured backend, or fall back to no-op with one warning.

    tracer_provider: tests pass an OpenTelemetry provider with an in-memory
    exporter; otherwise Phoenix registers an OTLP exporter to settings.phoenix_endpoint.
    """
    global _ACTIVE
    backend = settings.tracing
    tracing: Tracing = Tracing(settings.trace_redact, settings.trace_project)
    if backend == "phoenix":
        tracing = _setup_phoenix(settings, tracer_provider) or tracing
    elif backend == "langsmith":
        tracing = _setup_langsmith(settings) or tracing
    _ACTIVE = tracing
    return tracing


def _setup_phoenix(settings, tracer_provider) -> Optional[Tracing]:
    try:
        import openinference.instrumentation.langchain  # noqa: F401
        from phoenix.otel import register
    except ImportError as exc:
        log.warning("PHARMGUARD_TRACING=phoenix but tracing packages are missing (%s); running untraced. "
                    "Install requirements-tracing.txt.", exc.name)
        return None
    if tracer_provider is None:
        if not _collector_reachable(settings.phoenix_endpoint):
            log.warning("Phoenix collector not reachable at %s; running untraced.", settings.phoenix_endpoint)
            return None
        try:
            # auto_instrument=False: instrumentors are attached below with an explicit
            # TraceConfig, because register(auto_instrument=True) only takes redaction
            # settings from OPENINFERENCE_* environment variables.
            tracer_provider = register(project_name=settings.trace_project, endpoint=_otlp_endpoint(settings),
                                       auto_instrument=False, set_global_tracer_provider=False, verbose=False)
        except Exception as exc:
            log.warning("Phoenix setup failed (%s); running untraced.", exc)
            return None
    try:
        return PhoenixTracing(tracer_provider, settings.trace_redact, settings.trace_project)
    except Exception as exc:
        log.warning("Phoenix instrumentation failed (%s); running untraced.", exc)
        return None


def _otlp_endpoint(settings) -> str:
    base = settings.phoenix_endpoint.rstrip("/")
    return base if base.endswith("/v1/traces") else f"{base}/v1/traces"


def _setup_langsmith(settings) -> Optional[Tracing]:
    try:
        from langchain_core.tracers import LangChainTracer  # noqa: F401
        from langsmith import Client
    except ImportError as exc:
        log.warning("PHARMGUARD_TRACING=langsmith but packages are missing (%s); running untraced.", exc.name)
        return None
    if not settings.langsmith_key_present:
        log.warning("PHARMGUARD_TRACING=langsmith but LANGSMITH_API_KEY is not set; running untraced.")
        return None
    try:
        client = Client(hide_inputs=settings.trace_redact, hide_outputs=settings.trace_redact)
    except Exception as exc:
        log.warning("LangSmith client setup failed (%s); running untraced.", exc)
        return None
    return LangSmithTracing(client, settings.trace_redact, settings.trace_project)


def teardown_tracing() -> None:
    """Uninstrument and return to no-op tracing (tests, reconfiguration)."""
    global _ACTIVE
    if isinstance(_ACTIVE, PhoenixTracing):
        _ACTIVE.uninstrument()
    _ACTIVE.flush()
    _ACTIVE = Tracing()


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]

"""Request handling for the PharmGuard API, independent of any web framework.

CheckService is built once at start-up: it verifies the data build, loads the
components and compiles the graphs (deterministic / LLM, each with and without
FAERS) a single time. check() validates a request, picks the mode, runs the
graph in a bounded worker pool with a timeout and assembles the response.
Errors are ServiceError(status, code, message); nothing else leaves this module
as an HTTP response, so no stack trace can reach a client.

Fail closed: if the build is missing, unverified, synthetic or not the required
profile, the service stays up, /health says why, and check() raises 503. It
never falls back to the synthetic sample.
"""
from __future__ import annotations

import contextvars
import hmac
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional

from api.bootstrap import BuildError, Downloader, ensure_build, hf_snapshot_download
from api.settings import ApiSettings
from src.config import Config
from src.data.attribution import notices_for_provenance
from src.data.provenance import data_stamp, read_provenance
from src.graph import Components, PharmGuardGraph, Settings, build_components, build_graph
from src.input_validation import InvalidDrugNameError, clean_drug_names
from src.observability import Tracing
from src.retrieval.faers_retriever import FaersRetriever

log = logging.getLogger("pharmguard.api")
MIN_DRUGS, MAX_DRUGS = 2, 12
MODES = ("auto", "llm", "deterministic")


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: Optional[Dict[str, str]] = None):
        super().__init__(message)
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}

    def body(self, request_id: str) -> Dict[str, Any]:
        return {"request_id": request_id, "error": {"code": self.code, "message": self.message}}


@dataclass(frozen=True)
class CheckRequest:
    drugs: List[str]
    mode: str = "deterministic"
    include_evidence: bool = False
    include_trajectory: bool = False
    faers: bool = False


def parse_request(body: Any) -> CheckRequest:
    """Validate a /v1/check body (already JSON-decoded). Raises ServiceError(422)."""
    if not isinstance(body, dict):
        raise ServiceError(422, "invalid_body", "request body must be a JSON object")
    drugs = body.get("drugs")
    if not isinstance(drugs, list) or not all(isinstance(d, str) for d in drugs):
        raise ServiceError(422, "invalid_drugs", "drugs must be a list of strings")
    if not MIN_DRUGS <= len(drugs) <= MAX_DRUGS:
        raise ServiceError(422, "invalid_drug_count",
                           f"send between {MIN_DRUGS} and {MAX_DRUGS} drug names (got {len(drugs)})")
    try:
        names = clean_drug_names(drugs)
    except InvalidDrugNameError as exc:
        raise ServiceError(422, "invalid_drug_name", str(exc)) from None
    mode = body.get("mode", "deterministic")
    if mode not in MODES:
        raise ServiceError(422, "invalid_mode", f"mode must be one of {list(MODES)}")
    flags = {}
    for key in ("include_evidence", "include_trajectory", "faers"):
        v = body.get(key, False)
        if not isinstance(v, bool):
            raise ServiceError(422, "invalid_flag", f"{key} must be true or false")
        flags[key] = v
    return CheckRequest(names, mode, **flags)


# ------------------------------------------------------------------ FAERS cap

_FAERS_BUDGET: contextvars.ContextVar = contextvars.ContextVar("pharmguard_faers_budget", default=None)


class FaersBudget:
    def __init__(self, max_pairs: int, budget_s: float):
        self.max_pairs, self.deadline = max_pairs, time.monotonic() + budget_s
        self.consulted = self.skipped = 0


class CappedFaers:
    """FAERS lookups limited per request to max_pairs and a time budget; pairs over the
    cap are skipped (counted in the response), never silently reported as checked."""
    enabled = True

    def __init__(self, inner: FaersRetriever):
        self.inner = inner

    def retrieve_pair(self, a: str, b: str):
        budget = _FAERS_BUDGET.get()
        if budget is None or budget.consulted >= budget.max_pairs or time.monotonic() >= budget.deadline:
            if budget is not None:
                budget.skipped += 1
            return []
        budget.consulted += 1
        return self.inner.retrieve_pair(a, b)


# ------------------------------------------------------------------ service

class CheckService:
    def __init__(self, settings: ApiSettings, graphs: Optional[Dict[tuple, PharmGuardGraph]] = None,
                 load_error: Optional[str] = None, provenance: Optional[dict] = None):
        self.settings = settings
        self.graphs = graphs or {}
        self.load_error = load_error
        self.provenance = provenance
        self.stamp = data_stamp(settings.processed_dir) if graphs else None
        self.notices = [n.__dict__ for n in notices_for_provenance(provenance)] if graphs else []
        self._pool = ThreadPoolExecutor(max_workers=settings.max_concurrency, thread_name_prefix="pharmguard")
        self._slots = threading.BoundedSemaphore(settings.max_concurrency)

    # ---- construction

    @classmethod
    def from_settings(cls, settings: ApiSettings, downloader: Downloader = hf_snapshot_download,
                      components: Optional[Components] = None) -> "CheckService":
        try:
            ensure_build(settings, downloader)
            prov = cls._check_build(settings)
            gs = settings.graph or Settings(data_dir=settings.data_dir, mode="deterministic")
            gs = replace(gs, data_dir=settings.data_dir, mode="deterministic", rxnorm_enabled=False,
                         faers_enabled=False, tracing="none")
            comps = components or build_components(gs)
            tracing = Tracing()   # tracing off in the API
            det = PharmGuardGraph(gs, comps, tracing)
            faers_comps = replace(comps, faers=CappedFaers(FaersRetriever(enabled=True,
                                                                           timeout_s=settings.faers_timeout_s)))
            det_f = PharmGuardGraph(replace(gs, faers_enabled=True), faers_comps, tracing)
            graphs = {("deterministic", False): det, ("llm", False): det.with_mode("llm"),
                      ("deterministic", True): det_f, ("llm", True): det_f.with_mode("llm")}
            return cls(settings, graphs, provenance=prov)
        except BuildError as exc:
            log.error("data build unavailable: %s", exc)
            return cls(settings, load_error=str(exc))
        except Exception as exc:   # unexpected: keep the reason generic on /health, details in the log
            log.exception("start-up failed")
            return cls(settings, load_error=f"start-up failed ({type(exc).__name__}); see server log")

    @staticmethod
    def _check_build(settings: ApiSettings) -> dict:
        prov = read_provenance(settings.processed_dir)
        if prov is None:
            raise BuildError(f"no build at {settings.processed_dir} (provenance.json missing)")
        profile = prov.get("profile") or ("sample" if prov.get("synthetic") else prov.get("mode"))
        if profile != settings.required_profile:
            raise BuildError(f"build profile is {profile!r}; this server requires {settings.required_profile!r}")
        if prov.get("synthetic") and settings.required_profile != "sample":
            raise BuildError("build is synthetic sample data")
        if prov.get("not_for_redistribution") and settings.required_profile != "research":
            raise BuildError("build is marked not for redistribution")
        for table in ("interactions.parquet", "drug_vocabulary.parquet"):
            if not (settings.processed_dir / table).exists():
                raise BuildError(f"{table} is missing from the build")
        return prov

    # ---- status

    @property
    def ready(self) -> bool:
        return bool(self.graphs) and self.load_error is None

    @property
    def llm_configured(self) -> bool:
        g = self.graphs.get(("llm", False))
        return bool(g and g.components.llm_available)

    def health(self) -> Dict[str, Any]:
        prov = self.provenance or {}
        return {
            "status": "ok" if self.ready else "unavailable",
            "data_loaded": self.ready,
            "reason": self.load_error,
            "required_profile": self.settings.required_profile,
            "profile": (self.stamp or {}).get("profile"),
            "provenance_sha256": (self.stamp or {}).get("provenance_sha256"),
            "data_line": (self.stamp or {}).get("data"),
            "records": {"interactions": prov.get("interaction_records"),
                        "side_effects": prov.get("side_effect_records"),
                        "vocabulary_aliases": (prov.get("vocabulary") or {}).get("rows")} if prov else None,
            "llm_configured": self.llm_configured,
            "llm_requires_api_key": True,
            "api_key_configured": bool(self.settings.api_key),
            "faers_available": self.settings.allow_faers,
            "disclaimer": Config().disclaimer,
            "attribution": self.notices,
        }

    def mermaid(self) -> str:
        g = self.graphs.get(("llm", False))
        if g is not None:
            return g.compiled.get_graph().draw_mermaid().strip()
        placeholders = Components(None, None, None, None, None, llm_available=False)
        return build_graph(Settings(data_dir=self.settings.data_dir), placeholders).get_graph().draw_mermaid().strip()

    # ---- /v1/check

    def resolve_mode(self, requested: str, api_key: Optional[str]) -> str:
        authorized = bool(self.settings.api_key) and api_key is not None and hmac.compare_digest(
            api_key.encode(), self.settings.api_key.encode())
        if requested == "deterministic":
            return "deterministic"
        if requested == "llm":
            if not authorized:
                raise ServiceError(401, "llm_requires_api_key", "LLM mode needs a valid X-API-Key header")
            if not self.llm_configured:
                raise ServiceError(503, "llm_not_configured", "no LLM provider key is configured on this server")
            return "llm"
        return "llm" if authorized and self.llm_configured else "deterministic"   # auto

    def check(self, body: Any, api_key: Optional[str], request_id: str) -> Dict[str, Any]:
        t0 = time.perf_counter()
        if not self.ready:
            raise ServiceError(503, "data_unavailable", f"the data build is not loaded: {self.load_error}")
        req = parse_request(body)
        mode = self.resolve_mode(req.mode, api_key)
        if req.faers and not self.settings.allow_faers:
            raise ServiceError(422, "faers_disabled", "FAERS lookups are disabled on this server")
        graph = self.graphs[(mode, req.faers)]
        budget = FaersBudget(self.settings.faers_max_pairs, self.settings.faers_budget_s) if req.faers else None
        timeout = self.settings.timeout_llm_s if mode == "llm" else self.settings.timeout_deterministic_s

        if not self._slots.acquire(blocking=False):
            raise ServiceError(503, "busy", "the server is at capacity; retry shortly", {"Retry-After": "2"})

        def work():
            _FAERS_BUDGET.set(budget)
            return graph.run(req.drugs, tags=["api"], request_id=request_id)

        try:
            future = self._pool.submit(contextvars.copy_context().run, work)
        except Exception:
            self._slots.release()
            raise
        future.add_done_callback(lambda _: self._slots.release())   # a timed-out run keeps its slot
        try:
            state = future.result(timeout=timeout)
        except FutureTimeout:
            log.warning("request timed out after %.0f s (mode=%s)", timeout, mode)
            raise ServiceError(504, "timeout", f"the check did not finish within {timeout:.0f} s") from None
        except InvalidDrugNameError as exc:
            raise ServiceError(422, "invalid_drug_name", str(exc)) from None
        return self._response(state, req, mode, budget, t0)

    def _response(self, state: Dict[str, Any], req: CheckRequest, mode: str,
                  budget: Optional[FaersBudget], t0: float) -> Dict[str, Any]:
        v = state["final_validation"]
        nodes: Dict[str, float] = {}
        for t in state["trajectory"]:
            nodes[t["node"]] = round(nodes.get(t["node"], 0.0) + float(t["ms"]), 3)
        out = {
            "request_id": state["request_id"],
            "report_markdown": state["report"],
            "report_source": state["report_source"],
            # The template report as data (entries, findings, notices...), for deterministic reports;
            # null for LLM reports, which the page shows as styled markdown.
            "report_structure": state.get("report_structure") if state["report_source"].startswith("deterministic")
                                else None,
            "mode": mode,
            "validation": {"passed": v["passed"], "finding_codes": sorted({f["code"] for f in v["findings"]}),
                           "clinical_claims": v["stats"].get("clinical_claims"),
                           "citations": v["stats"].get("citations")},
            "unresolved_inputs": [{"input": u["query"], "note": u.get("note")} for u in state["plan"]["unresolved"]],
            "data": {"profile": self.stamp["profile"], "data_line": self.stamp["data"],
                     "provenance_sha256": self.stamp["provenance_sha256"]},
            "disclaimer": Config().disclaimer,
            "attribution": self.notices,
            "faers": {"requested": req.faers,
                      "consulted_pairs": budget.consulted if budget else 0,
                      "skipped_pairs": budget.skipped if budget else 0,
                      "max_pairs": self.settings.faers_max_pairs if req.faers else 0},
            "timings_ms": {"graph": round(state["latency_seconds"] * 1000, 3), "nodes": nodes,
                           "total": round((time.perf_counter() - t0) * 1000, 3)},
        }
        if req.include_evidence:
            out["evidence"] = state.get("evidence")
        if req.include_trajectory:
            out["trajectory"] = state["trajectory"]
        return out

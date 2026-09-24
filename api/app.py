"""FastAPI app for PharmGuard: POST /v1/check, GET /health, GET /v1/graph, GET /, /docs.

Run:  uvicorn api.app:app --host 0.0.0.0 --port 7860 --no-access-log
All request handling lives in api/service.py; this module maps it to HTTP.
Every response carries X-Request-ID, and every log line carries request_id.
Logs record counts and codes, never drug names or report text.
"""
from __future__ import annotations

import contextvars
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.ratelimit import SlidingWindowLimiter, client_ip, proxy_summary
from api.service import MAX_DRUGS, MIN_DRUGS, CheckService, ServiceError
from api.settings import ApiSettings

STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY_BYTES = 16_384
_REQUEST_ID: contextvars.ContextVar = contextvars.ContextVar("pharmguard_request_id", default="-")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
log = logging.getLogger("pharmguard.api")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}
# The page loads only its own script and stylesheet; no inline script, no third-party origin.
PAGE_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _REQUEST_ID.get()
        return True


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
    # The middleware logs every request (without the client IP); uvicorn's access log would
    # add a second line with the IP, so it stays off.
    logging.getLogger("uvicorn.access").disabled = True


class CheckBody(BaseModel):
    """Schema for /docs. Counts and names are validated by the service (same rules as the app)."""
    drugs: List[str] = Field(..., description=f"{MIN_DRUGS}-{MAX_DRUGS} drug names",
                             examples=[["warfarin", "aspirin", "simvastatin", "clarithromycin"]])
    mode: str = Field("deterministic", description="auto | llm | deterministic (llm needs X-API-Key)")
    include_evidence: bool = False
    include_trajectory: bool = False
    faers: bool = Field(False, description="also query openFDA FAERS for pairs with no curated record (capped)")


def _error(request_id: str, status: int, code: str, message: str, headers=None) -> JSONResponse:
    return JSONResponse({"request_id": request_id, "error": {"code": code, "message": message}},
                        status_code=status, headers=headers)


def create_app(service: Optional[CheckService] = None, settings: Optional[ApiSettings] = None,
               clock=time.monotonic) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if app.state.service is None:
            configure_logging()
            s = settings or ApiSettings.from_env()
            app.state.service = await run_in_threadpool(CheckService.from_settings, s)
            app.state.limiter = SlidingWindowLimiter(s.rate_limit_requests, s.rate_limit_window_s, clock)
        h = app.state.service.health()
        log.info("started: data_loaded=%s profile=%s reason=%s", h["data_loaded"], h["profile"], h["reason"])
        yield

    app = FastAPI(title="PharmGuard API", version="1.0",
                  description="Drug-interaction reports from a LangGraph state machine with deterministic "
                              "planning and bounded LLM retry. Decision support only; not medical advice.",
                  lifespan=lifespan)
    app.state.service = service
    if service is not None:
        s = service.settings
        app.state.limiter = SlidingWindowLimiter(s.rate_limit_requests, s.rate_limit_window_s, clock)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        rid = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex[:16]
        token = _REQUEST_ID.set(rid)
        request.state.request_id = rid
        t0 = time.perf_counter()
        try:
            length = request.headers.get("content-length")
            limited = None
            if request.method == "POST" and request.url.path == "/v1/check":
                svc = request.app.state.service
                ip = client_ip(request.headers, request.client.host if request.client else None,
                               svc.settings.trusted_proxy_hops)
                allowed, retry_after = request.app.state.limiter.check(ip)
                if not allowed:   # counted before the body is parsed, so malformed bursts count too
                    limited = _error(rid, 429, "rate_limited", "too many requests; slow down",
                                     {"Retry-After": str(max(1, int(retry_after + 0.999)))})
            if limited is not None:
                response = limited
            elif length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
                response = _error(rid, 413, "body_too_large", f"request body over {MAX_BODY_BYTES} bytes")
            else:
                try:
                    response = await call_next(request)
                except Exception:   # never a stack trace in a response; it goes to the log
                    log.exception("unhandled error")
                    response = _error(rid, 500, "internal_error", "internal error")
            response.headers["X-Request-ID"] = rid
            for k, v in SECURITY_HEADERS.items():
                response.headers.setdefault(k, v)
            log.info("%s %s -> %s in %.1f ms", request.method, request.url.path, response.status_code,
                     (time.perf_counter() - t0) * 1000)
            return response
        finally:
            _REQUEST_ID.reset(token)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error(request.state.request_id, exc.status_code, code,
                      exc.detail if isinstance(exc.detail, str) else code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        if any(e.get("type") == "json_invalid" for e in errors):
            return _error(request.state.request_id, 422, "invalid_json", "request body is not valid JSON")
        fields = sorted({".".join(str(x) for x in e.get("loc", ()) if x != "body") for e in errors})
        return _error(request.state.request_id, 422, "invalid_request",
                      "invalid request body" + (f" (fields: {', '.join(f for f in fields if f)})" if fields else ""))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error")
        return _error(getattr(request.state, "request_id", "-"), 500, "internal_error", "internal error")

    @app.get("/health", summary="Build, data and LLM status")
    async def health(request: Request):
        svc = request.app.state.service
        body = {"request_id": request.state.request_id, **svc.health(),
                "proxy": proxy_summary(request.headers, request.client.host if request.client else None,
                                       svc.settings.trusted_proxy_hops)}
        return JSONResponse(body, status_code=200 if body["data_loaded"] else 503)

    @app.get("/v1/graph", summary="The LangGraph topology as Mermaid")
    async def graph(request: Request):
        return {"request_id": request.state.request_id, "mermaid": request.app.state.service.mermaid()}

    @app.post("/v1/check", summary="Check a medication list")
    async def check(request: Request, body: CheckBody):
        svc: CheckService = request.app.state.service
        rid = request.state.request_id
        try:
            out = await run_in_threadpool(contextvars.copy_context().run, svc.check,
                                          body.model_dump(), request.headers.get("x-api-key"), rid)
        except ServiceError as exc:
            log.info("check rejected: %s", exc.code)
            return JSONResponse(exc.body(rid), status_code=exc.status, headers=exc.headers)
        log.info("check ok: n_drugs=%d mode=%s report_source=%s passed=%s graph_ms=%.1f",
                 len(body.drugs), out["mode"], out["report_source"], out["validation"]["passed"],
                 out["timings_ms"]["graph"])
        return out

    @app.get("/", include_in_schema=False)
    async def page():
        return FileResponse(STATIC / "index.html", headers={"Content-Security-Policy": PAGE_CSP,
                                                            "Cache-Control": "no-cache"})

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()

"""Only transient LLM errors are retried; the rest go straight to the template."""
from __future__ import annotations

import anthropic
import httpx2
import pytest

from src.llm import LLMError, is_transient_llm_error

REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _status(cls, code):
    return cls("x", response=httpx2.Response(code, request=REQ), body=None)


TRANSIENT = [
    anthropic.APITimeoutError(request=REQ),
    anthropic.APIConnectionError(request=REQ),
    _status(anthropic.RateLimitError, 429),
    _status(anthropic.InternalServerError, 500),
    _status(anthropic.OverloadedError, 529),
    _status(anthropic.ServiceUnavailableError, 503),
    TimeoutError("read timed out"),
    ConnectionError("reset"),
]
PERMANENT = [
    _status(anthropic.BadRequestError, 400),        # e.g. "temperature is not supported"
    _status(anthropic.AuthenticationError, 401),
    _status(anthropic.PermissionDeniedError, 403),
    _status(anthropic.NotFoundError, 404),
    LLMError("Anthropic response incomplete: stop_reason=max_tokens"),
    LLMError("ANTHROPIC_API_KEY not set."),
    ValueError("bug"),
]


@pytest.mark.parametrize("exc", TRANSIENT, ids=lambda e: type(e).__name__)
def test_transient(exc):
    assert is_transient_llm_error(exc)


@pytest.mark.parametrize("exc", PERMANENT, ids=lambda e: type(e).__name__)
def test_not_transient(exc):
    assert not is_transient_llm_error(exc)

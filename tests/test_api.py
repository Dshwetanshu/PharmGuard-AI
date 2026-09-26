"""API tests: the framework-free service, the HTTP layer (TestClient), the bootstrap
download (fake downloader) and the page's escaping (Node, if installed).

Offline: the sample build with required_profile="sample"; the fail-closed tests use
the real default (required_profile="public") against the same synthetic data.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from api.app import create_app  # noqa: E402
from api.bootstrap import BuildError, ensure_build, verify_build  # noqa: E402
from api.ratelimit import SlidingWindowLimiter, client_ip  # noqa: E402
from api.service import CheckService, ServiceError, parse_request  # noqa: E402
from api.settings import ApiSettings  # noqa: E402
from src.data.provenance import file_sha256, processed_file_hashes  # noqa: E402
from src.graph import Settings  # noqa: E402

DRUGS = ["lisinopril", "spironolactone", "aspirin"]
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def api_settings(test_data_dir, sample_ingest_report):
    return ApiSettings(data_dir=test_data_dir, required_profile="sample", api_key="secret-key-123",
                       rate_limit_requests=1000, graph=Settings(data_dir=test_data_dir, mode="deterministic"))


@pytest.fixture(scope="module")
def service(api_settings):
    svc = CheckService.from_settings(api_settings)
    assert svc.ready, svc.load_error
    return svc


@pytest.fixture()
def client(service):
    with TestClient(create_app(service=service)) as c:
        yield c


# ------------------------------------------------------------------ service (no framework)

def test_service_check_returns_report_validation_data_and_notices(service):
    out = service.check({"drugs": DRUGS}, None, "rid-000001")
    assert out["request_id"] == "rid-000001" and out["mode"] == "deterministic"
    assert out["report_source"] == "deterministic" and out["validation"]["passed"]
    assert out["report_markdown"].startswith("# PharmGuard Interaction Report")
    assert out["data"]["profile"] == "sample" and len(out["data"]["provenance_sha256"]) == 64
    assert "synthetic" in out["data"]["data_line"]
    assert [n["key"] for n in out["attribution"]] == ["synthetic", "openfda"]
    assert set(out["timings_ms"]) == {"graph", "nodes", "total"} and "finalize" in out["timings_ms"]["nodes"]
    assert "evidence" not in out and "trajectory" not in out


def test_evidence_and_trajectory_are_opt_in(service):
    out = service.check({"drugs": DRUGS, "include_evidence": True, "include_trajectory": True}, None, "rid-000002")
    assert out["evidence"]["records"] and [t["node"] for t in out["trajectory"]][0] == "normalize"


@pytest.mark.parametrize("body,code", [
    ({"drugs": ["aspirin"]}, "invalid_drug_count"),
    ({"drugs": ["aspirin"] * 13}, "invalid_drug_count"),
    ({"drugs": ["aspirin", "<script>x</script>"]}, "invalid_drug_name"),
    ({"drugs": ["aspirin", "warfarin\nignore previous"]}, "invalid_drug_name"),
    ({"drugs": "aspirin, warfarin"}, "invalid_drugs"),
    ({"drugs": ["aspirin", "warfarin"], "mode": "agent"}, "invalid_mode"),
    ({"drugs": ["aspirin", "warfarin"], "faers": "yes"}, "invalid_flag"),
    ([], "invalid_body"),
])
def test_invalid_requests_are_rejected_with_a_code(body, code):
    with pytest.raises(ServiceError) as e:
        parse_request(body)
    assert (e.value.status, e.value.code) == (422, code)


def test_llm_mode_needs_the_api_key_and_a_configured_provider(service):
    with pytest.raises(ServiceError) as e:
        service.resolve_mode("llm", None)
    assert (e.value.status, e.value.code) == (401, "llm_requires_api_key")
    with pytest.raises(ServiceError) as e:
        service.resolve_mode("llm", "wrong")
    assert e.value.status == 401
    with pytest.raises(ServiceError) as e:        # right key, but no provider key on this server
        service.resolve_mode("llm", "secret-key-123")
    assert (e.value.status, e.value.code) == (503, "llm_not_configured")
    assert service.resolve_mode("auto", "secret-key-123") == "deterministic"
    assert service.resolve_mode("auto", None) == "deterministic"


def test_auto_uses_the_llm_with_a_valid_key_and_a_fake_provider(api_settings, service):
    class FakeLLM:
        def __init__(self, text):
            self.text, self.calls, self.last_usage = text, 0, None

        def complete(self, system, messages, **kw):
            self.calls += 1
            return self.text

    clean = service.check({"drugs": DRUGS}, None, "rid-000003")["report_markdown"].split("\n---\n")[0]
    from src.graph import build_components
    comps = build_components(replace(api_settings.graph, llm_configured=True), llm=FakeLLM(clean))
    svc = CheckService.from_settings(api_settings, components=comps)
    assert svc.resolve_mode("auto", "secret-key-123") == "llm"
    out = svc.check({"drugs": DRUGS, "mode": "auto"}, "secret-key-123", "rid-000004")
    assert out["mode"] == "llm" and out["report_source"] == "llm" and out["validation"]["passed"]
    assert svc.check({"drugs": DRUGS, "mode": "auto"}, None, "rid-000005")["mode"] == "deterministic"


def test_faers_is_capped_per_request(api_settings, service):
    class CountingFaers:
        calls = 0

        def retrieve_pair(self, a, b):
            CountingFaers.calls += 1
            return []

    svc = CheckService.from_settings(replace(api_settings, faers_max_pairs=2))
    svc.graphs[("deterministic", True)].components.faers.inner = CountingFaers()
    drugs = ["metformin", "levothyroxine", "omeprazole", "atorvastatin", "sertraline"]
    out = svc.check({"drugs": drugs, "faers": True}, None, "rid-000006")
    assert out["faers"]["requested"] and out["faers"]["consulted_pairs"] == 2 == CountingFaers.calls
    assert out["faers"]["skipped_pairs"] > 0
    assert svc.check({"drugs": drugs}, None, "rid-000007")["faers"]["consulted_pairs"] == 0
    assert CountingFaers.calls == 2   # not requested -> not consulted


def test_timeout_returns_504_and_busy_returns_503(api_settings, service):
    svc = CheckService.from_settings(replace(api_settings, timeout_deterministic_s=0.05, max_concurrency=1))
    g = svc.graphs[("deterministic", False)]
    real = g.run
    g.run = lambda *a, **k: (time.sleep(0.4), real(*a, **k))[1]
    with pytest.raises(ServiceError) as e:
        svc.check({"drugs": DRUGS}, None, "rid-000008")
    assert (e.value.status, e.value.code) == (504, "timeout")
    with pytest.raises(ServiceError) as e:        # the timed-out run still holds the only slot
        svc.check({"drugs": DRUGS}, None, "rid-000009")
    assert (e.value.status, e.value.code) == (503, "busy")
    g.run = real
    deadline = time.monotonic() + 20          # the slow run releases its slot when it finishes
    while True:
        try:
            out = svc.check({"drugs": DRUGS}, None, "rid-000010")
            break
        except ServiceError as exc:
            assert exc.code == "busy" and time.monotonic() < deadline
            time.sleep(0.1)
    assert out["validation"]["passed"]


def test_fail_closed_on_synthetic_data_when_the_public_build_is_required(test_data_dir, sample_ingest_report):
    svc = CheckService.from_settings(ApiSettings(data_dir=test_data_dir, required_profile="public"))
    h = svc.health()
    assert (h["status"], h["data_loaded"]) == ("unavailable", False)
    assert "requires 'public'" in h["reason"]
    with pytest.raises(ServiceError) as e:
        svc.check({"drugs": DRUGS}, None, "rid-000011")
    assert (e.value.status, e.value.code) == (503, "data_unavailable")


def test_fail_closed_when_no_build_exists(tmp_path):
    svc = CheckService.from_settings(ApiSettings(data_dir=tmp_path / "nothing"))
    assert not svc.ready and "provenance.json missing" in svc.health()["reason"]


# ------------------------------------------------------------------ HTTP layer

def test_http_check_health_graph_and_request_ids(client):
    r = client.post("/v1/check", json={"drugs": DRUGS})
    assert r.status_code == 200 and r.headers["x-request-id"] == r.json()["request_id"]
    assert r.headers["x-content-type-options"] == "nosniff"
    h = client.get("/health")
    assert h.status_code == 200 and h.json()["data_loaded"] and h.json()["records"]["interactions"] == 85
    assert h.json()["llm_configured"] is False and "request_id" in h.json()
    assert client.get("/v1/graph").json()["mermaid"].count("generate_llm") >= 1
    assert client.get("/docs").status_code == 200 and client.get("/openapi.json").status_code == 200
    r = client.post("/v1/check", json={"drugs": DRUGS}, headers={"X-Request-ID": "client-supplied-1"})
    assert r.headers["x-request-id"] == "client-supplied-1"
    r = client.post("/v1/check", json={"drugs": DRUGS}, headers={"X-Request-ID": "bad id\nwith newline"})
    assert r.headers["x-request-id"] != "bad id\nwith newline" and len(r.headers["x-request-id"]) == 16


@pytest.mark.parametrize("body,status,code", [
    ({"drugs": ["aspirin"] * 13}, 422, "invalid_drug_count"),
    ({"drugs": ["aspirin", "a;b"]}, 422, "invalid_drug_name"),
    ({"drugs": 5}, 422, "invalid_request"),
    ({"drugs": ["aspirin", "warfarin"], "mode": "llm"}, 401, "llm_requires_api_key"),
])
def test_http_errors_are_json_with_request_id(client, body, status, code):
    r = client.post("/v1/check", json=body)
    assert r.status_code == status and r.json()["error"]["code"] == code
    assert r.json()["request_id"] == r.headers["x-request-id"]


def test_malformed_json_gets_a_clear_error(client):
    r = client.post("/v1/check", content=b'{"drugs": [}', headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_json"


def test_http_404_405_and_oversized_body(client):
    assert client.get("/nope").json()["error"]["code"] == "not_found"
    assert client.get("/v1/check").json()["error"]["code"] == "method_not_allowed"
    r = client.post("/v1/check", content=b"{" + b" " * 20000 + b"}", headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_no_stack_trace_reaches_the_client(api_settings, service):
    svc = CheckService.from_settings(api_settings)
    svc.check = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret internal detail /etc/passwd"))
    with TestClient(create_app(service=svc), raise_server_exceptions=False) as c:
        r = c.post("/v1/check", json={"drugs": DRUGS})
    assert r.status_code == 500 and r.json()["error"] == {"code": "internal_error", "message": "internal error"}
    assert "secret" not in r.text and "Traceback" not in r.text and r.headers["x-request-id"]


def test_http_503_when_data_not_loaded(test_data_dir, sample_ingest_report):
    svc = CheckService.from_settings(ApiSettings(data_dir=test_data_dir, required_profile="public"))
    with TestClient(create_app(service=svc)) as c:
        assert c.get("/health").status_code == 503
        r = c.post("/v1/check", json={"drugs": DRUGS})
    assert r.status_code == 503 and r.json()["error"]["code"] == "data_unavailable"


def test_rate_limit_burst_returns_429_with_retry_after(api_settings, service):
    svc = CheckService.from_settings(replace(api_settings, rate_limit_requests=3, rate_limit_window_s=60))
    now = [1000.0]
    with TestClient(create_app(service=svc, clock=lambda: now[0])) as c:
        codes = [c.post("/v1/check", json={"drugs": DRUGS}).status_code for _ in range(5)]
        assert codes == [200, 200, 200, 429, 429]
        r = c.post("/v1/check", json={"drugs": ["x"]})           # malformed requests count too
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
        now[0] += 61
        assert c.post("/v1/check", json={"drugs": DRUGS}).status_code == 200


def test_client_ip_uses_only_trusted_proxy_hops():
    h = {"x-forwarded-for": "6.6.6.6, 203.0.113.9"}      # client-forged entry, then the proxy's
    assert client_ip(h, "10.0.0.1", 1) == "203.0.113.9"
    assert client_ip(h, "10.0.0.1", 0) == "10.0.0.1"         # no trusted proxy: header ignored
    assert client_ip({}, "10.0.0.1", 1) == "10.0.0.1"
    lim = SlidingWindowLimiter(2, 10, clock=lambda: 0.0)
    assert [lim.check("a")[0], lim.check("a")[0], lim.check("a")[0], lim.check("b")[0]] == [True, True, False, True]


def test_health_reports_proxy_counts_without_addresses(client):
    h = client.get("/health", headers={"X-Forwarded-For": "198.51.100.7, 203.0.113.9"}).json()
    assert h["proxy"] == {"forwarded_for_entries": 2, "trusted_proxy_hops": 0, "client_key_is_tcp_peer": True}
    assert "198.51.100.7" not in json.dumps(h) and "203.0.113.9" not in json.dumps(h)
    from api.ratelimit import proxy_summary
    assert proxy_summary({"x-forwarded-for": "198.51.100.7"}, "10.0.0.1", 1)["client_key_is_tcp_peer"] is False


def test_page_is_served_with_a_strict_csp_and_no_inline_script(client):
    r = client.get("/")
    assert r.status_code == 200 and "script-src 'self'" in r.headers["content-security-policy"]
    html = r.text
    assert '<script src="/static/app.js"></script>' in html and "<script>" not in html
    assert ("Educational demo, not medical advice.</strong> Don't start, stop or change any medicine based on "
            "these results; talk to your pharmacist or doctor.") in html
    assert client.get("/static/app.js").status_code == 200
    assert "font-src 'self'" in r.headers["content-security-policy"]
    for asset in ("/static/style.css", "/static/favicon.svg", "/static/fonts/InterVariable.woff2",
                  "/static/fonts/Inter-LICENSE.txt"):
        assert client.get(asset).status_code == 200, asset


def test_page_makes_no_third_party_requests():
    """Every URL the page can load (src, href, url(), fetch) is same-origin."""
    import re
    static = ROOT / "api" / "static"
    html, css, js = ((static / n).read_text() for n in ("index.html", "style.css", "app.js"))
    urls = re.findall(r'(?:src|href)="([^"]*)"', html) + re.findall(r'url\(\s*"?([^")]*)', css)
    urls += re.findall(r'fetch\(\s*"([^"]*)"', js) + re.findall(r'href="(?![?#/])([^"]*)"', js)
    assert urls and all(u.startswith(("/", "?", "#")) and not u.startswith("//") for u in urls), urls
    assert "@import" not in css and not re.search(r"https?://", css + js)


def test_page_palette_has_no_green():
    """No green anywhere, so "no curated data" (or anything else) can't read as "safe"."""
    import colorsys
    import re
    css = (ROOT / "api" / "static" / "style.css").read_text()
    colours = [tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) for h in re.findall(r"#([0-9A-Fa-f]{6})\b", css)]
    colours += [tuple(int(x) / 255 for x in m) for m in re.findall(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", css)]
    assert len(colours) > 20
    for rgb in colours:
        h, lum, sat = colorsys.rgb_to_hls(*rgb)
        assert not (75 <= h * 360 <= 170 and sat > 0.2), rgb


# ------------------------------------------------------------------ page renderer (Node)

@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_page_renderer_escapes_everything_and_collapses_not_graded():
    report = "\n".join([
        "# PharmGuard Interaction Report", "", "## Summary", "Hi <img src=x onerror=alert(1)>", "",
        "## Major Findings", "- **a + b** — curated severity: Major (DDInter) [DDInter:DDI-1]",
        "## Listed by DDInter without a severity grade", "- **c + d** — curated severity: not graded (DDInter) [DDInter:DDI-2]",
        "- **<script>alert(2)</script> + e** — x [DDInter:DDI-3]", "",
        "## Coverage Notes", "### Unresolved Inputs", "- \"><svg onload=alert(3)>", "---", "**Disclaimer.** d",
    ])
    js = ("const m=require(%s);process.stdout.write(JSON.stringify({html:m.renderReport(%s),"
          "split1:m.splitDrugs('a, b'),split2:m.splitDrugs('insulin, regular, human\\nwarfarin')}))"
          % (json.dumps(str(ROOT / "api" / "static" / "app.js")), json.dumps(report)))
    out = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    html = out["html"]
    assert "<img" not in html and "<script>" not in html and "<svg" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html and "&lt;script&gt;" in html
    assert '<details class="collapsed"><summary>Listed by DDInter without a severity grade (2)</summary>' in html
    assert html.index("</details>") < html.index("Coverage Notes")
    assert "<strong>a + b</strong>" in html and '<span class="cite">[DDInter:DDI-1]</span>' in html
    assert out["split1"] == ["a", "b"] and out["split2"] == ["insulin, regular, human", "warfarin"]


HOSTILE = "<img src=x onerror=alert(1)>"


def _hostile(value, key=None):
    """Append markup to every free-text string; keep the keys the renderer switches on."""
    if isinstance(value, dict):
        return {k: _hostile(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_hostile(v, key) for v in value]
    if isinstance(value, str) and key not in ("status", "severity", "kind"):
        return value + HOSTILE
    return value


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_page_renders_the_structure_escaped_and_complete(service):
    out = service.check({"drugs": ["lisinopril", "Lisinopril", "spironolactone", "aspirin", "qqqzzz"]}, None, "rid-000009")
    s = out["report_structure"]
    assert s and s["findings"] and s["entries"]["notices"] and s["coverage"]["unresolved"]
    cite = {"source": "DDInter", "record_id": "DDI-9", "text": "DDInter:DDI-9"}
    s["ungraded"]["items"] = [dict(s["findings"][0], severity="not graded")]
    s["signals"]["items"] = [{"pair": ["a", "b"], "event": "nausea", "prr": 2.5, "reports": 1234, "citation": cite, "line": "x"}]
    s["signals"]["hidden"] = [{"pair": ["a", "b"], "count": 4, "line": "**a + b** — +4 more not shown", "after": 1}]
    s["coverage"]["no_data"] = {"intro": "none", "pairs": [["c", "d"]], "faers_note": None}
    s["faers"] = {"heading": "FAERS", "intro": "raw", "items": [{"pair": ["c", "d"], "event": "rash", "report_count": 1,
                                                                 "citation": cite, "line": "x"}]}
    s = _hostile(s)
    resp = _hostile({"report_source": "deterministic", "request_id": "rid", "validation": {"passed": True,
                     "clinical_claims": 3, "citations": 3}, "timings_ms": {"total": 12.3}})
    js = ("const m=require(%s);const p=m.renderStructured(%s);"
          "process.stdout.write(JSON.stringify({p:p,tech:m.techDetails(%s),pl:[m.plural(1,'report'),m.plural(2,'report')]}))"
          % (json.dumps(str(ROOT / "api" / "static" / "app.js")), json.dumps(s), json.dumps(resp)))
    got = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    html = got["p"]["body"] + got["p"]["entries"] + got["tech"]
    # Escape-then-render: the only markup is the page's own.
    assert "<img" not in html and html.count("&lt;img src=x onerror=alert(1)&gt;") > 20
    # Every entry, the duplicate notice, each finding with its record, the unresolved reason,
    # the summary sentence, the disclaimer and the data line are all present.
    for e in s["entries"]["items"]:
        assert escape_like(e["input"]) in html and (e["note"] is None or escape_like(e["note"]) in html)
    assert "Same drug entered more than once:" in html
    for f in s["findings"]:
        assert escape_like(f["pair"][0]) in html and escape_like(f["citation"]["record_id"]) in html
    for key in ("text",):
        assert escape_like(s["summary"][key]) in html
    assert escape_like(s["disclaimer"]) in html and escape_like(s["data_line"]) in html
    assert escape_like(s["coverage"]["unresolved"]["items"][0]["reason"]) in html
    # Severity by word and icon; the ungraded listings are collapsed (closed <details>).
    assert 'class="badge badge--major"' in html or 'class="badge badge--moderate"' in html
    assert '<details class="fold"><summary>' in html and "<details open" not in html
    assert "+4 more not shown" in html and "1,234 co-reports" in html and "1 report" in html
    assert "Report source" in got["tech"] and "Request ID" in got["tech"]
    assert got["pl"] == ["1 report", "2 reports"]


def escape_like(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;").replace("**", ""))


# ------------------------------------------------------------------ bootstrap (fake downloader)

def _build_copy(test_data_dir, dest: Path) -> str:
    """A verifiable build: the sample build with processed_files recorded in provenance."""
    src = Path(test_data_dir) / "processed"
    (dest / "processed").mkdir(parents=True)
    for p in src.iterdir():
        if p.is_file():
            shutil.copy(p, dest / "processed" / p.name)
    prov_path = dest / "processed" / "provenance.json"
    prov = json.loads(prov_path.read_text())
    prov["processed_files"] = processed_file_hashes(dest / "processed")
    prov_path.write_text(json.dumps(prov, indent=2, sort_keys=True) + "\n")
    return file_sha256(prov_path)


REV = "0123456789abcdef0123456789abcdef01234567"


def _settings(tmp_path, **kw):
    return ApiSettings(data_dir=tmp_path / "live", required_profile="sample", hf_dataset="org/pharmguard-public",
                       hf_revision=REV, hf_token="hf_readonly", **kw)


def test_bootstrap_downloads_verifies_and_serves(tmp_path, test_data_dir, sample_ingest_report):
    staged = tmp_path / "remote"
    pin = _build_copy(test_data_dir, staged)
    seen = {}

    def fake(repo, rev, token, dest):
        seen.update(repo=repo, rev=rev, token=token)
        shutil.copytree(staged / "processed", dest / "processed")
        return dest

    s = _settings(tmp_path, hf_provenance_sha256=pin)
    prov = ensure_build(s, fake)
    assert seen == {"repo": "org/pharmguard-public", "rev": REV, "token": "hf_readonly"}
    assert prov["processed_files"] and (tmp_path / "live" / "processed" / "interactions.parquet").exists()
    svc = CheckService.from_settings(replace(s, graph=Settings(data_dir=s.data_dir, mode="deterministic")),
                                     downloader=fake)
    assert svc.ready and svc.check({"drugs": DRUGS}, None, "rid-000012")["validation"]["passed"]


@pytest.mark.parametrize("tamper,message", [
    ("provenance", "does not match the pinned"),
    ("file", "does not match its sha256"),
    ("extra", "files not listed"),
    ("missing", "missing"),
])
def test_bootstrap_rejects_tampered_builds(tmp_path, test_data_dir, sample_ingest_report, tamper, message):
    staged = tmp_path / "remote"
    pin = _build_copy(test_data_dir, staged)
    proc = staged / "processed"
    if tamper == "provenance":
        (proc / "provenance.json").write_text((proc / "provenance.json").read_text() + " ")
    elif tamper == "file":
        (proc / "interactions.parquet").write_bytes((proc / "interactions.parquet").read_bytes() + b"x")
    elif tamper == "extra":
        (proc / "evil.parquet").write_bytes(b"x")
    else:
        (proc / "side_effects.parquet").unlink()

    def fake(repo, rev, token, dest):
        shutil.copytree(proc, dest / "processed")
        return dest

    with pytest.raises(BuildError, match=message):
        ensure_build(_settings(tmp_path, hf_provenance_sha256=pin), fake)
    assert not (tmp_path / "live" / "processed").exists()     # nothing unverified is put in place
    svc = CheckService.from_settings(_settings(tmp_path, hf_provenance_sha256=pin), downloader=fake)
    assert not svc.ready and message in svc.health()["reason"]


@pytest.mark.parametrize("kw,message", [
    ({"hf_revision": "main"}, "pinned 40-character commit sha"),
    ({"hf_provenance_sha256": None}, "64-character sha256"),
])
def test_bootstrap_requires_pins(tmp_path, kw, message):
    s = replace(_settings(tmp_path, hf_provenance_sha256="a" * 64), **kw)
    with pytest.raises(BuildError, match=message):
        ensure_build(s, lambda *a: None)


def test_bootstrap_download_failure_does_not_leak_the_token(tmp_path):
    def fake(repo, rev, token, dest):
        raise PermissionError(f"401 for token {token}")

    with pytest.raises(BuildError) as e:
        ensure_build(_settings(tmp_path, hf_provenance_sha256="a" * 64), fake)
    assert "hf_readonly" not in str(e.value) and "PermissionError" in str(e.value)


def test_no_download_configured_is_a_no_op(tmp_path):
    assert ensure_build(ApiSettings(data_dir=tmp_path), lambda *a: 1 / 0) is None


def test_verify_build_needs_processed_files(tmp_path, test_data_dir, sample_ingest_report):
    shutil.copytree(Path(test_data_dir) / "processed", tmp_path / "p")
    with pytest.raises(BuildError, match="no processed_files"):
        verify_build(tmp_path / "p", file_sha256(tmp_path / "p" / "provenance.json"))


def test_settings_from_env_defaults():
    s = ApiSettings.from_env(env={"PHARMGUARD_DATA_DIR": "/data/public", "PHARMGUARD_RATE_LIMIT": "5/30",
                                  "PHARMGUARD_TRUSTED_PROXY_HOPS": "1"})
    assert (s.required_profile, s.rate_limit_requests, s.rate_limit_window_s, s.trusted_proxy_hops) == \
        ("public", 5, 30.0, 1)
    assert s.graph.rxnorm_enabled is False and s.graph.tracing == "none" and s.graph.faers_enabled is False
    assert s.api_key is None and s.hf_dataset is None

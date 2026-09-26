// PharmGuard page. Every piece of text from the server or the user is escaped before it is
// placed in the DOM. Deterministic reports render from response.report_structure (the same
// data the markdown is written from, including the pair grid). Reports without a structure
// (LLM) fall back to the markdown: escaped first, then a small renderer turns the escaped text
// into headings, lists and bold, so no markup can execute. Report wording comes from the
// structure; the page adds only labels and counts taken from it, and never shows a zero count.
"use strict";

function escapeHtml(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
const esc = escapeHtml;
const bold = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

function plural(n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); }

function joinAnd(items) {
  return items.length <= 1 ? items.join("") : items.slice(0, -1).join(", ") + " and " + items[items.length - 1];
}

// ------------------------------------------------------------------ severity

const TIERS = ["Major", "Moderate", "Minor"];
const STATUS = {                     // grid status -> [css key, word shown]
  Major: ["major", "Major"], Moderate: ["moderate", "Moderate"], Minor: ["minor", "Minor"],
  "not graded": ["ungraded", "Not graded"], "signals only": ["signals", "Signals only"],
  "no curated data": ["none", "No curated data"],
};
const REF_ID = {findings: "finding-", ungraded: "ungraded-", signals: "signal-"};

// Three steps, filled by severity (3 Major, 2 Moderate, 1 Minor); the word beside it carries the meaning.
function marker(key) {
  return '<span class="sev sev--' + key + '" aria-hidden="true"><i></i><i></i><i></i></span>';
}
function severity(status) {
  const s = STATUS[status] || STATUS["not graded"];
  return '<span class="sevword sevword--' + s[0] + '">' + marker(s[0]) + "<span>" + esc(s[1]) + "</span></span>";
}

// ------------------------------------------------------------------ answer first

// The caution under a headline with nothing graded, matched to what is missing.
const CAUTION = {
  nodata: "Absence of a record doesn\u2019t mean the combination is safe.",
  ungraded: "A listing without a severity grade doesn\u2019t mean the combination is safe.",
  both: "Neither a missing record nor a listing without a severity grade means the combination is safe.",
  signals: "A statistical signal isn\u2019t a severity grade and doesn\u2019t mean the combination is safe.",
};

function caution(sum) {
  if (sum.no_data_pairs > 0 && sum.ungraded > 0) return CAUTION.both;
  if (sum.ungraded > 0) return CAUTION.ungraded;
  if (sum.no_data_pairs > 0) return CAUTION.nodata;
  return sum.signals > 0 ? CAUTION.signals : "";
}

// The headline leads with what was found and never reads as reassurance: with nothing graded it
// names the ungraded listings, signals or no-data pairs, and the caution goes directly under it.
function answer(s) {
  const sum = s.summary, g = sum.graded;
  const top = TIERS.find(t => g[t] > 0);
  const parts = [];            // [key, text], most important first
  TIERS.forEach(t => { if (g[t] > 0) parts.push([t, plural(g[t], t.toLowerCase() + " interaction")]); });
  if (sum.ungraded > 0) parts.push(["ungraded", plural(sum.ungraded, "listing") + " without a severity grade"]);
  if (sum.signals > 0) parts.push(["signals", plural(sum.signals, "statistical signal")]);
  if (sum.no_data_pairs > 0) parts.push(["nodata", plural(sum.no_data_pairs, "pair") + " with no curated data"]);
  let headline, rest = parts.slice(1);
  if (sum.pairs === 0) {
    headline = "No pairs could be checked";
    rest = [];
  } else if (parts.length && parts[0][0] === "nodata") {
    headline = sum.no_data_pairs === sum.pairs
      ? "No curated data for " + (sum.pairs === 1 ? "this pair" : "these " + sum.pairs + " pairs")
      : "No curated data for " + sum.no_data_pairs + " of " + sum.pairs + " pairs";
  } else {
    headline = parts.length ? parts[0][1] : "";
  }
  headline = headline.charAt(0).toUpperCase() + headline.slice(1);
  let sub;
  if (sum.pairs === 0) {
    sub = sum.medications ? plural(sum.medications, "medicine") + " recognized; a check needs at least two." :
                            "No medicines were recognized.";
  } else {
    sub = plural(sum.pairs, "pair") + " checked across " + plural(sum.medications, "medicine") + "." +
      (rest.length ? " Also " + joinAnd(rest.map(r => r[1])) + "." : "");
  }
  return {headline: headline, caution: !top && sum.pairs > 0 ? caution(sum) : "", sub: sub};
}

// Alerts that change what the report covers: duplicates, unrecognised inputs, readings to check.
function alerts(s) {
  const out = s.entries.notices.map(n => "<li>" + bold(n.text) + "</li>");
  const by = st => s.entries.items.filter(e => e.status === st);
  const unres = by("unresolved");
  if (unres.length) {
    out.push("<li><strong>Not recognized, left out of the check:</strong> " + unres.map(e => esc(e.input)).join(", ") + "</li>");
  }
  by("spelling_match").forEach(e => out.push("<li><strong>Spelling match, check this:</strong> " + esc(e.input) +
    " → " + esc(e.read_as) + "</li>"));
  by("ambiguous").forEach(e => out.push("<li><strong>Ambiguous name:</strong> " + esc(e.input) +
    (e.note ? ". " + esc(tidyNote(e.note)) : "") + "</li>"));
  by("combination").forEach(e => out.push("<li><strong>Combination product:</strong> " + esc(e.input) +
    (e.note ? ". " + esc(tidyNote(e.note)) : "") + "</li>"));
  return out.length ? '<ul class="alerts">' + out.join("") + "</ul>" : "";
}

// ------------------------------------------------------------------ pair grid (signature element)

function cellHtml(c) {
  const inner = severity(c.status);
  const s = STATUS[c.status] || STATUS["not graded"];
  const label = c.pair[0] + " and " + c.pair[1] + ": " + s[1];
  return c.ref
    ? '<a href="#' + REF_ID[c.ref.section] + c.ref.index + '" aria-label="' + esc(label) + '">' + inner + "</a>"
    : '<span class="c-static">' + inner + "</span>";
}

function gridHtml(g) {
  const n = g.drugs.length;
  if (n < 2) return "";
  const at = {};
  g.cells.forEach(c => { at[c.row + "," + c.col] = c; });
  let head = '<tr><td class="corner"></td>';
  for (let j = 0; j < n - 1; j++) {
    head += '<th scope="col"><span class="h-num" aria-hidden="true">' + (j + 1) + '</span><span class="h-name">' +
      esc(g.drugs[j]) + "</span></th>";
  }
  let body = "";
  for (let i = 1; i < n; i++) {
    body += '<tr><th scope="row"><span class="h-num" aria-hidden="true">' + (i + 1) + '</span><span class="h-name">' +
      esc(g.drugs[i]) + "</span></th>";
    for (let j = 0; j < n - 1; j++) {
      const c = at[i + "," + j];
      body += c ? '<td class="c c--' + (STATUS[c.status] || STATUS["not graded"])[0] + '">' + cellHtml(c) + "</td>"
                : '<td class="void"></td>';
    }
    body += "</tr>";
  }
  const list = g.cells.map(c => '<li class="c c--' + (STATUS[c.status] || STATUS["not graded"])[0] + '">' +
    '<span class="pl-pair">' + esc(c.pair[0]) + " + " + esc(c.pair[1]) + "</span>" + cellHtml(c) + "</li>").join("");
  // Narrow screens number the columns; this key says which medicine each number is.
  const key = '<ol class="grid-key" aria-hidden="true">' + g.drugs.map(d => "<li>" + esc(d) + "</li>").join("") + "</ol>";
  return '<div class="grid' + (n - 1 > 3 ? " grid--wide" : "") + '">' + key +
    '<div class="grid-scroll" tabindex="0" role="region" aria-label="Every pair checked">' +
    '<table class="pairs"><thead>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>" +
    '<ul class="pairlist">' + list + "</ul></div>";
}

// ------------------------------------------------------------------ findings and the rest

function findingRow(f, id) {
  const extra = [];
  if (f.condition) extra.push(esc(f.condition));
  if (f.mechanism) extra.push("Source mechanism: “" + esc(f.mechanism) + "”");
  return '<li class="f"' + (id ? ' id="' + id + '" tabindex="-1"' : "") + ">" + severity(f.severity) +
    '<div class="f-main"><p class="f-pair">' + esc(f.pair[0]) + " + " + esc(f.pair[1]) + "</p>" +
    (extra.length ? '<p class="f-extra">' + extra.join(". ") + "</p>" : "") + "</div>" +
    '<p class="cite">' + esc(f.citation.text) + "</p></li>";
}

function sourcesOf(items) {
  return items.map(f => f.source).filter((v, i, a) => a.indexOf(v) === i);
}

function section(id, title, sub, body) {
  return '<section class="sec" aria-labelledby="' + id + '"><h3 class="h3" id="' + id + '">' + esc(title) + "</h3>" +
    (sub ? '<p class="sec-sub">' + sub + "</p>" : "") + body + "</section>";
}

// "not found: check the spelling..." -> "Check the spelling...", so a line reads as one sentence.
function tidyNote(note) {
  const t = String(note || "").replace(/^not found:\s*/i, "").trim();
  if (!t) return "";
  const c = t.charAt(0).toUpperCase() + t.slice(1);
  return /[.!?]$/.test(c) ? c : c + ".";
}

// Exceptions first (in the order entered), then aliases, then exact matches.
const EXCEPTIONS = ["unresolved", "spelling_match", "ambiguous", "combination"];
function entryRank(e) {
  if (EXCEPTIONS.indexOf(e.status) >= 0) return 0;
  return e.how ? 1 : 2;
}

function entryLine(e) {
  const name = '<span class="e-typed">' + esc(e.input) + "</span>";
  switch (e.status) {
    case "recognized":
      return e.how ? "<li>" + name + " → " + esc(e.read_as) + ' <span class="quiet">(' + esc(e.how) + ")</span></li>"
                   : '<li class="e-exact">' + name + "</li>";
    case "spelling_match":
      return '<li class="e-flag">' + name + " → " + esc(e.read_as) + " <strong>(spelling match, check this)</strong></li>";
    case "unresolved":
      return '<li class="e-flag">' + name + ": <strong>not recognized.</strong>" +
        (e.note ? " " + esc(tidyNote(e.note)) : "") + "</li>";
    default: {
      const label = e.status === "combination" ? "combination product" : "ambiguous name";
      return '<li class="e-flag">' + name + (e.read_as ? " → " + esc(e.read_as) : "") + ": <strong>" + label +
        ".</strong>" + (e.note ? " " + esc(tidyNote(e.note)) : "") + "</li>";
    }
  }
}

// Structured report -> {headline, sub, body} (body = everything under the answer).
function renderStructured(s) {
  const a = answer(s);
  let body = alerts(s);
  if (s.coverage.all_covered) body += '<p class="covered">' + esc(s.coverage.all_covered) + "</p>";
  body += section("sec-grid", "Every pair checked", null, gridHtml(s.grid));
  if (s.findings.length) {
    body += section("sec-findings", "Interactions", "Severity grades from " + esc(joinAnd(sourcesOf(s.findings))) + ".",
      '<ol class="findings">' + s.findings.map((f, i) => findingRow(f, "finding-" + i)).join("") + "</ol>");
  }
  if (s.ungraded.items.length) {
    // Collapsed on screen; printing uses the open copy (a closed <details> prints closed).
    const title = "Listed by DDInter without a severity grade (" + s.ungraded.items.length + ")";
    const note = '<p class="sec-sub">' + esc(s.ungraded.note) + "</p>";
    // Open when it is all there is to show; collapsed under graded findings.
    body += '<section class="sec" aria-labelledby="sec-ungraded"><details class="fold screen-only"' +
      (s.findings.length ? "" : " open") + "><summary>" +
      '<h3 class="h3" id="sec-ungraded">' + title + "</h3></summary>" + note + '<ol class="findings">' +
      s.ungraded.items.map((f, i) => findingRow(f, "ungraded-" + i)).join("") + "</ol></details>" +
      '<div class="print-only"><h3 class="h3">' + title + "</h3>" + note + '<ol class="findings">' +
      s.ungraded.items.map(f => findingRow(f, null)).join("") + "</ol></div></section>";
  }
  if (s.signals.items.length) {
    const hidden = {};
    s.signals.hidden.forEach(h => { (hidden[h.after] = hidden[h.after] || []).push(h); });
    let rows = "";
    s.signals.items.forEach((x, i) => {
      rows += '<li class="f" id="signal-' + i + '" tabindex="-1"><span class="sevword sevword--signals">PRR ' +
        esc(x.prr == null ? "n/a" : Number(x.prr).toFixed(2)) + '</span><div class="f-main"><p class="f-pair">' +
        esc(x.pair[0]) + " + " + esc(x.pair[1]) + '</p><p class="f-extra">' + esc(x.event) + ". " +
        (x.reports == null ? "co-reports n/a" : esc(Number(x.reports).toLocaleString("en-US")) +
          (x.reports === 1 ? " co-report" : " co-reports")) + '</p></div><p class="cite">' + esc(x.citation.text) + "</p></li>";
      (hidden[i + 1] || []).forEach(h => {
        rows += '<li class="f-more">' + esc(h.pair[0]) + " + " + esc(h.pair[1]) + ": " +
          esc(h.line.split(" \u2014 ").pop()) + "</li>";
      });
    });
    body += section("sec-signals", s.signals.heading, esc(s.signals.intro), '<ol class="findings">' + rows + "</ol>");
  }
  if (s.faers) {
    body += section("sec-faers", s.faers.heading, esc(s.faers.intro), '<ol class="findings">' + s.faers.items.map(x =>
      '<li class="f"><span class="sevword sevword--signals">' + esc(plural(x.report_count, "report")) +
      '</span><div class="f-main"><p class="f-pair">' + esc(x.pair[0]) + " + " + esc(x.pair[1]) + '</p><p class="f-extra">' +
      esc(x.event) + '</p></div><p class="cite">' + esc(x.citation.text) + "</p></li>").join("") + "</ol>");
  }
  const nd = s.coverage.no_data;
  if (nd) {
    body += section("sec-nodata", "No curated interaction data", esc(nd.intro),
      '<ul class="nodata">' + nd.pairs.map(p => "<li>" + esc(p[0]) + " + " + esc(p[1]) + "</li>").join("") + "</ul>" +
      (nd.faers_note ? '<p class="sec-sub">' + esc(nd.faers_note) + "</p>" : ""));
  }
  if (s.entries.items.length) {
    const ordered = s.entries.items.map((e, i) => [entryRank(e), i, e]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    body += section("sec-entries", s.entries.heading, null,
      '<ul class="entries">' + ordered.map(x => entryLine(x[2])).join("") + "</ul>");
  }
  body += '<div class="report-foot"><p><strong>Disclaimer.</strong> ' + esc(s.disclaimer) + '</p><p class="small">' +
    esc(s.data_line) + "</p></div>";
  return {headline: a.headline, caution: a.caution, sub: a.sub, body: body};
}

// ------------------------------------------------------------------ markdown fallback (LLM reports)

function inline(escaped) {
  return escaped
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([A-Za-z][A-Za-z0-9 _-]*:[A-Za-z0-9._-]+)\]/g, '<span class="cite">[$1]</span>');
}

const COLLAPSED = ["Listed by DDInter without a severity grade"];

// Markdown (as produced by PharmGuard) -> HTML string. Input is escaped line by line.
function renderReport(markdown) {
  const lines = String(markdown || "").split("\n");
  const out = [];
  let list = false, collapsed = null;
  const closeList = () => { if (list) { out.push("</ul>"); list = false; } };
  const closeCollapsed = () => {
    if (collapsed) { closeList(); out.push("</details>"); collapsed = null; }
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      closeList();
      const level = h[1].length, title = h[2].trim();
      if (level <= 2) closeCollapsed();
      if (level === 2 && COLLAPSED.indexOf(title) >= 0) {
        let n = 0;
        for (let j = i + 1; j < lines.length && !/^#{1,2}\s/.test(lines[j]); j++) if (/^- /.test(lines[j])) n++;
        out.push('<details class="collapsed"><summary>' + escapeHtml(title) + " (" + n + ")</summary>");
        collapsed = title;
        continue;
      }
      out.push("<h" + (level + 1) + ">" + inline(escapeHtml(title)) + "</h" + (level + 1) + ">");
      continue;
    }
    if (/^- /.test(line)) {
      if (!list) { out.push("<ul>"); list = true; }
      out.push("<li>" + inline(escapeHtml(line.slice(2))) + "</li>");
      continue;
    }
    closeList();
    if (/^> /.test(line)) { out.push('<p class="notice">' + inline(escapeHtml(line.slice(2))) + "</p>"); continue; }
    if (line.trim() === "---") { closeCollapsed(); out.push("<hr>"); continue; }
    if (line.trim() !== "") out.push("<p>" + inline(escapeHtml(line)) + "</p>");
  }
  closeCollapsed();
  closeList();
  return out.join("\n");
}

// ------------------------------------------------------------------ technical details, notices

function techDetails(resp) {
  const v = resp.validation || {};
  const rows = [["Report source", resp.report_source], ["Automatic check", v.passed ? "passed" : "failed"],
                ["Claims checked", v.clinical_claims], ["Citations checked", v.citations],
                ["Time", resp.timings_ms ? Math.round(resp.timings_ms.total) + " ms" : null], ["Request ID", resp.request_id]];
  return '<details class="tech"><summary>Technical details</summary><dl>' +
    rows.filter(r => r[1] != null).map(([k, val]) => "<div><dt>" + esc(k) + "</dt><dd>" + esc(val) + "</dd></div>").join("") +
    "</dl></details>";
}

function sourcesHtml(list) {
  return (list || []).map(n => "<li><strong>" + esc(n.title) + ".</strong> " + esc(n.short || n.text) + "</li>").join("");
}
function citationsHtml(list) {
  return (list || []).map(n => "<li><strong>" + esc(n.title) + ".</strong> " + esc(n.text) + "</li>").join("");
}

// Same rule as src/input_validation.split_drug_input.
function splitDrugs(raw) {
  const lines = String(raw || "").split("\n").map(s => s.trim()).filter(Boolean);
  const parts = lines.length > 1 ? lines : String(raw || "").split(",").map(s => s.trim());
  return parts.filter(Boolean);
}

// ------------------------------------------------------------------ page

const EXAMPLES = ["warfarin, aspirin", "simvastatin, clarithromycin", "Coumadin, Diflucan", "sertraline, tramadol"];

function $(id) { return document.getElementById(id); }
function setText(id, text) { $(id).textContent = text || ""; }
function show(id, on) { $(id).hidden = !on; }

// Before a check the footer carries the disclaimer and data line; a report carries its own.
function pageFooter(visible) { show("disclaimer", visible); show("data-line", visible); }

function setNotices(list) {
  $("sources-list").innerHTML = sourcesHtml(list);
  $("citations-list").innerHTML = citationsHtml(list);
}

async function loadFooter() {
  try {
    const r = await fetch("/health");
    const h = await r.json();
    setText("disclaimer", h.disclaimer);
    setText("data-line", h.data_line || ("Data not loaded: " + (h.reason || "unknown")));
    if (!$("report").hidden) pageFooter(false);
    if ($("sources-list").children.length === 0) setNotices(h.attribution);
    if (!h.data_loaded) setText("status", "The service is unavailable: " + (h.reason || "data not loaded"));
  } catch (e) {
    setText("status", "Could not reach the service.");
  }
}

function setBusy(busy, n) {
  const button = $("submit");
  button.disabled = busy;
  button.textContent = busy ? "Checking…" : "Check interactions";
  $("results").setAttribute("aria-busy", busy ? "true" : "false");
  if (busy) setText("status", "Checking " + plural(n, "medicine") + "…");
}

function showError(message, requestId, inputProblem) {
  setText("error-msg", message);
  setText("error-id", requestId ? "Request " + requestId : "");
  $("drugs").setAttribute("aria-invalid", inputProblem ? "true" : "false");
  show("error", true);
  show("empty", true);
  pageFooter(true);
  setText("status", "Not checked.");
}

function openAncestors(el) {
  for (let p = el.parentElement; p; p = p.parentElement) if (p.tagName === "DETAILS") p.open = true;
}

// Grid cells link to their finding; a finding inside the collapsed section opens it first.
function onReportClick(ev) {
  const a = ev.target.closest && ev.target.closest('a[href^="#"]');
  if (!a) return;
  const target = document.getElementById(a.getAttribute("href").slice(1));
  if (!target) return;
  ev.preventDefault();
  openAncestors(target);
  target.focus({preventScroll: true});
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  target.scrollIntoView({behavior: smooth ? "smooth" : "auto", block: "center"});
  history.replaceState(null, "", "#" + target.id);
}

function showReport(body) {
  const s = body.report_structure;
  if (s) {
    const parts = renderStructured(s);
    setText("report-h", parts.headline);
    setText("report-caution", parts.caution);
    show("report-caution", !!parts.caution);
    setText("report-sub", parts.sub);
    $("report-body").innerHTML = parts.body;
  } else {
    // No structure (LLM report): the headline is the markdown's first heading.
    const md = String(body.report_markdown || "");
    const first = /^# (.*)\n?/.exec(md);
    setText("report-h", first ? first[1] : "Interaction report");
    show("report-caution", false);
    setText("report-sub", "");
    $("report-body").innerHTML = '<div class="md">' + renderReport(first ? md.slice(first[0].length) : md) + "</div>";
  }
  setText("checked", body.validation && body.validation.passed ? "Checked against source records." : "");
  setText("printed", "Checked on " + new Date().toLocaleString("en-GB", {dateStyle: "long", timeStyle: "short"}) +
    (body.request_id ? ", request " + body.request_id : "") + ".");
  $("tech").innerHTML = techDetails(body);
  if (body.attribution) setNotices(body.attribution);
  pageFooter(false);
  show("report", true);
  setText("status", "Report ready: " + $("report-h").textContent + ".");
  $("report-h").focus();
}

async function onSubmit(ev) {
  ev.preventDefault();
  const drugs = splitDrugs($("drugs").value);
  ["error", "report", "empty"].forEach(id => show(id, false));
  show("loading", true);
  setBusy(true, drugs.length);
  try {
    const r = await fetch("/v1/check", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({drugs: drugs, mode: "deterministic", faers: $("faers").checked}),
    });
    let body = {};
    try { body = await r.json(); } catch (e) { body = {}; }
    if (!r.ok) {
      const code = body.error ? body.error.code : "";
      showError(body.error ? body.error.message : "The server answered HTTP " + r.status + ".", body.request_id,
                /^invalid_drug/.test(code));
      return;
    }
    $("drugs").setAttribute("aria-invalid", "false");
    showReport(body);
  } catch (e) {
    showError("The request failed. Check your connection and try again.", null, false);
  } finally {
    show("loading", false);
    setBusy(false);
  }
}

if (typeof document !== "undefined") {
  const form = $("check-form");
  form.addEventListener("submit", onSubmit);
  $("report").addEventListener("click", onReportClick);
  $("print").addEventListener("click", () => window.print());
  $("examples").innerHTML = EXAMPLES.map(q => '<li><a href="?drugs=' + encodeURIComponent(q) + '">' +
    esc(q.replace(", ", " + ")) + "</a></li>").join("");
  loadFooter();
  // Shareable links: /?drugs=warfarin,aspirin fills the box (as plain text) and runs the check.
  const q = new URLSearchParams(window.location.search).get("drugs");
  if (q) {
    $("drugs").value = q;
    form.requestSubmit();
  }
}
if (typeof module !== "undefined") {
  module.exports = {escapeHtml, renderReport, renderStructured, splitDrugs, techDetails, plural, answer, gridHtml,
                    sourcesHtml, citationsHtml, tidyNote};
}

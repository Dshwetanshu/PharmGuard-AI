// PharmGuard page. Every piece of text from the server or the user is escaped before it is
// placed in the DOM; icons and the logo are fixed strings. Deterministic reports render as
// components from response.report_structure (the same data the markdown is written from).
// Reports without a structure (LLM) fall back to the markdown: escaped first, then a small
// renderer turns the escaped text into headings, lists and bold, so no markup can execute.
// Nothing here adds or rewords report content; labels and counts come from the structure.
"use strict";

function escapeHtml(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
const esc = escapeHtml;

// ------------------------------------------------------------------ icons (decorative; meaning is in the text)

const ICONS = {
  major: '<path d="M8.2 2.8h7.6l5.4 5.4v7.6l-5.4 5.4H8.2l-5.4-5.4V8.2z"/><path d="M12 7.5v5.5M12 16.2v.3"/>',
  moderate: '<path d="M12 3.2l9.3 16.3H2.7z"/><path d="M12 9.5v4.2M12 16.6v.3"/>',
  minor: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.2M12 7.8v.3"/>',
  ungraded: '<circle cx="12" cy="12" r="9"/><path d="M9.7 9.4a2.4 2.4 0 1 1 3.3 2.2c-.7.3-1 .8-1 1.5v.5M12 16.4v.3"/>',
  nodata: '<circle cx="12" cy="12" r="9" stroke-dasharray="2.6 2.4"/><path d="M8.5 12h7"/>',
  notice: '<path d="M12 3.2l9.3 16.3H2.7z"/><path d="M12 9.5v4.2M12 16.6v.3"/>',
  recognized: '<circle cx="12" cy="12" r="9"/><path d="M8 12.3l2.7 2.7L16.2 9.5"/>',
  spelling: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>',
  unresolved: '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
  combination: '<rect x="3.5" y="8" width="17" height="8" rx="4"/><path d="M12 8v8"/>',
  ambiguous: '<circle cx="12" cy="12" r="9"/><path d="M9.7 9.4a2.4 2.4 0 1 1 3.3 2.2c-.7.3-1 .8-1 1.5v.5M12 16.4v.3"/>',
  signal: '<path d="M4 20h16M7 16v4M12 11v9M17 6v14"/>',
  source: '<path d="M7 3.5h7l4 4v13H7z"/><path d="M14 3.5v4h4M9.5 12h6M9.5 15.5h6"/>',
  checked: '<path d="M12 3l7.5 3v5.5c0 4.5-3.2 8.2-7.5 9.5-4.3-1.3-7.5-5-7.5-9.5V6z"/><path d="M8.6 12l2.4 2.4 4.4-4.6"/>',
  arrow: '<path d="M5 12h13M13.5 7.5L18 12l-4.5 4.5"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.2M12 7.8v.3"/>',
  faers: '<path d="M5 4h14v16H5z"/><path d="M8.5 9h7M8.5 12.5h7M8.5 16h4"/>',
};
function icon(name, cls) {
  return '<svg class="i' + (cls ? " " + cls : "") + '" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
    (ICONS[name] || "") + "</svg>";
}

function plural(n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); }

// ------------------------------------------------------------------ structured report (deterministic)

const SEV = {Major: "major", Moderate: "moderate", Minor: "minor", "not graded": "ungraded"};
const SEV_WORD = {Major: "Major", Moderate: "Moderate", Minor: "Minor", "not graded": "Not graded"};
const bold = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

function badge(sev) {
  const k = SEV[sev] || "ungraded";
  return '<span class="badge badge--' + k + '">' + icon(k) + "<span>" + esc(SEV_WORD[sev] || sev) + "</span></span>";
}

function pill(c) {
  return '<span class="pill">' + icon("source") + '<span class="visually-hidden">Source record: </span>' +
    '<span class="pill-src">' + esc(c.source) + '</span><span class="pill-id">' + esc(c.record_id) + "</span></span>";
}

function findingRow(f) {
  const extra = [];
  if (f.condition) extra.push("<span>" + esc(f.condition) + "</span>");
  if (f.mechanism) extra.push("<span>Source mechanism: “" + esc(f.mechanism) + "”</span>");
  return '<li class="row row--' + (SEV[f.severity] || "ungraded") + '">' + badge(f.severity) +
    '<div class="row-main"><p class="pair">' + esc(f.pair[0]) + ' <span class="plus">+</span> ' + esc(f.pair[1]) + "</p>" +
    (extra.length ? '<p class="row-extra">' + extra.join('<span class="sep" aria-hidden="true"> · </span>') + "</p>" : "") +
    '<p class="row-src">Curated severity from ' + esc(f.source) + "</p></div>" + pill(f.citation) + "</li>";
}

const ENTRY_STATUS = {
  recognized: ["recognized", "Recognized"], spelling_match: ["spelling", "Spelling match · check this"],
  unresolved: ["unresolved", "Not recognized"], combination: ["combination", "Combination product"],
  ambiguous: ["ambiguous", "Ambiguous name"],
};
function entryItem(e) {
  const st = ENTRY_STATUS[e.status] || ENTRY_STATUS.unresolved;
  const read = e.read_as
    ? icon("arrow", "e-arrow") + '<span class="visually-hidden"> read as </span><span class="e-read">' + esc(e.read_as) +
      "</span>" + (e.how ? '<span class="e-how">' + esc(e.how) + "</span>" : "")
    : "";
  return '<li class="e e--' + esc(st[0]) + '">' + icon(st[0], "e-icon") +
    '<div class="e-main"><p class="e-line"><span class="e-typed">' + esc(e.input) + "</span>" + read +
    '<span class="e-status">' + esc(st[1]) + "</span></p>" + (e.note ? '<p class="e-note">' + esc(e.note) + "</p>" : "") +
    "</div></li>";
}

function entriesHtml(s) {
  return '<h2 class="panel-h" id="entries-h">' + esc(s.entries.heading) + '</h2><ul class="entries">' +
    s.entries.items.map(entryItem).join("") + "</ul>";
}

function tiles(sum) {
  const t = [["major", "Major", sum.graded.Major], ["moderate", "Moderate", sum.graded.Moderate],
             ["minor", "Minor", sum.graded.Minor], ["ungraded", "Not graded", sum.ungraded],
             ["nodata", "No curated data", sum.no_data_pairs], ["unresolved", "Not recognized", sum.unresolved]];
  return '<ul class="tiles" aria-label="Counts">' + t.map(([k, label, n]) =>
    '<li class="tile tile--' + k + (n ? "" : " is-zero") + '">' + icon(k) + '<span class="tile-n">' + esc(n) +
    '</span><span class="tile-label">' + esc(label) + "</span></li>").join("") + "</ul>";
}

function section(key, title, count, body, iconName) {
  return '<section class="sec sec--' + key + '" aria-labelledby="sec-' + key + '"><h3 class="sec-h" id="sec-' + key + '">' +
    (iconName ? icon(iconName) : "") + "<span>" + esc(title) + "</span>" +
    (count != null ? '<span class="count">' + esc(count) + "</span>" : "") + "</h3>" + body + "</section>";
}

// Structured report -> {entries, body} HTML. body holds everything shown in the report card.
function renderStructured(s) {
  let body = s.entries.notices.map(n => '<div class="callout callout-dup" role="note">' + icon("notice") +
    "<p>" + bold(n.text) + "</p></div>").join("");
  body += '<div class="summary">' + tiles(s.summary) + '<p class="summary-text">' + esc(s.summary.text) + "</p></div>";
  if (s.findings.length) {
    body += section("findings", "Findings", s.findings.length, '<ul class="rows">' + s.findings.map(findingRow).join("") + "</ul>");
  }
  if (s.ungraded.items.length) {
    body += '<section class="sec sec--ungraded"><details class="fold"><summary><h3 class="sec-h">' + icon("ungraded") +
      "<span>Listed by DDInter without a severity grade</span><span class=\"count\">" + esc(s.ungraded.items.length) +
      "</span>" + icon("chevron", "chev") + "</h3></summary><p class=\"sec-note\">" + esc(s.ungraded.note) +
      '</p><ul class="rows">' + s.ungraded.items.map(findingRow).join("") + "</ul></details></section>";
  }
  if (s.signals.items.length) {
    const hidden = {};
    s.signals.hidden.forEach(h => { (hidden[h.after] = hidden[h.after] || []).push(h); });
    let rows = "";
    s.signals.items.forEach((x, i) => {
      rows += '<li class="row row--signal">' + icon("signal", "row-icon") + '<div class="row-main"><p class="pair">' +
        esc(x.pair[0]) + ' <span class="plus">+</span> ' + esc(x.pair[1]) + '</p><p class="row-extra">' + esc(x.event) +
        '</p><p class="row-src">PRR ' + esc(x.prr == null ? "n/a" : Number(x.prr).toFixed(2)) + " · " +
        (x.reports == null ? "co-reports n/a" : esc(Number(x.reports).toLocaleString("en-US")) +
        (x.reports === 1 ? " co-report" : " co-reports")) + "</p></div>" + pill(x.citation) + "</li>";
      (hidden[i + 1] || []).forEach(h => {
        rows += '<li class="row row--more">' + bold(h.line) + "</li>";
      });
    });
    body += section("signals", s.signals.heading, s.signals.items.length,
      '<p class="sec-note">' + esc(s.signals.intro) + '</p><ul class="rows">' + rows + "</ul>", "signal");
  }
  const cov = s.coverage;
  if (cov.unresolved) {
    body += section("unresolved", "Unresolved inputs", cov.unresolved.items.length,
      '<p class="sec-note">' + esc(cov.unresolved.intro) + '</p><ul class="plain">' + cov.unresolved.items.map(u =>
        "<li>" + icon("unresolved") + "<span><strong>" + esc(u.input) + "</strong>" + (u.reason ? " — " + esc(u.reason) : "") +
        "</span></li>").join("") + "</ul>", "unresolved");
  }
  if (cov.no_data) {
    body += section("nodata", "No curated interaction data", cov.no_data.pairs.length,
      '<p class="sec-note">' + esc(cov.no_data.intro) + '</p><ul class="plain plain--pairs">' + cov.no_data.pairs.map(p =>
        "<li>" + icon("nodata") + "<span>" + esc(p[0]) + " + " + esc(p[1]) + "</span></li>").join("") + "</ul>" +
        (cov.no_data.faers_note ? '<p class="sec-note">' + esc(cov.no_data.faers_note) + "</p>" : ""), "nodata");
  }
  if (cov.all_covered) body += '<p class="covered">' + icon("info") + "<span>" + esc(cov.all_covered) + "</span></p>";
  if (s.faers) {
    body += section("faers", s.faers.heading, s.faers.items.length,
      '<p class="sec-note">' + esc(s.faers.intro) + '</p><ul class="rows">' + s.faers.items.map(x =>
        '<li class="row row--signal">' + icon("faers", "row-icon") + '<div class="row-main"><p class="pair">' + esc(x.pair[0]) +
        ' <span class="plus">+</span> ' + esc(x.pair[1]) + '</p><p class="row-extra">' + esc(x.event) + ": " +
        esc(plural(x.report_count, "report")) + "</p></div>" + pill(x.citation) + "</li>").join("") + "</ul>", "faers");
  }
  body += '<div class="report-foot"><p class="disclaimer"><strong>Disclaimer.</strong> ' + esc(s.disclaimer) +
    '</p><p class="meta">' + esc(s.data_line) + "</p></div>";
  return {title: s.title, entries: s.entries.items.length ? entriesHtml(s) : "", body: body};
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

function checkedMark(resp) {
  return resp.validation && resp.validation.passed
    ? '<span class="checked">' + icon("checked") + "<span>Checked against source records</span></span>" : "";
}

function techDetails(resp) {
  const v = resp.validation || {};
  const rows = [["Report source", resp.report_source], ["Automatic check", v.passed ? "passed" : "failed"],
                ["Claims checked", v.clinical_claims], ["Citations checked", v.citations],
                ["Time", resp.timings_ms ? Math.round(resp.timings_ms.total) + " ms" : "—"], ["Request ID", resp.request_id]];
  return '<details class="tech"><summary>' + icon("chevron", "chev") + "<span>Technical details</span></summary><dl>" +
    rows.filter(r => r[1] != null).map(([k, val]) => "<div><dt>" + esc(k) + "</dt><dd>" + esc(val) + "</dd></div>").join("") +
    "</dl></details>";
}

function noticesHtml(list) {
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

// Before a check the footer shows the disclaimer and data line; a report carries its own.
function pageFooter(visible) { show("disclaimer", visible); show("data-line", visible); }

function renderExamples() {
  $("examples").innerHTML = EXAMPLES.map(q => '<li><a class="btn btn-secondary" href="?drugs=' + encodeURIComponent(q) +
    '">' + esc(q.replace(", ", " + ")) + "</a></li>").join("");
}

async function loadFooter() {
  try {
    const r = await fetch("/health");
    const h = await r.json();
    setText("disclaimer", h.disclaimer);
    setText("data-line", h.data_line || ("Data not loaded: " + (h.reason || "unknown")));
    if (!$("report").hidden) pageFooter(false);
    if ($("attribution").children.length === 0) $("attribution").innerHTML = noticesHtml(h.attribution);
    if (!h.data_loaded) setText("status", "The service is unavailable: " + (h.reason || "data not loaded"));
  } catch (e) {
    setText("status", "Could not reach the service.");
  }
}

function setBusy(busy, n) {
  const button = $("submit");
  button.disabled = busy;
  button.querySelector(".btn-label").textContent = busy ? "Checking…" : "Check interactions";
  $("results").setAttribute("aria-busy", busy ? "true" : "false");
  if (busy) setText("status", "Checking " + plural(n, "medication") + "…");
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

function showReport(body) {
  const s = body.report_structure;
  if (s) {
    const parts = renderStructured(s);
    setText("report-h", parts.title);
    $("report-body").innerHTML = parts.body;
    $("entries").innerHTML = parts.entries;
    show("entries", !!parts.entries);
  } else {
    // No structure (LLM report): the title comes from the markdown's first heading.
    const md = String(body.report_markdown || "");
    const first = /^# (.*)\n?/.exec(md);
    setText("report-h", first ? first[1] : "Interaction report");
    $("report-body").innerHTML = '<div class="md">' + renderReport(first ? md.slice(first[0].length) : md) + "</div>";
    show("entries", false);
  }
  $("checked").innerHTML = checkedMark(body);
  $("tech").innerHTML = techDetails(body);
  if (body.attribution) $("attribution").innerHTML = noticesHtml(body.attribution);
  pageFooter(false);
  show("report", true);
  const g = s ? s.summary.graded : null;
  setText("status", g ? "Report ready: " + g.Major + " Major, " + g.Moderate + " Moderate, " + g.Minor + " Minor."
                      : "Report ready.");
  $("report-h").focus();
}

async function onSubmit(ev) {
  ev.preventDefault();
  const drugs = splitDrugs($("drugs").value);
  ["error", "report", "entries", "empty"].forEach(id => show(id, false));
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
  renderExamples();
  loadFooter();
  // Shareable links: /?drugs=warfarin,aspirin fills the box (as plain text) and runs the check.
  const q = new URLSearchParams(window.location.search).get("drugs");
  if (q) {
    $("drugs").value = q;
    form.requestSubmit();
  }
}
if (typeof module !== "undefined") module.exports = {escapeHtml, renderReport, renderStructured, splitDrugs, techDetails, plural};

// PharmGuard page. Every piece of text from the server or the user is escaped before
// it is placed in the DOM. The report markdown is escaped first, then a small renderer
// turns the escaped text into headings, lists and bold, so no markup in a report or a
// drug name can execute. the ungraded-listings section is collapsed with its count; the
// markdown report itself is complete (the API returns it unchanged).
"use strict";

function escapeHtml(text) {
  return String(text == null ? "" : text)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

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

// Same rule as src/input_validation.split_drug_input.
function splitDrugs(raw) {
  const lines = String(raw || "").split("\n").map(s => s.trim()).filter(Boolean);
  const parts = lines.length > 1 ? lines : String(raw || "").split(",").map(s => s.trim());
  return parts.filter(Boolean);
}

function setText(id, text) { document.getElementById(id).textContent = text || ""; }

function showNotices(notices) {
  const ul = document.getElementById("attribution");
  ul.textContent = "";
  (notices || []).forEach(n => {
    const li = document.createElement("li");
    const b = document.createElement("strong");
    b.textContent = n.title + ". ";
    li.appendChild(b);
    li.appendChild(document.createTextNode(n.text));
    ul.appendChild(li);
  });
}

async function loadFooter() {
  try {
    const r = await fetch("/health");
    const h = await r.json();
    setText("disclaimer", h.disclaimer);
    setText("data-line", h.data_line || ("Data not loaded: " + (h.reason || "unknown")));
    showNotices(h.attribution);
    if (!h.data_loaded) setText("status", "The service is unavailable: " + (h.reason || "data not loaded"));
  } catch (e) {
    setText("status", "Could not reach the service.");
  }
}

async function onSubmit(ev) {
  ev.preventDefault();
  const drugs = splitDrugs(document.getElementById("drugs").value);
  const button = document.getElementById("submit");
  button.disabled = true;
  setText("status", "Checking " + drugs.length + " medication(s)…");
  document.getElementById("result").hidden = true;
  try {
    const r = await fetch("/v1/check", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({drugs: drugs, mode: "deterministic", faers: document.getElementById("faers").checked}),
    });
    const body = await r.json();
    if (!r.ok) {
      const msg = body.error ? body.error.message : ("HTTP " + r.status);
      setText("status", "Not checked: " + msg + " (request " + (body.request_id || "?") + ")");
      return;
    }
    document.getElementById("report").innerHTML = renderReport(body.report_markdown);
    setText("meta", "report_source: " + body.report_source + " · validation: " +
            (body.validation.passed ? "passed" : "failed") + " · " + Math.round(body.timings_ms.total) +
            " ms · request " + body.request_id);
    setText("disclaimer", body.disclaimer);
    setText("data-line", body.data.data_line);
    showNotices(body.attribution);
    document.getElementById("result").hidden = false;
    setText("status", "");
  } catch (e) {
    setText("status", "Request failed.");
  } finally {
    button.disabled = false;
  }
}

if (typeof document !== "undefined") {
  const form = document.getElementById("check-form");
  form.addEventListener("submit", onSubmit);
  loadFooter();
  // Shareable links: /?drugs=warfarin,aspirin fills the box (as plain text) and runs the check.
  const q = new URLSearchParams(window.location.search).get("drugs");
  if (q) {
    document.getElementById("drugs").value = q;
    form.requestSubmit();
  }
}
if (typeof module !== "undefined") module.exports = {escapeHtml, renderReport, splitDrugs};

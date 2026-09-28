"""The deterministic report as data, and the markdown written from it.

build_structure(plan, result) returns a JSON-safe dict with every piece of the template
report: how each entry was read, notices, the summary counts, findings (pair, severity,
source, citation), ungraded listings, statistical signals, unresolved inputs, no-data pairs
and FAERS signals. render_markdown(structure) writes the markdown from that dict and nothing
else, so the API's structured report and the markdown can't disagree (a test checks it).
Each item also carries `line`, the exact markdown bullet text it becomes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

TIERS = ("Major", "Moderate", "Minor")
STRUCTURE_VERSION = 2
# Coverage note when every entry was recognized and every pair has at least one record.
ALL_COVERED_NOTE = "All entries were recognized, and each pair has a record in the loaded data."
# Grid cell statuses, most severe first. "signals only": statistical signals but no curated record.
GRID_STATUSES = ("Major", "Moderate", "Minor", "not graded", "signals only", "no curated data")


def plural(n: int, singular: str, plural_form: Optional[str] = None) -> str:
    """'1 medication', '4 medications'."""
    return f"{n} {singular if n == 1 else (plural_form or singular + 's')}"


def _join_names(names: List[str]) -> str:
    return " and ".join(names) if len(names) <= 2 else ", ".join(names[:-1]) + " and " + names[-1]


def entry_status(d) -> str:
    if d.resolved and d.generic_name:
        if d.method in ("fuzzy", "rxnorm_api"):
            return "spelling_match"
        return "recognized"
    return {"combination_product": "combination", "fuzzy_ambiguous": "ambiguous"}.get(d.method, "unresolved")


def entries_structure(plan) -> Dict[str, Any]:
    """How each entry was read, plus a notice for every drug entered more than once."""
    from src.agents.generator import ALIAS_KIND_LABELS, describe_entry
    entries = list(getattr(plan, "entries", None) or (list(plan.resolved) + list(plan.unresolved)))
    items = []
    for d in entries:
        how = None
        if d.resolved and d.generic_name and entry_status(d) == "recognized" \
                and " ".join(d.query.lower().split()) != d.generic_name.lower():
            how = ALIAS_KIND_LABELS.get(d.alias_kind or "", "alias")
        items.append({"input": d.query.strip(), "status": entry_status(d),
                      "read_as": d.generic_name if d.resolved else None, "how": how,
                      "note": None if d.resolved else d.note, "line": describe_entry(d)})
    groups: Dict[str, List[str]] = {}
    for d in entries:
        if d.resolved and d.generic_name:
            groups.setdefault(d.generic_name, []).append(d.query.strip())
    notices = []
    for generic, queries in groups.items():
        if len(queries) > 1:
            verb = "both mean" if len(queries) == 2 else "all mean"
            text = (f"**Same drug entered more than once:** {_join_names(queries)} {verb} {generic} "
                    "(possible duplicate therapy). It is analysed once.")
            notices.append({"kind": "duplicate", "drug": generic, "inputs": queries, "text": text})
    return {"items": items, "notices": notices}


def _citation(r) -> Dict[str, str]:
    return {"source": r.source, "record_id": r.record_id, "text": f"{r.source}:{r.record_id}"}


def _finding(r) -> Dict[str, Any]:
    from src.agents.generator import _is_placeholder
    graded = r.severity in TIERS
    sev = r.severity if graded else "not graded"
    line = f"**{r.drug_a} + {r.drug_b}** — curated severity: {sev} ({r.source})"
    condition = None if _is_placeholder(r.condition) else r.condition
    if condition:
        line += f"; {condition}"
    if r.mechanism:
        line += f'; source mechanism: "{r.mechanism}"'
    return {"severity": sev, "pair": [r.drug_a, r.drug_b], "source": r.source, "condition": condition,
            "mechanism": r.mechanism or None, "citation": _citation(r), "line": f"{line} {r.citation()}"}


def build_structure(plan, result) -> Dict[str, Any]:
    from src.agents.generator import (
        ENTRIES_HEADING, NOT_GRADED_NOTE, STATISTICAL_HEADING, _signal_stats, hidden_notice,
    )
    from src.agents.retriever import MAX_SIGNALS_PER_PAIR
    ent = entries_structure(plan)
    curated, signals = result.curated_records, result.statistical_signals
    hidden = result.total_hidden_signals
    graded = [r for r in curated if r.severity in TIERS]
    counts = {t: sum(r.severity == t for r in graded) for t in TIERS}
    by_tier = ", ".join(f"{t} {counts[t]}" for t in TIERS)
    summary_text = (
        f"Analyzed {plural(plan.num_drugs, 'medication')} across {plural(plan.num_pairs, 'unique pair')}. "
        f"Found {plural(len(graded), 'graded interaction')} ({by_tier}), "
        f"{plural(len(curated) - len(graded), 'listing')} without a severity grade and "
        f"{plural(len(signals), 'statistical reporting signal')}"
        + (f"; {plural(hidden, 'further signal')} {'is' if hidden == 1 else 'are'} not shown." if hidden else ".")
    )
    # Findings in severity order (Major, Moderate, Minor), then ungraded listings.
    findings = [_finding(r) for t in TIERS for r in curated if r.severity == t]
    ungraded = [_finding(r) for r in curated if r.severity not in TIERS]

    sig_items, sig_hidden = [], []
    for pair, records in result.interactions.items():
        for r in records:
            if r.is_statistical:
                sig_items.append({"pair": [r.drug_a, r.drug_b], "event": r.condition, "prr": r.prr,
                                  "reports": r.reports, "citation": _citation(r),
                                  "line": f"**{r.drug_a} + {r.drug_b}** — {r.condition}: {_signal_stats(r)} "
                                          f"{r.citation()}"})
        if result.hidden_signals.get(pair):
            n = result.hidden_signals[pair]
            sig_hidden.append({"pair": list(pair), "count": n,
                               "line": f"**{pair[0]} + {pair[1]}** — {hidden_notice(n)}", "after": len(sig_items)})

    unresolved = [{"input": u.query, "reason": u.note,
                   "line": f"{u.query}" + (f" — {u.note}" if u.note else "")} for u in plan.unresolved]
    nd = [list(p) for p in result.no_data_pairs]
    n_nd = len(nd)
    no_data = None
    if nd:
        no_data = {
            "intro": (f"No record in the queried curated sources for {'this pair' if n_nd == 1 else f'these {n_nd} pairs'}. "
                      "Absence of a record does not mean the combination is safe."),
            "pairs": nd,
            "faers_note": (f"FAERS reporting signals were found for {len(result.faers_signals)} of "
                           f"{'this pair' if n_nd == 1 else 'these pairs'}; see the unvalidated section below."
                           if result.faers_signals else None),
        }
    return {
        "version": STRUCTURE_VERSION,
        "grid": pair_grid(plan, findings, ungraded, sig_items, nd),
        "title": "PharmGuard Interaction Report",
        "entries": {"heading": ENTRIES_HEADING, **ent},
        "summary": {"medications": plan.num_drugs, "pairs": plan.num_pairs, "graded": counts,
                    "ungraded": len(ungraded), "signals": len(signals), "hidden_signals": hidden,
                    "unresolved": len(unresolved), "no_data_pairs": n_nd, "text": summary_text},
        "findings": findings,
        "ungraded": {"note": NOT_GRADED_NOTE, "items": ungraded},
        "signals": {"heading": STATISTICAL_HEADING,
                    "intro": ("Disproportionality statistics from co-reported adverse events: up to "
                              f"{MAX_SIGNALS_PER_PAIR} per pair, highest PRR first. A PRR compares how often an event "
                              "is reported with the pair against other drugs; it is not a clinical severity grade "
                              "and does not establish that the drugs interact."),
                    "items": sig_items, "hidden": sig_hidden},
        "coverage": {
            "unresolved": {"intro": "These inputs could not be matched to a drug in the local vocabulary and were excluded:",
                           "items": unresolved} if unresolved else None,
            "no_data": no_data,
            "all_covered": (ALL_COVERED_NOTE
                            if not unresolved and not nd else None),
        },
        "faers": faers_block(result),
        "disclaimer": None,     # filled in by Generator (the canonical footer)
        "data_line": None,
    }


FAERS_HEADING = "FAERS Spontaneous Reports (unvalidated)"
FAERS_INTRO = ("Disproportionality signals from FDA adverse-event reports that mention both drugs, for pairs "
               "with no curated interaction record. Shown only if PRR ≥ 2, chi-square ≥ 4, at least 3 reports, the ROR's "
               "lower 95% bound is above 1, and the pair's event rate is at least twice each drug's rate without "
               "the other. Spontaneous reports are not validated and do not establish that the drugs interact.")


def _fmt(v: Optional[float], digits: int = 2) -> str:
    return "—" if v is None else f"{v:.{digits}f}"


def faers_stats_text(s) -> str:
    return (f"PRR {_fmt(s.prr)}, ROR {_fmt(s.ror)} (95% CI {_fmt(s.ror_ci_low)}–{_fmt(s.ror_ci_high)}), "
            f"chi-square {_fmt(s.chi2, 1)}")


def faers_block(result) -> Optional[Dict[str, Any]]:
    """The unvalidated FAERS section: surfaced signals and how many co-reported events were suppressed."""
    items = [{"pair": list(p), "event": s.condition, "report_count": int(s.report_count),
              "prr": s.prr, "ror": s.ror, "ror_ci": [s.ror_ci_low, s.ror_ci_high], "chi2": s.chi2,
              "stats": faers_stats_text(s),
              "citation": {"source": s.source, "record_id": s.record_id, "text": f"{s.source}:{s.record_id}"},
              "line": (f"**{p[0]} + {p[1]}** — {s.condition}: {plural(int(s.report_count), 'report')}; "
                       f"{faers_stats_text(s)} {s.citation()}")}
             for p, sigs in result.faers_signals.items() for s in sigs]
    suppressed = sum(result.faers_suppressed.values())
    if not items and not suppressed:
        return None
    note = None
    if suppressed:
        note = (f"{plural(suppressed, 'co-reported event')} checked in FAERS "
                f"{'was' if suppressed == 1 else 'were'} suppressed: below these thresholds, or as common "
                "with one of the drugs alone.")
    return {"heading": FAERS_HEADING, "intro": FAERS_INTRO, "items": items, "suppressed": suppressed,
            "suppressed_note": note}


def faers_lines(block: Optional[Dict[str, Any]]) -> List[str]:
    if not block:
        return []
    lines = [f"## {block['heading']}", block["intro"]] + [f"- {i['line']}" for i in block["items"]]
    if block["suppressed_note"]:
        lines.append(block["suppressed_note"])
    return lines


def pair_grid(plan, findings, ungraded, signals, no_data) -> Dict[str, Any]:
    """Every checked pair once, with its most severe status and the report item it links to.

    drugs: the analysed drugs in the order entered (row i, column j < i is the pair drugs[i] + drugs[j]).
    """
    drugs = [d.generic_name.lower() for d in plan.resolved]
    index = {name: i for i, name in enumerate(drugs)}
    nd = {tuple(sorted(p)) for p in no_data}
    cells = []
    for a, b in plan.pairs:
        key = tuple(sorted((a, b)))
        status, ref = None, None
        for section, items in (("findings", findings), ("ungraded", ungraded), ("signals", signals)):
            for i, item in enumerate(items):
                if tuple(sorted(x.lower() for x in item["pair"])) == key:
                    status = item.get("severity", "signals only")
                    ref = {"section": section, "index": i}
                    break
            if status:
                break
        if status is None:
            if key not in nd:     # every retrieved pair has a report item; anything else is a bug
                raise ValueError(f"pair {a} + {b} has no report item and is not a no-data pair")
            status = "no curated data"
        row, col = sorted((index[a], index[b]), reverse=True)
        cells.append({"pair": [drugs[row], drugs[col]], "row": row, "col": col, "status": status, "ref": ref})
    cells.sort(key=lambda c: (c["row"], c["col"]))
    return {"drugs": drugs, "cells": cells}


def entries_markdown(ent: Dict[str, Any]) -> List[str]:
    if not ent["items"]:
        return []
    return ([f"## {ent['heading']}"] + [f"> {n['text']}" for n in ent["notices"]]
            + [f"- {e['line']}" for e in ent["items"]])


def render_markdown(s: Dict[str, Any]) -> List[str]:
    """Markdown lines (without the footer) written only from the structure."""
    from src.agents.generator import SEVERITY_HEADINGS
    lines = [f"# {s['title']}", ""]
    ent = entries_markdown(s["entries"])
    if ent:
        lines += ent + [""]
    lines += ["## Summary", s["summary"]["text"], ""]
    for tier in TIERS:
        rows = [f for f in s["findings"] if f["severity"] == tier]
        if rows:
            lines += [f"## {SEVERITY_HEADINGS[tier]}"] + [f"- {f['line']}" for f in rows] + [""]
    if s["ungraded"]["items"]:
        lines += [f"## {SEVERITY_HEADINGS['Unknown']}", s["ungraded"]["note"]]
        lines += [f"- {f['line']}" for f in s["ungraded"]["items"]] + [""]
    sig = s["signals"]
    if sig["items"]:
        lines += [f"## {sig['heading']}", sig["intro"]]
        hidden = list(sig["hidden"])
        for i, item in enumerate(sig["items"], start=1):
            lines.append(f"- {item['line']}")
            while hidden and hidden[0]["after"] == i:
                lines.append(f"- {hidden.pop(0)['line']}")
        lines += [f"- {h['line']}" for h in hidden] + [""]
    cov = s["coverage"]
    lines.append("## Coverage Notes")
    if cov["unresolved"]:
        lines += ["### Unresolved Inputs", cov["unresolved"]["intro"]]
        lines += [f"- {u['line']}" for u in cov["unresolved"]["items"]] + [""]
    if cov["no_data"]:
        nd = cov["no_data"]
        lines += ["### No Curated Interaction Data", nd["intro"]] + [f"- {a} + {b}" for a, b in nd["pairs"]]
        if nd["faers_note"]:
            lines.append(nd["faers_note"])
        lines.append("")
    if cov["all_covered"]:
        lines += [cov["all_covered"], ""]
    if s["faers"]:
        lines += faers_lines(s["faers"]) + [""]
    return lines

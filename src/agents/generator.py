"""Generator agent.

Produces the final clinical report from retrieved evidence. The prompt is
engineered around three anti-hallucination constraints:

  1. Every clinical claim MUST cite a specific source record_id.
  2. If no data was retrieved for a pair, the model MUST say so explicitly.
  3. The model must not invent mechanisms; if a mechanism is not in the source,
     say "Mechanism not specified in source".

The retrieved evidence is passed verbatim — the model's job is synthesis and
presentation, not recall.
"""
from __future__ import annotations

from typing import List, Optional

from src.agents.planner import RetrievalPlan
from src.agents.retriever import RetrievalResult
from src.config import Config, config as default_config
from src.llm import LLMClient


SYSTEM_PROMPT = """You are PharmGuard, a clinical decision-support assistant that reports drug-drug interactions and adverse-event signals from structured pharmaceutical databases.

You operate under four non-negotiable constraints:

1. CITE EVERY CLAIM. Every clinical statement must include an inline citation in the format [SOURCE:RECORD_ID]. Do not make claims that are not supported by the retrieved evidence.

2. NEVER FABRICATE. If no evidence was retrieved for a drug pair, you must state: "No interaction data available in the queried sources for [drug A] + [drug B]." Do not invent mechanisms, severities, or interactions.

3. QUOTE BEFORE PARAPHRASING. When describing a mechanism or condition, prefer language directly from the retrieved record. Do not add pharmacological detail that is not present in the evidence.

4. COVERAGE TRUTH. The Coverage Notes section must accurately reflect the evidence. If the evidence bundle shows pairs under "=== PAIRS WITH NO DATA ===", you must list ALL of those pairs in the Coverage Notes — do not summarize, do not omit. If no such section exists, you may state "All pairs had coverage." Do not claim coverage that is not in the evidence.

Your output format is structured markdown with these sections:
  - Summary (1-2 sentences stating number of drugs, pairs, and interaction records found)
  - Major Findings (severity = Major)
  - Moderate Findings (severity = Moderate)
  - Minor Findings (severity = Minor)
  - Coverage Notes (list unresolved inputs and no-data pairs exactly as given in evidence)
  - (Disclaimer is appended automatically by the system — do not add one.)

Omit any section that has no content. Be concise. A clinician reads this in 30 seconds. No fluff."""


class Generator:
    def __init__(self, cfg: Optional[Config] = None, llm: Optional[LLMClient] = None):
        self.cfg = cfg or default_config
        self.llm = llm  # Lazy init — allows dry-run without API key

    def generate(self, plan: RetrievalPlan, result: RetrievalResult) -> str:
        if self.llm is None:
            self.llm = LLMClient(self.cfg)

        evidence = self._format_evidence(plan, result)
        user_message = self._build_user_message(plan, result, evidence)

        report = self.llm.complete(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        # Always append the disclaimer — this is a safety invariant, not a model choice
        if "disclaimer" not in report.lower():
            report += f"\n\n---\n**Disclaimer.** {self.cfg.disclaimer}"

        return report

    # ---------- deterministic report (no LLM) ----------
    # Useful for testing, offline mode, and as a fallback if the LLM call fails.

    def generate_deterministic(self, plan: RetrievalPlan, result: RetrievalResult) -> str:
        lines = ["# PharmGuard Interaction Report", ""]

        # Summary
        lines.append("## Summary")
        lines.append(
            f"Analyzed {plan.num_drugs} medication(s) across {plan.num_pairs} unique pair(s). "
            f"Retrieved {result.total_interactions} interaction record(s) from structured sources."
        )
        lines.append("")

        # Group by severity
        buckets = {"Major": [], "Moderate": [], "Minor": [], "Unknown": []}
        for pair, records in result.interactions.items():
            for r in records:
                buckets.get(r.severity, buckets["Unknown"]).append((pair, r))

        for label in ("Major", "Moderate", "Minor"):
            if buckets[label]:
                lines.append(f"## {label} Findings")
                for pair, r in buckets[label]:
                    lines.append(
                        f"- **{r.drug_a} + {r.drug_b}** — {r.condition} "
                        f"(PRR={r.prr:.2f}) {r.citation()}"
                        if r.prr is not None
                        else f"- **{r.drug_a} + {r.drug_b}** — {r.condition} {r.citation()}"
                    )
                lines.append("")

        # Coverage
        lines.append("## Coverage Notes")
        if plan.unresolved:
            lines.append(
                "**Unresolved inputs:** "
                + ", ".join(u.query for u in plan.unresolved)
                + " — these were not matched to any drug in the RxNorm/DrugBank vocabulary and were excluded."
            )
        if result.no_data_pairs:
            lines.append(
                f"**No data found** for {len(result.no_data_pairs)} pair(s): "
                + ", ".join(f"{a}+{b}" for a, b in result.no_data_pairs[:5])
                + ("..." if len(result.no_data_pairs) > 5 else "")
            )
        if not plan.unresolved and not result.no_data_pairs:
            lines.append("All inputs resolved; all pairs had coverage in queried sources.")
        lines.append("")

        # Disclaimer
        lines.append("---")
        lines.append(f"**Disclaimer.** {self.cfg.disclaimer}")

        return "\n".join(lines)

    # ---------- helpers ----------

    def _format_evidence(self, plan: RetrievalPlan, result: RetrievalResult) -> str:
        blocks: List[str] = []

        blocks.append("=== INTERACTION EVIDENCE ===")
        if not result.interactions:
            blocks.append("(No interaction records retrieved for any pair.)")
        for pair, records in result.interactions.items():
            blocks.append(f"\nPair: {pair[0]} + {pair[1]}")
            for r in records:
                prr = f"{r.prr:.2f}" if r.prr is not None else "n/a"
                freq = f"{r.frequency:.4f}" if r.frequency is not None else "n/a"
                blocks.append(
                    f"  - [{r.source}:{r.record_id}] severity={r.severity}, "
                    f"condition={r.condition}, PRR={prr}, freq={freq}"
                )

        if result.side_effects:
            blocks.append("\n=== SIDE-EFFECT CONTEXT (SIDER) ===")
            for drug, ses in result.side_effects.items():
                top = ", ".join(s.side_effect for s in ses[:5])
                blocks.append(f"  {drug}: {top}")

        if result.no_data_pairs:
            blocks.append("\n=== PAIRS WITH NO DATA ===")
            for a, b in result.no_data_pairs:
                blocks.append(f"  - {a} + {b}: no record in queried sources")

        if plan.unresolved:
            blocks.append("\n=== UNRESOLVED INPUTS ===")
            for u in plan.unresolved:
                blocks.append(f"  - '{u.query}': could not be matched to a known drug")

        return "\n".join(blocks)

    def _build_user_message(self, plan: RetrievalPlan, result: RetrievalResult, evidence: str) -> str:
        drugs = ", ".join(d.generic_name for d in plan.resolved)
        return (
            f"Patient medication list (canonical names): {drugs}\n\n"
            f"Evidence retrieved from pharmaceutical databases:\n\n{evidence}\n\n"
            "Generate the PharmGuard interaction report using ONLY the evidence above. "
            "Cite every clinical claim with [SOURCE:RECORD_ID]. For pairs with no data, "
            "state this explicitly. Do not introduce any mechanism, severity, or interaction "
            "that is not present in the evidence block."
        )

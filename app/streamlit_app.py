"""PharmGuard AI — Streamlit UI.

Run with:
    streamlit run app/streamlit_app.py

Uses the LangGraph orchestration (src/graph). For comparison, the pre-LangGraph
pipeline runs with:
    PHARMGUARD_PIPELINE=legacy streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from src.graph import REPORT_SOURCES, PharmGuardGraph, Settings
from src.graph.settings import KEY_VARS
from src.input_validation import InvalidDrugNameError

LEGACY = os.getenv("PHARMGUARD_PIPELINE", "graph").lower() == "legacy"

# ---------- page setup ----------
st.set_page_config(
    page_title="PharmGuard AI",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("💊 PharmGuard AI")
st.caption(
    "Drug-interaction reports from a RAG system with deterministic planning. "
    "Every claim cites a source record; LLM reports are shown only if they pass validation."
)


# ---------- cached resources ----------
@st.cache_resource
def load_settings() -> Settings:
    return Settings.from_env()


@st.cache_resource
def load_graphs():
    graph = PharmGuardGraph(load_settings())
    return {"llm": graph.with_mode("llm"), "deterministic": graph.with_mode("deterministic")}


@st.cache_resource
def load_legacy_pipeline():
    from src.pipeline import PharmGuardPipeline
    return PharmGuardPipeline.from_config()


settings = load_settings()

# ---------- sidebar ----------
with st.sidebar:
    st.header("Settings")
    if settings.llm_configured:
        use_llm = st.toggle(
            "Use LLM for report generation",
            value=True,
            help=f"Model: {settings.llm_provider}:{settings.model_id}. The LLM report is checked against "
                 "the retrieved evidence; if it fails twice, the deterministic template is shown.",
        )
    else:
        use_llm = st.toggle("Use LLM for report generation", value=False, disabled=True)
        key_var = KEY_VARS.get(settings.llm_provider, "an API key")
        st.caption(f"LLM mode is off: no {key_var} is configured (set it in `.env`). "
                   "Reports use the deterministic template, which needs no API key.")
    if LEGACY:
        st.info("Running the legacy (pre-LangGraph) pipeline for comparison.")
    st.markdown("---")
    st.markdown(
        "**About.** PharmGuard is a decision-support prototype, not a substitute for "
        "professional medical judgment. It reports only what its loaded data contains; "
        "the data currently loaded is a small synthetic sample."
    )


# ---------- main input ----------
# Process example-button clicks BEFORE rendering the text area.
# This is the Streamlit way: widget state must be set before the widget is created.

# Initialize the text area's session state key
if "drug_input" not in st.session_state:
    st.session_state.drug_input = ""

examples = {
    "Geriatric (proposal)": "lisinopril, spironolactone, metformin, atorvastatin, aspirin, omeprazole, sertraline",
    "Post-MI": "aspirin, clopidogrel, atorvastatin, metoprolol, lisinopril, omeprazole",
    "Warfarin + NSAID": "warfarin, ibuprofen",
    "AFib cocktail": "warfarin, digoxin, amiodarone, atorvastatin, lisinopril",
}


def _load_example(value: str) -> None:
    """Callback: write to the text area's session state key."""
    st.session_state.drug_input = value


col_input, col_examples = st.columns([3, 1])

with col_input:
    raw = st.text_area(
        "Enter medications (one per line, or comma-separated):",
        height=140,
        placeholder="lisinopril\nspironolactone\nmetformin\naspirin",
        key="drug_input",
    )

with col_examples:
    st.markdown("**Try an example:**")
    for label, value in examples.items():
        st.button(
            label,
            key=f"ex_{label}",
            width="stretch",
            on_click=_load_example,
            args=(value,),
        )

# Parse input
drugs = []
if raw.strip():
    for line in raw.replace(",", "\n").splitlines():
        name = line.strip()
        if name:
            drugs.append(name)

go = st.button("Analyze interactions", type="primary", disabled=not drugs)


def _processed_data_error(e: Exception) -> None:
    st.error(
        "Processed data not found. Run `python scripts/ingest_data.py --sample` "
        "(or `--full` if you have datasets in data/raw/) first."
    )
    st.code(str(e))
    st.stop()


def _show_graph_result(state: dict, n_inputs: int) -> None:
    plan, retrieval = state["plan"], state.get("retrieval") or {}
    interactions = retrieval.get("interactions", [])
    no_data = retrieval.get("no_data_pairs", [])

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Drugs resolved", f"{len(plan['resolved'])}/{n_inputs}")
    m2.metric("Pairs analyzed", len(plan["pairs"]))
    m3.metric("Interactions found", sum(len(x["records"]) for x in interactions))
    m4.metric("Latency", f"{state['latency_seconds']:.2f}s")

    if plan["unresolved"]:
        st.warning("**Unresolved inputs** (excluded from analysis): "
                   + ", ".join(f"`{u['query']}`" for u in plan["unresolved"]))

    st.markdown("---")
    source = state["report_source"]
    text = f"**Report source:** {REPORT_SOURCES[source]}"
    if source == "deterministic_fallback":
        st.warning(text + " See the pipeline trace below for the validator's findings.")
    else:
        st.info(text)
    st.markdown(state["report"])

    with st.expander("🔍 Evidence audit trail"):
        st.caption("Exactly what was retrieved from the knowledge base.")
        if not interactions:
            st.info("No interaction records retrieved.")
        for x in interactions:
            st.markdown(f"**{x['pair'][0]} + {x['pair'][1]}**")
            for r in x["records"]:
                st.json(r)

    with st.expander("📊 No-data pairs (explicit uncertainty)"):
        if not no_data:
            st.success("All pairs had coverage.")
        for a, b in no_data:
            st.markdown(f"- `{a}` + `{b}` — no record in queried sources")

    with st.expander("⚙️ Pipeline trace"):
        st.caption("Trajectory: one row per graph node, in execution order.")
        st.dataframe(
            [{"node": t["node"], "status": t["status"], "ms": t["ms"]} for t in state["trajectory"]],
            width="stretch",
        )
        for t in state["trajectory"]:
            st.markdown(f"**{t['node']}** · {t['status']} · {t['ms']} ms")
            st.json(t["detail"], expanded=False)
        st.markdown("**Final report validation**")
        st.json(state["final_validation"], expanded=False)


def _show_legacy_result(result, n_inputs: int) -> None:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Drugs resolved", f"{result.plan.num_drugs}/{n_inputs}")
    m2.metric("Pairs analyzed", result.plan.num_pairs)
    m3.metric("Interactions found", result.retrieval.total_interactions)
    m4.metric("Latency", f"{result.latency_seconds:.2f}s")
    st.markdown("---")
    st.caption(f"Legacy pipeline · report_source = {result.trace.get('report_source')}")
    st.markdown(result.report)
    with st.expander("⚙️ Pipeline trace"):
        st.json(result.trace)


# ---------- run ----------
if go:
    if len(drugs) > 12:
        st.error(f"Input contains {len(drugs)} drugs. MVP supports up to 12.")
        st.stop()

    with st.spinner(f"Analyzing {len(drugs)} medications..."):
        try:
            if LEGACY:
                result = load_legacy_pipeline().run(drugs, use_llm=use_llm)
            else:
                # With no key the LLM-mode graph routes to the template itself and
                # reports deterministic_no_llm, which says why no LLM was used.
                mode = "llm" if (use_llm or not settings.llm_configured) else "deterministic"
                state = load_graphs()[mode].run(drugs)
        except FileNotFoundError as e:
            _processed_data_error(e)
        except InvalidDrugNameError as e:
            st.error(str(e))
            st.stop()

    if LEGACY:
        _show_legacy_result(result, len(drugs))
    else:
        _show_graph_result(state, len(drugs))


# ---------- footer ----------
st.markdown("---")
st.caption(
    "⚠️ Decision-support prototype. Not a substitute for professional medical judgment. "
    "Always consult a licensed clinician or pharmacist."
)

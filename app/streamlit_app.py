"""PharmGuard AI — Streamlit UI.

Run with:
    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from src.pipeline import PharmGuardPipeline


# ---------- page setup ----------
st.set_page_config(
    page_title="PharmGuard AI",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("💊 PharmGuard AI")
st.caption(
    "Grounded drug interaction detection — plan, retrieve, generate. "
    "Every claim traces to a source record."
)


# ---------- cached pipeline ----------
@st.cache_resource
def load_pipeline():
    return PharmGuardPipeline.from_config()


# ---------- sidebar ----------
with st.sidebar:
    st.header("Settings")
    use_llm = st.toggle(
        "Use LLM for report generation",
        value=True,
        help="If off, uses a deterministic template that requires no API key.",
    )
    st.markdown("---")
    st.markdown(
        "**About.** PharmGuard is a decision-support tool grounded in structured "
        "pharmaceutical databases (TWOSIDES, DrugBank, SIDER, RxNorm). It is not "
        "a substitute for professional medical judgment."
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
            use_container_width=True,
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


# ---------- run ----------
if go:
    if len(drugs) > 12:
        st.error(f"Input contains {len(drugs)} drugs. MVP supports up to 12.")
        st.stop()

    try:
        pipeline = load_pipeline()
    except FileNotFoundError as e:
        st.error(
            "Processed data not found. Run `python scripts/ingest_data.py --sample` "
            "(or `--full` if you have datasets in data/raw/) first."
        )
        st.code(str(e))
        st.stop()

    with st.spinner(f"Analyzing {len(drugs)} medications..."):
        result = pipeline.run(drugs, use_llm=use_llm)

    # ---------- header metrics ----------
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Drugs resolved", f"{result.plan.num_drugs}/{len(drugs)}")
    m2.metric("Pairs analyzed", result.plan.num_pairs)
    m3.metric("Interactions found", result.retrieval.total_interactions)
    m4.metric("Latency", f"{result.latency_seconds:.2f}s")

    # ---------- unresolved warning ----------
    if result.plan.unresolved:
        st.warning(
            "**Unresolved inputs** (excluded from analysis): "
            + ", ".join(f"`{u.query}`" for u in result.plan.unresolved)
        )

    # ---------- report ----------
    st.markdown("---")
    st.markdown(result.report)

    # ---------- evidence audit trail ----------
    with st.expander("🔍 Evidence audit trail"):
        st.caption("Exactly what was retrieved from the knowledge base.")
        if not result.retrieval.interactions:
            st.info("No interaction records retrieved.")
        for pair, records in result.retrieval.interactions.items():
            st.markdown(f"**{pair[0]} + {pair[1]}**")
            for r in records:
                st.json(r.to_dict())

    with st.expander("📊 No-data pairs (explicit uncertainty)"):
        if not result.retrieval.no_data_pairs:
            st.success("All pairs had coverage.")
        else:
            for a, b in result.retrieval.no_data_pairs:
                st.markdown(f"- `{a}` + `{b}` — no record in queried sources")

    with st.expander("⚙️ Pipeline trace"):
        st.json(result.trace)


# ---------- footer ----------
st.markdown("---")
st.caption(
    "⚠️ Decision-support tool. Not a substitute for professional medical judgment. "
    "Always consult a licensed clinician or pharmacist."
)

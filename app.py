import streamlit as st

st.set_page_config(
    page_title="DrillSense AI",
    page_icon="🛢️",
    layout="wide"
)

st.title("🛢️ DrillSense AI")
st.subheader("AI-Powered Drilling Performance & Lost Time Intelligence")

st.write(
    "A data-driven decision-support platform for analyzing "
    "Total Drilling Lost Time (TDLT), NPT, ILT, drilling causes, "
    "and potential time and cost savings."
)

st.info("TDLT = NPT + ILT")

st.success("DrillSense AI is successfully running.")

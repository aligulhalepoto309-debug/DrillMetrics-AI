
import io
import re
import pandas as pd
import streamlit as st
from pypdf import PdfReader

st.set_page_config(
    page_title="DrillSense AI",
    page_icon="🛢️",
    layout="wide",
)

st.title("🛢️ DrillSense AI")
st.subheader("Unified Lost Time Quantification & Decision Support")
st.caption("Drilling Performance and Lost Time Intelligence")
st.info("TDLT = NPT + ILT")

REQUIRED = [
    "Well_ID",
    "Report_Date",
    "Operation_Type",
    "Hole_Section",
    "Actual_Duration_hr",
    "Validated_NPT_hr",
]

KEYWORDS = [
    "malfunction", "failure", "breakdown", "stuck",
    "lost circulation", "equipment problem",
    "equipment failure", "washout", "fishing",
    "repair", "leak", "stalled", "plugged",
    "damage", "unable to", "power tong",
    "top drive", "motor failure", "motor/vfd",
    "motor vfd", "npt",
]

# ---------------------------------------------------------
# ROOT CAUSE CATEGORIES AND SUGGESTED REMEDIES
# These are preliminary rules, not confirmed diagnoses.
# ---------------------------------------------------------

CAUSES = {
    "Equipment malfunction": {
        "keywords": [
            "power tong", "top drive", "motor failure",
            "motor/vfd", "motor vfd", "malfunction",
            "equipment failure", "equipment problem",
            "mechanical failure", "breakdown", "pump failure",
        ],
        "remedy": (
            "Inspect the affected equipment and associated systems. "
            "Review maintenance history, fault logs, spare-parts "
            "availability, and the approved repair procedure."
        ),
    },
    "Lost circulation / fluid loss": {
        "keywords": [
            "lost circulation", "loss circulation",
            "lost returns", "loss of returns", "mud loss",
        ],
        "remedy": (
            "Review mud properties, loss intervals, formation "
            "conditions, and fluid-loss records. Evaluate suitable "
            "loss-control measures under the approved drilling programme."
        ),
    },
    "Stuck pipe / restricted movement": {
        "keywords": [
            "stuck pipe", "pipe stuck", "stuck drillstring",
            "differential sticking", "pack off", "pack-off",
        ],
        "remedy": (
            "Review hole-cleaning records, drilling parameters, "
            "wellbore conditions, and the sequence preceding the event. "
            "Follow the approved stuck-pipe response procedure."
        ),
    },
    "Washout / leakage": {
        "keywords": [
            "washout", "leak", "leakage", "fluid leak",
        ],
        "remedy": (
            "Inspect the affected component and connections. Verify "
            "pressure-test and maintenance records, identify the leak "
            "location, and follow the approved repair and testing procedure."
        ),
    },
    "Fishing / recovery operation": {
        "keywords": [
            "fishing", "fish in hole", "lost tool",
            "retrieval operation",
        ],
        "remedy": (
            "Review the incident timeline, fish description, and "
            "previous recovery attempts. Evaluate the approved fishing "
            "programme and confirm equipment readiness."
        ),
    },
    "Operational delay": {
        "keywords": [
            "waiting on", "unable to proceed", "operational delay",
            "waiting for", "delay in operation",
        ],
        "remedy": (
            "Verify the reason and duration of the delay. Review "
            "personnel, materials, service coordination, and operational "
            "planning to identify practical opportunities for improvement."
        ),
    },
}


def read_pdf(uploaded_file):
    reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
    parts = []

    for number, page in enumerate(reader.pages, start=1):
        parts.append(
            f"PAGE {number}\n{page.extract_text() or ''}"
        )

    return "\n".join(parts)


def detect_incidents(text):
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    incidents = []
    seen = set()

    for i, line in enumerate(lines):
        if not any(k in line.lower() for k in KEYWORDS):
            continue

        evidence = " | ".join(
            lines[max(0, i - 1):min(len(lines), i + 2)]
        )

        if evidence in seen:
            continue

        seen.add(evidence)
        duration = 0.0

        hour_match = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:hours|hour|hrs|hr)\b",
            evidence,
            re.IGNORECASE,
        )

        time_match = re.search(
            r"(\d{1,2}:\d{2})\s*(?:to|-)\s*(\d{1,2}:\d{2})",
            evidence,
            re.IGNORECASE,
        )

        if hour_match:
            duration = float(hour_match.group(1))

        elif time_match:
            def to_minutes(value):
                h, m = map(int, value.split(":"))
                return h * 60 + m

            start = to_minutes(time_match.group(1))
            end = to_minutes(time_match.group(2))

            if end < start:
                end += 24 * 60

            duration = (end - start) / 60

        incidents.append({
            "Confirm as NPT": False,
            "Incident / Evidence": evidence,
            "Duration (hours)": duration,
        })

    return incidents


def classify_cause(evidence):
    text = str(evidence).lower()

    for category, details in CAUSES.items():
        if any(keyword in text for keyword in details["keywords"]):
            return category

    return "Unclassified - requires review"


def recommend_remedy(category):
    if category in CAUSES:
        return CAUSES[category]["remedy"]

    return (
        "Review the original DDR and consult the drilling team. "
        "Confirm the event mechanism before selecting a corrective action."
    )


def calculate_matrix(data):
    df = data.copy()

    for col in ["Actual_Duration_hr", "Validated_NPT_hr"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df[
        ["Actual_Duration_hr", "Validated_NPT_hr"]
    ].isna().any().any():
        raise ValueError(
            "Actual_Duration_hr and Validated_NPT_hr must contain numbers."
        )

    if (df["Actual_Duration_hr"] < 0).any():
        raise ValueError("Actual durations cannot be negative.")

    if (df["Validated_NPT_hr"] < 0).any():
        raise ValueError("NPT durations cannot be negative.")

    if (
        df["Validated_NPT_hr"] > df["Actual_Duration_hr"]
    ).any():
        raise ValueError(
            "Validated NPT cannot exceed actual operation duration."
        )

    df["Adjusted_Duration_hr"] = (
        df["Actual_Duration_hr"] - df["Validated_NPT_hr"]
    )

    df["Benchmark_Duration_hr"] = (
        df.groupby(["Operation_Type", "Hole_Section"])
        ["Adjusted_Duration_hr"]
        .transform("median")
    )

    df["Potential_ILT_hr"] = (
        df["Adjusted_Duration_hr"] - df["Benchmark_Duration_hr"]
    ).clip(lower=0)

    df["TDLT_hr"] = (
        df["Validated_NPT_hr"] + df["Potential_ILT_hr"]
    )

    return df


def csv_bytes(data):
    return data.to_csv(index=False).encode("utf-8")


def show_root_cause_analysis(evidence_data):
    st.header("Root-Cause Analysis & Remedy Recommendations")

    st.write(
        "The system suggests preliminary cause categories from the "
        "recorded evidence. Review and correct every suggestion before "
        "using it in engineering decisions."
    )

    analyzed = evidence_data.copy()

    if "Incident / Evidence" not in analyzed.columns:
        st.info(
            "This dataset does not contain an incident-evidence column. "
            "Root-cause classification requires event descriptions or "
            "DDR evidence; it cannot be reliably inferred from duration "
            "values alone."
        )
        return

    analyzed["Suggested Cause"] = analyzed[
        "Incident / Evidence"
    ].apply(classify_cause)

    analyzed["Suggested Remedy"] = analyzed[
        "Suggested Cause"
    ].apply(recommend_remedy)

    analyzed["Reviewed Cause"] = analyzed["Suggested Cause"]

    edited = st.data_editor(
        analyzed,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Reviewed Cause": st.column_config.SelectboxColumn(
                "Reviewed Cause",
                options=list(CAUSES.keys()) + [
                    "Unclassified - requires review",
                    "Other - manual review",
                ],
                required=True,
            ),
            "Suggested Cause": st.column_config.TextColumn(
                "System-suggested category",
                disabled=True,
            ),
            "Suggested Remedy": st.column_config.TextColumn(
                "Suggested remedy",
                disabled=True,
            ),
        },
    )

    # Recompute the remedy from the reviewer's chosen category.
    edited["Final Remedy"] = edited["Reviewed Cause"].apply(
        recommend_remedy
    )

    st.subheader("Reviewed root-cause and remedy table")
    st.dataframe(
        edited,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download root-cause analysis (CSV)",
        data=csv_bytes(edited),
        file_name="drillsense_root_cause_analysis.csv",
        mime="text/csv",
    )


# =========================================================
# MAIN WORKFLOW SELECTION
# =========================================================

st.header("1. Select Data Source")

mode = st.radio(
    "Choose workflow",
    [
        "Operation Dataset (CSV / Excel)",
        "DDR PDF Review",
    ],
    horizontal=True,
)

# =========================================================
# WORKFLOW A: OPERATION DATASET
# =========================================================

if mode == "Operation Dataset (CSV / Excel)":

    uploaded = st.file_uploader(
        "Upload operation dataset",
        type=["csv", "xlsx"],
    )

    st.caption(
        "Required columns: Well_ID, Report_Date, Operation_Type, "
        "Hole_Section, Actual_Duration_hr, Validated_NPT_hr."
    )

    if uploaded is not None:
        try:
            if uploaded.name.lower().endswith(".csv"):
                raw = pd.read_csv(uploaded)
            else:
                raw = pd.read_excel(uploaded)

            missing = [c for c in REQUIRED if c not in raw.columns]

            if missing:
                st.error(
                    "Missing required columns: " + ", ".join(missing)
                )
                st.write("Columns detected:", list(raw.columns))
                st.dataframe(raw.head(50), use_container_width=True)

            elif raw[
                ["Well_ID", "Operation_Type", "Hole_Section"]
            ].isna().any().any():
                st.error(
                    "Well_ID, Operation_Type, and Hole_Section "
                    "must not be blank."
                )

            else:
                synthetic = (
                    "Source_Reference" in raw.columns
                    and "Review_Status" in raw.columns
                )

                if synthetic:
                    st.warning(
                        "SYNTHETIC DEMONSTRATION MODE: the data is "
                        "simulated and does not establish actual field "
                        "performance or validated Lower Indus Basin results."
                    )
                else:
                    st.info(
                        "Structured data detected. Verify the source, "
                        "units, NPT labels, and benchmark suitability."
                    )

                matrix = calculate_matrix(raw)

                if "Review_Status" not in matrix.columns:
                    matrix["Review_Status"] = "Requires verification"

                st.header("2. Filter Operation Records")

                col1, col2, col3 = st.columns(3)

                wells = sorted(matrix["Well_ID"].astype(str).unique())
                operations = sorted(
                    matrix["Operation_Type"].astype(str).unique()
                )
                sections = sorted(
                    matrix["Hole_Section"].astype(str).unique()
                )

                with col1:
                    selected_wells = st.multiselect(
                        "Well",
                        wells,
                        default=wells,
                    )

                with col2:
                    selected_operations = st.multiselect(
                        "Operation",
                        operations,
                        default=operations,
                    )

                with col3:
                    selected_sections = st.multiselect(
                        "Hole section",
                        sections,
                        default=sections,
                    )

                view = matrix[
                    matrix["Well_ID"].astype(str).isin(selected_wells)
                    & matrix["Operation_Type"].astype(str).isin(
                        selected_operations
                    )
                    & matrix["Hole_Section"].astype(str).isin(
                        selected_sections
                    )
                ].copy()

                st.header("3. Unified Lost Time Summary")

                npt_total = view["Validated_NPT_hr"].sum()
                ilt_total = view["Potential_ILT_hr"].sum()
                tdlt_total = view["TDLT_hr"].sum()

                a, b, c, d = st.columns(4)
                a.metric("Records", len(view))
                b.metric("NPT (hr)", f"{npt_total:.2f}")
                c.metric("Potential ILT (hr)", f"{ilt_total:.2f}")
                d.metric("TDLT (hr)", f"{tdlt_total:.2f}")

                st.header("4. Unified NPT–ILT Matrix")

                columns = [
                    "Well_ID",
                    "Report_Date",
                    "Operation_Type",
                    "Hole_Section",
                    "Actual_Duration_hr",
                    "Validated_NPT_hr",
                    "Adjusted_Duration_hr",
                    "Benchmark_Duration_hr",
                    "Potential_ILT_hr",
                    "TDLT_hr",
                    "Review_Status",
                ]

                columns = [c for c in columns if c in view.columns]

                st.dataframe(
                    view[columns].round(2),
                    use_container_width=True,
                    hide_index=True,
                )

                st.header("5. Calculation Method")

                st.latex(
                    r"\text{Adjusted Duration} = "
                    r"\text{Actual Duration} - \text{NPT}"
                )
                st.latex(
                    r"\text{Potential ILT} = "
                    r"\max(0,\text{Adjusted Duration} - \text{Benchmark})"
                )
                st.latex(r"\text{TDLT} = \text{NPT} + \text{Potential ILT}")

                st.caption(
                    "The benchmark is the median adjusted duration "
                    "for each operation type and hole section. Potential "
                    "ILT requires technical review and may reflect "
                    "legitimate operational differences."
                )

                st.header("6. Operation Summary")

                summary = (
                    view.groupby(
                        ["Operation_Type", "Hole_Section"],
                        as_index=False,
                    )
                    .agg(
                        Record_Count=("Well_ID", "count"),
                        Actual_Duration_hr=("Actual_Duration_hr", "sum"),
                        Validated_NPT_hr=("Validated_NPT_hr", "sum"),
                        Potential_ILT_hr=("Potential_ILT_hr", "sum"),
                        TDLT_hr=("TDLT_hr", "sum"),
                    )
                )

                st.dataframe(
                    summary.round(2),
                    use_container_width=True,
                    hide_index=True,
                )

                if not summary.empty:
                    st.bar_chart(
                        summary.set_index("Operation_Type")[
                            ["Validated_NPT_hr", "Potential_ILT_hr"]
                        ]
                    )

                st.header("7. Root-Cause Analysis")

                evidence_columns = [
                    "Incident / Evidence",
                    "Incident",
                    "Event_Description",
                    "Description",
                    "Event",
                ]

                evidence_col = next(
                    (
                        c for c in evidence_columns
                        if c in view.columns
                    ),
                    None,
                )

                if evidence_col:
                    cause_input = view.copy()
                    if evidence_col != "Incident / Evidence":
                        cause_input["Incident / Evidence"] = (
                            cause_input[evidence_col]
                        )
                    show_root_cause_analysis(cause_input)
                else:
                    st.info(
                        "Your operation dataset has no event-description "
                        "column, so root causes cannot be reliably inferred "
                        "from the operation durations alone. Use DDR PDF "
                        "Review to classify documented incidents, or add "
                        "an Incident / Evidence column to your dataset."
                    )

                st.header("8. Download Results")

                st.download_button(
                    "Download Unified Matrix CSV",
                    data=csv_bytes(view),
                    file_name="drillsense_unified_matrix.csv",
                    mime="text/csv",
                )

                st.download_button(
                    "Download Operation Summary CSV",
                    data=csv_bytes(summary),
                    file_name="drillsense_operation_summary.csv",
                    mime="text/csv",
                )

        except Exception as error:
            st.error(f"Could not process the dataset: {error}")


# =========================================================
# WORKFLOW B: DDR PDF REVIEW
# =========================================================

else:

    st.header("DDR Incident Review")

    pdf = st.file_uploader(
        "Upload Daily Drilling Report PDF",
        type=["pdf"],
    )

    if pdf is not None:
        try:
            text = read_pdf(pdf)

            with st.expander("View extracted report text"):
                st.text(text[:20000])

            incidents = detect_incidents(text)

            if not incidents:
                st.warning(
                    "No potential incidents were automatically detected. "
                    "Review the extracted report text manually."
                )

            else:
                st.write(
                    "Confirm each event and verify its duration "
                    "against the original DDR."
                )

                review = pd.DataFrame(incidents)

                edited = st.data_editor(
                    review,
                    use_container_width=True,
                    hide_index=True,
                    num_rows="dynamic",
                    column_config={
                        "Confirm as NPT": st.column_config.CheckboxColumn(
                            "Confirm as NPT"
                        ),
                        "Duration (hours)": st.column_config.NumberColumn(
                            "Duration (hours)",
                            min_value=0.0,
                            step=0.25,
                        ),
                    },
                )

                confirmed = edited[
                    edited["Confirm as NPT"] == True
                ].copy()

                confirmed["Duration (hours)"] = pd.to_numeric(
                    confirmed["Duration (hours)"],
                    errors="coerce",
                )

                invalid = (
                    confirmed["Duration (hours)"].isna().any()
                    or (confirmed["Duration (hours)"] < 0).any()
                )

                if invalid:
                    st.error(
                        "Confirmed NPT durations must be valid "
                        "non-negative numbers."
                    )
                    st.stop()

                npt = confirmed["Duration (hours)"].sum()

                st.metric("Confirmed NPT (hours)", f"{npt:.2f}")

                st.header("ILT Benchmark and Evidence")

                st.write(
                    "Use comparable operation records or another "
                    "documented benchmark. Avoid double-counting NPT."
                )

                evidence = st.text_area(
                    "Document benchmark, source, and justification",
                    placeholder=(
                        "Describe the comparable operation, reference "
                        "duration, source records, and justification."
                    ),
                )

                ilt = st.number_input(
                    "Potential ILT (hours)",
                    min_value=0.0,
                    value=0.0,
                    step=0.25,
                )

                if evidence.strip():
                    tdlt = npt + ilt

                    st.header("Unified Lost Time Result")

                    x, y, z = st.columns(3)
                    x.metric("NPT (hr)", f"{npt:.2f}")
                    y.metric("Potential ILT (hr)", f"{ilt:.2f}")
                    z.metric("TDLT (hr)", f"{tdlt:.2f}")

                    result = pd.DataFrame([{
                        "Report_File": pdf.name,
                        "Validated_NPT_hr": npt,
                        "Potential_ILT_hr": ilt,
                        "TDLT_hr": tdlt,
                        "ILT_Benchmark_Evidence": evidence,
                    }])

                    st.dataframe(
                        result,
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.download_button(
                        "Download TDLT Summary CSV",
                        data=csv_bytes(result),
                        file_name="drillsense_ddr_tdlt_summary.csv",
                        mime="text/csv",
                    )

                    st.download_button(
                        "Download Reviewed NPT Events CSV",
                        data=csv_bytes(edited),
                        file_name="drillsense_reviewed_npt.csv",
                        mime="text/csv",
                    )

                else:
                    st.info(
                        "Enter documented benchmark evidence before "
                        "finalizing the combined TDLT result."
                    )

                st.header("Root-Cause Analysis & Remedy Recommendations")

                cause_data = edited[
                    edited["Confirm as NPT"] == True
                ].copy()

                if not cause_data.empty:
                    show_root_cause_analysis(cause_data)
                else:
                    st.info(
                        "Confirm at least one event as NPT to begin "
                        "reviewing root causes and remedies."
                    )

        except Exception as error:
            st.error(f"Could not read the PDF: {error}")


st.divider()
st.caption(
    "Research prototype: automated categories are preliminary suggestions. "
    "Verify source evidence and technical recommendations before use. "
    "Synthetic results do not represent validated field performance."
)

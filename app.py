
import io
import re
import pandas as pd
import streamlit as st
from pypdf import PdfReader

st.set_page_config(
    page_title="DrillSense AI",
    page_icon="🛢️",
    layout="wide"
)

st.title("🛢️ DrillSense AI")
st.subheader("Unified Lost Time Quantification Matrix")
st.caption("Drilling Performance & Lost Time Intelligence")
st.info("Core equation: TDLT = NPT + ILT")

st.write(
    "DrillSense AI combines Non-Productive Time (NPT) and "
    "Invisible Lost Time (ILT) in one matrix for drilling "
    "performance analysis."
)

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
    "motor vfd", "npt"
]


def read_pdf(uploaded_file):
    reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        pages.append(
            f"PAGE {number}\n{page.extract_text() or ''}"
        )
    return "\n".join(pages)


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

        context = " | ".join(
            lines[max(0, i - 1):min(len(lines), i + 2)]
        )

        if context in seen:
            continue
        seen.add(context)

        duration = 0.0

        hour_match = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:hours|hour|hrs|hr)\b",
            context,
            re.IGNORECASE
        )

        time_match = re.search(
            r"(\d{1,2}:\d{2})\s*(?:to|-)\s*(\d{1,2}:\d{2})",
            context,
            re.IGNORECASE
        )

        if hour_match:
            duration = float(hour_match.group(1))
        elif time_match:
            def minutes(value):
                h, m = map(int, value.split(":"))
                return h * 60 + m

            start = minutes(time_match.group(1))
            end = minutes(time_match.group(2))

            if end < start:
                end += 24 * 60

            duration = (end - start) / 60

        incidents.append({
            "Confirm as NPT": False,
            "Incident / Evidence": context,
            "Duration (hours)": duration,
        })

    return incidents


def calculate_matrix(data):
    df = data.copy()

    for col in ["Actual_Duration_hr", "Validated_NPT_hr"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df[["Actual_Duration_hr", "Validated_NPT_hr"]].isna().any().any():
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
            "NPT cannot exceed the actual operation duration."
        )

    # Remove validated NPT before estimating excess operation time.
    df["Adjusted_Duration_hr"] = (
        df["Actual_Duration_hr"] - df["Validated_NPT_hr"]
    )

    # Benchmark comparable operations by operation type and hole section.
    df["Benchmark_Duration_hr"] = (
        df.groupby(["Operation_Type", "Hole_Section"])
        ["Adjusted_Duration_hr"]
        .transform("median")
    )

    # Potential ILT is adjusted duration above the benchmark.
    df["Potential_ILT_hr"] = (
        df["Adjusted_Duration_hr"] - df["Benchmark_Duration_hr"]
    ).clip(lower=0)

    # Unified total.
    df["TDLT_hr"] = (
        df["Validated_NPT_hr"] + df["Potential_ILT_hr"]
    )

    return df


def csv_bytes(data):
    return data.to_csv(index=False).encode("utf-8")


# ======================================================
# WORKFLOW 1: UNIFIED MATRIX FROM CSV / EXCEL
# ======================================================

st.header("1. Unified NPT–ILT Matrix")

mode = st.radio(
    "Choose your workflow",
    ["Operation Dataset (CSV / Excel)", "DDR PDF Review"],
    horizontal=True
)

if mode == "Operation Dataset (CSV / Excel)":

    uploaded = st.file_uploader(
        "Upload your operation dataset",
        type=["csv", "xlsx"]
    )

    st.caption(
        "Required columns: Well_ID, Report_Date, Operation_Type, "
        "Hole_Section, Actual_Duration_hr, Validated_NPT_hr"
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
                    "The dataset is missing required columns: "
                    + ", ".join(missing)
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
                is_synthetic = (
                    "Source_Reference" in raw.columns
                    and "Review_Status" in raw.columns
                )

                if is_synthetic:
                    st.warning(
                        "SYNTHETIC DEMONSTRATION MODE: These records "
                        "are simulated. Results do not represent actual "
                        "field performance or validated Lower Indus "
                        "Basin measurements."
                    )
                else:
                    st.info(
                        "Structured data detected. Verify source records, "
                        "time units, NPT labels, and benchmark suitability."
                    )

                matrix = calculate_matrix(raw)

                if "Review_Status" not in matrix.columns:
                    matrix["Review_Status"] = "Requires verification"

                st.header("2. Filter the Matrix")

                col1, col2, col3 = st.columns(3)

                wells = sorted(matrix["Well_ID"].astype(str).unique())
                operations = sorted(
                    matrix["Operation_Type"].astype(str).unique()
                )
                sections = sorted(
                    matrix["Hole_Section"].astype(str).unique()
                )

                with col1:
                    chosen_wells = st.multiselect(
                        "Well",
                        wells,
                        default=wells
                    )

                with col2:
                    chosen_operations = st.multiselect(
                        "Operation",
                        operations,
                        default=operations
                    )

                with col3:
                    chosen_sections = st.multiselect(
                        "Hole section",
                        sections,
                        default=sections
                    )

                view = matrix[
                    matrix["Well_ID"].astype(str).isin(chosen_wells)
                    & matrix["Operation_Type"].astype(str).isin(
                        chosen_operations
                    )
                    & matrix["Hole_Section"].astype(str).isin(
                        chosen_sections
                    )
                ].copy()

                st.header("3. Lost Time Results")

                npt_total = view["Validated_NPT_hr"].sum()
                ilt_total = view["Potential_ILT_hr"].sum()
                tdlt_total = view["TDLT_hr"].sum()

                a, b, c, d = st.columns(4)
                a.metric("Operation Records", len(view))
                b.metric("NPT (hours)", f"{npt_total:.2f}")
                c.metric("Potential ILT (hours)", f"{ilt_total:.2f}")
                d.metric("TDLT (hours)", f"{tdlt_total:.2f}")

                st.caption(
                    "Potential ILT is benchmark-based and requires "
                    "technical review. It is not automatically proof "
                    "that all excess time was avoidable."
                )

                st.header("4. Unified Quantification Matrix")

                display_cols = [
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

                display_cols = [
                    c for c in display_cols if c in view.columns
                ]

                st.dataframe(
                    view[display_cols].round(2),
                    use_container_width=True,
                    hide_index=True
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

                st.latex(
                    r"\text{TDLT} = \text{NPT} + \text{Potential ILT}"
                )

                st.write(
                    "The benchmark is the median adjusted duration "
                    "for records with the same operation type and "
                    "hole section in the uploaded dataset."
                )

                st.header("6. Operation Summary")

                summary = (
                    view.groupby(
                        ["Operation_Type", "Hole_Section"],
                        as_index=False
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
                    hide_index=True
                )

                if not summary.empty:
                    chart = summary.set_index("Operation_Type")[
                        ["Validated_NPT_hr", "Potential_ILT_hr"]
                    ]
                    st.bar_chart(chart)

                st.header("7. Download Results")

                st.download_button(
                    "Download Unified Matrix CSV",
                    data=csv_bytes(view),
                    file_name="drillsense_unified_matrix.csv",
                    mime="text/csv"
                )

                st.download_button(
                    "Download Operation Summary CSV",
                    data=csv_bytes(summary),
                    file_name="drillsense_operation_summary.csv",
                    mime="text/csv"
                )

        except Exception as error:
            st.error(f"Could not process the dataset: {error}")


# ======================================================
# WORKFLOW 2: DDR PDF REVIEW
# ======================================================

else:

    st.header("DDR PDF Incident Review")

    pdf = st.file_uploader(
        "Upload a Daily Drilling Report PDF",
        type=["pdf"]
    )

    if pdf is not None:
        try:
            text = read_pdf(pdf)

            with st.expander("View extracted PDF text"):
                st.text(text[:20000])

            incidents = detect_incidents(text)

            if not incidents:
                st.warning(
                    "No potential incidents were automatically detected. "
                    "This does not prove that the report contains no NPT. "
                    "Review the extracted text manually."
                )

            else:
                st.write(
                    "Review every detected event against the original DDR."
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
                            step=0.25
                        ),
                    }
                )

                confirmed = edited[
                    edited["Confirm as NPT"] == True
                ].copy()

                confirmed["Duration (hours)"] = pd.to_numeric(
                    confirmed["Duration (hours)"],
                    errors="coerce"
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
                    "A single DDR usually cannot establish a defensible "
                    "ILT benchmark on its own. Use comparable operation "
                    "records or another documented reference."
                )

                evidence = st.text_area(
                    "Document the benchmark, source, and justification",
                    placeholder=(
                        "Describe the comparable operations, benchmark "
                        "duration, reference records, and justification."
                    )
                )

                ilt = st.number_input(
                    "Potential ILT (hours)",
                    min_value=0.0,
                    value=0.0,
                    step=0.25
                )

                if evidence.strip():

                    tdlt = npt + ilt

                    st.header("Unified Lost Time Result")

                    x, y, z = st.columns(3)
                    x.metric("NPT (hours)", f"{npt:.2f}")
                    y.metric("Potential ILT (hours)", f"{ilt:.2f}")
                    z.metric("TDLT (hours)", f"{tdlt:.2f}")

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
                        hide_index=True
                    )

                    st.download_button(
                        "Download TDLT Summary CSV",
                        data=csv_bytes(result),
                        file_name="drillsense_ddr_tdlt_summary.csv",
                        mime="text/csv"
                    )

                    st.download_button(
                        "Download Reviewed NPT Events CSV",
                        data=csv_bytes(edited),
                        file_name="drillsense_reviewed_npt.csv",
                        mime="text/csv"
                    )

                else:
                    st.info(
                        "Enter documented benchmark evidence before "
                        "finalizing the combined TDLT result."
                    )

        except Exception as error:
            st.error(f"Could not read the PDF: {error}")


st.divider()

st.caption(
    "DrillSense AI is an FYP research prototype. Verify all source "
    "records, time units, NPT durations, and benchmark assumptions "
    "before interpreting results as field findings."
)

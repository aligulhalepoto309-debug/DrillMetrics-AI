import io
import re
import pandas as pd
import streamlit as st
from pypdf import PdfReader

# =========================================================
# DRILLSENSE AI — FINAL STREAMLIT APPLICATION
# Executive dashboard + existing Operation Dataset + DDR Review
# =========================================================

st.set_page_config(
    page_title="DrillSense AI",
    page_icon="🛢️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# Styling
# ---------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    .app-title {font-size: 2.25rem; font-weight: 750; margin-bottom: 0;}
    .app-subtitle {color:#64748b; margin-top:0.15rem; margin-bottom:1.2rem;}
    .section-label {
        font-size:0.78rem; font-weight:700; letter-spacing:0.08em;
        text-transform:uppercase; color:#64748b; margin-bottom:0.25rem;
    }
    .status-pill {
        display:inline-block; padding:0.25rem 0.65rem; border-radius:999px;
        background:#e2e8f0; color:#334155; font-size:0.75rem; font-weight:700;
    }
    .method-box {
        border:1px solid #cbd5e1; border-radius:0.65rem; padding:0.9rem 1rem;
        background:#f8fafc;
    }
    .small-note {font-size:0.82rem; color:#64748b;}
    [data-testid="stMetricValue"] {font-size:1.65rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------
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
    "lost circulation", "equipment problem", "equipment failure",
    "washout", "fishing", "repair", "leak", "stalled", "plugged",
    "damage", "unable to", "power tong", "top drive", "motor failure",
    "motor/vfd", "motor vfd", "npt", "lost returns", "mud loss",
    "waiting on", "operational delay",
]

CAUSES = {
    "Equipment malfunction": {
        "keywords": [
            "power tong", "top drive", "motor failure", "motor/vfd",
            "motor vfd", "malfunction", "equipment failure",
            "equipment problem", "mechanical failure", "breakdown",
            "pump failure",
        ],
        "remedy": (
            "Inspect the affected equipment and associated systems. "
            "Review maintenance history, fault logs, spare-parts "
            "availability, and the approved repair procedure."
        ),
    },
    "Lost circulation / fluid loss": {
        "keywords": [
            "lost circulation", "loss circulation", "lost returns",
            "loss of returns", "mud loss",
        ],
        "remedy": (
            "Review mud properties, loss intervals, formation conditions, "
            "and fluid-loss records. Evaluate suitable loss-control measures "
            "under the approved drilling programme."
        ),
    },
    "Stuck pipe / restricted movement": {
        "keywords": [
            "stuck pipe", "pipe stuck", "stuck drillstring",
            "differential sticking", "pack off", "pack-off",
        ],
        "remedy": (
            "Review hole-cleaning records, drilling parameters, wellbore "
            "conditions, and the sequence preceding the event. Follow the "
            "approved stuck-pipe response procedure."
        ),
    },
    "Washout / leakage": {
        "keywords": ["washout", "leak", "leakage", "fluid leak"],
        "remedy": (
            "Inspect the affected component and connections. Verify "
            "pressure-test and maintenance records, identify the leak "
            "location, and follow the approved repair and testing procedure."
        ),
    },
    "Fishing / recovery operation": {
        "keywords": [
            "fishing", "fish in hole", "lost tool", "retrieval operation",
        ],
        "remedy": (
            "Review the incident timeline, fish description, and previous "
            "recovery attempts. Evaluate the approved fishing programme and "
            "confirm equipment readiness."
        ),
    },
    "Operational delay": {
        "keywords": [
            "waiting on", "unable to proceed", "operational delay",
            "waiting for", "delay in operation",
        ],
        "remedy": (
            "Verify the reason and duration of the delay. Review personnel, "
            "materials, service coordination, and operational planning to "
            "identify practical opportunities for improvement."
        ),
    },
    "Drilling parameter issue": {
        "keywords": [
            "weight on bit", "wob", "rpm", "rop", "drilling parameter",
            "parameter adjustment", "rotary speed",
        ],
        "remedy": (
            "Review recorded drilling parameters and the event timeline. "
            "Compare the selected parameters with the approved drilling "
            "programme and documented operating limits."
        ),
    },
    "Wellbore instability": {
        "keywords": [
            "wellbore instability", "cavings", "hole instability",
            "tight hole", "hole condition",
        ],
        "remedy": (
            "Review hole conditions, mud properties, cavings, circulation "
            "records, and the approved wellbore-stability programme."
        ),
    },
}


# ---------------------------------------------------------
# Session state
# ---------------------------------------------------------
for key, default in {
    "matrix": None,
    "matrix_source": None,
    "operation_summary": None,
    "ddr_review": None,
    "ddr_result": None,
    "root_cause_data": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------
def csv_bytes(data):
    return data.to_csv(index=False).encode("utf-8")


def read_pdf(uploaded_file):
    reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
    parts = []
    for number, page in enumerate(reader.pages, start=1):
        parts.append(f"PAGE {number}\n{page.extract_text() or ''}")
    return "\n".join(parts)


def detect_incidents(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
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


def calculate_matrix(data, benchmark_mode="uploaded_or_median"):
    """
    Unified matrix:
      Adjusted Duration = Actual Duration - Validated NPT
      Potential ILT = max(0, Adjusted Duration - Benchmark)
      TDLT = Validated NPT + Potential ILT

    benchmark_mode:
      - uploaded_or_median: use Benchmark_Duration_hr if present,
        otherwise dataset median by Operation_Type + Hole_Section.
      - median: always use dataset median.
    """
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

    if (df["Validated_NPT_hr"] > df["Actual_Duration_hr"]).any():
        raise ValueError(
            "Validated NPT cannot exceed actual operation duration."
        )

    df["Adjusted_Duration_hr"] = (
        df["Actual_Duration_hr"] - df["Validated_NPT_hr"]
    )

    group_cols = ["Operation_Type", "Hole_Section"]
    median_benchmark = (
        df.groupby(group_cols)["Adjusted_Duration_hr"].transform("median")
    )

    if (
        benchmark_mode == "uploaded_or_median"
        and "Benchmark_Duration_hr" in df.columns
    ):
        uploaded_benchmark = pd.to_numeric(
            df["Benchmark_Duration_hr"], errors="coerce"
        )
        df["Benchmark_Duration_hr"] = uploaded_benchmark.fillna(
            median_benchmark
        )
        df["Benchmark_Basis"] = df["Benchmark_Duration_hr"].apply(
            lambda x: "Uploaded benchmark"
            if pd.notna(x)
            else "Dataset median reference"
        )
    else:
        df["Benchmark_Duration_hr"] = median_benchmark
        df["Benchmark_Basis"] = "Dataset median reference"

    df["Potential_ILT_hr"] = (
        df["Adjusted_Duration_hr"] - df["Benchmark_Duration_hr"]
    ).clip(lower=0)

    df["TDLT_hr"] = (
        df["Validated_NPT_hr"] + df["Potential_ILT_hr"]
    )

    return df


def show_root_cause_analysis(evidence_data, key_prefix="root"):
    st.subheader("Root-Cause Analysis & Remedy Recommendations")
    st.caption(
        "Cause categories are preliminary decision-support classifications. "
        "Review the source evidence before treating a cause or remedy as confirmed."
    )

    analyzed = evidence_data.copy()

    if "Incident / Evidence" not in analyzed.columns:
        st.info(
            "No incident-evidence column is available. Root causes cannot "
            "be reliably inferred from duration values alone."
        )
        return None

    analyzed["Suggested Cause"] = analyzed["Incident / Evidence"].apply(
        classify_cause
    )
    analyzed["Suggested Remedy"] = analyzed["Suggested Cause"].apply(
        recommend_remedy
    )

    if "Reviewed Cause" not in analyzed.columns:
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
                "System-suggested category", disabled=True
            ),
            "Suggested Remedy": st.column_config.TextColumn(
                "Suggested remedy", disabled=True
            ),
        },
        key=f"{key_prefix}_editor",
    )

    edited["Final Remedy"] = edited["Reviewed Cause"].apply(recommend_remedy)

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
        key=f"{key_prefix}_download",
    )

    return edited


def render_header():
    st.markdown('<div class="app-title">🛢️ DrillSense AI</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="app-subtitle">Unified Lost Time Quantification & Decision Support</div>',
        unsafe_allow_html=True,
    )


def render_sidebar():
    with st.sidebar:
        st.markdown("## 🛢️ DrillSense AI")
        st.caption("Drilling Performance & Lost Time Intelligence")
        st.divider()

        page = st.radio(
            "Navigation",
            [
                "Executive Dashboard",
                "Operation Dataset",
                "DDR PDF Review",
                "Root-Cause Analysis",
                "Validation & Export",
            ],
            key="navigation",
        )

        st.divider()

        if st.session_state.matrix is not None:
            m = st.session_state.matrix
            st.success("Operation dataset loaded")
            st.caption(
                f"{len(m):,} records • "
                f"{m['Well_ID'].nunique():,} wells"
            )
        else:
            st.info("No operation dataset loaded")

        if st.session_state.ddr_result is not None:
            st.success("DDR review available")

        st.divider()
        st.caption("Research prototype")
        st.caption("Synthetic results do not represent validated field performance.")

    return page


# ---------------------------------------------------------
# Page: Executive Dashboard
# ---------------------------------------------------------
def page_dashboard():
    render_header()

    st.markdown(
        '<span class="status-pill">RESEARCH PROTOTYPE • HUMAN REVIEW REQUIRED</span>',
        unsafe_allow_html=True,
    )
    st.write("")

    matrix = st.session_state.matrix

    if matrix is None:
        st.info(
            "No operation dataset is loaded yet. Use **Operation Dataset** "
            "in the sidebar to upload your CSV/Excel file. You can also use "
            "**DDR PDF Review** for single-report analysis."
        )

        a, b, c, d = st.columns(4)
        a.metric("Total Actual Hours", "—")
        b.metric("Validated NPT", "—")
        c.metric("Potential ILT", "—")
        d.metric("TDLT", "—")

        st.subheader("DrillSense AI workflow")
        st.markdown(
            """
            **1. Data → 2. Preprocessing → 3. NPT validation → "
            **4. ILT benchmark → 5. Unified TDLT → 6. Cause & remedy → "
            **7. Decision support → 8. Export**
            """
        )

        st.warning(
            "TDLT is only finalized when NPT is validated and an ILT value "
            "has a documented benchmark/evidence basis."
        )
        return

    total_actual = matrix["Actual_Duration_hr"].sum()
    total_npt = matrix["Validated_NPT_hr"].sum()
    total_ilt = matrix["Potential_ILT_hr"].sum()
    total_tdlt = matrix["TDLT_hr"].sum()

    st.caption(
        f"Dataset: {st.session_state.matrix_source or 'uploaded data'}"
    )

    a, b, c, d = st.columns(4)
    a.metric("Total Actual Hours", f"{total_actual:,.1f}")
    b.metric("Validated NPT", f"{total_npt:,.1f} hr")
    c.metric("Potential ILT", f"{total_ilt:,.1f} hr")
    d.metric("Total Drilling Lost Time", f"{total_tdlt:,.1f} hr")

    st.caption("TDLT = NPT + Potential ILT")

    st.divider()

    left, right = st.columns([1.45, 1])

    with left:
        st.subheader("Lost Time by Well")
        well_summary = (
            matrix.groupby("Well_ID", as_index=False)
            .agg(
                NPT_hr=("Validated_NPT_hr", "sum"),
                ILT_hr=("Potential_ILT_hr", "sum"),
                TDLT_hr=("TDLT_hr", "sum"),
            )
            .sort_values("TDLT_hr", ascending=False)
            .head(10)
            .set_index("Well_ID")
        )
        st.bar_chart(well_summary[["NPT_hr", "ILT_hr"]])

    with right:
        st.subheader("Lost Time Composition")
        composition = pd.DataFrame(
            {
                "Hours": [total_npt, total_ilt],
            },
            index=["NPT", "Potential ILT"],
        )
        st.bar_chart(composition)

        st.caption(
            "The native Streamlit chart is intentionally simple; the values "
            "are the research outputs, not a claim that ILT is inherently avoidable."
        )

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("Operation Summary")
        operation_summary = (
            matrix.groupby(
                ["Operation_Type", "Hole_Section"], as_index=False
            )
            .agg(
                Records=("Well_ID", "count"),
                Actual_hr=("Actual_Duration_hr", "sum"),
                NPT_hr=("Validated_NPT_hr", "sum"),
                ILT_hr=("Potential_ILT_hr", "sum"),
                TDLT_hr=("TDLT_hr", "sum"),
            )
            .sort_values("TDLT_hr", ascending=False)
        )
        st.dataframe(
            operation_summary.round(2),
            use_container_width=True,
            hide_index=True,
        )

    with right:
        st.subheader("Root-Cause Coverage")
        evidence_col = next(
            (
                c for c in [
                    "Incident / Evidence",
                    "Cause_Evidence",
                    "Incident",
                    "Event_Description",
                    "Description",
                    "Event",
                ]
                if c in matrix.columns
            ),
            None,
        )

        if evidence_col:
            tmp = matrix.copy()
            tmp["Incident / Evidence"] = tmp[evidence_col]
            tmp["Cause"] = tmp["Incident / Evidence"].apply(classify_cause)
            cause_summary = (
                tmp.groupby("Cause")
                .agg(Records=("Well_ID", "count"), TDLT_hr=("TDLT_hr", "sum"))
                .sort_values("TDLT_hr", ascending=False)
            )
            st.bar_chart(cause_summary[["TDLT_hr"]])
        else:
            st.info(
                "No evidence column is present. Cause analysis requires "
                "documented incident/evidence text or DDR review."
            )

    st.divider()
    st.subheader("Decision-Support Snapshot")
    st.markdown(
        """
        - **Validated NPT:** time explicitly reviewed and confirmed as NPT.
        - **Potential ILT:** time above the selected benchmark after removing NPT.
        - **TDLT:** NPT + Potential ILT.
        - **Cause:** preliminary evidence-based category requiring human review.
        - **Remedy:** decision-support suggestion; follow the approved well-specific procedure.
        """
    )


# ---------------------------------------------------------
# Page: Operation Dataset
# ---------------------------------------------------------
def page_operation_dataset():
    render_header()
    st.header("Operation Dataset")

    uploaded = st.file_uploader(
        "Upload operation dataset",
        type=["csv", "xlsx"],
        key="operation_upload",
    )

    st.caption(
        "Required: Well_ID, Report_Date, Operation_Type, Hole_Section, "
        "Actual_Duration_hr, Validated_NPT_hr."
    )

    benchmark_mode_label = st.selectbox(
        "ILT benchmark basis",
        [
            "Use uploaded Benchmark_Duration_hr when available; otherwise dataset median",
            "Use dataset median reference",
        ],
        help=(
            "A dataset median is a reference for demonstration/testing. "
            "For a defensible ILT study, use a documented comparable-operation baseline."
        ),
    )

    benchmark_mode = (
        "uploaded_or_median"
        if benchmark_mode_label.startswith("Use uploaded")
        else "median"
    )

    if uploaded is None:
        st.info("Upload your CSV or Excel dataset to populate the unified matrix.")
        return

    try:
        if uploaded.name.lower().endswith(".csv"):
            raw = pd.read_csv(uploaded)
        else:
            raw = pd.read_excel(uploaded)

        missing = [c for c in REQUIRED if c not in raw.columns]

        if missing:
            st.error("Missing required columns: " + ", ".join(missing))
            st.write("Columns detected:", list(raw.columns))
            st.dataframe(raw.head(50), use_container_width=True)
            return

        if raw[["Well_ID", "Operation_Type", "Hole_Section"]].isna().any().any():
            st.error("Well_ID, Operation_Type, and Hole_Section must not be blank.")
            return

        synthetic = (
            "Source_Reference" in raw.columns
            and "Review_Status" in raw.columns
        )

        if synthetic:
            st.warning(
                "SYNTHETIC DEMONSTRATION MODE: this dataset is simulated and "
                "does not establish actual Lower Indus Basin performance."
            )
        else:
            st.info(
                "Structured data detected. Verify source, units, NPT labels, "
                "and benchmark suitability."
            )

        matrix = calculate_matrix(raw, benchmark_mode=benchmark_mode)
        if "Review_Status" not in matrix.columns:
            matrix["Review_Status"] = "Requires verification"

        st.session_state.matrix = matrix
        st.session_state.matrix_source = uploaded.name

        st.success(f"Loaded {len(matrix):,} operation records.")

        st.subheader("Filter Operation Records")
        c1, c2, c3 = st.columns(3)

        wells = sorted(matrix["Well_ID"].astype(str).unique())
        operations = sorted(matrix["Operation_Type"].astype(str).unique())
        sections = sorted(matrix["Hole_Section"].astype(str).unique())

        with c1:
            selected_wells = st.multiselect("Well", wells, default=wells, key="op_wells")
        with c2:
            selected_operations = st.multiselect(
                "Operation", operations, default=operations, key="op_operations"
            )
        with c3:
            selected_sections = st.multiselect(
                "Hole section", sections, default=sections, key="op_sections"
            )

        view = matrix[
            matrix["Well_ID"].astype(str).isin(selected_wells)
            & matrix["Operation_Type"].astype(str).isin(selected_operations)
            & matrix["Hole_Section"].astype(str).isin(selected_sections)
        ].copy()

        st.subheader("Unified Lost Time Summary")
        a, b, c, d = st.columns(4)
        a.metric("Records", len(view))
        b.metric("NPT", f"{view['Validated_NPT_hr'].sum():,.2f} hr")
        c.metric("Potential ILT", f"{view['Potential_ILT_hr'].sum():,.2f} hr")
        d.metric("TDLT", f"{view['TDLT_hr'].sum():,.2f} hr")

        st.subheader("Unified NPT–ILT Matrix")

        columns = [
            "Well_ID", "Report_Date", "Operation_Type", "Hole_Section",
            "Actual_Duration_hr", "Validated_NPT_hr", "Adjusted_Duration_hr",
            "Benchmark_Duration_hr", "Benchmark_Basis",
            "Potential_ILT_hr", "TDLT_hr", "Review_Status",
        ]
        columns = [c for c in columns if c in view.columns]

        st.dataframe(
            view[columns].round(2),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Calculation Method")
        st.latex(
            r"\text{Adjusted Duration} = "
            r"\text{Actual Duration} - \text{Validated NPT}"
        )
        st.latex(
            r"\text{Potential ILT} = "
            r"\max(0,\text{Adjusted Duration} - \text{Benchmark})"
        )
        st.latex(r"\text{TDLT} = \text{NPT} + \text{Potential ILT}")

        if benchmark_mode == "median":
            st.warning(
                "The current benchmark is dataset-derived. It is a reference "
                "for analysis/testing, not automatically a validated ILT baseline."
            )
        elif "Benchmark_Duration_hr" in raw.columns:
            st.info(
                "Uploaded benchmark values are being used where available. "
                "Confirm their documentation and comparability."
            )
        else:
            st.warning(
                "No Benchmark_Duration_hr column was supplied, so the app "
                "uses the dataset median as a reference."
            )

        st.subheader("Operation Summary")
        summary = (
            view.groupby(["Operation_Type", "Hole_Section"], as_index=False)
            .agg(
                Record_Count=("Well_ID", "count"),
                Actual_Duration_hr=("Actual_Duration_hr", "sum"),
                Validated_NPT_hr=("Validated_NPT_hr", "sum"),
                Potential_ILT_hr=("Potential_ILT_hr", "sum"),
                TDLT_hr=("TDLT_hr", "sum"),
            )
        )
        st.session_state.operation_summary = summary

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

        # Cause evidence
        evidence_col = next(
            (
                c for c in [
                    "Incident / Evidence", "Cause_Evidence", "Incident",
                    "Event_Description", "Description", "Event",
                ]
                if c in view.columns
            ),
            None,
        )

        if evidence_col:
            st.subheader("Operation Cause Analysis")
            cause_input = view.copy()
            cause_input["Incident / Evidence"] = cause_input[evidence_col]
            edited = show_root_cause_analysis(cause_input, "operation_cause")
            if edited is not None:
                st.session_state.root_cause_data = edited
        else:
            st.info(
                "Your operation dataset has no event-description/evidence column. "
                "Root causes cannot be reliably inferred from durations alone. "
                "Use DDR PDF Review or add Incident / Evidence / Cause_Evidence."
            )

        st.subheader("Download")
        st.download_button(
            "Download Unified Matrix CSV",
            data=csv_bytes(view),
            file_name="drillsense_unified_matrix.csv",
            mime="text/csv",
            key="download_matrix",
        )
        st.download_button(
            "Download Operation Summary CSV",
            data=csv_bytes(summary),
            file_name="drillsense_operation_summary.csv",
            mime="text/csv",
            key="download_operation_summary",
        )

    except Exception as error:
        st.error(f"Could not process the dataset: {error}")


# ---------------------------------------------------------
# Page: DDR PDF Review
# ---------------------------------------------------------
def page_ddr_review():
    render_header()
    st.header("DDR PDF Review")

    pdf = st.file_uploader(
        "Upload Daily Drilling Report PDF",
        type=["pdf"],
        key="ddr_upload",
    )

    if pdf is None:
        st.info(
            "Upload a DDR PDF. The system will extract text and identify "
            "potential incidents for human confirmation."
        )
        return

    try:
        text = read_pdf(pdf)

        with st.expander("View extracted report text"):
            st.text(text[:30000])

        incidents = detect_incidents(text)

        if not incidents:
            st.warning(
                "No potential incidents were automatically detected. "
                "Review the extracted report text manually."
            )
            return

        st.write(
            "Confirm each event and verify its duration against the original DDR."
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
                    "Duration (hours)", min_value=0.0, step=0.25
                ),
            },
            key="ddr_event_editor",
        )

        confirmed = edited[edited["Confirm as NPT"] == True].copy()
        confirmed["Duration (hours)"] = pd.to_numeric(
            confirmed["Duration (hours)"], errors="coerce"
        )

        invalid = (
            confirmed["Duration (hours)"].isna().any()
            or (confirmed["Duration (hours)"] < 0).any()
        )

        if invalid:
            st.error("Confirmed NPT durations must be valid non-negative numbers.")
            return

        npt = float(confirmed["Duration (hours)"].sum())

        st.subheader("Validated NPT")
        st.metric("Confirmed NPT", f"{npt:.2f} hr")

        st.subheader("ILT Benchmark and Evidence")
        st.write(
            "Enter ILT only after establishing a documented baseline for "
            "comparable operations. Do not estimate ILT from missing data "
            "or treat all operating time as lost time."
        )

        evidence = st.text_area(
            "Document benchmark, source, and justification",
            placeholder=(
                "Example: comparable operation records, reference duration, "
                "source DDRs, benchmark method, and why the baseline is comparable."
            ),
            key="ddr_ilt_evidence",
        )

        ilt = st.number_input(
            "Potential ILT (hours)",
            min_value=0.0,
            value=0.0,
            step=0.25,
            key="ddr_ilt",
        )

        if evidence.strip():
            tdlt = npt + ilt

            st.subheader("Unified Lost Time Result")
            x, y, z = st.columns(3)
            x.metric("NPT", f"{npt:.2f} hr")
            y.metric("Potential ILT", f"{ilt:.2f} hr")
            z.metric("TDLT", f"{tdlt:.2f} hr")

            result = pd.DataFrame([{
                "Report_File": pdf.name,
                "Validated_NPT_hr": npt,
                "Potential_ILT_hr": ilt,
                "TDLT_hr": tdlt,
                "ILT_Benchmark_Evidence": evidence,
            }])

            st.session_state.ddr_review = edited
            st.session_state.ddr_result = result

            st.dataframe(result, use_container_width=True, hide_index=True)

            st.download_button(
                "Download TDLT Summary CSV",
                data=csv_bytes(result),
                file_name="drillsense_ddr_tdlt_summary.csv",
                mime="text/csv",
                key="ddr_summary_download",
            )
            st.download_button(
                "Download Reviewed NPT Events CSV",
                data=csv_bytes(edited),
                file_name="drillsense_reviewed_npt.csv",
                mime="text/csv",
                key="ddr_npt_download",
            )

            cause_data = edited[edited["Confirm as NPT"] == True].copy()
            if not cause_data.empty:
                st.subheader("Incident Cause Review")
                show_root_cause_analysis(cause_data, "ddr_cause")
        else:
            st.info(
                "Enter documented benchmark evidence before finalizing the "
                "combined TDLT result."
            )

    except Exception as error:
        st.error(f"Could not read the PDF: {error}")


# ---------------------------------------------------------
# Page: Root Cause
# ---------------------------------------------------------
def page_root_cause():
    render_header()
    st.header("Root-Cause Analysis & Remedies")

    matrix = st.session_state.matrix

    if st.session_state.root_cause_data is not None:
        st.subheader("Latest reviewed cause dataset")
        st.dataframe(
            st.session_state.root_cause_data,
            use_container_width=True,
            hide_index=True,
        )

    if matrix is None:
        st.info(
            "Load an operation dataset or complete a DDR review first."
        )
        return

    evidence_col = next(
        (
            c for c in [
                "Incident / Evidence", "Cause_Evidence", "Incident",
                "Event_Description", "Description", "Event",
            ]
            if c in matrix.columns
        ),
        None,
    )

    if evidence_col:
        cause_input = matrix.copy()
        cause_input["Incident / Evidence"] = cause_input[evidence_col]
        edited = show_root_cause_analysis(cause_input, "standalone_cause")
        if edited is not None:
            st.session_state.root_cause_data = edited
    else:
        st.warning(
            "The current operation dataset does not contain documented incident "
            "evidence. Add an evidence column or use DDR PDF Review."
        )


# ---------------------------------------------------------
# Page: Validation & Export
# ---------------------------------------------------------
def page_validation_export():
    render_header()
    st.header("Validation & Export")

    matrix = st.session_state.matrix

    if matrix is None:
        st.info("Load an operation dataset first.")
    else:
        st.subheader("Dataset validation checks")

        checks = []

        checks.append({
            "Check": "Required columns present",
            "Status": "PASS",
            "Detail": "All required columns were detected.",
        })

        n_negative = int(
            (matrix["Actual_Duration_hr"] < 0).sum()
            + (matrix["Validated_NPT_hr"] < 0).sum()
        )
        checks.append({
            "Check": "Non-negative durations",
            "Status": "PASS" if n_negative == 0 else "FAIL",
            "Detail": f"{n_negative} invalid negative values.",
        })

        n_over = int(
            (matrix["Validated_NPT_hr"] > matrix["Actual_Duration_hr"]).sum()
        )
        checks.append({
            "Check": "NPT does not exceed actual duration",
            "Status": "PASS" if n_over == 0 else "FAIL",
            "Detail": f"{n_over} records require correction.",
        })

        benchmark_basis = (
            matrix["Benchmark_Basis"].value_counts().to_dict()
            if "Benchmark_Basis" in matrix.columns
            else {}
        )
        checks.append({
            "Check": "Benchmark basis recorded",
            "Status": "PASS" if benchmark_basis else "REVIEW",
            "Detail": str(benchmark_basis),
        })

        validation_df = pd.DataFrame(checks)
        st.dataframe(
            validation_df,
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Research methodology reminder")
        st.markdown(
            """
            **NPT** should be supported by reviewed incident evidence.

            **ILT** should be benchmark-relative and supported by a documented
            comparable-operation baseline.

            **TDLT = NPT + ILT.**

            Root causes and remedies are decision-support outputs and require
            human review.
            """
        )

        st.download_button(
            "Download Full Unified Matrix",
            data=csv_bytes(matrix),
            file_name="drillsense_final_unified_matrix.csv",
            mime="text/csv",
            key="final_matrix_download",
        )

        if st.session_state.operation_summary is not None:
            st.download_button(
                "Download Operation Summary",
                data=csv_bytes(st.session_state.operation_summary),
                file_name="drillsense_final_operation_summary.csv",
                mime="text/csv",
                key="final_summary_download",
            )

    if st.session_state.ddr_result is not None:
        st.divider()
        st.subheader("Latest DDR result")
        st.dataframe(
            st.session_state.ddr_result,
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "Download Latest DDR Result",
            data=csv_bytes(st.session_state.ddr_result),
            file_name="drillsense_final_ddr_result.csv",
            mime="text/csv",
            key="final_ddr_download",
        )


# =========================================================
# APP ROUTER
# =========================================================
page = render_sidebar()

if page == "Executive Dashboard":
    page_dashboard()
elif page == "Operation Dataset":
    page_operation_dataset()
elif page == "DDR PDF Review":
    page_ddr_review()
elif page == "Root-Cause Analysis":
    page_root_cause()
elif page == "Validation & Export":
    page_validation_export()

st.divider()
st.caption(
    "DrillSense AI research prototype • TDLT = NPT + ILT • "
    "Potential ILT is benchmark-relative and requires documented evidence • "
    "Automated cause classifications are preliminary."
)

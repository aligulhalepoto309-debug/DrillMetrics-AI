
import re
from io import BytesIO

import pandas as pd
import streamlit as st
from pypdf import PdfReader


# ==================================================
# PAGE SETUP
# ==================================================

st.set_page_config(
    page_title="DrillSense AI",
    page_icon="🛢️",
    layout="wide",
)

st.title("🛢️ DrillSense AI")
st.caption("Drilling Performance & Lost Time Intelligence")
st.info("Core equation: TDLT = NPT + ILT")


# ==================================================
# INCIDENT DETECTION
# ==================================================

INCIDENT_TERMS = [
    "npt",
    "malfunction",
    "failure",
    "breakdown",
    "stuck",
    "lost circulation",
    "equipment problem",
    "equipment failure",
    "washout",
    "fishing",
    "repair",
    "leak",
    "stalled",
    "plugged",
    "damage",
    "unable to",
    "power tong",
    "top drive",
    "motor failure",
    "motor/vfd",
    "motor vfd",
]


def find_incident_candidates(page_text, page_number):
    """Find potential incidents, including terms split by PDF line breaks."""

    lines = page_text.splitlines()
    normalized = re.sub(r"\s+", " ", page_text.lower())
    candidates = []
    seen = set()

    for term in INCIDENT_TERMS:
        pattern = re.escape(term).replace(r"\ ", r"\s+")
        for match in re.finditer(pattern, normalized):
            start = max(0, match.start() - 180)
            end = min(len(normalized), match.end() + 220)
            excerpt = normalized[start:end].strip()

            # Recover readable context from the original page.
            # Use nearby lines containing the matched term.
            matching_line = None
            for i, line in enumerate(lines):
                if re.search(pattern, line.lower()):
                    matching_line = i
                    break

            if matching_line is not None:
                line_start = max(0, matching_line - 4)
                line_end = min(len(lines), matching_line + 5)
                excerpt = "\n".join(
                    lines[line_start:line_end]
                ).strip()

            key = (page_number, excerpt.lower())
            if key in seen:
                continue
            seen.add(key)

            # Look for a nearby explicit duration.
            duration = 0.0
            duration_match = re.search(
                r"(\d+(?:\.\d+)?)\s*"
                r"(?:hours?|hrs?|hr\b)",
                excerpt,
                re.IGNORECASE,
            )

            if not duration_match:
                duration_match = re.search(
                    r"(\d+(?:\.\d+)?)\s+WFD\b",
                    excerpt,
                    re.IGNORECASE,
                )

            if duration_match:
                duration = float(duration_match.group(1))

            candidates.append({
                "Page": page_number,
                "Matched terms": term,
                "Report excerpt": excerpt,
                "Confirm as NPT": False,
                "Duration (hours)": duration,
                "Review status": "Needs human review",
            })

    return candidates


def extract_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    pages = []

    for number, page in enumerate(reader.pages, start=1):
        pages.append({
            "Page": number,
            "Text": page.extract_text() or "",
        })

    return pages


def find_reported_npt_totals(text):
    """Extract explicit NPT totals when their wording is recognizable."""

    patterns = [
        r"total\s+npt\s+to\s+date\s*[:\-]?\s*"
        r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr\b)",

        r"npt\s+today\s*[:\-]?\s*"
        r"(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|hr\b)",
    ]

    totals = []

    for pattern in patterns:
        for match in re.finditer(
            pattern, text, re.IGNORECASE
        ):
            totals.append({
                "Label": (
                    "Total NPT to date"
                    if "total" in pattern
                    else "NPT today"
                ),
                "Reported hours": float(match.group(1)),
                "Source text": match.group(0),
            })

    return totals


# ==================================================
# FILE UPLOAD
# ==================================================

st.header("1. Upload Drilling Report")

uploaded_file = st.file_uploader(
    "Select a DDR or drilling dataset",
    type=["pdf", "csv", "xlsx"],
)

if uploaded_file is None:
    st.info("Supported files: PDF, CSV, and Excel (.xlsx).")
    st.stop()


filename = uploaded_file.name.lower()

# Keep the report's extracted text available for review.
full_text = ""
all_candidates = []
reported_totals = []


try:
    # --------------------------------------------------
    # PDF WORKFLOW
    # --------------------------------------------------

    if filename.endswith(".pdf"):
        pages = extract_pdf(uploaded_file)

        full_text = "\n\n".join(
            f"--- PAGE {page['Page']} ---\n{page['Text']}"
            for page in pages
        )

        st.success(
            f"PDF processed: {len(pages)} page(s)."
        )

        col1, col2 = st.columns(2)
        col1.metric("PDF Pages", len(pages))
        col2.metric("Extracted Characters", len(full_text))

        st.download_button(
            "Download Extracted Text",
            data=full_text.encode("utf-8"),
            file_name="drilling_report_extracted.txt",
            mime="text/plain",
        )

        with st.expander("View extracted report text"):
            for page in pages:
                st.markdown(f"**Page {page['Page']}**")
                if page["Text"].strip():
                    st.text(page["Text"])
                else:
                    st.warning(
                        "No selectable text found on this page. "
                        "OCR may be required."
                    )

        for page in pages:
            all_candidates.extend(
                find_incident_candidates(
                    page["Text"], page["Page"]
                )
            )

        reported_totals = find_reported_npt_totals(
            full_text
        )

    # --------------------------------------------------
    # CSV / EXCEL WORKFLOW
    # --------------------------------------------------

    else:
        if filename.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        st.success("Spreadsheet opened successfully.")

        st.subheader("Spreadsheet Preview")
        st.dataframe(df.head(50), use_container_width=True)

        col1, col2, col3 = st.columns(3)
        col1.metric("Records", len(df))
        col2.metric("Columns", len(df.columns))
        col3.metric(
            "Duplicate Rows",
            int(df.duplicated().sum()),
        )

        quality = pd.DataFrame({
            "Column": df.columns,
            "Data Type": [
                str(df[column].dtype) for column in df.columns
            ],
            "Missing Values": [
                int(df[column].isna().sum())
                for column in df.columns
            ],
            "Missing (%)": [
                round(df[column].isna().mean() * 100, 2)
                for column in df.columns
            ],
        })

        st.subheader("Data Quality Report")
        st.dataframe(quality, use_container_width=True)

        st.download_button(
            "Download Spreadsheet as CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="drilling_data_export.csv",
            mime="text/csv",
        )

        st.warning(
            "Spreadsheet data is displayed for inspection. "
            "Automatic NPT/ILT calculation from arbitrary "
            "spreadsheet columns is not enabled because column "
            "meanings and time units must first be validated."
        )

        st.stop()


    # ==================================================
    # HUMAN REVIEW
    # ==================================================

    st.divider()
    st.header("2. Review Potential NPT Events")

    st.write(
        "Review each excerpt against the original DDR. "
        "Check 'Confirm as NPT' only when the event and its "
        "duration have been verified. Edit durations as needed."
    )

    if not all_candidates:
        st.warning(
            "No configured incident terms were detected. "
            "This does not prove that no NPT occurred."
        )

        st.info(
            "Review the extracted text manually. A reviewer "
            "can only calculate NPT for incidents entered "
            "and validated in the review table."
        )

        review_df = pd.DataFrame(columns=[
            "Page",
            "Matched terms",
            "Report excerpt",
            "Confirm as NPT",
            "Duration (hours)",
            "Review status",
        ])

    else:
        review_df = pd.DataFrame(all_candidates)

        # Prevent duplicated candidates from appearing as
        # separate events when their excerpts overlap.
        review_df = review_df.drop_duplicates(
            subset=["Page", "Report excerpt"]
        ).reset_index(drop=True)

    edited_df = st.data_editor(
        review_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="incident_review_editor",
        column_config={
            "Page": st.column_config.NumberColumn(
                "PDF page", disabled=True
            ),
            "Matched terms": st.column_config.TextColumn(
                "Detected term", disabled=True
            ),
            "Report excerpt": st.column_config.TextColumn(
                "Original report excerpt", disabled=True,
                width="large",
            ),
            "Confirm as NPT": st.column_config.CheckboxColumn(
                "Confirm as NPT",
                help="Tick only after checking the original report.",
            ),
            "Duration (hours)": st.column_config.NumberColumn(
                "Duration (hours)",
                min_value=0.0,
                step=0.25,
                format="%.2f",
            ),
            "Review status": st.column_config.TextColumn(
                "Status", disabled=True
            ),
        },
    )

    # ==================================================
    # VALIDATE REVIEWED EVENTS
    # ==================================================

    st.divider()
    st.header("3. Validated NPT Calculation")

    if "Confirm as NPT" not in edited_df.columns:
        edited_df["Confirm as NPT"] = False

    if "Duration (hours)" not in edited_df.columns:
        edited_df["Duration (hours)"] = 0.0

    edited_df["Duration (hours)"] = pd.to_numeric(
        edited_df["Duration (hours)"],
        errors="coerce",
    )

    confirmed = edited_df[
        edited_df["Confirm as NPT"].fillna(False)
    ].copy()

    invalid_durations = confirmed[
        confirmed["Duration (hours)"].isna()
        | (confirmed["Duration (hours)"] <= 0)
    ]

    if not invalid_durations.empty:
        st.error(
            "One or more confirmed events have missing or "
            "non-positive durations. Correct them before "
            "calculating NPT."
        )
        npt_valid = False
        validated_npt = None
    else:
        npt_valid = True
        validated_npt = float(
            confirmed["Duration (hours)"].sum()
        )

    col1, col2 = st.columns(2)
    col1.metric("Detected Candidates", len(edited_df))
    col2.metric("Confirmed NPT Events", len(confirmed))

    if npt_valid:
        st.metric(
            "Validated NPT (hours)",
            f"{validated_npt:.2f}",
        )

    # ==================================================
    # DISCREPANCY WARNINGS
    # ==================================================

    st.header("4. Report Discrepancy Checks")

    if reported_totals:
        totals_df = pd.DataFrame(reported_totals)

        st.write("NPT totals extracted from the report:")
        st.dataframe(totals_df, use_container_width=True)

        if npt_valid:
            for item in reported_totals:
                reported = item["Reported hours"]

                # A report total may be a daily value or a
                # cumulative value; compare only like-for-like
                # values after the reviewer verifies the scope.
                if (
                    item["Label"] == "Total NPT to date"
                    and abs(reported - validated_npt) > 0.01
                ):
                    st.warning(
                        f"Discrepancy: report says total NPT "
                        f"to date is {reported:.2f} hours, while "
                        f"the currently confirmed event durations "
                        f"sum to {validated_npt:.2f} hours. "
                        "Verify reporting period, omitted events, "
                        "and source values before finalizing."
                    )

                elif (
                    item["Label"] == "NPT today"
                    and abs(reported - validated_npt) > 0.01
                ):
                    st.warning(
                        f"Possible discrepancy: report says "
                        f"NPT today is {reported:.2f} hours, "
                        f"while confirmed events sum to "
                        f"{validated_npt:.2f} hours. These values "
                        "may cover different reporting scopes; "
                        "verify before reconciling."
                    )
    else:
        st.info(
            "No recognizable NPT summary total was extracted. "
            "Check the original report for any stated NPT totals."
        )

    st.warning(
        "Automated discrepancy checks are indicators for review, "
        "not proof of an error. Confirm that compared values cover "
        "the same reporting period and use the same definitions."
    )

    # ==================================================
    # ILT INPUT AND TDLT
    # ==================================================

    st.divider()
    st.header("5. ILT and Total Drilling Lost Time")

    st.write(
        "Enter ILT only after establishing a documented baseline "
        "for comparable operations. Do not estimate ILT from "
        "missing data or treat all operating time as lost time."
    )

    ilt_text = st.text_input(
        "Validated ILT (hours)",
        value="",
        placeholder="e.g. 1.25",
        key="ilt_hours",
    )

    ilt_basis = st.text_input(
        "ILT baseline / method / evidence",
        value="",
        placeholder=(
            "e.g. approved benchmark, planned duration, "
            "or documented calculation method"
        ),
        key="ilt_basis",
    )

    ilt_hours = None
    ilt_valid = False

    if ilt_text.strip():
        try:
            ilt_hours = float(ilt_text)

            if ilt_hours < 0:
                st.error("ILT cannot be negative.")
            elif not ilt_basis.strip():
                st.warning(
                    "Provide the ILT baseline or method before "
                    "using this value in TDLT."
                )
            else:
                ilt_valid = True

        except ValueError:
            st.error(
                "Enter ILT as a valid number of hours, "
                "for example 1.25."
            )

    if npt_valid and ilt_valid:
        tdlt = validated_npt + ilt_hours

        col1, col2, col3 = st.columns(3)
        col1.metric("NPT (hours)", f"{validated_npt:.2f}")
        col2.metric("ILT (hours)", f"{ilt_hours:.2f}")
        col3.metric("TDLT (hours)", f"{tdlt:.2f}")

        st.success(
            f"TDLT = {validated_npt:.2f} + "
            f"{ilt_hours:.2f} = {tdlt:.2f} hours"
        )
    else:
        st.info(
            "TDLT is not finalized. Confirm valid NPT durations "
            "and enter a validated ILT value with its documented "
            "basis to calculate the total."
        )
        tdlt = None

    # ==================================================
    # DOWNLOAD REVIEW RESULTS
    # ==================================================

    st.divider()
    st.header("6. Export Review Results")

    export_df = edited_df.copy()

    if "Review status" in export_df.columns:
        export_df["Review status"] = export_df[
            "Confirm as NPT"
        ].fillna(False).map({
            True: "Confirmed by reviewer",
            False: "Not confirmed",
        })

    export_df["Validated NPT total (hours)"] = (
        validated_npt if npt_valid else None
    )
    export_df["ILT (hours)"] = (
        ilt_hours if ilt_valid else None
    )
    export_df["ILT basis"] = ilt_basis.strip() or None
    export_df["TDLT (hours)"] = tdlt

    export_df["Calculation note"] = (
        "Human review required; verify source report "
        "and reporting scope."
    )

    st.download_button(
        "Download Reviewed Events CSV",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name="drillsense_review_results.csv",
        mime="text/csv",
    )

    summary_df = pd.DataFrame([
        {"Metric": "Confirmed NPT events", "Value": len(confirmed)},
        {
            "Metric": "Validated NPT (hours)",
            "Value": validated_npt if npt_valid else "Not valid",
        },
        {
            "Metric": "ILT (hours)",
            "Value": ilt_hours if ilt_valid else "Not validated",
        },
        {
            "Metric": "ILT basis",
            "Value": ilt_basis.strip() or "Not provided",
        },
        {
            "Metric": "TDLT (hours)",
            "Value": tdlt if tdlt is not None else "Not calculated",
        },
    ])

    st.download_button(
        "Download Calculation Summary CSV",
        data=summary_df.to_csv(index=False).encode("utf-8"),
        file_name="drillsense_calculation_summary.csv",
        mime="text/csv",
    )

except Exception as error:
    st.error(f"Could not process this file: {error}")
    st.info(
        "Check that the file is valid. Scanned PDFs may require "
        "OCR, and password-protected PDFs may not be readable."
    )


st.divider()
st.caption(
    "DrillSense AI is a decision-support prototype. "
    "Detected events, extracted durations, report totals, and "
    "ILT baselines require verification against source records. "
    "The application does not independently certify drilling "
    "time-loss classifications."
)

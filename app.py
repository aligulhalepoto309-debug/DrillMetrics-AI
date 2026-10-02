
import re
from io import BytesIO

import pandas as pd
import streamlit as st
from pypdf import PdfReader

st.set_page_config(
    page_title="DrillSense AI",
    page_icon="🛢️",
    layout="wide",
)

st.title("🛢️ DrillSense AI")
st.caption("AI-Powered Drilling Performance & Lost Time Intelligence")
st.info("Core equation: TDLT = NPT + ILT")

st.header("DDR Analyzer")

st.write(
    "Upload a Daily Drilling Report to extract report text, "
    "identify potential NPT events, and review data quality."
)


# --------------------------------------------------
# NPT CANDIDATE DETECTION
# --------------------------------------------------

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


def find_incident_candidates(page_text):
    """Flag possible incidents using nearby PDF text lines."""

    lines = page_text.splitlines()
    candidates = []

    for i, line in enumerate(lines):
        matched = [
            term
            for term in INCIDENT_TERMS
            if term in line.lower()
        ]

        if not matched:
            continue

        # PDF tables can separate descriptions, codes,
        # and durations across nearby lines.
        start = max(0, i - 4)
        end = min(len(lines), i + 5)

        excerpt = "\n".join(lines[start:end]).strip()

        candidates.append({
            "Page": None,
            "Matched terms": ", ".join(matched),
            "Report excerpt": excerpt,
            "Review status": "Needs human review",
        })

    # Remove duplicate excerpts.
    unique = []
    seen = set()

    for item in candidates:
        key = item["Report excerpt"]

        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def extract_pdf(uploaded_file):
    reader = PdfReader(uploaded_file)
    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""

        pages.append({
            "Page": page_number,
            "Text": page_text,
        })

    return pages


# --------------------------------------------------
# FILE UPLOAD
# --------------------------------------------------

uploaded_file = st.file_uploader(
    "Upload your drilling report",
    type=["pdf", "csv", "xlsx"],
)

if uploaded_file is None:
    st.info(
        "Supported formats: PDF, CSV, and Excel (.xlsx)."
    )

else:
    filename = uploaded_file.name.lower()

    try:

        # ------------------------------------------
        # PDF REPORT
        # ------------------------------------------

        if filename.endswith(".pdf"):

            pages = extract_pdf(uploaded_file)

            full_text = "\n\n".join(
                f"--- PAGE {page['Page']} ---\n{page['Text']}"
                for page in pages
            )

            st.success(
                f"PDF opened successfully: {len(pages)} pages."
            )

            col1, col2 = st.columns(2)

            col1.metric("PDF Pages", len(pages))
            col2.metric(
                "Extracted Characters",
                len(full_text),
            )

            st.download_button(
                "Download Extracted Text",
                data=full_text.encode("utf-8"),
                file_name="drilling_report_extracted.txt",
                mime="text/plain",
            )

            st.subheader("Extracted Report Text")

            for page in pages:
                with st.expander(f"Page {page['Page']}"):
                    if page["Text"].strip():
                        st.text(page["Text"])
                    else:
                        st.warning(
                            "No selectable text found. "
                            "This page may require OCR."
                        )

            # Detect candidates page by page.
            all_candidates = []

            for page in pages:
                candidates = find_incident_candidates(
                    page["Text"]
                )

                for candidate in candidates:
                    candidate["Page"] = page["Page"]
                    all_candidates.append(candidate)

            st.subheader("Potential NPT / Incident Candidates")

            if all_candidates:

                candidate_df = pd.DataFrame(all_candidates)

                st.warning(
                    f"{len(candidate_df)} candidate excerpts found. "
                    "Review them against the original DDR."
                )

                st.dataframe(
                    candidate_df,
                    use_container_width=True,
                    hide_index=True,
                )

                st.download_button(
                    "Download Candidate Events CSV",
                    data=candidate_df.to_csv(
                        index=False
                    ).encode("utf-8"),
                    file_name="npt_candidates_for_review.csv",
                    mime="text/csv",
                )

            else:
                st.warning(
                    "No configured incident keywords were detected. "
                    "This does not prove that no NPT occurred. "
                    "Check the extracted text above."
                )

            st.subheader("NPT and TDLT")

            st.write(
                "NPT must be calculated from validated incident "
                "durations. Keyword matches alone do not confirm NPT."
            )

            st.write(
                "ILT requires a documented baseline for comparable "
                "operations. It is not inferred automatically here."
            )

            st.info(
                "TDLT = NPT + ILT. A total will be calculated only "
                "after the NPT events and ILT method are validated."
            )

        # ------------------------------------------
        # EXCEL OR CSV
        # ------------------------------------------

        else:

            if filename.endswith(".csv"):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)

            st.success("Spreadsheet opened successfully.")

            st.subheader("Data Preview")

            st.dataframe(
                df.head(50),
                use_container_width=True,
            )

            col1, col2, col3 = st.columns(3)

            col1.metric("Total Records", len(df))
            col2.metric("Total Columns", len(df.columns))
            col3.metric(
                "Duplicate Rows",
                int(df.duplicated().sum()),
            )

            st.subheader("Data Quality Report")

            quality = pd.DataFrame({
                "Column": df.columns,
                "Data Type": [
                    str(df[column].dtype)
                    for column in df.columns
                ],
                "Missing Values": [
                    int(df[column].isna().sum())
                    for column in df.columns
                ],
                "Missing (%)": [
                    round(
                        df[column].isna().mean() * 100,
                        2,
                    )
                    for column in df.columns
                ],
            })

            st.dataframe(
                quality,
                use_container_width=True,
            )

            st.download_button(
                "Download Spreadsheet as CSV",
                data=df.to_csv(
                    index=False
                ).encode("utf-8"),
                file_name="drilling_data_export.csv",
                mime="text/csv",
            )

    except Exception as error:
        st.error(f"Could not process this file: {error}")

        st.info(
            "Check that the file is valid. Scanned PDFs may need "
            "OCR, and password-protected PDFs may not be readable."
        )


st.divider()

st.caption(
    "DrillSense AI is a decision-support prototype. "
    "Verify extracted information and classifications against "
    "the original drilling report."
)

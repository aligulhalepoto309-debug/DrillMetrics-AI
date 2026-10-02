
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
    "Upload a daily drilling report in PDF, Excel, or CSV format. "
    "Review extracted records before using them for lost-time analysis."
)

uploaded_file = st.file_uploader(
    "Upload a drilling report",
    type=["pdf", "csv", "xlsx"],
)

# Keywords flag possible incidents for human review.
incident_terms = [
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
    "waiting on repair",
]


def find_incident_candidates(page_text):
    """Flag likely NPT events using keywords and common DDR wording."""
    lines = page_text.splitlines()
    candidates = []

    terms = [
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
    ]

    for i, line in enumerate(lines):
        matched = [
            term for term in terms
            if term in line.lower()
        ]

        if not matched:
            continue

        # Include nearby lines because PDF table columns
        # can be extracted onto separate lines.
        start = max(0, i - 3)
        end = min(len(lines), i + 4)
        excerpt = "\n".join(lines[start:end]).strip()

        if not excerpt:
            continue

        candidates.append({
            "Matched terms": ", ".join(matched),
            "Report excerpt": excerpt,
            "Review status": "Needs human review",
        })

    # Remove repeated excerpts.
    unique = []
    seen = set()

    for item in candidates:
        key = item["Report excerpt"]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def extract_pdf(uploaded):
    reader = PdfReader(uploaded)
    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({
            "Page": page_number,
            "Text": text,
        })

    return pages


if uploaded_file is None:
    st.info(
        "Upload a report to begin. PDF reports will be processed "
        "page by page; spreadsheet files will be previewed as tables."
    )

else:
    filename = uploaded_file.name.lower()

    try:
        if filename.endswith(".pdf"):
            pages = extract_pdf(uploaded_file)

            full_text = "\n\n".join(
                f"--- PAGE {p['Page']} ---\n{p['Text']}"
                for p in pages
            )

            st.success(
                f"PDF opened successfully: {len(pages)} pages found."
            )

            col1, col2 = st.columns(2)
            col1.metric("Pages", len(pages))
            col2.metric("Extracted characters", len(full_text))

            st.subheader("Extracted Report Text")
            st.caption(
                "Check this text against the original PDF. "
                "Table layouts and scanned pages may not extract perfectly."
            )

            st.download_button(
                "Download extracted text",
                data=full_text.encode("utf-8"),
                file_name="drilling_report_extracted.txt",
                mime="text/plain",
            )

            for page in pages:
                with st.expander(f"Page {page['Page']}"):
                    if page["Text"].strip():
                        st.text(page["Text"])
                    else:
                        st.warning(
                            "No selectable text found on this page. "
                            "It may be scanned and require OCR."
                        )

            st.subheader("Potential NPT / Incident Candidates")

            all_candidates = []

            for page in pages:
                for candidate in find_incident_candidates(page["Text"]):
                    all_candidates.append({
                        "Page": page["Page"],
                        **candidate,
                    })

            if all_candidates:
                candidate_df = pd.DataFrame(all_candidates)
                st.warning(
                    f"{len(candidate_df)} candidate excerpt(s) "
                    "found. These are not confirmed NPT events."
                )

                st.dataframe(
                    candidate_df,
                    use_container_width=True,
                    hide_index=True,
                )

                st.download_button(
                    "Download incident candidates CSV",
                    data=candidate_df.to_csv(index=False).encode("utf-8"),
                    file_name="incident_candidates_for_review.csv",
                    mime="text/csv",
                )
            else:
                st.info(
                    "No configured incident keywords were found. "
                    "This does not prove the report has no NPT."
                )

            st.subheader("Lost-Time Calculation")
            st.write("NPT = sum of validated NPT event durations.")
            st.write(
                "ILT requires a documented baseline and a validated "
                "method for measuring avoidable time."
            )
            st.write(
                "TDLT = NPT + ILT. No TDLT total is reported until "
                "both components can be supported by the data."
            )

        else:
            if filename.endswith(".csv"):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)

            st.success("Spreadsheet opened successfully.")

            st.subheader("Data Preview")
            st.dataframe(df.head(50), use_container_width=True)

            col1, col2, col3 = st.columns(3)
            col1.metric("Records", len(df))
            col2.metric("Columns", len(df.columns))
            col3.metric(
                "Duplicate rows",
                int(df.duplicated().sum()),
            )

            quality = pd.DataFrame({
                "Column": df.columns,
                "Data Type": [
                    str(df[c].dtype) for c in df.columns
                ],
                "Missing Values": [
                    int(df[c].isna().sum()) for c in df.columns
                ],
                "Missing (%)": [
                    round(df[c].isna().mean() * 100, 2)
                    for c in df.columns
                ],
            })

            st.subheader("Data Quality Report")
            st.dataframe(quality, use_container_width=True)

            st.download_button(
                "Download current data as CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="drilling_data_export.csv",
                mime="text/csv",
            )

    except Exception as e:
        st.error(f"Could not process this file: {e}")
        st.info(
            "If this is a scanned PDF, OCR support may be required. "
            "If this is an Excel file, confirm it is a valid .xlsx workbook."
        )

st.divider()
st.caption(
    "DrillSense AI is a decision-support prototype. "
    "Verify extracted events, classifications, and calculations "
    "against the original drilling records."
)

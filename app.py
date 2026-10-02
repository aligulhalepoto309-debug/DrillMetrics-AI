
import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(
    page_title="DrillSense AI",
    page_icon="🛢️",
    layout="wide"
)

st.title("🛢️ DrillSense AI")
st.caption(
    "AI-Powered Drilling Performance & Lost Time Intelligence"
)

st.info("Core equation: TDLT = NPT + ILT")

st.header("1. Drilling Data Upload")

uploaded_file = st.file_uploader(
    "Upload your drilling dataset",
    type=["csv", "xlsx"]
)

if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        st.success("Dataset uploaded successfully.")

        st.subheader("Raw Data Preview")
        st.dataframe(df.head(20), use_container_width=True)

        st.subheader("Dataset Overview")

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Records", len(df))
        col2.metric("Total Columns", len(df.columns))
        col3.metric(
            "Duplicate Rows",
            int(df.duplicated().sum())
        )

        st.subheader("Data Quality Report")

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
            ]
        })

        st.dataframe(quality, use_container_width=True)

        st.subheader("Preprocessing Options")

        remove_duplicates = st.checkbox(
            "Remove exact duplicate rows",
            value=False
        )

        if st.button("Prepare Dataset"):
            clean_df = df.copy()

            if remove_duplicates:
                clean_df = clean_df.drop_duplicates()

            st.success("Dataset prepared for review.")

            st.write(
                f"Records before: {len(df)} | "
                f"Records after: {len(clean_df)}"
            )

            st.dataframe(
                clean_df.head(20),
                use_container_width=True
            )

            csv_data = clean_df.to_csv(
                index=False
            ).encode("utf-8")

            st.download_button(
                "Download Prepared CSV",
                data=csv_data,
                file_name="prepared_drilling_data.csv",
                mime="text/csv"
            )

    except Exception as e:
        st.error(f"Could not read the dataset: {e}")

else:
    st.write(
        "Upload a CSV or Excel file to inspect its "
        "structure and data quality."
    )

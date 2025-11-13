"""Streamlit app for merging attribute tables into GeoPackages."""
from __future__ import annotations

import os
import tempfile
from io import BytesIO

import geopandas as gpd
import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="GeoPackage Attribute Filler",
    page_icon="🗂️",
    layout="centered",
)

st.markdown(
    """
    <style>
        * { font-family: "Segoe UI", sans-serif; }
        .main { background-color: #f3f5f9; }
        .app-container {
            max-width: 900px;
            margin: 0 auto;
        }
        .section-box {
            background: rgba(255, 255, 255, 0.9);
            border-radius: 18px;
            padding: 2rem;
            box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
            border: 1px solid rgba(15, 23, 42, 0.08);
        }
        .upload-box {
            background: #f6f7fb;
            border: 1px dashed rgba(71, 85, 105, 0.4);
            border-radius: 16px;
            padding: 1.5rem;
        }
        .join-card {
            background: #ffffff;
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
        }
        .download-panel {
            background: #e6f7f1;
            border-left: 6px solid #0f9d58;
            border-radius: 16px;
            padding: 1.5rem;
            color: #0f5132;
        }
        .step-title {
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 0.6rem;
            color: #0f172a;
        }
        .footer {
            text-align: center;
            color: #475569;
            margin-top: 3rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


def read_geopackage(uploaded_file: BytesIO) -> gpd.GeoDataFrame:
    """Read an uploaded GeoPackage file and return a GeoDataFrame."""
    if uploaded_file is None:
        raise ValueError("Please upload a GeoPackage file.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".gpkg") as tmp:
        tmp.write(uploaded_file.getbuffer())
        temp_path = tmp.name

    try:
        return gpd.read_file(temp_path)
    finally:
        os.remove(temp_path)


def read_table(uploaded_file: BytesIO) -> pd.DataFrame:
    """Read a CSV or Excel file into a pandas DataFrame."""
    if uploaded_file is None:
        raise ValueError("Please upload a spreadsheet file.")

    file_name = uploaded_file.name.lower()
    uploaded_file.seek(0)
    if file_name.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if file_name.endswith(".xlsx"):
        return pd.read_excel(uploaded_file, engine="openpyxl")

    raise ValueError("Unsupported file type. Please upload CSV or Excel files.")


def merge_attributes(
    base_gdf: gpd.GeoDataFrame,
    attr_df: pd.DataFrame,
    left_field: str,
    right_field: str,
) -> gpd.GeoDataFrame:
    """Merge attribute table into GeoDataFrame without duplicate columns."""

    if left_field not in base_gdf.columns:
        raise KeyError(f"'{left_field}' not found in GeoPackage fields.")
    if right_field not in attr_df.columns:
        raise KeyError(f"'{right_field}' not found in spreadsheet fields.")

    duplicate_columns = [col for col in attr_df.columns if col in base_gdf.columns]
    duplicate_columns = [col for col in duplicate_columns if col != right_field]

    cleaned_df = attr_df.drop(columns=duplicate_columns, errors="ignore").copy()

    if left_field == right_field:
        join_column = "__join_field__"
        cleaned_df.rename(columns={right_field: join_column}, inplace=True)
    else:
        join_column = right_field

    merged = base_gdf.merge(
        cleaned_df,
        how="left",
        left_on=left_field,
        right_on=join_column,
    )

    for col in (right_field, "__join_field__"):
        if col in merged.columns and col != left_field:
            merged = merged.drop(columns=[col])

    return gpd.GeoDataFrame(merged, geometry=base_gdf.geometry.name, crs=base_gdf.crs)


def geopackage_to_buffer(gdf: gpd.GeoDataFrame, layer_name: str) -> BytesIO:
    """Write GeoDataFrame to a GeoPackage stored inside a BytesIO buffer."""
    safe_layer = layer_name.replace(" ", "_") or "merged_layer"
    buffer = BytesIO()

    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
        temp_path = tmp.name

    try:
        gdf.to_file(temp_path, driver="GPKG", layer=safe_layer)
        with open(temp_path, "rb") as f:
            buffer.write(f.read())
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

    buffer.seek(0)
    return buffer


st.markdown('<div class="app-container">', unsafe_allow_html=True)
st.title("🗂️ GeoPackage Attribute Filler")
st.subheader("Clean, professional tool for GIS attribute merging.")
st.markdown("<br>", unsafe_allow_html=True)

# Step 1 – Upload files
st.markdown('<div class="section-box">', unsafe_allow_html=True)
st.markdown('<div class="step-title">Step 1 – Upload files</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="upload-box">Upload a GeoPackage and a spreadsheet (CSV or Excel). They should share a common key for joining.</div>',
    unsafe_allow_html=True,
)
st.markdown("<br>", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    gpkg_file = st.file_uploader("GeoPackage (.gpkg)", type=["gpkg"], key="gpkg")
with col2:
    table_file = st.file_uploader("Spreadsheet (.csv, .xlsx)", type=["csv", "xlsx"], key="table")

st.markdown("</div>", unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

base_gdf = None
attr_df = None
if gpkg_file and table_file:
    try:
        base_gdf = read_geopackage(gpkg_file)
        attr_df = read_table(table_file)
        st.success(
            f"Loaded {len(base_gdf):,} features and {len(attr_df):,} attribute rows successfully."
        )
    except Exception as exc:
        st.error(f"Unable to load files: {exc}")

st.markdown("<br>", unsafe_allow_html=True)

# Step 2 – Select join fields
if base_gdf is not None and attr_df is not None:
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.markdown('<div class="step-title">Step 2 – Select join fields</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="join-card">Choose the matching fields from each dataset. Fields already present in the GeoPackage will be ignored from the spreadsheet to prevent duplicates.</div>',
        unsafe_allow_html=True,
    )
    st.markdown("<br>", unsafe_allow_html=True)

    left_field = st.selectbox("Field in GeoPackage", base_gdf.columns.tolist())
    right_field = st.selectbox("Field in Spreadsheet", attr_df.columns.tolist())
    st.markdown("</div>", unsafe_allow_html=True)
else:
    left_field = right_field = None

st.markdown("<br>", unsafe_allow_html=True)

# Step 3 – Merge & download
if base_gdf is not None and attr_df is not None and left_field and right_field:
    st.markdown('<div class="section-box">', unsafe_allow_html=True)
    st.markdown('<div class="step-title">Step 3 – Merge & download</div>', unsafe_allow_html=True)

    default_output_name = os.path.splitext(gpkg_file.name)[0] + "_merged"
    output_name = st.text_input("Output file name", value=default_output_name)

    if st.button("Merge attributes", use_container_width=True):
        try:
            merged_gdf = merge_attributes(base_gdf, attr_df, left_field, right_field)
            buffer = geopackage_to_buffer(merged_gdf, output_name)

            st.markdown(
                '<div class="download-panel">✅ Attributes merged successfully. Download the enriched GeoPackage below.</div>',
                unsafe_allow_html=True,
            )
            st.download_button(
                label=f"Download {output_name}.gpkg",
                data=buffer,
                file_name=f"{output_name}.gpkg",
                mime="application/geopackage+sqlite3",
                use_container_width=True,
            )
            st.dataframe(merged_gdf.head())
        except Exception as exc:
            st.error(f"Merging failed: {exc}")

    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    '<div class="footer">Developed by Eng. IRANZI Prince Jean Claude</div>',
    unsafe_allow_html=True,
)
st.markdown("</div>", unsafe_allow_html=True)

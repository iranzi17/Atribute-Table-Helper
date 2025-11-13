import streamlit as st
import geopandas as gpd
import pandas as pd
import os
import tempfile

st.title("📌 Clean GPKG Attribute Filler – No Duplicate Columns")

gpkg_file = st.file_uploader("Upload GeoPackage (.gpkg)", type=["gpkg"])
data_file = st.file_uploader("Upload Data File (CSV or Excel)", type=["csv", "xlsx"])

if gpkg_file and data_file:

    gdf = gpd.read_file(gpkg_file)
    st.success("GeoPackage Loaded ✔")

    if data_file.name.endswith(".csv"):
        df = pd.read_csv(data_file)
    else:
        df = pd.read_excel(data_file)

    st.success("Data Loaded ✔")

    st.write("### Select join fields")
    left_key = st.selectbox("Field in GeoPackage", gdf.columns)
    right_key = st.selectbox("Field in Data File", df.columns)

    if st.button("Merge Without Duplicates"):

        try:
            # ---- Remove data-file columns that already exist in GPKG ----
            df_clean = df[[c for c in df.columns if c not in gdf.columns or c == right_key]]

            # ---- Perform merge without keeping duplicate fields ----
            merged = gdf.merge(
                df_clean,
                left_on=left_key,
                right_on=right_key,
                how="left",
                suffixes=("", "")   # IMPORTANT: no _x, no _y
            )

            # Ensure the merged result keeps GeoDataFrame metadata
            merged_gdf = gpd.GeoDataFrame(
                merged,
                geometry=gdf.geometry.name,
                crs=gdf.crs
            )

            st.success("Attributes Merged Successfully ✔")
            st.dataframe(merged.head())

            # ---- Export to BytesIO ----
            with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
                temp_path = tmp.name

            try:
                merged_gdf.to_file(temp_path, driver="GPKG")
                with open(temp_path, "rb") as updated:
                    data_bytes = updated.read()

                st.download_button(
                    "⬇ Download Updated GeoPackage",
                    data=data_bytes,
                    file_name="updated_clean.gpkg",
                    mime="application/geopackage+sqlite3"
                )
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        except Exception as e:
            st.error(f"Error: {e}")

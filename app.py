import streamlit as st
import geopandas as gpd
import pandas as pd
import os
import tempfile

st.title("📌 Clean GPKG Attribute Filler – No Duplicate Columns")

gpkg_file = st.file_uploader("Upload GeoPackage (.gpkg)", type=["gpkg"])
data_file = st.file_uploader("Upload Data File (CSV or Excel)", type=["csv", "xlsx"])
output_name = st.text_input(
    "Name for the updated GeoPackage (without extension)",
    value="updated_clean",
    help="This will also be used for the GeoPackage layer name."
).strip()

if not output_name:
    output_name = "updated_clean"

layer_name = output_name.replace(" ", "_")

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
            # ---- Merge while keeping incoming fields separate ----
            merged = gdf.merge(
                df,
                left_on=left_key,
                right_on=right_key,
                how="left",
                suffixes=("", "_incoming")
            )

            # ---- Overwrite / append attributes without duplicate columns ----
            incoming_cols = [c for c in df.columns if c != right_key]
            for col in incoming_cols:
                incoming_name = f"{col}_incoming"

                if col in gdf.columns:
                    if incoming_name in merged.columns:
                        merged[col] = merged[incoming_name].combine_first(merged[col])
                        merged.drop(columns=[incoming_name], inplace=True)
                else:
                    # Column only exists in the data file; keep its values without suffix
                    if incoming_name in merged.columns:
                        merged.rename(columns={incoming_name: col}, inplace=True)

            # Drop duplicate join column if user selected different fields
            if right_key in merged.columns and right_key != left_key:
                merged.drop(columns=[right_key], inplace=True)

            # Ensure the merged result keeps GeoDataFrame metadata
            merged_gdf = gpd.GeoDataFrame(
                merged,
                geometry=gdf.geometry.name,
                crs=gdf.crs
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
                merged_gdf.to_file(temp_path, driver="GPKG", layer=layer_name)
                with open(temp_path, "rb") as updated:
                    data_bytes = updated.read()

                st.download_button(
                    "⬇ Download Updated GeoPackage",
                    data=data_bytes,
                    file_name=f"{output_name}.gpkg",
                    mime="application/geopackage+sqlite3"
                )
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        except Exception as e:
            st.error(f"Error: {e}")
